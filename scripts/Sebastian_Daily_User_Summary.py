"""Sebastian_Daily_User_Summary.py — heartbeat สรุปวันละครั้ง ส่ง LINE ให้ user (2026-06-01)

รอบเย็น (20:00 ไทย, หลัง discovery รอบสุดท้าย 19:00 + buffer pipeline) — บอก user ว่า
"วันนี้ Sebastian ตรวจงานในพื้นที่ของคุณแล้ว เจองานที่เกี่ยวกับคุณ N งาน"

⚠️ นี่คือ engagement heartbeat ไม่ใช่การส่งงาน — งานที่ match ถูกส่งแยกตาม pipeline
ปกติ (Enrichment → queue → LINE_Sender) แล้ว ตัวนี้ทำให้ user รู้ว่าระบบยังเฝ้าให้อยู่
แม้วันที่ไม่มีงาน (กัญจน์เลือก "สรุปวันละ 1 ครั้ง" 2026-06-01 — เลี่ยง spam 3 รอบ/วัน)

นับ "งานที่เกี่ยวกับคุณ" = delivery_log status='sent' (ไม่นับ test) ในวันไทยปัจจุบัน

Usage:
    python scripts/Sebastian_Daily_User_Summary.py            # ส่งจริง
    python scripts/Sebastian_Daily_User_Summary.py --dry-run  # preview เฉยๆ
"""
import argparse
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
                  notes_due=None, link_fn=None) -> str:
    """สรุปประจำวัน (recap ไม่ใช่ส่งงาน): นับวันนี้ + รายการงานวันนี้ + todo พรุ่งนี้ + โน้ต due พรุ่งนี้."""
    import bid_open
    name = name or "ลูกค้า"
    d = datetime.now(TZ_TH)
    today = f"{d.day}/{d.month}"
    parts = [f"🎩 สรุปประจำวัน {today} — Sebastian\n\nสวัสดีครับ คุณ{name}"]
    if matched_today > 0:
        parts.append(f"📬 วันนี้ผมส่งงานในพื้นที่ของคุณไปแล้ว {matched_today} งาน:\n"
                     + bid_open.format_job_bullets(today_jobs or [], link_fn))
    else:
        parts.append("📭 วันนี้ยังไม่มีงานใหม่ในพื้นที่ของคุณ\nไม่ต้องห่วงครับ ผมเฝ้าตรวจให้ตลอด 🫡")
    if tomorrow_jobs:
        parts.append(f"📅 พรุ่งนี้มีงานเปิดยื่นซอง {len(tomorrow_jobs)} งาน:\n"
                     + bid_open.format_job_bullets(tomorrow_jobs, link_fn))
    if notes_due:
        note_lines = "\n".join(f"• {n['note']}" for n in notes_due)
        parts.append(f"📝 โน้ตที่ถึงกำหนดพรุ่งนี้ ({len(notes_due)}):\n{note_lines}")
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
    ap.add_argument("--dry-run", action="store_true", help="Preview เฉยๆ ไม่ส่งจริง")
    args = ap.parse_args()

    today_th = datetime.now(TZ_TH).strftime("%Y-%m-%d")
    tomorrow_th = (datetime.now(TZ_TH) + timedelta(days=1)).strftime("%Y-%m-%d")
    now_th = datetime.now(TZ_TH).strftime("%H:%M")

    import bid_open
    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        targets = []
        for c in customers:
            today_jobs = fetch_today_sent(conn, c["id"], today_th)
            cnt = len(today_jobs)   # นับ = จำนวนงาน distinct ที่ลิสต์ (header ตรงกับรายการ ไม่นับ retry ซ้ำ)
            tomorrow_jobs = bid_open.bid_open_for_customer(conn, c["id"], tomorrow_th)
            notes_due = fetch_notes_due(conn, c["id"], tomorrow_th)
            targets.append((c, cnt, today_jobs, tomorrow_jobs, notes_due))

    print(f"[{now_th}] daily recap — {len(targets)} real customers (today_th={today_th})", flush=True)

    from Sebastian_LINE_Sender import build_follow_link
    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, cnt, today_jobs, tomorrow_jobs, notes_due in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_message(name, cnt, today_jobs=today_jobs, tomorrow_jobs=tomorrow_jobs,
                            notes_due=notes_due, link_fn=link_fn)
        if args.dry_run:
            print(f"\n--- [{name}] วันนี้={cnt} พรุ่งนี้={len(tomorrow_jobs)} โน้ต={len(notes_due)} ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            print(f"  ✅ {name} (วันนี้={cnt})", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg}", flush=True)

    summary = f"📋 Daily recap {now_th} — ส่ง {ok}/{len(targets)} คน"
    if fail:
        summary += f" (ล้มเหลว {fail})"
    print(summary, flush=True)
    if not args.dry_run and targets:
        _discord(summary)


if __name__ == "__main__":
    main()
