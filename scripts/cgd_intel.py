"""cgd_intel.py — competitor intel ระดับท้องถิ่นจาก cgd_winners: ใครคือคู่แข่งงานนี้ + เขาลดราคายังไง.
descriptive เท่านั้น (ตลาดเป็นยังไง) ไม่ prescriptive (ไม่บอกราคาที่ควรยื่น).
พระเอก = โปรไฟล์คู่แข่งรายบริษัท (selection ไล่ระดับ ตำบล→อำเภอ→จังหวัด, stat จากประวัติบริษัท)
+ ภาพรวมเสริม + ป้ายความเชื่อมั่น. ใช้แนบการ์ด D0 (followed_bid_open). intel = value-add — ห้ามทำ notification พัง."""
import json
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_log = logging.getLogger("cgd_intel")

_KW_PATH = Path(__file__).parent.parent / "config" / "matching_preferences.json"

# competitive-set: เฉพาะวิธีที่ "แข่งราคาจริง" — CGD 91% เป็นเฉพาะเจาะจง/ตกลงราคา (disc≈0)
# ลาก median ลง 0 ทำให้ตัวเลขลวง. คู่แข่ง = บริษัทที่เล่นในสนามประมูลเท่านั้น (กัญจน์เน้น).
COMPETITIVE_SET = (
    "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
    "ประกวดราคาด้วยวิธีการทางอิเล็กทรอนิกส์",
    "สอบราคา",
    "คัดเลือก",
)
# 3 ปีงบล่าสุด — ราคาตลาดเก่าไม่สะท้อนปัจจุบัน (เงินเฟ้อ/ราคาวัสดุ)
RECENT_FY = ("2566", "2567", "2568")

# road subtype — แยก reference set คาดราคา เพราะ %ลดต่างกันชัด (evidence:
# data/probe_road_subtype_discount.json, กัญจน์ 2026-06-09 — concrete median ~25% vs
# asphalt ~14% รูปร่างต่างกันมาก → pool รวมกันทำให้คาดราคา bias). asphalt ชนะ concrete
# เพราะ "แอสฟัลท์ติกคอนกรีต" = ผิวแอสฟัลต์ (ไม่ใช่คอนกรีต).
_ASPHALT_KW = ("แอสฟัลท์", "แอสฟัลต์", "แอสฟัลติก", "ลาดยาง", "พาราแอสฟัลต์",
               "พาราแอสฟัลท์", "เคพซีล")
_CONCRETE_KW = ("คอนกรีตเสริมเหล็ก", "คสล", "ค.ส.ล", "คอนกรีต")

MIN_COMPETITORS = 2     # distinct winners ขั้นต่ำก่อนหยุด fallback
SHOW_N = 3              # จำนวนบริษัทที่โชว์
MIN_GAMES_FOR_IQR = 3   # ต่ำกว่านี้โชว์แค่ median
IQR_WIDE = 20           # p75-p25 เกินนี้ = ช่วงกว้าง (ลดความเชื่อมั่น)
TAMBON_MIN = 5          # ตำบลมีงาน < นี้ → โชว์บล็อกอำเภอคู่กันด้วย


def _load_keywords() -> list:
    return json.load(open(_KW_PATH, encoding="utf-8")).get("keywords", [])


def match_keywords(project_name: str, keywords: list = None) -> list:
    """คืน work-type tokens ที่ปรากฏในชื่องาน (vocab เดียวกับ job_matcher). ไม่ซ้ำ."""
    kws = keywords if keywords is not None else _load_keywords()
    name = project_name or ""
    out = []
    for kw in kws:
        if kw and kw in name and kw not in out:
            out.append(kw)
    return out


def road_subtype(project_name: str):
    """ประเภทผิวถนนจากชื่องาน: 'asphalt' | 'concrete' | None (ไม่ใช่ถนน/ระบุไม่ได้).
    asphalt ชนะ concrete — 'แอสฟัลท์ติกคอนกรีต' = ผิวแอสฟัลต์. ใช้แยก reference set ตอนคาดราคา
    (concrete vs asphalt %ลดต่างกันชัด). None → ไม่ filter subtype (pool เดิม)."""
    n = project_name or ""
    if any(k in n for k in _ASPHALT_KW):
        return "asphalt"
    if any(k in n for k in _CONCRETE_KW):
        return "concrete"
    return None


def resolve_location(project_id: str, project_name: str, dept_name: str, province: str, conn) -> dict:
    """runtime-compute (ไม่ persist) ตำบล+อำเภอ แม่น→หยาบ: [moi=phaseB] → geo(lat/lng) →
    unique-tambon → dept → province. คืน {tambon, amphoe, location_confidence, source,
    resolution_trace(list)}. query project_locations ครั้งเดียว. resolve ไม่ได้ → amphoe=None
    (select_competitors degrade province เดิม — precision ไม่แย่กว่าเดิม)."""
    import geo_reverse
    import job_matcher as jm
    trace = ["moi: deferred (phaseB)"]
    moi_name = lat = lng = ""
    if project_id:
        try:
            r = conn.execute("SELECT moi_name, latitude, longitude FROM project_locations "
                             "WHERE project_id=?", (project_id,)).fetchone()
            if r:
                moi_name, lat, lng = (r[0] or ""), (r[1] or ""), (r[2] or "")
        except sqlite3.OperationalError:
            pass   # ไม่มี table → ข้ามไป fallback
    try:
        name_tb = jm.tambon_from_name(project_name) or ""
    except Exception:
        name_tb = ""
    tb = moi_name or name_tb
    # ชั้น 2: geo (lat/lng corrected ตอน capture แล้ว — latitude=lat จริง)
    geo = geo_reverse.reverse_geocode(lat, lng) if (lat and lng) else None
    if geo:
        _prov, amphoe, gtb, dist = geo
        conf = "HIGH" if dist < 0.5 else "MEDIUM" if dist < 2 else "LOW"
        trace.append(f"geo: {amphoe} dist={dist*1000:.0f}m → {conf}")
        return {"tambon": tb or gtb, "amphoe": amphoe, "location_confidence": conf,
                "source": "geo", "resolution_trace": trace}
    trace.append("geo: no latlng")
    # ชั้น 3: unique tambon (ไม่ซ้ำในจังหวัด)
    if tb:
        amphoes = geo_reverse.amphoes_of_tambon(province, tb)
        if len(amphoes) == 1:
            trace.append(f"tambon: {tb} unique → {amphoes[0]}")
            return {"tambon": tb, "amphoe": amphoes[0], "location_confidence": "HIGH",
                    "source": "tambon", "resolution_trace": trace}
        trace.append(f"tambon: {tb} ambiguous({len(amphoes)})")
    # ชั้น 4: dept เดาอำเภอ
    try:
        dtb = jm.tambon_from_dept(dept_name) or ""
    except Exception:
        dtb = ""
    if dtb:
        damphoes = geo_reverse.amphoes_of_tambon(province, dtb)
        if len(damphoes) == 1:
            trace.append(f"dept: {dtb} → {damphoes[0]}")
            return {"tambon": tb or dtb, "amphoe": damphoes[0], "location_confidence": "MEDIUM",
                    "source": "dept", "resolution_trace": trace}
        trace.append(f"dept: {dtb} ambiguous/none")
    # ชั้น 5: province degrade
    trace.append("province degrade")
    return {"tambon": tb, "amphoe": None, "location_confidence": "LOW",
            "source": "province", "resolution_trace": trace}


def _pct(values: list, p: float):
    """percentile แบบ linear interpolation (deterministic). values ไม่ต้อง sort มาก่อน."""
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(v) - 1)
    if f == c:
        return v[f]
    return v[f] + (v[c] - v[f]) * (k - f)


def _fetch(conn, province: str, tokens: list, *, subdistrict=None, district=None, subtype=None) -> list:
    """ดึงงาน competitive ของ work-type (LIKE any token) ใน province + (เลือก subdistrict/district).
    subtype='concrete'/'asphalt' → จำกัด reference เฉพาะประเภทผิวถนนเดียวกัน (ดู road_subtype).
    คืน list[dict] (รวม district/subdistrict). graceful [] ถ้าไม่มี table/column."""
    fy_ph = ",".join("?" for _ in RECENT_FY)
    pt_ph = ",".join("?" for _ in COMPETITIVE_SET)
    like = " OR ".join("project_name LIKE ?" for _ in tokens)
    where = ["province=?", "win_price>0", f"fiscal_year IN ({fy_ph})",
             f"proc_type IN ({pt_ph})", f"({like})"]
    params = [province, *RECENT_FY, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    if subdistrict is not None:
        where.append("subdistrict=?"); params.append(subdistrict)
    if district is not None:
        where.append("district=?"); params.append(district)
    # subtype filter — concrete อ้างอิง concrete, asphalt อ้างอิง asphalt (asphalt ชนะ:
    # concrete ต้องไม่มี keyword asphalt เลย เพื่อกัน 'แอสฟัลท์ติกคอนกรีต' หลุดเข้า concrete)
    if subtype == "asphalt":
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in _ASPHALT_KW) + ")")
        params += [f"%{k}%" for k in _ASPHALT_KW]
    elif subtype == "concrete":
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in _CONCRETE_KW) + ")")
        params += [f"%{k}%" for k in _CONCRETE_KW]
        where.append("NOT (" + " OR ".join("project_name LIKE ?" for _ in _ASPHALT_KW) + ")")
        params += [f"%{k}%" for k in _ASPHALT_KW]
    try:
        cur = conn.execute(
            "SELECT project_name, winner, win_price, discount_pct, district, subdistrict "
            "FROM cgd_winners WHERE " + " AND ".join(where), params)
        return [{"project_name": r[0], "winner": r[1], "win_price": r[2],
                 "discount_pct": r[3], "district": r[4], "subdistrict": r[5]}
                for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []   # ไม่มี table/column cgd_winners → graceful


def _distinct_winners(rows: list) -> int:
    return len({r["winner"] for r in rows if r.get("winner")})


def select_competitors(province: str, tokens: list, tambon: str, amphoe, conn) -> tuple:
    """เลือกคู่แข่งจาก (ตำบล,อำเภอ) ที่ resolve มาแล้ว. คืน (rows, scope_label, level).
    amphoe+tambon → tambon level (subdistrict+district) → fallback อำเภอ → จังหวัด.
    amphoe=None → จังหวัด ทันที (precision preserve — ไม่ query district IS NULL).
    competitive-set ถูกกรองใน _fetch แล้ว."""
    wt = tokens[0] if tokens else "งาน"
    if amphoe and tambon:
        trows = _fetch(conn, province, tokens, subdistrict=tambon, district=amphoe)
        if _distinct_winners(trows) >= 1:
            return trows, f"งาน{wt} ต.{tambon} อ.{amphoe}", "tambon"
    if amphoe:
        arows = _fetch(conn, province, tokens, district=amphoe)
        if _distinct_winners(arows) >= MIN_COMPETITORS:
            return arows, f"งาน{wt} อ.{amphoe}", "amphoe"
    prows = _fetch(conn, province, tokens)
    if _distinct_winners(prows) >= 1:
        return prows, f"งาน{wt}ใน{province}", "province"
    return [], "", "province"


def _company_stats_from_rows(rows: list, winner: str) -> dict:
    """สถิติคู่แข่ง scope-local — นับเฉพาะงานของ winner ใน rows ที่ส่งมา (ไม่ใช่ประวัติทั้งบริษัท).
    games<MIN_GAMES_FOR_IQR → ไม่มี IQR (จุดน้อยเกินจะมีช่วง)."""
    discs = [r["discount_pct"] for r in rows
             if r.get("winner") == winner and r.get("discount_pct") is not None]
    games = sum(1 for r in rows if r.get("winner") == winner)
    out = {"games": games, "median": _pct(discs, 50), "p25": None, "p75": None}
    if len(discs) >= MIN_GAMES_FOR_IQR:
        out["p25"], out["p75"] = _pct(discs, 25), _pct(discs, 75)
    return out


def _conf_tag(n: int, p25, p75) -> str:
    """ป้ายความเชื่อมั่นแบบสั้น (ต่อบล็อก)."""
    wide = p25 is not None and p75 is not None and (p75 - p25) > IQR_WIDE
    if n < 10:
        return "🔴 ข้อมูลน้อย"
    if n < 30 or wide:
        return "🟡"
    return "🟢"


def _scope_block(rows: list, label: str) -> tuple:
    """บล็อกคู่แข่ง 1 scope (ตำบล/อำเภอ/จังหวัด). สถิติทุกตัว scope-local จาก rows.
    คืน (lines, p25, p75, n, top_name, top_median)."""
    counts = Counter(r["winner"] for r in rows if r.get("winner"))
    discs = [r["discount_pct"] for r in rows if r.get("discount_pct") is not None]
    p25, p75 = _pct(discs, 25), _pct(discs, 75)
    n = len(rows)
    top3 = counts.most_common(SHOW_N)
    top_name = top3[0][0] if top3 else None
    top_median = _company_stats_from_rows(rows, top_name)["median"] if top_name else None
    lines = [f"{label} — {n} งาน {_conf_tag(n, p25, p75)}"]
    for w, _ in top3:
        cs = _company_stats_from_rows(rows, w)
        nm = w or "?"                       # ชื่อเต็ม (text ธรรมดา ไม่จำกัดความยาว)
        if cs["p25"] is not None:
            lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}% "
                         f"({cs['p25']:.0f}–{cs['p75']:.0f}%)")
        elif cs["median"] is not None:
            lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}%")
        else:
            lines.append(f"  • {nm} · {cs['games']} งาน")
    if p75:
        lines.append(f"  📊 ส่วนลด {p25:.0f}–{p75:.0f}%")
    return lines, p25, p75, n, top_name, top_median


def confidence_label(area_n: int, p25, p75) -> str:
    """ป้ายความเชื่อมั่นทางสถิติ (จาก n + ความกว้าง IQR). คนละมิติกับ relevance (= header level)."""
    wide = p25 is not None and p75 is not None and (p75 - p25) > IQR_WIDE
    if area_n < 10:
        return "🔴 ข้อมูลน้อย — โปรดใช้วิจารณญาณ"
    if area_n < 30 or wide:
        return "🟡 เชื่อมั่นปานกลาง — ข้อมูลน้อย/ช่วงกว้าง (ดูเป็นแนวโน้ม ไม่ใช่ราคาตายตัว)"
    return "🟢 เชื่อถือได้ — ข้อมูลมากพอ"


def _build_intel(conn, province: str, tokens: list, tambon, amphoe, budget, subtype=None) -> dict | None:
    """ประกอบ intel dual-block จาก (ตำบล,อำเภอ) ที่ resolve มาแล้ว (แยกจาก resolve เพื่อ test ง่าย).
    - บล็อกตำบล: เสมอ (ถ้ามีชื่อตำบล) — สถิติเฉพาะงานในตำบล. 0 งาน → 'ยังไม่มีงานประเภทนี้'
    - บล็อกอำเภอ: เพิ่มเมื่อตำบล < TAMBON_MIN — สถิติเฉพาะงานในอำเภอ
    - amphoe=None → บล็อกจังหวัดเดี่ยว. คาดราคาอิงตำบลก่อน (ไม่มี→อำเภอ/จังหวัด).
    คืน {lines, prediction} · None ถ้าไม่มีคู่แข่งจริงเลย."""
    wt = tokens[0] if tokens else "งาน"
    blocks = []
    pp25 = pp75 = ptop = ptopm = None
    basis = ""
    if amphoe:
        header = (f"💡 ราคาอ้างอิง (งาน{wt}"
                  + (f" ต.{tambon}" if tambon else "") + f" อ.{amphoe})")
        t_rows = _fetch(conn, province, tokens, subdistrict=tambon, district=amphoe, subtype=subtype) if tambon else []
        tn = len(t_rows)
        if tambon:
            if t_rows:
                tl, t25, t75, _n, ttop, ttopm = _scope_block(t_rows, f"🏘 ในตำบล{tambon}")
                blocks += tl
                pp25, pp75, ptop, ptopm, basis = t25, t75, ttop, ttopm, "ตำบล"
            else:
                blocks.append(f"🏘 ในตำบล{tambon} — ยังไม่มีงานประเภทนี้")
        if tn < TAMBON_MIN:                       # ตำบลน้อย → โชว์อำเภอคู่กัน
            a_rows = _fetch(conn, province, tokens, district=amphoe, subtype=subtype)
            if a_rows:
                al, a25, a75, _n, atop, atopm = _scope_block(a_rows, f"🏙 ในอำเภอ{amphoe}")
                blocks += al
                if pp25 is None:                  # ตำบลไม่มี → คาดอิงอำเภอ
                    pp25, pp75, ptop, ptopm, basis = a25, a75, atop, atopm, "อำเภอ"
    else:
        p_rows = _fetch(conn, province, tokens, subtype=subtype)
        if not p_rows:
            return None
        pl, p25, p75, _n, ptopn, ptopmd = _scope_block(p_rows, f"🏙 ใน{province}")
        blocks += pl
        pp25, pp75, ptop, ptopm, basis = p25, p75, ptopn, ptopmd, "จังหวัด"
        header = f"💡 ราคาอ้างอิง (งาน{wt}ใน{province})"
    if not blocks or all("ยังไม่มีงาน" in b for b in blocks):
        return None                               # ไม่มีคู่แข่งจริงเลย → omit
    lines = [header, ""] + blocks
    pred = predict_winning_price(budget, pp25, pp75, ptop, ptopm)
    if pred:
        lines += [""] + predict_lines(pred, basis)
    return {"lines": lines, "prediction": pred, "tambon": tambon, "amphoe": amphoe}


def intel_context(province: str, project_name: str, dept_name: str = "",
                  project_id: str = "", budget=0, conn=None) -> dict | None:
    """resolve (ตำบล,อำเภอ) → ประกอบ dual-block intel + price prediction (scope-local).
    คืน {lines, prediction(dict|None)} · None ถ้าไม่มี work-type/คู่แข่ง/error. ห่อ try/except."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return None
        own = conn is None
        if own:
            from Sebastian_Customer_DB import get_connection
            conn = get_connection()
        try:
            loc = resolve_location(project_id, project_name, dept_name, province, conn)
            _log.info("intel_resolve project=%s source=%s amphoe=%s",
                      project_id, loc["source"], loc["amphoe"])
            return _build_intel(conn, province, tokens, loc["tambon"], loc["amphoe"],
                                budget, road_subtype(project_name))
        finally:
            if own:
                conn.close()
    except Exception:
        return None


def intel_lines(province: str, project_name: str, dept_name: str = "",
                project_id: str = "", conn=None) -> list:
    """บรรทัด 💡 competitor intel (back-compat wrapper). [] ถ้าไม่มีข้อมูล."""
    ctx = intel_context(province, project_name, dept_name, project_id, 0, conn)
    return ctx["lines"] if ctx else []


def predict_winning_price(budget, area_p25, area_p75, top_name=None, top_median=None) -> dict | None:
    """คาดช่วงราคาชนะ = ราคากลาง × (1 − ส่วนลด). ช่วงตลาด p25/p75 + เจ้าตัวเต็ง. None ถ้าข้อมูลไม่พอ.
    prediction เชิงสถิติ ไม่ใช่คำสั่ง (ดู predict_lines disclaimer)."""
    if not budget or area_p25 is None or area_p75 is None:
        return None
    b = float(budget)
    return {
        "budget": b, "area_disc_lo": area_p25, "area_disc_hi": area_p75,
        "area_price_lo": round(b * (1 - area_p75 / 100)), "area_price_hi": round(b * (1 - area_p25 / 100)),
        "top_name": top_name, "top_disc": top_median,
        "top_price": round(b * (1 - top_median / 100)) if top_median is not None else None,
    }


def compare_prediction(project_id: str, actual_price, conn=None) -> dict | None:
    """เทียบราคาจริง vs คำทำนาย → in_range + error% → update DB (closed-loop).
    None ถ้าไม่มี prediction / actual แปลงเป็นตัวเลขไม่ได้."""
    from Sebastian_Customer_DB import get_prediction, update_prediction_actual
    try:
        actual = float(actual_price)
    except (TypeError, ValueError):
        return None
    if not actual:
        return None
    p = get_prediction(project_id)
    if not p or p.get("area_price_lo") is None or p.get("area_price_hi") is None:
        return None
    lo, hi = p["area_price_lo"], p["area_price_hi"]
    in_range = lo <= actual <= hi
    mid = (lo + hi) / 2
    error_pct = round(abs(actual - mid) / actual * 100, 1)
    update_prediction_actual(project_id, round(actual), 1 if in_range else 0, error_pct)
    return {"in_range": in_range, "error_pct": error_pct,
            "area_price_lo": lo, "area_price_hi": hi, "actual": round(actual)}


def predict_lines(p: dict, basis: str = "ตำบล") -> list:
    """บรรทัด 💵 คาดราคา — โชว์ % (ที่มา) ก่อน → ราคา (ผล) + บอก basis (ตำบล/อำเภอ/จังหวัด).
    framing คาดการณ์ ไม่ใช่คำสั่ง. คู่แข่งโชว์ในบล็อกด้านบนแล้ว → ที่นี่เอาแค่ช่วงรวม."""
    if not p:
        return []
    lo = round(p["area_price_lo"] / 1000) * 1000   # ปัดหลักพัน — สื่อว่าเป็นค่าประมาณ
    hi = round(p["area_price_hi"] / 1000) * 1000
    return [f"💵 คาดราคาที่จะชนะ (ราคากลาง {p['budget']:,.0f} บาท):",
            f"   • อิง{basis} ลด {p['area_disc_lo']:.0f}–{p['area_disc_hi']:.0f}% → "
            f"ชนะราว {lo:,.0f}–{hi:,.0f} บาท",
            "   * ประเมินจากสถิติ โปรดคำนวณต้นทุนจริงประกอบ"]
