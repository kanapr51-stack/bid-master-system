"""_vocab_prefill_category.py — เดา 'หมวด' ให้ candidate ในคลัง (ช่วยกัญจน์รีวิวเร็วขึ้น)
+ ลบ field bsc_relevant (company-agnostic) + re-push Sheet vocab_review (หมวด pre-filled).
เดาด้วย hint substring — กัญจน์ดู+กด approve/แก้ที่ไม่ตรง. รัน: python scripts/_vocab_prefill_category.py
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

# ตรวจตามลำดับ — หมวดเฉพาะ/เด่นก่อน, อาคาร (generic building) ท้ายสุด
HINTS = [
    ("ไฟฟ้า/ส่องสว่าง", ["ไฟฟ้า", "ส่องสว่าง", "แสงสว่าง", "เสาไฟ", "โคมไฟ", "ไฟกิ่ง",
                         "พลังงานแสงอาทิตย์", "โซล่า", "โซลาร์", "หม้อแปลง", "ระบบจำหน่าย", "มิเตอร์"]),
    ("สะพาน", ["สะพาน", "ท่อลอด", "ต่างระดับ", "ทางเชื่อม", "บ็อกซ์", "คัลเวิร์ต"]),
    ("OTHER", ["สนามกีฬา", "ลานกีฬา", "กีฬา", "สวนสาธารณะ", "ภูมิทัศน์", "ออกกำลังกาย", "หอกระจายข่าว",
               "เสียงตามสาย", "กล้อง", "cctv", "ขยะ", "สนามเด็กเล่น", "เครื่องเล่น", "ป้าย"]),
    ("แหล่งน้ำ/ชลประทาน", ["เขื่อน", "ตลิ่ง", "ฝาย", "ขุดลอก", "อ่างเก็บ", "อ่าง", "คลอง", "ประปา", "บาดาล",
                           "สูบน้ำ", "ดาดคอนกรีต", "พนัง", "ทำนบ", "ริมแม่น้ำ", "แม่น้ำ", "ลำห้วย", "แก้มลิง",
                           "ธนาคารน้ำ", "สระ", "กักเก็บ", "ชลประทาน", "หนองน้ำ", "ประตูระบาย", "ริมน้ำ"]),
    ("รางระบายน้ำ/ท่อ", ["รางระบาย", "ร่องระบาย", "ท่อระบาย", "วางท่อ", "ท่อเมน", "บ่อพัก", "ระบายน้ำ"]),
    ("ถนน", ["ถนน", "ลาดยาง", "ผิวจราจร", "แอสฟัลต์", "ลูกรัง", "ไหล่ทาง", "เสริมผิว", "ผิวทาง",
             "คันทาง", "หินคลุก", "ทางหลวง", "บูรณะทาง", "สายทาง"]),
    ("ดิน/ปรับพื้นที่", ["ถมดิน", "ปรับพื้นที่", "งานดิน", "ปรับเกลี่ย", "ดินถม", "ถมที่", "โคก", "แปลง",
                        "ที่ดิน", "ทฤษฎีใหม่", "รูปแบบ", "ปรับรูป", "หนองนา"]),
    ("อาคาร", ["อาคาร", "ห้อง", "เมรุ", "เผาศพ", "หอประชุม", "โรงพยาบาล", "ที่ว่าการ", "ที่ทำการ",
               "สำนักงาน", "โรงเรียน", "ศพด", "ศูนย์พัฒนาเด็ก", "รั้ว", "กำแพง", "ศาลา", "หลังคา", "ฝ้า",
               "ลานคอนกรีต", "ลาน", "โรง", "อเนกประสงค์", "ป้อม", "ส้วม", "บ้านพัก", "เรือนแถว", "มุข",
               "ต่อเติม", "ปูพื้น", "กระเบื้อง", "โดม", "บันได", "ทางลาด", "ผนัง", "หอ"]),
]


def guess_category(term):
    t = term.lower()
    for cat, hints in HINTS:
        if any(h.lower() in t for h in hints):
            return cat
    return ""


def main():
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    guessed = 0
    for e in vocab["terms"]:
        e.pop("bsc_relevant", None)  # company-agnostic
        if e["status"] == "candidate":  # re-guess ทุกครั้ง (เป็นแค่คำเดา, กัญจน์ยืนยัน)
            e["category"] = guess_category(e["term"])
            if e["category"]:
                guessed += 1
    VOCAB.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    cand = [e for e in vocab["terms"] if e["status"] == "candidate"]
    print(f"candidate {len(cand)} | เดาหมวดได้ {guessed} | ว่าง {sum(1 for e in cand if not e['category'])}")

    rows = [["term", "freq", "gap", "ตัวอย่าง", "approve(✓/✗)", "หมวด(เดาให้-แก้ได้)", "guard"]]
    for e in cand:
        rows.append([e["term"], e["freq"], e["gap"], e["examples"][0], "", e["category"], e["guard"] or ""])
    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet("vocab_review"); ws.clear()
    except Exception:
        ws = sh.add_worksheet(title="vocab_review", rows=len(rows) + 10, cols=7)
    ws.resize(rows=len(rows) + 2, cols=7)
    ws.update(values=rows, range_name="A1")
    ws.freeze(rows=1)
    print(f"📊 re-push Sheet 'vocab_review': {len(rows)-1} candidate (หมวด pre-filled)")


if __name__ == "__main__":
    main()
