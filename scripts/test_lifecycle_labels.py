"""test_lifecycle_labels.py — ยืนยันป้ายหัวข้อ lifecycle ครบ (bid_open/prelim/winner)."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls   # noqa: E402


def test_bid_open_label():
    body = ls.format_notification(
        "J1", province="นครพนม", budget=500000,
        project_name="งานถนน", dept_name="อบต.บ้านแพง",
        announce_type="D0", source_stage="followed_bid_open")
    assert "ติดตาม" in body and "ยื่นซอง" in body, body
    print("✅ followed_bid_open label")


test_bid_open_label()
print("ALL PASS lifecycle_labels")
