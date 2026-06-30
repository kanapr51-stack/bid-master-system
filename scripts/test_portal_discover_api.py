"""test_portal_discover_api.py — GET /api/portal/discover (per-user matching, ตัด followed)."""
import os, sys, json, sqlite3, asyncio, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException

FUTURE = "2099-12-31"   # deadline ยังไม่หมด
FRESH = bms_api._now()  # B0 first_seen วันนี้ → tor_is_fresh ผ่าน


def setup():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at,notes) "
              "VALUES ('UDISC','x','trial',1,?,?,?)",
              (FRESH, FRESH, json.dumps({"classes": [{"keywords": ["คอนกรีต", "ท่อ"], "budgetMinBaht": 1000000, "budgetMaxBaht": 50000000}]})))
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='UDISC'").fetchone()[0]
    c.execute("INSERT OR IGNORE INTO subscriptions (customer_id,active,created_at,updated_at) VALUES (?,1,?,?)", (cid, FRESH, FRESH))
    sid = c.execute("SELECT id FROM subscriptions WHERE customer_id=?", (cid,)).fetchone()[0]
    c.execute("INSERT OR IGNORE INTO subscription_provinces (subscription_id,province) VALUES (?,'นครพนม')", (sid,))
    # งานในพื้นที่ + keyword + งบ → ควรเข้า
    rows = [
        ('D_MATCH', 'D0', 'นครพนม', 5000000, 'ก่อสร้างถนนคอนกรีตสาย 1'),     # biddable
        ('D_FOLLOWED', 'D0', 'นครพนม', 5000000, 'วางท่อระบายน้ำคอนกรีต'),     # ตาม followed แล้ว → ตัด
        ('D_OTHERPROV', 'D0', 'ชลบุรี', 5000000, 'ก่อสร้างถนนคอนกรีต'),       # นอกพื้นที่ → ตัด
        ('D_NOKW', 'D0', 'นครพนม', 5000000, 'ซื้อเวชภัณฑ์'),                  # ไม่มี keyword → ตัด
        ('D_LOWBUDGET', 'D0', 'นครพนม', 100000, 'ก่อสร้างถนนคอนกรีต'),        # ต่ำกว่างบ → ตัด
        ('B_FRESH', 'B0', 'นครพนม', 5000000, 'ก่อสร้างถนนคอนกรีต (ร่าง TOR)'), # planning
    ]
    for pid, ann, prov, bud, name in rows:
        c.execute("INSERT OR IGNORE INTO projects_seen (project_id,announce_type,province,budget,project_name,first_seen_at) "
                  "VALUES (?,?,?,?,?,?)", (pid, ann, prov, bud, name, FRESH))
        if ann == 'D0':
            c.execute("INSERT OR IGNORE INTO project_enrichments (project_id,bid_submit_date,bid_submit_time) VALUES (?,?,?)",
                      (pid, FUTURE, "10:00"))
    c.execute("INSERT OR IGNORE INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
              "VALUES (?,?,?,?,?,'active')", (cid, 'D_FOLLOWED', FRESH, 'D0', 'D0'))
    c.commit()


async def main():
    setup()
    # 403
    try:
        await bms_api.portal_discover_jobs(line_user_id='UDISC', x_bms_secret='bad'); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # no customer → empty
    r0 = await bms_api.portal_discover_jobs(line_user_id='UNONE', x_bms_secret='t')
    assert r0["jobs"] == {"biddable": [], "planning": []}, r0
    # real
    r = await bms_api.portal_discover_jobs(line_user_id='UDISC', x_bms_secret='t')
    bid_ids = {j["project_id"] for j in r["jobs"]["biddable"]}
    plan_ids = {j["project_id"] for j in r["jobs"]["planning"]}
    assert bid_ids == {'D_MATCH'}, bid_ids
    assert plan_ids == {'B_FRESH'}, plan_ids
    j = next(x for x in r["jobs"]["biddable"] if x["project_id"] == 'D_MATCH')
    assert j["matched_keywords"] == ["คอนกรีต"] and j["stage"] == "biddable" and j["budget"] == 5000000, j
    print("PASS test_portal_discover_api")


asyncio.run(main())
