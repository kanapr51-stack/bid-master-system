"""
bms_api.py — FastAPI bridge for BMS VPS
Receives webhooks from Vercel LINE handler + preferences from portal.

Endpoints:
  GET  /health                  — liveness check
  POST /webhook/line            — LINE follow/unfollow events (LINE signature verified)
  POST /api/preferences         — province preferences from portal (X-BMS-Secret verified)
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

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH              = Path("/opt/bms/data/bms_customers.db")
LINE_CHANNEL_SECRET  = os.getenv("SEBASTIAN_LINE_SECRET", "")
LINE_ACCESS_TOKEN    = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
BMS_INTERNAL_SECRET  = os.getenv("BMS_INTERNAL_SECRET", "")
TZ_TH = timezone(timedelta(hours=7))

LINE_API = "https://api.line.me/v2/bot"

app = FastAPI(title="BMS API Bridge", version="1.1")


def _now() -> str:
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── LINE helpers ──────────────────────────────────────────────────────────────

def _line_headers() -> dict:
    return {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}


async def fetch_line_profile(user_id: str) -> tuple[str, str | None]:
    """Return (display_name, picture_url). Falls back to 'LINE User' on error."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{LINE_API}/profile/{user_id}",
                headers=_line_headers(),
            )
        if r.status_code == 200:
            data = r.json()
            return data.get("displayName", "LINE User"), data.get("pictureUrl")
    except Exception:
        pass
    return "LINE User", None


async def push_welcome(user_id: str, display_name: str) -> None:
    """Send welcome message after new LINE follow."""
    text = (
        f"สวัสดีครับ คุณ{display_name} \U0001f44b\n\n"
        "ผม Sebastian ผู้ช่วยติดตามงานประมูลภาครัฐ\n\n"
        "เมื่อมีโครงการใหม่ในพื้นที่ที่คุณสนใจ ผมจะแจ้งเตือนทันทีครับ\n\n"
        "ทีมงานจะติดต่อเพื่อตั้งค่าพื้นที่ให้คุณเร็วๆ นี้ครับ \U0001f64f"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{LINE_API}/message/push",
                headers={**_line_headers(), "Content-Type": "application/json"},
                json={"to": user_id, "messages": [{"type": "text", "text": text}]},
            )
    except Exception:
        pass  # non-fatal — customer already created in DB


# ── LINE signature verification ───────────────────────────────────────────────

def verify_line_signature(body: bytes, signature: str | None) -> bool:
    if not signature or not LINE_CHANNEL_SECRET:
        return False
    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True, "db": DB_PATH.exists(), "ts": _now()}


@app.post("/webhook/line")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None),
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
                    # Re-follow: reactivate + refresh display_name
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

                # Ensure subscription row exists (no provinces yet — admin sets via /api/preferences)
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
                await push_welcome(user_id, display_name)

        elif event.get("type") == "unfollow":
            with get_conn() as conn:
                conn.execute(
                    "UPDATE customers SET active=0, updated_at=? WHERE line_user_id=?",
                    (now, user_id),
                )

    return {"ok": True}


@app.post("/api/preferences")
async def update_preferences(
    request: Request,
    x_bms_secret: str | None = Header(default=None),
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
