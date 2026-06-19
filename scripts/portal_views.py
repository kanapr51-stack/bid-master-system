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


_CSS = (
    "body{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:18px;background:#f5f6f8;color:#222}"
    ".wrap{max-width:480px;margin:0 auto}"
    ".back{display:inline-block;font-size:14px;color:#1d72b4;text-decoration:none;margin:0 0 12px}"
    ".h{font-size:18px;font-weight:700;margin:2px 0 4px}"
    ".jid{font-size:12px;color:#aaa;margin:0 0 6px}"
    ".meta{font-size:13px;color:#777;margin:3px 0}"
    ".msg{font-size:15px;color:#555;margin:14px 0}"
    ".bidhead{font-size:14px;font-weight:700;color:#555;margin:16px 0 6px}"
    ".brow{display:flex;justify-content:space-between;gap:10px;font-size:13px;padding:8px 0;border-bottom:1px solid #eee}"
    ".brow .bn{flex:1;color:#333;text-decoration:none}.brow .bp{white-space:nowrap;text-align:right;color:#555}"
    ".brow .bp small{color:#999}"
    ".blink{color:#1d72b4 !important}"
    ".bwin{font-weight:700}.bwin .bn,.bwin .blink{color:#1a7f37 !important}.bwin .bp{color:#1a7f37}"
    ".card{background:#fff;border-radius:14px;padding:14px 16px;margin:8px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}"
    ".stats{display:flex;gap:8px;margin:10px 0}"
    ".stat{flex:1;background:#fff;border-radius:12px;padding:10px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.05)}"
    ".stat b{display:block;font-size:18px;color:#1d72b4}.stat span{font-size:11px;color:#888}"
    ".chart{background:#fff;border-radius:12px;padding:12px 14px;margin:10px 0;box-shadow:0 2px 8px rgba(0,0,0,.05)}"
    ".chart .ct{font-size:13px;font-weight:700;color:#555;margin:0 0 8px}"
    ".br2{display:flex;align-items:center;gap:8px;font-size:12px;margin:4px 0}"
    ".br2 .lab{width:64px;color:#666;white-space:nowrap}"
    ".br2 .track{flex:1;background:#eef0f3;border-radius:6px;height:14px;overflow:hidden}"
    ".br2 .fill{display:block;height:100%}"
    ".br2 .val{width:54px;text-align:right;color:#555;white-space:nowrap}"
    ".yhead{font-size:14px;font-weight:700;color:#333;margin:14px 0 4px}"
    ".jrow{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:6px 0;border-bottom:1px solid #f2f2f2}"
    ".jrow .jn{flex:1;color:#1d72b4;text-decoration:none}.jrow .jp{white-space:nowrap;text-align:right;color:#666}"
)


def _HEAD(title):
    return ("<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title><style>{_CSS}</style></head><body><div class=\"wrap\">")


_FOOT = "</div></body></html>"


def _baht(x):
    return f"{x:,.0f}" if x else "-"


def render_job_page(data, token, exp):
    tok = _h.escape(token)
    head = _HEAD("รายละเอียดงาน")
    back = f"<a class=\"back\" href=\"/portal?t={tok}\">← งานที่ติดตาม</a>"
    if not data:
        return head + back + "<div class=\"msg\">ไม่พบรายละเอียดงานนี้</div>" + _FOOT
    j = data["job"]
    b = [back, f"<div class=\"h\">🏗️ {_h.escape(j['name'])}</div>",
         f"<div class=\"jid\">🆔 {_h.escape(str(j['project_id']))}</div>"]
    if j["location"]:
        b.append(f"<div class=\"meta\">📍 {_h.escape(j['location'])}</div>")
    if j["budget"]:
        b.append(f"<div class=\"meta\">💰 ราคากลาง {_baht(j['budget'])} บาท</div>")
    b.append(f"<div class=\"bidhead\">ผู้ยื่นทั้งหมด ({len(data['bidders'])} ราย)</div>")
    for i, bid in enumerate(data["bidders"], 1):
        wm = "🏆 " if bid["is_winner"] else ""
        sme = " 🏷SME" if bid["is_sme"] else ""
        nm = _h.escape(bid["name"] or "(ไม่ระบุชื่อ)")
        disc = f"ส่วนลด {bid['discount']:.1f}%" if bid["discount"] is not None else "—"
        cls = "brow bwin" if bid["is_winner"] else "brow"
        if bid["tin"]:
            link = (f"/portal/company?t={tok}&tin={_h.escape(bid['tin'])}"
                    f"&from={_h.escape(str(j['project_id']))}")
            nmhtml = f"<a class=\"bn blink\" href=\"{link}\">{i}. {wm}{nm}{sme}</a>"
        else:
            nmhtml = f"<span class=\"bn\">{i}. {wm}{nm}{sme}</span>"
        b.append(f"<div class=\"{cls}\">{nmhtml}"
                 f"<span class=\"bp\">{_baht(bid['price'])}<br><small>{disc}</small></span></div>")
    return head + "".join(b) + _FOOT
