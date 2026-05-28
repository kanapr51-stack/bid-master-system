"""
Sebastian_RSS_Probe.py — Lightweight RSS availability probe (Era B telemetry)

Runs every 30 min via Task Scheduler (BidMaster_RSS_Probe).
Probes 3 departments: 2 stable canary + 1 rotating deterministic selection.
Output: data/rss_availability_log.ndjson (append-only)

Schema v1 (frozen 2026-05-27):
  ts, era, probe_version, dept_id, http_status, latency_sec,
  item_count, empty_feed, parse_ok, error_type, raw_failure_reason
"""
import json
import os
import re
import sys
import time
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

from curl_cffi import requests as cffi_requests

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

# ── Constants ────────────────────────────────────────────────────────────────

RSS_URL      = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
DATA_DIR     = Path(__file__).parent.parent / "data"
LOG_DIR      = Path(__file__).parent.parent / "logs" / "rss_probe"

AVAIL_LOG    = DATA_DIR / "rss_availability_log.ndjson"
LOCK_FILE    = DATA_DIR / "rss_probe.lock"
CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"

PROBE_VERSION = "v1"
ERA           = "B"
TIMEOUT       = 15  # seconds — fail-fast

# 2 stable canary departments (high-traffic, validated 2026-05-27)
CANARY_DEPTS = ["0307", "0708"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}

TZ_TH = timezone(timedelta(hours=7))


# ── Helpers ──────────────────────────────────────────────────────────────────

def now_th() -> str:
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def decode_thai(raw: bytes) -> str:
    for enc in ["tis-620", "cp874", "utf-8"]:
        try:
            text = raw.decode(enc)
            if any("฀" <= c <= "๿" for c in text):
                return text
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_item_count(xml_text: str) -> int:
    return len(re.findall(r"<item>", xml_text))


def rotating_dept() -> str:
    """Deterministic per 30-min slot — same dept within a slot, rotates across slots."""
    try:
        catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        candidates = [d for d in catalog.keys() if d not in CANARY_DEPTS]
        if not candidates:
            return "0101"
        slot = int(time.time()) // 1800  # changes every 30 min
        return random.Random(slot).choice(candidates)
    except Exception:
        return "0101"


def classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "timed out" in msg or "timeout" in msg:
        return "timeout"
    if "tls" in msg or "ssl" in msg or "certificate" in msg:
        return "tls_error"
    if "connection" in msg:
        return "connection_error"
    return "unknown_error"


# ── Core probe ───────────────────────────────────────────────────────────────

def probe_dept(dept_id: str) -> dict:
    """Probe single dept. Separates transport success from semantic success."""
    ts = now_th()
    t_start = time.time()
    http_status      = None
    latency_sec      = None
    item_count       = 0
    empty_feed       = True
    parse_ok         = False
    error_type       = None
    raw_failure_reason = None

    try:
        r = cffi_requests.get(
            RSS_URL,
            params={"deptId": dept_id, "anounceType": "D0"},
            headers=HEADERS,
            timeout=TIMEOUT,
            impersonate="chrome120",
        )
        latency_sec = round(time.time() - t_start, 3)
        http_status = r.status_code

        if r.status_code == 200:
            try:
                text = decode_thai(r.content)
                item_count = parse_item_count(text)
                empty_feed = item_count == 0
                parse_ok   = True
            except Exception as e:
                # HTTP 200 but parse fail → semantic failure
                parse_ok           = False
                error_type         = "parse_error"
                raw_failure_reason = str(e)
        else:
            error_type         = f"http_{r.status_code}"
            raw_failure_reason = f"HTTP {r.status_code}"

    except Exception as e:
        latency_sec        = round(time.time() - t_start, 3)
        error_type         = classify_error(e)
        raw_failure_reason = str(e)

    return {
        "ts":                 ts,
        "era":                ERA,
        "probe_version":      PROBE_VERSION,
        "dept_id":            dept_id,
        "http_status":        http_status,
        "latency_sec":        latency_sec,
        "item_count":         item_count,
        "empty_feed":         empty_feed,
        "parse_ok":           parse_ok,
        "error_type":         error_type,
        "raw_failure_reason": raw_failure_reason,
    }


# ── Lock ─────────────────────────────────────────────────────────────────────

def acquire_lock() -> bool:
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age < 300:  # stale after 5 min
            return False
        LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock():
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Redirect stdout/stderr to log file (skip in CI)
    if not os.environ.get("CI", "").lower() in ("true", "1"):
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"probe_{ts_tag}.log"
        log_fh = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = log_fh
        sys.stderr = log_fh

    if not acquire_lock():
        print(f"[{now_th()}] probe already running — skip", flush=True)
        return

    try:
        depts = CANARY_DEPTS + [rotating_dept()]
        records = []

        for dept_id in depts:
            rec = probe_dept(dept_id)
            records.append(rec)

            if rec["error_type"]:
                line = f"FAIL dept={dept_id} error={rec['error_type']} raw={rec['raw_failure_reason']}"
            else:
                line = (
                    f"OK   dept={dept_id} "
                    f"HTTP {rec['http_status']} | "
                    f"{rec['item_count']} items | "
                    f"{rec['latency_sec']}s | "
                    f"parse={'ok' if rec['parse_ok'] else 'FAIL'}"
                )
            print(f"[{now_th()}] {line}", flush=True)

        # Append to availability log
        with open(AVAIL_LOG, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        print(f"[{now_th()}] done — {len(records)} records appended to {AVAIL_LOG.name}", flush=True)

    finally:
        release_lock()


if __name__ == "__main__":
    main()
