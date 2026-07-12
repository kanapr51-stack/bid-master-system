"""test_daily_recap.py — Daily summary = recap: นับงานวันนี้ + todo พรุ่งนี้ + โน้ต due."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db   # noqa: E402
db.init_schema()
import Sebastian_Daily_User_Summary as dus  # noqa: E402

TODAY = "2026-07-02"
TOMORROW = "2026-07-03"


def _seed():
    s = db.SubscriptionStore()
    cid = s.add_customer("Uaa", "กัญจน์")
    with db.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO projects_seen (project_id, province, project_name, first_seen_at) "
                     "VALUES ('P1','นครพนม','ก่อสร้างถนน คสล.', ?)", (TODAY,))
        conn.execute("INSERT INTO delivery_log (customer_id, project_id, status, attempted_at, is_test_data) "
                     "VALUES (?, 'P1', 'sent', ?, 0)", (cid, TODAY + "T09:00:00"))
        conn.execute("INSERT INTO job_notes (customer_id, project_id, entry_date, note, created_at) "
                     "VALUES (?, 'P1', ?, 'เตรียมเอกสารยื่นซอง', ?)", (cid, TOMORROW, TODAY))
    return cid


def test_fetch_today_sent():
    cid = _seed()
    with db.get_connection() as conn:
        jobs = dus.fetch_today_sent(conn, cid, TODAY)
    assert len(jobs) == 1 and jobs[0]["project_id"] == "P1", jobs
    assert "ถนน" in jobs[0]["name"], jobs
    print("✅ fetch_today_sent")


def test_fetch_notes_due():
    cid = _seed()
    with db.get_connection() as conn:
        due = dus.fetch_notes_due(conn, cid, TOMORROW)
    assert len(due) == 1 and "เอกสาร" in due[0]["note"], due
    print("✅ fetch_notes_due")


def test_recap_message_has_all_sections():
    msg = dus.build_message(
        "กัญจน์", 1,
        today_jobs=[{"project_id": "P1", "name": "ก่อสร้างถนน คสล."}],
        tomorrow_jobs=[{"project_id": "P2", "name": "งานยื่นพรุ่งนี้"}],
        notes_due=[{"project_id": "P1", "note": "เตรียมเอกสารยื่นซอง"}])
    assert "1 งาน" in msg, msg          # นับวันนี้
    assert "ถนน" in msg, msg             # รายการวันนี้
    assert "พรุ่งนี้" in msg, msg        # todo พรุ่งนี้
    assert "เอกสาร" in msg, msg          # โน้ต due
    print("✅ recap message ครบ 4 ส่วน")


def test_notify_time_parse():
    import json
    assert dus.DEFAULT_NOTIFY == "23:00"                                      # กัญจน์ 2026-07-12
    assert dus._notify_time(json.dumps({"notifyTime": "06:30"})) == "06:30"
    assert dus._notify_time(json.dumps({"notifyTime": "25:99"})) == "23:00"   # format ผิด → default
    assert dus._notify_time(json.dumps({"classes": []})) == "23:00"          # ไม่มี key
    assert dus._notify_time("") == "23:00"
    assert dus._notify_time("not-json") == "23:00"
    print("✅ _notify_time parse + default 23:00")


def test_is_due_and_marker():
    cid = _seed()
    with db.get_connection() as conn:
        # ยังไม่ถึงเวลา → ไม่ due
        assert not dus.is_due(conn, cid, "20:00", "19:59", TODAY)
        # ถึงเวลา + ยังไม่ mark → due (รวมกรณีเลยเวลามานาน = self-healing)
        assert dus.is_due(conn, cid, "20:00", "20:00", TODAY)
        assert dus.is_due(conn, cid, "06:00", "23:00", TODAY)
        # mark แล้ว → ไม่ due ซ้ำ (วันเดียวกัน) แต่วันใหม่ due ได้
        dus.mark_recap_sent(conn, cid, TODAY, TODAY + "T20:00:05")
        assert not dus.is_due(conn, cid, "20:00", "20:30", TODAY)
        assert dus.is_due(conn, cid, "20:00", "20:30", TOMORROW)
    print("✅ is_due + marker กันส่งซ้ำ")


def test_morning_variant_message():
    msg = dus.build_message(
        "กัญจน์", 2,
        today_jobs=[{"project_id": "P1", "name": "งานเมื่อวาน 1"}, {"project_id": "P2", "name": "งานเมื่อวาน 2"}],
        tomorrow_jobs=[{"project_id": "P3", "name": "งานเปิดยื่นวันนี้"}],
        notes_due=[{"project_id": "P1", "note": "ยื่นซองเช้านี้"}], morning=True)
    assert "เมื่อวานผมส่งงาน" in msg and "2 งาน" in msg, msg
    assert "วันนี้มีงานเปิดยื่นซอง" in msg, msg
    assert "โน้ตที่ถึงกำหนดวันนี้" in msg, msg
    assert "พรุ่งนี้" not in msg, msg
    # ฉบับเช้า ไม่มีงานเมื่อวาน → copy ถูกกาล
    msg0 = dus.build_message("กัญจน์", 0, morning=True)
    assert "เมื่อวานยังไม่มีงานใหม่" in msg0, msg0
    print("✅ morning variant (เมื่อวาน/วันนี้)")


test_fetch_today_sent()
test_fetch_notes_due()
test_recap_message_has_all_sections()
test_notify_time_parse()
test_is_due_and_marker()
test_morning_variant_message()
print("ALL PASS daily_recap")
