"""test_deadline_time.py — งาน 1: เพิ่มช่วงเวลายื่นซองในการ์ด (province_api path).
deadline_provider ดึงเวลา + เก็บ project_locations.deadline_time + _deadline_from_db คืนเวลา."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import deadline_provider_doczip as dp
from Sebastian_Customer_DB import init_schema, get_connection
import Sebastian_LINE_Sender as snd


def test_extract_time():
    assert dp._extract_time("ระหว่างเวลา 13.00 น. ถึง 16.00 น.") == "13.00-16.00 น."
    assert dp._extract_time("ระหว่างเวลา 8.30 น. ถึง 16.30 น.") == "8.30-16.30 น."
    assert dp._extract_time("ในวันที่ 20 มิถุนายน 2569") is None   # ไม่มีช่วงเวลา
    print("✅ _extract_time (ช่วงเวลายื่น)")


def test_parse_returns_triple():
    # parse_deadline_from_pdf ต้องคืน 3-tuple (date, time, stage) — pdf ขยะ → (None, None, error)
    d, t, stage = dp.parse_deadline_from_pdf(b"not a pdf")
    assert d is None and t is None and stage in ("pdf_error", "no_text"), (d, t, stage)
    print("✅ parse_deadline_from_pdf คืน 3-tuple")


def test_deadline_from_db_reads_time():
    init_schema()
    with get_connection() as c:
        c.execute("INSERT INTO project_locations (project_id, deadline, deadline_time, created_at) "
                  "VALUES ('PT1','2026-06-20','13.00-16.00 น.','2026-06-11')")
    assert snd._deadline_from_db("PT1") == ("2026-06-20", "13.00-16.00 น."), snd._deadline_from_db("PT1")
    # งานไม่มีเวลา → คืน date + เวลาว่าง (ไม่ error)
    with get_connection() as c:
        c.execute("INSERT INTO project_locations (project_id, deadline, created_at) "
                  "VALUES ('PT2','2026-06-21','2026-06-11')")
    assert snd._deadline_from_db("PT2") == ("2026-06-21", ""), snd._deadline_from_db("PT2")
    print("✅ _deadline_from_db อ่าน deadline_time (+ ไม่มีเวลาไม่พัง)")


def test_card_shows_time():
    card = snd.format_notification("PT1", province="นครพนม", announce_type="D0", budget=5000000,
                                   project_name="ถนน คสล.", dept_name="อบต.x",
                                   bid_submit_date="2026-06-20", bid_submit_time="13.00-16.00 น.",
                                   source_stage="followed_bid_open")
    assert "⏰ ยื่นซอง 20 มิ.ย. 13.00-16.00 น." in card, card
    print("✅ การ์ดโชว์เวลายื่นซอง")


if __name__ == "__main__":
    test_extract_time()
    test_parse_returns_triple()
    test_deadline_from_db_reads_time()
    test_card_shows_time()
    print("\n✅ ALL test_deadline_time PASS")
