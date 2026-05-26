"""
queue_health.py — Export queue age + ingestion state snapshot
Output: data/queue_health_snapshot.json
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

ROOT        = Path(__file__).parent.parent
QUEUE_FILE  = ROOT / "data" / "rss_queue.json"
STATE_FILE  = ROOT / "data" / "api_ingestion_state.json"
HISTORY_FILE = ROOT / "data" / "ingestion_run_history.json"
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

    # Rolling metrics from last 5 runs (EWMA-lite: short window, non-stationary env)
    history = []
    if HISTORY_FILE.exists():
        try:
            raw = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            history = raw if isinstance(raw, list) else []
        except Exception:
            history = []
    recent = history[-5:] if len(history) >= 5 else history

    if recent:
        avg_processed  = sum(r.get("processed_count", 0) for r in recent) / len(recent)
        early_stop_cnt = sum(1 for r in recent if r.get("early_stop"))
        success_rate   = avg_processed / 15  # fraction of limit achieved
    else:
        avg_processed  = 15 * 0.8
        early_stop_cnt = 0
        success_rate   = 0.8  # bootstrap assumption

    RUNS_PER_HOUR    = 2
    effective_per_hr = RUNS_PER_HOUR * avg_processed
    drain_eta_hours  = round(len(queue) / effective_per_hr, 1) if queue and effective_per_hr > 0 else 0.0

    # drain_eta_confidence
    if len(recent) < 3:
        drain_confidence = "low"
    elif early_stop_cnt > 0 or success_rate < 0.6:
        drain_confidence = "low"
    elif early_stop_cnt == 0 and success_rate >= 0.9:
        drain_confidence = "high"
    else:
        drain_confidence = "medium"

    snap = {
        "generated_at":            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queue_depth":             len(queue),
        "oldest_item_age_minutes": round(oldest_min, 1),
        "oldest_item_queued_at":   oldest_ts,
        "newest_item_queued_at":   newest_ts,
        "queue_by_type":           dict(type_counts),
        "drain_eta_hours":         drain_eta_hours,
        "drain_eta_confidence":    drain_confidence,
        "recent_runs_window":      len(recent),
        "recent_success_rate":     round(success_rate, 2),
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
