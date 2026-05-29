"""
Sebastian_Daily_Digest.py — BMS operational health digest

Sends Discord message at 08:00 with last-24h system health.
Objective: detect silent failure fast, not executive BI.

Status symbols:
  PASS  = healthy
  WARN  = degraded but functioning
  FAIL  = failure
  ZERO  = informative zero (healthy absence)
"""
import os
import sys
import io
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Discord_Notify import load_env, get_credentials, send

TZ_TH   = timezone(timedelta(hours=7))
BASE    = Path(__file__).parent.parent
NOW     = datetime.now(TZ_TH)
WINDOW  = NOW - timedelta(hours=24)


def _ts(s: str):
    try:
        return datetime.fromisoformat(s).astimezone(TZ_TH)
    except Exception:
        return None


# ── RSS availability ──────────────────────────────────────────────────────────

def rss_section() -> str:
    log_path = BASE / "data" / "rss_availability_log.ndjson"
    if not log_path.exists():
        return "RSS: FAIL  log file missing"

    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            ts = _ts(e.get("ts", ""))
            if ts and ts >= WINDOW:
                events.append(e)
        except Exception:
            pass

    if not events:
        return "RSS: WARN  no probes in last 24h"

    ok      = sum(1 for e in events if e.get("http_status") == 200 and e.get("parse_ok"))
    timeout = sum(1 for e in events if e.get("error_type") == "timeout")
    fail    = len(events) - ok - timeout
    lats    = [e["latency_sec"] for e in events if e.get("http_status") == 200 and e.get("latency_sec")]
    avg_lat = f"{sum(lats)/len(lats):.2f}s" if lats else "-"

    ok_events = [e for e in events if e.get("http_status") == 200]
    last_ok   = max((_ts(e["ts"]) for e in ok_events), default=None)
    last_ok_s = last_ok.strftime("%H:%M") if last_ok else "none"

    total = len(events)
    if ok == total:
        sym = "PASS "
    elif ok > 0:
        sym = "WARN "
    else:
        sym = "FAIL "

    return (
        f"RSS: {sym}\n"
        f"  checks {ok}/{total} OK  timeout={timeout}  fail={fail}\n"
        f"  last_ok={last_ok_s}  avg_lat={avg_lat}"
    )


# ── Discovery ─────────────────────────────────────────────────────────────────

def discovery_section() -> str:
    queue_path = BASE / "data" / "rss_queue.json"
    if not queue_path.exists():
        return "Discovery: FAIL  rss_queue.json missing"

    items = json.loads(queue_path.read_text(encoding="utf-8"))
    new_24h = [i for i in items if _ts(i.get("queued_at", "")) and _ts(i["queued_at"]) >= WINDOW]
    d0_new  = [i for i in new_24h if i.get("anounce_type") == "D0"]

    target = {"นครพนม", "บึงกาฬ"}
    hits   = [i for i in d0_new if any(p in i.get("title", "") for p in target)]

    sym = "PASS " if new_24h else "ZERO "
    lines = [
        f"Discovery: {sym}",
        f"  new items 24h={len(new_24h)}  D0={len(d0_new)}",
        f"  target province hits={len(hits)}",
    ]
    if not new_24h:
        lines.append("  (RSS may have been down or no new announcements)")
    return "\n".join(lines)


# ── Delivery ──────────────────────────────────────────────────────────────────

def delivery_section() -> str:
    db_path = Path(os.environ.get("BMS_DATA_DIR") or str(BASE / "data")) / "bms_customers.db"
    if not db_path.exists():
        return "Delivery: FAIL  bms_customers.db missing"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    sent = conn.execute(
        "SELECT COUNT(*) n FROM delivery_log "
        "WHERE status='sent' AND is_test_data=0 AND attempted_at >= ?",
        (WINDOW.isoformat(),),
    ).fetchone()["n"]

    failed = conn.execute(
        "SELECT COUNT(*) n FROM delivery_log "
        "WHERE status!='sent' AND is_test_data=0 AND attempted_at >= ?",
        (WINDOW.isoformat(),),
    ).fetchone()["n"]

    pending = conn.execute(
        "SELECT COUNT(*) n FROM notification_queue "
        "WHERE status='pending' AND is_test_data=0"
    ).fetchone()["n"]

    last_sender_log = BASE / "logs" / "line_sender" / f"sender_{NOW.strftime('%Y%m%d')}.log"
    sender_alive = last_sender_log.exists()

    if sent > 0:
        sym = "PASS "
    elif not sender_alive:
        sym = "FAIL "  # sender never ran today
    elif pending == 0:
        sym = "ZERO "  # healthy zero — nothing to send
    else:
        sym = "WARN "  # pending but not sent

    # Monthly quota (LINE push API = 200 free/month)
    LINE_MONTHLY_QUOTA = 200
    month_start = NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    sent_month = conn.execute(
        "SELECT COUNT(*) n FROM delivery_log "
        "WHERE status='sent' AND is_test_data=0 AND attempted_at >= ?",
        (month_start,),
    ).fetchone()["n"]
    quota_remaining = LINE_MONTHLY_QUOTA - sent_month

    # Per-customer sent today
    per_customer = conn.execute(
        "SELECT c.display_name, COUNT(*) n FROM delivery_log d "
        "JOIN customers c ON c.id = d.customer_id "
        "WHERE d.status='sent' AND d.is_test_data=0 AND d.attempted_at >= ? "
        "GROUP BY d.customer_id",
        (WINDOW.isoformat(),),
    ).fetchall()

    lines = [
        f"Delivery: {sym}",
        f"  sent={sent}  failed={failed}  queue_pending={pending}",
        f"  quota: {sent_month}/{LINE_MONTHLY_QUOTA} used  remaining={quota_remaining}",
    ]
    if per_customer:
        breakdown = "  ".join(f"{r['display_name'][:10]}={r['n']}" for r in per_customer)
        lines.append(f"  per_user: {breakdown}")
    if quota_remaining <= 20:
        lines.append(f"  ⚠️ QUOTA LOW: {quota_remaining} remaining this month")
    if sent == 0 and pending == 0 and sym == "ZERO ":
        lines.append("  (no matching projects in queue — expected)")
    if failed > 0:
        lines.append(f"  WARNING: {failed} delivery failures need review")
    conn.close()
    return "\n".join(lines)


# ── Enrichment ───────────────────────────────────────────────────────────────

def enrichment_section() -> str:
    db_path = Path(os.environ.get("BMS_DATA_DIR") or str(BASE / "data")) / "bms_customers.db"
    if not db_path.exists():
        return "Enrichment: FAIL  bms_customers.db missing"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    total   = conn.execute("SELECT COUNT(*) n FROM project_locations").fetchone()["n"]
    pending = conn.execute("SELECT COUNT(*) n FROM project_locations WHERE enrichment_status='pending'").fetchone()["n"]
    success = conn.execute("SELECT COUNT(*) n FROM project_locations WHERE enrichment_status='success'").fetchone()["n"]
    failed  = conn.execute("SELECT COUNT(*) n FROM project_locations WHERE enrichment_status='failed'").fetchone()["n"]
    oldest  = conn.execute(
        "SELECT MIN(created_at) ts FROM project_locations WHERE enrichment_status='pending'"
    ).fetchone()["ts"]
    conn.close()

    if oldest:
        oldest_dt = _ts(oldest)
        age_min   = int((NOW - oldest_dt).total_seconds() / 60) if oldest_dt else 0
        age_str   = f"{age_min}min"
    else:
        age_str = "-"

    if failed > 5:
        sym = "WARN "
    elif pending > 0 and success == 0:
        sym = "WARN "
    else:
        sym = "PASS "

    lines = [
        f"Enrichment: {sym}",
        f"  total={total}  success={success}  pending={pending}  failed={failed}",
        f"  oldest_pending_age={age_str}",
    ]
    if failed > 0:
        lines.append(f"  ⚠️ {failed} projects permanently failed (>= 5 attempts)")
    return "\n".join(lines)


# ── Tasks ─────────────────────────────────────────────────────────────────────

def tasks_section() -> str:
    today = NOW.strftime("%Y%m%d")
    results = []
    for name, log_path in [
        ("RSS_Notifier",    BASE / "logs" / "rss_notifier"     / f"notifier_{today}.log"),
        ("LINE_Sender",     BASE / "logs" / "line_sender"      / f"sender_{today}.log"),
        ("Enrich_Worker",   BASE / "logs" / "enrichment_worker" / f"enrichment_{today}.log"),
    ]:
        if not log_path.exists():
            results.append(f"  {name}: FAIL  no log today")
            continue
        lines = [l for l in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        if not lines:
            results.append(f"  {name}: WARN  log empty")
            continue
        last_line = lines[-1]
        # extract timestamp from log line [HH:MM:SS]
        last_time = last_line[1:9] if last_line.startswith("[") else "?"
        results.append(f"  {name}: PASS  last_run={last_time}")

    return "Tasks:\n" + "\n".join(results)


# ── System ────────────────────────────────────────────────────────────────────

def system_section() -> str:
    boot_log = BASE / "logs" / "boot_trace.log"
    if not boot_log.exists():
        return "System: WARN  boot_trace.log missing"

    lines = boot_log.read_text(encoding="utf-8").splitlines()
    today_boots = [l for l in lines if l.startswith(NOW.strftime("%Y-%m-%d"))]
    recent = today_boots[-4:] if today_boots else []

    if recent:
        last = recent[-1]
        return f"System: PASS \n  today cold-starts={len(today_boots)}\n  last: {last[11:35]}"
    else:
        return "System: ZERO \n  no cold-starts today (stable, no reboot)"


# ── Main ──────────────────────────────────────────────────────────────────────

def _snapshot_enrichment_stats() -> None:
    """INSERT OR IGNORE yesterday's enrichment stats into enrichment_daily_stats."""
    db_path = Path(os.environ.get("BMS_DATA_DIR") or str(BASE / "data")) / "bms_customers.db"
    if not db_path.exists():
        return
    yesterday = (NOW - timedelta(hours=24)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) n FROM project_locations").fetchone()["n"]
    hits  = conn.execute(
        "SELECT COUNT(*) n FROM project_locations "
        "WHERE province_name IN ('นครพนม','บึงกาฬ') AND enrichment_status='success'"
    ).fetchone()["n"]
    conn.execute(
        "INSERT OR IGNORE INTO enrichment_daily_stats (stat_date, total_enriched, target_hits, created_at) "
        "VALUES (?,?,?,?)",
        (yesterday, total, hits, NOW.isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def main():
    _snapshot_enrichment_stats()

    rss   = rss_section()
    disc  = discovery_section()
    enr   = enrichment_section()
    dlv   = delivery_section()
    task  = tasks_section()
    sys_  = system_section()

    date_str = NOW.strftime("%Y-%m-%d %H:%M")
    msg = "\n".join([
        f"BMS Daily Digest — {date_str}",
        "=" * 36,
        rss,
        "",
        disc,
        "",
        enr,
        "",
        dlv,
        "",
        task,
        "",
        sys_,
    ])

    load_env()
    token, ch = get_credentials()
    send(token, ch, msg)
    print(msg)


if __name__ == "__main__":
    main()
