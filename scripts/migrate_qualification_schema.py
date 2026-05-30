"""
migrate_qualification_schema.py — schema migration สำหรับ Qualification Plane (2026-05-30)

idempotent — รันซ้ำได้ปลอดภัย. ทำตาม Delivery-wiring decision (ChatGPT+Claude converged):
  1. source_epochs table (dual-epoch: province_api ใช้ table, RSS ยังใช้ txt เดิม)
     + ตั้ง province_api epoch = now → suppress backlog (Q2 decision)
  2. project_locations generalize → qualification queue หลาย source (Q3 decision: reuse ไม่สร้าง table ใหม่)
     + source, need_location (province_api รู้ province แล้ว → 0), qualification_status

⚠️ backup ก่อนรันเสมอ: cp bms_customers.db backups/..._pre_epoch_schema.db

Usage (VPS): BMS_DATA_DIR=/opt/bms/data python3 scripts/migrate_qualification_schema.py [--set-epoch]
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")


def _db_path() -> str:
    return os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"), "bms_customers.db")


def _utc_now() -> str:
    # ตรง format projects_seen.first_seen_at เพื่อให้ string-compare ถูก
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def migrate(set_epoch: bool = False):
    conn = sqlite3.connect(_db_path())
    try:
        # 1) source_epochs
        conn.execute("""CREATE TABLE IF NOT EXISTS source_epochs (
            source TEXT PRIMARY KEY, epoch_ts TEXT NOT NULL, created_at TEXT)""")
        now = _utc_now()
        existing = conn.execute(
            "SELECT epoch_ts FROM source_epochs WHERE source='province_api'").fetchone()
        if set_epoch or not existing:
            conn.execute(
                "INSERT OR REPLACE INTO source_epochs(source,epoch_ts,created_at) VALUES (?,?,?)",
                ("province_api", now, now))
            print(f"set province_api epoch = {now}")
        else:
            print(f"province_api epoch มีอยู่แล้ว = {existing[0]} (ใช้ --set-epoch เพื่อ reset)")

        # 2) project_locations columns (additive, idempotent)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(project_locations)")]
        adds = [
            ("source", "ALTER TABLE project_locations ADD COLUMN source TEXT DEFAULT 'rss'"),
            ("need_location", "ALTER TABLE project_locations ADD COLUMN need_location INTEGER DEFAULT 1"),
            ("qualification_status", "ALTER TABLE project_locations ADD COLUMN qualification_status TEXT"),
        ]
        for name, ddl in adds:
            if name not in cols:
                conn.execute(ddl); print(f"added column project_locations.{name}")
            else:
                print(f"column project_locations.{name} มีอยู่แล้ว")
        conn.commit()

        # verify
        ep = conn.execute("SELECT epoch_ts FROM source_epochs WHERE source='province_api'").fetchone()[0]
        older = conn.execute(
            "SELECT COUNT(*) FROM projects_seen WHERE source='province_api' AND first_seen_at < ?", (ep,)).fetchone()[0]
        newer = conn.execute(
            "SELECT COUNT(*) FROM projects_seen WHERE source='province_api' AND first_seen_at >= ?", (ep,)).fetchone()[0]
        print(f"verify: backlog(suppress)={older}  new(notify-eligible)={newer}  epoch={ep}")
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set-epoch", action="store_true", help="reset province_api epoch = now")
    a = ap.parse_args()
    migrate(set_epoch=a.set_epoch)
