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
    """งานใน cgd_winners ที่ province ตรง + ชื่อมี ≥ min_overlap ของ tokens + win_price>0.
    candidate fetch = LIKE ANY token (ใช้ idx province) → filter overlap ใน Python.
    conn inject ได้ (test); default = Sebastian_Customer_DB.get_connection()."""
    if not province or not tokens:
        return []
    own = conn is None
    if own:
        from Sebastian_Customer_DB import get_connection
        conn = get_connection()
    try:
        like = " OR ".join("project_name LIKE ?" for _ in tokens)
        params = [province] + [f"%{t}%" for t in tokens]
        try:
            cur = conn.execute(
                f"SELECT project_name, winner, win_price, discount_pct FROM cgd_winners "
                f"WHERE province=? AND win_price>0 AND ({like})", params)
            fetched = cur.fetchall()
        except sqlite3.OperationalError:
            return []   # ไม่มี table cgd_winners → graceful
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
    strict (≥2 token) → relax (≥1) → silence (<min_count). ห่อ try/except — ห้าม throw."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return []
        if len(tokens) >= 2:
            rows = query_similar(province, tokens, 2, conn=conn)
            if len(rows) < min_count:
                rows = query_similar(province, tokens, 1, conn=conn)   # widen
        else:
            rows = query_similar(province, tokens, 1, conn=conn)
        if len(rows) < min_count:
            return []
        s = compute_stats(rows)
        lines = [f"💡 ราคาอ้างอิง (งาน{tokens[0]}ใน{province})",
                 f"📊 จาก {s['count']} งานย้อนหลัง"]
        if s["discount_p25"] is not None:
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
