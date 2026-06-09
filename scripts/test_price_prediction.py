"""test_price_prediction.py — price_predictions CRUD + accuracy summary + compare_prediction."""
import os, tempfile, sys; from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db; db.init_schema()


def test_prediction_crud():
    with db.get_connection() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(price_predictions)")]
    assert "project_id" in cols and "area_price_lo" in cols and "in_range" in cols, cols
    db.save_prediction({"project_id": "P1", "budget": 2000000, "area_disc_lo": 8, "area_disc_hi": 15,
                        "area_price_lo": 1700000, "area_price_hi": 1840000, "top_name": "หจก.A",
                        "top_disc": 11, "top_price": 1780000})
    db.save_prediction({"project_id": "P1", "budget": 999, "area_disc_lo": 1, "area_disc_hi": 2,
                        "area_price_lo": 500000, "area_price_hi": 600000, "top_name": "หจก.B",
                        "top_disc": 5, "top_price": 550000})   # upsert — ทับด้วยค่าล่าสุด
    p = db.get_prediction("P1")
    assert p["budget"] == 999 and p["area_price_lo"] == 500000, p   # ทับแล้ว
    db.update_prediction_actual("P1", actual_price=1750000, in_range=1, error_pct=3.0)
    p2 = db.get_prediction("P1")
    assert p2["actual_price"] == 1750000 and p2["in_range"] == 1, p2
    # re-save prediction หลัง W0 ต้องไม่ลบ actual
    db.save_prediction({"project_id": "P1", "budget": 888, "area_disc_lo": 1, "area_disc_hi": 2,
                        "area_price_lo": 400000, "area_price_hi": 500000, "top_name": "หจก.C",
                        "top_disc": 5, "top_price": 450000})
    p3 = db.get_prediction("P1")
    assert p3["budget"] == 888 and p3["actual_price"] == 1750000, p3   # prediction ทับ, actual คง
    assert db.get_prediction("NOPE") is None
    print("✅ prediction CRUD + upsert")


def test_accuracy_summary():
    with db.get_connection() as c:
        c.execute("DELETE FROM price_predictions")   # เริ่มสะอาด (กันปนจาก test ก่อน)
    for pid, inr, err in [("A", 1, 2.0), ("B", 1, 4.0), ("C", 0, 18.0)]:
        db.save_prediction({"project_id": pid, "budget": 1})
        db.update_prediction_actual(pid, actual_price=1, in_range=inr, error_pct=err)
    s = db.prediction_accuracy_summary()
    assert s["verified"] == 3 and s["in_range"] == 2, s
    assert s["in_range_pct"] == 66.7 and s["mean_error_pct"] == 8.0, s
    print("✅ accuracy summary")


def test_compare_prediction():
    import cgd_intel as ci
    db.save_prediction({"project_id": "W1", "budget": 2000000, "area_disc_lo": 8, "area_disc_hi": 15,
                        "area_price_lo": 1700000, "area_price_hi": 1840000, "top_name": "A",
                        "top_disc": 11, "top_price": 1780000})
    v = ci.compare_prediction("W1", 1750000)   # ในช่วง 1.70–1.84 (mid 1.77 → err ~1%)
    assert v["in_range"] is True and v["error_pct"] <= 8, v
    p = db.get_prediction("W1")
    assert p["actual_price"] == 1750000 and p["in_range"] == 1, p
    # นอกช่วง
    db.save_prediction({"project_id": "W2", "budget": 2000000, "area_price_lo": 1700000, "area_price_hi": 1840000})
    v2 = ci.compare_prediction("W2", 1500000)
    assert v2["in_range"] is False, v2
    # ไม่มี prediction / actual แปลงไม่ได้ → None
    assert ci.compare_prediction("NOPE", 1) is None
    assert ci.compare_prediction("W1", "ไม่ใช่ตัวเลข") is None
    print("✅ compare_prediction")


if __name__ == "__main__":
    test_prediction_crud()
    test_accuracy_summary()
    test_compare_prediction()
    print("ALL PASS price_prediction")
