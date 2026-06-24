"""Sebastian_Backlog_Digest.py — รวมงานที่ส่งไม่ออกช่วง LINE quota เต็ม → แจ้งทีเดียว (รันวันที่ 1).

ที่มา: ระหว่าง quota เต็ม (300/300) งานใหม่ที่ match แต่ส่งไม่ออกถูก log เป็น delivery_log
status!='sent'. สคริปต์นี้รวมต่อ user → ส่งข้อความเดียว (เฉพาะงานที่ยังไม่หมดเขตยื่นซอง)
แล้ว mark delivered (idempotent — ส่งสำเร็จค่อย mark → quota ยังไม่พร้อม = รันซ้ำได้).

Usage:
    python scripts/Sebastian_Backlog_Digest.py [--since YYYY-MM-DD] [--dry-run]
"""
import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import bid_open
import follow_token
import Sebastian_LINE_Sender as _ls
from Sebastian_Customer_DB import get_connection
from Sebastian_LINE_Sender import _load_line_token, send_line_push, build_follow_link

TZ_TH = timezone(timedelta(hours=7))


def _portal_link(line_user_id: str) -> str:
    try:
        return _ls.PUBLIC_BASE_URL.rstrip("/") + "/portal?t=" + follow_token.make_token(line_user_id, None)
    except Exception:
        return ""


def build_backlog_message(name: str, jobs: list, link_fn=None, portal_link: str = "") -> str:
    """ข้อความรวมงานสะสม (งานใหม่ช่วง quota เต็ม). link_fn(pid)->url ต่อรายการ."""
    name = name or "ลูกค้า"
    head = (f"📋 งานใหม่ที่สะสมไว้ — Sebastian\n\n"
            f"สวัสดีครับ คุณ{name}\n"
            f"ช่วงที่ผ่านมามีงานเปิดประมูลในพื้นที่ของคุณ {len(jobs)} งาน (ยังไม่หมดเขตยื่นซอง):\n\n")
    body = bid_open.format_job_bullets(jobs, link_fn)
    tail = f"\n\n🗂 ดูทั้งหมดบนบอร์ด: {portal_link}" if portal_link else ""
    return head + body + tail


def _mark_delivered(conn, customer_id: int, project_id: str, now: str):
    """บันทึก delivery_log 'sent' (ส่งผ่าน digest แล้ว) → กันส่งซ้ำ (NOT EXISTS sent)."""
    conn.execute(
        "INSERT INTO delivery_log (customer_id, project_id, channel, status, error_type, attempted_at, is_test_data) "
        "VALUES (?,?, 'line','sent','backlog_digest',?,0)",
        (customer_id, project_id, now),
    )


def main():
    ap = argparse.ArgumentParser(description="Sebastian backlog digest (รวมงานสะสมช่วง quota เต็ม)")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD (default = 30 วันก่อน)")
    ap.add_argument("--dry-run", action="store_true", help="Preview เฉยๆ ไม่ส่งจริง")
    args = ap.parse_args()

    now = datetime.now(TZ_TH)
    today_th = now.strftime("%Y-%m-%d")
    since = args.since or (now - timedelta(days=30)).strftime("%Y-%m-%d")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S+07:00")

    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        targets = []
        for c in customers:
            jobs = bid_open.undelivered_backlog(conn, c["id"], since=since, min_deadline=today_th)
            if jobs:
                targets.append((dict(c), jobs))

    print(f"[{now.strftime('%H:%M')}] backlog digest — since={since}, {len(targets)} customers มีงานสะสม", flush=True)

    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, jobs in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_backlog_message(name, jobs, link_fn=link_fn, portal_link=_portal_link(c["line_user_id"]))
        if args.dry_run:
            print(f"\n--- [{name}] {len(jobs)} งาน ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            with get_connection() as conn:                     # idempotent: mark เฉพาะตอนส่งสำเร็จ
                for j in jobs:
                    _mark_delivered(conn, c["id"], j["project_id"], now_iso)
            print(f"  ✅ {name} ({len(jobs)} งาน) → mark delivered", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg} (ไม่ mark → รันซ้ำได้)", flush=True)

    print(f"📋 backlog digest — ส่ง {ok}/{len(targets)} คน" + (f" (ล้มเหลว {fail})" if fail else ""), flush=True)


if __name__ == "__main__":
    main()
