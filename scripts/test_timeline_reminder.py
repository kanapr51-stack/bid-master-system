"""test_timeline_reminder.py — find_due_reminders + build_reminder_text (job_notes due today)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import timeline_reminder as tr


def _conn():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, line_user_id TEXT, display_name TEXT, active INT)")
    c.execute("CREATE TABLE projects_seen(project_id TEXT, project_name TEXT)")
    c.execute("CREATE TABLE job_notes(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, "
              "project_id TEXT, entry_date TEXT, note TEXT, created_at TEXT, updated_at TEXT)")
    c.execute("INSERT INTO customers VALUES (1,'U1','กัญจน์',1)")
    c.execute("INSERT INTO customers VALUES (2,'U2','คนสอง',1)")
    c.execute("INSERT INTO customers VALUES (3,'U3','ปิดอยู่',0)")     # inactive
    c.execute("INSERT INTO projects_seen VALUES ('PA','งานถนน A')")
    c.execute("INSERT INTO projects_seen VALUES ('PB','งานสะพาน B')")
    def add(cid, pid, d, note):
        c.execute("INSERT INTO job_notes (customer_id,project_id,entry_date,note,created_at) "
                  "VALUES (?,?,?,?,?)", (cid, pid, d, note, "t"))
    add(1, "PA", "2026-01-21", "โทรหาช่าง")          # วันนี้
    add(1, "PA", "2026-01-21", "เช็คแบบ")            # วันนี้ งานเดียวกัน
    add(1, "PB", "2026-01-22", "ดูหน้างาน")          # พรุ่งนี้ อีกงาน
    add(1, "PA", "2026-01-25", "อีกหลายวัน")          # นอกช่วง — ไม่เข้า
    add(2, "PA", "2026-01-21", "ของคนสอง")
    add(3, "PA", "2026-01-21", "ของคนปิด")            # inactive — ไม่เข้า
    return c


c = _conn()
# เตือนวันนี้ (21) + พรุ่งนี้ (22)
groups = tr.find_due_reminders(c, "2026-01-21", "2026-01-22")
byu = {g["line_user_id"]: g for g in groups}
assert set(byu) == {"U1", "U2"}, "ต้องมีแค่ active"                   # U3 inactive ตัดออก
u1 = byu["U1"]
assert len(u1["jobs"]) == 2, u1["jobs"]                               # PA(วันนี้) + PB(พรุ่งนี้)
pa = next(j for j in u1["jobs"] if j["project_id"] == "PA")
assert len(pa["items"]) == 2 and all(it["when"] == "วันนี้" for it in pa["items"]), pa
pb = next(j for j in u1["jobs"] if j["project_id"] == "PB")
assert pb["items"][0]["when"] == "พรุ่งนี้", pb
assert "อีกหลายวัน" not in str(u1), "วันนอกช่วงต้องไม่หลุดเข้ามา"
# build text — มีป้าย [วันนี้]/[พรุ่งนี้]
txt = tr.build_reminder_text(u1)
assert "เตือนไทม์ไลน์งาน" in txt and "21 ม.ค. 2569" in txt, txt
assert "[วันนี้] โทรหาช่าง" in txt and "[พรุ่งนี้] ดูหน้างาน" in txt, txt
# เตือนเฉพาะวันนี้ (ไม่ส่ง tomorrow) → PB ไม่เข้า
g1 = tr.find_due_reminders(c, "2026-01-21")
assert all(j["project_id"] != "PB" for g in g1 for j in g["jobs"]), "single-date ต้องไม่มีพรุ่งนี้"
assert tr.find_due_reminders(c, "2030-01-01", "2030-01-02") == []
print("OK test_timeline_reminder")
