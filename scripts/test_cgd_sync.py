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
                             latitude="17.9", longitude="104.2")  # source compensate แล้ว → ค่าจริง
with db.get_connection() as cc:
    r = cc.execute("SELECT district_moi_id, moi_name, latitude, longitude FROM project_locations "
                   "WHERE project_id='LOC1'").fetchone()
assert r[0] == "480400" and r[1] == "โพนทอง", r
assert r[2] == "17.9" and r[3] == "104.2", r  # เก็บตามที่รับ ไม่ swap (latitude=lat จริง)
# regression: ไม่มีพิกัด (production เจอแน่) → ต้องไม่พัง, เก็บ "" (มีแต่ moi)
with db.get_connection() as cc:
    cc.execute("INSERT OR IGNORE INTO project_locations (project_id, location_confidence, "
               "enrichment_status, created_at) VALUES ('LOC2','unknown','pending','2026-06-07')")
db.save_project_location_raw("LOC2", district_moi_id="480400", moi_name="บ้านแพง",
                             latitude=None, longitude=None)  # ไม่มีพิกัด
with db.get_connection() as cc:
    r2 = cc.execute("SELECT moi_name, latitude, longitude FROM project_locations "
                    "WHERE project_id='LOC2'").fetchone()
assert r2[0] == "บ้านแพง" and r2[1] == "" and r2[2] == "", r2  # graceful: lat/lng ว่าง ไม่ throw
print("✅ save_project_location_raw (missing coords graceful)")
print("✅ save_project_location_raw (swap)")

# v123: migration normalize lat/lng ที่ swap (latitude>90 = สลับอยู่ → คืน)
with db.get_connection() as cc:
    cc.execute("INSERT OR IGNORE INTO project_locations (project_id, location_confidence, "
               "enrichment_status, created_at) VALUES ('SWAP1','unknown','pending','2026-06-07')")
    cc.execute("UPDATE project_locations SET latitude='104.09', longitude='17.94' WHERE project_id='SWAP1'")  # swapped
db._migrate_v123()
with db.get_connection() as cc:
    sw = cc.execute("SELECT latitude, longitude FROM project_locations WHERE project_id='SWAP1'").fetchone()
assert sw[0] == "17.94" and sw[1] == "104.09", sw   # สลับคืน latitude=lat จริง
# LOC1 (latitude=17.9 ถูกอยู่แล้ว) ไม่ถูกแตะ
with db.get_connection() as cc:
    ok = cc.execute("SELECT latitude FROM project_locations WHERE project_id='LOC1'").fetchone()
assert ok[0] == "17.9", ok
print("✅ migrate v123 (normalize swapped lat/lng)")

# Bug1: backfill projects_seen.province จาก project_locations.province_name
with db.get_connection() as cc:
    cc.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name) "
               "VALUES ('PV1','D0','','province_api','2026-06-07','ถนน ต.โพธิ์หมากแข้ง')")  # province ว่าง
    cc.execute("INSERT OR IGNORE INTO project_locations (project_id, province_name, location_confidence, "
               "enrichment_status, created_at) VALUES ('PV1','บึงกาฬ','hard','success','2026-06-07')")
n = db.backfill_provinces_from_locations()
with db.get_connection() as cc:
    pv = cc.execute("SELECT province FROM projects_seen WHERE project_id='PV1'").fetchone()
assert pv[0] == "บึงกาฬ", pv   # เติมจาก province_name
assert n >= 1, n
print("✅ backfill province from location (PV1 → บึงกาฬ)")
print("✅ PASS cgd_sync (v119 + merge idempotent + extract_subset)")
