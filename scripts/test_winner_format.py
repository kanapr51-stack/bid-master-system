"""test_winner_format.py — การ์ดแจ้งผู้ชนะ (winner + คู่แข่ง + ราคา) สำหรับงานติดตาม."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_LINE_Sender import format_winner  # noqa: E402

msg = format_winner(
    project_name="ก่อสร้างถนน คสล. ต.บ้านแพง",
    winner="บริษัท เอ จำกัด", price_agree="950000",
    competitors=[{"name": "บริษัท บี จำกัด", "price": "1100000"},
                 {"name": "บริษัท ซี จำกัด", "price": "1050000"}],
    budget=1200000, project_id="69069999999")

assert "ประกาศผู้ชนะ" in msg, msg
assert "บริษัท เอ จำกัด" in msg and "950,000" in msg, msg
assert "บริษัท บี จำกัด" in msg and "1,100,000" in msg, msg
assert "บริษัท ซี จำกัด" in msg and "1,050,000" in msg, msg
assert "69069999999" in msg, msg

# ไม่มีคู่แข่ง (ผู้ยื่นรายเดียว)
msg2 = format_winner("งานเล็ก", "บ.เดียว", "50000", competitors=[], budget=0, project_id="P2")
assert "ประกาศผู้ชนะ" in msg2 and "บ.เดียว" in msg2, msg2
assert "50,000" in msg2, msg2

print("✅ PASS winner format")
