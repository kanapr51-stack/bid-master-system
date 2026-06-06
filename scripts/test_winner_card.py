"""test_winner_card.py — _winner_card_from_results: เลือกผู้ชนะ + dedupe คู่แข่ง จาก bid_results."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_LINE_Sender import _winner_card_from_results  # noqa: E402

item = {"project_id": "P1", "project_name": "ถนน คสล.", "budget": 1200000}
results = [  # winner + คู่แข่งซ้ำชื่อ (per line-item) → ต้อง dedupe
    {"bidder_name": "บ.A", "price_agree": "950000", "price_proposal": "950000", "is_winner": 1},
    {"bidder_name": "บ.B", "price_agree": "", "price_proposal": "1100000", "is_winner": 0},
    {"bidder_name": "บ.B", "price_agree": "", "price_proposal": "1100000", "is_winner": 0},  # ซ้ำ
    {"bidder_name": "บ.C", "price_agree": "", "price_proposal": "1050000", "is_winner": 0},
]
alt, flex = _winner_card_from_results(item, results)
txt = flex["body"]["contents"][1]["text"]  # detail text
assert "ประกาศผู้ชนะ" in alt, alt
assert "บ.A" in txt and "950,000" in txt, txt
assert txt.count("บ.B") == 1, "คู่แข่งซ้ำต้อง dedupe: " + txt
assert "บ.C" in txt and "1,050,000" in txt, txt
# ไม่มีปุ่ม (lifecycle จบ)
assert "footer" not in flex or not flex.get("footer"), "winner card ไม่ควรมีปุ่ม ⭐"

print("✅ PASS winner card from bid_results")
