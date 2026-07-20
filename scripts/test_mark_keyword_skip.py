"""test_mark_keyword_skip.py — N+207: SubscriptionStore.mark_keyword_skip() ต้อง mark
queue row เป็น 'skipped' (ไม่ retry, ไม่เขียน delivery_log เพราะไม่ใช่ LINE attempt จริง)
และงานนั้นต้องยัง "อัปเดตเงียบๆ" บนบอร์ด "งานทั้งหมด" (/api/portal/all-jobs, N+205 filter
status!='cancelled')."""
import os, sys, json, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api


def seed():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                     "VALUES ('UKS','ทดสอบ','trial','2026-01-01','2026-01-01')")
        conn.execute(
            "INSERT INTO notification_queue (customer_id, project_id, status, created_at, "
            "province_snapshot, project_name_snapshot, source_stage, is_test_data) "
            "VALUES (1,'PSKIP','pending','2026-07-21T08:00:00','นครพนม','งานไม่ตรง keyword',"
            "'province_qualified',0)")
        conn.commit()
        row = conn.execute("SELECT id FROM notification_queue WHERE project_id='PSKIP'").fetchone()
        return row["id"]


async def main():
    qid = seed()
    store = db.SubscriptionStore()
    store.mark_keyword_skip(qid)

    with bms_api.get_conn() as conn:
        r = conn.execute(
            "SELECT status, last_error_type, retry_count FROM notification_queue WHERE id=?",
            (qid,)).fetchone()
        assert r["status"] == "skipped", r["status"]
        assert r["last_error_type"] == "keyword_no_match", r["last_error_type"]
        assert r["retry_count"] == 0, r["retry_count"]  # ไม่ผ่าน retry path
        dl = conn.execute("SELECT COUNT(*) c FROM delivery_log WHERE project_id='PSKIP'").fetchone()
        assert dl["c"] == 0, "ไม่ใช่ LINE attempt จริง — ต้องไม่เขียน delivery_log"

    # N+205: บอร์ด "งานทั้งหมด" อ่าน status!='cancelled' — 'skipped' ต้องยังขึ้น (silent update)
    r2 = await bms_api.portal_all_jobs_json(line_user_id='UKS', x_bms_secret='t')
    assert r2["count"] == 1 and r2["jobs"][0]["project_id"] == "PSKIP", r2

    print("PASS test_mark_keyword_skip")


asyncio.run(main())
