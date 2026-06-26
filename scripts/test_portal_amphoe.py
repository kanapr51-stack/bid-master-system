"""test_portal_amphoe.py — board แสดง อ. (อำเภอ) จากตำบล: unique→โชว์, กำกวม/ไม่มี→ข้าม."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()

# monkeypatch geo: นาทม→unique, กำกวม→2 อำเภอ, อื่น→[]
import geo_reverse
geo_reverse.amphoes_of_tambon = lambda prov, tb: {"นาทม": ["นาทม"], "กำกวม": ["เอ", "บี"]}.get(tb, [])

with db.get_connection() as c:
    c.execute("INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('U','n','trial',1,'t','t')")
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='U'").fetchone()[0]
    # J1 ตำบล unique, J2 ไม่มีตำบล (งานระดับจังหวัด), J3 ตำบลกำกวม
    for pid, prov, moi in [("J1", "นครพนม", "นาทม"), ("J2", "บึงกาฬ", None), ("J3", "นครพนม", "กำกวม")]:
        c.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
                  "VALUES (?,?,?,?,?,?)", (pid, "งาน " + pid, "D0", prov, 1000000, "t"))
        c.execute("INSERT INTO project_locations (project_id,moi_name,province_name,created_at) VALUES (?,?,?,?)",
                  (pid, moi, prov, "t"))
        c.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                  "VALUES (?,?,?,?,?,?)", (cid, pid, "t", "D0", "D0", "active"))

import bms_api as api
g = api._portal_jobs("U")
loc = {j["project_id"]: j["location"] for j in g["bidding"]}

assert loc["J1"] == "ต.นาทม อ.นาทม จ.นครพนม", loc["J1"]      # ตำบล unique → มี อ.
assert loc["J2"] == "จ.บึงกาฬ", loc["J2"]                      # ไม่มีตำบล → แค่ จ.
assert loc["J3"] == "ต.กำกวม จ.นครพนม", loc["J3"]             # ตำบลกำกวม → ไม่โชว์ อ.
print("✅ ALL PASS test_portal_amphoe")
