"""test_follow_link_guard.py — build_follow_link ต้อง fail-loud เมื่อประกอบลิงก์ไม่ได้."""
import os, sys, tempfile
from pathlib import Path
os.environ.pop("BMS_FOLLOW_SECRET", None)         # ทำให้ make_token พลาด (ต้องไม่มี secret)
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()   # tmpdir ก่อน import (กัน touch prod runtime) — suite convention
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls   # noqa: E402


def test_strict_raises_when_link_broken():
    raised = False
    try:
        ls.build_follow_link("Uxx", "J1")   # strict default → ต้อง raise
    except RuntimeError:
        raised = True
    assert raised, "ประกอบลิงก์ไม่ได้ต้อง raise ไม่ใช่คืน '' เงียบ"
    print("✅ build_follow_link strict fail-loud")


def test_non_strict_returns_empty():
    out = ls.build_follow_link("Uxx", "J1", strict=False)
    assert out == "", out
    print("✅ non-strict คืน '' (พฤติกรรมเดิม)")


test_strict_raises_when_link_broken()
test_non_strict_returns_empty()
print("ALL PASS follow_link_guard")
