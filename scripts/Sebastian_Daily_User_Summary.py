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


def build_message(name: str, matched_today: int, tomorrow_jobs=None, link_fn=None) -> str:
    """สร้างข้อความ heartbeat รายบุคคล (butler persona). tomorrow_jobs = งานยื่นซองพรุ่งนี้
    (ในพื้นที่) → ต่อท้ายเป็น section ถ้ามี. link_fn(pid)->url ต่อรายการ."""
    name = name or "ลูกค้า"
    d = datetime.now(TZ_TH)
    today = f"{d.day}/{d.month}"
    head = f"🎩 สรุปประจำวัน {today} — Sebastian\n\nสวัสดีครับ คุณ{name}\n"
    if matched_today > 0:
        base = (
            head +
            f"วันนี้ผมตรวจงานประมูลในพื้นที่ของคุณครบทุกรอบแล้ว\n"
            f"📬 เจองานที่เกี่ยวกับคุณ {matched_today} งาน — ส่งให้คุณก่อนหน้านี้แล้ว ✅\n\n"
            f"พรุ่งนี้ผมจะเฝ้าตรวจให้ต่อครับ 🫡"
        )
    else:
        base = (
            head +
            f"วันนี้ผมตรวจงานประมูลในพื้นที่ของคุณครบทุกรอบแล้ว\n"
            f"📭 ยังไม่มีงานใหม่ที่ตรงกับเงื่อนไขของคุณวันนี้\n\n"
            f"ไม่ต้องห่วงครับ ผมเฝ้าให้ตลอด — มีงานเมื่อไหร่ส่งทันที 🫡"
        )
    if tomorrow_jobs:
        import bid_open
        base += (f"\n\n📅 พรุ่งนี้มีงานเปิดประมูล {len(tomorrow_jobs)} งานในพื้นที่ของคุณ:\n"
                 + bid_open.format_job_bullets(tomorrow_jobs, link_fn))
    return base


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

    # โหลด active real customers + นับงานที่ match วันนี้ (ไม่นับ test account) + งานยื่นซองพรุ่งนี้
    import bid_open
    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        targets = []
        for c in customers:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM delivery_log "
                "WHERE customer_id=? AND status='sent' AND COALESCE(is_test_data,0)=0 "
                "AND attempted_at LIKE ?",
                (c["id"], today_th + "%"),
            ).fetchone()[0]
            tomorrow_jobs = bid_open.bid_open_for_customer(conn, c["id"], tomorrow_th)
            targets.append((c, cnt, tomorrow_jobs))

    print(f"[{now_th}] daily summary — {len(targets)} real customers (today_th={today_th})", flush=True)

    from Sebastian_LINE_Sender import build_follow_link
    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, cnt, tomorrow_jobs in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_message(name, cnt, tomorrow_jobs=tomorrow_jobs, link_fn=link_fn)
        if args.dry_run:
            print(f"\n--- [{name}] matched_today={cnt} พรุ่งนี้={len(tomorrow_jobs)} ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            print(f"  ✅ {name} (matched_today={cnt})", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg}", flush=True)

    summary = f"📋 Daily summary {now_th} — ส่ง heartbeat {ok}/{len(targets)} คน"
    if fail:
        summary += f" (ล้มเหลว {fail})"
    print(summary, flush=True)
    if not args.dry_run and targets:
        _discord(summary)


if __name__ == "__main__":
    main()
