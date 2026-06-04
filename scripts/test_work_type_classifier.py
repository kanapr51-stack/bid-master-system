"""test_work_type_classifier.py — unit test (standalone assert runner, ไม่มี pytest ในเครื่อง)
รัน: python scripts/test_work_type_classifier.py  → exit 0 ถ้าผ่านหมด, exit 1 ถ้า fail
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from work_type_classifier import classify_work_type, WORK_TYPE_VERSION  # noqa: E402

CASES = [
    # (title, expected_primary, expected_secondary_set)
    ("ก่อสร้างถนน คสล. พร้อมรางระบายน้ำ", "ถนน", {"รางระบายน้ำ/ท่อ"}),
    ("ก่อสร้างรางระบายน้ำ รูปตัวยู", "รางระบายน้ำ/ท่อ", set()),
    ("ก่อสร้างอาคารเรียน 3 ชั้น", "อาคาร", set()),
    ("ปรับปรุงผิวจราจรลาดยางแอสฟัลต์", "ถนน", set()),
    ("ก่อสร้างสนามกีฬาอเนกประสงค์", "OTHER", set()),
    ("จัดซื้อวัสดุสำนักงาน", "UNKNOWN", set()),
    ("ก่อสร้างสะพาน คสล. ข้ามคลอง", "สะพาน", {"แหล่งน้ำ/ชลประทาน"}),
    ("ติดตั้งไฟฟ้าส่องสว่างพลังงานแสงอาทิตย์", "ไฟฟ้า/ส่องสว่าง", set()),
    ("ก่อสร้างถนนพร้อมไฟฟ้าส่องสว่าง", "ถนน", {"ไฟฟ้า/ส่องสว่าง"}),
    ("จ้างเหมาจัดทำตารางเมตรวัดพื้นที่", "UNKNOWN", set()),  # guard: ตาราง ไม่ใช่ ราง
    ("มอบรางวัลประจำปี", "UNKNOWN", set()),                  # guard: รางวัล ไม่ใช่ ราง
]


def main():
    fails = []
    for title, exp_primary, exp_secondary in CASES:
        r = classify_work_type(title)
        if r["primary"] != exp_primary:
            fails.append(f"  PRIMARY  {title!r}: got {r['primary']!r} != {exp_primary!r}")
        if set(r["secondary"]) != exp_secondary:
            fails.append(f"  SECONDARY {title!r}: got {set(r['secondary'])} != {exp_secondary}")
        if r["version"] != WORK_TYPE_VERSION:
            fails.append(f"  VERSION  {title!r}: got {r['version']!r}")
        if r["all"] and r["all"][0] != r["primary"]:
            fails.append(f"  ALL-ORDER {title!r}: all[0]={r['all'][0]!r} != primary")

    if fails:
        print(f"❌ FAIL {len(fails)} assertions:")
        print("\n".join(fails))
        sys.exit(1)
    print(f"✅ PASS {len(CASES)} cases")


if __name__ == "__main__":
    main()
