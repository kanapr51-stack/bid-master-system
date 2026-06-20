"""test_job_notes_schema.py — init_schema สร้างตาราง job_notes."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as c:
    cols = [r[1] for r in c.execute("PRAGMA table_info(job_notes)")]
assert cols, "ตาราง job_notes ไม่ถูกสร้าง"
for need in ["id", "customer_id", "project_id", "entry_date", "note", "created_at", "updated_at"]:
    assert need in cols, f"ขาดคอลัมน์ {need}: {cols}"
print("OK test_job_notes_schema")
