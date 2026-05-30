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
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Header, HTTPException

# -- Config -------------------------------------------------------------------

DB_PATH              = Path("/opt/bms/data/bms_customers.db")
LINE_CHANNEL_SECRET  = os.getenv("SEBASTIAN_LINE_SECRET", "")
LINE_ACCESS_TOKEN    = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
BMS_INTERNAL_SECRET  = os.getenv("BMS_INTERNAL_SECRET", "")
TZ_TH = timezone(timedelta(hours=7))

LINE_API = "https://api.line.me/v2/bot"

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

            else:
                await reply_message(
                    reply_token,
                    "พิมพ์ ช่วย เพื่อดูคำสั่งที่ใช้ได้ครับ \U0001f916",
                )

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
