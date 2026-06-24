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


def job_detail(conn, pid, calc_params=None):
    ps = conn.execute(
        "SELECT project_name, budget, province FROM projects_seen WHERE project_id=?",
        (pid,)).fetchone()
    rows = conn.execute(
        "SELECT bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme "
        "FROM bid_results WHERE project_id=?", (pid,)).fetchall()
    if not rows and not ps:
        return None
    budget = (ps["budget"] if ps else 0) or 0
    dept_name = ""
    try:
        dn = conn.execute(
            "SELECT dept_name FROM projects_seen WHERE project_id=?", (pid,)).fetchone()
        if dn and "dept_name" in dn.keys():
            dept_name = dn["dept_name"] or ""
    except sqlite3.OperationalError:
        dept_name = ""
    intel_lines = None
    company_tables = None
    winrate_table = None
    custom_calc = None
    try:
        import cgd_intel
        intel_ctx = cgd_intel.intel_context(
            (ps["province"] if ps else "") or "", (ps["project_name"] if ps else "") or "",
            dept_name, pid, budget, conn)
        if intel_ctx:
            intel_lines = intel_ctx["lines"]
            company_tables = intel_ctx.get("company_tables")
            winrate_table = intel_ctx.get("winrate_table")
            if calc_params and company_tables:
                custom_calc = cgd_intel.calc_custom_winrate(
                    conn, (ps["province"] if ps else "") or "",
                    cgd_intel.match_keywords((ps["project_name"] if ps else "") or ""),
                    (ps["project_name"] if ps else "") or "", dept_name,
                    intel_ctx.get("amphoe"),
                    calc_params.get("my_price"), budget,
                    calc_params.get("selected_names") or [], calc_params.get("extra_names") or [])
    except Exception:
        intel_lines = None
    loc, deadline, deadline_time = "", None, None
    try:
        l = conn.execute(
            "SELECT moi_name, province_name, deadline, deadline_time FROM project_locations WHERE project_id=?",
            (pid,)).fetchone()
        if l:
            moi = (l["moi_name"] or "") if "moi_name" in l.keys() else ""
            prov = (l["province_name"] or "") if "province_name" in l.keys() else ""
            loc = ((f"ต.{moi} " if moi else "") + (f"จ.{prov}" if prov else "")).strip()
            deadline = (l["deadline"] if "deadline" in l.keys() else None) or None
            deadline_time = (l["deadline_time"] if "deadline_time" in l.keys() else None) or None
    except sqlite3.OperationalError:
        loc, deadline, deadline_time = "", None, None
    if not deadline or not deadline_time:
        # fallback: งาน rss วัน+เวลายื่นซองอยู่ใน project_enrichments (ไม่ถูก copy ไป project_locations)
        try:
            er = conn.execute(
                "SELECT bid_submit_date, bid_submit_time FROM project_enrichments WHERE project_id=?", (pid,)).fetchone()
            if er:
                if not deadline and er["bid_submit_date"]:
                    deadline = er["bid_submit_date"]
                if not deadline_time and ("bid_submit_time" in er.keys()) and er["bid_submit_time"]:
                    deadline_time = er["bid_submit_time"]
        except sqlite3.OperationalError:
            pass
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
                    "deadline_time": deadline_time,
                    "pred_lo": pred_lo, "pred_hi": pred_hi}, "bidders": bidders,
            "intel_lines": intel_lines, "company_tables": company_tables,
            "winrate_table": winrate_table, "custom_calc": custom_calc}


# proc_type → กลุ่ม. _PROC_BID mirror cgd_intel.COMPETITIVE_SET (source of truth ของ "แข่งราคาจริง")
_PROC_BID = frozenset((
    "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
    "ประกวดราคาด้วยวิธีการทางอิเล็กทรอนิกส์",
    "สอบราคา",
    "คัดเลือก",
))


def _proc_group(pt):
    """'bid' (ประมูล/แข่งขัน) | 'specific' (เฉพาะเจาะจง) | 'other' (พิเศษ/อื่นๆ)."""
    pt = pt or ""
    if pt in _PROC_BID:
        return "bid"
    if "เฉพาะเจาะจง" in pt or "ตกลงราคา" in pt:
        return "specific"
    return "other"


# legal-entity prefixes ตัดทิ้งก่อนเทียบชื่อ (eGP ย่อ 'หจก.' / CGD เต็ม 'ห้างหุ้นส่วนจำกัด')
_LEGAL_TOKENS = ("ห้างหุ้นส่วนจำกัด", "ห้างหุ้นส่วนสามัญ", "หจก.", "หจก", "บริษัท",
                 "บจก.", "บจก", "จำกัด", "(มหาชน)", "มหาชน", "นางสาว", "นาง", "นาย",
                 "กิจการร่วมค้า")


def _norm_name(s):
    """ตัด prefix นิติบุคคล + ช่องว่าง/จุด เหลือแกนชื่อ — สำหรับเทียบ exact. คืน '' ถ้าไม่เหลือ."""
    s = s or ""
    for tok in _LEGAL_TOKENS:
        s = s.replace(tok, "")
    return s.replace(" ", "").replace(".", "").replace("\t", "").replace("\n", "").strip()


def _prefilter_key(name):
    """คำยาวสุดของชื่อ (หลังตัด prefix) — ใช้เป็น LIKE prefilter ที่ยังคงอยู่ในค่าจริง (มี space)."""
    s = name or ""
    for tok in _LEGAL_TOKENS:
        s = s.replace(tok, "")
    words = [w for w in s.replace(".", " ").split() if w]
    return max(words, key=len) if words else ""


def won_portfolio(conn, name, proc="all"):
    """ผลงานที่ชนะของบริษัท (cgd_winners — ทุกวิธีจัดซื้อ, winner-only).
    join ด้วย 'ชื่อ' (winner) — winner_tin ใน source เพี้ยน ~99% (ดู progress_log N+157).
    match แบบ normalized_winner exact (index seek — เดิม LIKE scan ทั้งตาราง วัดจริง ~3s/ครั้ง
    หลัง cgd_winners โต 1.2M+ แถว ดู N+157.5 perf fix 2026-06-22).
    stats เต็มเสมอ; proc กรองเฉพาะ job list. คืน None ถ้าไม่มีตาราง/ชื่อสั้นเกิน/ไม่เจองาน."""
    core = _norm_name(name)
    if not core:
        return None
    try:
        rows = conn.execute(
            "SELECT project_id, project_name, winner, win_price, budget, proc_type "
            "FROM cgd_winners WHERE normalized_winner=?", (core,)).fetchall()
    except sqlite3.OperationalError:
        return None
    if not rows:
        return None
    groups = {k: {"count": 0, "value": 0.0} for k in ("bid", "specific", "other")}
    jobs = []
    for r in rows:
        price = _to_float(r["win_price"]) or 0.0
        g = _proc_group(r["proc_type"])
        groups[g]["count"] += 1
        groups[g]["value"] += price
        jobs.append({"pid": r["project_id"], "name": r["project_name"] or r["project_id"],
                     "price": price, "proc_type": r["proc_type"] or "", "group": g,
                     "discount": _discount(price, _to_float(r["budget"]) or 0)})
    total = {"count": len(jobs), "value": sum(j["price"] for j in jobs)}

    def _top(pool):
        pool = [j for j in pool if j["price"] > 0]
        if not pool:
            return None
        j = max(pool, key=lambda x: x["price"])
        return {"pid": j["pid"], "name": j["name"], "price": j["price"], "group": j["group"]}

    proc = proc if proc in ("bid", "specific", "other") else "all"
    shown = jobs if proc == "all" else [j for j in jobs if j["group"] == proc]
    shown.sort(key=lambda j: j["price"], reverse=True)
    return {"total": total, "groups": groups, "top_overall": _top(jobs),
            "top_bid": _top([j for j in jobs if j["group"] == "bid"]),
            "top_nonbid": _top([j for j in jobs if j["group"] != "bid"]),
            "proc": proc, "jobs": shown}


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


def area_portfolio(conn, name, project_ids):
    """ผลงานของ name เฉพาะใน project_ids (exact match — id มาจาก cgd_intel scope query เดิม,
    ไม่ใช่ fuzzy area parsing ใหม่ — bid_results มีพิกัดน้อยเกิน ~7/1084, deferred ใน spec 2026-06-20 §11).
    None ถ้า project_ids ว่าง หรือไม่เจองานของ name ใน id ชุดนั้น."""
    ids = [p for p in (project_ids or []) if p]
    if not ids:
        return None
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT project_id, project_name, win_price, budget FROM cgd_winners "
        f"WHERE project_id IN ({placeholders}) AND winner=?", (*ids, name)).fetchall()
    if not rows:
        return None
    jobs = []
    for r in rows:
        price = _to_float(r["win_price"])
        jobs.append({"project_id": r["project_id"], "name": r["project_name"] or r["project_id"],
                    "price": price, "discount": _discount(price, _to_float(r["budget"]) or 0),
                    "is_winner": True})
    return {"label_count": len(jobs), "jobs": jobs}


_CSS = (
    # background: soft pastel gradient (ไม่ขาวจืดเกินไป) — luminance สูงพอ ไม่กระทบ contrast ตัวอักษรเทาเดิม
    # line-height 1.8: งานวิจัย Cadson Demak/Microsoft Typography — ไทยมีวรรณยุกต์/สระบน-ล่าง
    # ต้องการพื้นที่แนวตั้งมากกว่าอังกฤษ (เดิม 1.5) ดู progress_log N+166
    "body{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:18px;"
    "background:linear-gradient(160deg,#f3f7fc 0%,#fbf7f0 100%);color:#222;line-height:1.8}"
    ".wrap{max-width:480px;margin:0 auto}"
    ".back{display:inline-block;font-size:14px;color:#1d72b4;text-decoration:none;margin:0 0 12px}"
    ".h{font-size:18px;font-weight:700;margin:2px 0 4px}"
    ".jid{font-size:12px;color:#aaa;margin:0 0 6px}"
    ".meta{font-size:13px;color:#666;margin:3px 0}"
    # ตัวเลขเด่น (เช่น คาดราคา) — ใหญ่/หนา/มีสี ให้กวาดตาเจอใน 3 วินาที (NN/g F-pattern)
    ".feature{font-size:16px;font-weight:700;color:#1d72b4;background:#eaf3fb;border-radius:10px;"
    "padding:8px 12px;margin:8px 0}"
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
    ".ovf{margin:8px 0}"
    ".ovf textarea{width:100%;box-sizing:border-box;font-size:14px;padding:9px;border:1px solid #ddd;"
    "border-radius:8px;font-family:inherit;resize:vertical}"
    ".ovf button{margin-top:6px;font-size:14px;padding:8px 14px;border:0;border-radius:8px;"
    "background:#1db446;color:#fff}"
    ".nadd{display:flex;gap:6px;margin:8px 0;flex-wrap:wrap}"
    ".nadd input[type=text]{flex:1;min-width:120px}"
    ".nadd input,.nedit input,.nadd button,.nedit button,.ndel button{font-size:14px;padding:7px 9px;border:1px solid #ddd;border-radius:8px}"
    ".nadd button{background:#1db446;color:#fff;border:0}"
    ".rail{border-left:3px solid #1d72b4;margin:10px 0 10px 8px}"
    ".rstation{position:relative;padding:6px 0 12px 18px}"
    ".rstation::before{content:'';position:absolute;left:-9px;top:8px;width:13px;height:13px;border-radius:50%;background:#1d72b4;border:2px solid #fff}"
    ".rdate{font-size:13px;font-weight:700;color:#1d72b4;margin:0 0 4px}"
    ".nedit{display:inline-flex;gap:4px;flex-wrap:wrap}.ndel{display:inline}"
    ".chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}"
    ".chip{font-size:12px;padding:5px 10px;border-radius:14px;background:#eef0f3;color:#555;text-decoration:none;white-space:nowrap}"
    ".chip.on{background:#1d72b4;color:#fff}"
    ".wonlist{margin-top:6px}"
    ".wonlist summary{cursor:pointer;font-size:13px;font-weight:700;color:#1d72b4;padding:6px 0;list-style:none}"
    ".wonlist summary::-webkit-details-marker{display:none}"
    ".wonlist summary::before{content:'▸ ';font-size:11px}"
    ".wonlist[open] summary::before{content:'▾ '}"
    ".rstation.today::before{background:#f7941d}"
    ".rdate.today{color:#f7941d}"
    ".rstation.past::before{background:#d9534f}"
    ".rdate.past{color:#d9534f}"
    ".pastlist summary{color:#d9534f}"
    ".star{font-size:20px;text-decoration:none;margin-left:8px;vertical-align:middle}"
    # กัญจน์ทักว่า card-transform เดิมแยกแถวเป็นกล่องลอยหลายกล่อง อ่านไม่รู้สึกเป็นตารางเดียว
    # → กลับมาเป็นตารางจริง 1 กล่อง มีเส้นกรอบ (grid) รอบทุก cell ชัดเจน ห่อด้วย .tblwrap กล่องเดียว
    ".itbl{width:100%;border-collapse:collapse;font-size:12px;line-height:1.4}"
    # เส้นกรอบแค่ขวา+ล่างของแต่ละ cell (ไม่ใส่บน/ซ้าย) — รวมกันมองเป็นเส้นตารางครบทุกช่อง
    # แต่ไม่ไปชนกับกรอบมุมโค้งของ .tblwrap รอบนอก (เลี่ยงเส้นซ้อนที่มุม)
    ".itbl th,.itbl td{padding:6px 8px;text-align:right;white-space:nowrap;"
    "border-right:1px solid #e3e7eb;border-bottom:1px solid #e3e7eb}"
    ".itbl th:first-child,.itbl td:first-child{text-align:left}"
    ".itbl tr th:last-child,.itbl tr td:last-child{border-right:0}"
    ".itbl tr:last-child td{border-bottom:0}"
    ".itbl th{color:#555;font-weight:600;background:#f3f6f9}"
    ".itbl a{color:#1d72b4;text-decoration:none}"
    ".itbl .notin{color:#999}"
    ".tblwrap{overflow-x:auto;margin:8px 0;-webkit-overflow-scrolling:touch;"
    "border-radius:12px;border:1px solid #e3e7eb;background:#fff}"
    ".calcform{margin:10px 0}"
    ".calcform label{display:block;font-size:13px;padding:4px 0;color:#444}"
    ".calcform textarea{width:100%;box-sizing:border-box;font-size:14px;padding:9px;"
    "border:1px solid #ddd;border-radius:8px;font-family:inherit;resize:vertical;margin:4px 0}"
    ".calcform input[type=number]{font-size:14px;padding:7px 9px;border:1px solid #ddd;"
    "border-radius:8px;width:160px}"
    ".calcform button{margin-top:8px;font-size:14px;padding:8px 14px;border:0;border-radius:8px;"
    "background:#1d72b4;color:#fff}"
    ".calcresult{background:#fff;border-radius:12px;padding:12px 14px;margin:10px 0;"
    "box-shadow:0 2px 8px rgba(0,0,0,.05)}"
    ".calcresult .big{font-size:20px;font-weight:700;color:#1d72b4;margin:0 0 8px}"
    ".calcresult .crow{display:flex;justify-content:space-between;gap:8px;font-size:13px;"
    "padding:4px 0;border-bottom:1px solid #f2f2f2}"
    ".calcresult .note{font-size:12px;color:#888;margin-top:8px}"
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


def _render_overview(pid, tok, overview):
    pe = _h.escape(str(pid))
    return (
        "<div class=\"bidhead\">📝 โน้ตภาพรวม</div>"
        "<form class=\"ovf\" method=\"post\" action=\"/portal/job/note\">"
        f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
        f"<input type=\"hidden\" name=\"pid\" value=\"{pe}\">"
        "<input type=\"hidden\" name=\"action\" value=\"save_overview\">"
        f"<textarea name=\"note\" rows=\"4\" placeholder=\"จดภาพรวมงานนี้ เช่น คนติดต่อ งบ เงื่อนไข จุดเด่น...\">"
        f"{_h.escape(overview or '')}</textarea>"
        "<button type=\"submit\">💾 บันทึกโน้ต</button></form>")


def _render_company_tables(tables, tok):
    """ตารางบริษัทคู่แข่งแบบเต็ม (ไม่จำกัด 3) ต่อ scope — ชื่อ resolve tin ได้ = ลิงก์ /portal/company, ไม่ได้ = grey."""
    out = []
    for blk in tables:
        if not blk.get("companies"):
            continue
        out.append(f"<div class=\"bidhead\">🏢 คู่แข่ง {_h.escape(blk['label'])} "
                   f"({blk['n']} งาน {blk['conf_tag']})</div>")
        out.append("<div class=\"tblwrap\"><table class=\"itbl\"><tr><th>บริษัท</th>"
                   "<th>งาน</th><th>ลด%</th></tr>")
        for cmp_ in blk["companies"]:
            nm = _h.escape(cmp_["name"])
            disc = f"{cmp_['median']:.0f}%" if cmp_.get("median") is not None else "—"
            if cmp_.get("tin"):
                ids = ",".join(str(p) for p in (cmp_.get("project_ids") or []))
                href = (f"/portal/company?t={tok}&tin={_h.escape(cmp_['tin'])}"
                       f"&area_ids={_h.escape(ids)}&area_label={_h.escape(blk['label'])}")
                name_html = f"<a href=\"{href}\">{nm}</a>"
            else:
                name_html = f"<span class=\"notin\">{nm}</span>"
            out.append(f"<tr><td>{name_html}</td><td>{cmp_['games']}</td><td>{disc}</td></tr>")
        out.append("</table></div>")
    return "".join(out)


def _render_winrate_table(wt):
    """ตารางโอกาสชนะตามจำนวนผู้ยื่น N=1..max เต็ม (เดิม 3 คอลัมน์ mean±SD)."""
    ns, rows = wt["ns"], wt["rows"]
    out = [f"<div class=\"bidhead\">💵 โอกาสชนะตามจำนวนผู้ยื่น (งบ {wt['budget']:,.0f})</div>",
           "<div class=\"tblwrap\"><table class=\"itbl\"><tr><th>ราคายื่น</th>"
           + "".join(f"<th>{k} ราย</th>" for k in ns) + "</tr>"]
    for price, ws in rows:
        out.append(f"<tr><td>{price:,.0f}</td>" + "".join(f"<td>{w}%</td>" for w in ws) + "</tr>")
    out.append("</table></div>")
    sd_txt = f" (±{round(wt['n_sd'])})" if len(ns) > 1 else ""
    out.append(f"<div class=\"meta\">📊 สนามนี้เฉลี่ย {round(wt['n_mean'])} ผู้ยื่น{sd_txt} "
              f"· จาก {wt['n_auctions']} งาน · {wt['n_bids']} ราย</div>")
    if wt.get("conf"):
        emoji, scope_word = wt["conf"]
        out.append(f"<div class=\"meta\">{emoji} โอกาส% อิง{scope_word} (พื้นที่นี้ข้อมูลบาง)</div>")
    return "".join(out)


def _render_custom_calc_form(company_tables, custom_calc, prefill, tok, pid):
    """ฟอร์มคำนวณโอกาสชนะเจาะจงคู่แข่ง (N+168) — checkbox จาก company_tables (dedupe ด้วยชื่อ
    normalized) + textarea พิมพ์ชื่อเพิ่ม + ราคาที่จะยื่น. ไม่มี JS — submit จริงไปหลังบ้าน."""
    prefill = prefill or {}
    seen, opts = set(), []
    for blk in company_tables or []:
        for cmp_ in blk.get("companies") or []:
            core = _norm_name(cmp_["name"])
            if core and core not in seen:
                seen.add(core)
                opts.append(cmp_)
    checked_names = set(prefill.get("selected_names") or [])
    out = ["<div class=\"bidhead\">🎯 คำนวณโอกาสชนะเจาะจงคู่แข่ง</div>",
           "<form class=\"calcform\" method=\"post\" action=\"/portal/job/calc\">",
           f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">",
           f"<input type=\"hidden\" name=\"pid\" value=\"{_h.escape(str(pid))}\">"]
    for cmp_ in opts:
        nm = _h.escape(cmp_["name"])
        chk = " checked" if cmp_["name"] in checked_names else ""
        if cmp_.get("median") is not None:
            out.append(f"<label><input type=\"checkbox\" name=\"competitors\" value=\"{nm}\"{chk}> "
                       f"{nm} (ชนะ {cmp_['games']} งาน, ลดเฉลี่ย {cmp_['median']:.0f}%)</label>")
        else:
            out.append(f"<label><input type=\"checkbox\" name=\"competitors\" value=\"{nm}\"{chk}> {nm}</label>")
    extra_pf = _h.escape("\n".join(prefill.get("extra_names") or []))
    out.append("<label>หรือพิมพ์ชื่อบริษัทอื่นเพิ่ม (1 ชื่อ/บรรทัด):</label>"
               f"<textarea name=\"extra_names\" rows=\"2\">{extra_pf}</textarea>")
    price_pf = _h.escape(str(prefill.get("my_price") or ""))
    out.append("<label>ราคาที่จะยื่น (บาท):</label>"
               f"<input type=\"number\" name=\"my_price\" value=\"{price_pf}\" min=\"1\" step=\"1\">"
               "<button type=\"submit\">คำนวณโอกาสชนะ</button></form>")
    if custom_calc:
        out.append(f"<div class=\"calcresult\"><div class=\"big\">🎯 โอกาสชนะของคุณรวม: "
                   f"{custom_calc['overall_win_pct']}%</div>"
                   f"<div class=\"meta\">ราคาของคุณ = ลด {custom_calc['my_discount_pct']}%</div>")
        for b in custom_calc["breakdown"]:
            src = b.get("source") or ""
            src_note = f" ({src})" if src else ""
            out.append(f"<div class=\"crow\"><span>{_h.escape(b['name'])}{src_note}</span>"
                       f"<span>ชนะคุณ ~{b['win_pct_against']}%</span></div>")
        out.append("<div class=\"note\">*โอกาส% ประเมินจากนิสัยการยื่นราคาของคู่แข่งในงานประเภท+หน่วยงาน"
                   "แบบเดียวกัน (โมเดล Gates) — เป็นการประมาณ ไม่ใช่การรับประกัน</div></div>")
    elif custom_calc is None and prefill.get("my_price"):
        out.append("<div class=\"msg\">เลือกคู่แข่งอย่างน้อย 1 บริษัท หรือกรอกราคาให้ถูกต้อง</div>")
    return "".join(out)


def render_job_page(data, token, exp, notes=None, overview="", starred=False):
    tok = _h.escape(token)
    head = _HEAD("รายละเอียดงาน")
    back = f"<a class=\"back\" href=\"/portal?t={tok}\">← งานที่ติดตาม</a>"
    if not data:
        return head + back + "<div class=\"msg\">ไม่พบรายละเอียดงานนี้</div>" + _FOOT
    j = data["job"]
    pid_esc = _h.escape(str(j["project_id"]))
    star_href = f"/portal/star_toggle?t={tok}&pid={pid_esc}&back=job"
    star_icon = "⭐" if starred else "☆"
    b = [back, f"<div class=\"h\">🏗️ {_h.escape(j['name'])}<a class=\"star\" href=\"{star_href}\">{star_icon}</a></div>",
         f"<div class=\"jid\">🆔 {pid_esc}</div>"]
    if j["location"]:
        b.append(f"<div class=\"meta\">📍 {_h.escape(j['location'])}</div>")
    if j["budget"]:
        b.append(f"<div class=\"meta\">💰 ราคากลาง {_baht(j['budget'])} บาท</div>")
    if j.get("deadline"):
        _dl = _fmt_date_th(j['deadline'])
        if j.get("deadline_time"):
            _dl += " " + j["deadline_time"]
        b.append(f"<div class=\"dl\">⏰ ยื่นซอง {_h.escape(_dl)}</div>")
        cd = _countdown_th(j["deadline"])
        if cd:
            b.append(f"<div class=\"cd\">⏳ {cd}</div>")
    if j.get("pred_lo") and j.get("pred_hi"):
        b.append(f"<div class=\"feature\">💵 คาดราคา {_baht(j['pred_lo'])}–{_baht(j['pred_hi'])} บาท</div>")
    if data.get("intel_lines"):
        b.append("<div class=\"bidhead\">📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่</div>")
        for line in data["intel_lines"]:
            b.append(f"<div class=\"meta\">{_h.escape(line)}</div>")
    if data.get("company_tables"):
        b.append(_render_company_tables(data["company_tables"], tok))
    if data.get("winrate_table"):
        b.append(_render_winrate_table(data["winrate_table"]))
    if data.get("company_tables"):
        b.append(_render_custom_calc_form(data["company_tables"], data.get("custom_calc"),
                                          data.get("calc_prefill"), tok, j["project_id"]))
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
    b.append(_render_overview(j["project_id"], tok, overview or ""))
    b.append(_render_timeline(j["project_id"], tok, notes or []))
    return head + "".join(b) + _FOOT


def _render_today_card(today_items, tomorrow_items, today_label):
    if today_items:
        line = " · ".join(f"{_h.escape(it['project_name'])} — {_h.escape(it['note'])}" for it in today_items)
        today_line = f"วันนี้: {line}"
    else:
        today_line = "วันนี้: ⚪ ไม่มีรายการ"
    if tomorrow_items:
        it = tomorrow_items[0]
        tom_line = f"🔔 พรุ่งนี้: {_h.escape(it['project_name'])} — {_h.escape(it['note'])}"
    else:
        tom_line = "🔔 พรุ่งนี้: ⚪ ไม่มีรายการ"
    return (f"<div class=\"card\"><div class=\"rdate\">📅 {_h.escape(today_label)}</div>"
            f"<div class=\"meta\">{today_line}</div>"
            f"<div class=\"meta\">{tom_line}</div></div>")


def render_timeline_page(notes, token, exp):
    """หน้า /portal/timeline — รวม job_notes ทุกงานเป็นรางเดียว. read+navigate เท่านั้น (แก้โน้ตที่หน้างานเดิม)."""
    tok = _h.escape(token)
    head = _HEAD("ไทม์ไลน์รวมทุกงาน")
    b = [f"<a class=\"back\" href=\"/portal?t={tok}\">← Bid Board</a>",
         "<div class=\"h\">🚂 ไทม์ไลน์รวมทุกงาน</div>"]
    if not notes:
        b.append("<div class=\"msg\">ยังไม่มีรายการในไทม์ไลน์ — เพิ่มได้จากหน้างานแต่ละงาน</div>")
        return head + "".join(b) + _FOOT

    today = datetime.now(TZ_TH).date()
    tomorrow = today + timedelta(days=1)

    def _d(n):
        try:
            return datetime.fromisoformat(str(n["entry_date"])[:10]).date()
        except (ValueError, TypeError):
            return today

    past = sorted((n for n in notes if _d(n) < today), key=_d, reverse=True)
    upcoming = sorted((n for n in notes if _d(n) >= today), key=_d)
    today_items = [n for n in upcoming if _d(n) == today]
    tomorrow_items = [n for n in upcoming if _d(n) == tomorrow]
    today_label = f"วันนี้ {_fmt_date_th(today.isoformat())}"

    def _station(n, dcls, dlabel):
        link = f"/portal/job?t={tok}&pid={_h.escape(str(n['project_id']))}"
        rcls = f"rstation {dcls}".strip()
        dcls_full = f"rdate {dcls}".strip()
        return (f"<div class=\"{rcls}\"><div class=\"{dcls_full}\">{_h.escape(dlabel)}</div>"
                f"<div class=\"meta\"><a class=\"blink\" href=\"{link}\">{_h.escape(n['project_name'])}</a>"
                f" — {_h.escape(n['note'])}</div></div>")

    b.append(_render_today_card(today_items, tomorrow_items, today_label))
    b.append("<div class=\"rail\">")
    for n in upcoming:
        d = _d(n)
        if d == today:
            dcls, dlabel = "today", today_label
        elif d == tomorrow:
            dcls, dlabel = "", f"พรุ่งนี้ {_fmt_date_th(n['entry_date'])}"
        else:
            dcls, dlabel = "", _fmt_date_th(n["entry_date"])
        b.append(_station(n, dcls, dlabel))
    b.append("</div>")
    if past:
        b.append(f"<details class=\"wonlist pastlist\"><summary>🔴 ที่ผ่านมา / เลยกำหนด ({len(past)})</summary>")
        for n in past:
            b.append(_station(n, "past", _fmt_date_th(n["entry_date"])))
        b.append("</details>")
    return head + "".join(b) + _FOOT


def _bar(lab, value, maxv, color, val_txt):
    pct = int(value / maxv * 100) if maxv else 0
    return (f"<div class=\"br2\"><span class=\"lab\">{_h.escape(str(lab))}</span>"
            f"<span class=\"track\"><span class=\"fill\" style=\"width:{pct}%;background:{color}\"></span></span>"
            f"<span class=\"val\">{val_txt}</span></div>")


def _render_h2h(h2h):
    """section ⚔️ เทียบกับเรา (head-to-head)."""
    win_pct = round(h2h["our_wins"] / h2h["shared"] * 100) if h2h["shared"] else 0
    out = [f"<div class=\"chart\"><div class=\"ct\">⚔️ เทียบกับ {_h.escape(h2h['our_name'])}</div>",
           "<div class=\"stats\">"
           f"<div class=\"stat\"><b>{h2h['shared']}</b><span>เจอกัน</span></div>"
           f"<div class=\"stat\"><b>{h2h['our_wins']}</b><span>เราชนะ</span></div>"
           f"<div class=\"stat\"><b>{h2h['their_wins']}</b><span>เขาชนะ</span></div>"
           f"<div class=\"stat\"><b>{win_pct}%</b><span>เราชนะ%</span></div>"
           "</div>"]
    for j in h2h["jobs"][:10]:
        mark = {"us": "🟢 เราชนะ", "them": "🔴 เขาชนะ", "other": "⚪ รายอื่นชนะ"}[j["winner_side"]]
        out.append(
            f"<div class=\"jrow\"><span class=\"jn\">{_h.escape(j['name'])}</span></div>"
            f"<div class=\"meta\">{mark} · เรา {_baht(j['our_price'])} / เขา {_baht(j['their_price'])}</div>")
    out.append("</div>")
    return "".join(out)


_PROC_LABELS = {"all": "ทั้งหมด", "bid": "ประมูล", "specific": "เจาะจง", "other": "วิธีอื่น"}


def _render_won(wp, tin, tok, from_pid):
    """section 🏆 ผลงานที่ชนะ (ทุกวิธีจัดซื้อ) — stat ประมูล/เจาะจง + มูลค่าสูงสุด + filter proc."""
    g = wp["groups"]
    out = ["<div class=\"chart\"><div class=\"ct\">🏆 ผลงานที่ชนะ (ทุกวิธีจัดซื้อ)</div>",
           "<div class=\"stats\">"
           f"<div class=\"stat\"><b>{g['bid']['count']}</b><span>ประมูล {_baht(g['bid']['value'])}</span></div>"
           f"<div class=\"stat\"><b>{g['specific']['count']}</b><span>เจาะจง {_baht(g['specific']['value'])}</span></div>"
           f"<div class=\"stat\"><b>{wp['total']['count']}</b><span>รวม {_baht(wp['total']['value'])}</span></div>"
           "</div>"]
    if wp["top_overall"]:
        t = wp["top_overall"]
        out.append(f"<div class=\"meta\">💎 มูลค่าสูงสุด: {_h.escape(t['name'])} — {_baht(t['price'])} บาท</div>")
    if wp["top_bid"]:
        out.append(f"<div class=\"meta\">🥇 สูงสุด (ประมูล): {_h.escape(wp['top_bid']['name'])} — {_baht(wp['top_bid']['price'])}</div>")
    if wp["top_nonbid"]:
        out.append(f"<div class=\"meta\">🥈 สูงสุด (วิธีอื่น): {_h.escape(wp['top_nonbid']['name'])} — {_baht(wp['top_nonbid']['price'])}</div>")
    frag = f"&from={_h.escape(str(from_pid))}" if from_pid else ""
    chips = []
    for key in ("all", "bid", "specific", "other"):
        cnt = wp["total"]["count"] if key == "all" else g[key]["count"]
        cls = "chip on" if wp["proc"] == key else "chip"
        chips.append(f"<a class=\"{cls}\" href=\"/portal/company?t={tok}&tin={_h.escape(tin)}"
                     f"&proc={key}{frag}\">{_PROC_LABELS[key]} {cnt}</a>")
    out.append("<div class=\"chips\">" + "".join(chips) + "</div>")
    # รายชื่องานซ่อนใน <details> — เปิดเองเมื่อ filter อยู่ (proc != all)
    op = " open" if wp["proc"] != "all" else ""
    out.append(f"<details class=\"wonlist\"{op}><summary>📋 ดูรายชื่องาน ({len(wp['jobs'])})</summary>")
    if not wp["jobs"]:
        out.append("<div class=\"msg\">ไม่มีงานในกลุ่มนี้</div>")
    for j in wp["jobs"][:50]:
        disc = f"ส่วนลด {j['discount']:.1f}%" if j["discount"] is not None else "—"
        out.append(f"<div class=\"jrow\"><span class=\"jn\">{_h.escape(j['name'])}</span>"
                   f"<span class=\"jp\">{_baht(j['price'])}<br><small>{disc}</small></span></div>")
    out.append("</details></div>")
    return "".join(out)


def render_company_page(data, token, from_pid, exp, h2h=None, won=None, area=None, area_label=""):
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
    # ⚔️ เทียบกับเรา (head-to-head) — โชว์เฉพาะมี company_tin + เจอกัน
    if h2h:
        b.append(_render_h2h(h2h))
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
    # 🏆 ผลงานที่ชนะทุกวิธีจัดซื้อ (cgd_winners) — หลังกราฟ, โชว์เฉพาะมีข้อมูล
    if won:
        b.append(_render_won(won, data["tin"], tok, from_pid))
    # 📍 ผลงานในพื้นที่นี้ — เฉพาะเมื่อเข้ามาจากลิงก์ scope (area_ids) ก่อน timeline แยกรายปี (decision: ชูพื้นที่นี้ก่อน)
    if area:
        b.append(f"<div class=\"chart\"><div class=\"ct\">📍 ผลงานในพื้นที่นี้"
                 f"{(' — ' + _h.escape(area_label)) if area_label else ''} ({area['label_count']} งาน)</div>")
        for j in area["jobs"]:
            disc = f"ส่วนลด {j['discount']:.1f}%" if j["discount"] is not None else "—"
            link = f"/portal/job?t={tok}&pid={_h.escape(str(j['project_id']))}"
            b.append(f"<div class=\"jrow\"><a class=\"jn\" href=\"{link}\">✅ {_h.escape(j['name'])}</a>"
                     f"<span class=\"jp\">{_baht(j['price'])}<br><small>{disc}</small></span></div>")
        b.append("</div>")
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


def all_job_notes(conn, customer_id):
    """job_notes ทุกงานของ user (join ชื่องาน) — สำหรับหน้า /portal/timeline. คืน [] ถ้าไม่มี customer."""
    if not customer_id:
        return []
    rows = conn.execute(
        "SELECT jn.id, jn.project_id, jn.entry_date, jn.note, ps.project_name "
        "FROM job_notes jn LEFT JOIN projects_seen ps ON ps.project_id = jn.project_id "
        "WHERE jn.customer_id=? ORDER BY jn.entry_date ASC, jn.id ASC", (customer_id,)).fetchall()
    return [{"id": r["id"], "project_id": r["project_id"],
             "project_name": r["project_name"] or r["project_id"],
             "entry_date": r["entry_date"], "note": r["note"]} for r in rows]


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


def get_job_overview(conn, customer_id, pid):
    """โน้ตภาพรวม free-form ของ user ต่องาน. คืน '' ถ้าไม่มี."""
    if not customer_id:
        return ""
    r = conn.execute(
        "SELECT note FROM job_overview WHERE customer_id=? AND project_id=?",
        (customer_id, pid)).fetchone()
    return (r["note"] if r else "") or ""


def save_job_overview(conn, customer_id, pid, note):
    """upsert โน้ตภาพรวม (1 อันต่อ customer/project). note ว่าง = ลบ."""
    if not customer_id:
        return
    note = (note or "").strip()
    if not note:
        conn.execute("DELETE FROM job_overview WHERE customer_id=? AND project_id=?",
                     (customer_id, pid))
        return
    now = _now_th()
    cur = conn.execute(
        "UPDATE job_overview SET note=?, updated_at=? WHERE customer_id=? AND project_id=?",
        (note, now, customer_id, pid))
    if cur.rowcount == 0:
        conn.execute(
            "INSERT INTO job_overview (customer_id, project_id, note, created_at, updated_at) "
            "VALUES (?,?,?,?,?)", (customer_id, pid, note, now, now))


def toggle_star(conn, customer_id, pid):
    """สลับ ⭐ 'ที่สนใจ' (ชั้นที่ 2, แยกจาก followed_jobs.starred_at) ของ (customer, project).
    คืนสถานะใหม่ (True=ติดดาวแล้ว). no-op คืน False ถ้าไม่มี customer."""
    if not customer_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM job_stars WHERE customer_id=? AND project_id=?", (customer_id, pid)).fetchone()
    if row:
        conn.execute("DELETE FROM job_stars WHERE customer_id=? AND project_id=?", (customer_id, pid))
        return False
    conn.execute("INSERT INTO job_stars (customer_id, project_id, created_at) VALUES (?,?,?)",
                 (customer_id, pid, _now_th()))
    return True


def starred_project_ids(conn, customer_id):
    """set ของ project_id ที่ user ติดดาว 'ที่สนใจ' ไว้. คืน set() ถ้าไม่มี customer."""
    if not customer_id:
        return set()
    rows = conn.execute("SELECT project_id FROM job_stars WHERE customer_id=?", (customer_id,)).fetchall()
    return {r["project_id"] for r in rows}


def head_to_head(conn, our_tin, competitor_tin):
    """เทียบ 'เรา' (our_tin) กับคู่แข่ง (competitor_tin) เฉพาะงานที่ยื่นด้วยกัน.
    คืน {our_name, shared, our_wins, their_wins, other, jobs:[{project_id,name,our_price,
    their_price,winner_side}]} | None (ไม่มี tin / tin เดียวกัน / ไม่มีงานเจอกัน)."""
    if not our_tin or not competitor_tin or our_tin == competitor_tin:
        return None
    rows = conn.execute(
        "SELECT br.project_id, br.bidder_tin, br.bidder_name, br.price_proposal, br.is_winner, "
        "ps.project_name "
        "FROM bid_results br LEFT JOIN projects_seen ps ON ps.project_id = br.project_id "
        "WHERE br.bidder_tin IN (?, ?)", (our_tin, competitor_tin)).fetchall()
    our_name = next((r["bidder_name"] for r in rows if r["bidder_tin"] == our_tin and r["bidder_name"]), "")
    byproj = {}
    for r in rows:
        p = byproj.setdefault(r["project_id"], {"name": r["project_name"] or r["project_id"],
                                                "us": None, "them": None})
        side = "us" if r["bidder_tin"] == our_tin else "them"
        p[side] = {"price": _to_float(r["price_proposal"]), "is_winner": bool(r["is_winner"])}
    shared = [(pid, v) for pid, v in byproj.items() if v["us"] and v["them"]]
    if not shared:
        return None
    jobs = []
    our_wins = their_wins = other = 0
    for pid, v in shared:
        if v["us"]["is_winner"]:
            wside = "us"; our_wins += 1
        elif v["them"]["is_winner"]:
            wside = "them"; their_wins += 1
        else:
            wside = "other"; other += 1
        jobs.append({"project_id": pid, "name": v["name"], "our_price": v["us"]["price"],
                     "their_price": v["them"]["price"], "winner_side": wside})
    jobs.sort(key=lambda j: j["project_id"], reverse=True)
    return {"our_name": our_name or "บริษัทเรา", "shared": len(shared), "our_wins": our_wins,
            "their_wins": their_wins, "other": other, "jobs": jobs}
