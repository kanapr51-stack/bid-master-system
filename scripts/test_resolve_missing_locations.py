"""test_resolve_missing_locations.py — locfill pass: เติม moi จาก detail/dept, retry, selector."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_ENV"] = "dev"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
# project_locations qualification columns (เพิ่มโดย migrate_qualification_schema.py บน prod, ไม่ใช่ init_schema)
with db.get_connection() as _c:
    _cols = [r[1] for r in _c.execute("PRAGMA table_info(project_locations)")]
    for _name, _ddl in [("source", "ALTER TABLE project_locations ADD COLUMN source TEXT DEFAULT 'rss'"),
                        ("need_location", "ALTER TABLE project_locations ADD COLUMN need_location INTEGER DEFAULT 1"),
                        ("qualification_status", "ALTER TABLE project_locations ADD COLUMN qualification_status TEXT")]:
        if _name not in _cols:
            _c.execute(_ddl)
import Sebastian_Enrichment_Worker as w


def seed(pid, moi=None, attempts=0, source="province_api", dept="", retry=None):
    with db.get_connection() as c:
        c.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name,dept_name) "
                  "VALUES (?,?,?,?,?,?,?)", (pid, "D0", "นครพนม", "province_api", "2026-06-01", "งาน " + pid, dept))
        c.execute("INSERT INTO project_locations (project_id,province_name,moi_name,source,enrichment_status,need_location,enrichment_attempts,next_retry_at,created_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (pid, "นครพนม", moi, source, "failed", 0, attempts, retry, "2026-06-01"))


def moi_of(pid):
    with db.get_connection() as c:
        return c.execute("SELECT moi_name,district_moi_id,latitude,enrichment_attempts FROM project_locations WHERE project_id=?", (pid,)).fetchone()


seed("A")                                              # detail มี moi
seed("B", dept="องค์การบริหารส่วนตำบลโพนแพง")          # detail ไม่มี moi → dept fallback
seed("C", dept="แขวงทางหลวงนครพนม")                     # ไม่มีทั้งคู่ → attempt+1
seed("D", attempts=3)                                  # เกิน max → ไม่แตะ
seed("E", moi="มีแล้ว")                                # moi เต็ม → ข้าม
seed("F", source="rss")                                # RSS → ข้าม


def fake_detail(pid):
    if pid == "A":
        return {"valid": True, "moi_name": "นาทม", "district_moi_id": "481100", "latitude": "17.85", "longitude": "104.02"}
    if pid == "D":
        return {"valid": True, "moi_name": "ไม่ควรเซฟ", "district_moi_id": "x", "latitude": "", "longitude": ""}
    return {"valid": False}  # B, C


n = w.resolve_missing_locations(lambda m: None, resolve_detail=fake_detail, sleep_sec=0)

a = moi_of("A"); assert a[0] == "นาทม" and a[1] == "481100" and a[2] == "17.85", a
assert moi_of("B")[0] == "โพนแพง", moi_of("B")
cc = moi_of("C"); assert cc[0] is None and cc[3] == 1, cc
dd = moi_of("D"); assert dd[0] is None and dd[3] == 3, dd
assert moi_of("E")[0] == "มีแล้ว", moi_of("E")
assert moi_of("F")[0] is None, moi_of("F")
assert n == 2, n
print("✅ ALL PASS test_resolve_missing_locations")
