"""test_format_winner_detailed.py — Round 2: ผู้ชนะ + ความแม่น + breakdown ต่อราย + ป้าย."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as snd

analyzed = [
    {"name": "หจก.X", "price": 738000, "discount": 27.4, "is_winner": True,
     "hist": {"scope": "ตำบล", "n": 2, "median": 25.0}, "trend": "↑", "tag": "warned"},
    {"name": "หจก.Y", "price": 752000, "discount": 26.1, "is_winner": False,
     "hist": {"scope": "นอกตำบล", "n": 4, "median": 30.0}, "trend": "↓", "tag": "regular_missed"},
    {"name": "หจก.Z", "price": 760000, "discount": 25.3, "is_winner": False,
     "hist": {"scope": "", "n": 0, "median": None}, "trend": None, "tag": "newcomer"},
]
cmp = {"held": False, "error_pct": 1.1, "upper": 730000}
acc = {"verified": 5, "in_range": 4, "in_range_pct": 80.0}
txt = snd.format_winner_detailed("ถนนคอนกรีต", "หจก.X", 738000, 1017000, analyzed, cmp, acc, 28.0, "P1")
assert "ผู้ชนะ: หจก.X" in txt and "738,000" in txt, txt
assert "เทียบกรอบบน" in txt and "อยู่ในกรอบ 4/5" in txt, txt
assert "หจก.Y" in txt and "เจ้าประจำ" in txt, txt          # ป้าย regular_missed
assert "หน้าใหม่" in txt, txt                                # Z
assert "ตลาดตำบล 28" in txt, txt
print("OK test_format_winner_detailed")
