"""test_z_blend.py — Bühlmann credibility Z-blend (ตำบล↔อำเภอ). TDD สำหรับสูตรวิจัย 2026-06-13.
Z = n/(n+3) · blend = Z·ตำบล + (1−Z)·อำเภอ."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci


def test_credibility_z():
    # n=0 → ไม่เชื่อตำบลเลย · n=3 → ครึ่ง (k=3) · n มากๆ → ~เชื่อตำบลเต็ม
    assert ci.credibility_z(0) == 0.0
    assert ci.credibility_z(3) == 0.5
    assert ci.credibility_z(9) == 0.75
    assert abs(ci.credibility_z(2) - 0.4) < 1e-9
    assert ci.credibility_z(1000) > 0.99
    print("✅ credibility_z (k=3)")


def test_blend_disc():
    # ตำบล 40, อำเภอ 32, n=2 → Z=0.4 → 0.4*40+0.6*32 = 35.2
    assert abs(ci.blend_disc(40, 32, 2) - 35.2) < 1e-9
    # n=0 → อำเภอล้วน
    assert ci.blend_disc(40, 32, 0) == 32
    # ฝั่งใดเป็น None → ใช้อีกฝั่ง (graceful)
    assert ci.blend_disc(None, 32, 5) == 32
    assert ci.blend_disc(40, None, 5) == 40
    assert ci.blend_disc(None, None, 5) is None
    print("✅ blend_disc (credibility blend)")


def test_blend_หนองเดิ่น_case():
    """closed-loop: ตำบล 40% (n=2) + อำเภอ 32% → blend 35.2% ใกล้จริง 33.7% กว่า 40% เดิม."""
    blended = ci.blend_disc(40.0, 32.0, 2)
    assert 34 <= blended <= 36, blended            # ขยับจาก 40 เข้าหาจริง 33.7
    assert abs(blended - 33.7) < abs(40 - 33.7)    # ใกล้จริงกว่าเดิมแน่นอน
    print("✅ blend หนองเดิ่น (40→35.2 ใกล้จริง 33.7 กว่าเดิม)")


def _blend_conn():
    """fixture: ตำบลX บาง (2 งาน ลด ~40) + อำเภอมีตำบลอื่นลดต่ำกว่า (~30) → คาดควร blend (~34)."""
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    rows = [  # (pid, sub, winner, disc)
        ("T1", "ตX", "หจก.ก", 38.0), ("T2", "ตX", "หจก.ข", 42.0),               # ตำบลX: 2 งาน med 40
        ("A1", "ตY", "หจก.ค", 28.0), ("A2", "ตY", "หจก.ง", 30.0),
        ("A3", "ตZ", "หจก.จ", 30.0), ("A4", "ตZ", "หจก.ฉ", 32.0),               # อำเภออื่น med ~30
    ]
    for pid, sub, win, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", f"ก่อสร้างถนน คสล. ต.{sub}", win, 500000, disc, "2568", EB, "อ.ทดสอบ", sub))
    c.commit(); return c


def test_build_intel_blends_thin_tambon():
    """ตำบลบาง (2 งาน med 40) + อำเภอ (med ~30) → คาดราคาต้อง blend (ไม่ใช่ตำบลล้วน 40)
    + ป้ายโชว์น้ำหนักตำบล. Z=2/(2+3)=0.4 → blended med ~34."""
    c = _blend_conn()
    ctx = ci._build_intel(c, "นครพนม", ["ถนน"], "ตX", "อ.ทดสอบ", budget=1000000)
    assert ctx and ctx["prediction"], ctx
    med = ctx["prediction"].get("area_disc_med")
    assert med is not None and 31 <= med <= 39, f"ควร blend (ไม่ใช่ 40 ตำบลล้วน/30 อำเภอล้วน) ได้ {med}"
    L = "\n".join(ctx["lines"])
    assert "น้ำหนักตำบล" in L, f"ป้ายต้องโชว์น้ำหนัก: {L}"
    print(f"✅ _build_intel blend ตำบลบาง (med={med:.1f} อยู่ระหว่าง 30↔40) + ป้ายน้ำหนัก")


if __name__ == "__main__":
    test_credibility_z()
    test_blend_disc()
    test_blend_หนองเดิ่น_case()
    test_build_intel_blends_thin_tambon()
    print("ALL PASS (z-blend)")
