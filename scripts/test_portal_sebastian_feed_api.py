"""test_portal_sebastian_feed_api.py — GET /api/portal/sebastian-feed (แท็บ Sebastian, ประวัติ
แจ้งเตือนสไตล์แชท): dedup ต่อ project เอารอบล่าสุด (เกณฑ์เดียวกับ all-jobs), เรียงเก่า→ใหม่,
message เนื้อหาตรงกับ format_notification() จริงเป๊ะ, ไม่เขียน price_predictions ซ้ำ."""
import os, sys, json, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


def seed():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                     "VALUES ('U1','ทดสอบ','trial','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, "
                     "project_name, dept_name, first_seen_at) VALUES "
                     "('P1', 'D0', 'นครพนม', 5000000, 'ถนน คสล. สายหนึ่ง', 'อบต.ทดสอบ', '2026-07-01')")
        conn.execute("INSERT INTO project_locations (project_id, deadline, deadline_time, created_at) "
                     "VALUES ('P1', '2026-08-03', '09.00-12.00 น.', '2026-07-01')")
        q = ("INSERT INTO notification_queue (customer_id, project_id, status, created_at, "
             "province_snapshot, project_name_snapshot, dept_name_snapshot, source_stage, is_test_data) "
             "VALUES (?,?,?,?,?,?,?,?,?)")
        # P1 ส่ง 2 รอบ: D0 ก่อน แล้วค่อยประกาศผล → ต้องเหลือ 1 ข้อความ stage=won, ใช้ snapshot ล่าสุด
        conn.execute(q, (1, 'P1', 'sent', '2026-07-01T08:00:00', 'นครพนม', 'ถนน คสล. สายหนึ่ง', 'อบต.ทดสอบ', 'province_qualified', 0))
        conn.execute(q, (1, 'P1', 'sent', '2026-07-05T08:00:00', 'นครพนม', 'ถนน คสล. สายหนึ่ง', 'อบต.ทดสอบ', 'followed_winner', 0))
        # P2: snapshot ล้วน (ไม่มีใน projects_seen/project_locations)
        conn.execute(q, (1, 'P2', 'sent', '2026-07-06T08:00:00', 'บึงกาฬ', 'อาคารเรียนสองชั้น', 'สพฐ.ทดสอบ', 'province_tor_review', 0))
        # P3: LINE ส่งไม่สำเร็จ (quota เต็ม) → ยังต้องขึ้น (ไม่ผูกผลส่ง LINE)
        conn.execute(q, (1, 'P3', 'failed', '2026-07-06T09:00:00', 'นครพนม', 'งานที่ส่งพลาด', '', 'province_qualified', 0))
        # P4: test data → ไม่ขึ้น
        conn.execute(q, (1, 'P4', 'sent', '2026-07-06T10:00:00', 'นครพนม', 'งานทดสอบระบบ', '', 'province_qualified', 1))
        # P5: queue status='cancelled' → ไม่ขึ้น
        conn.execute(q, (1, 'P5', 'cancelled', '2026-07-06T09:15:00', 'นครพนม', 'แถวคิวถูกยกเลิก', '', 'province_qualified', 0))
        # ดาว P1
        conn.execute("INSERT INTO job_stars (customer_id, project_id, created_at) VALUES (1,'P1','2026-07-05')")
        # cgd_winners: คู่แข่งจริง 2 ราย งานถนน คสล. อบต. ใน นครพนม (ตรง keyword+subtype+market ของ P1)
        # ให้ cgd_intel.intel_context() คืน prediction จริง (ไม่ None) — พิสูจน์ว่า record_prediction=False
        # เซฟจากการเขียนซ้ำจริง (ไม่ใช่ผ่านเพราะ intel_ctx ไม่มี prediction key อยู่แล้วเฉยๆ)
        q2 = ("INSERT INTO cgd_winners (project_id, province, dept, project_name, winner, budget, "
              "win_price, discount_pct, fiscal_year, proc_type) VALUES (?,?,?,?,?,?,?,?,?,?)")
        EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
        conn.execute(q2, ("CGD1", "นครพนม", "อบต.สนามทดสอบ", "จ้างก่อสร้างถนน คสล. หมู่ 1 ตำบลสนาม",
                          "หจก.สนามหนึ่ง", 5000000, 4000000, 20.0, "2568", EB))
        conn.execute(q2, ("CGD2", "นครพนม", "อบต.สนามทดสอบ", "จ้างก่อสร้างถนน คสล. หมู่ 2 ตำบลสนาม",
                          "หจก.สนามสอง", 5000000, 3750000, 25.0, "2568", EB))


async def main():
    seed()
    # 403 secret ผิด
    try:
        await bms_api.portal_sebastian_feed_json(line_user_id='U1', x_bms_secret='bad')
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403

    r = await bms_api.portal_sebastian_feed_json(line_user_id='U1', x_bms_secret='t')
    assert r["ok"] and r["count"] == 3, r  # P1(dedup), P2, P3(failed ก็ขึ้น) — ไม่มี P4(test)/P5(cancelled)
    msgs = r["messages"]
    # เรียงเก่า→ใหม่ (แชท): P1(07-01 dedup ใช้ created_at ล่าสุด 07-05) ไม่ใช่ — ลำดับตาม created_at ที่ใช้แสดง
    assert [m["project_id"] for m in msgs] == ['P1', 'P2', 'P3'], msgs  # เก่า→ใหม่ ตาม sent_at ล่าสุดของแต่ละ project
    byid = {m["project_id"]: m for m in msgs}
    assert byid['P1']["stage"] == 'won' and byid['P1']["sent_at"] == '2026-07-05T08:00:00', byid['P1']
    assert byid['P1']["starred"] is True and byid['P2']["starred"] is False, byid

    # message เนื้อหาตรงกับ format_notification() จริงเป๊ะ (byte ต่อ byte) — กัน message drift
    from Sebastian_LINE_Sender import format_notification, _clean_project_name, _plain_text_body
    expected_text = format_notification(
        project_id='P1', province='นครพนม', announce_type='D0', budget=5000000,
        project_name='ถนน คสล. สายหนึ่ง', dept_name='อบต.ทดสอบ',
        bid_submit_date='2026-08-03', bid_submit_time='09.00-12.00 น.',
        source_stage='followed_winner', record_prediction=False,
    )
    expected_full_name = _clean_project_name('ถนน คสล. สายหนึ่ง')
    expected_message = _plain_text_body(expected_text, expected_full_name)
    assert byid['P1']["message"] == expected_message, (byid['P1']["message"], expected_message)
    assert '⏰ ยื่นซอง 3 ส.ค.' in byid['P1']["message"], byid['P1']["message"]

    # P2 ไม่มี projects_seen/project_locations → graceful (budget=0 "ไม่ระบุ", ไม่มี deadline)
    assert 'ไม่ระบุ' in byid['P2']["message"] or '💰' in byid['P2']["message"], byid['P2']["message"]
    assert '⏰' not in byid['P2']["message"], byid['P2']["message"]

    # P2 = TOR review (source_stage='province_tor_review') ไม่มี projects_seen row → announce_type
    # ต้อง fallback ให้ตรง stage จริง (ไม่ใช่เหมาแบบ "D0") ไม่งั้น format_notification() จะขึ้นหัวข้อ
    # "🔔 พบงานเปิดกำหนดวันยื่นซองใหม่" (D0) แทนที่จะเป็น "📋 รับฟังคำวิจารณ์" (TOR review) — bug ที่
    # fixture นี้เคยไม่จับเพราะไม่มี assertion เช็คหัวข้อ (regression guard)
    assert byid['P2']["message"].startswith('📋 รับฟังคำวิจารณ์'), byid['P2']["message"]
    assert '🔔 พบงานเปิดกำหนดวันยื่นซองใหม่' not in byid['P2']["message"], byid['P2']["message"]

    json.dumps(r, ensure_ascii=False)

    # record_prediction=False จริง — ต้องไม่มี row ใน price_predictions หลังเรียก endpoint
    # (P1 มี cgd_winners คู่แข่งจริงที่ seed ไว้ข้างบน → intel_context() ของ P1 คืน prediction จริง
    # ไม่ใช่ None ดังนั้น assertion นี้พิสูจน์ record_prediction=False จริง ไม่ใช่ผ่านลอยๆ เพราะไม่มี
    # prediction ให้เขียนอยู่แล้ว)
    with bms_api.get_conn() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM price_predictions").fetchone()[0]
    assert cnt == 0, cnt

    # control: เรียก format_notification() ตรงๆ ด้วย seed เดียวกันแต่ record_prediction=True (default
    # ตอน production ส่งจริง) ต้องเขียนจริง 1 row — พิสูจน์ว่า path ไปถึง save_prediction() จริง
    # (ไม่ใช่ cnt==0 ข้างบนผ่านเพราะ intel_ctx.get("prediction") เป็น falsy อยู่แล้วไม่ว่า flag จะเป็นอะไร)
    format_notification(
        project_id='P1', province='นครพนม', announce_type='D0', budget=5000000,
        project_name='ถนน คสล. สายหนึ่ง', dept_name='อบต.ทดสอบ',
        bid_submit_date='2026-08-03', bid_submit_time='09.00-12.00 น.',
        source_stage='followed_winner', record_prediction=True,
    )
    with bms_api.get_conn() as conn:
        cnt2 = conn.execute("SELECT COUNT(*) FROM price_predictions").fetchone()[0]
    assert cnt2 == 1, cnt2

    # ลูกค้าไม่มี → ก้อนว่าง ไม่ crash
    r = await bms_api.portal_sebastian_feed_json(line_user_id='U9', x_bms_secret='t')
    assert r == {"ok": True, "count": 0, "messages": []}, r

    print("PASS test_portal_sebastian_feed_api")


asyncio.run(main())
