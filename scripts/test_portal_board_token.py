"""test_portal_board_token.py — GET /api/portal/board-token (mint token ให้บอร์ด Next.js ลิงก์หน้า detail)."""
import os, sys, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
import follow_token
from fastapi import HTTPException


async def main():
    # 403
    try:
        await bms_api.portal_board_token(line_user_id='U1', x_bms_secret='bad'); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # mint แล้ว verify กลับได้ user เดิม, p=None (portal-level)
    r = await bms_api.portal_board_token(line_user_id='U1', x_bms_secret='t')
    assert r["ok"] and r["token"] and r["base"] == bms_api.PUBLIC_BASE_URL.rstrip("/"), r
    v = follow_token.verify_token(r["token"])
    assert v and v[0] == 'U1' and v[1] is None, v
    print("PASS test_portal_board_token")


asyncio.run(main())
