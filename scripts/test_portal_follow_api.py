"""test_portal_follow_api.py — POST /api/portal/follow → followed_jobs active + ตัดออกจาก discover."""
import os, sys, json, sqlite3, asyncio, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


class FakeReq:
    def __init__(self, body): self._b = body
    async def json(self): return self._b


def setup():
    now = bms_api._now()
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UFOL','x','trial',1,?,?)", (now, now))
    c.execute("INSERT OR IGNORE INTO projects_seen (project_id,announce_type,province,budget,project_name,first_seen_at) "
              "VALUES ('PFOL','D0','นครพนม',5000000,'ก่อสร้างถนนคอนกรีต',?)", (now,))
    c.commit()


async def main():
    setup()
    # 403
    try:
        await bms_api.portal_follow_job(FakeReq({"line_user_id": "UFOL", "project_id": "PFOL"}), x_bms_secret='bad'); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # no customer → 404
    try:
        await bms_api.portal_follow_job(FakeReq({"line_user_id": "UNONE", "project_id": "PFOL"}), x_bms_secret='t'); assert False
    except HTTPException as e:
        assert e.status_code == 404
    # happy → followed_jobs active
    r = await bms_api.portal_follow_job(FakeReq({"line_user_id": "UFOL", "project_id": "PFOL"}), x_bms_secret='t')
    assert r["ok"] and r["followed"] is True, r
    c = sqlite3.connect(bms_api.DB_PATH)
    st = c.execute("SELECT status FROM followed_jobs fj JOIN customers cu ON cu.id=fj.customer_id "
                   "WHERE cu.line_user_id='UFOL' AND fj.project_id='PFOL'").fetchone()
    assert st and st[0] == 'active', st
    print("PASS test_portal_follow_api")


asyncio.run(main())
