"""portal_views.py — หน้า detail งาน + ประวัติบริษัท (Portal Phase 2b / Phase 1).
Query bms_customers.db (bid_results + projects_seen) — รับ conn จาก caller (กัน circular import).
Render มือถือ-first, กราฟ inline CSS bar (ไม่พึ่ง chart lib)."""
import html as _h
import sqlite3


def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _year_th(pid):
    s = str(pid or "")
    if len(s) >= 2 and s[:2].isdigit():
        return 2500 + int(s[:2])
    return None


def _discount(price, budget):
    if price and budget and budget > 0:
        return round((1 - price / budget) * 100, 1)
    return None


def job_detail(conn, pid):
    ps = conn.execute(
        "SELECT project_name, budget, province FROM projects_seen WHERE project_id=?",
        (pid,)).fetchone()
    rows = conn.execute(
        "SELECT bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme "
        "FROM bid_results WHERE project_id=?", (pid,)).fetchall()
    if not rows and not ps:
        return None
    budget = (ps["budget"] if ps else 0) or 0
    loc = ""
    try:
        l = conn.execute(
            "SELECT moi_name, province_name FROM project_locations WHERE project_id=?",
            (pid,)).fetchone()
        if l:
            moi = (l["moi_name"] or "") if "moi_name" in l.keys() else ""
            prov = (l["province_name"] or "") if "province_name" in l.keys() else ""
            loc = ((f"ต.{moi} " if moi else "") + (f"จ.{prov}" if prov else "")).strip()
    except sqlite3.OperationalError:
        loc = ""
    if not loc and ps and ps["province"]:
        loc = f"จ.{ps['province']}"
    bidders = []
    for r in rows:
        price = _to_float(r["price_proposal"])
        bidders.append({
            "name": r["bidder_name"] or "", "tin": r["bidder_tin"] or "",
            "price": price, "agree": _to_float(r["price_agree"]),
            "is_winner": bool(r["is_winner"]),
            "is_sme": bool(r["is_sme"] if "is_sme" in r.keys() else 0),
            "discount": _discount(price, budget)})
    bidders.sort(key=lambda b: (not b["is_winner"], b["price"] is None, b["price"] or 0))
    return {"job": {"project_id": pid, "name": (ps["project_name"] if ps else "") or pid,
                    "location": loc, "budget": budget}, "bidders": bidders}


def company_profile(conn, tin):
    rows = conn.execute(
        "SELECT br.project_id, br.bidder_name, br.price_proposal, br.is_winner, br.is_sme, "
        "ps.project_name, ps.budget, ps.province "
        "FROM bid_results br LEFT JOIN projects_seen ps ON ps.project_id=br.project_id "
        "WHERE br.bidder_tin=?", (tin,)).fetchall()
    if not rows:
        return None
    name = next((r["bidder_name"] for r in rows if r["bidder_name"]), "") or ""
    is_sme = any(bool(r["is_sme"]) for r in rows)
    total = len(rows)
    wins = sum(1 for r in rows if r["is_winner"])
    win_rate = round(wins / total * 100, 1) if total else 0.0
    provinces = sorted({r["province"] for r in rows if r["province"]})
    discs = []
    for r in rows:
        d = _discount(_to_float(r["price_proposal"]), (r["budget"] or 0))
        if d is not None:
            discs.append(d)
    hist = []
    for lo in range(0, 40, 5):
        hist.append({"lo": lo, "hi": lo + 5, "count": sum(1 for d in discs if lo <= d < lo + 5)})
    hist.append({"lo": 40, "hi": None, "count": sum(1 for d in discs if d >= 40)})
    disc_avg = round(sum(discs) / len(discs), 1) if discs else None
    years = {}
    for r in rows:
        y = _year_th(r["project_id"])
        g = years.setdefault(y or 0, {"year": y, "bids": 0, "wins": 0, "jobs": []})
        g["bids"] += 1
        if r["is_winner"]:
            g["wins"] += 1
        g["jobs"].append({"project_id": r["project_id"], "name": r["project_name"] or r["project_id"],
                          "is_winner": bool(r["is_winner"]), "price": _to_float(r["price_proposal"]),
                          "discount": _discount(_to_float(r["price_proposal"]), (r["budget"] or 0))})
    by_year = []
    for key in sorted(years, key=lambda k: (k == 0, -(k or 0))):
        g = years[key]
        g["jobs"].sort(key=lambda j: j["project_id"], reverse=True)
        by_year.append(g)
    return {"name": name, "tin": tin, "is_sme": is_sme, "total_bids": total, "wins": wins,
            "win_rate": win_rate, "provinces": provinces, "discount_hist": hist,
            "discount_avg": disc_avg, "by_year": by_year}
