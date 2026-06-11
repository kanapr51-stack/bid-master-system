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

# water/irrigation subtype — แยก reference set เพราะ %ลดต่างกันชัด (evidence:
# data/subtype_variance_report.json, กัญจน์ 2026-06-11 — ขุดลอก/ขุดสระ median ~37% vs
# ฝาย/ประปา ~10-13% gap 26 จุด > ถนน 11 จุด). งานขุด = แทบไม่มีต้นทุนวัสดุ (เครื่องจักร+
# น้ำมัน) ลดลึก; ฝาย/ประปา/อ่าง = มีโครงสร้าง คสล.+อุปกรณ์ ลดตื้น.
# excavation ชนะ structure — 'ขุดลอกอ่างเก็บน้ำ' = งานขุด (ต้นทุนหลัก = การขุด).
_WATER_EXCAV_KW = ("ขุดลอก", "ขุดสระ", "ขุดคลอง", "ขุดร่อง", "ขุดลำห้วย", "ขุดลำ")
_WATER_STRUCT_KW = ("ฝาย", "ประปา", "อ่างเก็บน้ำ", "ดาดคอนกรีต", "คลองส่งน้ำ",
                    "ดาด", "สถานีสูบน้ำ", "ระบบส่งน้ำ")

# agency market regime — ตัวขับ %ส่วนลดที่แท้จริง (evidence: docs/research_market_regime_discount.md,
# กัญจน์ 2026-06-11). งานท้องถิ่น (อปท.) แข่งดุ median ~28% vs งานส่วนกลาง/กรมทางหลวง ชิดเพดาน ~0.3%
# — pool รวมกันทำให้คาดราคางานท้องถิ่นต่ำกว่าจริง. ไม่ใช่ budget/ชั้นผู้รับเหมา (corr budget-ผู้ยื่น=0).
_LOCAL_AGENCY_KW = ("องค์การบริหารส่วนตำบล", "องค์การบริหารส่วนจังหวัด", "เทศบาล",
                    "เมืองพัทยา", "กรุงเทพมหานคร", "อบต.", "อบจ.")

MIN_COMPETITORS = 2     # distinct winners ขั้นต่ำก่อนหยุด fallback
SHOW_N = 3              # จำนวนบริษัทที่โชว์
MIN_GAMES_FOR_IQR = 3   # ต่ำกว่านี้โชว์แค่ median
IQR_WIDE = 20           # p75-p25 เกินนี้ = ช่วงกว้าง (ลดความเชื่อมั่น)
TAMBON_MIN = 5          # ตำบลมีงาน < นี้ → โชว์บล็อกอำเภอคู่กันด้วย
CONTESTED_MIN_DISCOUNT = 15   # ถนน/งานขุด — valley กว้าง (bimodal gap ~9-17%) competition เริ่มสูง
CONTESTED_MIN_DEFAULT = 5     # อาคาร/ราง/ทั่วไป/ฝาย-ประปา — competition เริ่มหลัง spike ~5%
# floor "งานแข่งจริง" ต่างตามชนิดงาน — โหมดไม่แข่ง = spike 0-4% เหมือนกัน แต่โหมดแข่งเริ่มต่างกัน
# (evidence: histogram local market — ถนน competition mode 25%+ valley 5-24 → floor 15;
# อาคาร/water_struct competition เริ่ม ~5% → floor 5. ถ้าใช้ 15 กับอาคารจะตัดงานแข่งจริง 5-14% ทิ้ง).
_CONTESTED_FLOOR_BY_SUBTYPE = {
    "asphalt": 15, "concrete": 15, "water_excav": 15, "water_struct": 5,
}


def _contested_floor(subtype=None, tokens=None) -> float:
    """ส่วนลดขั้นต่ำที่ถือว่า 'มีคู่แข่งจริง' ตามชนิดงาน: ถนน/ขุด=15 (valley กว้าง),
    อาคาร/ราง/ฝาย-ประปา/ทั่วไป=5 (competition เริ่มหลัง spike). ถนนไม่ระบุผิว (ลูกรัง) → 15 จาก tokens."""
    if subtype in _CONTESTED_FLOOR_BY_SUBTYPE:
        return _CONTESTED_FLOOR_BY_SUBTYPE[subtype]
    if tokens and any("ถนน" in t for t in tokens):   # ถนนทั่วไป/ลูกรัง — valley กว้างเหมือนกัน
        return CONTESTED_MIN_DISCOUNT
    return CONTESTED_MIN_DEFAULT


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


def water_subtype(project_name: str):
    """ประเภทงานแหล่งน้ำจากชื่องาน: 'water_excav' (ขุด ลดลึก ~37%) | 'water_struct'
    (ฝาย/ประปา/อ่าง ลดตื้น ~10-13%) | None (ไม่ใช่งานน้ำ/ระบุไม่ได้ → pool เดิม).
    excavation ชนะ structure — 'ขุดลอกอ่างเก็บน้ำ' = งานขุด. ใช้แยก reference set ตอนคาดราคา."""
    n = project_name or ""
    if any(k in n for k in _WATER_EXCAV_KW):
        return "water_excav"
    if any(k in n for k in _WATER_STRUCT_KW):
        return "water_struct"
    return None


def agency_market(dept_name: str):
    """ระบอบตลาดจากชื่อหน่วยงาน: 'local' (อปท. — อบต./เทศบาล/อบจ. แข่งดุ ~28%) |
    'central' (ส่วนกลาง/กรม/ทางหลวง — ชิดเพดาน ~0.3%) | None (ไม่มีชื่อหน่วยงาน → ไม่ filter).
    ใช้แยก reference set ตอนคาดราคา — งานท้องถิ่นต้องอ้างอิงงานท้องถิ่นเท่านั้น (ตัวขับส่วนลดจริง)."""
    if not dept_name:
        return None
    return "local" if any(k in dept_name for k in _LOCAL_AGENCY_KW) else "central"


def work_nature(project_name: str) -> str:
    """ลักษณะงาน: 'purchase' (จัด*ซื้อ*วัสดุ เช่น เหล็ก/คอนกรีตผสมเสร็จ ลด ~0-2%) vs
    'construction' (*จ้างก่อสร้าง* ลด ~25-38%). คนละ pool — pool รวมกันทำช่วงคาดราคาเพี้ยน
    (งานซื้อชื่อมี 'คอนกรีต/ถนน' หลุดเข้า reference งานก่อสร้าง). default = construction."""
    return "purchase" if "ซื้อ" in (project_name or "") else "construction"


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


def _fetch(conn, province: str, tokens: list, *, subdistrict=None, district=None,
           subtype=None, include_old=False, nature=None, contested_only=False, market=None) -> list:
    """ดึงงาน competitive ของ work-type (LIKE any token) ใน province + (เลือก subdistrict/district).
    subtype='concrete'/'asphalt' → จำกัด reference เฉพาะประเภทผิวถนนเดียวกัน (ดู road_subtype).
    nature='construction'/'purchase' → จำกัดลักษณะงาน (จ้างก่อสร้าง vs ซื้อวัสดุ ลด%ต่างกันมาก).
    market='local'/'central' → จำกัดระบอบตลาด (ท้องถิ่นแข่งดุ vs ส่วนกลางชิดเพดาน — ตัวขับส่วนลดจริง).
    include_old=True → ไม่จำกัด 3 ปีล่าสุด (ย้อนทุกปีงบ) สำหรับพื้นที่ข้อมูลน้อย.
    คืน list[dict] (รวม district/subdistrict). graceful [] ถ้าไม่มี table/column."""
    pt_ph = ",".join("?" for _ in COMPETITIVE_SET)
    like = " OR ".join("project_name LIKE ?" for _ in tokens)
    where = ["province=?", "win_price>0", f"proc_type IN ({pt_ph})", f"({like})"]
    params = [province, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    # ลักษณะงาน — งาน 'ซื้อ' (วัสดุ ลด ~0-2%) คนละ pool กับ 'จ้างก่อสร้าง' (ลด ~25-38%)
    if nature == "construction":
        where.append("project_name NOT LIKE ?"); params.append("%ซื้อ%")
    elif nature == "purchase":
        where.append("project_name LIKE ?"); params.append("%ซื้อ%")
    # contested = เฉพาะงานที่มีคู่แข่งจริง (ตัดโหมด no-competition ~0% ที่ทำช่วงเพี้ยน)
    if contested_only:
        where.append("discount_pct >= ?"); params.append(_contested_floor(subtype, tokens))
    if not include_old:                       # default = 3 ปีงบล่าสุด (ราคาปัจจุบัน)
        fy_ph = ",".join("?" for _ in RECENT_FY)
        where.append(f"fiscal_year IN ({fy_ph})")
        params += list(RECENT_FY)
    # ตำแหน่งจับคู่จากชื่องาน (ground truth) OR คอลัมน์ — คอลัมน์ district/subdistrict
    # มาจาก geocode พิกัด ซึ่ง snap ไปอำเภอเมืองผิดบ่อย (เช่น งานตำบลนาทม tag เป็นเมืองนครพนม).
    # ชื่องานระบุ "ตำบลX อำเภอY" เชื่อถือได้กว่า. belt-and-suspenders กันงานที่ชื่อไม่ระบุตำบล.
    if subdistrict is not None:                   # เต็ม 'ตำบลX' + ย่อ 'ต.X' (CGD เขียนทั้งสองแบบ)
        where.append("(subdistrict=? OR project_name LIKE ? OR project_name LIKE ?)")
        params += [subdistrict, f"%ตำบล{subdistrict}%", f"%ต.{subdistrict}%"]
    if district is not None:
        where.append("(district=? OR project_name LIKE ? OR project_name LIKE ?)")
        params += [district, f"%อำเภอ{district}%", f"%อ.{district}%"]
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
    elif subtype == "water_excav":
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in _WATER_EXCAV_KW) + ")")
        params += [f"%{k}%" for k in _WATER_EXCAV_KW]
    elif subtype == "water_struct":     # structure ต้องไม่มี keyword ขุด (excavation ชนะ)
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in _WATER_STRUCT_KW) + ")")
        params += [f"%{k}%" for k in _WATER_STRUCT_KW]
        where.append("NOT (" + " OR ".join("project_name LIKE ?" for _ in _WATER_EXCAV_KW) + ")")
        params += [f"%{k}%" for k in _WATER_EXCAV_KW]
    # market filter — ท้องถิ่น (อปท.) อ้างอิงท้องถิ่น, ส่วนกลาง = ที่ไม่ใช่ อปท. (กรม/ทางหลวง)
    if market == "local":
        where.append("(" + " OR ".join("dept LIKE ?" for _ in _LOCAL_AGENCY_KW) + ")")
        params += [f"%{k}%" for k in _LOCAL_AGENCY_KW]
    elif market == "central":
        where.append("NOT (" + " OR ".join("dept LIKE ?" for _ in _LOCAL_AGENCY_KW) + ")")
        params += [f"%{k}%" for k in _LOCAL_AGENCY_KW]
    try:
        cur = conn.execute(
            "SELECT project_name, winner, win_price, discount_pct, district, subdistrict "
            "FROM cgd_winners WHERE " + " AND ".join(where), params)
        return [{"project_name": r[0], "winner": r[1], "win_price": r[2],
                 "discount_pct": r[3], "district": r[4], "subdistrict": r[5]}
                for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []   # ไม่มี table/column cgd_winners → graceful


def company_area_history(conn, province, tokens, company, subdistrict, district) -> dict:
    """ประวัติส่วนลดของบริษัทในพื้นที่ (competitive-set). ตำบลก่อน ไม่มี→ทั้งจังหวัด.
    คืน {scope:'ตำบล'|'นอกตำบล'|'', n, median}."""
    trows = [r for r in _fetch(conn, province, tokens, subdistrict=subdistrict, district=district)
             if r.get("winner") == company]
    if trows:
        discs = [r["discount_pct"] for r in trows if r.get("discount_pct") is not None]
        return {"scope": "ตำบล", "n": len(trows), "median": _pct(discs, 50)}
    prows = [r for r in _fetch(conn, province, tokens) if r.get("winner") == company]
    if prows:
        discs = [r["discount_pct"] for r in prows if r.get("discount_pct") is not None]
        return {"scope": "นอกตำบล", "n": len(prows), "median": _pct(discs, 50)}
    return {"scope": "", "n": 0, "median": None}


def analyze_bidders(conn, province, tokens, subdistrict, district, budget, bidders, warned) -> list:
    """วิเคราะห์ผู้ยื่นทุกราย: เรียงราคา + ส่วนลดครั้งนี้ + ประวัติพื้นที่ + เทรนด์ + ป้าย.
    bidders: list[{bidder_name, price_proposal, is_winner}]. warned: ชื่อ top-3 ที่เตือนตอน D0.
    tag: 'warned' | 'regular_missed' (มีประวัติแต่ไม่เตือน) | 'newcomer'."""
    def _price(b):
        try:
            return float(b.get("price_proposal") or 0)
        except (TypeError, ValueError):
            return 0.0
    ranked = sorted([b for b in bidders if _price(b) > 0], key=_price)
    out = []
    b_ = float(budget) if budget else 0
    for b in ranked:
        name = b.get("bidder_name") or "?"
        price = _price(b)
        disc = round((1 - price / b_) * 100, 1) if b_ > 0 else None
        import competitor_trend as _ct
        _discs, _scope = _ct.company_series(conn, province, tokens, name, subdistrict, district)
        _t = _ct.ewma_trend(_discs)
        hist = {"scope": _scope, "n": _t["n"], "median": _t["median"], "ewma": _t["ewma"]}
        trend = _t["trend"]
        if name in warned:
            tag = "warned"
        elif hist["n"] > 0:
            tag = "regular_missed"
        else:
            tag = "newcomer"
        out.append({"name": name, "price": price, "discount": disc, "is_winner": bool(b.get("is_winner")),
                    "hist": hist, "trend": trend, "tag": tag})
    return out


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
    return lines, p25, p75, n, top_name, top_median, _pct(discs, 50)


def confidence_label(area_n: int, p25, p75) -> str:
    """ป้ายความเชื่อมั่นทางสถิติ (จาก n + ความกว้าง IQR). คนละมิติกับ relevance (= header level)."""
    wide = p25 is not None and p75 is not None and (p75 - p25) > IQR_WIDE
    if area_n < 10:
        return "🔴 ข้อมูลน้อย — โปรดใช้วิจารณญาณ"
    if area_n < 30 or wide:
        return "🟡 เชื่อมั่นปานกลาง — ข้อมูลน้อย/ช่วงกว้าง (ดูเป็นแนวโน้ม ไม่ใช่ราคาตายตัว)"
    return "🟢 เชื่อถือได้ — ข้อมูลมากพอ"


def _fetch_scope(conn, province, tokens, *, subdistrict=None, district=None, subtype=None,
                 nature=None, contested_only=False, market=None):
    """ดึง reference ของ scope — 3 ปีล่าสุดก่อน; ถ้าคู่แข่งน้อย (< MIN_COMPETITORS) ย้อนทุกปีงบ
    เพื่อให้พื้นที่ข้อมูลน้อย (อำเภอเล็ก/ใหม่) ยังคาดราคาได้. คืน (rows, used_old)."""
    rows = _fetch(conn, province, tokens, subdistrict=subdistrict, district=district,
                  subtype=subtype, nature=nature, contested_only=contested_only, market=market)
    if _distinct_winners(rows) >= MIN_COMPETITORS:
        return rows, False
    old = _fetch(conn, province, tokens, subdistrict=subdistrict, district=district,
                 subtype=subtype, nature=nature, contested_only=contested_only, market=market,
                 include_old=True)
    return (old, True) if _distinct_winners(old) > _distinct_winners(rows) else (rows, False)


def _build_intel(conn, province: str, tokens: list, tambon, amphoe, budget, subtype=None,
                 nature=None, contested_only=False, market=None) -> dict | None:
    """ประกอบ intel dual-block จาก (ตำบล,อำเภอ) ที่ resolve มาแล้ว (แยกจาก resolve เพื่อ test ง่าย).
    - บล็อกตำบล: เสมอ (ถ้ามีชื่อตำบล) — สถิติเฉพาะงานในตำบล. 0 งาน → 'ยังไม่มีงานประเภทนี้'
    - บล็อกอำเภอ: เพิ่มเมื่อตำบล < TAMBON_MIN — สถิติเฉพาะงานในอำเภอ
    - amphoe=None → บล็อกจังหวัดเดี่ยว. คาดราคาอิงตำบลก่อน (ไม่มี→อำเภอ/จังหวัด).
    contested_only=True → เฉพาะงานแข่งจริง (ตัด no-competition) + framing 'ถ้ามีคู่แข่ง'.
    คืน {lines, prediction} · None ถ้าไม่มีคู่แข่งจริงเลย."""
    wt = tokens[0] if tokens else "งาน"
    cf = dict(subtype=subtype, nature=nature, contested_only=contested_only, market=market)
    blocks = []
    pp25 = pp75 = ptop = ptopm = pmed = None
    basis = ""
    basis_sub = basis_dist = None    # scope ที่ใช้คาดราคา (สำหรับ recency series)
    basis_old = False                # คาดราคาอิงข้อมูลย้อนเกิน 3 ปี (พื้นที่งานน้อย) → ติดป้าย
    tag = " (งานแข่งจริง)" if contested_only else ""
    if amphoe:
        header = (f"💡 ราคาอ้างอิง (งาน{wt}"
                  + (f" ต.{tambon}" if tambon else "") + f" อ.{amphoe}){tag}")
        t_rows, t_old = _fetch_scope(conn, province, tokens, subdistrict=tambon,
                                     district=amphoe, **cf) if tambon else ([], False)
        tn = len(t_rows)
        if tambon:
            if t_rows:
                tl, t25, t75, _n, ttop, ttopm, tmed = _scope_block(t_rows, f"🏘 ในตำบล{tambon}")
                blocks += tl
                pp25, pp75, ptop, ptopm, pmed, basis = t25, t75, ttop, ttopm, tmed, "ตำบล"
                basis_sub, basis_dist, basis_old = tambon, amphoe, t_old
            else:
                blocks.append(f"🏘 ในตำบล{tambon} — ยังไม่มีงานประเภทนี้")
        if tn < TAMBON_MIN:                       # ตำบลน้อย → โชว์อำเภอคู่กัน
            a_rows, a_old = _fetch_scope(conn, province, tokens, district=amphoe, **cf)
            if a_rows:
                al, a25, a75, _n, atop, atopm, amed = _scope_block(a_rows, f"🏙 ในอำเภอ{amphoe}")
                blocks += al
                if pp25 is None:                  # ตำบลไม่มี → คาดอิงอำเภอ
                    pp25, pp75, ptop, ptopm, pmed, basis = a25, a75, atop, atopm, amed, "อำเภอ"
                    basis_sub, basis_dist, basis_old = None, amphoe, a_old
    else:
        p_rows, p_old = _fetch_scope(conn, province, tokens, **cf)
        if not p_rows:
            return None
        pl, p25, p75, _n, ptopn, ptopmd, pmedn = _scope_block(p_rows, f"🏙 ใน{province}")
        blocks += pl
        pp25, pp75, ptop, ptopm, pmed, basis = p25, p75, ptopn, ptopmd, pmedn, "จังหวัด"
        basis_sub, basis_dist, basis_old = None, None, p_old
        header = f"💡 ราคาอ้างอิง (งาน{wt}ใน{province}){tag}"
    if not blocks or all("ยังไม่มีงาน" in b for b in blocks):
        return None                               # ไม่มีคู่แข่งจริงเลย → omit
    lines = [header, ""] + blocks
    if pp25 is not None and pp75 is not None:
        import competitor_trend as _ct
        _series = _ct.area_win_series(conn, province, tokens, basis_sub, basis_dist, subtype, nature, contested_only, market)
        new25, new75 = _ct.recency_adjusted_pct(_series, pp25, pp75)
        if pmed is not None and new25 is not None:    # เลื่อน median ตาม delta เดียวกัน
            pmed += new25 - pp25
        pp25, pp75 = new25, new75
    pred = predict_winning_price(budget, pp25, pp75, ptop, ptopm, area_median=pmed)
    if pred:
        lines += [""] + predict_lines(pred, basis, contested=contested_only)
        if basis_old:                             # อิงข้อมูลเก่ากว่า 3 ปี — แจ้งให้ผู้ใช้รู้
            lines.append("📜 รวมข้อมูลเก่ากว่า 3 ปี (พื้นที่นี้งานน้อย) — ใช้เป็นแนวโน้ม")
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
            # subtype = ผิวถนน (concrete/asphalt) หรือ งานน้ำ (ขุด/โครงสร้าง) — งานหนึ่งเป็นได้แค่อย่างเดียว
            sub = road_subtype(project_name) or water_subtype(project_name)
            nat = work_nature(project_name)
            mkt = agency_market(dept_name)   # ระบอบตลาด (ท้องถิ่น/ส่วนกลาง) — ตัวขับส่วนลดจริง

            def _b(contested):
                return _build_intel(conn, province, tokens, loc["tambon"], loc["amphoe"],
                                    budget, sub, nat, contested_only=contested, market=mkt)
            # โฟกัสงานแข่งจริงก่อน (ตัด no-competition ที่ทำช่วงเพี้ยน)
            ctx = _b(True)
            if ctx and ctx.get("prediction"):
                return ctx
            # พื้นที่แทบไม่มีงานแข่ง → ใช้ทั้งหมด + แจ้งว่าแข่งน้อย
            ctx = _b(False)
            if ctx and ctx.get("prediction"):
                ctx["lines"].append("⚠️ พื้นที่นี้แข่งขันน้อย — ราคาอาจไม่สะท้อนการแข่งขัน")
            return ctx
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


def predict_winning_price(budget, area_p25, area_p75, top_name=None, top_median=None,
                          area_median=None) -> dict | None:
    """คาดช่วงราคาชนะ = ราคากลาง × (1 − ส่วนลด). ช่วงตลาด p25/p75 + ค่าปกติ (median) + เจ้าตัวเต็ง.
    None ถ้าข้อมูลไม่พอ. prediction เชิงสถิติ ไม่ใช่คำสั่ง (ดู predict_lines disclaimer)."""
    if not budget or area_p25 is None or area_p75 is None:
        return None
    b = float(budget)
    return {
        "budget": b, "area_disc_lo": area_p25, "area_disc_hi": area_p75,
        "area_price_lo": round(b * (1 - area_p75 / 100)), "area_price_hi": round(b * (1 - area_p25 / 100)),
        "area_disc_med": area_median,
        "area_price_med": round(b * (1 - area_median / 100)) if area_median is not None else None,
        "top_name": top_name, "top_disc": top_median,
        "top_price": round(b * (1 - top_median / 100)) if top_median is not None else None,
    }


def compare_prediction(project_id: str, actual_price, conn=None) -> dict | None:
    """เทียบราคาจริง vs คำทำนาย → in_range + error% → update DB (closed-loop).
    None ถ้าไม่มี prediction / actual แปลงเป็นตัวเลขไม่ได้."""
    from Sebastian_Customer_DB import get_prediction
    try:
        actual = float(actual_price)
    except (TypeError, ValueError):
        return None
    if not actual:
        return None
    p = get_prediction(project_id)
    if not p or p.get("area_price_lo") is None or p.get("area_price_hi") is None:
        return None
    return _compare_core(project_id, p, actual, commit=True)


def compare_prediction_provisional(project_id: str, actual_price, conn=None):
    """เทียบเบื้องต้น (Round 1) — เหมือน compare_prediction แต่ไม่เขียน DB/สถิติ."""
    from Sebastian_Customer_DB import get_prediction
    try:
        actual = float(actual_price)
    except (TypeError, ValueError):
        return None
    if not actual:
        return None
    p = get_prediction(project_id)
    if not p or p.get("area_price_hi") is None:
        return None
    return _compare_core(project_id, p, actual, commit=False)


def _compare_core(project_id: str, p: dict, actual: float, commit: bool) -> dict:
    """core เทียบกรอบบน. held = actual <= area_price_hi. error% = (actual-hi)/hi (มีเครื่องหมาย)."""
    from Sebastian_Customer_DB import update_prediction_actual
    hi = p["area_price_hi"]
    held = actual <= hi
    error_pct = round((actual - hi) / hi * 100, 1)
    if commit:
        update_prediction_actual(project_id, round(actual), 1 if held else 0, error_pct)
    return {"held": held, "error_pct": error_pct, "upper": hi,
            "area_price_lo": p["area_price_lo"], "area_price_hi": hi, "actual": round(actual),
            "pred_med": p.get("area_price_med")}   # ค่ากลาง (ปกติ) สำหรับเทียบ win/lose


def predict_lines(p: dict, basis: str = "ตำบล", contested: bool = False) -> list:
    """บรรทัด 💵 คาดราคา — โชว์ % (ที่มา) ก่อน → ราคา (ผล) + ค่าปกติ (median) + basis.
    contested=True → framing 'ถ้ามีคู่แข่ง ผู้ชนะลด' (โฟกัสงานแข่งจริง).
    framing คาดการณ์ ไม่ใช่คำสั่ง. คู่แข่งโชว์ในบล็อกด้านบนแล้ว → ที่นี่เอาแค่ช่วงรวม."""
    if not p:
        return []
    lo = round(p["area_price_lo"] / 1000) * 1000   # ปัดหลักพัน — สื่อว่าเป็นค่าประมาณ
    hi = round(p["area_price_hi"] / 1000) * 1000
    head = "💵 ถ้ามีคู่แข่ง ผู้ชนะลด" if contested else "💵 คาดราคาที่จะชนะ"
    med, medp = p.get("area_disc_med"), p.get("area_price_med")
    med_txt = f" (ปกติ ~{med:.0f}%)" if med is not None else ""
    medp_txt = (f" (ปกติ {round(medp / 1000) * 1000:,.0f})") if medp is not None else ""
    return [f"{head} (ราคากลาง {p['budget']:,.0f} บาท):",
            f"   • อิง{basis} ลด {p['area_disc_lo']:.0f}–{p['area_disc_hi']:.0f}%{med_txt} → "
            f"ชนะราว {lo:,.0f}–{hi:,.0f} บาท{medp_txt}",
            "   * ประเมินจากสถิติ โปรดคำนวณต้นทุนจริงประกอบ"]
