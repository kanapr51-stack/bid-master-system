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


def test_build_explain_shape():
    import cgd_intel as ci
    ex = ci._build_explain(
        inputs={"budget": 2500000, "project_name": "ถนน X", "province": "นครพนม",
                "tambon": "ก", "amphoe": "ข", "location_confidence": "HIGH"},
        classify={"subtype": "concrete_road", "market": "local", "work_kind": "new"},
        scope_level="ตำบล", n=12,
        analysis={"disc_lo": 0.22, "disc_med": 0.27, "disc_hi": 0.31,
                  "top_name": "หจก. ก", "top_disc": 0.28},
        raw_records=[{"project_name": "ถนน Y", "winner": "หจก. ก",
                      "win_price": 1980000, "discount": 0.26}],
        output={"price_lo": 1725000, "price_med": 1825000, "price_hi": 1950000})
    assert ex["schema_version"] == 1
    assert ex["scope"]["level"] == "ตำบล" and ex["scope"]["n"] == 12
    assert ex["classify"]["subtype"] == "concrete_road"
    assert ex["raw_records"][0]["winner"] == "หจก. ก"
    assert ex["output"]["price_med"] == 1825000
    print("✅ _build_explain shape")


def test_audit_list_requires_key():
    _fresh_db()  # ตั้ง BMS_DB_PATH + สร้าง schema (price_predictions)
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    import bms_api
    importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    c = TestClient(bms_api.app)
    assert c.get("/audit").status_code == 401, "ไม่มี key ต้อง 401"
    assert c.get("/audit?key=wrong").status_code == 401, "key ผิดต้อง 401"
    assert c.get("/audit?key=secret123").status_code == 200, "key ถูกต้อง 200"
    print("✅ /audit auth (401/401/200)")


if __name__ == "__main__":
    test_save_prediction_stores_explain_json()
    test_build_explain_shape()
    test_audit_list_requires_key()
    print("ALL PASS audit_view")
