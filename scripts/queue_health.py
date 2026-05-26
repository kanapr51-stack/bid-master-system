"""
queue_health.py — Export queue age + ingestion state snapshot
Output: data/queue_health_snapshot.json
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parent.parent
QUEUE_FILE  = ROOT / "data" / "rss_queue.json"
STATE_FILE  = ROOT / "data" / "api_ingestion_state.json"
OUTPUT_FILE = ROOT / "data" / "queue_health_snapshot.json"

def age_minutes(ts_str: str) -> float:
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return 0.0

def classify_health(oldest_min: float, api_state: str) -> str:
    if api_state == "BLOCKED":
        return "BLOCKED"
    if oldest_min > 24 * 60:
        return "INGESTION_FAILURE"
    if oldest_min > 6 * 60:
        return "CRITICAL"
    if oldest_min > 2 * 60:
        return "DEGRADED"
    return "HEALTHY"

def main():
    queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8")) if QUEUE_FILE.exists() else []
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}

    if queue:
        ages = [(item.get("queued_at", ""), age_minutes(item.get("queued_at", ""))) for item in queue]
        oldest_ts, oldest_min = max(ages, key=lambda x: x[1])
        newest_ts, newest_min = min(ages, key=lambda x: x[1])
    else:
        oldest_ts = newest_ts = ""
        oldest_min = newest_min = 0.0

    type_counts = Counter(item.get("anounce_type", "?") for item in queue)
    api_state   = state.get("api_state", "UNKNOWN")
    health      = classify_health(oldest_min, api_state)

    # drain_eta: assumes limit=15 IDs/run, 2 runs/hour, ~80% success rate per run
    RUNS_PER_HOUR     = 2
    IDS_PER_RUN       = 15
    SUCCESS_RATE      = 0.8
    effective_per_hr  = RUNS_PER_HOUR * IDS_PER_RUN * SUCCESS_RATE
    drain_eta_hours   = round(len(queue) / effective_per_hr, 1) if queue else 0.0

    snap = {
        "generated_at":            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queue_depth":             len(queue),
        "oldest_item_age_minutes": round(oldest_min, 1),
        "oldest_item_queued_at":   oldest_ts,
        "newest_item_queued_at":   newest_ts,
        "queue_by_type":           dict(type_counts),
        "drain_eta_hours":         drain_eta_hours,
        "api_state":               api_state,
        "blocked_until":           state.get("blocked_until", ""),
        "last_canary_success":     state.get("last_canary_success", ""),
        "health":                  health,
    }

    OUTPUT_FILE.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(snap, ensure_ascii=False))
    return 0 if health in ("HEALTHY", "BLOCKED") else 1

if __name__ == "__main__":
    sys.exit(main())
