"""test_portal_notes.py — job_notes data layer (list/add/edit/delete + ownership)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _conn():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE job_notes(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, "
              "project_id TEXT, entry_date TEXT, note TEXT, created_at TEXT, updated_at TEXT)")
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
print("OK test_portal_notes")
