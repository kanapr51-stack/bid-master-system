"""test_cgd_intel.py — competitive intel (query cgd_winners → stats → LINE lines)."""
import sys, sqlite3; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci


def test_match_keywords():
    kws = ["ถนน", "คสล", "อาคาร"]
    assert ci.match_keywords("ก่อสร้างถนน คสล. บ้านแพง", keywords=kws) == ["ถนน", "คสล"]
    assert ci.match_keywords("จัดซื้อรถยนต์", keywords=kws) == []
    assert ci.match_keywords("", keywords=kws) == []
    # default โหลด config จริง — งานถนนต้องเจอ token
    assert "ถนน" in ci.match_keywords("ปรับปรุงถนนลาดยาง")
    print("✅ match_keywords")


if __name__ == "__main__":
    test_match_keywords()
    print("ALL PASS (Task 1)")
