"""
Sebastian_Enrichment_Worker.py — Enrichment Plane (2026-05-29)

Role: Take pending project_locations → enrich via eGP API → enqueue notification

  RSS Notifier  → project_locations(pending)
  THIS WORKER   → getProcurementDetail → hard location → enqueue if target province
  LINE Sender   → deliver notification

Design (ChatGPT-confirmed 2026-05-29):
  - Batch: 20 items/run to stay within eGP rate limit (100 req/120s)
  - Sleep: 1.5s between projects → 2 calls/1.5s ≈ 1.3 req/s/type, safe
  - No retry ladder yet — enrichment_attempts tracks debug signal only
  - Enrich ALL projects (not just target) — build canonical intelligence layer
  - WAF downtime: skip run when api_state != HEALTHY

Run: every 2 min via systemd timer (bms-enrichment-worker)
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import SubscriptionStore, init_schema, get_connection, _now, _now_plus

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_PROVINCES  = {"นครพนม", "บึงกาฬ"}
BATCH_SIZE        = 20
SLEEP_BETWEEN_SEC = 1.5
RETRY_DELAY_MIN   = 30
API_STATE_PATH    = Path(__file__).parent.parent / "data" / "api_ingestion_state.json"
LOG_DIR           = Path(__file__).parent.parent / "logs" / "enrichment_worker"
TZ_TH             = timezone(timedelta(hours=7))

MOI_PROVINCE_MAP = {
    "38": "บึงกาฬ",
    "48": "นครพนม",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _api_state() -> str:
    try:
        if API_STATE_PATH.exists():
            return json.loads(API_STATE_PATH.read_text(encoding="utf-8-sig")).get("api_state", "UNKNOWN")
    except Exception:
        pass
    return "UNKNOWN"


def _enrich(project_id: str) -> dict | None:
    try:
        from process5_http_client import get_procurement_detail
        data = get_procurement_detail(project_id)
        if not data.get("valid"):
            return None
        province_moi_id = str(data.get("province_moi_id") or "")
        province_name   = MOI_PROVINCE_MAP.get(province_moi_id[:2], "")
        lat = data.get("latitude") or ""
        lng = data.get("longitude") or ""
        return {
            "province_moi_id": province_moi_id,
            "district_moi_id": str(data.get("district_moi_id") or ""),
            "moi_name":        data.get("moi_name") or "",
            "province_name":   province_name,
            "latitude":        str(lat)[:200],
            "longitude":       str(lng)[:200],
        }
    except Exception:
        return None


def _save_success(project_id: str, loc: dict) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute("""
            UPDATE project_locations
            SET province_moi_id=?, district_moi_id=?, moi_name=?,
                province_name=?, latitude=?, longitude=?,
                location_confidence='hard', enrichment_status='success',
                next_retry_at=NULL, enriched_at=?,
                enrichment_attempts=enrichment_attempts+1
            WHERE project_id=?
        """, (loc["province_moi_id"], loc["district_moi_id"], loc["moi_name"],
              loc["province_name"], loc["latitude"], loc["longitude"],
              now, project_id))


def _save_retry(project_id: str) -> None:
    with get_connection() as conn:
        conn.execute("""
            UPDATE project_locations
            SET next_retry_at=?, enrichment_attempts=enrichment_attempts+1
            WHERE project_id=?
        """, (_now_plus(RETRY_DELAY_MIN), project_id))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"enrichment_{datetime.now().strftime('%Y%m%d')}.log"

    def log(msg: str):
        line = f"[{_now()}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    api = _api_state()
    log(f"=== Enrichment Worker start api_state={api} ===")

    if api != "HEALTHY":
        log("API not HEALTHY — skip run")
        log("=== Enrichment Worker done (skipped) ===")
        return

    init_schema()
    store = SubscriptionStore()
    now   = _now()

    # Take batch of pending items
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT pl.project_id, ps.announce_type, ps.budget,
                   ps.project_name, ps.dept_name, pl.enrichment_attempts
            FROM project_locations pl
            LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE pl.enrichment_status = 'pending'
              AND (pl.next_retry_at IS NULL OR pl.next_retry_at <= ?)
            ORDER BY pl.enrichment_attempts ASC, pl.created_at ASC
            LIMIT ?
        """, (now, BATCH_SIZE)).fetchall()

    rows = [dict(r) for r in rows]
    log(f"Batch: {len(rows)} pending items to enrich")

    if not rows:
        log("No pending items — exit")
        log("=== Enrichment Worker done ===")
        return

    stats = {"enriched": 0, "failed": 0, "target_hit": 0, "enqueued": 0, "dedup": 0}

    for i, row in enumerate(rows):
        pid = row["project_id"]

        loc = _enrich(pid)

        if not loc:
            _save_retry(pid)
            stats["failed"] += 1
            log(f"  [{i+1}/{len(rows)}] FAIL {pid} attempts={row['enrichment_attempts']+1}")
        else:
            _save_success(pid, loc)
            stats["enriched"] += 1
            province = loc["province_name"]
            tambon   = loc["moi_name"]
            log(f"  [{i+1}/{len(rows)}] OK {pid} province={province or '?'} tambon={tambon}")

            if province in TARGET_PROVINCES:
                stats["target_hit"] += 1
                announce_type = row.get("announce_type") or "D0"
                budget        = int(row.get("budget") or 0)
                project_name  = row.get("project_name") or ""

                n = store.enqueue_notifications({
                    "project_id":           pid,
                    "province":             province,
                    "announce_type":        announce_type,
                    "budget":               budget,
                    "project_name":         project_name,
                    "dept_name":            row.get("dept_name") or "",
                    "extraction_confidence": "high",
                    "is_backfill":          False,
                    "source_stage":         "api_enriched",
                }, min_confidence="high")

                if n > 0:
                    stats["enqueued"] += 1
                    log(f"    → ENQUEUED {n}x province={province} tambon={tambon}")
                else:
                    stats["dedup"] += 1

        # Rate limit guard
        if i < len(rows) - 1:
            time.sleep(SLEEP_BETWEEN_SEC)

    # Summary
    with get_connection() as conn:
        total_pending = conn.execute(
            "SELECT COUNT(*) FROM project_locations WHERE enrichment_status='pending'"
        ).fetchone()[0]

    log(
        f"Done — enriched={stats['enriched']} failed={stats['failed']} "
        f"target_hit={stats['target_hit']} enqueued={stats['enqueued']} "
        f"dedup={stats['dedup']} | queue_remaining={total_pending}"
    )
    log("=== Enrichment Worker done ===")


if __name__ == "__main__":
    main()
