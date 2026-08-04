"""test_portal_sebastian_feed_api.py — GET /api/portal/sebastian-feed (แท็บ Sebastian, ประวัติ
แจ้งเตือนสไตล์แชท): dedup ต่อ project เอารอบล่าสุด (เกณฑ์เดียวกับ all-jobs), เรียงเก่า→ใหม่,
message เนื้อหาตรงกับ formatter จริงเป๊ะ (format_notification สำหรับ stage ทั่วไป,
format_winner_detailed สำหรับ followed_winner), ไม่เขียน price_predictions ซ้ำ, status filter
เอาเฉพาะที่ยิงจริง (sent/failed), announce_type ของ TOR-review ไม่โดน projects_seen ที่เลื่อนไป D0
แล้วทับ, limit bound งานหนักจริง (final review fix — endpoint เป็น sync def ไม่ใช่ async แล้ว)."""
import os, sys, json, tempfile
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
        # P1 bid_results: ผู้ชนะ + คู่แข่ง 1 ราย — ให้ format_winner_detailed() มีของจริงให้ render
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, "
                     "price_agree, is_winner, fetched_at) VALUES "
                     "('P1', 'หจก.ผู้ชนะทดสอบ', '1111', '4200000', '4200000', 1, '2026-07-05')")
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, "
                     "price_agree, is_winner, fetched_at) VALUES "
                     "('P1', 'หจก.คู่แข่งทดสอบ', '2222', '4500000', NULL, 0, '2026-07-05')")
        # P2: snapshot ล้วน (ไม่มีใน projects_seen/project_locations)
        conn.execute(q, (1, 'P2', 'sent', '2026-07-06T08:00:00', 'บึงกาฬ', 'อาคารเรียนสองชั้น', 'สพฐ.ทดสอบ', 'province_tor_review', 0))
        # P3: LINE ส่งไม่สำเร็จ (quota เต็ม) → ยังต้องขึ้น (ไม่ผูกผลส่ง LINE, status='failed' อยู่ใน allowlist)
        conn.execute(q, (1, 'P3', 'failed', '2026-07-06T09:00:00', 'นครพนม', 'งานที่ส่งพลาด', '', 'province_qualified', 0))
        # P4: test data → ไม่ขึ้น
        conn.execute(q, (1, 'P4', 'sent', '2026-07-06T10:00:00', 'นครพนม', 'งานทดสอบระบบ', '', 'province_qualified', 1))
        # P5: queue status='cancelled' → ไม่ขึ้น
        conn.execute(q, (1, 'P5', 'cancelled', '2026-07-06T09:15:00', 'นครพนม', 'แถวคิวถูกยกเลิก', '', 'province_qualified', 0))
        # P6: status='skipped' (personal keyword gate N+207) → ไม่เคยยิง LINE จริง → ต้องไม่ขึ้น (Important#4)
        conn.execute(q, (1, 'P6', 'skipped', '2026-07-06T09:20:00', 'นครพนม', 'งานถูกกรอง keyword', '', 'province_qualified', 0))
        # P7: status='pending' (ยังไม่ถึงคิวส่ง) → ต้องไม่ขึ้น (Important#4)
        conn.execute(q, (1, 'P7', 'pending', '2026-07-06T09:25:00', 'นครพนม', 'งานรอคิวส่ง', '', 'province_qualified', 0))
        # P8: TOR review ที่ projects_seen.announce_type เลื่อนไป 'D0' แล้ว (lifecycle จริงไหลต่อ B0→D0)
        # ต้องยังขึ้นหัวข้อ TOR-review เสมอ ไม่ใช่ D0 (Important#3 — bug นี้เกิดเฉพาะตอน projects_seen
        # row มีอยู่จริงและ.announce_type ไม่ตรงกับตอนส่ง ซึ่ง P2 ข้างบนไม่จับเพราะไม่มี row เลย)
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, "
                     "project_name, dept_name, first_seen_at) VALUES "
                     "('P8', 'D0', 'นครพนม', 3000000, 'ถนนลูกรัง สายแปด', 'อบต.แปด', '2026-07-07')")
        conn.execute(q, (1, 'P8', 'sent', '2026-07-07T08:00:00', 'นครพนม', 'ถนนลูกรัง สายแปด', 'อบต.แปด', 'province_tor_review', 0))
        # P9/P10: followed_prelim / followed_cancelled — real formatter ยิง live network, endpoint
        # ต้อง fallback แบบย่อจากแคชเท่านั้น (Critical#2)
        conn.execute(q, (1, 'P9', 'sent', '2026-07-08T08:00:00', 'นครพนม', 'งานรอผลเบื้องต้น', 'อบต.เก้า', 'followed_prelim', 0))
        conn.execute(q, (1, 'P10', 'sent', '2026-07-08T09:00:00', 'นครพนม', 'งานถูกยกเลิกภายหลัง', 'อบต.สิบ', 'followed_cancelled', 0))
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


def seed_perf(n: int):
    """ลูกค้า UPERF: n โครงการ D0 แยกกันหมด (ไม่มี dedup) ยิง sent ทั้งก้อน — ใช้ยืนยันว่า
    limit ตัดงานหนัก (format_notification calls) จริง ไม่ใช่แค่ตัดขนาด response (Critical#1)."""
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                     "VALUES ('UPERF','ทดสอบ perf','trial','2026-01-01','2026-01-01')")
        q = ("INSERT INTO notification_queue (customer_id, project_id, status, created_at, "
             "province_snapshot, project_name_snapshot, dept_name_snapshot, source_stage, is_test_data) "
             "VALUES (?,?,?,?,?,?,?,?,?)")
        cust_id = conn.execute("SELECT id FROM customers WHERE line_user_id='UPERF'").fetchone()[0]
        for i in range(n):
            pid = f"PERF{i:03d}"
            conn.execute(q, (cust_id, pid, 'sent', f'2026-07-10T{8 + i % 12:02d}:00:00',
                             'นครพนม', f'งานถนนลาดยาง เลข {i}', 'อบต.เพิร์ฟ', 'province_qualified', 0))
    return cust_id


def main():
    seed()
    # 403 secret ผิด
    try:
        bms_api.portal_sebastian_feed_json(line_user_id='U1', x_bms_secret='bad')
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403

    r = bms_api.portal_sebastian_feed_json(line_user_id='U1', x_bms_secret='t')
    assert r["ok"] and r["count"] == 6, r  # P1(dedup), P2, P3(failed), P8, P9, P10 — ไม่มี P4(test)/
                                            # P5(cancelled)/P6(skipped)/P7(pending)
    msgs = r["messages"]
    ids = [m["project_id"] for m in msgs]
    # เรียงเก่า→ใหม่ (แชท) ตาม created_at ล่าสุดของแต่ละ project — P6(skipped)/P7(pending) ต้องไม่ขึ้น
    assert ids == ['P1', 'P2', 'P3', 'P8', 'P9', 'P10'], ids
    byid = {m["project_id"]: m for m in msgs}
    assert byid['P1']["stage"] == 'won' and byid['P1']["sent_at"] == '2026-07-05T08:00:00', byid['P1']
    assert byid['P1']["starred"] is True and byid['P2']["starred"] is False, byid

    # ── Critical#2: followed_winner ต้องใช้ format_winner_detailed() ไม่ใช่ format_notification() ──
    import cgd_intel as ci
    from Sebastian_LINE_Sender import format_winner_detailed, format_notification, _clean_project_name, _plain_text_body
    with bms_api.get_conn() as conn:
        results = [dict(r) for r in conn.execute(
            "SELECT * FROM bid_results WHERE project_id=? ORDER BY is_winner DESC, price_agree", ('P1',))]
        tokens = ci.match_keywords('ถนน คสล. สายหนึ่ง')
        loc = ci.resolve_location('P1', 'ถนน คสล. สายหนึ่ง', 'อบต.ทดสอบ', 'นครพนม', conn)
        analyzed = ci.analyze_bidders(conn, 'นครพนม', tokens, loc['tambon'], loc['amphoe'],
                                      5000000, results, warned=[])
    win = next(b for b in results if b.get("is_winner"))
    expected_full_name = _clean_project_name('ถนน คสล. สายหนึ่ง')
    expected_winner_msg = format_winner_detailed(expected_full_name, win['bidder_name'], win['price_agree'],
                                                 5000000, analyzed, None, {}, None, 'P1')
    assert byid['P1']["message"] == expected_winner_msg, (byid['P1']["message"], expected_winner_msg)
    assert '🏆 ผู้ชนะ: หจก.ผู้ชนะทดสอบ' in byid['P1']["message"], byid['P1']["message"]
    assert '🔔 พบงานเปิดกำหนดวันยื่นซองใหม่' not in byid['P1']["message"], byid['P1']["message"]  # ไม่ใช่ D0 generic

    # P2 ไม่มี projects_seen/project_locations → graceful (budget=0 "ไม่ระบุ", ไม่มี deadline)
    assert 'ไม่ระบุ' in byid['P2']["message"] or '💰' in byid['P2']["message"], byid['P2']["message"]
    assert '⏰' not in byid['P2']["message"], byid['P2']["message"]

    # P2 = TOR review (source_stage='province_tor_review') ไม่มี projects_seen row → announce_type
    # ต้อง fallback ให้ตรง stage จริง (ไม่ใช่เหมาแบบ "D0")
    assert byid['P2']["message"].startswith('📋 รับฟังคำวิจารณ์'), byid['P2']["message"]
    assert '🔔 พบงานเปิดกำหนดวันยื่นซองใหม่' not in byid['P2']["message"], byid['P2']["message"]

    # ── Important#3: P8 มี projects_seen.announce_type='D0' (เลื่อนไปแล้วจริง) แต่ source_stage
    # ยังบอกว่าเป็น TOR-review ตอนส่ง → ต้องขึ้นหัวข้อ TOR-review เสมอ ไม่ใช่ D0 ──
    assert byid['P8']["message"].startswith('📋 รับฟังคำวิจารณ์'), byid['P8']["message"]
    assert '🔔 พบงานเปิดกำหนดวันยื่นซองใหม่' not in byid['P8']["message"], byid['P8']["message"]

    # ── Critical#2: followed_prelim/followed_cancelled — fallback ย่อจากแคช ไม่ยิง live network ──
    assert byid['P9']["message"].startswith('📊 มีการประกาศราคาเบื้องต้น'), byid['P9']["message"]
    assert 'งานรอผลเบื้องต้น' in byid['P9']["message"], byid['P9']["message"]
    assert byid['P10']["message"].startswith('❌ งานนี้ถูกยกเลิกแล้ว'), byid['P10']["message"]
    assert 'งานถูกยกเลิกภายหลัง' in byid['P10']["message"], byid['P10']["message"]

    json.dumps(r, ensure_ascii=False)

    # record_prediction=False จริง — ต้องไม่มี row ใน price_predictions หลังเรียก endpoint
    # (P1 มี cgd_winners คู่แข่งจริงที่ seed ไว้ข้างบน; แม้ P1 ไปทาง followed_winner reconstruction
    # แล้ว (ไม่เรียก intel_context/compare_prediction เลยตามที่ตั้งใจ) ก็ยังต้อง cnt==0 อยู่ดี —
    # และ P2/P3/P8 ยังผ่าน format_notification(record_prediction=False) ตามเดิม)
    with bms_api.get_conn() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM price_predictions").fetchone()[0]
    assert cnt == 0, cnt

    # control: เรียก format_notification() ตรงๆ ด้วย seed เดียวกันแต่ record_prediction=True (default
    # ตอน production ส่งจริง) ต้องเขียนจริง 1 row — พิสูจน์ว่า path ไปถึง save_prediction() จริง
    format_notification(
        project_id='P1', province='นครพนม', announce_type='D0', budget=5000000,
        project_name='ถนน คสล. สายหนึ่ง', dept_name='อบต.ทดสอบ',
        bid_submit_date='2026-08-03', bid_submit_time='09.00-12.00 น.',
        source_stage='province_qualified', record_prediction=True,
    )
    with bms_api.get_conn() as conn:
        cnt2 = conn.execute("SELECT COUNT(*) FROM price_predictions").fetchone()[0]
    assert cnt2 == 1, cnt2

    # ลูกค้าไม่มี → ก้อนว่าง ไม่ crash
    r = bms_api.portal_sebastian_feed_json(line_user_id='U9', x_bms_secret='t')
    assert r == {"ok": True, "count": 0, "messages": []}, r

    # ── Critical#1: limit ต้อง bound งานหนักจริง (format_notification calls) ไม่ใช่แค่ response size ──
    # ── N+216: skip_intel=True ต้องกัน cgd_intel.intel_context() ไม่ให้ถูกเรียกเลยแม้แต่ครั้งเดียว
    # (วัดจริงบน prod: 44.8s สำหรับ 30 ข้อความ D0 เพราะ LIKE scan ~2M แถว cgd_winners ไม่มี index) ──
    N, LIMIT = 12, 5
    seed_perf(N)
    import Sebastian_LINE_Sender as sender_mod
    import cgd_intel as ci_mod
    orig_fn = sender_mod.format_notification
    orig_intel = ci_mod.intel_context
    calls = {"n": 0}
    intel_calls = {"n": 0}
    def _counting(*a, **kw):
        calls["n"] += 1
        return orig_fn(*a, **kw)
    def _counting_intel(*a, **kw):
        intel_calls["n"] += 1
        return orig_intel(*a, **kw)
    sender_mod.format_notification = _counting
    ci_mod.intel_context = _counting_intel
    try:
        rp = bms_api.portal_sebastian_feed_json(line_user_id='UPERF', x_bms_secret='t', limit=LIMIT)
    finally:
        sender_mod.format_notification = orig_fn
        ci_mod.intel_context = orig_intel
    assert rp["count"] == N, rp["count"]           # total dedup ก่อน slice ยังถูกต้อง (N โครงการ)
    assert len(rp["messages"]) == LIMIT, len(rp["messages"])
    assert calls["n"] == LIMIT, calls["n"]          # ← หัวใจของ fix เดิม: เรียก formatter แค่ LIMIT ครั้ง ไม่ใช่ N ครั้ง
    assert intel_calls["n"] == 0, intel_calls["n"]  # ← หัวใจของ hotfix N+216: ไม่เรียก cgd_intel เลยแม้แต่ครั้งเดียว
    # ได้ LIMIT โครงการ "ใหม่สุด" จริง (PERF011..PERF007 ตาม created_at DESC ก่อน reverse)
    got = [m["project_id"] for m in rp["messages"]]
    assert got == [f"PERF{i:03d}" for i in range(N - LIMIT, N)], got

    print("PASS test_portal_sebastian_feed_api")


main()
