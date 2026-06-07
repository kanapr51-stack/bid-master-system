"""test_cgd_sync.py — merge subset เข้า cgd_winners (idempotent) + extract_subset."""
import os, tempfile, sys, sqlite3
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db; db.init_schema()   # ต้องสร้าง cgd_winners (v119)
import cgd_sync_to_vps as sy

# v119: cgd_winners table ถูกสร้างโดย init_schema
with db.get_connection() as c:
    cols = [r[1] for r in c.execute("PRAGMA table_info(cgd_winners)")]
assert "project_id" in cols and "winner" in cols and "win_price" in cols, cols
assert "district" in cols and "subdistrict" in cols, cols  # v121

rows = [{"project_id": "P1", "province": "นครพนม", "dept": "อบต.x", "project_name": "ถนน",
         "winner": "บ.A", "winner_tin": "1", "budget": 1100000, "win_price": 950000,
         "discount_pct": 5.0, "announce_date": "9 เม.ย. 69", "fiscal_year": "2569",
         "proc_type": "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
         "district": "บ้านแพง", "subdistrict": "โพนทอง"}]
n = sy.merge_winners(rows, now="2026-06-06T00:00:00")
assert n == 1, n
got = sy.get_cgd_winners("นครพนม")
assert len(got) == 1 and got[0]["winner"] == "บ.A", got
assert got[0]["proc_type"] == "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", got[0]  # v120: proc_type ไหลผ่าน
assert got[0]["district"] == "บ้านแพง" and got[0]["subdistrict"] == "โพนทอง", got[0]  # v121
sy.merge_winners(rows, now="2026-06-07T00:00:00")  # idempotent (INSERT OR REPLACE ตาม project_id)
assert len(sy.get_cgd_winners("นครพนม")) == 1

# extract_subset: ดึง subset เป้าหมายจาก winner_history.db (residential)
wh = str(Path(os.environ["BMS_DATA_DIR"]) / "wh.db")
c = sqlite3.connect(wh)
c.execute("""CREATE TABLE winner_history (project_id TEXT PRIMARY KEY, fiscal_year TEXT,
    province TEXT, district TEXT, subdistrict TEXT, project_name TEXT, dept TEXT,
    proc_type TEXT, winner TEXT, winner_tin TEXT, budget INTEGER, mid_price INTEGER,
    win_price INTEGER, discount_pct REAL, price_valid INTEGER, announce_date TEXT,
    contract_no TEXT, sign_date TEXT, status TEXT, source TEXT, raw_json TEXT)""")
c.execute("INSERT INTO winner_history (project_id,province,district,subdistrict,winner,win_price,fiscal_year,proc_type) "
          "VALUES ('A1','นครพนม','บ้านแพง','โพนทอง','บ.B',500000,'2568','สอบราคา')")
c.execute("INSERT INTO winner_history (project_id,province,winner,win_price,fiscal_year) "
          "VALUES ('A2','กรุงเทพมหานคร','บ.C',999,'2568')")  # นอกพื้นที่ → ไม่ extract
c.commit(); c.close()
subset = sy.extract_subset(wh, provinces=["นครพนม", "บึงกาฬ"])
assert len(subset) == 1 and subset[0]["project_id"] == "A1", subset
assert subset[0]["proc_type"] == "สอบราคา", subset[0]  # v120: extract_subset ดึง proc_type
assert subset[0]["district"] == "บ้านแพง" and subset[0]["subdistrict"] == "โพนทอง", subset[0]  # v121

# save_project_location_raw — persist raw location + swap lat/lng (eGP API mislabels)
with db.get_connection() as cc:
    cc.execute("INSERT OR IGNORE INTO project_locations (project_id, location_confidence, "
               "enrichment_status, created_at) VALUES ('LOC1','unknown','pending','2026-06-07')")
db.save_project_location_raw("LOC1", district_moi_id="480400", moi_name="โพนทอง",
                             api_latitude="104.2", api_longitude="17.9")  # API: lat field=real lng
with db.get_connection() as cc:
    r = cc.execute("SELECT district_moi_id, moi_name, latitude, longitude FROM project_locations "
                   "WHERE project_id='LOC1'").fetchone()
assert r[0] == "480400" and r[1] == "โพนทอง", r
assert r[2] == "17.9" and r[3] == "104.2", r  # swapped: stored latitude=real lat(17.9), longitude=real lng(104.2)
print("✅ save_project_location_raw (swap)")
print("✅ PASS cgd_sync (v119 + merge idempotent + extract_subset)")
