"""test_portal_last_scan_api.py — GET /api/portal/last-scan (badge เล็กข้างปุ่มแจ้งเตือน, N+224).

N+224: อ่าน ExecMainStartTimestamp ของ bms-rss-scraper.service จาก systemd ตรงๆ
(แทน MAX(first_seen_at) เดิมของ N+223 ที่ค้างถ้าไม่เจองานใหม่) — mock subprocess.run
เพราะเครื่อง dev ไม่มี systemd/service จริงให้ยิง
"""
import os, sys, asyncio, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


def _mock_run(stdout: str):
    m = MagicMock()
    m.stdout = stdout
    return m


async def main():
    # 403
    try:
        await bms_api.portal_last_scan(x_bms_secret="bad"); assert False
    except HTTPException as e:
        assert e.status_code == 403

    # systemctl คืน timestamp ปกติ → parse เป็น ISO ไทยถูกต้อง
    with patch("bms_api.subprocess.run", return_value=_mock_run("Sat 2026-08-22 20:07:15 UTC\n")):
        r = await bms_api.portal_last_scan(x_bms_secret="t")
        assert r["ok"] is True
        assert r["last_scan_at"] == "2026-08-23T03:07:15+07:00", r  # UTC+7

    # service ยังไม่เคยรัน (n/a) → คืนค่าว่าง ไม่พัง
    with patch("bms_api.subprocess.run", return_value=_mock_run("n/a\n")):
        r = await bms_api.portal_last_scan(x_bms_secret="t")
        assert r == {"ok": True, "last_scan_at": ""}, r

    # systemctl ใช้ไม่ได้ (exception) → fail-open คืนค่าว่าง ไม่ throw
    with patch("bms_api.subprocess.run", side_effect=FileNotFoundError):
        r = await bms_api.portal_last_scan(x_bms_secret="t")
        assert r == {"ok": True, "last_scan_at": ""}, r

    print("PASS test_portal_last_scan_api")


asyncio.run(main())
