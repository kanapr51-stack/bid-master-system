"""POST /api/portal/push-subscribe|unsubscribe|test — 403 guard, upsert, disable, ส่งทดสอบ (mock)"""
import os, sys, asyncio, sqlite3, tempfile, shutil
from pathlib import Path
from unittest.mock import patch

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_WEBPUSH_DISABLED="1")
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


class FakeReq:
    def __init__(self, body): self._b = body
    async def json(self): return self._b


def setup_customer():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UPUSH','x','trial',1,'2026-07-14T00:00:00+07:00','2026-07-14T00:00:00+07:00')")
    c.commit(); c.close()


async def main():
    setup_customer()
    SUB = {"line_user_id": "UPUSH", "endpoint": "https://push.example/e1",
           "p256dh": "pk", "auth": "ak", "user_agent": "UA1"}
    # 403
    try:
        await bms_api.portal_push_subscribe(FakeReq(SUB), x_bms_secret="wrong"); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # subscribe → row
    r = await bms_api.portal_push_subscribe(FakeReq(SUB), x_bms_secret="t")
    assert r["ok"] is True
    c = sqlite3.connect(bms_api.DB_PATH); c.row_factory = sqlite3.Row
    row = c.execute("SELECT * FROM push_subscriptions WHERE endpoint='https://push.example/e1'").fetchone()
    assert row["p256dh"] == "pk" and row["disabled_at"] is None
    # subscribe ซ้ำ endpoint เดิม (key ใหม่) → update ไม่ duplicate
    r = await bms_api.portal_push_subscribe(FakeReq({**SUB, "p256dh": "pk2"}), x_bms_secret="t")
    rows = c.execute("SELECT p256dh FROM push_subscriptions WHERE endpoint='https://push.example/e1'").fetchall()
    assert len(rows) == 1 and rows[0]["p256dh"] == "pk2", [dict(x) for x in rows]
    # unsubscribe → disabled_at
    r = await bms_api.portal_push_unsubscribe(
        FakeReq({"line_user_id": "UPUSH", "endpoint": "https://push.example/e1"}), x_bms_secret="t")
    assert r["ok"] is True
    row = c.execute("SELECT disabled_at FROM push_subscriptions").fetchone()
    assert row["disabled_at"], dict(row)
    # subscribe อีกรอบ → re-enable
    await bms_api.portal_push_subscribe(FakeReq(SUB), x_bms_secret="t")
    assert c.execute("SELECT disabled_at FROM push_subscriptions").fetchone()["disabled_at"] is None
    # push-test → เรียก webpush_send.send_to_user
    with patch.object(bms_api.webpush_send, "send_to_user", return_value=(2, 0)) as m:
        r = await bms_api.portal_push_test(FakeReq({"line_user_id": "UPUSH"}), x_bms_secret="t")
        assert r == {"ok": True, "sent": 2, "failed": 0}, r
        assert m.call_args[0][0] == "UPUSH"
    c.close()
    print("PASS test_push_api")


asyncio.run(main())
