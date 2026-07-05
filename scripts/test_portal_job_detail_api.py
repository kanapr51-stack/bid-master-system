"""test_portal_job_detail_api.py — JSON endpoints หน้า detail ธีม Board B
(GET /api/portal/job-detail · POST /api/portal/job-note · POST /api/portal/job-calc)."""
import os, sys, json, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException

PID = "69000000001"


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def seed():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                     "VALUES ('U1','ทดสอบ','trial','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, project_name, first_seen_at) "
                     "VALUES (?, 'D0', 'นครพนม', 5000000, 'จ้างก่อสร้างถนน คสล. ทดสอบ', '2026-07-01')", (PID,))
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, price_agree, is_winner) "
                     "VALUES (?, 'หจก.ผู้ชนะ', '0403000000001', '4500000', '4500000', 1)", (PID,))
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, price_agree, is_winner) "
                     "VALUES (?, 'หจก.ผู้แพ้', '0403000000002', '4800000', NULL, 0)", (PID,))


async def main():
    seed()
    # 403 ทุก endpoint เมื่อ secret ผิด
    for coro in (bms_api.portal_job_detail_json(line_user_id='U1', pid=PID, x_bms_secret='bad'),
                 bms_api.portal_job_note_json(FakeRequest({}), x_bms_secret='bad'),
                 bms_api.portal_job_calc_json(FakeRequest({}), x_bms_secret='bad')):
        try:
            await coro; assert False, "expected 403"
        except HTTPException as e:
            assert e.status_code == 403

    # job-detail: โครงครบ + bidder ผู้ชนะขึ้นก่อน + href หน้าบริษัทธีม A + serialize เป็น JSON ได้
    r = await bms_api.portal_job_detail_json(line_user_id='U1', pid=PID, x_bms_secret='t')
    assert r["ok"], r
    d = r["data"]
    assert d["job"]["project_id"] == PID and d["job"]["budget"] == 5000000, d["job"]
    assert len(d["bidders"]) == 2 and d["bidders"][0]["is_winner"], d["bidders"]
    assert d["bidders"][0]["href"].startswith(bms_api.PUBLIC_BASE_URL.rstrip("/") + "/portal/company?t="), d["bidders"][0]
    assert d["notes"] == [] and d["overview"] == "" and d["starred"] is False, d
    assert "intel_lines" not in d
    json.dumps(d, ensure_ascii=False)  # ต้อง serialize ได้ทั้งก้อน

    # job-detail: ไม่พบงาน
    r = await bms_api.portal_job_detail_json(line_user_id='U1', pid='no-such', x_bms_secret='t')
    assert r == {"ok": False, "error": "not_found"}, r

    # job-note: add → edit → save_overview → delete (คืน state ใหม่ทุกครั้ง)
    r = await bms_api.portal_job_note_json(FakeRequest(
        {"line_user_id": "U1", "pid": PID, "action": "add", "entry_date": "2026-07-07", "note": "โทรหาช่าง"}),
        x_bms_secret='t')
    assert r["ok"] and len(r["notes"]) == 1 and r["notes"][0]["note"] == "โทรหาช่าง", r
    nid = r["notes"][0]["id"]
    r = await bms_api.portal_job_note_json(FakeRequest(
        {"line_user_id": "U1", "pid": PID, "action": "edit", "note_id": nid, "entry_date": "2026-07-08", "note": "นัดดูหน้างาน"}),
        x_bms_secret='t')
    assert r["notes"][0]["note"] == "นัดดูหน้างาน" and r["notes"][0]["entry_date"] == "2026-07-08", r
    r = await bms_api.portal_job_note_json(FakeRequest(
        {"line_user_id": "U1", "pid": PID, "action": "save_overview", "note": "งบ 5 ล้าน คู่แข่ง 2 ราย"}),
        x_bms_secret='t')
    assert r["overview"] == "งบ 5 ล้าน คู่แข่ง 2 ราย", r
    r = await bms_api.portal_job_note_json(FakeRequest(
        {"line_user_id": "U1", "pid": PID, "action": "delete", "note_id": nid}), x_bms_secret='t')
    assert r["notes"] == [], r

    # job-note: action มั่ว → 400, ลูกค้าไม่มี → 404
    try:
        await bms_api.portal_job_note_json(FakeRequest({"line_user_id": "U1", "pid": PID, "action": "drop"}), x_bms_secret='t')
        assert False
    except HTTPException as e:
        assert e.status_code == 400
    try:
        await bms_api.portal_job_note_json(FakeRequest({"line_user_id": "U9", "pid": PID, "action": "add"}), x_bms_secret='t')
        assert False
    except HTTPException as e:
        assert e.status_code == 404

    # job-calc: scratch DB ไม่มีข้อมูล intel → custom_calc = None แต่ ok ต้อง True (ไม่ crash)
    r = await bms_api.portal_job_calc_json(FakeRequest(
        {"line_user_id": "U1", "pid": PID, "my_price": "4600000",
         "selected_names": ["หจก.ผู้ชนะ"], "extra_names": []}), x_bms_secret='t')
    assert r["ok"] and "custom_calc" in r, r

    print("PASS test_portal_job_detail_api")


asyncio.run(main())
