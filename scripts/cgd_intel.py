"""cgd_intel.py — competitive intel จาก cgd_winners: ผู้ชนะงานคล้ายในพื้นที่ + ราคา/ส่วนลด.
descriptive เท่านั้น (ตลาดเป็นยังไง) ไม่ prescriptive (ไม่บอกราคาที่ควรยื่น).
ใช้แนบการ์ด D0 (source_stage=followed_bid_open). intel = value-add — ห้ามทำ notification พัง."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_KW_PATH = Path(__file__).parent.parent / "config" / "matching_preferences.json"

# competitive-set: เฉพาะวิธีที่ "แข่งราคาจริง" — CGD 91% เป็นเฉพาะเจาะจง/ตกลงราคา (disc≈0)
# ลาก median ลง 0 ทำให้ตัวเลขลวง. e-bidding ลดจริง ~14% (ดู project_cgd_market_insight).
COMPETITIVE_SET = (
    "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
    "ประกวดราคาด้วยวิธีการทางอิเล็กทรอนิกส์",
    "สอบราคา",
    "คัดเลือก",
)
# 3 ปีงบล่าสุด — ราคาตลาดเก่าไม่สะท้อนปัจจุบัน (เงินเฟ้อ/ราคาวัสดุ)
RECENT_FY = ("2566", "2567", "2568")


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


def query_similar(province: str, tokens: list, min_overlap: int, conn=None) -> list:
    """งานใน cgd_winners ที่ province ตรง + win_price>0 + competitive-set + 3 ปีงบล่าสุด,
    และชื่อมี ≥ min_overlap ของ tokens. candidate fetch = LIKE ANY token (ใช้ idx province)
    → filter overlap ใน Python. ไม่มี work-type ก็ไม่คิวรี (intel ไม่ข้ามหมวด — ดู intel_lines).
    conn inject ได้ (test); default = Sebastian_Customer_DB.get_connection()."""
    if not province or not tokens:
        return []
    own = conn is None
    if own:
        from Sebastian_Customer_DB import get_connection
        conn = get_connection()
    try:
        fy_ph = ",".join("?" for _ in RECENT_FY)
        pt_ph = ",".join("?" for _ in COMPETITIVE_SET)
        like = " OR ".join("project_name LIKE ?" for _ in tokens)
        params = [province, *RECENT_FY, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
        try:
            cur = conn.execute(
                "SELECT project_name, winner, win_price, discount_pct FROM cgd_winners "
                f"WHERE province=? AND win_price>0 AND fiscal_year IN ({fy_ph}) "
                f"AND proc_type IN ({pt_ph}) AND ({like})", params)
            fetched = cur.fetchall()
        except sqlite3.OperationalError:
            return []   # ไม่มี table/column cgd_winners → graceful
        out = []
        for row in fetched:
            pname, winner, win_price, disc = row[0], row[1], row[2], row[3]
            if sum(1 for t in tokens if t in (pname or "")) >= min_overlap:
                out.append({"project_name": pname, "winner": winner,
                            "win_price": win_price, "discount_pct": disc})
        return out
    finally:
        if own:
            conn.close()


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


def compute_stats(rows: list) -> dict:
    """สถิติตลาด: count, ส่วนลด median/p25/p75, ช่วงราคาชนะ p10/p90, ผู้ชนะบ่อย top3+count."""
    discs = [r["discount_pct"] for r in rows if r.get("discount_pct") is not None]
    prices = [r["win_price"] for r in rows if r.get("win_price")]
    winners = Counter(r["winner"] for r in rows if r.get("winner"))
    return {
        "count": len(rows),
        "discount_median": _pct(discs, 50),
        "discount_p25": _pct(discs, 25),
        "discount_p75": _pct(discs, 75),
        "price_lo": _pct(prices, 10),
        "price_hi": _pct(prices, 90),
        "top_winners": winners.most_common(3),
    }


def intel_lines(province: str, project_name: str, min_count: int = 10, conn=None) -> list:
    """บรรทัด 💡 competitive intel สำหรับแนบการ์ด D0. คืน [] ถ้าข้อมูลไม่พอ/error.
    fallback: L1 จว.+work-type(≥2)+comp → L2 ≥1+comp → omit. ทุก level กรอง
    competitive-set + 3 ปีล่าสุดแล้ว. ห่อ try/except — ห้าม throw.

    ไม่มี fallback ข้ามหมวดงาน (เคยมี L3 จว.+comp ทุก work-type — ตัดออก 2026-06-07):
    discount/ราคาข้ามหมวด (ถนน vs อาคาร vs ไฟฟ้า dynamics ต่างกัน) มี descriptive value ต่ำ
    + misleading risk สูง → ยอมไม่โชว์ดีกว่าโชว์สิ่งที่ตีความผิดได้ (descriptive principle).
    งานถนนพื้นที่เป้าหมายมี e-bidding มากพอถึง min_count (นพ.673/บก.439) → L1/L2 พอ.

    TODO: ถ้า enrich proc_type ของงาน D0 ได้ (projects_seen มีแค่ announce_type) →
    upgrade เป็น e-bidding-only เพื่อ precision สูงสุด (ตอนนี้ competitive-set กว้างพอ)."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return []                                          # นิยาม "คล้าย" ไม่ได้ → omit
        if len(tokens) >= 2:
            rows = query_similar(province, tokens, 2, conn=conn)        # L1
            if len(rows) < min_count:
                rows = query_similar(province, tokens, 1, conn=conn)    # L2 widen
        else:
            rows = query_similar(province, tokens, 1, conn=conn)        # L2
        if len(rows) < min_count:
            return []                                                  # omit (กัน stat หลอก)
        s = compute_stats(rows)
        lines = [f"💡 ราคาอ้างอิง (งาน{tokens[0]}ใน{province})",
                 f"📊 จาก {s['count']} งานย้อนหลัง"]
        # discount: โชว์เฉพาะเมื่อมี signal จริง (p75>0). CGD ~80% ชนะที่ราคากลางพอดี (disc=0)
        # → ถ้า p75=0 บรรทัด "0–0%" ไม่ให้ข้อมูล + misleading → omit (descriptive, ไม่ลวง)
        if s["discount_p75"]:
            lines.append(f"📉 ส่วนลดที่พบบ่อย {s['discount_p25']:.0f}–{s['discount_p75']:.0f}%")
        if s["price_lo"] is not None:
            lines.append(f"💵 ช่วงราคาชนะ {s['price_lo']/1e6:.1f}–{s['price_hi']/1e6:.1f} ลบ.")
        if s["top_winners"]:
            lines.append("🏆 ผู้ชนะบ่อย:")
            for nm, cnt in s["top_winners"]:
                lines.append(f"  • {(nm or '?')[:32]} ({cnt})")
        return lines
    except Exception:
        return []
