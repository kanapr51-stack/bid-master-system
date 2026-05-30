"""
reclassify_backlog_by_announcedate.py — one-time backlog cleanup (ChatGPT+Claude converged 2026-05-30)

ปัญหา: P2 บึงกาฬ ingest ใช้ projectId-prefix (creation signal) แยก backlog
        แต่ projectId เก่า + announceDate ล่าสุด = งานเปิดที่ถูก suppress ผิด (เช่น 69049214773)
แก้: re-fetch list ครั้งเดียว → ใช้ announceDate (opportunity signal) re-classify

policy (terminal, ไม่ใช่ non-terminal loop — base rate backlog = almost all expired):
  suppressed_backlog ที่ announceDate >= today-WINDOW → 'pending' (ให้ resolver authoritative gate เช็ค)
  ที่เหลือ → คง suppressed_backlog (terminal)
  --reset-provider-errors: failed_provider_error → 'pending' (transient ที่ fail 5x — ลองใหม่)

announceDate format = ISO CE ('2026-05-29T...' → [:10]) → string compare ปลอดภัย
รันบน VPS (worker mode อ่าน token ที่ Windows push) — read-only list fetch, ไม่ resolve PDF

Usage:
  python reclassify_backlog_by_announcedate.py --province บึงกาฬ --moi 380000          # dry-run
  python reclassify_backlog_by_announcedate.py --province บึงกาฬ --moi 380000 --apply --reset-provider-errors
"""
import sys
import os
import sqlite3
import argparse
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from token_service import TokenService, make_provider
import Sebastian_Province_Discovery as disc


def _db_path() -> str:
    return os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"), "bms_customers.db")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--province", required=True)
    ap.add_argument("--moi", required=True)
    ap.add_argument("--budget-year", default="2569")
    ap.add_argument("--window-days", type=int, default=45,
                    help="announceDate ภายใน N วัน → pending (default 45)")
    ap.add_argument("--reset-provider-errors", action="store_true",
                    help="failed_provider_error → pending (transient retry)")
    ap.add_argument("--apply", action="store_true", help="เขียนจริง (default: dry-run)")
    args = ap.parse_args()

    # token: worker mode (อ่าน cache ที่ push มา ไม่ harvest)
    svc = TokenService(make_provider(""), allow_refresh=False)
    token = svc.get_valid_token()
    if not token:
        h = svc.health()
        print(f"❌ ไม่ได้ token (state={h['state']}, err={h.get('last_error')})")
        return 1
    print(f"🔑 token OK (เหลือ {svc.health()['remaining_sec']}s)")

    # 1) re-fetch list → {projectId: announceDate(ISO CE 'YYYY-MM-DD')}
    items = disc.fetch_all_d0(token, args.moi, args.budget_year)
    amap = {}
    for it in items:
        r = disc.normalize(it, args.province)
        if r["project_id"]:
            amap[r["project_id"]] = r["announce_date"]   # already [:10]
    print(f"📥 announceDate map: {len(amap)} projects")
    if not amap:
        print("❌ list ว่าง — token หมดอายุ? ยกเลิก")
        return 2

    cutoff = (date.today() - timedelta(days=args.window_days)).isoformat()
    print(f"🪟 window cutoff (announceDate >=): {cutoff}")

    conn = sqlite3.connect(_db_path())
    backlog = conn.execute(
        "SELECT project_id FROM project_locations "
        "WHERE source='province_api' AND province_name=? AND qualification_status='suppressed_backlog'",
        (args.province,)).fetchall()
    to_pending = []
    no_date = 0
    for (pid,) in backlog:
        ad = amap.get(pid, "")
        if not ad:
            no_date += 1
            continue
        if ad >= cutoff:
            to_pending.append((pid, ad))
    print(f"\n📊 suppressed_backlog: {len(backlog)} | recent announceDate (>= cutoff): {len(to_pending)} | ไม่มี announceDate ใน list: {no_date}")
    for pid, ad in sorted(to_pending, key=lambda x: x[1], reverse=True)[:30]:
        print(f"   → pending {pid} (announce={ad}, prefix={pid[:4]})")

    reset_pe = []
    if args.reset_provider_errors:
        reset_pe = [r[0] for r in conn.execute(
            "SELECT project_id FROM project_locations "
            "WHERE source='province_api' AND province_name=? AND qualification_status='failed_provider_error'",
            (args.province,)).fetchall()]
        print(f"♻️  failed_provider_error → pending: {len(reset_pe)}")

    if not args.apply:
        print(f"\n(dry-run — จะเปลี่ยน {len(to_pending)} backlog + {len(reset_pe)} provider_error เป็น pending ถ้าใส่ --apply)")
        return 0

    for pid, _ in to_pending:
        conn.execute("UPDATE project_locations SET qualification_status='pending', enrichment_attempts=0 WHERE project_id=?", (pid,))
    for pid in reset_pe:
        conn.execute("UPDATE project_locations SET qualification_status='pending', enrichment_attempts=0 WHERE project_id=?", (pid,))
    conn.commit()
    conn.close()
    print(f"\n✅ APPLIED: {len(to_pending)} backlog→pending, {len(reset_pe)} provider_error→pending "
          f"(resolver จะเช็ค deadline รอบ enrichment ถัดไป)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
