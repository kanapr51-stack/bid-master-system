"""test_prelim_summary.py — parse_prelim_text: ราคา/จำนวนผู้เสนอ/เวลาเปิดเผย + 2-ซอง."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import prelim_summary as ps

# งานหลักเกณฑ์ราคา (มีราคา) — ตัวเลขไทย
TXT_PRICE = """สรุปข้อมูลการเสนอราคาเบื้องต้น
เลขที่โครงการ : ๖๙๐๕๙๐๗๕๔๕๔
จำนวนผู้เสนอราคา : ๓ ราย
หลักเกณฑ์การพิจารณา : หลักเกณฑ์ราคา
การเสนอราคาเบื้องต้น
รายการพิจารณา ราคาต่ำสุดที่เสนอ
รายการพิจารณาที่ ๑ ก่อสร้างถนน กว้าง ๔.๐๐ เมตร ๗๔๐,๐๐๐.๐๐
หมายเหตุ : โดยการเสนอราคาแบบเกณฑ์ขั้นต่ำ (๒ ซอง) ตามระเบียบ ข้อ ๘๓ (๓) จะไม่มีการแสดงข้อมูลราคา
เปิดเผย ณ วันที่ ๙ มิถุนายน ๒๕๖๙ เวลา ๑๒:๐๒ น."""

r = ps.parse_prelim_text(TXT_PRICE)
assert r["has_price"] is True, r
assert r["lowest_price"] == 740000.0, r
assert r["num_bidders"] == 3, r
assert r["revealed_at"] and "12:02" in r["revealed_at"], r

# งานเกณฑ์ขั้นต่ำ 2 ซอง — ไม่แสดงราคา (item line ไม่มีเลขราคา)
TXT_TWOENV = """สรุปข้อมูลการเสนอราคาเบื้องต้น
จำนวนผู้เสนอราคา : ๒ ราย
หลักเกณฑ์การพิจารณา : เกณฑ์ราคาประกอบเกณฑ์อื่น
รายการพิจารณา ราคาต่ำสุดที่เสนอ
รายการพิจารณาที่ ๑ ก่อสร้างอาคาร
หมายเหตุ : การเสนอราคาแบบเกณฑ์ขั้นต่ำ (๒ ซอง) จะไม่มีการแสดงข้อมูลราคา
เปิดเผย ณ วันที่ ๙ มิถุนายน ๒๕๖๙ เวลา ๑๔:๐๐ น."""
r2 = ps.parse_prelim_text(TXT_TWOENV)
assert r2["has_price"] is False and r2["lowest_price"] is None, r2
assert r2["num_bidders"] == 2, r2

# garbage → ปลอดภัย
r3 = ps.parse_prelim_text("ไม่มีข้อมูล")
assert r3["num_bidders"] is None and r3["lowest_price"] is None, r3

print("OK test_prelim_summary")
