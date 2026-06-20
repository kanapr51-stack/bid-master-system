"""test_portal_stars.py — job_stars data layer (toggle_star + starred_project_ids, ⭐ ที่สนใจ ชั้นที่สอง)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _conn():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE job_stars(customer_id INTEGER, project_id TEXT, created_at TEXT, "
              "PRIMARY KEY(customer_id, project_id))")
    return c


c = _conn()
# toggle ครั้งแรก = ติดดาว
assert pv.toggle_star(c, 1, "PA") is True
assert pv.starred_project_ids(c, 1) == {"PA"}
# toggle ครั้งสอง (งานเดิม) = ถอดดาว กลับสถานะเดิม
assert pv.toggle_star(c, 1, "PA") is False
assert pv.starred_project_ids(c, 1) == set()
# ดาวหลายงาน
pv.toggle_star(c, 1, "PA")
pv.toggle_star(c, 1, "PB")
assert pv.starred_project_ids(c, 1) == {"PA", "PB"}
# cross-customer isolation: คนละคนไม่เห็นดาวกัน
assert pv.starred_project_ids(c, 2) == set()
pv.toggle_star(c, 2, "PA")
assert pv.starred_project_ids(c, 1) == {"PA", "PB"} and pv.starred_project_ids(c, 2) == {"PA"}
# customer None → no-op, คืนค่าว่างเสมอ
assert pv.toggle_star(c, None, "PA") is False
assert pv.starred_project_ids(c, None) == set()
# ไม่มี duplicate (customer_id, project_id) — PK กันระดับ DB
n = c.execute("SELECT COUNT(*) FROM job_stars WHERE customer_id=1 AND project_id='PA'").fetchone()[0]
assert n == 1, f"ต้องมีแถวเดียว เจอ {n}"
print("OK test_portal_stars")
