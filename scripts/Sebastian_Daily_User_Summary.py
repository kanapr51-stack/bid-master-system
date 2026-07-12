"""Sebastian_Daily_User_Summary.py — heartbeat สรุปวันละครั้ง ส่ง LINE ให้ user (2026-06-01)

N+200 (2026-07-12): per-customer notifyTime — timer ยิงทุก 15 นาที สคริปต์เช็คเองว่า
ลูกค้าคนไหน "ถึงเวลาที่ตั้งไว้ (notes.notifyTime, default 20:00) แล้วยังไม่ได้รับวันนี้"
(marker: daily_recap_log กันส่งซ้ำ + self-healing ถ้า timer พลาดรอบ จะส่งรอบถัดไป)
- notifyTime ก่อนเที่ยง → ฉบับเช้า: สรุปงาน "เมื่อวาน" + งานเปิดยื่นซอง "วันนี้" + โน้ต due วันนี้
- บ่าย/เย็น → ฉบับเดิม: งานวันนี้ + เปิดยื่นพรุ่งนี้ + โน้ต due พรุ่งนี้

⚠️ นี่คือ engagement heartbeat ไม่ใช่การส่งงาน — งานที่ match ถูกส่งแยกตาม pipeline
ปกติ (Enrichment → queue → LINE_Sender) แล้ว ตัวนี้ทำให้ user รู้ว่าระบบยังเฝ้าให้อยู่
แม้วันที่ไม่มีงาน (กัญจน์เลือก "สรุปวันละ 1 ครั้ง" 2026-06-01 — เลี่ยง spam 3 รอบ/วัน)

นับ "งานที่เกี่ยวกับคุณ" = delivery_log status='sent' (ไม่นับ test) ในวันอ้างอิง

Usage:
    python scripts/Sebastian_Daily_User_Summary.py            # ส่งเฉพาะคนที่ถึงเวลา (โหมด timer)
    python scripts/Sebastian_Daily_User_Summary.py --all      # ส่งทุกคนทันที (manual, ยัง mark กันซ้ำ)
    python scripts/Sebastian_Daily_User_Summary.py --dry-run  # preview เฉยๆ (ไม่ mark)
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from Sebastian_Customer_DB import get_connection
from Sebastian_LINE_Sender import _load_line_token, send_line_push

TZ_TH = timezone(timedelta(hours=7))


def fetch_today_sent(conn, customer_id: int, today_th: str) -> list:
    """งานที่ส่งสำเร็จให้ลูกค้ารายนี้วันนี้ (delivery_log status='sent', ไม่นับ test).
    คืน [{project_id, name}]. graceful."""
    try:
        rows = conn.execute("""
            SELECT DISTINCT dl.project_id, COALESCE(ps.project_name, dl.project_id)
            FROM delivery_log dl
            LEFT JOIN projects_seen ps ON ps.project_id = dl.project_id
            WHERE dl.customer_id=? AND dl.status='sent'
              AND COALESCE(dl.is_test_data,0)=0 AND dl.attempted_at LIKE ?
        """, (customer_id, today_th + "%")).fetchall()
    except Exception:
        return []
    return [{"project_id": r[0], "name": r[1] or r[0]} for r in rows]


DEFAULT_NOTIFY = "20:00"


def _notify_time(notes_str, default: str = DEFAULT_NOTIFY) -> str:
    """อ่าน notifyTime 'HH:MM' จาก notes JSON (หน้า /portal/settings เซฟ) — พัง/ไม่มี/format ผิด → default."""
    try:
        v = (json.loads(notes_str or "{}").get("notifyTime") or "").strip()
        datetime.strptime(v, "%H:%M")
        return v
    except (ValueError, TypeError):
        return default


def recap_sent_today(conn, customer_id: int, date_th: str) -> bool:
    """เคยส่ง recap ให้ลูกค้ารายนี้ในวัน (ไทย) นี้แล้วหรือยัง — daily_recap_log marker."""
    try:
        return conn.execute("SELECT 1 FROM daily_recap_log WHERE customer_id=? AND date_th=?",
                            (customer_id, date_th)).fetchone() is not None
    except Exception:
        return False        # ตารางยังไม่มี (schema เก่า) → ถือว่ายังไม่ส่ง


def mark_recap_sent(conn, customer_id: int, date_th: str, sent_at: str) -> None:
    conn.execute("INSERT OR REPLACE INTO daily_recap_log (customer_id, date_th, sent_at) VALUES (?,?,?)",
                 (customer_id, date_th, sent_at))


def is_due(conn, customer_id: int, notify_hhmm: str, now_hhmm: str, date_th: str) -> bool:
    """ถึงเวลา (now >= notifyTime) และยังไม่ได้รับวันนี้ — self-healing: พลาดรอบ timer แล้วรอบถัดไปยังส่ง."""
    return now_hhmm >= notify_hhmm and not recap_sent_today(conn, customer_id, date_th)


def fetch_notes_due(conn, customer_id: int, date_th: str) -> list:
    """job_notes ที่ entry_date == วันที่ระบุ (โน้ต/timeline ที่ถึงกำหนด). คืน [{project_id, note}]."""
    try:
        rows = conn.execute(
            "SELECT DISTINCT project_id, note FROM job_notes WHERE customer_id=? AND entry_date=?",
            (customer_id, date_th)).fetchall()
    except Exception:
        return []
    return [{"project_id": r[0], "note": r[1]} for r in rows]


def build_message(name: str, matched_today: int, today_jobs=None, tomorrow_jobs=None,
                  notes_due=None, link_fn=None, morning: bool = False) -> str:
    """สรุปประจำวัน (recap ไม่ใช่ส่งงาน). ฉบับเย็น (default): งานวันนี้ + todo พรุ่งนี้.
    morning=True (notifyTime ก่อนเที่ยง): งาน "เมื่อวาน" + เปิดยื่นซอง/โน้ต "วันนี้"
    (caller ต้องส่งข้อมูลของวันที่ตรง variant มาเอง — ฟังก์ชันนี้เปลี่ยนแค่คำ)."""
    import bid_open
    name = name or "ลูกค้า"
    d = datetime.now(TZ_TH)
    today = f"{d.day}/{d.month}"
    day_word = "เมื่อวาน" if morning else "วันนี้"
    next_word = "วันนี้" if morning else "พรุ่งนี้"
    parts = [f"🎩 สรุปประจำวัน {today} — Sebastian\n\nสวัสดีครับ คุณ{name}"]
    if matched_today > 0:
        parts.append(f"📬 {day_word}ผมส่งงานในพื้นที่ของคุณไปแล้ว {matched_today} งาน:\n"
                     + bid_open.format_job_bullets(today_jobs or [], link_fn))
    else:
        parts.append(f"📭 {day_word}ยังไม่มีงานใหม่ในพื้นที่ของคุณ\nไม่ต้องห่วงครับ ผมเฝ้าตรวจให้ตลอด 🫡")
    if tomorrow_jobs:
        parts.append(f"📅 {next_word}มีงานเปิดยื่นซอง {len(tomorrow_jobs)} งาน:\n"
                     + bid_open.format_job_bullets(tomorrow_jobs, link_fn))
    if notes_due:
        note_lines = "\n".join(f"• {n['note']}" for n in notes_due)
        parts.append(f"📝 โน้ตที่ถึงกำหนด{next_word} ({len(notes_due)}):\n{note_lines}")
    return "\n\n".join(parts)


def _discord(msg: str) -> None:
    try:
        from Sebastian_Discord_Notify import load_env, get_credentials, send
        load_env()
        token, ch = get_credentials()
        send(token, ch, msg)
    except Exception as e:
        print(f"[WARN] Discord notify failed: {e}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Sebastian daily user heartbeat (LINE)")
    ap.add_argument("--dry-run", action="store_true", help="Preview เฉยๆ ไม่ส่งจริง ไม่ mark")
    ap.add_argument("--all", action="store_true", help="ส่งทุกคนทันที ข้ามเช็คเวลา/marker (ยัง mark กันซ้ำ)")
    args = ap.parse_args()

    now = datetime.now(TZ_TH)
    today_th = now.strftime("%Y-%m-%d")
    yesterday_th = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_th = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    now_th = now.strftime("%H:%M")

    import bid_open
    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name, notes FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        targets = []
        for c in customers:
            nt = _notify_time(c["notes"])
            if not args.all and not is_due(conn, c["id"], nt, now_th, today_th):
                continue
            morning = int(nt[:2]) < 12
            # เช้า = สรุปเมื่อวาน + เปิดยื่น/โน้ตของวันนี้ · เย็น = วันนี้ + พรุ่งนี้ (เดิม)
            ref_day = yesterday_th if morning else today_th
            next_day = today_th if morning else tomorrow_th
            ref_jobs = fetch_today_sent(conn, c["id"], ref_day)
            cnt = len(ref_jobs)   # นับ = จำนวนงาน distinct ที่ลิสต์ (header ตรงกับรายการ ไม่นับ retry ซ้ำ)
            next_jobs = bid_open.bid_open_for_customer(conn, c["id"], next_day)
            notes_due = fetch_notes_due(conn, c["id"], next_day)
            targets.append((c, nt, morning, cnt, ref_jobs, next_jobs, notes_due))

    print(f"[{now_th}] daily recap — due {len(targets)}/{len(customers)} customers (today_th={today_th})", flush=True)
    if not targets:
        return

    from Sebastian_LINE_Sender import build_follow_link
    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, nt, morning, cnt, ref_jobs, next_jobs, notes_due in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_message(name, cnt, today_jobs=ref_jobs, tomorrow_jobs=next_jobs,
                            notes_due=notes_due, link_fn=link_fn, morning=morning)
        if args.dry_run:
            print(f"\n--- [{name}] notify={nt} {'เช้า' if morning else 'เย็น'} งาน={cnt} เปิดยื่น={len(next_jobs)} โน้ต={len(notes_due)} ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            with get_connection() as conn:
                mark_recap_sent(conn, c["id"], today_th, now.isoformat(timespec="seconds"))
            print(f"  ✅ {name} (notify={nt}, งาน={cnt})", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg}", flush=True)

    summary = f"📋 Daily recap {now_th} — ส่ง {ok}/{len(targets)} คนที่ถึงเวลา"
    if fail:
        summary += f" (ล้มเหลว {fail})"
    print(summary, flush=True)
    if not args.dry_run and targets:
        _discord(summary)


if __name__ == "__main__":
    main()
