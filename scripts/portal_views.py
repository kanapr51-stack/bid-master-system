"""portal_views.py — หน้า detail งาน + ประวัติบริษัท (Portal Phase 2b / Phase 1).
Query bms_customers.db (bid_results + projects_seen) — รับ conn จาก caller (กัน circular import).
Render มือถือ-first, กราฟ inline CSS bar (ไม่พึ่ง chart lib)."""
import html as _h
import sqlite3
from datetime import datetime, timezone, timedelta

TZ_TH = timezone(timedelta(hours=7))
_TH_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _fmt_date_th(s):
    """'YYYY-MM-DD' → 'D ด. พ.ศ.'. parse ไม่ได้ → คืนค่าเดิม."""
    if not s:
        return ""
    try:
        d = datetime.fromisoformat(str(s)[:10]).date()
    except (ValueError, TypeError):
        return s
    return f"{d.day} {_TH_MONTHS[d.month]} {d.year + 543}"


def _countdown_th(s):
    """'YYYY-MM-DD' → นับถอยหลังถึงวันยื่นซอง (tz ไทย). parse ไม่ได้ → ''."""
    if not s:
        return ""
    try:
        d = datetime.fromisoformat(str(s)[:10]).date()
    except (ValueError, TypeError):
        return ""
    days = (d - datetime.now(TZ_TH).date()).days
    if days < 0:
        return "เลยกำหนดแล้ว"
    if days == 0:
        return "วันนี้วันสุดท้าย!"
    if days == 1:
        return "พรุ่งนี้วันสุดท้าย"
    return f"เหลืออีก {days} วัน"


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
    loc, deadline = "", None
    try:
        l = conn.execute(
            "SELECT moi_name, province_name, deadline FROM project_locations WHERE project_id=?",
            (pid,)).fetchone()
        if l:
            moi = (l["moi_name"] or "") if "moi_name" in l.keys() else ""
            prov = (l["province_name"] or "") if "province_name" in l.keys() else ""
            loc = ((f"ต.{moi} " if moi else "") + (f"จ.{prov}" if prov else "")).strip()
            deadline = (l["deadline"] if "deadline" in l.keys() else None) or None
    except sqlite3.OperationalError:
        loc, deadline = "", None
    if not loc and ps and ps["province"]:
        loc = f"จ.{ps['province']}"
    pred_lo = pred_hi = None
    try:
        pr = conn.execute(
            "SELECT area_price_lo, area_price_hi FROM price_predictions WHERE project_id=?",
            (pid,)).fetchone()
        if pr:
            pred_lo = _to_float(pr["area_price_lo"])
            pred_hi = _to_float(pr["area_price_hi"])
    except sqlite3.OperationalError:
        pred_lo = pred_hi = None
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
                    "location": loc, "budget": budget, "deadline": deadline,
                    "pred_lo": pred_lo, "pred_hi": pred_hi}, "bidders": bidders}


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
    ".dl{font-size:13px;color:#d9534f;margin:3px 0}"
    ".cd{font-size:13px;font-weight:600;color:#1d72b4;margin:3px 0}"
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
    ".nadd{display:flex;gap:6px;margin:8px 0;flex-wrap:wrap}"
    ".nadd input[type=text]{flex:1;min-width:120px}"
    ".nadd input,.nedit input,.nadd button,.nedit button,.ndel button{font-size:14px;padding:7px 9px;border:1px solid #ddd;border-radius:8px}"
    ".nadd button{background:#1db446;color:#fff;border:0}"
    ".rail{border-left:3px solid #1d72b4;margin:10px 0 10px 8px}"
    ".rstation{position:relative;padding:6px 0 12px 18px}"
    ".rstation::before{content:'';position:absolute;left:-9px;top:8px;width:13px;height:13px;border-radius:50%;background:#1d72b4;border:2px solid #fff}"
    ".rdate{font-size:13px;font-weight:700;color:#1d72b4;margin:0 0 4px}"
    ".nedit{display:inline-flex;gap:4px;flex-wrap:wrap}.ndel{display:inline}"
)


def _HEAD(title):
    return ("<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title><style>{_CSS}</style></head><body><div class=\"wrap\">")


_FOOT = "</div></body></html>"


def _baht(x):
    return f"{x:,.0f}" if x else "-"


def _render_timeline(pid, tok, notes):
    pe = _h.escape(str(pid))
    out = ["<div class=\"bidhead\">🚂 ไทม์ไลน์ของฉัน</div>",
           f"<form class=\"nadd\" method=\"post\" action=\"/portal/job/note\">"
           f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
           f"<input type=\"hidden\" name=\"pid\" value=\"{pe}\">"
           f"<input type=\"hidden\" name=\"action\" value=\"add\">"
           f"<input type=\"date\" name=\"entry_date\" required>"
           f"<input type=\"text\" name=\"note\" placeholder=\"สิ่งที่จะทำ เช่น โทรหาช่าง\" required>"
           f"<button type=\"submit\">➕ เพิ่ม</button></form>"]
    if not notes:
        out.append("<div class=\"msg\">ยังไม่มีรายการ — เพิ่มด้านบนได้เลย</div>")
        return "".join(out)
    out.append("<div class=\"rail\">")
    for nt in notes:
        nid = _h.escape(str(nt["id"]))
        dlabel = _h.escape(_fmt_date_th(nt["entry_date"]))
        dval = _h.escape(str(nt["entry_date"])[:10])
        txt = _h.escape(nt["note"])
        out.append(
            f"<div class=\"rstation\"><div class=\"rdate\">{dlabel}</div>"
            f"<form class=\"nedit\" method=\"post\" action=\"/portal/job/note\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"pid\" value=\"{pe}\">"
            f"<input type=\"hidden\" name=\"note_id\" value=\"{nid}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"edit\">"
            f"<input type=\"date\" name=\"entry_date\" value=\"{dval}\">"
            f"<input type=\"text\" name=\"note\" value=\"{txt}\">"
            f"<button type=\"submit\">💾</button></form>"
            f"<form class=\"ndel\" method=\"post\" action=\"/portal/job/note\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"pid\" value=\"{pe}\">"
            f"<input type=\"hidden\" name=\"note_id\" value=\"{nid}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"delete\">"
            f"<button type=\"submit\">🗑</button></form></div>")
    out.append("</div>")
    return "".join(out)


def render_job_page(data, token, exp, notes=None):
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
    if j.get("deadline"):
        b.append(f"<div class=\"dl\">⏰ ยื่นซอง {_h.escape(_fmt_date_th(j['deadline']))}</div>")
        cd = _countdown_th(j["deadline"])
        if cd:
            b.append(f"<div class=\"cd\">⏳ {cd}</div>")
    if j.get("pred_lo") and j.get("pred_hi"):
        b.append(f"<div class=\"meta\">💵 คาดราคา {_baht(j['pred_lo'])}–{_baht(j['pred_hi'])} บาท</div>")
    if not data["bidders"]:
        b.append("<div class=\"bidhead\">ยังไม่มีผู้ยื่น</div>")
        b.append("<div class=\"msg\">งานนี้ยังไม่มีข้อมูลผู้ยื่น — รอประมูล/ประกาศผล</div>")
    else:
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
    b.append(_render_timeline(j["project_id"], tok, notes or []))
    return head + "".join(b) + _FOOT


def _bar(lab, value, maxv, color, val_txt):
    pct = int(value / maxv * 100) if maxv else 0
    return (f"<div class=\"br2\"><span class=\"lab\">{_h.escape(str(lab))}</span>"
            f"<span class=\"track\"><span class=\"fill\" style=\"width:{pct}%;background:{color}\"></span></span>"
            f"<span class=\"val\">{val_txt}</span></div>")


def render_company_page(data, token, from_pid, exp):
    tok = _h.escape(token)
    head = _HEAD("ประวัติบริษัท")
    if from_pid:
        back = f"<a class=\"back\" href=\"/portal/job?t={tok}&pid={_h.escape(str(from_pid))}\">← กลับไปงาน</a>"
    else:
        back = f"<a class=\"back\" href=\"/portal?t={tok}\">← งานที่ติดตาม</a>"
    if not data:
        return head + back + "<div class=\"msg\">ไม่พบประวัติบริษัทนี้</div>" + _FOOT
    sme = " 🏷SME" if data["is_sme"] else ""
    b = [back, f"<div class=\"h\">🏢 {_h.escape(data['name'] or '(ไม่ระบุชื่อ)')}{sme}</div>",
         f"<div class=\"jid\">{_h.escape(data['tin'])}</div>"]
    # stat cards
    b.append("<div class=\"stats\">"
             f"<div class=\"stat\"><b>{data['total_bids']}</b><span>ยื่น</span></div>"
             f"<div class=\"stat\"><b>{data['wins']}</b><span>ชนะ</span></div>"
             f"<div class=\"stat\"><b>{data['win_rate']:.0f}%</b><span>win-rate</span></div>"
             f"<div class=\"stat\"><b>{len(data['provinces'])}</b><span>จังหวัด</span></div>"
             "</div>")
    # chart 1: ยื่น/ชนะ รายปี
    maxb = max([g["bids"] for g in data["by_year"]] or [1])
    rows1 = []
    for g in data["by_year"]:
        ylab = f"ปี {g['year']}" if g["year"] else "ไม่ทราบปี"
        rows1.append(_bar(ylab, g["bids"], maxb, "#1d72b4", f"ยื่น {g['bids']}"))
        rows1.append(_bar("", g["wins"], maxb, "#1a7f37", f"ชนะ {g['wins']}"))
    b.append("<div class=\"chart\"><div class=\"ct\">📊 ยื่น–ชนะ รายปี</div>" + "".join(rows1) + "</div>")
    # chart 2: ส่วนลดที่ชอบเสนอ
    maxh = max([x["count"] for x in data["discount_hist"]] or [1])
    rows2 = []
    for x in data["discount_hist"]:
        lab = f"{x['lo']}-{x['hi']}%" if x["hi"] is not None else f"≥{x['lo']}%"
        rows2.append(_bar(lab, x["count"], maxh, "#c2410c", str(x["count"])))
    avg = f" (เฉลี่ย {data['discount_avg']:.1f}%)" if data["discount_avg"] is not None else ""
    b.append(f"<div class=\"chart\"><div class=\"ct\">💸 ส่วนลดที่ชอบเสนอ{avg}</div>" + "".join(rows2) + "</div>")
    # timeline แยกรายปี
    for g in data["by_year"]:
        ylab = f"ปี {g['year']}" if g["year"] else "ไม่ทราบปี"
        b.append(f"<div class=\"yhead\">{ylab} — ยื่น {g['bids']} ชนะ {g['wins']}</div>")
        b.append("<div class=\"card\">")
        for j in g["jobs"]:
            mark = "✅" if j["is_winner"] else "▫️"
            disc = f"ส่วนลด {j['discount']:.1f}%" if j["discount"] is not None else "—"
            link = f"/portal/job?t={tok}&pid={_h.escape(str(j['project_id']))}"
            b.append(f"<div class=\"jrow\"><a class=\"jn\" href=\"{link}\">{mark} {_h.escape(j['name'])}</a>"
                     f"<span class=\"jp\">{_baht(j['price'])}<br><small>{disc}</small></span></div>")
        b.append("</div>")
    return head + "".join(b) + _FOOT


def _valid_date(s):
    try:
        datetime.strptime(str(s)[:10], "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _now_th():
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def list_job_notes(conn, customer_id, pid):
    if not customer_id:
        return []
    rows = conn.execute(
        "SELECT id, entry_date, note FROM job_notes WHERE customer_id=? AND project_id=? "
        "ORDER BY entry_date ASC, id ASC", (customer_id, pid)).fetchall()
    return [{"id": r["id"], "entry_date": r["entry_date"], "note": r["note"]} for r in rows]


def add_job_note(conn, customer_id, pid, entry_date, note):
    note = (note or "").strip()
    if not customer_id or not note or not _valid_date(entry_date):
        return
    now = _now_th()
    conn.execute(
        "INSERT INTO job_notes (customer_id, project_id, entry_date, note, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)", (customer_id, pid, str(entry_date)[:10], note, now, now))


def edit_job_note(conn, customer_id, note_id, entry_date, note):
    note = (note or "").strip()
    if not customer_id or not note or not _valid_date(entry_date):
        return
    try:
        note_id = int(note_id)
    except (TypeError, ValueError):
        return
    conn.execute(
        "UPDATE job_notes SET entry_date=?, note=?, updated_at=? WHERE id=? AND customer_id=?",
        (str(entry_date)[:10], note, _now_th(), note_id, customer_id))


def delete_job_note(conn, customer_id, note_id):
    if not customer_id:
        return
    try:
        note_id = int(note_id)
    except (TypeError, ValueError):
        return
    conn.execute("DELETE FROM job_notes WHERE id=? AND customer_id=?", (note_id, customer_id))
