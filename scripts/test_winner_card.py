"""test_winner_card.py — _winner_card_from_results: เลือกผู้ชนะ + dedupe คู่แข่ง + บรรทัดเทียบคำทำนาย."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db; db.init_schema()  # noqa: E402
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


# ── closed-loop: การ์ดผู้ชนะมีบรรทัดเทียบคาด vs จริง (เมื่อ prediction verified) ──
db.save_prediction({"project_id": "WC1", "budget": 2000000,
                    "area_price_lo": 1700000, "area_price_hi": 1840000})
db.update_prediction_actual("WC1", 1750000, 1, 3.0)
item2 = {"project_id": "WC1", "project_name": "ถนน", "budget": 2000000}
res2 = [{"bidder_name": "บ.A", "price_agree": "1750000", "price_proposal": "1750000", "is_winner": 1}]
_alt2, flex2 = _winner_card_from_results(item2, res2)
body2 = flex2["body"]["contents"][1]["text"]
assert "Sebastian คาด" in body2 and "ตรง" in body2, body2
# ไม่มี prediction → การ์ดปกติ (ไม่มีบรรทัด)
_a3, flex3 = _winner_card_from_results({"project_id": "NOPRED", "project_name": "x", "budget": 1}, res2)
assert "Sebastian คาด" not in flex3["body"]["contents"][1]["text"]
print("✅ PASS winner card prediction line")
