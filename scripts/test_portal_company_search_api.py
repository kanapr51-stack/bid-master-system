"""test_portal_company_search_api.py — GET /api/portal/company-search (แถบ "ประวัติ" ค้นบริษัท,
N+217: แทนที่ Neon Postgres เดิมที่ไม่เชื่อมกับฐานข้อมูลจริง — ดู progress_log)."""
import os, sys, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException

TIN_A = "0403000000001"
TIN_B = "0403000000002"


def seed():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, project_name, first_seen_at) "
                     "VALUES ('P1', 'D0', 'นครพนม', 5000000, 'จ้างก่อสร้างถนน', '2026-07-01')")
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, project_name, first_seen_at) "
                     "VALUES ('P2', 'D0', 'นครพนม', 3000000, 'จ้างซ่อมถนน', '2026-07-02')")
        # TIN_A ยื่น 2 งาน (มากกว่า TIN_B) — ต้องขึ้นก่อนตอนค้นด้วยคำที่แมตช์ทั้งคู่
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, is_winner) "
                     "VALUES ('P1', 'หจก.รุ่งเรืองก่อสร้าง', ?, '4500000', 1)", (TIN_A,))
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, is_winner) "
                     "VALUES ('P2', 'หจก.รุ่งเรืองก่อสร้าง', ?, '2800000', 0)", (TIN_A,))
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, is_winner) "
                     "VALUES ('P1', 'หจก.รุ่งเจริญ', ?, '4600000', 0)", (TIN_B,))


async def main():
    seed()
    # 403 secret ผิด
    try:
        await bms_api.portal_company_search_json(query='รุ่ง', x_bms_secret='bad')
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403

    # คำค้นสั้นกว่า 2 ตัวอักษร → ก้อนว่าง ไม่ยิง query จริง
    r = await bms_api.portal_company_search_json(query='ร', x_bms_secret='t')
    assert r == {"ok": True, "results": []}, r

    # ค้นด้วยคำที่แมตช์ทั้งสองบริษัท — เรียงตาม total_bids มากสุดก่อน
    r = await bms_api.portal_company_search_json(query='รุ่ง', x_bms_secret='t')
    assert r["ok"], r
    tins = [c["tin"] for c in r["results"]]
    assert tins == [TIN_A, TIN_B], tins   # TIN_A มี 2 งาน > TIN_B มี 1 งาน
    assert r["results"][0]["total_bids"] == 2 and r["results"][0]["wins"] == 1, r["results"][0]

    # ค้นด้วย TIN ตรงๆ (partial) → เจอเฉพาะราย
    r = await bms_api.portal_company_search_json(query=TIN_B, x_bms_secret='t')
    assert [c["tin"] for c in r["results"]] == [TIN_B], r

    # ไม่เจอ → ก้อนว่าง ไม่ error
    r = await bms_api.portal_company_search_json(query='ไม่มีจริงแน่นอน', x_bms_secret='t')
    assert r == {"ok": True, "results": []}, r

    print("PASS test_portal_company_search_api")


asyncio.run(main())
