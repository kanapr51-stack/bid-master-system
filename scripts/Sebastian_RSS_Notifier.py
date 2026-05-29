"""
Sebastian_RSS_Notifier.py — RSS Discovery Plane (v3, 2026-05-29)

Role: Discovery ONLY — no API calls, no filtering, no enqueue.

  RSS Scraper  → rss_queue.json
  RSS Notifier → record project_seen + insert project_locations(pending)  ← THIS FILE
  Enrichment Worker → enrich location → filter → enqueue notification

Separation rationale (ChatGPT-confirmed 2026-05-29):
  Discovery Plane was blocked by Enrichment Plane when both lived in one process.
  Rate limit on eGP API caused 232/260 items to fail silently.
  Separating planes means WAF downtime / rate limits never affect discovery latency.

Run: every 5 min via systemd timer (bms-rss-notifier)
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import SubscriptionStore, init_schema, get_connection, _now

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────

NOTIFY_TYPES   = {"D0"}
RSS_QUEUE_PATH = Path(__file__).parent.parent / "data" / "rss_queue.json"
EPOCH_PATH     = Path(__file__).parent.parent / "data" / "rss_notifier_epoch.txt"
LOG_DIR        = Path(__file__).parent.parent / "logs" / "rss_notifier"
TZ_TH          = timezone(timedelta(hours=7))


# ── Epoch ─────────────────────────────────────────────────────────────────────

def get_notifier_epoch() -> str:
    if EPOCH_PATH.exists():
        return EPOCH_PATH.read_text(encoding="utf-8").strip()
    epoch = datetime.now(TZ_TH).isoformat(timespec="seconds")
    EPOCH_PATH.write_text(epoch, encoding="utf-8")
    return epoch


def is_backfill_item(queued_at: str, epoch: str) -> bool:
    return queued_at < epoch


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"notifier_{datetime.now().strftime('%Y%m%d')}.log"

    def log(msg: str):
        line = f"[{_now()}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log("=== RSS Notifier (discovery-only) start ===")

    init_schema()
    epoch = get_notifier_epoch()

    if not RSS_QUEUE_PATH.exists():
        log("rss_queue.json not found — exit")
        return

    try:
        items = json.loads(RSS_QUEUE_PATH.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = items.get("items", [])
    except Exception as e:
        log(f"ABORT: {e}")
        return

    eligible = [i for i in items if i.get("anounce_type", "") in NOTIFY_TYPES]
    log(f"rss_queue: {len(items)} total → {len(eligible)} D0 eligible")

    store = SubscriptionStore()
    stats = {"scanned": 0, "new_pending": 0, "already_known": 0}

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

        # Register in canonical registry (idempotent)
        store.record_project_seen(
            project_id            = project_id,
            announce_type         = announce_type,
            province              = "",
            budget                = budget,
            project_name          = title,
            dept_id               = dept_id,
            dept_name             = "",
            extraction_confidence = "unknown",
            source                = "rss",
        )

        # Insert pending location record (INSERT OR IGNORE — idempotent)
        backfill = is_backfill_item(queued_at, epoch)
        now = _now()
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO project_locations "
                "(project_id, location_confidence, enrichment_status, created_at) "
                "VALUES (?, 'unknown', 'pending', ?)",
                (project_id, now),
            )
            if cur.lastrowid and cur.rowcount > 0:
                stats["new_pending"] += 1
            else:
                stats["already_known"] += 1

    log(
        f"Done — scanned={stats['scanned']} "
        f"new_pending={stats['new_pending']} already_known={stats['already_known']}"
    )
    log("=== RSS Notifier done ===")


if __name__ == "__main__":
    main()
