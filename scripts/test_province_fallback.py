"""test_province_fallback.py — อำเภอไม่มี precedent แต่จังหวัดมี ≥3 → คาดจากจังหวัด + ป้ายเตือน
bug 2026-06-12: งานรั้ว อ.บึงโขงหลง (0 precedent) ทั้งที่บึงกาฬมีรั้ว 8 ราย → ควร fallback
รันด้วย: python scripts/test_province_fallback.py
"""
import os
import sys
import tempfile
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")


def _seed_db():
    d = tempfile.mkdtemp(prefix="bms_pf_")
    os.environ["BMS_DATA_DIR"] = d
    import Sebastian_Customer_DB as db
    importlib.reload(db)
    db.init_schema()
    conn = db.get_connection()
    # 4 งานรั้วใน อ.โซ่พิสัย (ไม่ใช่บึงโขงหลง) — distinct winners 4
    seeds = [("หจก. A", 20), ("หจก. B", 25), ("หจก. C", 22), ("บ. D", 28)]
    for i, (w, disc) in enumerate(seeds):
        conn.execute(
            "INSERT INTO cgd_winners(project_id,province,dept,project_name,winner,win_price,"
            "discount_pct,fiscal_year,proc_type,district,subdistrict) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (f"W{i}", "บึงกาฬ", "อบต.โซ่พิสัย", f"ก่อสร้างรั้ว รร.ทดสอบ {i}", w,
             1000000, disc, "2568", "สอบราคา", "โซ่พิสัย", "xyz"))
    conn.commit()
    return db, conn


def test_province_fallback_when_amphoe_empty():
    import cgd_intel as ci
    db, conn = _seed_db()
    # อ.บึงโขงหลง ไม่มีรั้ว แต่จังหวัดมี 4 → ต้อง fallback
    ctx = ci._build_intel(conn, "บึงกาฬ", ["รั้ว"], "บึงโขงหลง", "บึงโขงหลง", 700000)
    assert ctx is not None and ctx.get("prediction"), "ต้องมีราคาคาด (fallback จังหวัด)"
    lines = "\n".join(ctx["lines"])
    assert "ข้ามพื้นที่" in lines, "ต้องมีป้ายเตือนข้ามพื้นที่"
    assert ctx.get("explain") and "ข้ามพื้นที่" in ctx["explain"]["scope"]["level"], "explain scope = cross-area"
    print("✅ province fallback + ป้ายเตือน (อำเภอว่าง → จังหวัด)")


def test_no_fallback_when_province_too_few():
    import cgd_intel as ci
    db, conn = _seed_db()
    # ลบให้เหลือ 2 distinct (< 3) → ต้องไม่ fallback (None)
    conn.execute("DELETE FROM cgd_winners WHERE project_id IN ('W2','W3')")
    conn.commit()
    ctx = ci._build_intel(conn, "บึงกาฬ", ["รั้ว"], "บึงโขงหลง", "บึงโขงหลง", 700000)
    assert ctx is None, "จังหวัด < 3 ราย → ไม่เดา (None)"
    print("✅ จังหวัด < 3 → ไม่ fallback (empty ดีกว่าเดา)")


if __name__ == "__main__":
    test_province_fallback_when_amphoe_empty()
    test_no_fallback_when_province_too_few()
    print("ALL PASS province_fallback")
