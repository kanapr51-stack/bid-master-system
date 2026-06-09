"""test_compare_upper_bound.py — compare_prediction เทียบกรอบบน + provisional ไม่เขียน DB."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import cgd_intel as ci

db.save_prediction({"project_id": "P1", "budget": 1000000, "area_disc_lo": 28, "area_disc_hi": 33,
                    "area_price_lo": 670000, "area_price_hi": 730000, "top_name": "A", "top_disc": 30, "top_price": 700000})

# formal: actual 740000 > hi 730000 → นอกกรอบ (สูงกว่า) error +1.37%
v = ci.compare_prediction("P1", 740000)
assert v and v["held"] is False, v
assert abs(v["error_pct"] - 1.37) < 0.1, v       # (740000-730000)/730000*100
assert v["upper"] == 730000, v
# commit แล้ว (verified)
p = db.get_prediction("P1")
assert p["actual_price"] == 740000 and p["verified_at"] is not None, p
assert p["in_range"] == 0, p                      # held=False → in_range=0

# provisional (Round 1): ไม่เขียน DB
db.save_prediction({"project_id": "P2", "budget": 1000000, "area_disc_lo": 28, "area_disc_hi": 33,
                    "area_price_lo": 670000, "area_price_hi": 730000, "top_name": "A", "top_disc": 30, "top_price": 700000})
vp = ci.compare_prediction_provisional("P2", 720000)   # 720000 <= 730000 → held
assert vp and vp["held"] is True and vp["upper"] == 730000, vp
p2 = db.get_prediction("P2")
assert p2["actual_price"] is None and p2["verified_at"] is None, p2   # ไม่เขียน

print("OK test_compare_upper_bound")
