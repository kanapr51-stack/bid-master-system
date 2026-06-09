"""test_format_prelim.py — format_prelim_notification (มีราคา + closed-loop / 2-ซอง)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as snd

# มีราคา + cmp (จาก compare_prediction_provisional)
prelim = {"has_price": True, "lowest_price": 740000.0, "num_bidders": 3, "revealed_at": "9 มิ.ย. 2569 12:02"}
cmp = {"held": False, "error_pct": 1.4, "upper": 730000, "area_price_lo": 670000, "area_price_hi": 730000}
txt = snd.format_prelim_notification("ถนนคอนกรีต ต.โพธิ์หมากแข้ง", 1017000, prelim, cmp, "P1")
assert "เบื้องต้น" in txt and "740,000" in txt and "3 ราย" in txt, txt
assert "กรอบบน" in txt and "730,000" in txt, txt
assert "รอประกาศผู้ชนะ" in txt and "P1" in txt, txt

# 2-ซอง (ไม่มีราคา) → ไม่มีบรรทัดเทียบ
prelim2 = {"has_price": False, "lowest_price": None, "num_bidders": 2, "revealed_at": ""}
txt2 = snd.format_prelim_notification("งาน", 1000000, prelim2, None, "P2")
assert "2 ราย" in txt2 and "ยังไม่เปิดเผย" in txt2, txt2
assert "กรอบบน" not in txt2, txt2
print("OK test_format_prelim")
