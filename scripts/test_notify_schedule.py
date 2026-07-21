"""test_notify_schedule.py — helper กลาง per-customer notify time (N+201):
pref_time parse + is_due/mark ต่อ kind (daily_notify_log)."""
import os, sys, json, tempfile; from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()   # isolate จาก prod ก่อน import DB
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import notify_schedule as ns

TODAY, TOMORROW = "2026-07-12", "2026-07-13"


def test_pref_time():
    assert ns.DEFAULT_MORNING == "07:30"
    assert ns.pref_time(json.dumps({"morningNotifyTime": "06:15"}), "morningNotifyTime", "07:30") == "06:15"
    assert ns.pref_time(json.dumps({"morningNotifyTime": "9999"}), "morningNotifyTime", "07:30") == "07:30"
    assert ns.pref_time(json.dumps({"notifyTime": "23:00"}), "morningNotifyTime", "07:30") == "07:30"  # คนละ key
    assert ns.pref_time("", "morningNotifyTime", "07:30") == "07:30"
    assert ns.pref_time("not-json", "morningNotifyTime", "07:30") == "07:30"
    print("✅ pref_time parse + default")


def test_is_due_marker_per_kind():
    with db.get_connection() as conn:
        # ยังไม่ถึงเวลา → ไม่ due · ถึงแล้ว → due (รวมเลยเวลามานาน = self-healing)
        assert not ns.is_due(conn, "bidopen", 1, "07:30", "07:29", TODAY)
        assert ns.is_due(conn, "bidopen", 1, "07:30", "07:30", TODAY)
        assert ns.is_due(conn, "bidopen", 1, "07:30", "18:00", TODAY)
        # mark แล้ว → kind เดิมไม่ due ซ้ำ แต่ kind อื่น/วันใหม่/ลูกค้าอื่น ยัง due
        ns.mark_sent(conn, "bidopen", 1, TODAY, TODAY + "T07:30:05")
        assert not ns.is_due(conn, "bidopen", 1, "07:30", "07:45", TODAY)
        assert ns.is_due(conn, "timeline", 1, "07:30", "07:45", TODAY)   # คนละ kind
        assert ns.is_due(conn, "bidopen", 2, "07:30", "07:45", TODAY)    # คนละลูกค้า
        assert ns.is_due(conn, "bidopen", 1, "07:30", "07:45", TOMORROW) # วันใหม่
    print("✅ is_due + marker แยกต่อ kind/ลูกค้า/วัน")


def test_webpush_ctx_suppresses_retry():
    """N+208: LINE retry ทุก 15 นาทีตอน fail (quota เต็ม ฯลฯ) ต้อง mirror webpush แค่ครั้งแรก/วัน/kind."""
    with db.get_connection() as conn:
        # ครั้งแรกที่ due วันนี้ → mirror ปกติ (None) แม้ LINE จะยังไม่รู้ผล
        assert ns.webpush_ctx(conn, "bidopen", 10, TODAY, TODAY + "T07:30:05") is None
        # รอบ retry ถัดไป (LINE ยัง fail อยู่) → suppress กันเด้งซ้ำ
        assert ns.webpush_ctx(conn, "bidopen", 10, TODAY, TODAY + "T07:45:07") == {"suppress": True}
        assert ns.webpush_ctx(conn, "bidopen", 10, TODAY, TODAY + "T08:00:03") == {"suppress": True}
        # คนละ kind / ลูกค้า / วัน → ยังนับเป็นครั้งแรก (mirror ปกติ)
        assert ns.webpush_ctx(conn, "timeline", 10, TODAY, TODAY + "T07:45:07") is None
        assert ns.webpush_ctx(conn, "bidopen", 11, TODAY, TODAY + "T07:45:07") is None
        assert ns.webpush_ctx(conn, "bidopen", 10, TOMORROW, TOMORROW + "T07:30:00") is None
        # ไม่ชนกับ marker LINE เดิม (daily_notify_log kind='bidopen' ของ customer 1 จาก test ก่อนหน้า)
        assert not ns.sent_today(conn, "bidopen", 10, TODAY)   # LINE เอง (คนละ kind กับ 'bidopen_webpush') ยังไม่ mark
    print("✅ webpush_ctx: suppress ตั้งแต่รอบ 2 เป็นต้นไป ต่อ kind/ลูกค้า/วัน")


def test_graceful_no_table():
    import sqlite3
    empty = sqlite3.connect(":memory:")
    assert not ns.sent_today(empty, "bidopen", 1, TODAY)   # ไม่มีตาราง → ถือว่ายังไม่ส่ง ไม่ throw
    print("✅ graceful schema เก่า")


test_pref_time()
test_is_due_marker_per_kind()
test_webpush_ctx_suppresses_retry()
test_graceful_no_table()
print("ALL PASS notify_schedule")
