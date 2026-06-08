"""test_bms_follow.py — _follow_status / _record_follow / _record_unfollow / _follow_page_html."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id, display_name, tier, active, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?)", ("Uabc", "Test", "trial", 1, "2026-06-08T10:00:00", "2026-06-08T10:00:00"))
    conn.execute("INSERT INTO projects_seen (project_id, project_name, announce_type, province, budget, first_seen_at) "
                 "VALUES (?,?,?,?,?,?)", ("P1", "งานทดสอบถนน", "D0", "นครพนม", 5000000, "2026-06-08T10:00:00"))

import bms_api as api

# ยังไม่ติดตาม → inactive
assert api._follow_status("Uabc", "P1") == "inactive"
# follow → active
api._record_follow("Uabc", "P1")
assert api._follow_status("Uabc", "P1") == "active"
# unfollow → inactive (status='unfollowed')
res = api._record_unfollow("Uabc", "P1")
assert res and res[1] == "P1", res
assert api._follow_status("Uabc", "P1") == "inactive"
# re-follow → active อีกครั้ง (ON CONFLICT reactivate)
api._record_follow("Uabc", "P1")
assert api._follow_status("Uabc", "P1") == "active"
# ลูกค้าไม่รู้จัก → no_customer
assert api._follow_status("Uxxx", "P1") == "no_customer"

# HTML render — 3 สถานะ
d = api._project_detail("P1")
h_active = api._follow_page_html("tok", "active", d, "8 มิ.ย. 09:00", 2000000000)
assert "ยกเลิกการติดตาม" in h_active and "งานทดสอบถนน" in h_active and "ลิงก์นี้ใช้ได้ถึง" in h_active
h_inactive = api._follow_page_html("tok", "inactive", d, "", 2000000000)
assert "ติดตามงานนี้" in h_inactive and "ยกเลิกการติดตาม" not in h_inactive
h_nocust = api._follow_page_html("tok", "no_customer", {}, "", 2000000000)
assert "เพิ่มเพื่อน" in h_nocust
h_invalid = api._follow_page_html("tok", "invalid", {}, "", 0)
assert ("หมดอายุ" in h_invalid) or ("ไม่ถูกต้อง" in h_invalid)

print("OK test_bms_follow")
