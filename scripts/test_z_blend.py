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


if __name__ == "__main__":
    test_credibility_z()
    test_blend_disc()
    test_blend_หนองเดิ่น_case()
    print("ALL PASS (z-blend)")
