"""ตาราง push_subscriptions + webpush_delivery_log ถูกสร้างโดย init_schema + insert/select ได้"""
import os, sys, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"))
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db
db.init_schema()

with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                 "VALUES ('UPUSH', 'x', 'trial', '2026-07-14T00:00:00+07:00', '2026-07-14T00:00:00+07:00')")
    cid = conn.execute("SELECT id FROM customers WHERE line_user_id='UPUSH'").fetchone()["id"]
    conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, user_agent, created_at) "
                 "VALUES (?, 'https://push.example/ep1', 'pk', 'ak', 'UA', '2026-07-14T00:00:00+07:00')", (cid,))
    sid = conn.execute("SELECT id FROM push_subscriptions WHERE endpoint='https://push.example/ep1'").fetchone()["id"]
    conn.execute("INSERT INTO webpush_delivery_log (subscription_id, customer_id, project_id, source_stage, status, error, attempted_at) "
                 "VALUES (?, ?, 'P1', 'api_enriched', 'sent', '', '2026-07-14T00:00:01+07:00')", (sid, cid))
    row = conn.execute("SELECT status FROM webpush_delivery_log WHERE subscription_id=?", (sid,)).fetchone()
    assert row["status"] == "sent", row
    # endpoint UNIQUE
    import sqlite3
    try:
        conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, created_at) "
                     "VALUES (?, 'https://push.example/ep1', 'pk2', 'ak2', 'x')", (cid,))
        assert False, "endpoint UNIQUE ไม่ทำงาน"
    except sqlite3.IntegrityError:
        pass

print("PASS test_webpush_schema")
