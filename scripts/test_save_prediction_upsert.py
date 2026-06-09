"""test_save_prediction_upsert.py — save_prediction upsert ทับ prediction แต่ไม่ลบ actual."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()

# save ครั้งแรก (ค่า pooled)
db.save_prediction({"project_id": "P1", "budget": 1000000, "area_disc_lo": 5, "area_disc_hi": 30,
                    "area_price_lo": 700000, "area_price_hi": 950000, "top_name": "A", "top_disc": 20, "top_price": 800000})
# verify actual (W0)
db.update_prediction_actual("P1", 740000, 1, 1.5)
# save ครั้งสอง (ค่า concrete ที่โชว์จริง) → ต้องทับ prediction
db.save_prediction({"project_id": "P1", "budget": 1000000, "area_disc_lo": 24, "area_disc_hi": 41,
                    "area_price_lo": 590000, "area_price_hi": 760000, "top_name": "B", "top_disc": 30, "top_price": 700000})

p = db.get_prediction("P1")
assert p["area_price_hi"] == 760000, p          # prediction ทับแล้ว
assert p["area_disc_lo"] == 24, p
assert p["top_name"] == "B", p
assert p["actual_price"] == 740000, p           # actual ไม่ถูกลบ
assert p["in_range"] == 1 and p["error_pct"] == 1.5, p
assert p["verified_at"] is not None, p
print("OK test_save_prediction_upsert")
