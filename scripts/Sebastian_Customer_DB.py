"""
Sebastian_Customer_DB.py — SQLite schema v1.3 + SubscriptionStore abstraction

Schema v1.1 (2026-05-28):
  notification_queue  — + sending_at, retry_count, next_retry_at,
                          worker_id, last_error, last_error_type
  delivery_log        — replaces sent_notifications: append-only audit log (no UNIQUE)

Schema v1.2 (2026-05-28):
  projects_seen       — + project_name (low-medium trust), dept_id, dept_name

Schema v1.3 (2026-05-28):
  projects_seen       — + extraction_confidence (high/medium/low), source (rss/api)
  notification_queue  — + province_snapshot, project_name_snapshot, dept_name_snapshot
                          (immutable snapshot at enqueue time — audit/replay does not JOIN live)

Schema v1.4 (2026-05-28):
  notification_queue  — + is_backfill INTEGER (0=live discovery, 1=imported/backfill)
                          backfill items use different message label in format_notification()

Architecture: notification = historical event, not live view.
  Confidence gating: only enqueue if extraction_confidence == 'high' (pilot phase).
  Snapshot at enqueue: DO NOT JOIN live projects_seen at send/render time.
  rss_queue = immutable discovery log (no processed flag — projects_seen handles dedup).

State machine:
  pending → sending → sent
                    ↘ pending (retryable error, retry_count++)
                    ↘ failed  (terminal error OR retry_count >= MAX_RETRIES)
  sending → pending   (timeout recovery: sending_at > 5min)

notification_queue = source of truth for lifecycle
delivery_log       = append-only audit trail of every delivery attempt
"""
import sqlite3
import sys
import os
import socket
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).parent.parent / "data" / "bms_customers.db"
TZ_TH   = timezone(timedelta(hours=7))

SENDING_TIMEOUT_MIN = 5
MAX_RETRIES         = 3
RETRY_DELAY_MIN     = 5


def _now() -> str:
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def _now_plus(minutes: int) -> str:
    return (datetime.now(TZ_TH) + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema():
    """Create all tables if not exist + migrate v1 → v1.1. Safe on every startup."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id  TEXT NOT NULL UNIQUE,
                display_name  TEXT,
                tier          TEXT NOT NULL DEFAULT 'trial',
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id     INTEGER NOT NULL REFERENCES customers(id),
                announce_types  TEXT NOT NULL DEFAULT 'D0',
                min_budget      INTEGER NOT NULL DEFAULT 0,
                work_categories TEXT,
                delivery_mode   TEXT NOT NULL DEFAULT 'instant',
                active          INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subscription_provinces (
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
                province        TEXT NOT NULL,
                PRIMARY KEY (subscription_id, province)
            );

            -- canonical semantic event store (append-only, source of truth for delivery/matching/replay)
            -- field provenance / trust level:
            --   project_id           : RSS          → high
            --   announce_type        : RSS code     → high
            --   province             : RSS (parsed) → medium (see extraction_confidence)
            --   budget               : RSS          → medium
            --   project_name         : RSS title    → low-medium (truncation/encoding/abbrev)
            --   dept_id              : RSS param    → medium-high
            --   dept_name            : dept catalog → medium-high
            --   extraction_confidence: rule-based   → high/medium/low
            --   source               : origin       → rss | api
            -- NOTE: project_name is a raw semantic field — do NOT assume exact-string stability
            -- NOTE: province may be updated by API enrich — but notification snapshots are immutable
            CREATE TABLE IF NOT EXISTS projects_seen (
                project_id           TEXT PRIMARY KEY,
                announce_type        TEXT,
                province             TEXT,
                budget               INTEGER,
                project_name         TEXT,
                dept_id              TEXT,
                dept_name            TEXT,
                extraction_confidence TEXT,
                source               TEXT NOT NULL DEFAULT 'rss',
                first_seen_at        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notification_queue (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id           INTEGER NOT NULL REFERENCES customers(id),
                project_id            TEXT NOT NULL,
                status                TEXT NOT NULL DEFAULT 'pending',
                retry_count           INTEGER NOT NULL DEFAULT 0,
                next_retry_at         TEXT,
                sending_at            TEXT,
                worker_id             TEXT,
                last_error            TEXT,
                last_error_type       TEXT,
                created_at            TEXT NOT NULL,
                processed_at          TEXT,
                -- immutable snapshot of key fields at enqueue time
                -- DO NOT JOIN live projects_seen at render/send/audit — use these fields instead
                province_snapshot     TEXT,
                project_name_snapshot TEXT,
                dept_name_snapshot    TEXT,
                -- 0 = live discovery alert, 1 = backfill/imported (different message wording)
                is_backfill           INTEGER NOT NULL DEFAULT 0,
                UNIQUE(customer_id, project_id)
            );

            -- append-only delivery audit log (no UNIQUE — every attempt recorded)
            CREATE TABLE IF NOT EXISTS delivery_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id   INTEGER NOT NULL REFERENCES customers(id),
                project_id    TEXT NOT NULL,
                channel       TEXT NOT NULL DEFAULT 'line',
                status        TEXT NOT NULL,
                error_type    TEXT,
                attempted_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sub_customer
                ON subscriptions(customer_id);
            CREATE INDEX IF NOT EXISTS idx_queue_status
                ON notification_queue(status);
            CREATE INDEX IF NOT EXISTS idx_queue_retry
                ON notification_queue(status, next_retry_at);
            CREATE INDEX IF NOT EXISTS idx_dlog_customer_project
                ON delivery_log(customer_id, project_id);
            CREATE INDEX IF NOT EXISTS idx_prov_province
                ON subscription_provinces(province);
        """)
    _migrate_v1_to_v11()
    _migrate_v12()
    _migrate_v13()
    _migrate_v14()
    print(f"Schema v1.4 ready: {DB_PATH}")


def _migrate_v14():
    """Add is_backfill to notification_queue (idempotent)."""
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE notification_queue ADD COLUMN is_backfill INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass


def _migrate_v13():
    """Add snapshot cols to notification_queue + confidence/source to projects_seen (idempotent)."""
    stmts = [
        "ALTER TABLE notification_queue ADD COLUMN province_snapshot     TEXT",
        "ALTER TABLE notification_queue ADD COLUMN project_name_snapshot TEXT",
        "ALTER TABLE notification_queue ADD COLUMN dept_name_snapshot    TEXT",
        "ALTER TABLE projects_seen      ADD COLUMN extraction_confidence TEXT",
        "ALTER TABLE projects_seen      ADD COLUMN source                TEXT NOT NULL DEFAULT 'rss'",
    ]
    with get_connection() as conn:
        for sql in stmts:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists


def _migrate_v12():
    """Add project_name/dept_id/dept_name to projects_seen if upgrading from v1.1 (idempotent)."""
    stmts = [
        "ALTER TABLE projects_seen ADD COLUMN project_name TEXT",
        "ALTER TABLE projects_seen ADD COLUMN dept_id      TEXT",
        "ALTER TABLE projects_seen ADD COLUMN dept_name    TEXT",
    ]
    with get_connection() as conn:
        for sql in stmts:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists


def _migrate_v1_to_v11():
    """Add new notification_queue columns if upgrading from v1 (idempotent)."""
    stmts = [
        "ALTER TABLE notification_queue ADD COLUMN retry_count     INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE notification_queue ADD COLUMN next_retry_at   TEXT",
        "ALTER TABLE notification_queue ADD COLUMN sending_at      TEXT",
        "ALTER TABLE notification_queue ADD COLUMN worker_id       TEXT",
        "ALTER TABLE notification_queue ADD COLUMN last_error      TEXT",
        "ALTER TABLE notification_queue ADD COLUMN last_error_type TEXT",
    ]
    with get_connection() as conn:
        for sql in stmts:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists


# ── SubscriptionStore ─────────────────────────────────────────────────────────

class SubscriptionStore:

    def add_customer(self, line_user_id: str, display_name: str = "", tier: str = "trial") -> int:
        with get_connection() as conn:
            now = _now()
            cur = conn.execute(
                "INSERT OR IGNORE INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (line_user_id, display_name, tier, now, now),
            )
            if cur.lastrowid:
                return cur.lastrowid
            row = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (line_user_id,)).fetchone()
            return row["id"]

    def add_subscription(self, customer_id: int, provinces: list[str],
                         announce_types: list[str] = None,
                         min_budget: int = 0,
                         work_categories: list[str] = None,
                         delivery_mode: str = "instant") -> int:
        announce_types  = announce_types or ["D0"]
        work_categories = work_categories or []
        now = _now()
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO subscriptions "
                "(customer_id, announce_types, min_budget, work_categories, delivery_mode, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (customer_id, ",".join(announce_types), min_budget,
                 ",".join(work_categories), delivery_mode, now, now),
            )
            sub_id = cur.lastrowid
            for p in provinces:
                conn.execute(
                    "INSERT OR IGNORE INTO subscription_provinces (subscription_id, province) VALUES (?, ?)",
                    (sub_id, p.strip()),
                )
            return sub_id

    def record_project_seen(self, project_id: str, announce_type: str = "",
                            province: str = "", budget: int = 0,
                            project_name: str = "", dept_id: str = "",
                            dept_name: str = "",
                            extraction_confidence: str = "",
                            source: str = "rss"):
        """
        Register project in canonical registry (idempotent — INSERT OR IGNORE).
        extraction_confidence: 'high' | 'medium' | 'low' (rule-based, not ML)
        source: 'rss' | 'api'
        """
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO projects_seen "
                "(project_id, announce_type, province, budget, "
                " project_name, dept_id, dept_name, "
                " extraction_confidence, source, first_seen_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (project_id, announce_type, province, budget,
                 project_name or None, dept_id or None, dept_name or None,
                 extraction_confidence or None, source or "rss", _now()),
            )

    def enqueue_notifications(self, project: dict,
                               min_confidence: str = "high") -> int:
        """
        Match project against subscriptions → insert pending items into notification_queue.
        Returns count of new queue items created.

        project keys: project_id, province, announce_type, budget,
                      project_name, dept_name, extraction_confidence,
                      is_backfill (bool/int, default False)

        min_confidence: gate — only enqueue if project confidence >= threshold.
          'high'   → only high (default, pilot phase)
          'medium' → high + medium
          'low'    → all (no gate)

        Snapshot semantics: province_snapshot, project_name_snapshot, dept_name_snapshot
        are copied into notification_queue at INSERT time.
        DO NOT JOIN live projects_seen at send/render/audit — use snapshot fields instead.

        is_backfill=True: item was discovered before notifier epoch → different message label.
        """
        _CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}
        project_id   = project.get("project_id", "")
        province     = project.get("province", "")
        ann_type     = project.get("announce_type", "D0")
        budget       = project.get("budget", 0) or 0
        confidence   = project.get("extraction_confidence", "") or "low"
        project_name = project.get("project_name", "") or None
        dept_name    = project.get("dept_name", "") or None
        is_backfill  = 1 if project.get("is_backfill") else 0

        # Confidence gate
        if _CONFIDENCE_RANK.get(confidence, 0) < _CONFIDENCE_RANK.get(min_confidence, 2):
            return 0

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT s.customer_id, s.announce_types, s.min_budget, c.line_user_id, c.tier
                FROM subscriptions s
                JOIN customers c ON c.id = s.customer_id
                JOIN subscription_provinces sp ON sp.subscription_id = s.id
                WHERE s.active=1 AND c.active=1 AND sp.province=?
            """, (province,)).fetchall()

            count = 0
            now = _now()
            for row in rows:
                if ann_type not in row["announce_types"].split(","):
                    continue
                if budget < row["min_budget"]:
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO notification_queue "
                    "(customer_id, project_id, status, created_at, "
                    " province_snapshot, project_name_snapshot, dept_name_snapshot, is_backfill) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (row["customer_id"], project_id, "pending", now,
                     province or None, project_name, dept_name, is_backfill),
                )
                if cur.lastrowid:
                    count += 1
            return count

    def acquire_batch(self, batch_size: int = 1, wid: str = "") -> list[dict]:
        """
        Atomically acquire pending items → 'sending'.
        Uses BEGIN IMMEDIATE for crash-safe atomic read+write.
        Returns list of acquired row dicts (includes project details from projects_seen).
        """
        wid = wid or worker_id()
        conn = get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("""
                SELECT q.id, q.customer_id, q.project_id, q.retry_count,
                       q.is_backfill,
                       c.line_user_id, c.tier,
                       q.province_snapshot     AS province,
                       q.project_name_snapshot AS project_name,
                       q.dept_name_snapshot    AS dept_name,
                       ps.announce_type, ps.budget
                FROM notification_queue q
                JOIN customers c ON c.id = q.customer_id
                LEFT JOIN projects_seen ps ON ps.project_id = q.project_id
                WHERE q.status = 'pending'
                  AND (q.next_retry_at IS NULL OR q.next_retry_at <= ?)
                ORDER BY q.created_at
                LIMIT ?
            """, (_now(), batch_size)).fetchall()

            now = _now()
            for r in rows:
                conn.execute(
                    "UPDATE notification_queue "
                    "SET status='sending', sending_at=?, worker_id=? WHERE id=?",
                    (now, wid, r["id"]),
                )
            conn.commit()
            result = [dict(r) for r in rows]
            for item in result:
                item["worker_id"] = wid
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def recover_stuck_sending(self, timeout_minutes: int = SENDING_TIMEOUT_MIN) -> int:
        """
        Reset 'sending' items older than timeout → 'pending' (worker_timeout).
        Items at MAX_RETRIES → 'failed' instead.
        """
        cutoff = (datetime.now(TZ_TH) - timedelta(minutes=timeout_minutes)).isoformat(timespec="seconds")
        with get_connection() as conn:
            # Recoverable: reset to pending with retry delay
            cur = conn.execute("""
                UPDATE notification_queue
                SET status        = 'pending',
                    sending_at    = NULL,
                    worker_id     = NULL,
                    retry_count   = retry_count + 1,
                    last_error_type = 'worker_timeout',
                    next_retry_at = ?
                WHERE status = 'sending'
                  AND sending_at < ?
                  AND retry_count < ?
            """, (_now_plus(RETRY_DELAY_MIN), cutoff, MAX_RETRIES))
            recovered = cur.rowcount

            # Terminal: exhausted retries via timeout
            conn.execute("""
                UPDATE notification_queue
                SET status          = 'failed',
                    last_error_type = 'worker_timeout',
                    processed_at    = ?
                WHERE status = 'sending'
                  AND sending_at < ?
                  AND retry_count >= ?
            """, (_now(), cutoff, MAX_RETRIES))
            return recovered

    def mark_delivery_result(self, queue_id: int, customer_id: int, project_id: str,
                              status: str, error: str = "", error_type: str = ""):
        """
        Update queue lifecycle + append to delivery_log.
        status='sent'    → terminal success
        error_type='terminal' → terminal failure (invalid user, blocked)
        otherwise        → retryable: back to pending, retry_count++, next_retry_at set
        """
        now = _now()
        with get_connection() as conn:
            if status == "sent":
                conn.execute(
                    "UPDATE notification_queue "
                    "SET status='sent', processed_at=?, sending_at=NULL, worker_id=NULL "
                    "WHERE id=?",
                    (now, queue_id),
                )
            elif error_type == "terminal":
                conn.execute(
                    "UPDATE notification_queue "
                    "SET status='failed', processed_at=?, last_error=?, last_error_type='terminal' "
                    "WHERE id=?",
                    (now, error[:500], queue_id),
                )
            else:
                # Retryable — increment retry_count then check if exhausted
                conn.execute(
                    "UPDATE notification_queue "
                    "SET status='pending', sending_at=NULL, worker_id=NULL, "
                    "    retry_count=retry_count+1, next_retry_at=?, "
                    "    last_error=?, last_error_type=? "
                    "WHERE id=?",
                    (_now_plus(RETRY_DELAY_MIN), error[:500], error_type or "retryable", queue_id),
                )
                conn.execute(
                    "UPDATE notification_queue SET status='failed', processed_at=? "
                    "WHERE id=? AND retry_count >= ?",
                    (now, queue_id, MAX_RETRIES),
                )

            # Always append audit record
            conn.execute(
                "INSERT INTO delivery_log "
                "(customer_id, project_id, channel, status, error_type, attempted_at) "
                "VALUES (?,?,?,?,?,?)",
                (customer_id, project_id, "line", status, error_type or None, now),
            )

    def already_sent(self, customer_id: int, project_id: str) -> bool:
        """notification_queue is source of truth for successful delivery."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM notification_queue "
                "WHERE customer_id=? AND project_id=? AND status='sent'",
                (customer_id, project_id),
            ).fetchone()
            return row is not None

    def get_pending_queue(self, limit: int = 50) -> list[dict]:
        """Read-only peek at pending queue. Use acquire_batch() in worker."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT q.id, q.customer_id, q.project_id, c.line_user_id, c.tier "
                "FROM notification_queue q "
                "JOIN customers c ON c.id = q.customer_id "
                "WHERE q.status='pending' ORDER BY q.created_at LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]


if __name__ == "__main__":
    import os
    db = Path(__file__).parent.parent / "data" / "bms_customers.db"
    if db.exists():
        os.remove(db)
        print("Removed old DB")

    init_schema()
    store = SubscriptionStore()

    cid = store.add_customer("Uxxxxxxxxx_TEST", display_name="ทดสอบ บริษัทก่อสร้าง", tier="trial")
    store.add_subscription(cid, provinces=["นครพนม", "บึงกาฬ"], min_budget=500_000)
    print(f"Customer id={cid} added")

    # Test 1: high-confidence project → should enqueue
    pid = "69039196328"
    store.record_project_seen(
        pid, announce_type="D0", province="นครพนม", budget=1_000_000,
        project_name="จ้างก่อสร้างถนน ต.บ้านแพง", dept_id="0708", dept_name="อบต.บ้านแพง",
        extraction_confidence="high", source="rss",
    )
    project = {
        "project_id": pid, "province": "นครพนม", "announce_type": "D0", "budget": 1_000_000,
        "project_name": "จ้างก่อสร้างถนน ต.บ้านแพง", "dept_name": "อบต.บ้านแพง",
        "extraction_confidence": "high",
    }
    print(f"Enqueued (high conf): {store.enqueue_notifications(project)} (expect 1)")
    print(f"Re-enqueue (idempotent): {store.enqueue_notifications(project)} (expect 0)")

    # Test 2: low-confidence → confidence gate should block
    pid_low = "69039000001"
    store.record_project_seen(
        pid_low, province="นครพนม", announce_type="D0", budget=800_000,
        extraction_confidence="low", source="rss",
    )
    blocked = store.enqueue_notifications({
        "project_id": pid_low, "province": "นครพนม", "announce_type": "D0", "budget": 800_000,
        "extraction_confidence": "low",
    })
    print(f"Blocked (low conf):  {blocked} (expect 0)")

    # Test 3: acquire batch — verify snapshot fields returned
    wid = worker_id()
    items = store.acquire_batch(batch_size=1, wid=wid)
    assert len(items) == 1
    item = items[0]
    assert item["province"] == "นครพนม",       f"province snapshot wrong: {item['province']}"
    assert item["project_name"] == "จ้างก่อสร้างถนน ต.บ้านแพง", f"project_name wrong: {item['project_name']}"
    assert item["dept_name"] == "อบต.บ้านแพง", f"dept_name wrong: {item['dept_name']}"
    print(f"Acquired: worker_id={item['worker_id']}, province_snapshot='{item['province']}'")

    # Test 4: send success
    store.mark_delivery_result(item["id"], item["customer_id"], item["project_id"], "sent")
    print(f"already_sent after mark: {store.already_sent(cid, pid)} (expect True)")

    # Test 5: retryable failure
    pid2 = "69039999999"
    store.record_project_seen(pid2, province="นครพนม", announce_type="D0", budget=800_000,
                               extraction_confidence="high", source="rss")
    store.enqueue_notifications({"project_id": pid2, "province": "นครพนม", "announce_type": "D0",
                                  "budget": 800_000, "extraction_confidence": "high"})
    items2 = store.acquire_batch(batch_size=1, wid=wid)
    if items2:
        store.mark_delivery_result(items2[0]["id"], items2[0]["customer_id"], items2[0]["project_id"],
                                   "failed", error="HTTP 429", error_type="retryable")
        print("Retryable fail recorded — item back to pending with next_retry_at")

    # Test 6: timeout recovery
    recovered = store.recover_stuck_sending(timeout_minutes=0)
    print(f"Timeout recovery: {recovered} recovered")

    # Test 7: is_backfill flag
    pid_back = "69039000002"
    store.record_project_seen(pid_back, province="นครพนม", announce_type="D0", budget=600_000,
                               extraction_confidence="high", source="rss")
    n_back = store.enqueue_notifications({
        "project_id": pid_back, "province": "นครพนม", "announce_type": "D0",
        "budget": 600_000, "extraction_confidence": "high", "is_backfill": True,
    })
    assert n_back == 1, f"Expected 1 backfill enqueued, got {n_back}"
    items_back = store.acquire_batch(batch_size=1, wid=wid)
    assert items_back[0]["is_backfill"] == 1, "is_backfill should be 1"
    print(f"Backfill flag: is_backfill={items_back[0]['is_backfill']} (expect 1)")

    print("\nSchema v1.4 smoke test passed ✅")
