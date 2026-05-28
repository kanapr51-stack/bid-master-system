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

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH             = Path("/opt/bms/data/bms_customers.db")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
BMS_INTERNAL_SECRET = os.getenv("BMS_INTERNAL_SECRET", "")
TZ_TH = timezone(timedelta(hours=7))

app = FastAPI(title="BMS API Bridge", version="1.0")


def _now() -> str:
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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
    db_ok = DB_PATH.exists()
    return {"ok": True, "db": db_ok, "ts": _now()}


@app.post("/webhook/line")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None),
):
    body = await request.body()

    if not verify_line_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="Invalid LINE signature")

    payload = json.loads(body)   # parse from bytes — not re-reading stream
    events  = payload.get("events", [])

    with get_conn() as conn:
        for event in events:
            user_id = (event.get("source") or {}).get("userId")
            if not user_id:
                continue

            now = _now()
            if event.get("type") == "follow":
                conn.execute(
                    "INSERT OR IGNORE INTO customers "
                    "(line_user_id, display_name, tier, active, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (user_id, "LINE User", "trial", 1, now, now),
                )
            elif event.get("type") == "unfollow":
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

    payload    = await request.json()
    customer_id = payload.get("customer_id")
    provinces  = payload.get("provinces", [])
    keywords   = payload.get("keywords", "")

    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id required")

    now = _now()
    with get_conn() as conn:
        # Verify customer exists
        row = conn.execute(
            "SELECT id FROM customers WHERE id=? AND active=1", (customer_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Upsert subscription (one per customer for now)
        sub = conn.execute(
            "SELECT id FROM subscriptions WHERE customer_id=? AND active=1",
            (customer_id,)
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
            conn.execute(
                "UPDATE subscriptions SET updated_at=? WHERE id=?", (now, sub_id)
            )

        # Replace provinces (normalized join table)
        conn.execute(
            "DELETE FROM subscription_provinces WHERE subscription_id=?", (sub_id,)
        )
        for province in provinces:
            conn.execute(
                "INSERT INTO subscription_provinces (subscription_id, province) VALUES (?,?)",
                (sub_id, province.strip()),
            )

        # Keywords stored in subscriptions.work_categories for now
        if keywords is not None:
            conn.execute(
                "UPDATE subscriptions SET work_categories=?, updated_at=? WHERE id=?",
                (keywords, now, sub_id),
            )

    return {"ok": True, "sub_id": sub_id, "provinces": provinces}
