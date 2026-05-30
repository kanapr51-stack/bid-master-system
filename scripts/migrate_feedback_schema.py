"""
migrate_feedback_schema.py — P2 feedback capture (2026-05-31)

สร้าง table `feedback` เก็บ reaction จาก LINE reply (👍/👎/ใหม่/โทรแล้ว)
ผูกกับงานล่าสุดที่ส่งให้ user (delivery_log). idempotent.

action: useful | not_relevant | never_seen | action_taken
"""
import os
import sqlite3


def _db() -> str:
    return os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"), "bms_customers.db")


def main():
    conn = sqlite3.connect(_db())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            project_id  TEXT,
            action      TEXT NOT NULL,
            raw_text    TEXT,
            created_at  TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_action ON feedback(action)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_customer ON feedback(customer_id)")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    print(f"✅ feedback table ready (rows={n})")
    conn.close()


if __name__ == "__main__":
    main()
