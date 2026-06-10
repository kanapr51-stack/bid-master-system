"""competitor_trend.py — recency-weighted (EWMA) discount trend จาก cgd_winners + bid_results.
ใช้ปรับ prediction (area, recency-adjusted percentile) + เทรนด์ส่วนลดต่อบริษัท (Round 2).
ดู docs/superpowers/specs/2026-06-10-competitor-trend-adaptive-discount-design.md"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ALPHA = 0.3        # EWMA recency weight (ปานกลาง — ล่าสุดมากสุด แต่ไม่ไล่ noise)
MIN_N = 3          # < นี้ → ไม่ปรับ/ไม่โชว์เทรนด์ (data น้อย)
CAP = 8.0          # damping: เลื่อน percentile ได้ ≤ CAP จุด/รอบ (กัน 1 ฟลุ๊คดันแรง)
TREND_EPS = 2.0    # เกณฑ์ ↑/↓


def ewma(values, alpha=ALPHA):
    """recency-weighted average. values เรียง เก่า→ใหม่ (ตัวท้ายน้ำหนักมากสุด). None ถ้าว่าง."""
    if not values:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return acc


def median(values):
    """มัธยฐาน. None ถ้าว่าง."""
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def ewma_trend(values, alpha=ALPHA, min_n=MIN_N):
    """คืน {ewma, median, n, trend}. trend ∈ {↑,↓,→,None}. n<min_n → ewma=median, trend=None."""
    n = len(values)
    md = median(values)
    if n < min_n:
        return {"ewma": md, "median": md, "n": n, "trend": None}
    ew = ewma(values, alpha)
    if ew > md + TREND_EPS:
        tr = "↑"
    elif ew < md - TREND_EPS:
        tr = "↓"
    else:
        tr = "→"
    return {"ewma": ew, "median": md, "n": n, "trend": tr}


def recency_adjusted_pct(values, p25, p75, alpha=ALPHA, min_n=MIN_N, cap=CAP):
    """เลื่อน (p25,p75) ตาม EWMA-median delta (damped ≤cap, คงความกว้าง). n<min_n → ไม่ปรับ."""
    if len(values) < min_n or p25 is None or p75 is None:
        return p25, p75
    md = median(values)
    ew = ewma(values, alpha)
    delta = max(-cap, min(cap, ew - md))
    return p25 + delta, p75 + delta


import cgd_intel as ci


def _area_where(province, tokens, subdistrict, district, subtype):
    """ประกอบ WHERE + params สำหรับ cgd_winners (สอดคล้อง cgd_intel._fetch + announce_date)."""
    fy_ph = ",".join("?" for _ in ci.RECENT_FY)
    pt_ph = ",".join("?" for _ in ci.COMPETITIVE_SET)
    like = " OR ".join("project_name LIKE ?" for _ in tokens)
    where = ["province=?", "win_price>0", "discount_pct IS NOT NULL",
             f"fiscal_year IN ({fy_ph})", f"proc_type IN ({pt_ph})", f"({like})"]
    params = [province, *ci.RECENT_FY, *ci.COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    if subdistrict is not None:
        where.append("subdistrict=?"); params.append(subdistrict)
    if district is not None:
        where.append("district=?"); params.append(district)
    if subtype == "asphalt":
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in ci._ASPHALT_KW) + ")")
        params += [f"%{k}%" for k in ci._ASPHALT_KW]
    elif subtype == "concrete":
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in ci._CONCRETE_KW) + ")")
        params += [f"%{k}%" for k in ci._CONCRETE_KW]
        where.append("NOT (" + " OR ".join("project_name LIKE ?" for _ in ci._ASPHALT_KW) + ")")
        params += [f"%{k}%" for k in ci._ASPHALT_KW]
    return " AND ".join(where), params


def _cgd_rows(conn, province, tokens, subdistrict, district, subtype, winner=None):
    """(announce_date, discount_pct, winner) จาก cgd_winners. winner!=None → filter บริษัท."""
    where, params = _area_where(province, tokens, subdistrict, district, subtype)
    if winner is not None:
        where += " AND winner=?"; params.append(winner)
    try:
        cur = conn.execute(f"SELECT announce_date, discount_pct, winner FROM cgd_winners WHERE {where}", params)
        return [(r[0] or "", r[1], r[2]) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def _bidresult_rows(conn, province, bidder=None, winner_only=False):
    """ส่วนลดจาก bid_results + budget (projects_seen, province scope). คืน [(fetched_at, disc)].
    bidder!=None → เฉพาะบริษัทนั้น (ใช้ price_proposal). winner_only → is_winner=1 (ใช้ price_agree)."""
    col = "price_agree" if winner_only else "price_proposal"
    where = ["ps.province=?", f"b.{col} IS NOT NULL", f"b.{col} != ''", "ps.budget>0"]
    params = [province]
    if winner_only:
        where.append("b.is_winner=1")
    if bidder is not None:
        where.append("b.bidder_name=?"); params.append(bidder)
    try:
        cur = conn.execute(
            f"SELECT b.fetched_at, b.{col}, ps.budget FROM bid_results b "
            f"JOIN projects_seen ps ON ps.project_id=b.project_id WHERE " + " AND ".join(where), params)
    except sqlite3.OperationalError:
        return []
    out = []
    for fa, price, budget in cur.fetchall():
        try:
            p, bud = float(price), float(budget or 0)
            if bud > 0 and p > 0:
                out.append((fa or "", round((1 - p / bud) * 100.0, 4)))
        except (TypeError, ValueError):
            pass
    return out


def area_win_series(conn, province, tokens, subdistrict=None, district=None, subtype=None):
    """ส่วนลดผู้ชนะในพื้นที่ เรียงเก่า→ใหม่ (cgd_winners + bid_results winner). คืน list[float]."""
    rows = [(d, disc) for d, disc, _w in _cgd_rows(conn, province, tokens, subdistrict, district, subtype)
            if disc is not None]
    rows += _bidresult_rows(conn, province, winner_only=True)
    rows.sort(key=lambda x: x[0])
    return [disc for _d, disc in rows]


def company_series(conn, province, tokens, company, subdistrict=None, district=None, subtype=None):
    """ส่วนลดของบริษัท เรียงเก่า→ใหม่ (cgd_winners win + bid_results proposal). ตำบลก่อน→จังหวัด.
    คืน (list[float], scope) — scope ∈ {'ตำบล','นอกตำบล',''}."""
    def _series(sub, dist):
        rows = [(d, disc) for d, disc, _w in
                _cgd_rows(conn, province, tokens, sub, dist, subtype, winner=company) if disc is not None]
        rows += _bidresult_rows(conn, province, bidder=company)
        rows.sort(key=lambda x: x[0])
        return [disc for _d, disc in rows]
    if subdistrict is not None:
        s = _series(subdistrict, district)
        if s:
            return s, "ตำบล"
    s = _series(None, None)
    return (s, "นอกตำบล") if s else ([], "")
