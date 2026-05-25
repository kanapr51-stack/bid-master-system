"""
Sebastian_Telemetry.py — BMS operational telemetry (SQLite-backed)

Circuit breaker + poll log สำหรับ eGP RSS endpoint.

Why SQLite (not git): atomic writes, WAL concurrent reads, queryable history.
Why not Redis/external: single-machine setup, SQLite is perfect for this scale.

Schema versions:
  v1 = legacy_snapshot (backfilled from rss_run_*.json — no TTFB)
  v2 = full_metrics (live instrumentation — has TTFB + response_time_ms)
"""
import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "bms_telemetry.db"

# Circuit breaker thresholds
CB_FAIL_THRESHOLD = 3    # consecutive failures → OPEN
CB_COOLDOWN_MIN   = 30   # minutes in OPEN state before HALF_OPEN retry

SCHEMA_VERSION_LEGACY = 1   # backfilled from snapshot files
SCHEMA_VERSION_LIVE   = 2   # live instrumentation


@contextmanager
def _conn():
    """Fresh connection per operation — safe for overlapping runners (:22/:52).
    WAL allows concurrent reads; timeout=30 waits for write lock rather than crash."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables + indexes if they don't exist."""
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS breaker_state (
                endpoint       TEXT PRIMARY KEY,
                state          TEXT    NOT NULL DEFAULT 'CLOSED',
                fail_count     INTEGER NOT NULL DEFAULT 0,
                last_success   TEXT,
                cooldown_until TEXT,
                updated_at     TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS poll_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                polled_at        TEXT    NOT NULL,
                endpoint         TEXT    NOT NULL,
                dept_id          TEXT,
                anounce_type     TEXT,
                source_type      TEXT    NOT NULL DEFAULT 'rss',
                success          INTEGER NOT NULL,
                http_status      INTEGER,
                ttfb_ms          REAL,
                response_time_ms REAL,
                bytes_received   INTEGER,
                items_count      INTEGER NOT NULL DEFAULT 0,
                fail_streak      INTEGER NOT NULL DEFAULT 0,
                failure_reason   TEXT,
                schema_version   INTEGER NOT NULL DEFAULT 2,
                data_quality     TEXT    NOT NULL DEFAULT 'full_metrics'
            );

            CREATE INDEX IF NOT EXISTS idx_poll_polled_at
                ON poll_log (polled_at);
            CREATE INDEX IF NOT EXISTS idx_poll_endpoint
                ON poll_log (endpoint, polled_at);
        """)


# ──────────────────────────────────────────────────────────────────────────────
# Circuit breaker
# ──────────────────────────────────────────────────────────────────────────────

def check_breaker(endpoint: str) -> str:
    """Return CLOSED / OPEN / HALF_OPEN.
    Caller skips fetch when OPEN; attempts one probe when HALF_OPEN."""
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT state, cooldown_until FROM breaker_state WHERE endpoint=?",
            (endpoint,)
        ).fetchone()

    if row is None:
        return "CLOSED"

    if row["state"] == "OPEN" and row["cooldown_until"]:
        if datetime.now() >= datetime.fromisoformat(row["cooldown_until"]):
            return "HALF_OPEN"

    return row["state"]


def record_poll(
    endpoint: str,
    dept_id: str,
    anounce_type: str,
    success: bool,
    http_status: int,
    response_time_ms: float | None,
    ttfb_ms: float | None,
    bytes_received: int | None,
    items_count: int,
    failure_reason: str | None = None,
    source_type: str = "rss",
) -> str:
    """Log one poll attempt. Update breaker state. Return new breaker state."""
    init_db()
    now = datetime.now().isoformat(timespec="seconds")

    with _conn() as conn:
        row = conn.execute(
            "SELECT fail_count, state, last_success, cooldown_until FROM breaker_state WHERE endpoint=?",
            (endpoint,)
        ).fetchone()

        prev_fails = row["fail_count"] if row else 0

        if success:
            new_fails      = 0
            new_state      = "CLOSED"
            last_success   = now
            cooldown_until = None
        else:
            new_fails    = prev_fails + 1
            last_success = row["last_success"] if row else None

            if new_fails >= CB_FAIL_THRESHOLD:
                new_state      = "OPEN"
                cooldown_until = (
                    datetime.now() + timedelta(minutes=CB_COOLDOWN_MIN)
                ).isoformat(timespec="seconds")
            else:
                new_state      = row["state"] if row else "CLOSED"
                cooldown_until = row["cooldown_until"] if row else None

        conn.execute("""
            INSERT INTO breaker_state
                (endpoint, state, fail_count, last_success, cooldown_until, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                state          = excluded.state,
                fail_count     = excluded.fail_count,
                last_success   = COALESCE(excluded.last_success, last_success),
                cooldown_until = excluded.cooldown_until,
                updated_at     = excluded.updated_at
        """, (endpoint, new_state, new_fails, last_success, cooldown_until, now))

        conn.execute("""
            INSERT INTO poll_log (
                polled_at, endpoint, dept_id, anounce_type, source_type,
                success, http_status, ttfb_ms, response_time_ms,
                bytes_received, items_count, fail_streak, failure_reason,
                schema_version, data_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now, endpoint, dept_id, anounce_type, source_type,
            1 if success else 0, http_status,
            ttfb_ms, response_time_ms, bytes_received, items_count,
            new_fails, failure_reason,
            SCHEMA_VERSION_LIVE, "full_metrics",
        ))

    return new_state


# ──────────────────────────────────────────────────────────────────────────────
# Backfill legacy snapshots
# ──────────────────────────────────────────────────────────────────────────────

def backfill_from_snapshots(data_dir: Path) -> int:
    """Insert one legacy_snapshot row per rss_run_*.json file.

    TTFB and response_time_ms are NULL (not captured in legacy format).
    data_quality='legacy_snapshot' so queries can filter by metric completeness.
    Returns number of rows inserted.
    """
    snapshots = sorted(data_dir.glob("rss_run_*.json"))
    if not snapshots:
        return 0

    init_db()
    inserted = 0

    for path in snapshots:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        run_at = data.get("run_at", "")
        if not run_at:
            continue

        with _conn() as conn:
            already = conn.execute(
                "SELECT id FROM poll_log WHERE polled_at=? AND data_quality='legacy_snapshot' LIMIT 1",
                (run_at,)
            ).fetchone()
            if already:
                continue

            total_items  = data.get("total_items", 0)
            poll_errors  = data.get("poll_errors", 0)
            depts_polled = data.get("depts_polled", 1)
            success      = total_items > 0 or (poll_errors < depts_polled)

            conn.execute("""
                INSERT INTO poll_log (
                    polled_at, endpoint, dept_id, anounce_type, source_type,
                    success, http_status, ttfb_ms, response_time_ms,
                    bytes_received, items_count, fail_streak, failure_reason,
                    schema_version, data_quality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_at,
                "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml",
                "",       # global snapshot — no specific dept_id
                "mixed",  # legacy snapshots cover multiple anounce_types
                "rss",
                1 if success else 0,
                200 if success else -1,
                None, None, None,   # ttfb_ms, response_time_ms, bytes_received → not available
                total_items,
                0,                  # fail_streak unknown from snapshot
                None,
                SCHEMA_VERSION_LEGACY, "legacy_snapshot",
            ))
            inserted += 1

    return inserted


# ──────────────────────────────────────────────────────────────────────────────
# Quick diagnostics (for CLI / progress_log)
# ──────────────────────────────────────────────────────────────────────────────

def print_status(endpoint: str):
    """Print breaker state + last 5 polls to stdout."""
    init_db()
    state = check_breaker(endpoint)
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM breaker_state WHERE endpoint=?", (endpoint,)
        ).fetchone()
        recent = conn.execute(
            """SELECT polled_at, success, response_time_ms, items_count, failure_reason
               FROM poll_log WHERE endpoint=? ORDER BY polled_at DESC LIMIT 5""",
            (endpoint,)
        ).fetchall()

    out = (f"\n=== Circuit Breaker: {state} ===\n")
    if row:
        out += (f"  fails={row['fail_count']}  last_success={row['last_success']}"
                f"  cooldown_until={row['cooldown_until']}\n")
    out += "\nRecent polls:\n"
    for r in recent:
        icon   = "OK " if r["success"] else "ERR"
        rt     = f"{r['response_time_ms']:.0f}ms" if r["response_time_ms"] else "-"
        reason = f" [{r['failure_reason']}]" if r["failure_reason"] else ""
        out += f"  [{icon}] {r['polled_at']}  {rt}  items={r['items_count']}{reason}\n"
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    import sys
    DATA_DIR = Path(__file__).parent.parent / "data"
    RSS_ENDPOINT = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"

    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        n = backfill_from_snapshots(DATA_DIR)
        print(f"Backfilled {n} legacy snapshot rows → {DB_PATH}")
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        print_status(RSS_ENDPOINT)
    else:
        print("Usage: python Sebastian_Telemetry.py [backfill|status]")
