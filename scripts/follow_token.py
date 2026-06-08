"""follow_token.py — stateless signed token สำหรับ follow-link (HMAC, ไม่เก็บ DB).

payload = {"u": user_id, "p": project_id|None, "e": exp_epoch}
token   = base64url(json(payload)) + "." + base64url(hmac_sha256(secret, payload_b64))

p=None  → portal-level token (Phase 2). follow-link ส่ง project_id เสมอ.
secret  = env BMS_FOLLOW_SECRET (sender มินต์ + bms_api verify แชร์ secret เดียวกัน).
"""
import base64
import hashlib
import hmac
import json
import os
import time

_SECRET = os.getenv("BMS_FOLLOW_SECRET", "")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_b64: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(sig)


def make_token(user_id: str, project_id: str = None, ttl_days: int = 120,
               secret: str = None, now: int = None) -> str:
    secret = _SECRET if secret is None else secret
    if not secret:
        raise RuntimeError("BMS_FOLLOW_SECRET not set")
    now = int(time.time()) if now is None else now
    payload = {"u": user_id, "p": project_id, "e": now + ttl_days * 86400}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return payload_b64 + "." + _sign(payload_b64, secret)


def verify_token(token: str, secret: str = None, now: int = None):
    """คืน (user_id, project_id, exp_epoch) หรือ None ถ้า sig ผิด/หมดอายุ/รูปแบบเสีย."""
    secret = _SECRET if secret is None else secret
    if not secret or not token or "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload_b64, secret), sig):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        return None
    e = payload.get("e")
    if not isinstance(e, int):
        return None
    now = int(time.time()) if now is None else now
    if e <= now:
        return None
    return payload.get("u"), payload.get("p"), e
