"""test_portal_jobs_api.py — GET /api/portal/jobs (reuse _portal_jobs) + 403 guard."""
import os, sys, asyncio, sqlite3, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


def setup_follow():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UJOBS','x','trial',1,'2026-06-01T10:00:00+07:00','2026-06-01T10:00:00+07:00')")
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='UJOBS'").fetchone()[0]
    c.execute("INSERT OR IGNORE INTO projects_seen (project_id,announce_type,province,budget,project_name,first_seen_at) "
              "VALUES ('P1','D0','นครพนม',1000000,'งานทดสอบถนน','2026-06-01T10:00:00+07:00')")
    c.execute("INSERT OR IGNORE INTO followed_jobs "
              "(customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
              "VALUES (?,?,?,?,?,'active')", (cid, 'P1', 't', 'D0', 'D0'))
    c.commit()
    return cid


async def main():
    setup_follow()
    # 403
    try:
        await bms_api.portal_get_jobs(line_user_id='UJOBS', x_bms_secret='wrong'); assert False, "no 403"
    except HTTPException as e:
        assert e.status_code == 403
    # no customer → empty groups
    r0 = await bms_api.portal_get_jobs(line_user_id='UNONE', x_bms_secret='t')
    assert r0["ok"] and r0["jobs"]["bidding"] == [], r0
    # real follow → P1 ใน bidding (D0) + budget + starred=False
    r = await bms_api.portal_get_jobs(line_user_id='UJOBS', x_bms_secret='t')
    bidding = r["jobs"]["bidding"]
    j = next((x for x in bidding if x["project_id"] == 'P1'), None)
    assert j is not None, r["jobs"]
    assert j["budget"] == 1000000 and j["name"] == 'งานทดสอบถนน' and j["starred"] is False, j
    print("PASS test_portal_jobs_api")


asyncio.run(main())
