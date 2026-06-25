"""test_format_cancelled.py — การ์ดแจ้งงานยกเลิก (followed_cancelled)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_ENV"] = "dev"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_LINE_Sender import format_cancelled_notification


# เต็ม: ชื่อ + จังหวัด + note
t = format_cancelled_notification("ก่อสร้างถนน คสล. สายบ้านแพง", "นครพนม", "ยกเลิกระหว่างยื่นซอง (S01)")
assert "❌ โครงการถูกยกเลิก" in t, t
assert "ก่อสร้างถนน คสล. สายบ้านแพง" in t, t
assert "📍 จ.นครพนม" in t, t
assert "ยกเลิกระหว่างยื่นซอง (S01)" in t, t
print("✅ การ์ดเต็ม (ชื่อ+จังหวัด+note)")

# ไม่มีจังหวัด → ไม่มีบรรทัด 📍
t2 = format_cancelled_notification("งาน X", "", "")
assert "❌ โครงการถูกยกเลิก" in t2 and "งาน X" in t2, t2
assert "📍" not in t2, t2
print("✅ การ์ดไม่มีจังหวัด → ไม่มี 📍")

# ไม่มี note → ไม่ crash, ยังมีหัวข้อ + ชื่อ
t3 = format_cancelled_notification("งาน Y", "บึงกาฬ")
assert "📍 จ.บึงกาฬ" in t3 and "งาน Y" in t3, t3
print("✅ การ์ดไม่มี note")

print("✅ ALL PASS test_format_cancelled")
