"""Sebastian_BidOpen_Morning.py — แจ้งเตือนเช้า (07:00 ไทย): งานที่ยื่นซอง "วันนี้" ในพื้นที่ของ user.

scope = bid_open.bid_open_for_customer (งานที่ระบบ match ให้ลูกค้า = delivery_log non-test)
ที่ bid_submit_date == วันนี้ (ไทย). ส่ง LINE เฉพาะ user ที่มี ≥1 งาน (0 งาน = ไม่ส่ง — เลี่ยง spam เช้า).

Usage:
    python scripts/Sebastian_BidOpen_Morning.py            # ส่งจริง
    python scripts/Sebastian_BidOpen_Morning.py --dry-run  # preview เฉยๆ
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
    """ลิงก์หน้า Bid Board ต่อ user (portal token p=None). คืน '' ถ้า mint พลาด."""
    try:
        return _ls.PUBLIC_BASE_URL.rstrip("/") + "/portal?t=" + follow_token.make_token(line_user_id, None)
    except Exception:
        return ""


def build_morning_message(name: str, jobs: list, link_fn=None, portal_link: str = "") -> str:
    """ข้อความแจ้งเช้า — งานยื่นซองวันนี้. link_fn(pid)->url ต่อรายการ (None=ไม่ใส่)."""
    name = name or "ลูกค้า"
    d = datetime.now(TZ_TH)
    today = f"{d.day}/{d.month}"
    head = (f"🔔 งานเปิดประมูลวันนี้ {today} — Sebastian\n\n"
            f"สวัสดีครับ คุณ{name}\n"
            f"วันนี้มีงานที่ถึงกำหนดยื่นซอง {len(jobs)} งานในพื้นที่ของคุณ:\n\n")
    body = bid_open.format_job_bullets(jobs, link_fn)
    tail = f"\n\n🗂 ดูทั้งหมดบนบอร์ด: {portal_link}" if portal_link else ""
    return head + body + tail


def main():
    ap = argparse.ArgumentParser(description="Sebastian morning bid-open reminder (LINE)")
    ap.add_argument("--dry-run", action="store_true", help="Preview เฉยๆ ไม่ส่งจริง")
    args = ap.parse_args()

    today_th = datetime.now(TZ_TH).strftime("%Y-%m-%d")
    now_th = datetime.now(TZ_TH).strftime("%H:%M")

    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        targets = []
        for c in customers:
            jobs = bid_open.bid_open_for_customer(conn, c["id"], today_th)
            if jobs:
                targets.append((c, jobs))

    print(f"[{now_th}] morning bid-open — {len(targets)} customers มีงานยื่นซองวันนี้ (today_th={today_th})", flush=True)

    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, jobs in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_morning_message(name, jobs, link_fn=link_fn, portal_link=_portal_link(c["line_user_id"]))
        if args.dry_run:
            print(f"\n--- [{name}] {len(jobs)} งาน ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            print(f"  ✅ {name} ({len(jobs)} งาน)", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg}", flush=True)

    print(f"🔔 morning bid-open {now_th} — ส่ง {ok}/{len(targets)} คน" + (f" (ล้มเหลว {fail})" if fail else ""), flush=True)


if __name__ == "__main__":
    main()
