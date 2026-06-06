"""test_deadline_fallback.py — line-sender อ่าน deadline จาก project_locations (fallback เมื่อไม่มี pdf_url)."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()
import Sebastian_LINE_Sender as ls  # noqa: E402

with db.get_connection() as conn:
    conn.execute("INSERT INTO project_locations (project_id, province_name, location_confidence, "
                 "enrichment_status, created_at, deadline) VALUES (?,?,?,?,?,?)",
                 ("J1", "นครพนม", "hard", "failed", "2026-06-06", "2026-06-20 16:30:00"))
    conn.execute("INSERT INTO project_locations (project_id, province_name, location_confidence, "
                 "enrichment_status, created_at, deadline) VALUES (?,?,?,?,?,?)",
                 ("J2", "นครพนม", "hard", "failed", "2026-06-06", None))

assert ls._deadline_from_db("J1") == ("2026-06-20", "16:30"), ls._deadline_from_db("J1")
assert ls._deadline_from_db("J2") == ("", ""), ls._deadline_from_db("J2")   # NULL deadline
assert ls._deadline_from_db("NOPE") == ("", ""), ls._deadline_from_db("NOPE")  # ไม่มี row

print("✅ PASS deadline fallback from project_locations")
