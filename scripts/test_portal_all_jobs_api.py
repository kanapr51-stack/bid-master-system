"""test_portal_all_jobs_api.py — GET /api/portal/all-jobs (การ์ด 'งานทั้งหมด' Board B):
dedup ต่อ project เอารอบล่าสุด, กรอง cancelled/is_test_data (ไม่ผูกผลส่ง LINE — sent/failed ขึ้นทั้งคู่),
เรียงใหม่→เก่า, stage map, count ไม่ติด limit."""
import os, sys, json, asyncio, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ_TH = timezone(timedelta(hours=7))

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


class _req:
    """mock Request มีแค่ .json() — สำหรับ endpoint ที่อ่าน body ตรง"""
    def __init__(self, body): self._b = body
    async def json(self): return self._b


def seed():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                     "VALUES ('U1','ทดสอบ','trial','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, project_name, first_seen_at) "
                     "VALUES ('P1', 'D0', 'นครพนม', 5000000, 'ถนน คสล. สายหนึ่ง', '2026-07-01')")
        # P1 ส่ง 2 รอบ: D0 ก่อน แล้วค่อยประกาศผล → ต้องเหลือ 1 รายการ stage=won
        q = ("INSERT INTO notification_queue (customer_id, project_id, status, created_at, "
             "province_snapshot, project_name_snapshot, source_stage, is_test_data) VALUES (?,?,?,?,?,?,?,?)")
        conn.execute(q, (1, 'P1', 'sent', '2026-07-01T08:00:00', 'นครพนม', 'ถนน คสล. สายหนึ่ง', 'province_qualified', 0))
        conn.execute(q, (1, 'P1', 'sent', '2026-07-05T08:00:00', 'นครพนม', 'ถนน คสล. สายหนึ่ง', 'followed_winner', 0))
        # P2: snapshot ล้วน (ไม่มีใน projects_seen) — TOR review → stage=pre
        conn.execute(q, (1, 'P2', 'sent', '2026-07-06T08:00:00', 'บึงกาฬ', 'อาคารเรียนสองชั้น', 'province_tor_review', 0))
        # P3: LINE ส่งไม่สำเร็จ (เช่น quota เต็ม) → สแกน+จับคู่แล้วจริง ต้องขึ้นบอร์ดเหมือนกัน
        conn.execute(q, (1, 'P3', 'failed', '2026-07-06T09:00:00', 'นครพนม', 'งานที่ส่งพลาด', 'province_qualified', 0))
        # P4: test data → ไม่ขึ้น
        conn.execute(q, (1, 'P4', 'sent', '2026-07-06T10:00:00', 'นครพนม', 'งานทดสอบระบบ', 'province_qualified', 1))
        # P5: cancelled ล่าสุดสุด → ขึ้นเป็นรายการแรก (source_stage=followed_cancelled คนละความหมายกับ queue status='cancelled')
        conn.execute(q, (1, 'P5', 'sent', '2026-07-07T08:00:00', 'นครพนม', 'งานที่ถูกยกเลิก', 'followed_cancelled', 0))
        # P6: queue status='cancelled' (แถวซ้ำ/ถูก dedup ทิ้ง) → ต้องไม่ขึ้นบอร์ด
        conn.execute(q, (1, 'P6', 'cancelled', '2026-07-06T09:15:00', 'นครพนม', 'แถวคิวถูกยกเลิก', 'province_qualified', 0))
        # ดาว P1
        conn.execute("INSERT INTO job_stars (customer_id, project_id, created_at) VALUES (1,'P1','2026-07-05')")
        # N+197: P1 ติดตามอยู่ (active) / P5 เคยติดตามแล้วเลิก (unfollowed) → followed ต้องเป็น false
        conn.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                     "VALUES (1,'P1','2026-07-05','D0','W0','active')")
        conn.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                     "VALUES (1,'P5','2026-07-06','D0','D0','unfollowed')")


async def main():
    seed()
    # 403 secret ผิด
    try:
        await bms_api.portal_all_jobs_json(line_user_id='U1', x_bms_secret='bad')
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403

    r = await bms_api.portal_all_jobs_json(line_user_id='U1', x_bms_secret='t')
    assert r["ok"] and r["count"] == 4, r  # P1(dedup), P2, P3(failed ก็ขึ้น), P5 — ไม่มี P4(test)/P6(queue cancelled)
    assert r["new_today"] == 0, r  # ทุกแถว seed เป็นวันที่เก่า (2026-07) ไม่ใช่วันนี้จริง
    jobs = r["jobs"]
    assert [j["project_id"] for j in jobs] == ['P5', 'P3', 'P2', 'P1'], jobs  # ใหม่ → เก่า
    byid = {j["project_id"]: j for j in jobs}
    assert byid['P1']["stage"] == 'won' and byid['P1']["sent_at"] == '2026-07-05T08:00:00', byid['P1']  # เอารอบล่าสุด
    assert byid['P1']["budget"] == 5000000 and byid['P1']["starred"] is True, byid['P1']
    assert byid['P1']["followed"] is True, byid['P1']
    assert byid['P2']["followed"] is False and byid['P5']["followed"] is False, byid
    assert byid['P2']["stage"] == 'pre' and byid['P2']["budget"] == 0 and byid['P2']["name"] == 'อาคารเรียนสองชั้น', byid['P2']
    assert byid['P3']["stage"] == 'bidding' and byid['P3']["name"] == 'งานที่ส่งพลาด', byid['P3']  # failed แต่จับคู่แล้วจริง → ขึ้น
    assert byid['P5']["stage"] == 'cancelled' and byid['P5']["starred"] is False, byid['P5']
    assert 'P6' not in byid, byid  # queue status='cancelled' → ไม่ขึ้น
    json.dumps(r, ensure_ascii=False)

    # limit ไม่กระทบ count / new_today (N+213: badge "New+N" การ์ดงานทั้งหมด)
    r = await bms_api.portal_all_jobs_json(line_user_id='U1', limit=1, x_bms_secret='t')
    assert r["count"] == 4 and r["new_today"] == 0 and len(r["jobs"]) == 1 and r["jobs"][0]["project_id"] == 'P5', r

    # เพิ่มงานที่สแกน+จับคู่ "วันนี้" จริง (2 รายการ) → new_today ต้องนับแค่งานวันนี้ ไม่รวมของเก่า
    today_iso = datetime.now(TZ_TH).isoformat(timespec="seconds")
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO notification_queue (customer_id, project_id, status, created_at, "
                     "province_snapshot, project_name_snapshot, source_stage, is_test_data) "
                     "VALUES (1,'P7','sent',?,'นครพนม','งานใหม่วันนี้ 1','province_qualified',0)", (today_iso,))
        conn.execute("INSERT INTO notification_queue (customer_id, project_id, status, created_at, "
                     "province_snapshot, project_name_snapshot, source_stage, is_test_data) "
                     "VALUES (1,'P8','sent',?,'นครพนม','งานใหม่วันนี้ 2','province_qualified',0)", (today_iso,))
    r = await bms_api.portal_all_jobs_json(line_user_id='U1', x_bms_secret='t')
    assert r["count"] == 6 and r["new_today"] == 2, r
    # limit=1 ยังคืน new_today ที่ถูกต้อง (ไม่ผูกกับความยาว jobs ที่ตัด)
    r = await bms_api.portal_all_jobs_json(line_user_id='U1', limit=1, x_bms_secret='t')
    assert r["new_today"] == 2 and len(r["jobs"]) == 1, r

    # ลูกค้าไม่มี → ก้อนว่าง ไม่ crash
    r = await bms_api.portal_all_jobs_json(line_user_id='U9', x_bms_secret='t')
    assert r == {"ok": True, "count": 0, "jobs": []}, r

    # N+197.1: unfollow → followed=false → follow กลับ → true (toggle roundtrip)
    r = await bms_api.portal_unfollow_job_json(_req({"line_user_id": "U1", "project_id": "P1"}), x_bms_secret="t")
    assert r == {"ok": True, "followed": False}, r
    r = await bms_api.portal_all_jobs_json(line_user_id='U1', x_bms_secret='t')
    assert {j["project_id"]: j["followed"] for j in r["jobs"]}['P1'] is False, r
    with bms_api.get_conn() as conn:
        st = conn.execute("SELECT status FROM followed_jobs WHERE customer_id=1 AND project_id='P1'").fetchone()[0]
    assert st == 'unfollowed', st
    r = await bms_api.portal_follow_job(_req({"line_user_id": "U1", "project_id": "P1"}), x_bms_secret="t")
    assert r["ok"] is True, r
    r = await bms_api.portal_all_jobs_json(line_user_id='U1', x_bms_secret='t')
    assert {j["project_id"]: j["followed"] for j in r["jobs"]}['P1'] is True, r
    # unfollow: 403 secret ผิด / 404 ลูกค้าไม่มี
    try:
        await bms_api.portal_unfollow_job_json(_req({"line_user_id": "U1", "project_id": "P1"}), x_bms_secret="bad")
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403
    try:
        await bms_api.portal_unfollow_job_json(_req({"line_user_id": "U9", "project_id": "P1"}), x_bms_secret="t")
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404

    print("PASS test_portal_all_jobs_api")


asyncio.run(main())
