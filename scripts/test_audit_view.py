"""test_audit_view.py — Price Prediction Audit View (plain-script style, รันด้วย python scripts/test_audit_view.py)

แยก temp DB ต่อ test ด้วย BMS_DATA_DIR (Customer_DB) + BMS_DB_PATH (bms_api) → ไม่แตะ prod.
"""
import os
import sys
import json
import tempfile
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")


def _fresh_db():
    """temp dir ใหม่ → ชี้ทั้ง Customer_DB และ bms_api มาที่ไฟล์เดียวกัน + init_schema."""
    d = tempfile.mkdtemp(prefix="bms_audit_test_")
    os.environ["BMS_DATA_DIR"] = d
    os.environ["BMS_DB_PATH"] = str(Path(d) / "bms_customers.db")
    import Sebastian_Customer_DB as db
    importlib.reload(db)
    db.init_schema()
    return db


def test_save_prediction_stores_explain_json():
    db = _fresh_db()
    explain = {"schema_version": 1, "scope": {"level": "tambon", "n": 12}}
    db.save_prediction({"project_id": "P1", "budget": 2500000,
                        "area_price_lo": 1700000, "area_price_hi": 1950000,
                        "explain_json": json.dumps(explain, ensure_ascii=False)})
    row = db.get_prediction("P1")
    assert row is not None, "prediction ไม่ถูกเก็บ"
    assert json.loads(row["explain_json"])["scope"]["n"] == 12, row.get("explain_json")
    print("✅ save_prediction stores explain_json")


if __name__ == "__main__":
    test_save_prediction_stores_explain_json()
    print("ALL PASS audit_view")
