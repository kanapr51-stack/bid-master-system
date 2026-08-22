"""test_portal_last_scan_api.py — GET /api/portal/last-scan (badge เล็กข้างปุ่มแจ้งเตือน, N+225).

N+225: เอา MAX(ExecMainStartTimestamp) จาก 3 หน่วย province-discovery จริง
(ไม่นับ RSS scraper — คุณกัญจน์แยกไว้ชัดว่าคนละ pipeline) — mock subprocess.run
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


# ตอบตามลำดับ _DISCOVERY_UNITS: province-discovery, full-nkp, full-bkg
STDOUTS_MIXED = [
    "Sat 2026-08-22 12:00:01 UTC\n",
    "Sat 2026-08-22 12:30:01 UTC\n",
    "Sat 2026-08-22 13:30:01 UTC\n",  # ล่าสุดสุด → ต้องถูกเลือก
]


async def main():
    # 403
    try:
        await bms_api.portal_last_scan(x_bms_secret="bad"); assert False
    except HTTPException as e:
        assert e.status_code == 403

    # 3 หน่วยมีเวลาต่างกัน → เลือกอันล่าสุดสุด (full-bkg 13:30:01 UTC = 20:30:01 ไทย)
    with patch("bms_api.subprocess.run", side_effect=[_mock_run(s) for s in STDOUTS_MIXED]):
        r = await bms_api.portal_last_scan(x_bms_secret="t")
        assert r["ok"] is True
        assert r["last_scan_at"] == "2026-08-22T20:30:01+07:00", r

    # ทุกหน่วยยังไม่เคยรัน (n/a) → คืนค่าว่าง ไม่พัง
    with patch("bms_api.subprocess.run", return_value=_mock_run("n/a\n")):
        r = await bms_api.portal_last_scan(x_bms_secret="t")
        assert r == {"ok": True, "last_scan_at": ""}, r

    # systemctl ใช้ไม่ได้ (exception) → fail-open คืนค่าว่าง ไม่ throw
    with patch("bms_api.subprocess.run", side_effect=FileNotFoundError):
        r = await bms_api.portal_last_scan(x_bms_secret="t")
        assert r == {"ok": True, "last_scan_at": ""}, r

    print("PASS test_portal_last_scan_api")


asyncio.run(main())
