"""test_recency.py — L3 recency weighting (half-life 1 ปี). TDD วิจัย 2026-06-13.
weight = 0.5^(อายุ/half_life) · ถ่วง percentile ตามความสด → ข้อมูลเก่าจาง."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci


def test_recency_weight():
    assert ci.recency_weight(2569, 2569) == 1.0           # ปีเดียวกัน = เต็ม
    assert ci.recency_weight(2568, 2569) == 0.5           # 1 ปี = ครึ่ง (half-life 1)
    assert abs(ci.recency_weight(2567, 2569) - 0.25) < 1e-9
    assert ci.recency_weight(2562, 2569) < 0.01           # 7 ปี ≈ ศูนย์ (ฆ่าข้อมูลเก่า)
    assert ci.recency_weight(None, 2569) == 1.0           # ไม่มีปี → neutral
    assert ci.recency_weight(2570, 2569) == 1.0           # อนาคต → clamp เต็ม
    print("✅ recency_weight (half-life 1)")


def test_wpct():
    assert ci._wpct([10, 20, 30], [1, 1, 1], 50) == 20    # น้ำหนักเท่า = median ปกติ
    assert ci._wpct([10, 40], [1, 0.01], 50) == 10        # 40 น้ำหนักน้อย → median เอน 10
    assert ci._wpct([], [], 50) is None
    print("✅ _wpct (weighted percentile)")


def test_scope_block_recency():
    """scope ที่มีข้อมูลเก่า-ดุ (2562, 40%) + สด-อนุรักษ์ (2568, 25%) → median เอนของสด (~25)."""
    rows = [{"discount_pct": 40.0, "winner": "หจก.เก่า", "fiscal_year": "2562", "subdistrict": "x", "district": "y"},
            {"discount_pct": 25.0, "winner": "หจก.สด", "fiscal_year": "2568", "subdistrict": "x", "district": "y"}]
    _l, p25, p75, n, _t, _tm, med = ci._scope_block(rows, "🏘 ทดสอบ", now_year=2569)
    assert med is not None and med <= 30, f"ของเก่าควรจาง median เอน 25 ไม่ใช่ 32.5; ได้ {med}"
    print(f"✅ _scope_block recency (median={med} เอนของสด)")


if __name__ == "__main__":
    test_recency_weight()
    test_wpct()
    test_scope_block_recency()
    print("ALL PASS (recency)")
