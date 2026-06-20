"""
bms_api.py -- FastAPI bridge for BMS VPS
Receives webhooks from LINE Messaging API + preferences from portal.

Endpoints:
  GET  /health                  -- liveness check
  POST /webhook/line            -- LINE events: follow/unfollow/message (LINE signature verified)
  POST /api/preferences         -- province preferences from portal (X-BMS-Secret verified)
"""
import hashlib
import hmac
import json
import base64
import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

sys.path.insert(0, str(Path(__file__).parent))
import follow_token  # noqa: E402
import portal_views  # noqa: E402

# -- Config -------------------------------------------------------------------

DB_PATH              = Path(os.getenv("BMS_DB_PATH", "/opt/bms/data/bms_customers.db"))
LINE_CHANNEL_SECRET  = os.getenv("SEBASTIAN_LINE_SECRET", "")
LINE_ACCESS_TOKEN    = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
BMS_INTERNAL_SECRET  = os.getenv("BMS_INTERNAL_SECRET", "")
TZ_TH = timezone(timedelta(hours=7))

LINE_API = "https://api.line.me/v2/bot"
PUBLIC_BASE_URL = os.getenv("BMS_PUBLIC_BASE_URL", "https://api.butler-bms.com")

# in-memory conversation state: {user_id: "waiting_province"}
_conv_state: dict[str, str] = {}

app = FastAPI(title="BMS API Bridge", version="1.3")


def _now() -> str:
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# -- LINE helpers -------------------------------------------------------------

def _line_headers() -> dict:
    return {"Authorization": "Bearer " + LINE_ACCESS_TOKEN}


async def fetch_line_profile(user_id: str):
    """Return (display_name, picture_url). Falls back to 'LINE User' on error."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                LINE_API + "/profile/" + user_id,
                headers=_line_headers(),
            )
        if r.status_code == 200:
            data = r.json()
            return data.get("displayName", "LINE User"), data.get("pictureUrl")
    except Exception:
        pass
    return "LINE User", None


async def push_message(user_id: str, text: str) -> None:
    """Push message to a LINE user (no replyToken needed)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                LINE_API + "/message/push",
                headers={**_line_headers(), "Content-Type": "application/json"},
                json={"to": user_id, "messages": [{"type": "text", "text": text}]},
            )
    except Exception:
        pass


async def reply_message(reply_token: str, text: str) -> None:
    """Reply via replyToken -- must call within ~30s of receiving the event."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                LINE_API + "/message/reply",
                headers={**_line_headers(), "Content-Type": "application/json"},
                json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
            )
    except Exception:
        pass


async def reply_raw(reply_token: str, messages: list) -> None:
    """Reply ด้วย messages ดิบ (รองรับ flex). reply ฟรี ไม่กิน quota."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                LINE_API + "/message/reply",
                headers={**_line_headers(), "Content-Type": "application/json"},
                json={"replyToken": reply_token, "messages": messages},
            )
    except Exception:
        pass


# -- Message text helpers (ASCII quotes only, no smart/curly quotes) ----------

def _welcome_text(display_name: str) -> str:
    return "\n".join([
        "สวัสดีครับ คุณ" + display_name + " \U0001f44b",
        "",
        "ผม Sebastian ผู้ช่วยติดตามงานประมูลภาครัฐ",
        "",
        "เมื่อมีโครงการใหม่ในพื้นที่ที่คุณสนใจ ผมจะแจ้งเตือนทันทีครับ",
        "",
        "พิมพ์ \U0001f449 ตั้งค่า เพื่อเลือกจังหวัดที่ต้องการติดตามได้เลยครับ",
        "พิมพ์ ช่วย เพื่อดูคำสั่งทั้งหมด",
    ])


def _help_text() -> str:
    return "\n".join([
        "\U0001f4d6 คำสั่งของ Sebastian",
        "",
        "ช่วย    -- แสดงคำสั่งทั้งหมด",
        "สถานะ  -- ดูจังหวัดที่ตั้งค่าไว้",
        "ตั้งค่า -- ตั้งจังหวัดที่ต้องการติดตาม",
        "\U0001f5c2 งานของฉัน -- ดูงานที่ติดตามทั้งหมด",
        "",
        "เมื่อได้รับแจ้งเตือน ตอบกลับบอกเราได้เลยครับ:",
        "\U0001f44d สนใจ / \U0001f44e ไม่เกี่ยว / ใหม่ (ไม่เคยเห็น) / โทรแล้ว",
        "(จะนับกับงานที่เพิ่งแจ้งเตือนล่าสุด)",
        "",
        "การแจ้งเตือนจะส่งเมื่อมีโครงการใหม่ในพื้นที่ของคุณครับ",
    ])


# -- Feedback capture (P2, 2026-05-31) ---------------------------------------
# keyword reply → ผูกกับงานล่าสุดที่ส่งให้ user (locked spec: ไม่ใช่ NLP/portal)
# ลำดับสำคัญ: negative/compound ก่อน bare positive — กัน substring ชน
# ("ไม่สนใจ" มี "สนใจ" → ถ้าเช็ค "สนใจ" ก่อนจะกลายเป็น useful ตรงข้ามความหมาย)
FB_KEYWORDS = [
    ("\U0001f44e", "not_relevant"), ("ไม่เกี่ยว", "not_relevant"), ("ไม่สนใจ", "not_relevant"),
    ("\U0001f195", "never_seen"), ("ไม่เคยเห็น", "never_seen"), ("ใหม่", "never_seen"),
    ("\U0001f4de", "action_taken"), ("โทรแล้ว", "action_taken"),
    ("ติดต่อแล้ว", "action_taken"), ("จะติดต่อ", "action_taken"), ("ติดต่อ", "action_taken"),
    ("\U0001f44d", "useful"), ("สนใจ", "useful"), ("useful", "useful"),
]
FB_LABEL = {
    "useful": "\U0001f44d สนใจ", "not_relevant": "\U0001f44e ไม่เกี่ยว",
    "never_seen": "\U0001f195 ไม่เคยเห็น", "action_taken": "\U0001f4de จะติดต่อ",
}


def _match_feedback(text_in: str):
    """คืน action ถ้าข้อความเป็น feedback keyword (ข้อความสั้น กัน false match). ไม่งั้น None"""
    t = (text_in or "").strip()
    if not t or len(t) > 25:   # feedback reply สั้น
        return None
    low = t.lower()
    for kw, action in FB_KEYWORDS:
        if kw in t or kw in low:
            return action
    return None


def _record_feedback(user_id: str, action: str, raw_text: str):
    """บันทึก feedback กับงานล่าสุดที่ส่งให้ user. คืน (project_name, project_id) | None"""
    with get_conn() as conn:
        cust = conn.execute(
            "SELECT id FROM customers WHERE line_user_id=?", (user_id,)
        ).fetchone()
        if not cust:
            return None
        cid = cust["id"]
        last = conn.execute(
            "SELECT project_id FROM delivery_log WHERE customer_id=? AND status='sent' "
            "ORDER BY attempted_at DESC LIMIT 1", (cid,)
        ).fetchone()
        pid = last["project_id"] if last else None
        if not pid:
            return None
        name_row = conn.execute(
            "SELECT project_name FROM projects_seen WHERE project_id=?", (pid,)
        ).fetchone()
        pname = (name_row["project_name"] if name_row else "") or pid
        conn.execute(
            "INSERT INTO feedback (customer_id, project_id, action, raw_text, created_at) "
            "VALUES (?,?,?,?,?)", (cid, pid, action, (raw_text or "")[:200], _now())
        )
    return pname, pid


def _record_feedback_by_project(user_id: str, action: str, project_id: str):
    """บันทึก feedback กับ project_id ที่ระบุตรง (จาก postback). upsert: 1 row/customer/project.
    คืน (project_name, project_id) | None"""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return None
        cid = cust["id"]
        # upsert: ลบ feedback เดิมของ project นี้ก่อน (กดใหม่ทับเก่า)
        conn.execute("DELETE FROM feedback WHERE customer_id=? AND project_id=?", (cid, project_id))
        conn.execute(
            "INSERT INTO feedback (customer_id, project_id, action, raw_text, created_at) "
            "VALUES (?,?,?,?,?)", (cid, project_id, action, "", _now())
        )
        name_row = conn.execute(
            "SELECT project_name FROM projects_seen WHERE project_id=?", (project_id,)
        ).fetchone()
        pname = (name_row["project_name"] if name_row else "") or project_id
    return pname, project_id


def _record_follow(user_id: str, project_id: str):
    """⭐ ติดตามงาน → followed_jobs (upsert, stage จาก projects_seen). คืน (pname, pid) | None."""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return None
        cid = cust["id"]
        row = conn.execute(
            "SELECT announce_type, project_name FROM projects_seen WHERE project_id=?", (project_id,)
        ).fetchone()
        ann = (row["announce_type"] if row else "") or "D0"
        pname = (row["project_name"] if row else "") or project_id
        conn.execute("""
            INSERT INTO followed_jobs
              (customer_id, project_id, starred_at, starred_stage, last_stage_notified, status)
            VALUES (?,?,?,?,?,'active')
            ON CONFLICT(customer_id, project_id) DO UPDATE SET status='active'
        """, (cid, project_id, _now(), ann, ann))
    return pname, project_id


def _record_unfollow(user_id: str, project_id: str):
    """ยกเลิกติดตาม → followed_jobs.status='unfollowed' (แยกจาก system 'closed'). คืน (pname, pid) | None."""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return None
        conn.execute(
            "UPDATE followed_jobs SET status='unfollowed' WHERE customer_id=? AND project_id=?",
            (cust["id"], project_id))
        row = conn.execute(
            "SELECT project_name FROM projects_seen WHERE project_id=?", (project_id,)).fetchone()
        pname = (row["project_name"] if row else "") or project_id
    return pname, project_id


def _follow_status(user_id: str, project_id: str) -> str:
    """'active' (กำลังติดตาม) | 'inactive' (unfollowed/closed/ไม่มี row) | 'no_customer'."""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return "no_customer"
        row = conn.execute(
            "SELECT status FROM followed_jobs WHERE customer_id=? AND project_id=?",
            (cust["id"], project_id)).fetchone()
    return "active" if (row and row["status"] == "active") else "inactive"


def _fmt_exp_th(exp_epoch: int) -> str:
    """epoch → 'D ด. YYYY' (พ.ศ.) สำหรับแสดงวันหมดอายุลิงก์."""
    if not exp_epoch:
        return ""
    dt = datetime.fromtimestamp(exp_epoch, TZ_TH)
    months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    return f"{dt.day} {months[dt.month]} {dt.year + 543}"


def _follow_page_html(token: str, state: str, d: dict, deadline: str, exp_epoch: int) -> str:
    """HTML มือถือ-first. state: 'active' | 'inactive' | 'no_customer' | 'invalid'."""
    import html as _html
    head = (
        "<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>ติดตามงาน</title><style>"
        "body{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:24px;"
        "background:#f5f6f8;color:#222}"
        ".card{max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:24px;"
        "box-shadow:0 2px 12px rgba(0,0,0,.08)}"
        ".h{font-size:18px;font-weight:700;margin:0 0 12px}"
        ".name{font-size:16px;font-weight:600;margin:8px 0}"
        ".meta{font-size:13px;color:#888;margin:4px 0}"
        ".dl{font-size:13px;color:#d9534f;margin:4px 0}"
        "button{width:100%;padding:16px;font-size:17px;font-weight:700;border:0;border-radius:12px;"
        "margin-top:20px;color:#fff}"
        ".follow{background:#1db446}.unfollow{background:#d9534f}"
        ".exp{font-size:11px;color:#bbb;margin-top:18px;text-align:center}"
        ".msg{font-size:15px;color:#555;margin:12px 0}"
        "</style></head><body><div class=\"card\">"
    )
    foot = "</div></body></html>"

    if state == "invalid":
        return head + "<div class=\"h\">ลิงก์ไม่ถูกต้องหรือหมดอายุ</div>" \
            "<div class=\"msg\">ลิงก์ติดตามนี้ใช้ไม่ได้แล้ว กรุณาเปิดจากข้อความแจ้งเตือนล่าสุดครับ</div>" + foot
    if state == "no_customer":
        return head + "<div class=\"h\">ยังไม่ได้เพิ่มเพื่อน</div>" \
            "<div class=\"msg\">กรุณาเพิ่มเพื่อน Sebastian ก่อนติดตามงานครับ</div>" + foot

    name = _html.escape(d.get("project_name", ""))
    info = _html.escape(_detail_info_line(d))
    body = [f"<div class=\"name\">🏗️ {name}</div>", f"<div class=\"meta\">{info}</div>"]
    if deadline:
        body.append(f"<div class=\"dl\">⏰ ยื่นซอง {_html.escape(deadline)}</div>")

    tok = _html.escape(token)
    if state == "active":
        body.insert(0, "<div class=\"h\">✅ งานนี้ติดตามอยู่แล้ว</div>")
        body.append(
            f"<form method=\"post\" action=\"/follow\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"unfollow\">"
            f"<button class=\"unfollow\" type=\"submit\">ยกเลิกการติดตาม</button></form>")
    else:  # inactive
        body.insert(0, "<div class=\"h\">ติดตามงานนี้?</div>")
        body.append(
            f"<form method=\"post\" action=\"/follow\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"follow\">"
            f"<button class=\"follow\" type=\"submit\">⭐ ติดตามงานนี้</button></form>")

    exp_str = _fmt_exp_th(exp_epoch)
    if exp_str:
        body.append(f"<div class=\"exp\">🔗 ลิงก์นี้ใช้ได้ถึง {exp_str} — ข้อมูลที่ติดตามไม่หาย</div>")
    return head + "".join(body) + foot


def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


_TH_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _fmt_date_th(s: str) -> str:
    """'YYYY-MM-DD' → 'D ด. YYYY(พ.ศ.)'. ถ้า parse ไม่ได้ (เช่น ฟอร์แมตไทยอยู่แล้ว) คืนค่าเดิม."""
    if not s:
        return ""
    try:
        d = datetime.fromisoformat(str(s)[:10]).date()
    except (ValueError, TypeError):
        return s
    return f"{d.day} {_TH_MONTHS[d.month]} {d.year + 543}"


def _countdown_th(deadline_str: str) -> str:
    """'YYYY-MM-DD' → ข้อความนับถอยหลังถึงวันยื่นซอง (เทียบวันนี้ tz ไทย). คืน '' ถ้า parse ไม่ได้."""
    if not deadline_str:
        return ""
    try:
        d = datetime.fromisoformat(str(deadline_str)[:10]).date()
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


def _portal_jobs(user_id: str):
    """งานที่ user ติดตาม (active+closed) จัดกลุ่ม stage. คืน {won,bidding,pre} | None (ไม่มี customer).
    won = มีผู้ชนะ (bid_results) หรือ announce W* · bidding = D0 ยังไม่มีผล · pre = อื่น (B*)."""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return None
        cid = cust["id"]
        follows = conn.execute(
            "SELECT project_id, last_stage_notified FROM followed_jobs "
            "WHERE customer_id=? AND status IN ('active','closed')",
            (cid,)).fetchall()
        groups = {"won": [], "prelim": [], "bidding": [], "pre": []}
        for f in follows:
            pid = f["project_id"]
            ps = conn.execute(
                "SELECT project_name, announce_type, province, budget FROM projects_seen WHERE project_id=?",
                (pid,)).fetchone()
            if not ps:
                continue
            try:
                loc = conn.execute(
                    "SELECT moi_name, deadline FROM project_locations WHERE project_id=?", (pid,)).fetchone()
            except sqlite3.OperationalError:
                loc = None
            moi = (loc["moi_name"] if loc and "moi_name" in loc.keys() else "") or ""
            deadline = (loc["deadline"] if loc and "deadline" in loc.keys() else "") or ""
            prov = ps["province"] or ""
            location = ((f"ต.{moi} " if moi else "") + (f"จ.{prov}" if prov else "")).strip()
            budget = ps["budget"] or 0
            pr = conn.execute(
                "SELECT area_price_lo, area_price_hi FROM price_predictions WHERE project_id=?", (pid,)).fetchone()
            results = conn.execute(
                "SELECT bidder_name, price_proposal, price_agree, is_winner, is_sme "
                "FROM bid_results WHERE project_id=?",
                (pid,)).fetchall()
            ann = ps["announce_type"] or ""
            lsn = (f["last_stage_notified"] if "last_stage_notified" in f.keys() else "") or ""
            job = {"project_id": pid, "name": ps["project_name"] or pid, "location": location,
                   "deadline": deadline, "pred_lo": pr["area_price_lo"] if pr else None,
                   "pred_hi": pr["area_price_hi"] if pr else None,
                   "winner": None, "winner_price": None, "winner_disc": None, "competitors": [],
                   "bidders": [], "prelim_low": None, "prelim_n": 0}
            win = next((r for r in results if r["is_winner"]), None)
            if win or ann.startswith("W") or lsn == "W0":
                if win:
                    wp = _to_float(win["price_agree"]) or _to_float(win["price_proposal"])
                    job["winner"] = win["bidder_name"]
                    job["winner_price"] = wp
                    if wp and budget:
                        job["winner_disc"] = round((1 - wp / budget) * 100, 1)
                    seen = set()
                    for r in results:
                        if r["is_winner"] or not r["bidder_name"] or r["bidder_name"] in seen:
                            continue
                        seen.add(r["bidder_name"])
                        job["competitors"].append({"name": r["bidder_name"], "price": _to_float(r["price_proposal"])})
                    job["competitors"] = job["competitors"][:3]
                bidders = [{"name": r["bidder_name"] or "", "price": _to_float(r["price_proposal"]),
                            "is_winner": bool(r["is_winner"]),
                            "is_sme": bool(r["is_sme"] if "is_sme" in r.keys() else 0)}
                           for r in results]
                bidders.sort(key=lambda b: (not b["is_winner"], b["price"] is None, b["price"] or 0))
                job["bidders"] = bidders
                groups["won"].append(job)
            elif lsn == "PRELIM":
                props = [p for p in (_to_float(r["price_proposal"]) for r in results) if p]
                job["prelim_low"] = min(props) if props else None
                job["prelim_n"] = len(props)
                groups["prelim"].append(job)
            elif ann == "D0":
                groups["bidding"].append(job)
            else:
                groups["pre"].append(job)
        return groups


def _portal_page_html(groups: dict, exp_epoch: int = 0, token: str = "") -> str:
    """HTML มือถือ-first — รายการงานติดตามจัดกลุ่ม stage. read-only."""
    import html as _h
    head = (
        "<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>งานที่ติดตาม</title><style>"
        "body{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:18px;background:#f5f6f8;color:#222}"
        ".wrap{max-width:480px;margin:0 auto}"
        ".h{font-size:19px;font-weight:700;margin:4px 0 14px}"
        ".search{width:100%;box-sizing:border-box;padding:11px 14px;font-size:15px;"
        "border:1px solid #ddd;border-radius:12px;margin:0 0 6px;outline:none}"
        ".search:focus{border-color:#1d72b4}"
        ".nohit{font-size:14px;color:#999;margin:14px 0;display:none}"
        ".grp{font-size:14px;font-weight:700;color:#555;margin:16px 0 8px}"
        ".job{background:#fff;border-radius:14px;padding:14px 16px;margin:8px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}"
        ".jn{font-size:15px;font-weight:600;margin:0 0 2px}"
        ".jid{font-size:12px;color:#aaa;margin:0 0 4px}"
        ".meta{font-size:13px;color:#888;margin:3px 0}"
        ".dl{font-size:13px;color:#d9534f;margin:3px 0}"
        ".win{font-size:14px;font-weight:600;color:#1a7f37;margin:3px 0}"
        ".joblink{text-decoration:none;color:inherit;display:block}"
        ".more{font-size:13px;font-weight:600;color:#1d72b4;margin:8px 0 0}"
        ".dots{font-size:12px;color:#999;margin:4px 0}"
        ".badge{font-size:11px;padding:2px 8px;border-radius:10px;color:#fff;margin-left:6px}"
        ".bd{background:#1d72b4}.bw{background:#1a7f37}.bp{background:#7a5cc6}.bs{background:#c2410c}"
        ".cd{font-size:13px;font-weight:600;color:#1d72b4;margin:3px 0}"
        ".msg{font-size:15px;color:#555;margin:12px 0}"
        ".exp{font-size:11px;color:#bbb;margin-top:18px;text-align:center}"
        "</style></head><body><div class=\"wrap\">"
    )
    foot = "</div></body></html>"
    n = sum(len(v) for v in groups.values())
    body = [f"<div class=\"h\">🗂 งานที่คุณติดตาม ({n})</div>"]
    if n == 0:
        body.append("<div class=\"msg\">ยังไม่มีงานที่ติดตาม — กดดาว ⭐ ในข้อความแจ้งเตือนเพื่อเริ่มติดตามครับ</div>")
        return head + "".join(body) + foot

    body.append(
        "<input id=\"q\" class=\"search\" type=\"search\" autocomplete=\"off\" "
        "placeholder=\"🔍 ค้นหางาน (ชื่อ / ID / พื้นที่)\">")
    body.append("<div id=\"nohit\" class=\"nohit\">ไม่พบงานที่ตรงกับคำค้น</div>")

    def _baht(x):
        return f"{x:,.0f}" if x else "-"

    def _card(j, kind):
        L = [f"<div class=\"jn\">🏗️ {_h.escape(j['name'] or '')}</div>",
             f"<div class=\"jid\">🆔 {_h.escape(str(j['project_id']))}</div>"]
        if j["location"]:
            L.append(f"<div class=\"meta\">📍 {_h.escape(j['location'])}</div>")
        if kind == "bidding":
            L.append("<div class=\"dots\">●━━●━━○<span class=\"badge bd\">ประกาศวันยื่นซอง</span></div>")
            if j["deadline"]:
                L.append(f"<div class=\"dl\">⏰ ยื่นซอง {_h.escape(_fmt_date_th(j['deadline']))}</div>")
                cd = _countdown_th(j["deadline"])
                if cd:
                    L.append(f"<div class=\"cd\">⏳ {cd}</div>")
            if j["pred_lo"] and j["pred_hi"]:
                L.append(f"<div class=\"meta\">💵 คาด {_baht(j['pred_lo'])}–{_baht(j['pred_hi'])} บาท</div>")
        elif kind == "prelim":
            L.append("<div class=\"dots\">●━━●━━◐<span class=\"badge bs\">สรุปราคาเบื้องต้น</span></div>")
            if j["prelim_low"]:
                n = f" ({j['prelim_n']} ราย)" if j["prelim_n"] else ""
                L.append(f"<div class=\"win\">💰 ราคาต่ำสุดที่เสนอ {_baht(j['prelim_low'])} บาท{n}</div>")
            else:
                L.append("<div class=\"meta\">💰 เปิดเผยราคาเบื้องต้นแล้ว — รอประกาศผู้ชนะทางการ</div>")
        elif kind == "won":
            L.append("<div class=\"dots\">●━━●━━●<span class=\"badge bw\">ประกาศผู้ชนะทางการ</span></div>")
            if j["winner"]:
                disc = f" (ลด {j['winner_disc']:.0f}%)" if j["winner_disc"] is not None else ""
                L.append(f"<div class=\"win\">🏆 {_h.escape(j['winner'])} · {_baht(j['winner_price'])}{disc}</div>")
            L.append("<div class=\"more\">ดูผู้ยื่นทั้งหมด →</div>")
        else:
            L.append("<div class=\"dots\">●━━○━━○<span class=\"badge bp\">รับฟังคำประชาวิจารณ์</span></div>")
        if kind != "won":
            L.append("<div class=\"more\">ดูรายละเอียด →</div>")
        href = f"/portal/job?t={_h.escape(token)}&pid={_h.escape(str(j['project_id']))}"
        return f"<a class=\"job joblink\" href=\"{href}\">" + "".join(L) + "</a>"

    for key, label in (("bidding", "🔵 ประกาศวันยื่นซอง"), ("prelim", "📊 สรุปราคาเบื้องต้น"),
                       ("pre", "🟣 รับฟังคำประชาวิจารณ์"), ("won", "🏆 ประกาศผู้ชนะทางการ")):
        if groups.get(key):
            cards = "".join(_card(j, key) for j in groups[key])
            body.append(f"<div class=\"gw\"><div class=\"grp\">{label} ({len(groups[key])})</div>{cards}</div>")
    exp_str = _fmt_exp_th(exp_epoch)
    if exp_str:
        body.append(f"<div class=\"exp\">🔗 ลิงก์นี้ใช้ได้ถึง {exp_str}</div>")
    body.append(
        "<script>(function(){"
        "var q=document.getElementById('q'),nh=document.getElementById('nohit');"
        "if(q){q.addEventListener('input',function(){"
        "var s=q.value.trim().toLowerCase(),tot=0;"
        "document.querySelectorAll('.gw').forEach(function(g){var v=0;"
        "g.querySelectorAll('.job').forEach(function(c){"
        "var on=!s||c.textContent.toLowerCase().indexOf(s)>=0;"
        "c.style.display=on?'':'none';if(on)v++;});"
        "g.style.display=v?'':'none';tot+=v;});"
        "if(nh)nh.style.display=tot?'none':'block';});}})();</script>")
    return head + "".join(body) + foot


def _portal_link(user_id: str) -> str:
    """ลิงก์ portal ต่อ user (portal token p=None)."""
    return PUBLIC_BASE_URL.rstrip("/") + "/portal?t=" + follow_token.make_token(user_id, None)


# -- Feedback flex (postback): ตอบกลับรายละเอียดงาน + ปุ่มแก้ไข -----------------
FB_FULL_LABEL = {
    "interested":   "\U0001f44d สนใจ/น่าติดตาม",
    "relevant_low": "\U0001f914 เกี่ยวข้องแต่ไม่น่าสนใจ",
    "irrelevant":   "\U0001f44e ไม่เกี่ยวข้องเลย",
}


def _fmt_budget_th(budget) -> str:
    if not budget:
        return "ไม่ระบุ"
    if budget >= 1_000_000:
        return f"{budget / 1_000_000:.1f} ล้านบาท"
    return f"{int(budget):,} บาท"


def _project_detail(project_id: str) -> dict:
    """ดึงรายละเอียดงานจาก projects_seen สำหรับแสดงตอนตอบ feedback"""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT project_name, budget, dept_name, province "
                "FROM projects_seen WHERE project_id=?", (project_id,)
            ).fetchone()
    except Exception:
        row = None
    if not row:
        return {"project_name": project_id, "budget": 0, "dept_name": "", "province": ""}
    return {
        "project_name": row["project_name"] or project_id,
        "budget": row["budget"] or 0,
        "dept_name": row["dept_name"] or "",
        "province": row["province"] or "",
    }


def _detail_info_line(d: dict) -> str:
    parts = []
    if d.get("province"):
        parts.append("\U0001f4cd " + d["province"])
    parts.append("\U0001f4b0 " + _fmt_budget_th(d.get("budget")))
    if d.get("dept_name"):
        parts.append("\U0001f3e2 " + d["dept_name"])
    return "  ".join(parts)


def _follow_deadline(project_id: str) -> str:
    """อ่าน deadline ที่ resolve ไว้ (project_locations) — แสดงในการ์ดยืนยันถ้ามี. คืน '' ถ้าไม่มี."""
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT deadline FROM project_locations WHERE project_id=?",
                               (project_id,)).fetchone()
        dl = (row["deadline"] if row else "") or ""
        return dl[:16].replace("T", " ") if dl else ""
    except Exception:
        return ""


def _follow_confirm_flex(project_id: str, d: dict, deadline: str = "") -> dict:
    """bubble: ⭐ ติดตามงานนี้แล้ว + รายละเอียดงานที่ติดตาม + (deadline ถ้ามี) + สิ่งที่จะแจ้งต่อ."""
    body = [
        {"type": "text", "text": "⭐ ติดตามงานนี้แล้ว",
         "weight": "bold", "size": "md", "color": "#1DB446"},
        {"type": "separator", "margin": "md"},
        {"type": "text", "text": "\U0001f3d7️ " + d.get("project_name", project_id)[:300],
         "size": "sm", "margin": "md", "wrap": True, "weight": "bold"},
        {"type": "text", "text": _detail_info_line(d),
         "size": "xs", "color": "#888888", "margin": "sm", "wrap": True},
    ]
    if deadline:
        body.append({"type": "text", "text": "⏰ ยื่นซอง " + deadline,
                     "size": "xs", "color": "#D9534F", "margin": "sm", "wrap": True})
    body.append({"type": "separator", "margin": "md"})
    body.append({"type": "text", "text": "\U0001f514 จะแจ้งให้เมื่อ:\n  • งานเปิดประมูล\n  • ประกาศผู้ชนะ",
                 "size": "xs", "color": "#555555", "margin": "md", "wrap": True})
    body.append({"type": "text", "text": "\U0001f511 " + project_id,
                 "size": "xxs", "color": "#aaaaaa", "margin": "md"})
    return {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": body}}


def _confirm_flex(action: str, project_id: str, d: dict) -> dict:
    """bubble: ✅ บันทึกแล้ว + label + รายละเอียดงาน + ปุ่ม ✏️ แก้ไข feedback"""
    label = FB_FULL_LABEL.get(action, "")
    return {
        "type": "bubble",
        "body": {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": "✅ บันทึก feedback แล้ว",
             "weight": "bold", "size": "md", "color": "#1DB446"},
            {"type": "text", "text": label, "size": "sm", "margin": "sm", "wrap": True},
            {"type": "separator", "margin": "md"},
            {"type": "text", "text": "\U0001f3d7️ " + d.get("project_name", project_id)[:300],
             "size": "sm", "margin": "md", "wrap": True, "weight": "bold"},
            {"type": "text", "text": _detail_info_line(d),
             "size": "xs", "color": "#888888", "margin": "sm", "wrap": True},
        ]},
        "footer": {"type": "box", "layout": "vertical", "contents": [
            {"type": "button", "style": "secondary", "height": "sm",
             "action": {"type": "postback", "label": "✏️ แก้ไข feedback",
                        "data": "fbedit:" + project_id, "displayText": "แก้ไข feedback"}},
        ]},
    }


def _choose_flex(project_id: str, d: dict) -> dict:
    """bubble: เลือก feedback ใหม่ (3 ปุ่ม fb:action:project)"""
    footer_btns = []
    for act, label in FB_FULL_LABEL.items():
        footer_btns.append({
            "type": "button", "style": "secondary", "height": "sm",
            "action": {"type": "postback", "label": label,
                       "data": f"fb:{act}:{project_id}", "displayText": label},
        })
    return {
        "type": "bubble",
        "body": {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": "เลือก feedback ใหม่สำหรับงานนี้",
             "weight": "bold", "size": "sm", "wrap": True},
            {"type": "text", "text": "\U0001f3d7️ " + d.get("project_name", project_id)[:300],
             "size": "xs", "color": "#888888", "margin": "sm", "wrap": True},
        ]},
        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": footer_btns},
    }


def _save_provinces(user_id: str, provinces: list[str]) -> None:
    """Upsert provinces for existing customer (replaces all existing subscription_provinces)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM customers WHERE line_user_id=? AND active=1", (user_id,)
        ).fetchone()
        if not row:
            return
        cid = row["id"]
        sub = conn.execute(
            "SELECT id FROM subscriptions WHERE customer_id=? AND active=1", (cid,)
        ).fetchone()
        if not sub:
            conn.execute(
                "INSERT INTO subscriptions (customer_id, announce_types, min_budget, active, created_at) "
                "VALUES (?,?,?,1,?)", (cid, "D0", 0, datetime.now(TZ_TH).isoformat(timespec="seconds"))
            )
            sub = conn.execute(
                "SELECT id FROM subscriptions WHERE customer_id=? AND active=1", (cid,)
            ).fetchone()
        sid = sub["id"]
        conn.execute("DELETE FROM subscription_provinces WHERE subscription_id=?", (sid,))
        for province in provinces:
            conn.execute(
                "INSERT INTO subscription_provinces (subscription_id, province) VALUES (?,?)",
                (sid, province),
            )


def _status_text(display_name: str, provinces: list, tier: str) -> str:
    if provinces:
        prov_lines = "\n".join("• " + p for p in provinces)
        prov_block = "ติดตามจังหวัด:\n" + prov_lines
    else:
        prov_block = "ยังไม่ได้ตั้งค่าจังหวัดครับ"
    return "\n".join([
        "\U0001f4cb สถานะของคุณ" + display_name,
        "",
        prov_block,
        "",
        'พิมพ์ "ตั้งค่า" เพื่อเปลี่ยนจังหวัดที่ต้องการติดตาม',
    ])


def _get_customer_status(user_id: str):
    """Return (display_name, provinces, tier) or None if not found."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT c.id, c.display_name, c.tier "
            "FROM customers c WHERE c.line_user_id=? AND c.active=1",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        sub = conn.execute(
            "SELECT id FROM subscriptions WHERE customer_id=? AND active=1",
            (row["id"],),
        ).fetchone()
        provinces = []
        if sub:
            rows = conn.execute(
                "SELECT province FROM subscription_provinces WHERE subscription_id=?",
                (sub["id"],),
            ).fetchall()
            provinces = [r["province"] for r in rows]
        return row["display_name"] or "ลูกค้า", provinces, row["tier"]


# -- LINE signature verification ----------------------------------------------

def verify_line_signature(body: bytes, signature) -> bool:
    if not signature or not LINE_CHANNEL_SECRET:
        return False
    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


# -- Endpoints ----------------------------------------------------------------

@app.get("/health")
async def health():
    return {"ok": True, "db": DB_PATH.exists(), "ts": _now()}


# -- Price prediction audit (internal, shared-secret) -------------------------
def _check_audit_key(key: str):
    expected = os.getenv("BMS_AUDIT_KEY", "")
    if not expected or key != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


_STAGE = {"B0": "🟣 รับฟังคำวิจารณ์", "D0": "🔵 ประกาศ/ยื่นซอง",
          "PRELIM": "🟡 ราคาเบื้องต้น", "W0": "🟢 ประกาศผู้ชนะ"}
_STAGE_RANK = {"B0": 1, "D0": 2, "PRELIM": 3, "W0": 4}
_WORK_KIND = {"new": "สร้างใหม่", "reno": "ปรับปรุง/ซ่อม"}
_MARKET = {"local": "ท้องถิ่น (อปท.)", "provincial": "อบจ.", "central": "ส่วนกลาง (กรม)"}
_SUBTYPE = {"concrete_road": "ถนนคอนกรีต", "asphalt_road": "ถนนแอสฟัลต์",
            "water_dredge": "ขุดลอก", "water_structure": "ฝาย/โครงสร้างน้ำ"}


def _stage_label(s): return _STAGE.get(s or "", s or "—")
def _work_kind_label(s): return _WORK_KIND.get(s or "", "—")
def _market_label(s): return _MARKET.get(s or "", "—")
def _subtype_label(s): return _SUBTYPE.get(s or "", "—")


def _most_advanced_stage(stages: list) -> str:
    best, best_rank = "", 0
    for s in stages:
        r = _STAGE_RANK.get(s or "", 0)
        if r > best_rank:
            best, best_rank = s, r
    return best


def _audit_list_html(rows: list, key: str) -> str:
    trs = ""
    for r in rows:
        lo, hi = r.get("area_price_lo") or 0, r.get("area_price_hi") or 0
        if r.get("actual_price") is None:
            stat = "⏳ รอผล"
        else:
            stat = ("✅ ในกรอบ" if r.get("in_range") else "❌ หลุด") + f" ({r.get('error_pct')}%)"
        name = r.get("project_name") or "(ไม่มีชื่อ)"
        trs += (f"<tr><td><a href='/audit/{r['project_id']}?key={key}'>{name}</a>"
                f"<br><small>{r['project_id']}</small></td>"
                f"<td>{_stage_label(r.get('stage'))}</td>"
                f"<td>{lo:,}–{hi:,}</td><td>{stat}</td></tr>")
    return ("<html><head><meta charset='utf-8'><title>Audit ราคา</title>"
            "<style>body{font-family:sans-serif;padding:16px}table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:6px}small{color:#888}</style></head><body>"
            "<h2>การทำนายราคา (ล่าสุด 200)</h2><table>"
            "<tr><th>งาน</th><th>สถานะ</th><th>ช่วงราคาคาด</th><th>ผลจริง(ทางการ)</th></tr>"
            f"{trs}</table></body></html>")


@app.get("/audit")
async def audit_list(key: str = ""):
    _check_audit_key(key)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        preds = conn.execute(
            "SELECT pp.project_id, pp.area_price_lo, pp.area_price_hi, pp.predicted_at, "
            "pp.actual_price, pp.in_range, pp.error_pct, ps.project_name "
            "FROM price_predictions pp LEFT JOIN projects_seen ps ON ps.project_id=pp.project_id "
            "ORDER BY pp.predicted_at DESC LIMIT 200").fetchall()
        rows = [dict(r) for r in preds]
        for r in rows:
            stages = [x[0] for x in conn.execute(
                "SELECT last_stage_notified FROM followed_jobs WHERE project_id=?",
                (r["project_id"],)).fetchall()]
            r["stage"] = _most_advanced_stage([s for s in stages if s])
    return HTMLResponse(_audit_list_html(rows, key))


def _audit_detail_html(r: dict) -> str:
    ex = json.loads(r["explain_json"]) if r.get("explain_json") else None
    cat = ""
    if ex:
        cls, inp = ex.get("classify", {}), ex.get("inputs", {})
        cat = (f"<h3>หมวดงาน</h3><ul>"
               f"<li>หมวดงาน: {inp.get('work_type') or '—'}</li>"
               f"<li>หมวดย่อย: {_subtype_label(cls.get('subtype'))}</li>"
               f"<li>ประเภท: {_work_kind_label(cls.get('work_kind'))}</li>"
               f"<li>ระบอบตลาด: {_market_label(cls.get('market'))}</li></ul>")
    if not ex:
        body = "<p>ไม่มีข้อมูล explain (การทำนายเก่าก่อนเปิดฟีเจอร์)</p>"
    else:
        sc, an = ex.get("scope", {}), ex.get("analysis", {})
        recs = "".join(
            f"<tr><td>{x.get('project_name','')}</td><td>{x.get('winner','')}</td>"
            f"<td>{(x.get('win_price') or 0):,}</td><td>{x.get('discount','')}</td></tr>"
            for x in ex.get("raw_records", []))
        body = (f"<h3>วิธีคิด</h3><ul>"
                f"<li>scope: {sc.get('level')} (n={sc.get('n')})</li>"
                f"<li>ส่วนลดกลาง: {an.get('disc_med')} · คู่แข่ง top: {an.get('top_name')}</li>"
                f"<li>{ex.get('formula','')}</li></ul>"
                f"<h3>ข้อมูลดิบอ้างอิง ({len(ex.get('raw_records', []))} งาน)</h3>"
                f"<table><tr><th>งาน</th><th>ผู้ชนะ</th><th>ราคาชนะ</th><th>%ลด</th></tr>"
                f"{recs}</table>")
    if r.get("prelim_price") is not None:
        pl = (f"<h3>🟡 ราคาเบื้องต้น (ยังไม่ทางการ)</h3>"
              f"<p>เบื้องต้น {r['prelim_price']:,} · คาด {r.get('area_price_med') or '-'} · "
              f"ต่าง {r.get('prelim_error_pct')}% · "
              f"{'✅ ในกรอบ' if r.get('prelim_in_range') else '❌ หลุด'} <i>(ยังไม่ทางการ)</i></p>")
    else:
        pl = ""
    if r.get("actual_price") is not None:
        cl = (f"<h3>🟢 คาด vs จริง (ทางการ W0)</h3><p>คาด {r.get('area_price_med') or '-'} · "
              f"จริง {r['actual_price']:,} · error {r.get('error_pct')}% · "
              f"{'✅ ในกรอบ' if r.get('in_range') else '❌ หลุด'}</p>")
    else:
        cl = "<h3>🟢 คาด vs จริง (ทางการ W0)</h3><p>⏳ รอผลประมูล</p>"
    lo, hi = r.get("area_price_lo") or 0, r.get("area_price_hi") or 0
    name = r.get("project_name") or r["project_id"]
    return ("<html><head><meta charset='utf-8'>"
            f"<title>{r['project_id']}</title>"
            "<style>body{font-family:sans-serif;padding:16px}table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:6px}small{color:#888}</style></head><body>"
            f"<p><a href='/audit?key={r.get('_key','')}'>← กลับ</a></p>"
            f"<h2>{name}</h2><p><small>{r['project_id']}</small> — ช่วงราคา {lo:,}–{hi:,}</p>"
            f"{cat}{body}{pl}{cl}</body></html>")


@app.get("/audit/{project_id}")
async def audit_detail(project_id: str, key: str = ""):
    _check_audit_key(key)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT pp.*, ps.project_name FROM price_predictions pp "
            "LEFT JOIN projects_seen ps ON ps.project_id=pp.project_id "
            "WHERE pp.project_id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    d = dict(row)
    d["_key"] = key
    return HTMLResponse(_audit_detail_html(d))


@app.get("/follow")
async def follow_get(t: str = ""):
    v = follow_token.verify_token(t)
    if not v or not v[1]:           # invalid/expired หรือ portal token (ไม่มี project_id)
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", v[2] if v else 0))
    user_id, project_id, exp = v
    state = _follow_status(user_id, project_id)
    if state == "no_customer":
        return HTMLResponse(_follow_page_html(t, "no_customer", {}, "", exp))
    d = _project_detail(project_id)
    return HTMLResponse(_follow_page_html(t, state, d, _follow_deadline(project_id), exp))


@app.post("/follow")
async def follow_post(request: Request):
    from urllib.parse import parse_qs
    form = parse_qs((await request.body()).decode("utf-8"))
    t = (form.get("t") or [""])[0]
    action = (form.get("action") or [""])[0]
    v = follow_token.verify_token(t)
    if not v or not v[1]:
        raise HTTPException(status_code=400, detail="invalid token")
    user_id, project_id, exp = v
    if action == "follow":
        _record_follow(user_id, project_id)
    elif action == "unfollow":
        _record_unfollow(user_id, project_id)
    state = _follow_status(user_id, project_id)
    if state == "no_customer":
        return HTMLResponse(_follow_page_html(t, "no_customer", {}, "", exp))
    d = _project_detail(project_id)
    return HTMLResponse(_follow_page_html(t, state, d, _follow_deadline(project_id), exp))


@app.get("/portal")
async def portal_get(t: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    jobs = _portal_jobs(v[0])
    if jobs is None:
        return HTMLResponse(_follow_page_html(t, "no_customer", {}, "", v[2]))
    return HTMLResponse(_portal_page_html(jobs, v[2], t))


@app.get("/portal/job")
async def portal_job_get(t: str = "", pid: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        cid = cust["id"] if cust else None
        data = portal_views.job_detail(conn, pid)
        notes = portal_views.list_job_notes(conn, cid, pid) if cid else []
        overview = portal_views.get_job_overview(conn, cid, pid) if cid else ""
    return HTMLResponse(portal_views.render_job_page(data, t, v[2], notes, overview))


@app.get("/portal/company")
async def portal_company_get(t: str = "", tin: str = "", from_: str = Query("", alias="from")):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        data = portal_views.company_profile(conn, tin)
    return HTMLResponse(portal_views.render_company_page(data, t, from_, v[2]))


@app.post("/portal/job/note")
async def portal_job_note_post(request: Request):
    from urllib.parse import parse_qs, quote
    form = parse_qs((await request.body()).decode("utf-8"))
    g = lambda k: (form.get(k) or [""])[0]
    t = g("t")
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    pid, action = g("pid"), g("action")
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        cid = cust["id"] if cust else None
        if cid:
            if action == "add":
                portal_views.add_job_note(conn, cid, pid, g("entry_date"), g("note"))
            elif action == "edit":
                portal_views.edit_job_note(conn, cid, g("note_id"), g("entry_date"), g("note"))
            elif action == "delete":
                portal_views.delete_job_note(conn, cid, g("note_id"))
            elif action == "save_overview":
                portal_views.save_job_overview(conn, cid, pid, g("note"))
    return RedirectResponse(f"/portal/job?t={quote(t)}&pid={quote(pid)}", status_code=303)


@app.post("/webhook/line")
async def line_webhook(
    request: Request,
    x_line_signature=Header(default=None),
):
    body = await request.body()

    if not verify_line_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="Invalid LINE signature")

    payload = json.loads(body)
    events  = payload.get("events", [])

    for event in events:
        user_id = (event.get("source") or {}).get("userId")
        if not user_id:
            continue

        now = _now()

        if event.get("type") == "follow":
            display_name, _ = await fetch_line_profile(user_id)

            with get_conn() as conn:
                existing = conn.execute(
                    "SELECT id, active FROM customers WHERE line_user_id=?",
                    (user_id,),
                ).fetchone()

                if existing:
                    conn.execute(
                        "UPDATE customers SET active=1, display_name=?, updated_at=? "
                        "WHERE line_user_id=?",
                        (display_name, now, user_id),
                    )
                    customer_id = existing["id"]
                    is_new = False
                else:
                    cur = conn.execute(
                        "INSERT INTO customers "
                        "(line_user_id, display_name, tier, active, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (user_id, display_name, "trial", 1, now, now),
                    )
                    customer_id = cur.lastrowid
                    is_new = True

                has_sub = conn.execute(
                    "SELECT id FROM subscriptions WHERE customer_id=? AND active=1",
                    (customer_id,),
                ).fetchone()
                if not has_sub:
                    conn.execute(
                        "INSERT INTO subscriptions "
                        "(customer_id, announce_types, min_budget, delivery_mode, active, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (customer_id, "D0", 0, "instant", 1, now, now),
                    )

            if is_new:
                await push_message(user_id, _welcome_text(display_name))

        elif event.get("type") == "unfollow":
            with get_conn() as conn:
                conn.execute(
                    "UPDATE customers SET active=0, updated_at=? WHERE line_user_id=?",
                    (now, user_id),
                )

        elif event.get("type") == "message":
            reply_token = event.get("replyToken")
            if not reply_token:
                continue
            text_in = ((event.get("message") or {}).get("text") or "").strip()
            text_lower = text_in.lower()

            # --- state: waiting_province ---
            if _conv_state.get(user_id) == "waiting_province":
                _conv_state.pop(user_id, None)
                provinces = [p.strip() for p in text_in.replace("，", ",").split(",") if p.strip()]
                if provinces:
                    _save_provinces(user_id, provinces)
                    prov_str = ", ".join(provinces)
                    await reply_message(
                        reply_token,
                        f"✅ บันทึกจังหวัด \"{prov_str}\" แล้วครับ\n\nพิมพ์ สถานะ เพื่อตรวจสอบ",
                    )
                else:
                    await reply_message(reply_token, "ไม่พบชื่อจังหวัด กรุณาลองใหม่ครับ")
                continue

            # --- feedback (P2): 👍/👎/ใหม่/โทรแล้ว → งานล่าสุดที่ส่งให้ ---
            fb_action = _match_feedback(text_in)
            if fb_action:
                res = _record_feedback(user_id, fb_action, text_in)
                if res:
                    short = res[0][:40]
                    if fb_action == "never_seen":
                        msg = ("\U0001f195 รับทราบครับ! บันทึกว่า \"" + short +
                               "\" เป็นงานที่ไม่เคยเห็นมาก่อน \U0001f64f ข้อมูลนี้มีค่ามากสำหรับเรา")
                    else:
                        msg = ("✅ บันทึก " + FB_LABEL[fb_action] + " สำหรับ \"" + short +
                               "\" แล้วครับ ขอบคุณที่ช่วยให้ Sebastian ฉลาดขึ้น \U0001f64f")
                    await reply_message(reply_token, msg)
                else:
                    await reply_message(
                        reply_token,
                        "ยังไม่มีงานที่ส่งให้ล่าสุดครับ — feedback จะนับกับงานที่เพิ่งแจ้งเตือน",
                    )
                continue

            # --- normal commands ---
            if text_lower in ("ช่วย", "help", "?", "คำสั่ง"):
                await reply_message(reply_token, _help_text())

            elif text_lower in ("สถานะ", "status"):
                info = _get_customer_status(user_id)
                if info:
                    name, provinces, tier = info
                    await reply_message(reply_token, _status_text(name, provinces, tier))
                else:
                    await reply_message(
                        reply_token,
                        "ยังไม่ได้ลงทะเบียนครับ กรุณา follow บัญชีนี้ใหม่อีกครั้ง",
                    )

            elif text_lower in ("ตั้งค่า", "ตั้งค่าจังหวัด", "set", "province"):
                _conv_state[user_id] = "waiting_province"
                await reply_message(
                    reply_token,
                    "\U0001f4cd กรุณาพิมพ์จังหวัดที่ต้องการติดตามครับ\n\nถ้าหลายจังหวัด คั่นด้วยจุลภาค\nเช่น: นครพนม, บึงกาฬ",
                )

            elif text_lower in ("งานของฉัน", "งานที่ติดตาม", "portal", "พอร์ทัล", "ติดตาม"):
                await reply_message(reply_token, "🗂 ดูงานที่ติดตามทั้งหมด:\n" + _portal_link(user_id))

            else:
                await reply_message(
                    reply_token,
                    "พิมพ์ ช่วย เพื่อดูคำสั่งที่ใช้ได้ครับ \U0001f916",
                )

        elif event.get("type") == "postback":
            reply_token = event.get("replyToken")
            data = ((event.get("postback") or {}).get("data") or "")

            # กด "แก้ไข feedback" → ส่งการ์ด 3 ปุ่มเลือกใหม่: fbedit:<project_id>
            if data.startswith("fbedit:"):
                project_id = data.split(":", 1)[1]
                if project_id and reply_token:
                    d = _project_detail(project_id)
                    await reply_raw(reply_token, [{
                        "type": "flex", "altText": "แก้ไข feedback",
                        "contents": _choose_flex(project_id, d),
                    }])
                continue

            # ⭐ ติดตามงาน: star:<project_id>
            if data.startswith("star:"):
                project_id = data.split(":", 1)[1]
                if project_id:
                    _record_follow(user_id, project_id)
                    if reply_token:
                        d = _project_detail(project_id)
                        await reply_raw(reply_token, [{
                            "type": "flex", "altText": "⭐ ติดตามงานนี้แล้ว",
                            "contents": _follow_confirm_flex(project_id, d, _follow_deadline(project_id)),
                        }])
                continue

            # เลือก feedback: fb:<action>:<project_id>
            if data.startswith("fb:"):
                parts = data.split(":", 2)
                if len(parts) == 3 and parts[1] in ("interested", "relevant_low", "irrelevant") and parts[2]:
                    action, project_id = parts[1], parts[2]
                    _record_feedback_by_project(user_id, action, project_id)
                    if reply_token:
                        d = _project_detail(project_id)
                        await reply_raw(reply_token, [{
                            "type": "flex", "altText": "บันทึก feedback แล้ว",
                            "contents": _confirm_flex(action, project_id, d),
                        }])
                continue

    return {"ok": True}


@app.post("/api/preferences")
async def update_preferences(
    request: Request,
    x_bms_secret=Header(default=None),
):
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    payload     = await request.json()
    customer_id = payload.get("customer_id")
    provinces   = payload.get("provinces", [])
    keywords    = payload.get("keywords", "")

    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id required")

    now = _now()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM customers WHERE id=? AND active=1", (customer_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Customer not found")

        sub = conn.execute(
            "SELECT id FROM subscriptions WHERE customer_id=? AND active=1",
            (customer_id,),
        ).fetchone()

        if not sub:
            cur = conn.execute(
                "INSERT INTO subscriptions "
                "(customer_id, announce_types, min_budget, delivery_mode, active, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (customer_id, "D0", 0, "instant", 1, now, now),
            )
            sub_id = cur.lastrowid
        else:
            sub_id = sub["id"]
            conn.execute("UPDATE subscriptions SET updated_at=? WHERE id=?", (now, sub_id))

        conn.execute(
            "DELETE FROM subscription_provinces WHERE subscription_id=?", (sub_id,)
        )
        for province in provinces:
            conn.execute(
                "INSERT INTO subscription_provinces (subscription_id, province) VALUES (?,?)",
                (sub_id, province.strip()),
            )

        if keywords is not None:
            conn.execute(
                "UPDATE subscriptions SET work_categories=?, updated_at=? WHERE id=?",
                (keywords, now, sub_id),
            )

    return {"ok": True, "sub_id": sub_id, "provinces": provinces}
