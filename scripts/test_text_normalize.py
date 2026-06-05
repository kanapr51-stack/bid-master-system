"""test_text_normalize.py — standalone assert runner."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from text_normalize import normalize_thai  # noqa: E402

CASES = [
    # (input, expected)
    ("ธนาคารนํ้าใต้ดิน", "ธนาคารน้ำใต้ดิน"),          # นํ้า(U+0E4D 0E49 0E32) → น้ำ
    ("เก็บกักนํ้าไว้ใช้", "เก็บกักน้ำไว้ใช้"),
    ("ก่อสร้างถนน ค.ส.ล.", "ก่อสร้างถนน คสล"),
    ("ถนน ค.ส.ล สายหลัก", "ถนน คสล สายหลัก"),
    ("ถนนคสล.", "ถนนคสล"),
    ("ราง  ระบาย   น้ำ", "ราง ระบาย น้ำ"),            # ยุบเว้นวรรค
    ("  ก่อสร้าง  ", "ก่อสร้าง"),                      # strip
    ("ก่อสร้างรางระบายน้ำ", "ก่อสร้างรางระบายน้ำ"),    # น้ำ ถูกอยู่แล้ว ไม่เปลี่ยน
    ("", ""),
]


def main():
    fails = []
    for inp, exp in CASES:
        got = normalize_thai(inp)
        if got != exp:
            fails.append(f"  {inp!r} → {got!r} != {exp!r}  ({[hex(ord(c)) for c in got]})")
    if normalize_thai(None) != "":
        fails.append("  None ไม่คืน ''")
    if fails:
        print("❌ FAIL:\n" + "\n".join(fails)); sys.exit(1)
    print(f"✅ PASS {len(CASES)} cases")


if __name__ == "__main__":
    main()
