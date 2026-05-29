"""
Sebastian_RSS_Notifier.py — RSS → notification classifier/enqueuer

Architecture (v2, 2026-05-29):
  RSS Scraper   → rss_queue.json (append-only discovery log)
  RSS Notifier  → eGP location enrichment → enqueue notifications (THIS FILE)
  LINE Sender   → deliver → LINE push API

Location enrichment (ChatGPT-confirmed 2026-05-29):
  - Every new project → getProcurementDetail → provinceMoiId/districtMoiId/moiName
  - api_state=HEALTHY  → enrich immediately → confidence='hard' → enqueue
  - api_state=DOWN     → save pending → retry on next HEALTHY window
  - Never enqueue from title regex (confidence='soft') — trust erosion risk
  - 9/1273 title-extract hit rate = evidence title location is unreliable

location_confidence:
  hard    = eGP API (provinceMoiId/districtMoiId/moiName) — gate for notification
  unknown = pending enrichment

Run: every 5 min via systemd timer (bms-rss-notifier)
     or manually: python scripts/Sebastian_RSS_Notifier.py [--dry-run]
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import SubscriptionStore, init_schema, get_connection, _now

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_PROVINCES     = {"นครพนม", "บึงกาฬ"}
NOTIFY_TYPES         = {"D0"}
MAX_LOCATION_RETRIES = 3
PENDING_RETRY_MIN    = 30   # retry pending after N minutes

RSS_QUEUE_PATH  = Path(__file__).parent.parent / "data" / "rss_queue.json"
EPOCH_PATH      = Path(__file__).parent.parent / "data" / "rss_notifier_epoch.txt"
API_STATE_PATH  = Path(__file__).parent.parent / "data" / "api_ingestion_state.json"
LOG_DIR         = Path(__file__).parent.parent / "logs" / "rss_notifier"
TZ_TH           = timezone(timedelta(hours=7))

# MOI province code prefix (2 digits) → province name
MOI_PROVINCE_MAP = {
    "38": "บึงกาฬ",
    "48": "นครพนม",
}


# ── API state ─────────────────────────────────────────────────────────────────

def _api_state() -> str:
    try:
        if API_STATE_PATH.exists():
            return json.loads(API_STATE_PATH.read_text(encoding="utf-8-sig")).get("api_state", "UNKNOWN")
    except Exception:
        pass
    return "UNKNOWN"


def _now_plus_minutes(n: int) -> str:
    return (datetime.now(TZ_TH) + timedelta(minutes=n)).isoformat(timespec="seconds")


# ── Location enrichment ───────────────────────────────────────────────────────

def _enrich_location(project_id: str) -> dict | None:
    """
    Call getProcurementDetail → return location dict or None on fail.
    Returns: {province_moi_id, district_moi_id, moi_name, province_name, lat, lng}
    """
    try:
        from process5_http_client import get_procurement_detail
        data = get_procurement_detail(project_id)
        if not data.get("valid"):
            return None

        province_moi_id = data.get("province_moi_id", "") or ""
        district_moi_id = data.get("district_moi_id", "") or ""
        moi_name        = data.get("moi_name", "") or ""
        lat             = data.get("latitude", "") or ""
        lng             = data.get("longitude", "") or ""

        # Derive province name from MOI code prefix
        province_name = MOI_PROVINCE_MAP.get(str(province_moi_id)[:2], "")

        return {
            "province_moi_id": province_moi_id,
            "district_moi_id": district_moi_id,
            "moi_name":        moi_name,
            "province_name":   province_name,
            "latitude":        str(lat)[:200] if lat else "",
            "longitude":       str(lng)[:200] if lng else "",
        }
    except Exception:
        return None


def _save_location(project_id: str, loc: dict | None, status: str,
                   next_retry_at: str | None = None) -> None:
    """Upsert project_locations record."""
    now = _now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT project_id FROM project_locations WHERE project_id=?",
            (project_id,)
        ).fetchone()

        if existing:
            if loc and status == "success":
                conn.execute("""
                    UPDATE project_locations
                    SET province_moi_id=?, district_moi_id=?, moi_name=?,
                        province_name=?, latitude=?, longitude=?,
                        location_confidence='hard', enrichment_status='success',
                        next_retry_at=NULL, enriched_at=?
                    WHERE project_id=?
                """, (loc["province_moi_id"], loc["district_moi_id"], loc["moi_name"],
                      loc["province_name"], loc["latitude"], loc["longitude"],
                      now, project_id))
            else:
                conn.execute("""
                    UPDATE project_locations
                    SET enrichment_status=?, next_retry_at=?
                    WHERE project_id=?
                """, (status, next_retry_at, project_id))
        else:
            if loc and status == "success":
                conn.execute("""
                    INSERT INTO project_locations
                    (project_id, province_moi_id, district_moi_id, moi_name,
                     province_name, latitude, longitude,
                     location_confidence, enrichment_status, enriched_at, created_at)
                    VALUES (?,?,?,?,?,?,?,'hard','success',?,?)
                """, (project_id, loc["province_moi_id"], loc["district_moi_id"],
                      loc["moi_name"], loc["province_name"],
                      loc["latitude"], loc["longitude"], now, now))
            else:
                conn.execute("""
                    INSERT INTO project_locations
                    (project_id, location_confidence, enrichment_status,
                     next_retry_at, created_at)
                    VALUES (?,'unknown',?,?,?)
                """, (project_id, status, next_retry_at, now))


def _get_cached_location(project_id: str) -> dict | None:
    """Return location row if enrichment_status='success', else None."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_locations WHERE project_id=? AND enrichment_status='success'",
                (project_id,)
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


# ── Notifier epoch ────────────────────────────────────────────────────────────

def get_notifier_epoch() -> str:
    if EPOCH_PATH.exists():
        return EPOCH_PATH.read_text(encoding="utf-8").strip()
    epoch = datetime.now(TZ_TH).isoformat(timespec="seconds")
    EPOCH_PATH.write_text(epoch, encoding="utf-8")
    return epoch


def is_backfill_item(queued_at: str, epoch: str) -> bool:
    return queued_at < epoch


# ── Pending location retry loop ───────────────────────────────────────────────

def process_pending_locations(store: SubscriptionStore, epoch: str, log) -> dict:
    """
    Retry pending location enrichments when api_state=HEALTHY.
    Called at start of each notifier run — reuses same timer, no new worker.
    Returns stats dict.
    """
    stats = {"retried": 0, "promoted": 0, "still_pending": 0}

    if _api_state() != "HEALTHY":
        return stats

    now = _now()
    try:
        with get_connection() as conn:
            pending = conn.execute("""
                SELECT pl.project_id, ps.announce_type, ps.budget,
                       ps.project_name, ps.dept_name
                FROM project_locations pl
                LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
                WHERE pl.enrichment_status = 'pending'
                  AND (pl.next_retry_at IS NULL OR pl.next_retry_at <= ?)
                LIMIT 20
            """, (now,)).fetchall()
    except Exception as e:
        log(f"  pending_retry: query error {e}")
        return stats

    for row in pending:
        pid = row["project_id"]
        stats["retried"] += 1

        loc = _enrich_location(pid)
        if not loc:
            _save_location(pid, None, "pending", _now_plus_minutes(PENDING_RETRY_MIN))
            stats["still_pending"] += 1
            continue

        # Got hard location
        _save_location(pid, loc, "success")
        province = loc.get("province_name", "")

        if province not in TARGET_PROVINCES:
            log(f"  pending_retry: {pid} province={province or '?'} not in target → skip")
            continue

        announce_type = row["announce_type"] or "D0"
        budget        = int(row["budget"] or 0)
        project_name  = row["project_name"] or ""
        backfill      = is_backfill_item(row["project_id"], epoch)  # use project_id as proxy

        n = store.enqueue_notifications({
            "project_id":           pid,
            "province":             province,
            "announce_type":        announce_type,
            "budget":               budget,
            "project_name":         project_name,
            "dept_name":            row["dept_name"] or "",
            "extraction_confidence": "high",
            "is_backfill":          backfill,
            "source_stage":         "api_enriched",
        }, min_confidence="high")

        if n > 0:
            stats["promoted"] += 1
            log(f"  pending_retry: PROMOTED {pid} province={province} tambon={loc['moi_name']}")
        else:
            log(f"  pending_retry: {pid} already enqueued (dedup)")

    return stats


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RSS notification classifier/enqueuer v2")
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
    api  = _api_state()
    log(f"=== RSS Notifier start mode={mode} api_state={api} ===")

    if not dry_run:
        init_schema()
        store = SubscriptionStore()

    epoch = get_notifier_epoch()
    log(f"Notifier epoch: {epoch}")

    # ── Pass 1: retry pending locations from previous runs ──────────────────
    if not dry_run:
        p = process_pending_locations(store, epoch, log)
        if p["retried"]:
            log(f"Pending retry — retried={p['retried']} promoted={p['promoted']} still_pending={p['still_pending']}")

    # ── Pass 2: process new RSS items ────────────────────────────────────────
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

    eligible = [i for i in items if i.get("anounce_type", "") in NOTIFY_TYPES]
    log(f"rss_queue: {len(items)} total → {len(eligible)} eligible ({', '.join(NOTIFY_TYPES)})")

    if not eligible:
        log("No eligible items — exit")
        return

    stats = {"scanned": 0, "cached_hit": 0, "enriched": 0,
             "pending_new": 0, "enqueued": 0, "skipped_dedup": 0, "not_target": 0}

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

        if dry_run:
            loc = _enrich_location(project_id) if api == "HEALTHY" else None
            province = loc.get("province_name", "") if loc else "(api_down)"
            tambon   = loc.get("moi_name", "") if loc else ""
            log(f"  DRY {project_id} province={province} tambon={tambon} title={title[:50]}")
            continue

        # Always record in projects_seen (dedup registry)
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

        # Check location cache first
        cached = _get_cached_location(project_id)
        if cached:
            stats["cached_hit"] += 1
            province = cached.get("province_name", "")
        elif api == "HEALTHY":
            # Enrich now
            loc = _enrich_location(project_id)
            if loc:
                _save_location(project_id, loc, "success")
                province = loc.get("province_name", "")
                stats["enriched"] += 1
                log(f"  enriched: {project_id} province={province} tambon={loc['moi_name']}")
            else:
                _save_location(project_id, None, "pending", _now_plus_minutes(PENDING_RETRY_MIN))
                stats["pending_new"] += 1
                log(f"  pending: {project_id} (enrich failed, retry in {PENDING_RETRY_MIN}m)")
                continue
        else:
            # API DOWN — queue for enrichment later
            existing = _get_cached_location(project_id)
            if not existing:
                _save_location(project_id, None, "pending", _now_plus_minutes(PENDING_RETRY_MIN))
            stats["pending_new"] += 1
            continue

        # Filter by target provinces
        if province not in TARGET_PROVINCES:
            stats["not_target"] += 1
            continue

        backfill = is_backfill_item(queued_at, epoch)
        n = store.enqueue_notifications({
            "project_id":           project_id,
            "province":             province,
            "announce_type":        announce_type,
            "budget":               budget,
            "project_name":         title,
            "dept_name":            "",
            "extraction_confidence": "high",
            "is_backfill":          backfill,
            "source_stage":         "api_enriched",
        }, min_confidence="high")

        label = "BACKFILL" if backfill else "LIVE"
        if n > 0:
            stats["enqueued"] += 1
            log(f"  [{label}] enqueued {n}x {project_id} province={province}")
        else:
            stats["skipped_dedup"] += 1

    log(
        f"Done — scanned={stats['scanned']} "
        f"cache_hit={stats['cached_hit']} enriched={stats['enriched']} "
        f"pending_new={stats['pending_new']} not_target={stats['not_target']} "
        f"enqueued={stats['enqueued']} dedup_skip={stats['skipped_dedup']}"
    )
    log("=== RSS Notifier done ===")


if __name__ == "__main__":
    main()
