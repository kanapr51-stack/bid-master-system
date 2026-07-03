"""test_set_customer_tier.py — migration expires_at + /api/portal/customer + set_customer_tier."""
import os, sys, sqlite3, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
import set_customer_tier


def setup():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UTIER','ทดสอบ','trial',1,'2026-07-01T00:00:00','2026-07-01T00:00:00')")
    c.commit()


async def main():
    setup()
    # ยังไม่ตั้ง expires_at → fallback created+30
    r = await bms_api.portal_get_customer(line_user_id='UTIER', x_bms_secret='t')
    assert r["customer"]["tier"] == "trial", r
    assert r["customer"]["expires_at"].startswith("2026-07-31"), r

    # dry-run — ไม่เขียน
    set_customer_tier.set_tier('UTIER', 'standard', '2026-12-31', apply=False)
    r = await bms_api.portal_get_customer(line_user_id='UTIER', x_bms_secret='t')
    assert r["customer"]["tier"] == "trial", r

    # apply — tier + expires_at จริง
    set_customer_tier.set_tier('UTIER', 'standard', '2026-12-31', apply=True)
    r = await bms_api.portal_get_customer(line_user_id='UTIER', x_bms_secret='t')
    assert r["customer"]["tier"] == "standard", r
    assert r["customer"]["expires_at"] == "2026-12-31", r

    # เคลียร์ expires (เว้นว่าง) → กลับ fallback
    set_customer_tier.set_tier('UTIER', 'trial', '', apply=True)
    r = await bms_api.portal_get_customer(line_user_id='UTIER', x_bms_secret='t')
    assert r["customer"]["tier"] == "trial", r
    assert r["customer"]["expires_at"].startswith("2026-07-31"), r
    print("PASS test_set_customer_tier")


asyncio.run(main())
