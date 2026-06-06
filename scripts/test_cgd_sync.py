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

rows = [{"project_id": "P1", "province": "นครพนม", "dept": "อบต.x", "project_name": "ถนน",
         "winner": "บ.A", "winner_tin": "1", "budget": 1100000, "win_price": 950000,
         "discount_pct": 5.0, "announce_date": "9 เม.ย. 69", "fiscal_year": "2569",
         "proc_type": "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"}]
n = sy.merge_winners(rows, now="2026-06-06T00:00:00")
assert n == 1, n
got = sy.get_cgd_winners("นครพนม")
assert len(got) == 1 and got[0]["winner"] == "บ.A", got
assert got[0]["proc_type"] == "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", got[0]  # v120: proc_type ไหลผ่าน
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
c.execute("INSERT INTO winner_history (project_id,province,winner,win_price,fiscal_year,proc_type) "
          "VALUES ('A1','นครพนม','บ.B',500000,'2568','สอบราคา')")
c.execute("INSERT INTO winner_history (project_id,province,winner,win_price,fiscal_year) "
          "VALUES ('A2','กรุงเทพมหานคร','บ.C',999,'2568')")  # นอกพื้นที่ → ไม่ extract
c.commit(); c.close()
subset = sy.extract_subset(wh, provinces=["นครพนม", "บึงกาฬ"])
assert len(subset) == 1 and subset[0]["project_id"] == "A1", subset
assert subset[0]["proc_type"] == "สอบราคา", subset[0]  # v120: extract_subset ดึง proc_type
print("✅ PASS cgd_sync (v119 + merge idempotent + extract_subset)")
