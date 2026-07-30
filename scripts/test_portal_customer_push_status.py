"""GET /api/portal/customer คืน has_push_subscription: true เมื่อมี push_subscriptions ที่ยัง active,
false เมื่อไม่มี หรือถูก disable แล้วทั้งหมด"""
import os, sys, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db
db.init_schema()
import bms_api

NOW = "2026-07-30T00:00:00+07:00"


async def main():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, active, created_at, updated_at) "
                     "VALUES ('UNOSUB','x','trial',1,?,?)", (NOW, NOW))
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, active, created_at, updated_at) "
                     "VALUES ('UHASSUB','y','trial',1,?,?)", (NOW, NOW))
        cid = conn.execute("SELECT id FROM customers WHERE line_user_id='UHASSUB'").fetchone()["id"]
        conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, created_at) "
                     "VALUES (?, 'https://push.example/e1', 'pk', 'ak', ?)", (cid, NOW))

    r = await bms_api.portal_get_customer(line_user_id="UNOSUB", x_bms_secret="t")
    assert r["customer"]["has_push_subscription"] is False, r

    r = await bms_api.portal_get_customer(line_user_id="UHASSUB", x_bms_secret="t")
    assert r["customer"]["has_push_subscription"] is True, r

    # disabled subscription ไม่นับว่า active
    with bms_api.get_conn() as conn:
        conn.execute("UPDATE push_subscriptions SET disabled_at=? WHERE customer_id=?", (NOW, cid))
    r = await bms_api.portal_get_customer(line_user_id="UHASSUB", x_bms_secret="t")
    assert r["customer"]["has_push_subscription"] is False, r

    # ลูกค้าไม่มีในระบบ → customer เป็น None ไม่ crash
    r = await bms_api.portal_get_customer(line_user_id="UNKNOWN", x_bms_secret="t")
    assert r["customer"] is None, r

    print("PASS test_portal_customer_push_status")


asyncio.run(main())
