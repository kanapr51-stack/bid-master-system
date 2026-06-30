"""test_portal_upgrade_api.py — POST /api/portal/upgrade-request (แจ้ง admin, mock Discord)."""
import os, sys, asyncio, sqlite3, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db; db.init_schema()
import Sebastian_Discord_Notify as dn
import bms_api
from fastapi import HTTPException

# mock Discord ไม่ให้ยิงจริง
_sent = {}
dn.load_env = lambda: None
dn.get_credentials = lambda: ("Bot x", "ch")
dn.send = lambda token, ch, content: _sent.update(content=content) or True


class FakeReq:
    def __init__(self, d): self._d = d
    async def json(self): return self._d


async def main():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UUPG','บ.ทดสอบ','trial',1,'t','t')"); c.commit()
    # 403
    try:
        await bms_api.portal_upgrade_request(FakeReq({'line_user_id': 'UUPG', 'tier': 'standard'}), x_bms_secret='x'); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # 400 ขาด tier
    try:
        await bms_api.portal_upgrade_request(FakeReq({'line_user_id': 'UUPG'}), x_bms_secret='t'); assert False
    except HTTPException as e:
        assert e.status_code == 400
    # happy path → ส่ง Discord, ok
    r = await bms_api.portal_upgrade_request(FakeReq({'line_user_id': 'UUPG', 'tier': 'premium', 'billing': 'annual'}), x_bms_secret='t')
    assert r["ok"] is True, r
    assert 'premium' in _sent.get('content', '') and 'บ.ทดสอบ' in _sent['content'], _sent
    print("PASS test_portal_upgrade_api")


asyncio.run(main())
