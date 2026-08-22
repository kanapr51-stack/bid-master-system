"""test_portal_last_scan_api.py — GET /api/portal/last-scan (badge เล็กข้างปุ่มแจ้งเตือน, N+223)."""
import os, sys, sqlite3, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


def setup():
    c = sqlite3.connect(bms_api.DB_PATH)
    rows = [
        ("P1", "D0", "นครพนม", 1000000, "งาน A", "2026-08-20T10:00:00+07:00"),
        ("P2", "D0", "นครพนม", 1000000, "งาน B", "2026-08-21T23:31:04+07:00"),  # ใหม่สุด
        ("P3", "D0", "นครพนม", 1000000, "งาน C", "2026-08-19T08:00:00+07:00"),
    ]
    for pid, ann, prov, bud, name, seen in rows:
        c.execute("INSERT OR IGNORE INTO projects_seen (project_id,announce_type,province,budget,project_name,first_seen_at) "
                  "VALUES (?,?,?,?,?,?)", (pid, ann, prov, bud, name, seen))
    c.commit()


async def main():
    setup()
    try:
        await bms_api.portal_last_scan(x_bms_secret="bad"); assert False
    except HTTPException as e:
        assert e.status_code == 403

    r = await bms_api.portal_last_scan(x_bms_secret="t")
    assert r["ok"] is True
    assert r["last_scan_at"] == "2026-08-21T23:31:04+07:00", r
    print("PASS test_portal_last_scan_api")


asyncio.run(main())
