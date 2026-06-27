"""test_daily_digest.py — Daily summary digest: fetch qualified_digest jobs, list, mark listed."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
# qualification_status เพิ่มผ่าน migrate_qualification_schema (ไม่อยู่ใน init_schema) → ALTER ใน test setup
with db.get_connection() as _c:
    cols = [r[1] for r in _c.execute("PRAGMA table_info(project_locations)")]
    if "qualification_status" not in cols:
        _c.execute("ALTER TABLE project_locations ADD COLUMN qualification_status TEXT")
import Sebastian_Daily_User_Summary as dus

def _seed():
    with db.get_connection() as conn:
        for pid, prov, name, fs in [
            ("J1", "นครพนม", "ก่อสร้างถนน คสล. หมู่ 1", "2026-06-27T00:00:00"),
            ("J2", "บึงกาฬ", "ก่อสร้างรางระบายน้ำ", "2026-06-27T00:00:00"),
            ("J3", "นครพนม", "งานลิสต์ไปแล้ว", "2026-06-26T00:00:00")]:
            conn.execute("INSERT OR REPLACE INTO projects_seen "
                         "(project_id, province, project_name, first_seen_at) VALUES (?,?,?,?)",
                         (pid, prov, name, fs))
        for pid, st in [("J1", "qualified_digest"), ("J2", "qualified_digest"),
                        ("J3", "digest_listed")]:   # J3 ลิสต์ไปแล้ว ไม่ควรกลับมา
            conn.execute("INSERT OR REPLACE INTO project_locations "
                         "(project_id, created_at, qualification_status) VALUES (?,?,?)",
                         (pid, "2026-06-27T00:00:00", st))

def test_fetch_digest_jobs():
    _seed()
    with db.get_connection() as conn:
        jobs = dus.fetch_digest_jobs(conn)
    ids = {j["project_id"] for j in jobs}
    assert ids == {"J1", "J2"}, ids                 # เฉพาะ qualified_digest (ไม่เอา digest_listed)
    assert all(j["name"] for j in jobs)
    print("✅ fetch_digest_jobs — เฉพาะ qualified_digest")

def test_build_message_lists_digest():
    jobs = [{"project_id": "J1", "name": "ก่อสร้างถนน คสล. หมู่ 1", "deadline_time": ""},
            {"project_id": "J2", "name": "ก่อสร้างรางระบายน้ำ", "deadline_time": ""}]
    msg = dus.build_message("กัญจน์", 0, digest_jobs=jobs)
    assert "2 งาน" in msg and "ก่อสร้างถนน" in msg and "รางระบายน้ำ" in msg, msg
    # ไม่มีงาน → ข้อความว่าง
    msg0 = dus.build_message("กัญจน์", 0, digest_jobs=[])
    assert "ยังไม่มีงาน" in msg0, msg0
    print("✅ build_message ลิสต์งาน digest / กรณีไม่มีงาน")

def test_mark_digest_listed():
    _seed()
    with db.get_connection() as conn:
        n = dus.mark_digest_listed(conn, ["J1", "J2"])
        assert n == 2, n
        jobs2 = dus.fetch_digest_jobs(conn)
    assert jobs2 == [], jobs2                        # mark แล้ว → ไม่กลับมาในรอบถัดไป (กันลิสต์ซ้ำ)
    print("✅ mark_digest_listed — กันลิสต์ซ้ำวันถัดไป")

test_fetch_digest_jobs()
test_build_message_lists_digest()
test_mark_digest_listed()
print("ALL PASS daily_digest")
