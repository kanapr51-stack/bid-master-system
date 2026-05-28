"""
Sebastian_WAF_Morning_Pulse.py — WAF behavioral characterization pulse

Controlled experiment: canary_1 → unseen_id → canary_2 → summarize → exit
NO auto-resume. Human-in-the-loop decision after reviewing output.

Threshold profile v1_empirical_20260527:
  healthy  : avg_ms < 1000
  degraded : avg_ms > 2500 AND p95/avg < 1.5
  ambiguous: everything else

Output:
  data/waf_pulse_log.ndjson  — per-step records (append-only)
  stdout                     — human-readable summary
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Discord_Notify import load_env, get_credentials, send as discord_send

sys.stdout.reconfigure(encoding="utf-8")

# ── Constants ────────────────────────────────────────────────────────────────

PROCESS5_BASE = "https://process5.gprocurement.go.th"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer":         f"{PROCESS5_BASE}/",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
}
TIMEOUT   = 20   # single request, no retry — clean latency measurement
CANARY_ID = "69039439931"

DATA_DIR  = Path(__file__).parent.parent / "data"
PULSE_LOG = DATA_DIR / "waf_pulse_log.ndjson"
RSS_QUEUE = DATA_DIR / "rss_queue.json"
STATE_FILE = DATA_DIR / "api_ingestion_state.json"

TZ_TH = timezone(timedelta(hours=7))

# Threshold profile — do NOT change without incrementing version label
THRESHOLD_PROFILE = "v1_empirical_20260527"
HEALTHY_AVG_CEIL   = 1000   # ms
DEGRADED_AVG_FLOOR = 2500   # ms
DEGRADED_RATIO_CEIL = 1.5   # p95/avg


# ── Helpers ──────────────────────────────────────────────────────────────────

def now_th() -> str:
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def classify(latency_ms: float) -> tuple[str, dict]:
    """Returns (label, reason_dict). Single-request classification."""
    reason = {
        "latency_ms":     round(latency_ms),
        "threshold_profile": THRESHOLD_PROFILE,
    }
    if latency_ms < HEALTHY_AVG_CEIL:
        reason["matched_rule"] = f"healthy_avg_lt_{HEALTHY_AVG_CEIL}ms"
        return "healthy", reason
    if latency_ms > DEGRADED_AVG_FLOOR:
        reason["matched_rule"] = f"degraded_avg_gt_{DEGRADED_AVG_FLOOR}ms"
        return "degraded", reason
    reason["matched_rule"] = "ambiguous_middle_zone"
    return "ambiguous", reason


def probe_single(project_id: str) -> tuple[float, int, bool]:
    """
    One bare HTTP GET, no retry. Returns (latency_ms, http_status, valid).
    valid = server returned non-empty JSON with flowSeqno/stepId present.
    """
    t0 = time.time()
    try:
        r = requests.get(
            f"{API_BASE}/getProjectDetail",
            params={"projectId": project_id},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        latency_ms = (time.time() - t0) * 1000
        if not r.ok:
            return latency_ms, r.status_code, False
        try:
            body = r.json()
            data = body.get("data", {}) or {}
            valid = bool(data.get("flowSeqno") or data.get("stepId") or data.get("flowId"))
        except Exception:
            valid = False
        return latency_ms, r.status_code, valid
    except requests.Timeout:
        return (time.time() - t0) * 1000, 0, False
    except Exception:
        return (time.time() - t0) * 1000, -1, False


def pick_unseen_id() -> str:
    """Pick first typical unseen ID from RSS queue (not canary, not edge-case dept)."""
    try:
        items = json.loads(RSS_QUEUE.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = items.get("items", [])
        for item in items:
            pid = item.get("project_id") or item.get("projectId", "")
            # Skip canary, short IDs, P-prefixed (pre-TOR), anomalous
            if pid and pid != CANARY_ID and len(pid) >= 11 and not pid.startswith("P"):
                return pid
    except Exception:
        pass
    return "69039196328"  # fallback: known valid D0 from 2026-05-27 run


def classify_sequence(labels: list[str]) -> str:
    """Name the 3-step transition pattern."""
    if labels == ["healthy", "healthy", "healthy"]:
        return "stable_healthy"
    if labels == ["degraded", "degraded", "degraded"]:
        return "persistent_degraded"
    if labels[0] == "healthy" and labels[2] in ("degraded", "ambiguous"):
        if labels[1] in ("degraded", "ambiguous"):
            return "transition_after_novelty"
        return "ambiguous_transition"
    if labels[0] == "healthy" and labels[1] in ("degraded", "ambiguous") and labels[2] == "healthy":
        return "novelty_transient"
    if "ambiguous" in labels and "degraded" not in labels:
        return "ambiguous_healthy_leaning"
    if "ambiguous" in labels:
        return "ambiguous"
    return "mixed_unclear"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ts_run  = datetime.now(TZ_TH).strftime("%Y%m%d_%H%M")
    seq_id  = f"pulse_{ts_run}"
    unseen  = pick_unseen_id()

    steps = [
        ("canary_1", CANARY_ID,  "canary"),
        ("unseen",   unseen,     "unseen"),
        ("canary_2", CANARY_ID,  "canary"),
    ]

    print(f"\n{'='*55}")
    print(f"  WAF Morning Pulse — {seq_id}")
    print(f"  Threshold: {THRESHOLD_PROFILE}")
    print(f"  Unseen ID: {unseen}")
    print(f"{'='*55}\n")

    records = []
    labels  = []

    for step_name, project_id, request_type in steps:
        print(f"[{now_th()}] step={step_name} id={project_id} ...", end=" ", flush=True)
        latency_ms, http_status, valid = probe_single(project_id)
        label, reason = classify(latency_ms)
        labels.append(label)

        record = {
            "ts":               now_th(),
            "sequence_id":      seq_id,
            "step":             step_name,
            "request_type":     request_type,
            "target_id":        project_id,
            "latency_ms":       round(latency_ms),
            "http_status":      http_status,
            "valid_response":   valid,
            "classification":   label,
            "classification_reason": reason,
        }
        records.append(record)

        status_icon = {"healthy": "✅", "degraded": "❌", "ambiguous": "⚠️"}.get(label, "?")
        print(f"{round(latency_ms)}ms  HTTP {http_status}  valid={valid}  → {label} {status_icon}")

        # Inter-step pause — avoid burst
        if step_name != "canary_2":
            time.sleep(3)

    # Summary
    latency_series = [r["latency_ms"] for r in records]
    seq_pattern    = classify_sequence(labels)

    notes_map = {
        "stable_healthy":          "no regime shift observed — safe to consider gradual ramp-up",
        "persistent_degraded":     "WAF degradation persists after silence — extend experiment",
        "transition_after_novelty":"possible regime escalation after novelty interaction",
        "novelty_transient":       "novelty caused temporary spike, regime recovered",
        "ambiguous_transition":    "unclear transition — do not conclude, observe more",
        "ambiguous_healthy_leaning": "likely healthy but ambiguous — proceed cautiously",
        "ambiguous":               "insufficient signal — do not make operational decisions",
        "mixed_unclear":           "mixed signals — manual inspection required",
    }

    summary = {
        "sequence_id":      seq_id,
        "sequence_pattern": seq_pattern,
        "latency_series":   latency_series,
        "classifications":  labels,
        "notes":            notes_map.get(seq_pattern, "see per-step records"),
    }

    print(f"\n{'─'*55}")
    print(f"  Sequence pattern : {seq_pattern}")
    print(f"  Latency series   : {latency_series} ms")
    print(f"  Classifications  : {labels}")
    print(f"  Notes            : {summary['notes']}")
    print(f"{'─'*55}")
    print("\n⚠️  NO auto-action taken. Human decision required.\n")

    # Discord recommendation
    recommendation_map = {
        "stable_healthy":            ("✅ RESUME",  "WAF ปกติ — แนะนำเปิด Queue Processor ได้ (batch เล็กก่อน)"),
        "persistent_degraded":       ("❌ HOLD",    "WAF ยังบล็อกอยู่ — อย่าเพิ่งเปิด Queue Processor"),
        "transition_after_novelty":  ("⚠️ WAIT",   "Regime shift หลัง novelty — รอ observe อีก 1-2 ชั่วโมง"),
        "novelty_transient":         ("⚠️ WAIT",   "Spike ชั่วคราวจาก novelty — ทดสอบ canary เพิ่มก่อน"),
        "ambiguous_transition":      ("⚠️ WAIT",   "Signal ไม่ชัด — ดู pulse รอบถัดไปก่อน"),
        "ambiguous_healthy_leaning": ("⚠️ WAIT",   "น่าจะ healthy แต่ยังไม่ชัดพอ — รออีก 30 นาที"),
        "ambiguous":                 ("⚠️ WAIT",   "Signal ไม่พอ — อย่าตัดสินใจ"),
        "mixed_unclear":             ("⚠️ WAIT",   "ผลผสม — ต้องดู log ละเอียดก่อน"),
    }
    action_label, action_reason = recommendation_map.get(seq_pattern, ("⚠️ WAIT", "Unknown pattern"))

    discord_msg = (
        f"🌅 **WAF Morning Pulse — {seq_id}**\n"
        f"Pattern: `{seq_pattern}`\n"
        f"Latency: `{latency_series[0]}ms → {latency_series[1]}ms → {latency_series[2]}ms`\n"
        f"Classification: `{' → '.join(labels)}`\n\n"
        f"**Recommendation: {action_label}**\n"
        f"{action_reason}"
    )
    try:
        load_env()
        token, ch = get_credentials()
        discord_send(token, ch, discord_msg)
        print("Discord notification sent.")
    except Exception as e:
        print(f"Discord notify failed: {e}")

    # Append per-step records to ndjson log
    with open(PULSE_LOG, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.write(json.dumps({"ts": now_th(), "type": "summary", **summary},
                            ensure_ascii=False) + "\n")

    print(f"Log: {PULSE_LOG}")

    # Update state file: clear needs_revalidation only if healthy confirmed
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if seq_pattern == "stable_healthy":
            state["needs_revalidation"] = False
            state["pulse_result"]       = seq_pattern
            state["last_pulse_at"]      = now_th()
            state["updated_at"]         = now_th()
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=4),
                                  encoding="utf-8")
            print("State: needs_revalidation cleared (stable_healthy confirmed)")
        else:
            state["pulse_result"] = seq_pattern
            state["last_pulse_at"] = now_th()
            state["updated_at"]    = now_th()
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=4),
                                  encoding="utf-8")
            print(f"State: pulse_result={seq_pattern} recorded, needs_revalidation unchanged")
    except Exception as e:
        print(f"State update failed: {e}")


if __name__ == "__main__":
    main()
