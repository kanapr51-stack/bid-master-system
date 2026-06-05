"""_vocab_firstpass.py — first-pass: mark ✓ ใน Sheet ให้คำชัวร์ ~20 (demo sync จริง).
push Sheet (approve=✓ + หมวดถูก สำหรับ SURE, prefilled หมวด blank approve สำหรับที่เหลือ) →
จากนั้นรัน apply_vocab_review.py ต่อ. รัน: python scripts/_vocab_firstpass.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from sheets_client import get_client

ROOT = Path(__file__).parent.parent
VOCAB = ROOT / "config" / "construction_vocab.json"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"

SURE = {
    "เขื่อน": "แหล่งน้ำ/ชลประทาน", "เขื่อนป้องกัน": "แหล่งน้ำ/ชลประทาน",
    "ตลิ่ง": "แหล่งน้ำ/ชลประทาน", "ป้องกันตลิ่ง": "แหล่งน้ำ/ชลประทาน",
    "ตลิ่งริมแม่น้ำ": "แหล่งน้ำ/ชลประทาน", "สูบน้ำ": "แหล่งน้ำ/ชลประทาน",
    "เมรุ": "อาคาร", "เผาศพ": "อาคาร", "หอประชุม": "อาคาร", "โรงพยาบาล": "อาคาร",
    "ที่ว่าการอำเภอ": "อาคาร", "ที่ทำการ": "อาคาร", "ลาน": "อาคาร", "ก่อสร้างลาน": "อาคาร",
    "บ่อขยะ": "OTHER", "ขยะมูลฝอย": "OTHER",
    "พลังงานแสงอาทิตย์": "ไฟฟ้า/ส่องสว่าง", "ระบบจำหน่าย": "ไฟฟ้า/ส่องสว่าง",
    "ทฤษฎีใหม่": "ดิน/ปรับพื้นที่",
}


def main():
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    present = {e["term"] for e in vocab["terms"] if e["status"] == "candidate"}
    marked = [t for t in SURE if t in present]
    # set หมวดให้ถูกในคลัง
    for e in vocab["terms"]:
        if e["term"] in SURE:
            e["category"] = SURE[e["term"]]
    VOCAB.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = [["term", "freq", "gap", "ตัวอย่าง", "approve(✓/✗)", "หมวด(เดาให้-แก้ได้)", "guard"]]
    for e in vocab["terms"]:
        if e["status"] != "candidate":
            continue
        ap = "✓" if e["term"] in SURE else ""
        rows.append([e["term"], e["freq"], e["gap"], e["examples"][0], ap, e["category"], e["guard"] or ""])
    gc = get_client()
    ws = gc.open_by_key(SHEET_ID).worksheet("vocab_review")
    ws.clear()
    ws.resize(rows=len(rows) + 2, cols=7)
    ws.update(values=rows, range_name="A1")
    ws.freeze(rows=1)
    print(f"✓ mark {len(marked)} คำชัวร์ ใน Sheet: {marked}")
    print("→ รันต่อ: python scripts/apply_vocab_review.py")


if __name__ == "__main__":
    main()
