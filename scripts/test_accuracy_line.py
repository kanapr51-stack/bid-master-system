"""test_accuracy_line.py — C: ฐานความแม่นยำ = ค่ากลาง (ปกติ) + framing win/lose.
requirement กัญจน์ 2026-06-11: ราคาที่คาด ≤ ราคาชนะ → ยื่นแล้วชนะ → 'ความแม่นยำ';
คาด > ราคาชนะ → ยื่นแล้วแพ้ → 'ความคลาดเคลื่อนจากราคาชนะ'. prediction เก่าไม่มี median → fallback กรอบบน."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as snd


def test_win_uses_accuracy():
    # คาด (ค่ากลาง) 740,000 ≤ ชนะจริง 750,000 → ยื่นราคาคาดก็ชนะ → ความแม่นยำ
    cmp = {"pred_med": 740000, "upper": 800000, "error_pct": -6.0, "held": True}
    line = snd._accuracy_line(cmp, 750000)
    assert "ความแม่นยำ" in line and "ราคาที่คาดชนะได้" in line, line
    assert "98.7%" in line, line   # 100 - |740000-750000|/750000*100 = 98.67
    print("✅ win → ความแม่นยำ")


def test_lose_uses_deviation():
    # คาด (ค่ากลาง) 110,000 > ชนะจริง 100,000 → ยื่นแล้วแพ้ → ความคลาดเคลื่อนจากราคาชนะ
    cmp = {"pred_med": 110000, "upper": 120000, "error_pct": -8.0, "held": True}
    line = snd._accuracy_line(cmp, 100000)
    assert "ความคลาดเคลื่อนจากราคาชนะ" in line and "ราคาที่คาดจะแพ้" in line, line
    assert "10.0%" in line, line   # (110000-100000)/100000*100
    print("✅ lose → ความคลาดเคลื่อนจากราคาชนะ")


def test_fallback_no_median():
    # prediction เก่าไม่มี pred_med → เทียบกรอบบน (เดิม)
    cmp = {"upper": 730000, "error_pct": 1.1, "held": False}
    line = snd._accuracy_line(cmp, 738000)
    assert "ความแม่นยำ" in line and "คาดกรอบบน" in line, line
    print("✅ fallback (ไม่มี median) → เทียบกรอบบน")


def test_winner_detailed_median():
    analyzed = [{"name": "หจก.X", "price": 750000, "discount": 26.0, "is_winner": True,
                 "hist": {"scope": "ตำบล", "n": 2, "median": 25.0}, "trend": "", "tag": "warned"}]
    cmp = {"pred_med": 740000, "upper": 800000, "error_pct": -6.0, "held": True}
    txt = snd.format_winner_detailed("ถนน", "หจก.X", 750000, 1000000, analyzed, cmp,
                                     {"verified": 5, "in_range": 4}, 28.0, "P1")
    assert "ความแม่นยำ" in txt and "ราคาที่คาดชนะได้" in txt and "สะสมอยู่ในกรอบ 4/5" in txt, txt
    print("✅ format_winner_detailed (median win + สะสม)")


if __name__ == "__main__":
    test_win_uses_accuracy()
    test_lose_uses_deviation()
    test_fallback_no_median()
    test_winner_detailed_median()
    print("\n✅ ALL test_accuracy_line PASS")
