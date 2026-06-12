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


def test_audit_detail_renders_explain():
    db = _fresh_db()
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    explain = {"schema_version": 1,
               "classify": {"subtype": "concrete_road", "market": "local"},
               "scope": {"level": "ตำบล", "n": 12},
               "analysis": {"disc_med": 0.27, "top_name": "หจก. ก"},
               "raw_records": [{"project_name": "ถนน Y", "winner": "หจก. ก",
                                "win_price": 1980000, "discount": 0.26}],
               "output": {"price_med": 1825000}}
    db.save_prediction({"project_id": "P9", "budget": 2500000,
                        "area_price_lo": 1700000, "area_price_hi": 1950000,
                        "explain_json": json.dumps(explain, ensure_ascii=False)})
    import bms_api
    importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    c = TestClient(bms_api.app)
    assert c.get("/audit/P9").status_code == 401, "ไม่มี key ต้อง 401"
    html = c.get("/audit/P9?key=secret123").text
    assert "ถนนคอนกรีต" in html, "ต้องมี subtype (แปลไทยแล้ว v2)"
    assert "หจก. ก" in html, "ต้องมีผู้ชนะ raw record"
    assert "1,980,000" in html, "ต้องมีราคาชนะ format comma"
    print("✅ /audit/{id} detail renders explain")


def test_resave_with_explain_preserves_closed_loop():
    """re-save prediction (พร้อม explain ใหม่) ต้องไม่ลบ actual_price/in_range/error_pct เดิม."""
    db = _fresh_db()
    db.save_prediction({"project_id": "P5", "budget": 2000000,
                        "area_price_lo": 1600000, "area_price_hi": 1800000,
                        "area_price_med": 1700000,
                        "explain_json": json.dumps({"v": "old"}, ensure_ascii=False)})
    db.update_prediction_actual("P5", actual_price=1720000, in_range=1, error_pct=1.2)
    # re-predict: เซฟใหม่พร้อม explain ใหม่
    db.save_prediction({"project_id": "P5", "budget": 2000000,
                        "area_price_lo": 1650000, "area_price_hi": 1820000,
                        "explain_json": json.dumps({"v": "new"}, ensure_ascii=False)})
    row = db.get_prediction("P5")
    assert row["actual_price"] == 1720000, "actual_price ถูกลบ!"
    assert row["in_range"] == 1 and row["error_pct"] == 1.2, "closed-loop เพี้ยน"
    assert json.loads(row["explain_json"])["v"] == "new", "explain ไม่อัปเดต"
    assert row["area_price_lo"] == 1650000, "prediction ไม่อัปเดต"
    print("✅ re-save preserves closed-loop (actual/in_range/error)")


def test_prelim_does_not_touch_official():
    db = _fresh_db()
    db.save_prediction({"project_id": "PP", "budget": 2000000,
                        "area_price_lo": 1600000, "area_price_hi": 1800000})
    db.update_prediction_actual("PP", actual_price=1720000, in_range=1, error_pct=1.2)
    db.update_prediction_prelim("PP", prelim_price=1650000, in_range=0, error_pct=-8.3)
    r = db.get_prediction("PP")
    assert r["prelim_price"] == 1650000 and r["prelim_in_range"] == 0
    assert r["prelim_error_pct"] == -8.3 and r["prelim_at"]
    assert r["actual_price"] == 1720000 and r["in_range"] == 1 and r["error_pct"] == 1.2
    print("✅ prelim แยกจาก official")


def test_label_helpers():
    import bms_api as a
    assert a._stage_label("PRELIM").startswith("🟡")
    assert "ผู้ชนะ" in a._stage_label("W0")
    assert a._stage_label("ZZZ") in ("—", "ZZZ")
    assert a._most_advanced_stage(["D0", "W0", "PRELIM"]) == "W0"
    assert a._most_advanced_stage([]) == ""
    assert a._work_kind_label("new") == "สร้างใหม่"
    assert a._market_label("local") == "ท้องถิ่น (อปท.)"
    assert a._subtype_label("concrete_road") == "ถนนคอนกรีต"
    assert a._subtype_label(None) == "—"
    print("✅ label helpers")


def test_audit_list_shows_name_and_stage():
    db = _fresh_db()
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    db.save_prediction({"project_id": "PL", "budget": 2000000,
                        "area_price_lo": 1600000, "area_price_hi": 1800000})
    with db.get_connection() as conn:
        conn.execute("INSERT INTO projects_seen(project_id,project_name,first_seen_at) VALUES(?,?,?)",
                     ("PL", "ก่อสร้างถนนทดสอบ", "2026-06-12"))
        conn.execute("INSERT INTO followed_jobs(customer_id,project_id,starred_at,last_stage_notified,status)"
                     " VALUES(1,'PL','2026-06-12','PRELIM','active')")
        conn.execute("INSERT INTO followed_jobs(customer_id,project_id,starred_at,last_stage_notified,status)"
                     " VALUES(2,'PL','2026-06-12','D0','active')")
    import bms_api, importlib
    importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    html = TestClient(bms_api.app).get("/audit?key=secret123").text
    assert "ก่อสร้างถนนทดสอบ" in html, "ต้องมีชื่องาน"
    assert "ราคาเบื้องต้น" in html, "stage ต้องเป็น PRELIM (ก้าวหน้าสุดจาก 2 customer)"
    print("✅ list แสดงชื่องาน + stage")


def test_audit_detail_category_and_prelim():
    db = _fresh_db()
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    explain = {"schema_version": 1, "inputs": {"work_type": "ถนน"},
               "classify": {"subtype": "concrete_road", "market": "local", "work_kind": "new"},
               "scope": {"level": "ตำบล", "n": 4}, "analysis": {"disc_med": 0.27},
               "raw_records": [], "output": {"price_med": 1700000}}
    db.save_prediction({"project_id": "PD", "budget": 2000000,
                        "area_price_lo": 1600000, "area_price_hi": 1800000,
                        "area_price_med": 1700000,
                        "explain_json": json.dumps(explain, ensure_ascii=False)})
    db.update_prediction_prelim("PD", prelim_price=1650000, in_range=1, error_pct=-2.9)
    import bms_api, importlib
    importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    html = TestClient(bms_api.app).get("/audit/PD?key=secret123").text
    assert "ถนนคอนกรีต" in html and "สร้างใหม่" in html and "ท้องถิ่น (อปท.)" in html, "บล็อกหมวดงาน"
    assert "ราคาเบื้องต้น (ยังไม่ทางการ)" in html and "1,650,000" in html, "บล็อก PRELIM"
    print("✅ detail หมวดงาน + PRELIM")


if __name__ == "__main__":
    test_save_prediction_stores_explain_json()
    test_build_explain_shape()
    test_audit_list_requires_key()
    test_audit_detail_renders_explain()
    test_resave_with_explain_preserves_closed_loop()
    test_prelim_does_not_touch_official()
    test_label_helpers()
    test_audit_list_shows_name_and_stage()
    test_audit_detail_category_and_prelim()
    print("ALL PASS audit_view")
