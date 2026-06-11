"""
Sebastian_Customer_DB.py — SQLite schema v1.11 + SubscriptionStore abstraction

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

Schema v1.5 (2026-05-28):
  notification_queue  — + source_stage TEXT (latent metadata, NOT active in delivery logic)
                          values: 'rss_provisional' | 'api_enriched'
                          intentionally deferred: enriched re-notification semantics
                          are out of scope for pilot phase (see progress_log.md N+32)

Schema v1.6 (2026-05-28):
  notification_queue  — + is_test_data INTEGER NOT NULL DEFAULT 0
  delivery_log        — + is_test_data INTEGER NOT NULL DEFAULT 0
  Observability hygiene boundary — separates production metrics from fault-injection.
  Production queries: WHERE is_test_data=0
  Synthetic/validation: WHERE is_test_data=1
  Kept separate from source_stage to preserve data-provenance semantic purity.

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

_DATA_DIR = os.environ.get("BMS_DATA_DIR") or str(Path(__file__).parent.parent / "data")
DB_PATH = Path(_DATA_DIR) / "bms_customers.db"
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


def save_project_location_raw(project_id: str, district_moi_id: str = "", moi_name: str = "",
                              latitude: str = "", longitude: str = "") -> None:
    """persist raw location จาก getProcurementDetail (MOI disambiguation Phase A).
    lat/lng ถูก compensate mislabel ที่ source (get_procurement_detail) แล้ว → เก็บตรงๆ ไม่ swap.
    เก็บเฉพาะ raw (district_moi_id/moi_name/lat/lng) — amphoe/confidence เป็น runtime-compute
    (ไม่ persist, กัน stale). ไม่แตะ qualification/enrichment_status."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_locations SET district_moi_id=?, moi_name=?, latitude=?, longitude=? "
            "WHERE project_id=?",
            (district_moi_id or "", moi_name or "",
             str(latitude or ""), str(longitude or ""), project_id))


def is_following(customer_id: int, project_id: str) -> bool:
    """ลูกค้ารายนี้ติดตามงานนี้อยู่ไหม (followed_jobs active) — ใช้กันโชว์ปุ่ม ⭐ ซ้ำ."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM followed_jobs WHERE customer_id=? AND project_id=? AND status='active'",
            (customer_id, project_id)).fetchone() is not None


def save_prediction(p: dict) -> None:
    """เก็บคำทำนายราคาตอน D0 — upsert ทับด้วยค่าล่าสุดที่ส่งจริง (กันค่าเก่าค้าง).
    ON CONFLICT ทับเฉพาะคอลัมน์ prediction — ไม่แตะ actual_price/in_range/error_pct/verified_at."""
    cols = ("project_id", "budget", "area_disc_lo", "area_disc_hi", "area_price_lo",
            "area_price_hi", "area_disc_med", "area_price_med", "top_name", "top_disc", "top_price")
    upd = [c for c in cols if c != "project_id"] + ["predicted_at"]
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO price_predictions ({','.join(cols)}, predicted_at) "
            f"VALUES ({','.join('?' for _ in cols)}, ?) "
            f"ON CONFLICT(project_id) DO UPDATE SET "
            + ", ".join(f"{c}=excluded.{c}" for c in upd),
            tuple(p.get(c) for c in cols) + (_now(),))


def get_prediction(project_id: str) -> dict | None:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT * FROM price_predictions WHERE project_id=?", (project_id,)).fetchone()
        return dict(r) if r else None


def update_prediction_actual(project_id: str, actual_price, in_range: int, error_pct: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_predictions SET actual_price=?, in_range=?, error_pct=?, verified_at=? "
            "WHERE project_id=?", (actual_price, in_range, error_pct, _now(), project_id))


def prediction_accuracy_summary() -> dict:
    """running credibility: in-range rate + mean error% จาก verified rows."""
    with get_connection() as conn:
        rows = conn.execute("SELECT in_range, error_pct FROM price_predictions "
                            "WHERE verified_at IS NOT NULL").fetchall()
    n = len(rows)
    inr = sum(1 for r in rows if r[0] == 1)
    errs = [r[1] for r in rows if r[1] is not None]
    return {
        "verified": n,
        "in_range": inr,
        "in_range_pct": round(inr * 100.0 / n, 1) if n else 0.0,
        "mean_error_pct": round(sum(errs) / len(errs), 1) if errs else 0.0,
    }


def backfill_provinces_from_locations() -> int:
    """เติม projects_seen.province จาก project_locations.province_name (authoritative จาก MOI enrich)
    เมื่อ province ว่าง — แก้เคส province extraction จากชื่องานล้มเหลว (ชื่อไม่มี 'จังหวัด').
    schema sanction: 'province may be updated by API enrich'. คืนจำนวน row ที่อัปเดต."""
    with get_connection() as conn:
        cur = conn.execute("""
            UPDATE projects_seen SET province = (
                SELECT pl.province_name FROM project_locations pl
                WHERE pl.project_id = projects_seen.project_id)
            WHERE (province IS NULL OR province = '')
              AND EXISTS (SELECT 1 FROM project_locations pl
                          WHERE pl.project_id = projects_seen.project_id
                            AND pl.province_name IS NOT NULL AND pl.province_name != '')""")
        return cur.rowcount


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
    _migrate_v15()
    _migrate_v16()
    _migrate_v17()
    _migrate_v18()
    _migrate_v19()
    _migrate_v110()
    _migrate_v111()
    _migrate_v112()
    _migrate_v113()
    _migrate_v114()
    _migrate_v115()
    _migrate_v116()
    _migrate_v117()
    _migrate_v118()
    _migrate_v119()
    _migrate_v120()
    _migrate_v121()
    _migrate_v122()
    _migrate_v123()
    _migrate_v124()
    _migrate_v125()
    print(f"Schema v1.13 ready: {DB_PATH}")


def _migrate_v125():
    """project_locations +deadline_time — ช่วงเวลายื่นซอง '13.00-16.00 น.' จาก PDF (province_api path)
    เพื่อโชว์เวลาในการ์ด D0 ไม่ใช่แค่วันที่. additive ALTER (idempotent)."""
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE project_locations ADD COLUMN deadline_time TEXT")
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v124():
    """price_predictions +area_disc_med +area_price_med — เก็บ 'ค่ากลาง (ปกติ)' ที่โชว์ตอน D0
    เพื่อเทียบ win/lose ตอน W0 (ราคาที่คาด ≤ ราคาชนะ → ชนะ=ความแม่นยำ / > → แพ้=ความคลาดเคลื่อน).
    additive ALTER (idempotent). prediction เก่าไม่มี median → display fallback เทียบกรอบบน."""
    with get_connection() as conn:
        for col, typ in (("area_disc_med", "REAL"), ("area_price_med", "INTEGER")):
            try:
                conn.execute(f"ALTER TABLE price_predictions ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # already exists


def _migrate_v123():
    """normalize lat/lng ที่ swap (row จาก _enrich path เก่า ก่อน compensate mislabel ที่ source).
    latitude ของไทย ≤ ~21 เสมอ → ถ้า latitude>90 = ค่าจริงเป็น longitude (swap อยู่) → สลับคืน.
    idempotent (รอบสอง latitude<90 → ไม่แตะ)."""
    with get_connection() as conn:
        try:
            conn.execute(
                "UPDATE project_locations SET latitude=longitude, longitude=latitude "
                "WHERE latitude IS NOT NULL AND latitude!='' AND CAST(latitude AS REAL) > 90")
        except sqlite3.OperationalError:
            pass


def _migrate_v122():
    """price_predictions — เก็บคำทำนายราคาชนะตอน D0 → เทียบจริงตอน W0 (credibility engine).
    เก็บ raw prediction + ผลเทียบ (in_range/error คำนวณตอน verify, เก็บเพื่อ aggregate credibility).
    additive (table ใหม่)."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_predictions (
                project_id    TEXT PRIMARY KEY,
                budget        INTEGER,
                area_disc_lo  REAL, area_disc_hi REAL,
                area_price_lo INTEGER, area_price_hi INTEGER,
                area_disc_med REAL, area_price_med INTEGER,
                top_name      TEXT, top_disc REAL, top_price INTEGER,
                predicted_at  TEXT,
                actual_price  INTEGER, in_range INTEGER, error_pct REAL, verified_at TEXT
            )""")


def _migrate_v121():
    """cgd_winners +district +subdistrict — competitor intel ระดับตำบล/อำเภอ (winner_history
    มี district 100%, subdistrict 91%). additive ALTER (idempotent). ต้อง re-sync 617K หลัง migrate."""
    with get_connection() as conn:
        for col in ("district", "subdistrict"):
            try:
                conn.execute(f"ALTER TABLE cgd_winners ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # already exists


def _migrate_v120():
    """cgd_winners.proc_type — วิธีจัดซื้อ (เฉพาะเจาะจง/e-bidding/สอบราคา/คัดเลือก/...).
    ให้ cgd_intel กรองเฉพาะ competitive-set — งานเฉพาะเจาะจง 91% disc≈0 ลาก median ลง 0
    ทำให้ตัวเลขลวง. additive ALTER (idempotent). ต้อง re-sync 617K จาก residential หลัง migrate
    (row เก่า proc_type=NULL → ถูกกรองออกจาก intel จนกว่าจะ re-sync)."""
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE cgd_winners ADD COLUMN proc_type TEXT")
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v119():
    """cgd_winners — subset ผู้ชนะพื้นที่เป้าหมายจาก CGD (sync จาก residential node).
    ป้อน feature competitive intel ใน LINE (ใครชนะงานคล้ายๆ ราคาเท่าไหร่). 1 row = 1 งาน.
    sync จาก winner_history.db บนเครื่องบ้าน (CGD 403 จาก VPS) ผ่าน cgd_sync_to_vps.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cgd_winners (
                project_id   TEXT PRIMARY KEY,
                province     TEXT,
                dept         TEXT,
                project_name TEXT,
                winner       TEXT,
                winner_tin   TEXT,
                budget       INTEGER,
                win_price    INTEGER,
                discount_pct REAL,
                announce_date TEXT,
                fiscal_year  TEXT,
                synced_at    TEXT
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cgdw_province ON cgd_winners(province)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cgdw_winner ON cgd_winners(winner)")


def _migrate_v118():
    """bid_results — competitive intel: ผู้ยื่นทุกราย + ราคา ต่องาน (จาก getProcureResult).
    เก็บถาวรเพื่อวิเคราะห์งานครั้งหน้า (ใครแข่ง/ราคาเท่าไหร่/ลดกี่ %). 1 row = 1 bidder.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bid_results (
                project_id     TEXT NOT NULL,
                bidder_name    TEXT,
                bidder_tin     TEXT,
                price_proposal TEXT,
                price_agree    TEXT,
                is_winner      INTEGER NOT NULL DEFAULT 0,
                is_sme         INTEGER NOT NULL DEFAULT 0,
                result_flag    TEXT,
                fetched_at     TEXT,
                PRIMARY KEY (project_id, bidder_tin)
            )""")


def _migrate_v117():
    """notification_queue dedup model: (customer,project) → (customer,project,source_stage).
    BMS เปลี่ยนเป็น event-centric — งานเดียวแจ้งได้ 1 ครั้ง/stage (B0→D0→W0) แทน 1 ครั้ง/งาน.
    business dedup อยู่ที่ followed_jobs.last_stage_notified · queue = delivery dedup ต่อ event.
    idempotent (rebuild เฉพาะถ้ายังเป็น 2-col unique) + เก็บข้อมูลครบ (copy explicit column).
    ⚠️ rebuild table — ต้อง backup DB ก่อน deploy (A+ guardrail).
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='notification_queue'"
        ).fetchone()
        if not row:
            return  # table ยังไม่มี (จะถูกสร้างใหม่จาก CREATE — แต่ยังเป็น 2-col, รอบหน้า migrate)
        ddl = " ".join(row[0].split())
        if "source_stage)" in ddl:  # 3-col unique มีแล้ว → migrated
            return
        cols = [r[1] for r in conn.execute("PRAGMA table_info(notification_queue)")]
        if "source_stage" not in cols:
            conn.execute("ALTER TABLE notification_queue ADD COLUMN source_stage TEXT")
            cols.append("source_stage")
        conn.execute("UPDATE notification_queue SET source_stage='legacy' "
                     "WHERE source_stage IS NULL OR source_stage=''")
        conn.execute("""
            CREATE TABLE notification_queue_new (
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
                province_snapshot     TEXT,
                project_name_snapshot TEXT,
                dept_name_snapshot    TEXT,
                is_backfill           INTEGER NOT NULL DEFAULT 0,
                source_stage          TEXT,
                is_test_data          INTEGER NOT NULL DEFAULT 0,
                UNIQUE(customer_id, project_id, source_stage)
            )""")
        ordered = ["id", "customer_id", "project_id", "status", "retry_count", "next_retry_at",
                   "sending_at", "worker_id", "last_error", "last_error_type", "created_at",
                   "processed_at", "province_snapshot", "project_name_snapshot",
                   "dept_name_snapshot", "is_backfill", "source_stage", "is_test_data"]
        common = ",".join(c for c in ordered if c in cols)
        conn.execute(f"INSERT INTO notification_queue_new ({common}) SELECT {common} FROM notification_queue")
        conn.execute("DROP TABLE notification_queue")
        conn.execute("ALTER TABLE notification_queue_new RENAME TO notification_queue")


def _migrate_v116():
    """projects_seen.stage_updated_at — เวลาที่ announce_type เลื่อน stage (B0→D0→W0).
    เก็บ lifecycle timing ไว้คำนวณ B0→D0 ใช้กี่วัน (โดยไม่ต้อง event-history เต็มรูป).
    NULL = ยังไม่เคยเลื่อน (stage แรกที่เห็น = announce_date/first_seen_at).
    """
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE projects_seen ADD COLUMN stage_updated_at TEXT")
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v115():
    """followed_jobs — ⭐ watchlist (ติดตามงานข้าม stage B0→D0→W0).
    last_stage_notified = stage ล่าสุดที่แจ้งแล้ว (dedup). status active|closed.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS followed_jobs (
                customer_id          INTEGER NOT NULL,
                project_id           TEXT NOT NULL,
                starred_at           TEXT NOT NULL,
                starred_stage        TEXT,
                last_stage_notified  TEXT,
                status               TEXT NOT NULL DEFAULT 'active',
                PRIMARY KEY (customer_id, project_id)
            )""")


def _migrate_v114():
    """Add announce_date to projects_seen — สำหรับ B0 รับฟังคำวิจารณ์ freshness gate (2026-06-06).
    B0 comment period สั้น (~3วัน) + backlog เก่า first_seen=วันนี้ → ต้องดู announce_date จริง
    เพื่อกัน blast + ส่งเฉพาะช่วงรับฟังฯ. NULL = ไม่รู้ (เก่า/RSS) → gate ถือว่า not-fresh.
    """
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE projects_seen ADD COLUMN announce_date TEXT")
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v113():
    """Add deadline to project_locations — เก็บ deadline ที่ resolve ได้ (2026-06-03, INC-001 P1 audit).
    เดิมทิ้ง deadline หลัง gate → cross-check ต้อง re-resolve (แพง + PDF งานปิดหาย).
    เก็บไว้ → audit ย้อนหลังเป็น SQL query ฟรี. NULL = ยังไม่ resolve / RSS path (ไม่ resolve deadline).
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "ALTER TABLE project_locations ADD COLUMN deadline TEXT"
            )
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v112():
    """Add discovery_confirmed to project_locations — RSS Shadow Mode (2026-06-03).
    1 = Discovery/full sweep ยืนยันเห็น project นี้ (claim ได้แม้ RSS เจอก่อน).
    แยกจาก source (provenance บริสุทธิ์) — gate: RSS path enqueue เฉพาะ =1 เมื่อ BMS_RSS_NOTIFY=off.
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "ALTER TABLE project_locations ADD COLUMN discovery_confirmed INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v111():
    """Add enrichment_daily_stats table — daily snapshot of enrichment hit rate.
    Populated by Daily Digest at 08:00 (inserts yesterday's stats).
    stat_date = 'YYYY-MM-DD' (date the enrichment ran, not the digest date).
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enrichment_daily_stats (
                stat_date      TEXT PRIMARY KEY,
                total_enriched INTEGER NOT NULL DEFAULT 0,
                target_hits    INTEGER NOT NULL DEFAULT 0,
                created_at     TEXT NOT NULL
            )
        """)


def _migrate_v110():
    """Add is_test_data to customers table — hygiene boundary for test/bootstrap accounts.
    Mirrors is_test_data pattern in notification_queue/delivery_log (schema v1.6).
    Production queries: WHERE is_test_data=0 (or no filter if table is already clean).
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "ALTER TABLE customers ADD COLUMN is_test_data INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v19():
    """Add enrichment_attempts to project_locations.
    Distinguishes 'never tried' vs 'tried N times' — debug signal, not retry control.
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "ALTER TABLE project_locations ADD COLUMN enrichment_attempts INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # already exists


def _migrate_v18():
    """Add project_locations table — canonical location enriched from eGP API.

    Schema design (ChatGPT-confirmed 2026-05-29):
      - pending   = discovered but not yet enriched (API DOWN or first-seen)
      - success   = enriched from getProcurementDetail → hard location
      - failed    = API returned empty/error after MAX_LOCATION_RETRIES
      location_confidence:
        hard    = from eGP API (provinceMoiId/districtMoiId/moiName)
        soft    = from title regex (fallback, not used for notification gating)
        unknown = pending enrichment
      next_retry_at: set when API is DOWN — rss-notifier retries on next HEALTHY window
    """
    with get_connection() as conn:
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_locations (
                    project_id          TEXT PRIMARY KEY,
                    province_moi_id     TEXT,
                    district_moi_id     TEXT,
                    moi_name            TEXT,
                    province_name       TEXT,
                    latitude            TEXT,
                    longitude           TEXT,
                    location_confidence TEXT NOT NULL DEFAULT 'unknown'
                        CHECK(location_confidence IN ('hard','soft','unknown')),
                    enrichment_status   TEXT NOT NULL DEFAULT 'pending'
                        CHECK(enrichment_status IN ('pending','success','failed')),
                        -- ⚠️ source='province_api' ตั้ง 'failed' เป็น SENTINEL จงใจ (ไม่ได้ enrich พังจริง):
                        --    เป็นค่าเดียวใน 3 ค่าที่ RSS path (WHERE ='pending'/'success') ไม่แตะ → กัน blast.
                        --    สถานะจริงของ province_api อยู่ที่ qualification_status (enqueued/suppressed_*).
                        --    METRIC: วัด province_api ด้วย qualification_status เสมอ ห้ามใช้ enrichment_status
                    next_retry_at       TEXT,
                    enriched_at         TEXT,
                    created_at          TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ploc_status_retry
                    ON project_locations(enrichment_status, next_retry_at)
            """)
        except sqlite3.OperationalError:
            pass


def _migrate_v17():
    """Add project_enrichments table (per-project, shared across customers/notifications).

    Schema design (ChatGPT-confirmed 2026-05-28):
      - per-project semantics (NOT per-delivery — avoid duplication explosion)
      - enrichment_status enum: success | failed | partial  (NO 'pending' — no async worker yet)
      - extraction_confidence enum: high | medium | low
          high   = bid_submit_date + time both matched
          medium = bid_submit_date matched only
          low    = heuristic/ambiguous parse
      - parsed_at: UTC ISO8601 (Z suffix) for replay/drift analysis
      - raw_extract_json: preserved for parser-version replay
      - re-parse policy: only when parser_version changes OR manual replay
    """
    with get_connection() as conn:
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_enrichments (
                    project_id            TEXT PRIMARY KEY,
                    parser_version        TEXT NOT NULL,
                    enrichment_status     TEXT NOT NULL CHECK(enrichment_status IN ('success','failed','partial')),
                    extraction_confidence TEXT CHECK(extraction_confidence IN ('high','medium','low')),
                    parsed_at             TEXT NOT NULL,
                    parse_duration_ms     INTEGER,
                    pdf_download_ms       INTEGER,
                    bid_submit_date       TEXT,
                    bid_submit_time       TEXT,
                    eb_number             TEXT,
                    announce_date_pdf     TEXT,
                    pdf_url               TEXT,
                    raw_extract_json      TEXT,
                    parse_error_type      TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_enrich_parser_version
                    ON project_enrichments(parser_version)
            """)
        except sqlite3.OperationalError:
            pass


def _migrate_v16():
    """Add is_test_data to notification_queue + delivery_log (idempotent).
    Observability hygiene: separates synthetic fault-injection from production metrics.
    Never merged into source_stage — different semantic axis (test identity vs data provenance).
    """
    stmts = [
        "ALTER TABLE notification_queue ADD COLUMN is_test_data INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE delivery_log       ADD COLUMN is_test_data INTEGER NOT NULL DEFAULT 0",
    ]
    with get_connection() as conn:
        for sql in stmts:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass


def _migrate_v15():
    """Add source_stage to notification_queue (latent metadata, idempotent).
    source_stage is stored for future upgrade-path decisions — NOT active in delivery logic.
    Enriched re-notification semantics are intentionally deferred beyond pilot phase.
    """
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE notification_queue ADD COLUMN source_stage TEXT")
        except sqlite3.OperationalError:
            pass


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

    # ── ⭐ Follow/Star watchlist (followed_jobs) ──
    def add_follow(self, customer_id: int, project_id: str, starred_stage: str, now: str = None) -> None:
        now = now or _now()
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO followed_jobs
                  (customer_id, project_id, starred_at, starred_stage, last_stage_notified, status)
                VALUES (?,?,?,?,?,'active')
                ON CONFLICT(customer_id, project_id) DO UPDATE SET status='active'
            """, (customer_id, project_id, now, starred_stage, starred_stage))

    def get_active_follows(self) -> list[dict]:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM followed_jobs WHERE status='active'")]

    def mark_stage_notified(self, customer_id: int, project_id: str, stage: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE followed_jobs SET last_stage_notified=? WHERE customer_id=? AND project_id=?",
                (stage, customer_id, project_id))

    def close_follow(self, project_id: str, customer_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE followed_jobs SET status='closed' WHERE customer_id=? AND project_id=?",
                (customer_id, project_id))

    def record_bid_results(self, project_id: str, bidders: list, fetched_at: str = None) -> int:
        """เก็บ bidders (จาก get_procure_result) ลง bid_results — competitive intel.
        bidder dict: receiveNameTh, receiveTin, priceProposal, priceAgree, resultFlag, is_sme.
        is_winner = มี priceAgree. idempotent (INSERT OR REPLACE ตาม project+tin). คืนจำนวน row."""
        fetched_at = fetched_at or _now()
        n = 0
        with get_connection() as conn:
            for b in bidders:
                pa = (b.get("priceAgree") or "").strip()
                conn.execute("""
                    INSERT OR REPLACE INTO bid_results
                      (project_id, bidder_name, bidder_tin, price_proposal, price_agree,
                       is_winner, is_sme, result_flag, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (project_id, b.get("receiveNameTh") or "", b.get("receiveTin") or "",
                      b.get("priceProposal") or "", pa,
                      1 if pa else 0, 1 if b.get("is_sme") else 0,
                      b.get("resultFlag") or "", fetched_at))
                n += 1
        return n

    def get_bid_results(self, project_id: str) -> list[dict]:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM bid_results WHERE project_id=? ORDER BY is_winner DESC, price_agree",
                (project_id,))]

    def enqueue_for_customer(self, customer_id: int, project: dict, is_test_data: int = 0) -> int:
        """targeted enqueue ให้ลูกค้าคนเดียว (followup ⭐ — ไม่ fan-out ตาม subscription
        เพราะคนติดดาวคือคนเดียวที่ควรได้). dedup ด้วย (customer,project,source_stage).
        คืน 1 ถ้า insert ใหม่, 0 ถ้าซ้ำ stage เดิม."""
        pid = project.get("project_id", "")
        src = project.get("source_stage", "api_enriched") or "api_enriched"
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO notification_queue "
                "(customer_id, project_id, status, created_at, province_snapshot, "
                " project_name_snapshot, dept_name_snapshot, is_backfill, source_stage, is_test_data) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (customer_id, pid, "pending", _now(),
                 project.get("province") or None, project.get("project_name") or None,
                 project.get("dept_name") or None, 0, src, 1 if is_test_data else 0))
        return 1 if cur.lastrowid else 0

    def enqueue_notifications(self, project: dict,
                               min_confidence: str = "high",
                               is_test_data: int = 0) -> int:
        """
        Match project against subscriptions → insert pending items into notification_queue.
        Returns count of new queue items created.

        project keys: project_id, province, announce_type, budget,
                      project_name, dept_name, extraction_confidence,
                      is_backfill (bool/int, default False),
                      source_stage (str, default 'api_enriched')
        is_test_data: 1 = synthetic/fault-injection item, excluded from production metrics.

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
        source_stage = project.get("source_stage", "api_enriched") or "api_enriched"

        # Confidence gate
        if _CONFIDENCE_RANK.get(confidence, 0) < _CONFIDENCE_RANK.get(min_confidence, 2):
            return 0

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT s.customer_id, s.announce_types, s.min_budget, c.line_user_id,
                       c.tier, c.is_test_data
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
                    " province_snapshot, project_name_snapshot, dept_name_snapshot, "
                    " is_backfill, source_stage, is_test_data) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (row["customer_id"], project_id, "pending", now,
                     province or None, project_name, dept_name, is_backfill, source_stage,
                     1 if (is_test_data or row["is_test_data"]) else 0),  # project synthetic OR test customer
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
                       q.is_backfill, q.source_stage, q.is_test_data,
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

            # Always append audit record (propagate is_test_data for clean metric filtering)
            q_row = conn.execute(
                "SELECT is_test_data FROM notification_queue WHERE id=?", (queue_id,)
            ).fetchone()
            is_test = q_row["is_test_data"] if q_row else 0
            conn.execute(
                "INSERT INTO delivery_log "
                "(customer_id, project_id, channel, status, error_type, attempted_at, is_test_data) "
                "VALUES (?,?,?,?,?,?,?)",
                (customer_id, project_id, "line", status, error_type or None, now, is_test),
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
    # default = migrate only (init_schema) — ปลอดภัยรันบน prod (เช่น ตอน deploy)
    init_schema()
    print(f"Schema ready: {DB_PATH}")
    if "--smoke" not in sys.argv:
        sys.exit(0)
    # ===== smoke test (DEV ONLY) — seeds test customer/projects, ห้ามรันบน prod =====
    # รันด้วย: python Sebastian_Customer_DB.py --smoke  (บน dev DB เท่านั้น)
    store = SubscriptionStore()

    # Need a test customer for smoke tests — use INSERT OR IGNORE so safe on existing DB
    cid = store.add_customer("Uxxxxxxxxx_TEST", display_name="ทดสอบ บริษัทก่อสร้าง", tier="trial")
    store.add_subscription(cid, provinces=["นครพนม", "บึงกาฬ"], min_budget=500_000)
    print(f"Customer id={cid} (existing or new)")

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

    print("\nSchema v1.11 smoke test passed ✅")
