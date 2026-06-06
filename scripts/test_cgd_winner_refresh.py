"""test_cgd_winner_refresh.py — incremental upsert winner_history (dedup project_id)."""
import os, tempfile, sys, sqlite3
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_winner_refresh as wr

DB = str(Path(os.environ["BMS_DATA_DIR"]) / "wh_test.db")

def rec(pid, prov, name):
    return {"รหัสโครงการ": pid, "ปีงบประมาณ": "2569", "จังหวัด": prov,
            "ชื่อโครงการ": name, "ชื่อหน่วยงาน": "อบต.x", "วิธีจัดซื้อฯ": "e-bidding",
            "ราคากลาง(บาท)": "1000000", "ราคาตกลงซื้อ/จ้าง": "950000",
            "งบประมาณ(บาท)": "1100000", "วันที่ประกาศ": "9-เม.ย.-69",
            "ผู้เสนอราคาที่ชนะการเสนอราคา": "บ.A"}

# รอบ 1: 2 records → insert 2
calls = {"n": 0}
def fake_search(rid, province, limit, offset):
    if offset > 0: return {"result": {"records": [], "total": 2}}
    return {"result": {"records": [rec("P1", province, "ถนน"), rec("P2", province, "อาคาร")], "total": 2}}

n1 = wr.refresh_year(DB, "2569", "rid-x", ["นครพนม"], search=fake_search)
assert n1 == 2, n1
c = sqlite3.connect(DB)
assert c.execute("SELECT COUNT(*) FROM winner_history").fetchone()[0] == 2
assert c.execute("SELECT win_price FROM winner_history WHERE project_id='P1'").fetchone()[0] == 950000
c.close()

# รอบ 2: records เดิม → INSERT OR IGNORE → ไม่เพิ่ม (idempotent)
n2 = wr.refresh_year(DB, "2569", "rid-x", ["นครพนม"], search=fake_search)
c = sqlite3.connect(DB)
assert c.execute("SELECT COUNT(*) FROM winner_history").fetchone()[0] == 2, "idempotent fail"
c.close()
print("✅ PASS cgd_winner_refresh")
