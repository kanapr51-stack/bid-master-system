"""
seed_self_notify.py — Synthetic notification injection harness (evolving from self-notify bootstrap)

Two modes (combinable):

  SEED customer + subscription:
    python scripts/seed_self_notify.py --line-id U...
    python scripts/seed_self_notify.py --line-id U... --provinces กรุงเทพ นนทบุรี

  INJECT synthetic project event → projects_seen → notification_queue:
    python scripts/seed_self_notify.py --project-id 68012345678 --province นครพนม
    python scripts/seed_self_notify.py --project-id 68012345678 --province กรุงเทพ --budget 2500000

  Combined (seed customer then inject):
    python scripts/seed_self_notify.py --line-id U... --project-id 68012345678 --province นครพนม

  Add --dry-run to any of the above to preview without writing.

Always injects through projects_seen → matching → notification_queue.
Never bypasses the matching pipeline.

LINE user ID source: LINE Developers Console → Basic Settings → "Your user ID"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import SubscriptionStore, init_schema, _now

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_ANNOUNCE_TYPES = ["D0"]
DEFAULT_MIN_BUDGET     = 0


# ── Customer seed ─────────────────────────────────────────────────────────────

def seed_customer(line_user_id: str, provinces: list[str], dry_run: bool = False):
    print(f"\n{'[DRY RUN] ' if dry_run else ''}[SEED CUSTOMER]")
    print(f"  LINE user ID : {line_user_id}")
    print(f"  Provinces    : {provinces}")
    print(f"  Types        : {DEFAULT_ANNOUNCE_TYPES}")

    if dry_run:
        print("  → DRY RUN — ไม่ได้ write จริง")
        return None

    init_schema()
    store = SubscriptionStore()

    cid = store.add_customer(
        line_user_id = line_user_id,
        display_name = "เจ้าของ BMS (test)",
        tier         = "trial",
    )
    sub_id = store.add_subscription(
        customer_id    = cid,
        provinces      = provinces,
        announce_types = DEFAULT_ANNOUNCE_TYPES,
        min_budget     = DEFAULT_MIN_BUDGET,
    )
    print(f"  → Customer id={cid}, Subscription id={sub_id} provinces={provinces} ✅")
    return store


# ── Project inject ────────────────────────────────────────────────────────────

def inject_project(project_id: str, province: str, budget: int,
                   announce_type: str, project_name: str = "",
                   dept_name: str = "", dry_run: bool = False) -> int:
    """
    Inject synthetic project through projects_seen → matching → notification_queue.
    Returns count of new queue items created.
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}[INJECT PROJECT]")
    print(f"  project_id    : {project_id}")
    print(f"  province      : {province}")
    print(f"  budget        : {budget:,} บาท")
    print(f"  announce_type : {announce_type}")
    if project_name:
        print(f"  project_name  : {project_name}")
    if dept_name:
        print(f"  dept_name     : {dept_name}")

    if dry_run:
        print("  → DRY RUN — ไม่ได้ write จริง")
        return 0

    init_schema()
    store = SubscriptionStore()

    # Step 1: canonical registry (idempotent)
    store.record_project_seen(
        project_id    = project_id,
        announce_type = announce_type,
        province      = province,
        budget        = budget,
        project_name  = project_name,
        dept_name     = dept_name,
    )
    print(f"  → projects_seen recorded ✅")

    # Step 2: match against subscriptions → notification_queue
    project = {
        "project_id":    project_id,
        "province":      province,
        "announce_type": announce_type,
        "budget":        budget,
    }
    queued = store.enqueue_notifications(project)

    if queued:
        print(f"  → {queued} notification(s) enqueued ✅")
    else:
        # Diagnose why 0 matched
        conn = __import__("Sebastian_Customer_DB", fromlist=["get_connection"]).get_connection()
        subs = conn.execute("""
            SELECT c.line_user_id, sp.province
            FROM subscriptions s
            JOIN customers c ON c.id = s.customer_id
            JOIN subscription_provinces sp ON sp.subscription_id = s.id
            WHERE s.active=1 AND c.active=1
        """).fetchall()
        conn.close()
        if not subs:
            print("  → 0 enqueued — ไม่มี customer/subscription ใน DB")
            print("     แก้: รัน --line-id U... --provinces <province> ก่อน")
        else:
            provinces_in_db = sorted(set(r["province"] for r in subs))
            print(f"  → 0 enqueued — province='{province}' ไม่ตรงกับ subscription ใดเลย")
            print(f"     subscriptions ที่มีอยู่: {provinces_in_db}")
            print(f"     แก้: เพิ่ม province '{province}' ด้วย --line-id U... --provinces {province}")

    pending = store.get_pending_queue()
    print(f"\nPending queue: {len(pending)} item(s)")
    for item in pending[:3]:
        print(f"  queue_id={item['id']} project={item['project_id']} → {item['line_user_id']}")
    if len(pending) > 3:
        print(f"  ... and {len(pending)-3} more")

    if queued:
        print("\nพร้อมแล้ว ✅")
        print("  ลำดับถัดไป:")
        print("  1. python scripts/Sebastian_LINE_Sender.py --dry-run  (ดู message)")
        print("  2. python scripts/Sebastian_LINE_Sender.py             (send จริง)")

    return queued


# ── Auto-seed from rss_queue ──────────────────────────────────────────────────

def auto_seed_from_queue(provinces: list[str], limit: int = 3) -> int:
    """Find matching items from rss_queue and inject. Returns count seeded."""
    queue_path = Path(__file__).parent.parent / "data" / "rss_queue.json"
    if not queue_path.exists():
        return 0
    try:
        items = json.loads(queue_path.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = items.get("items", [])
    except Exception as e:
        print(f"  (auto-seed skipped: {e})")
        return 0

    seeded = 0
    for item in items:
        province = item.get("province", "")
        if province not in provinces:
            continue
        pid = item.get("project_id") or item.get("projectId", "")
        if not pid:
            continue
        n = inject_project(
            project_id    = pid,
            province      = province,
            budget        = item.get("budget", 0) or 0,
            announce_type = item.get("announce_type", "D0"),
            dry_run       = False,
        )
        if n:
            seeded += 1
        if seeded >= limit:
            break
    return seeded


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Synthetic notification injection harness for BMS self-notify testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Customer seed flags
    parser.add_argument("--line-id",   help="LINE user ID (U...) จาก LINE Developers Console")
    parser.add_argument("--provinces", nargs="+", default=["นครพนม", "บึงกาฬ"],
                        help="Provinces for subscription (default: นครพนม บึงกาฬ)")

    # Project inject flags
    parser.add_argument("--project-id",    help="Inject specific project_id into projects_seen")
    parser.add_argument("--province",      help="Province for injected project")
    parser.add_argument("--budget",        type=int, default=0, help="Budget in baht (default: 0)")
    parser.add_argument("--announce-type", default="D0", help="Announce type (default: D0)")
    parser.add_argument("--project-name",  default="", help="Project name (optional, low-medium trust)")
    parser.add_argument("--dept-name",     default="", help="Department name (optional)")

    # Common
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")

    args = parser.parse_args()

    if not args.line_id and not args.project_id:
        parser.print_help()
        sys.exit(1)

    if args.line_id and not args.line_id.startswith("U"):
        print("ERROR: LINE user ID ต้องขึ้นต้นด้วย 'U'")
        sys.exit(1)

    if args.project_id and not args.province:
        print("ERROR: --project-id ต้องระบุ --province ด้วย")
        sys.exit(1)

    # Mode 1: seed customer
    if args.line_id:
        seed_customer(args.line_id, args.provinces, dry_run=args.dry_run)

    # Mode 2: inject specific project
    if args.project_id:
        inject_project(
            project_id    = args.project_id,
            province      = args.province,
            budget        = args.budget,
            announce_type = args.announce_type,
            project_name  = args.project_name,
            dept_name     = args.dept_name,
            dry_run       = args.dry_run,
        )
    elif args.line_id and not args.dry_run:
        # Auto-seed from rss_queue if no specific project given
        print("\n[AUTO-SEED] ค้นหา project จาก rss_queue ที่ตรงกับ provinces...")
        n = auto_seed_from_queue(args.provinces)
        if n == 0:
            print(f"  ไม่พบ project จาก {args.provinces} ใน rss_queue")
            print("  ใช้ --project-id <id> --province <province> เพื่อ inject manual")
