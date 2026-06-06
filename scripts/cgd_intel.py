"""cgd_intel.py — competitor intel ระดับท้องถิ่นจาก cgd_winners: ใครคือคู่แข่งงานนี้ + เขาลดราคายังไง.
descriptive เท่านั้น (ตลาดเป็นยังไง) ไม่ prescriptive (ไม่บอกราคาที่ควรยื่น).
พระเอก = โปรไฟล์คู่แข่งรายบริษัท (selection ไล่ระดับ ตำบล→อำเภอ→จังหวัด, stat จากประวัติบริษัท)
+ ภาพรวมเสริม + ป้ายความเชื่อมั่น. ใช้แนบการ์ด D0 (followed_bid_open). intel = value-add — ห้ามทำ notification พัง."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

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


def resolve_tambon(project_name: str, dept_name: str = "") -> str:
    """ตำบลของงาน D0 จาก name → dept (ฟรี ไม่เรียก API — บทเรียน INC-001: resolve API ใน
    notify path ทำ WAF block). resolve ไม่ได้ → '' (intel_lines degrade เป็นจังหวัด)."""
    try:
        import job_matcher as jm
        return jm.tambon_from_name(project_name) or jm.tambon_from_dept(dept_name)
    except Exception:
        return ""


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


def select_competitors(province: str, tokens: list, tambon: str, conn) -> tuple:
    """เลือกคู่แข่งไล่ระดับ ตำบล→อำเภอ→จังหวัด. คืน (rows, scope_label, level).
    อำเภอ derive จาก cgd_winners (DISTINCT district ของตำบล) — หลายอำเภอ=ambiguous→province.
    competitive-set ถูกกรองใน _fetch แล้ว (เฉพาะเจาะจงไม่หลุด)."""
    wt = tokens[0] if tokens else "งาน"
    if tambon:
        trows = _fetch(conn, province, tokens, subdistrict=tambon)
        districts = {r["district"] for r in trows if r.get("district")}
        if len(districts) == 1:
            d = next(iter(districts))
            if _distinct_winners(trows) >= MIN_COMPETITORS:
                return trows, f"งาน{wt} ต.{tambon} อ.{d}", "tambon"
            arows = _fetch(conn, province, tokens, district=d)   # widen → อำเภอ
            if _distinct_winners(arows) >= MIN_COMPETITORS:
                return arows, f"งาน{wt} อ.{d}", "amphoe"
        # ambiguous (หลายอำเภอ) / ไม่มี / ไม่พอ → province
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


def intel_lines(province: str, project_name: str, dept_name: str = "", conn=None) -> list:
    """บรรทัด 💡 competitor intel ระดับท้องถิ่นสำหรับการ์ด D0. คืน [] ถ้าไม่มีคู่แข่ง/error.
    พระเอก=โปรไฟล์คู่แข่งรายบริษัท (selection ไล่ระดับ ตำบล→อำเภอ→จังหวัด, stat จากประวัติบริษัท)
    + ภาพรวมเสริม + ป้ายความเชื่อมั่น. competitive-set กรองทั้ง selection+stat. ห่อ try/except."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return []
        own = conn is None
        if own:
            from Sebastian_Customer_DB import get_connection
            conn = get_connection()
        try:
            tambon = resolve_tambon(project_name, dept_name)
            rows, scope, _level = select_competitors(province, tokens, tambon, conn)
            if not rows:
                return []
            counts = Counter(r["winner"] for r in rows if r.get("winner"))
            lines = [f"💡 ราคาอ้างอิง ({scope})", "🏆 คู่แข่งแถบนี้:"]
            for winner, _ in counts.most_common(SHOW_N):
                cs = company_stats(winner, tokens, conn)
                nm = (winner or "?")[:28]
                if cs["p25"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}% "
                                 f"({cs['p25']:.0f}–{cs['p75']:.0f}%)")
                elif cs["median"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}%")
                else:
                    lines.append(f"  • {nm} · {cs['games']} งาน")
            discs = [r["discount_pct"] for r in rows if r.get("discount_pct") is not None]
            area_n = len(rows)
            p25, p75 = _pct(discs, 25), _pct(discs, 75)
            if p75:
                lines.append(f"📊 ภาพรวม {area_n} งาน · ลด {p25:.0f}–{p75:.0f}%")
            else:
                lines.append(f"📊 ภาพรวม {area_n} งาน")
            lines.append(confidence_label(area_n, p25, p75))
            return lines
        finally:
            if own:
                conn.close()
    except Exception:
        return []
