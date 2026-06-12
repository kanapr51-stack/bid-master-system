"""test_resolve_amphoe.py — geo amphoe snap ข้ามอำเภอ ต้องถูกแก้ด้วย unique-tambon mapping.
bug 2026-06-12: งานรั้ว 69069138608 resolve = (ตำบลบึงโขงหลง, อ.เซกา) = คู่ไม่มีจริง → คาดราคาไม่ได้
รันด้วย: python scripts/test_resolve_amphoe.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

import cgd_intel as ci


def test_reconcile_corrects_cross_amphoe_geo():
    # ตำบล unique → 1 อำเภอ แต่ geo ให้คนละอำเภอ → ต้องแก้ตาม geo ของตำบล
    amphoe, corrected = ci._reconcile_amphoe("บึงโขงหลง", "เซกา", ["บึงโขงหลง"])
    assert amphoe == "บึงโขงหลง", f"ต้องแก้เป็นบึงโขงหลง ได้ {amphoe}"
    assert corrected is True
    print("✅ แก้ geo amphoe ข้ามอำเภอ (เซกา→บึงโขงหลง)")


def test_reconcile_keeps_geo_when_consistent():
    # geo สอดคล้องกับ unique-tambon → ไม่แตะ
    amphoe, corrected = ci._reconcile_amphoe("บึงโขงหลง", "บึงโขงหลง", ["บึงโขงหลง"])
    assert amphoe == "บึงโขงหลง" and corrected is False
    print("✅ geo สอดคล้อง → คงเดิม")


def test_reconcile_keeps_geo_when_tambon_ambiguous():
    # ตำบลอยู่ได้หลายอำเภอ (ไม่ unique) → เชื่อ geo (ตัดสินไม่ได้จากตำบลอย่างเดียว)
    amphoe, corrected = ci._reconcile_amphoe("นาดี", "เมือง", ["เมือง", "ศรีเชียงใหม่"])
    assert amphoe == "เมือง" and corrected is False
    print("✅ ตำบลกำกวม → เชื่อ geo")


def test_reconcile_no_tambon():
    amphoe, corrected = ci._reconcile_amphoe("", "เซกา", [])
    assert amphoe == "เซกา" and corrected is False
    print("✅ ไม่มีตำบล → คง geo")


if __name__ == "__main__":
    test_reconcile_corrects_cross_amphoe_geo()
    test_reconcile_keeps_geo_when_consistent()
    test_reconcile_keeps_geo_when_tambon_ambiguous()
    test_reconcile_no_tambon()
    print("ALL PASS resolve_amphoe")
