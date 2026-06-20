"""test_portal_notes.py — job_notes data layer (list/add/edit/delete + ownership)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _conn():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE job_notes(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, "
              "project_id TEXT, entry_date TEXT, note TEXT, created_at TEXT, updated_at TEXT)")
    c.execute("CREATE TABLE job_overview(customer_id INTEGER, project_id TEXT, note TEXT, "
              "created_at TEXT, updated_at TEXT, PRIMARY KEY(customer_id, project_id))")
    return c


c = _conn()
# add 2 entries (วันหลังก่อน) → list ต้องเรียง asc
pv.add_job_note(c, 1, "PID", "2026-01-22", "โทรถามรายละเอียด")
pv.add_job_note(c, 1, "PID", "2026-01-21", "โทรหาช่าง")
lst = pv.list_job_notes(c, 1, "PID")
assert [x["entry_date"] for x in lst] == ["2026-01-21", "2026-01-22"], lst
assert lst[0]["note"] == "โทรหาช่าง", lst
# validate: note ว่าง / date ผิด → ไม่เพิ่ม
pv.add_job_note(c, 1, "PID", "2026-01-23", "   ")
pv.add_job_note(c, 1, "PID", "not-a-date", "x")
assert len(pv.list_job_notes(c, 1, "PID")) == 2, "ควรยังมี 2"
# edit ของตัวเอง
nid = lst[0]["id"]
pv.edit_job_note(c, 1, nid, "2026-01-21", "โทรหาช่างปูน")
assert pv.list_job_notes(c, 1, "PID")[0]["note"] == "โทรหาช่างปูน"
# ownership: customer อื่นแก้ไม่ได้
pv.edit_job_note(c, 999, nid, "2026-01-21", "HACKED")
assert pv.list_job_notes(c, 1, "PID")[0]["note"] == "โทรหาช่างปูน", "ห้ามแก้ของคนอื่น"
# delete ของคนอื่น → ไม่หาย ; ของตัวเอง → หาย
pv.delete_job_note(c, 999, nid)
assert len(pv.list_job_notes(c, 1, "PID")) == 2
pv.delete_job_note(c, 1, nid)
assert len(pv.list_job_notes(c, 1, "PID")) == 1
# customer None → []
assert pv.list_job_notes(c, None, "PID") == []

# --- job_overview (free-form, upsert, ว่าง=ลบ, ต่อ customer) ---
assert pv.get_job_overview(c, 1, "PID") == "", "default ต้องว่าง"
pv.save_job_overview(c, 1, "PID", "ภาพรวม: งบ 1.5 ล้าน คนติดต่อโยธา")
assert pv.get_job_overview(c, 1, "PID") == "ภาพรวม: งบ 1.5 ล้าน คนติดต่อโยธา"
# upsert: แก้ทับ (ไม่เพิ่มแถวใหม่)
pv.save_job_overview(c, 1, "PID", "แก้ใหม่")
assert pv.get_job_overview(c, 1, "PID") == "แก้ใหม่"
assert c.execute("SELECT COUNT(*) FROM job_overview WHERE customer_id=1 AND project_id='PID'").fetchone()[0] == 1
# แยกต่อ customer (คนอื่นไม่เห็นของเรา)
assert pv.get_job_overview(c, 2, "PID") == ""
pv.save_job_overview(c, 2, "PID", "ของคนสอง")
assert pv.get_job_overview(c, 1, "PID") == "แก้ใหม่" and pv.get_job_overview(c, 2, "PID") == "ของคนสอง"
# ว่าง = ลบ
pv.save_job_overview(c, 1, "PID", "   ")
assert pv.get_job_overview(c, 1, "PID") == ""
assert c.execute("SELECT COUNT(*) FROM job_overview WHERE customer_id=1 AND project_id='PID'").fetchone()[0] == 0
# customer None → '' / no-op
assert pv.get_job_overview(c, None, "PID") == ""
print("OK test_portal_notes")
