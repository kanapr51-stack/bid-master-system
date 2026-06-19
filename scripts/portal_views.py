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
