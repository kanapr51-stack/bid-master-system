"""test_portal_cancelled.py — งาน lsn=CANCELLED → กลุ่ม cancelled (ไม่ใช่ prelim) + HTML."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()

with db.get_connection() as c:
    c.execute("INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('U','n','trial',1,'t','t')")
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='U'").fetchone()[0]
    for pid, ann, nm in [("PC", "D0", "ถนน ยกเลิก"), ("PP", "D0", "ถนน PRELIM")]:
        c.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
                  "VALUES (?,?,?,?,?,?)", (pid, nm, ann, "นครพนม", 1000000, "t"))
    # PC = ยกเลิก (lsn=CANCELLED)  ·  PP = สรุปราคาเบื้องต้น (lsn=PRELIM)
    for pid, lsn in [("PC", "CANCELLED"), ("PP", "PRELIM")]:
        c.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                  "VALUES (?,?,?,?,?,?)", (cid, pid, "t", "D0", lsn, "active"))
    # PP มีราคาเสนอ (ทำให้เข้า prelim group ตามปกติ)
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,fetched_at) "
              "VALUES ('PP','','PT1','820000','',0,'t')")

import bms_api as api
g = api._portal_jobs("U")
assert g is not None, g

# PC ต้องอยู่ใน cancelled — ไม่ใช่ prelim/bidding/won
assert [j["project_id"] for j in g.get("cancelled", [])] == ["PC"], g.get("cancelled")
assert all(j["project_id"] != "PC" for j in g["prelim"]), "PC ต้องไม่อยู่ใน prelim"
assert all(j["project_id"] != "PC" for j in g["bidding"]), "PC ต้องไม่อยู่ใน bidding"
# PP ยังอยู่ prelim ตามเดิม
assert [j["project_id"] for j in g["prelim"]] == ["PP"], g["prelim"]
print("✅ grouping — PC=cancelled, PP=prelim (PC หลุดจากสรุปราคาเบื้องต้น)")

# HTML แสดงกลุ่มยกเลิก
html = api._portal_page_html(g, token="tok")
assert "ยกเลิกโครงการ" in html, "HTML ต้องมีหัวข้อกลุ่มยกเลิก"
assert "ถนน ยกเลิก" in html, "HTML ต้องมีชื่องานยกเลิก"
print("✅ HTML แสดงกลุ่ม ❌ ยกเลิกโครงการ")

print("✅ ALL PASS test_portal_cancelled")
