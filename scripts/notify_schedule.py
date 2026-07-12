"""notify_schedule.py — per-customer เวลาแจ้งเตือน (N+201): helper กลางของสคริปต์ notify
ที่เปลี่ยนจาก timer เวลาตายตัว → timer ทุก 15 นาที + เช็คเวลาต่อลูกค้า + marker กันส่งซ้ำ.

- เวลาอ่านจาก customers.notes JSON (หน้า /portal/settings เซฟ) — format 'HH:MM' เท่านั้น
- marker: daily_notify_log(kind, customer_id, date_th) = "ประมวลผลแล้ววันนี้"
  (ส่งสำเร็จ หรือ ไม่มีอะไรต้องส่ง) → ส่งล้มเหลว = ไม่ mark = รอบ 15 นาทีถัดไป retry เอง
- recap สรุปประจำวัน (Sebastian_Daily_User_Summary) ใช้ daily_recap_log เดิมของตัวเอง (N+200)
"""
import json
from datetime import datetime

DEFAULT_MORNING = "07:30"   # เวลาแจ้งเตือนตอนเช้า (งานยื่นซองวันนี้ + แผนงานที่จด) — กัญจน์ 2026-07-12


def pref_time(notes_str, key: str, default: str) -> str:
    """อ่านเวลา 'HH:MM' จาก notes JSON ตาม key — พัง/ไม่มี/format ผิด → default."""
    try:
        v = (json.loads(notes_str or "{}").get(key) or "").strip()
        datetime.strptime(v, "%H:%M")
        return v
    except (ValueError, TypeError):
        return default


def sent_today(conn, kind: str, customer_id: int, date_th: str) -> bool:
    """ประมวลผล kind นี้ให้ลูกค้ารายนี้ในวัน (ไทย) นี้แล้วหรือยัง."""
    try:
        return conn.execute(
            "SELECT 1 FROM daily_notify_log WHERE kind=? AND customer_id=? AND date_th=?",
            (kind, customer_id, date_th)).fetchone() is not None
    except Exception:
        return False        # ตารางยังไม่มี (schema เก่า) → ถือว่ายังไม่ส่ง


def mark_sent(conn, kind: str, customer_id: int, date_th: str, sent_at: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO daily_notify_log (kind, customer_id, date_th, sent_at) VALUES (?,?,?,?)",
        (kind, customer_id, date_th, sent_at))


def is_due(conn, kind: str, customer_id: int, notify_hhmm: str, now_hhmm: str, date_th: str) -> bool:
    """ถึงเวลา (now >= เวลาที่ตั้ง) และยังไม่ประมวลผลวันนี้ — self-healing ถ้า timer พลาดรอบ."""
    return now_hhmm >= notify_hhmm and not sent_today(conn, kind, customer_id, date_th)
