"""test_queue_stage_dedup.py — A+ migration v117: (cust,proj) → (cust,proj,stage).
ทดสอบ (1) migration บน legacy data เก็บข้อมูลครบ + (2) stage dedup ทำงาน."""
import os, tempfile, sys, sqlite3
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402

# ── (1) migration บน legacy table (2-col unique + source_stage NULL) ──
dbp = db.DB_PATH
conn = sqlite3.connect(dbp)
conn.executescript("""
    CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, line_user_id TEXT, display_name TEXT);
    CREATE TABLE notification_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL, project_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', retry_count INTEGER NOT NULL DEFAULT 0,
        next_retry_at TEXT, sending_at TEXT, worker_id TEXT, last_error TEXT, last_error_type TEXT,
        created_at TEXT NOT NULL, processed_at TEXT,
        province_snapshot TEXT, project_name_snapshot TEXT, dept_name_snapshot TEXT,
        is_backfill INTEGER NOT NULL DEFAULT 0, source_stage TEXT,
        UNIQUE(customer_id, project_id));
    INSERT INTO customers (id, line_user_id, display_name) VALUES (1,'U1','พ่อ');
    INSERT INTO notification_queue (customer_id,project_id,status,created_at,source_stage)
        VALUES (1,'OLD1','sent','2026-06-01',NULL);
    INSERT INTO notification_queue (customer_id,project_id,status,created_at,source_stage)
        VALUES (1,'OLD2','sent','2026-06-02','province_tor_review');
""")
conn.commit(); conn.close()

db._migrate_v117()

conn = sqlite3.connect(dbp); conn.row_factory = sqlite3.Row
# legacy rows survive + NULL → 'legacy'
rows = {r["project_id"]: r["source_stage"] for r in conn.execute("SELECT project_id, source_stage FROM notification_queue")}
assert rows == {"OLD1": "legacy", "OLD2": "province_tor_review"}, rows
# new 3-col unique มีจริง
ddl = " ".join(conn.execute("SELECT sql FROM sqlite_master WHERE name='notification_queue'").fetchone()[0].split())
assert "source_stage)" in ddl, ddl
conn.close()

# idempotent: รันซ้ำไม่พัง + ไม่เปลี่ยนข้อมูล
db._migrate_v117()
conn = sqlite3.connect(dbp)
assert conn.execute("SELECT COUNT(*) FROM notification_queue").fetchone()[0] == 2
conn.close()

# ── (2) stage dedup ผ่าน enqueue_for_customer ──
s = db.SubscriptionStore()
assert s.enqueue_for_customer(1, {"project_id": "A", "source_stage": "province_tor_review"}) == 1
assert s.enqueue_for_customer(1, {"project_id": "A", "source_stage": "followed_bid_open"}) == 1   # คนละ stage = ส่งได้
assert s.enqueue_for_customer(1, {"project_id": "A", "source_stage": "followed_bid_open"}) == 0   # ซ้ำ stage = ไม่ส่ง
conn = sqlite3.connect(dbp)
assert conn.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='A'").fetchone()[0] == 2
conn.close()

print("✅ PASS queue stage dedup + migration v117 (legacy preserved)")
