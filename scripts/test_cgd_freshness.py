"""test_cgd_freshness.py — parse Thai date + รายงาน max date/ปี."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
from cgd_freshness import parse_thai_date
import datetime as dt
assert parse_thai_date("9-เม.ย.-69") == dt.date(2026, 4, 9), parse_thai_date("9-เม.ย.-69")
assert parse_thai_date("15-ม.ค.-68") == dt.date(2025, 1, 15)
assert parse_thai_date("-") is None
assert parse_thai_date("") is None
print("✅ PASS cgd_freshness parser")
