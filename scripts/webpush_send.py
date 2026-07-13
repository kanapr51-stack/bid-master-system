"""ส่ง Web Push (VAPID) ไปทุกเครื่องที่ลูกค้า subscribe บนบอร์ด B.

Contract: ไม่ raise ออกนอก module เด็ดขาด (best-effort ขนานกับ LINE — LINE path
ห้ามล้มเพราะ webpush). ผลส่งลง webpush_delivery_log เท่านั้น ห้ามแตะ delivery_log
(bid_open.undelivered_backlog อ่านตารางนั้นตัดสินงานค้าง).
เปิดใช้เมื่อมี VAPID_PRIVATE_KEY + VAPID_SUBJECT ใน env; BMS_WEBPUSH_DISABLED=1 = ปิด.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import get_connection  # noqa: E402

_TZ = timezone(timedelta(hours=7))
TITLE_MAX = 60
BODY_MAX = 180


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _board_base() -> str:
    return os.environ.get("BMS_BOARD_BASE_URL", "https://bid-master-dashboard.vercel.app").rstrip("/")


def job_url(project_id: str) -> str:
    if project_id:
        return f"{_board_base()}/portal/job/{project_id}"
    return f"{_board_base()}/portal/world"


def split_text(text: str) -> tuple[str, str]:
    """หั่นข้อความ LINE เป็น (title, body) สำหรับ notification — บรรทัดแรก = title."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    title = (lines[0] if lines else "BMS Bid Board")[:TITLE_MAX]
    body = " ".join(lines[1:])[:BODY_MAX]
    return title, body


def _log(conn, sub_id: int, customer_id: int, project_id: str, source_stage: str,
         status: str, error: str = "") -> None:
    conn.execute(
        "INSERT INTO webpush_delivery_log "
        "(subscription_id, customer_id, project_id, source_stage, status, error, attempted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sub_id, customer_id, project_id or "", source_stage or "", status, (error or "")[:300], _now()))


def send_to_user(line_user_id: str, title: str, body: str, url: str,
                 project_id: str = "", source_stage: str = "") -> tuple[int, int]:
    """ยิงไปทุก subscription active ของ user. คืน (sent, failed). ไม่ raise."""
    try:
        if os.environ.get("BMS_WEBPUSH_DISABLED") == "1":
            return (0, 0)
        priv = os.environ.get("VAPID_PRIVATE_KEY", "")
        subject = os.environ.get("VAPID_SUBJECT", "")
        if not priv or not subject:
            return (0, 0)  # ยังไม่ config = feature ปิดเงียบๆ
        from pywebpush import webpush, WebPushException
        payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
        sent = failed = 0
        with get_connection() as conn:
            cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?",
                                (line_user_id,)).fetchone()
            if not cust:
                return (0, 0)
            cid = cust["id"]
            subs = conn.execute(
                "SELECT id, endpoint, p256dh, auth FROM push_subscriptions "
                "WHERE customer_id=? AND disabled_at IS NULL", (cid,)).fetchall()
            for s in subs:
                try:
                    webpush(
                        subscription_info={"endpoint": s["endpoint"],
                                           "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                        data=payload,
                        vapid_private_key=priv,
                        vapid_claims={"sub": subject},
                        timeout=10,
                    )
                    conn.execute("UPDATE push_subscriptions SET last_ok_at=? WHERE id=?",
                                 (_now(), s["id"]))
                    _log(conn, s["id"], cid, project_id, source_stage, "sent")
                    sent += 1
                except WebPushException as e:
                    code = getattr(getattr(e, "response", None), "status_code", None)
                    try:
                        if code in (404, 410):  # เพิกถอน/ลบเบราว์เซอร์ → ปิดถาวร ไม่ยิงซ้ำ
                            conn.execute("UPDATE push_subscriptions SET disabled_at=? WHERE id=?",
                                         (_now(), s["id"]))
                        _log(conn, s["id"], cid, project_id, source_stage, "failed", f"HTTP {code}: {e}")
                    except Exception:
                        pass  # log พังซ้ำ — อย่าให้ล้ม loop แล้ว rollback แถวของเครื่องก่อนหน้า
                    failed += 1
                except Exception as e:  # payload/key เพี้ยน ฯลฯ — log แล้วไปต่อเครื่องถัดไป
                    try:
                        _log(conn, s["id"], cid, project_id, source_stage, "failed",
                             f"{type(e).__name__}: {e}")
                    except Exception:
                        pass  # log พังซ้ำ — อย่าให้ล้ม loop แล้ว rollback แถวของเครื่องก่อนหน้า
                    failed += 1
        return (sent, failed)
    except Exception:
        return (0, 0)


def mirror_text(line_user_id: str, text: str,
                project_id: str = "", source_stage: str = "") -> tuple[int, int]:
    """Mirror ข้อความ LINE → web push (title/body หั่นจาก text). ไม่ raise."""
    try:
        title, body = split_text(text)
        return send_to_user(line_user_id, title, body, job_url(project_id),
                            project_id, source_stage)
    except Exception:
        return (0, 0)
