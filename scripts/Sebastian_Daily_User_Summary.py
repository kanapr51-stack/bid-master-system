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


def fetch_digest_jobs(conn) -> list:
    """งานก่อสร้างทั่วจังหวัดที่รอรวมในสรุป (qualification_status='qualified_digest' — worker พักไว้
    แทนเด้งทีละงาน). คืน [{project_id, name, province, deadline_time}] เรียงจังหวัด+ชื่อ. graceful."""
    try:
        rows = conn.execute("""
            SELECT pl.project_id, COALESCE(ps.project_name, pl.project_id),
                   COALESCE(ps.province, ''), COALESCE(pl.deadline_time, '')
            FROM project_locations pl
            LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE pl.qualification_status = 'qualified_digest'
            ORDER BY ps.province, ps.project_name
        """).fetchall()
    except Exception:
        return []
    return [{"project_id": r[0], "name": r[1] or r[0], "province": r[2] or "",
             "deadline_time": r[3] or ""} for r in rows]


def mark_digest_listed(conn, project_ids) -> int:
    """mark งานที่ลิสต์ในสรุปไปแล้ว → 'digest_listed' (กันลิสต์ซ้ำวันถัดไป). คืนจำนวนที่อัปเดต."""
    ids = list(project_ids)
    if not ids:
        return 0
    qs = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"UPDATE project_locations SET qualification_status='digest_listed' "
        f"WHERE project_id IN ({qs}) AND qualification_status='qualified_digest'", ids)
    return cur.rowcount


def build_message(name: str, matched_today: int, tomorrow_jobs=None, link_fn=None,
                  digest_jobs=None) -> str:
    """สร้างข้อความสรุปรายบุคคล (butler persona).
    digest_jobs = งานก่อสร้างใหม่ทั่วจังหวัดวันนี้ (เนื้อหาหลัก) · tomorrow_jobs = งานยื่นซองพรุ่งนี้.
    link_fn(pid)->url ต่อรายการ."""
    import bid_open
    name = name or "ลูกค้า"
    d = datetime.now(TZ_TH)
    today = f"{d.day}/{d.month}"
    parts = [f"🎩 สรุปประจำวัน {today} — Sebastian\n\nสวัสดีครับ คุณ{name}"]
    if digest_jobs:
        parts.append(f"📋 วันนี้มีงานก่อสร้างใหม่ในพื้นที่ของคุณ {len(digest_jobs)} งาน:\n"
                     + bid_open.format_job_bullets(digest_jobs, link_fn))
    else:
        parts.append("📭 วันนี้ยังไม่มีงานก่อสร้างใหม่ในพื้นที่ของคุณ\n"
                     "ไม่ต้องห่วงครับ ผมเฝ้าตรวจให้ตลอด 🫡")
    if tomorrow_jobs:
        parts.append(f"📅 พรุ่งนี้มีงานเปิดประมูล {len(tomorrow_jobs)} งานในพื้นที่ของคุณ:\n"
                     + bid_open.format_job_bullets(tomorrow_jobs, link_fn))
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

    # โหลด active real customers + นับงานที่ match วันนี้ (ไม่นับ test account) + งานยื่นซองพรุ่งนี้
    import bid_open
    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        # งานก่อสร้างใหม่ทั่วจังหวัด (digest) — list เดียว ทุกคนเห็นเหมือนกัน (whole-province, ทุกคน)
        digest_jobs = fetch_digest_jobs(conn)
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

    print(f"[{now_th}] daily summary — {len(targets)} real customers, "
          f"digest งานก่อสร้างใหม่ {len(digest_jobs)} งาน (today_th={today_th})", flush=True)

    from Sebastian_LINE_Sender import build_follow_link
    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, cnt, tomorrow_jobs in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_message(name, cnt, tomorrow_jobs=tomorrow_jobs, link_fn=link_fn,
                            digest_jobs=digest_jobs)
        if args.dry_run:
            print(f"\n--- [{name}] digest={len(digest_jobs)} พรุ่งนี้={len(tomorrow_jobs)} ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            print(f"  ✅ {name} (digest={len(digest_jobs)})", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg}", flush=True)

    # mark digest jobs ว่าลิสต์แล้ว — เฉพาะตอนส่งจริง + มีคนรับได้สำเร็จ (กันลิสต์ซ้ำ/กันหายตอนส่งล้ม)
    if not args.dry_run and ok > 0 and digest_jobs:
        with get_connection() as conn:
            marked = mark_digest_listed(conn, [j["project_id"] for j in digest_jobs])
        print(f"  📋 mark digest_listed: {marked} งาน", flush=True)

    summary = (f"📋 Daily summary {now_th} — ส่ง {ok}/{len(targets)} คน "
               f"(งานก่อสร้างใหม่ {len(digest_jobs)} งาน)")
    if fail:
        summary += f" (ล้มเหลว {fail})"
    print(summary, flush=True)
    if not args.dry_run and targets:
        _discord(summary)


if __name__ == "__main__":
    main()
