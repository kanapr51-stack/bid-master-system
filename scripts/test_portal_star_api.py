"""test_portal_star_api.py — POST /api/portal/star toggle job_stars."""
import os, sys, asyncio, sqlite3, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


class FakeReq:
    def __init__(self, d): self._d = d
    async def json(self): return self._d


async def main():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('USTAR','x','trial',1,'t','t')"); c.commit()
    # 404 ไม่มี customer
    try:
        await bms_api.portal_star_toggle_json(FakeReq({'line_user_id': 'UNONE', 'project_id': 'P9'}), x_bms_secret='t'); assert False
    except HTTPException as e:
        assert e.status_code == 404
    # 403 secret ผิด
    try:
        await bms_api.portal_star_toggle_json(FakeReq({'line_user_id': 'USTAR', 'project_id': 'P9'}), x_bms_secret='x'); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # toggle on
    r1 = await bms_api.portal_star_toggle_json(FakeReq({'line_user_id': 'USTAR', 'project_id': 'P9'}), x_bms_secret='t')
    assert r1["starred"] is True, r1
    # toggle off
    r2 = await bms_api.portal_star_toggle_json(FakeReq({'line_user_id': 'USTAR', 'project_id': 'P9'}), x_bms_secret='t')
    assert r2["starred"] is False, r2
    print("PASS test_portal_star_api")


asyncio.run(main())
