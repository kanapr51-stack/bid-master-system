"""Sebastian_BidOpen_Morning.py — แจ้งเตือนเช้า: งานที่ยื่นซอง "วันนี้" ในพื้นที่ของ user.

N+201 (2026-07-12): per-customer morningNotifyTime (notes, default 07:30) — timer ยิงทุก 15 นาที
สคริปต์เช็คเองว่าใครถึงเวลา+ยังไม่ประมวลผลวันนี้ (marker daily_notify_log kind='bidopen';
due แต่ไม่มีงาน = mark เฉยๆ ไม่ส่ง → พฤติกรรม one-shot/วัน เท่าเดิม แค่เวลาเลือกได้)

scope = bid_open.bid_open_for_customer (งานที่ระบบ match ให้ลูกค้า = delivery_log non-test)
ที่ bid_submit_date == วันนี้ (ไทย). ส่ง LINE เฉพาะ user ที่มี ≥1 งาน (0 งาน = ไม่ส่ง — เลี่ยง spam เช้า).

Usage:
    python scripts/Sebastian_BidOpen_Morning.py            # ส่งเฉพาะคนที่ถึงเวลา (โหมด timer)
    python scripts/Sebastian_BidOpen_Morning.py --all      # ส่งทุกคนทันที (manual)
    python scripts/Sebastian_BidOpen_Morning.py --dry-run  # preview เฉยๆ (ไม่ mark)
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
    ap.add_argument("--dry-run", action="store_true", help="Preview เฉยๆ ไม่ส่งจริง ไม่ mark")
    ap.add_argument("--all", action="store_true", help="ส่งทุกคนทันที ข้ามเช็คเวลา/marker")
    args = ap.parse_args()

    import notify_schedule as ns
    now = datetime.now(TZ_TH)
    today_th = now.strftime("%Y-%m-%d")
    now_th = now.strftime("%H:%M")
    now_iso = now.isoformat(timespec="seconds")

    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name, notes FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        targets, no_jobs = [], []
        for c in customers:
            t = ns.pref_time(c["notes"], "morningNotifyTime", ns.DEFAULT_MORNING)
            if not args.all and not ns.is_due(conn, "bidopen", c["id"], t, now_th, today_th):
                continue
            jobs = bid_open.bid_open_for_customer(conn, c["id"], today_th)
            if jobs:
                targets.append((c, t, jobs))
            else:
                no_jobs.append(c["id"])
        if not args.dry_run:
            for cid in no_jobs:   # due แต่ไม่มีงาน → mark ว่าประมวลผลแล้ว (one-shot/วัน เท่าพฤติกรรมเดิม)
                ns.mark_sent(conn, "bidopen", cid, today_th, now_iso)

    print(f"[{now_th}] morning bid-open — due {len(targets) + len(no_jobs)}/{len(customers)} · มีงาน {len(targets)} (today_th={today_th})", flush=True)
    if not targets:
        return

    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, t, jobs in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_morning_message(name, jobs, link_fn=link_fn, portal_link=_portal_link(c["line_user_id"]))
        if args.dry_run:
            print(f"\n--- [{name}] notify={t} {len(jobs)} งาน ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            with get_connection() as conn:
                ns.mark_sent(conn, "bidopen", c["id"], today_th, now_iso)
            print(f"  ✅ {name} (notify={t}, {len(jobs)} งาน)", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg}", flush=True)

    print(f"🔔 morning bid-open {now_th} — ส่ง {ok}/{len(targets)} คน" + (f" (ล้มเหลว {fail})" if fail else ""), flush=True)


if __name__ == "__main__":
    main()
