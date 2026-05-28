"""
Sebastian_RSS_Notifier.py — RSS → notification classifier/enqueuer

Architecture plane: sits between RSS Scraper and LINE Sender

  RSS Scraper   → discover events → rss_queue.json (append-only discovery log)
  RSS Notifier  → classify province + confidence → enqueue notifications (THIS FILE)
  LINE Sender   → deliver notifications → LINE push API

Design:
  - rss_queue.json = immutable discovery log — no processed flag added
  - projects_seen  = natural dedup via INSERT OR IGNORE (idempotent, replay-safe)
  - Province classification: wrapper heuristic over province_extractor
      if province in TARGET_PROVINCES → confidence="high"
      else → confidence="none" (skip enqueue)
  - confidence_source: structured namespace reserved for future expansion
      current: "title_extract" | "no_evidence"
      future:  "dept_province_map" (when deptId catalog is built)
  - Backfill epoch: items queued before NOTIFIER_EPOCH → is_backfill=True
      → different message label in LINE notification (📦 instead of 🔔)
  - Only D0 announce_type supported in pilot phase

Run: every 5 min via Task Scheduler (BidMaster_RSS_Notifier)
     or manually: python scripts/Sebastian_RSS_Notifier.py [--dry-run]
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import SubscriptionStore, init_schema, _now

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_PROVINCES = {"นครพนม", "บึงกาฬ"}
NOTIFY_TYPES     = {"D0"}          # pilot: announce only (not winner W0)
MIN_CONFIDENCE   = "high"          # pilot gate — only enqueue high-confidence

RSS_QUEUE_PATH   = Path(__file__).parent.parent / "data" / "rss_queue.json"
EPOCH_PATH       = Path(__file__).parent.parent / "data" / "rss_notifier_epoch.txt"
LOG_DIR          = Path(__file__).parent.parent / "logs" / "rss_notifier"
TZ_TH            = timezone(timedelta(hours=7))


# ── Province classification ───────────────────────────────────────────────────

def classify_province(title: str, dept_id: str = "") -> dict:
    """
    Wrapper heuristic over province_extractor.
    Returns:
      {"province": str, "confidence": str, "confidence_source": str}

    confidence: "high" | "none"
    confidence_source: "title_extract" | "no_evidence"
      (reserved namespace — expand with "dept_province_map" when deptId catalog built)

    Asymmetric error design (pilot phase):
      - False positives from wrong provinces → harmless (no subscription matches)
      - Only TARGET_PROVINCES have subscribers → gate = implicit false-positive filter
    """
    try:
        from province_extractor import extract_province
        province = extract_province(title)
    except Exception:
        province = ""

    if province in TARGET_PROVINCES:
        return {
            "province":          province,
            "confidence":        "high",
            "confidence_source": "title_extract",
        }
    return {
        "province":          province,
        "confidence":        "none",
        "confidence_source": "no_evidence",
    }


# ── Notifier epoch ────────────────────────────────────────────────────────────

def get_notifier_epoch() -> str:
    """
    Return ISO timestamp of first notifier run.
    Items queued before this epoch → is_backfill=True.
    Creates epoch file on first call.
    """
    if EPOCH_PATH.exists():
        return EPOCH_PATH.read_text(encoding="utf-8").strip()
    epoch = datetime.now(TZ_TH).isoformat(timespec="seconds")
    EPOCH_PATH.write_text(epoch, encoding="utf-8")
    return epoch


def is_backfill_item(queued_at: str, epoch: str) -> bool:
    """Item queued before notifier epoch = was already 'old' when notifier started."""
    return queued_at < epoch


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RSS notification classifier/enqueuer")
    parser.add_argument("--dry-run", action="store_true",
                        help="Classify and log without writing to DB")
    args = parser.parse_args()
    dry_run = args.dry_run

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"notifier_{datetime.now().strftime('%Y%m%d')}.log"

    def log(msg: str):
        line = f"[{_now()}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    mode = "DRY RUN" if dry_run else "LIVE"
    log(f"=== RSS Notifier start mode={mode} ===")

    # Load rss_queue
    if not RSS_QUEUE_PATH.exists():
        log("rss_queue.json not found — exit")
        return

    try:
        items = json.loads(RSS_QUEUE_PATH.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = items.get("items", [])
    except Exception as e:
        log(f"ABORT: failed to load rss_queue.json: {e}")
        return

    # Filter to notify-eligible types
    eligible = [i for i in items if i.get("anounce_type", "") in NOTIFY_TYPES]
    log(f"rss_queue: {len(items)} total → {len(eligible)} eligible ({', '.join(NOTIFY_TYPES)})")

    if not eligible:
        log("No eligible items — exit")
        return

    epoch = get_notifier_epoch()
    log(f"Notifier epoch: {epoch}")

    if not dry_run:
        init_schema()
        store = SubscriptionStore()

    stats = {"scanned": 0, "no_province": 0, "enqueued": 0, "skipped_dedup": 0}

    for item in eligible:
        project_id    = item.get("projectId") or item.get("project_id", "")
        title         = item.get("title", "")
        dept_id       = item.get("deptId", "")
        announce_type = item.get("anounce_type", "D0")
        queued_at     = item.get("queued_at", "")
        budget        = int(item.get("budget", 0) or 0)

        if not project_id:
            continue

        stats["scanned"] += 1
        classification = classify_province(title, dept_id)

        if classification["confidence"] != "high":
            stats["no_province"] += 1
            continue

        province   = classification["province"]
        backfill   = is_backfill_item(queued_at, epoch)
        short_title = title[:60] + ("…" if len(title) > 60 else "")

        if dry_run:
            label = "BACKFILL" if backfill else "LIVE"
            log(f"  [{label}] {project_id} province={province} title={short_title}")
            stats["enqueued"] += 1
            continue

        store.record_project_seen(
            project_id           = project_id,
            announce_type        = announce_type,
            province             = province,
            budget               = budget,
            project_name         = title,
            dept_id              = dept_id,
            dept_name            = "",
            extraction_confidence = classification["confidence"],
            source               = "rss",
        )

        n = store.enqueue_notifications({
            "project_id":          project_id,
            "province":            province,
            "announce_type":       announce_type,
            "budget":              budget,
            "project_name":        title,
            "dept_name":           "",
            "extraction_confidence": classification["confidence"],
            "is_backfill":         backfill,
            "source_stage":        "rss_provisional",
        }, min_confidence=MIN_CONFIDENCE)

        if n > 0:
            stats["enqueued"] += 1
            label = "BACKFILL" if backfill else "LIVE"
            log(f"  [{label}] enqueued {n}x {project_id} province={province}")
        else:
            stats["skipped_dedup"] += 1

    log(
        f"Done — scanned={stats['scanned']} "
        f"no_province={stats['no_province']} "
        f"enqueued={stats['enqueued']} "
        f"dedup_skip={stats['skipped_dedup']}"
    )
    log("=== RSS Notifier done ===")


if __name__ == "__main__":
    main()
