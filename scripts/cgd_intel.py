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

MIN_COMPETITORS = 2     # distinct winners ขั้นต่ำก่อนหยุด fallback
SHOW_N = 3              # จำนวนบริษัทที่โชว์
MIN_GAMES_FOR_IQR = 3   # ต่ำกว่านี้โชว์แค่ median
IQR_WIDE = 20           # p75-p25 เกินนี้ = ช่วงกว้าง (ลดความเชื่อมั่น)


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


def _fetch(conn, province: str, tokens: list, *, subdistrict=None, district=None) -> list:
    """ดึงงาน competitive ของ work-type (LIKE any token) ใน province + (เลือก subdistrict/district).
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


def _fetch_winner(conn, winner: str, tokens: list) -> list:
    """ส่วนลดของ winner รายนั้น (work-type เดียวกัน, competitive, recent FY). คือประวัติบริษัท
    (cgd_winners = subset target provinces อยู่แล้ว → ไม่ต้อง filter province)."""
    fy_ph = ",".join("?" for _ in RECENT_FY)
    pt_ph = ",".join("?" for _ in COMPETITIVE_SET)
    like = " OR ".join("project_name LIKE ?" for _ in tokens)
    params = [winner, *RECENT_FY, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    try:
        cur = conn.execute(
            "SELECT discount_pct FROM cgd_winners WHERE winner=? AND win_price>0 "
            f"AND fiscal_year IN ({fy_ph}) AND proc_type IN ({pt_ph}) AND ({like})", params)
        return [r[0] for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def company_stats(winner: str, tokens: list, conn) -> dict:
    """median (+IQR ถ้า games≥MIN_GAMES_FOR_IQR) ส่วนลดจากประวัติบริษัท."""
    rows = _fetch_winner(conn, winner, tokens)
    discs = [d for d in rows if d is not None]
    out = {"games": len(rows), "median": _pct(discs, 50), "p25": None, "p75": None}
    if len(discs) >= MIN_GAMES_FOR_IQR:
        out["p25"], out["p75"] = _pct(discs, 25), _pct(discs, 75)
    return out


def confidence_label(area_n: int, p25, p75) -> str:
    """ป้ายความเชื่อมั่นทางสถิติ (จาก n + ความกว้าง IQR). คนละมิติกับ relevance (= header level)."""
    wide = p25 is not None and p75 is not None and (p75 - p25) > IQR_WIDE
    if area_n < 10:
        return "🔴 ข้อมูลน้อย — โปรดใช้วิจารณญาณ"
    if area_n < 30 or wide:
        return "🟡 เชื่อมั่นปานกลาง — ข้อมูลน้อย/ช่วงกว้าง (ดูเป็นแนวโน้ม ไม่ใช่ราคาตายตัว)"
    return "🟢 เชื่อถือได้ — ข้อมูลมากพอ"


def intel_context(province: str, project_name: str, dept_name: str = "",
                  project_id: str = "", conn=None) -> dict | None:
    """resolve+select+stats ครั้งเดียว → คืน context: lines (competitor block) + stats
    (area_p25/area_p75/top_name/top_median) สำหรับ price prediction reuse (DRY).
    None ถ้าไม่มี work-type/คู่แข่ง/error. ห่อ try/except — ห้าม throw."""
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
            # metric: aggregate location_resolution_source ภายหลัง (geo/tambon/dept/province %)
            _log.info("intel_resolve project=%s source=%s conf=%s amphoe=%s",
                      project_id, loc["source"], loc["location_confidence"], loc["amphoe"])
            rows, scope, _level = select_competitors(province, tokens, loc["tambon"], loc["amphoe"], conn)
            if not rows:
                return None
            counts = Counter(r["winner"] for r in rows if r.get("winner"))
            discs = [r["discount_pct"] for r in rows if r.get("discount_pct") is not None]
            area_n = len(rows)
            p25, p75 = _pct(discs, 25), _pct(discs, 75)
            top3 = counts.most_common(SHOW_N)
            top_name = top3[0][0] if top3 else None
            top_median = company_stats(top_name, tokens, conn)["median"] if top_name else None
            lines = [f"💡 ราคาอ้างอิง ({scope})", "🏆 คู่แข่งแถบนี้:"]
            for winner, _ in top3:
                cs = company_stats(winner, tokens, conn)
                nm = (winner or "?")[:28]
                if cs["p25"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}% "
                                 f"({cs['p25']:.0f}–{cs['p75']:.0f}%)")
                elif cs["median"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}%")
                else:
                    lines.append(f"  • {nm} · {cs['games']} งาน")
            if p75:
                lines.append(f"📊 ภาพรวม: งานแบบนี้แถบนี้มักลด {p25:.0f}–{p75:.0f}% จากราคากลาง")
            else:
                lines.append(f"📊 ภาพรวม {area_n} งาน")
            lines.append(confidence_label(area_n, p25, p75))
            return {"lines": lines, "scope": scope, "rows": rows,
                    "area_p25": p25, "area_p75": p75,
                    "top_name": top_name, "top_median": top_median}
        finally:
            if own:
                conn.close()
    except Exception:
        return None


def intel_lines(province: str, project_name: str, dept_name: str = "",
                project_id: str = "", conn=None) -> list:
    """บรรทัด 💡 competitor intel (back-compat wrapper รอบ intel_context). [] ถ้าไม่มีข้อมูล."""
    ctx = intel_context(province, project_name, dept_name, project_id, conn)
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


def predict_lines(p: dict) -> list:
    """บรรทัด 💵 คาดราคา — โชว์ % (ที่มา) ก่อน → ราคา (ผล). framing คาดการณ์ ไม่ใช่คำสั่ง."""
    if not p:
        return []
    out = [f"💵 คาดราคาที่จะชนะ (ราคากลาง {p['budget']/1e6:.1f} ลบ.):",
           f"   • ตลาดแถบนี้ลด {p['area_disc_lo']:.0f}–{p['area_disc_hi']:.0f}% → "
           f"ชนะราว {p['area_price_lo']/1e6:.1f}–{p['area_price_hi']/1e6:.1f} ลบ."]
    if p.get("top_price") is not None:
        out.append(f"   • เจ้าตัวเต็ง ({(p['top_name'] or '?')[:20]}) มักลด ~{p['top_disc']:.0f}% → "
                   f"~{p['top_price']/1e6:.1f} ลบ.")
    out.append("   * ประเมินจากสถิติ โปรดคำนวณต้นทุนจริงประกอบ")
    return out
