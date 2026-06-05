"""_vocab_approve_batch3.py — batch 3 (data-driven จาก UNKNOWN sample จริง, ไม่ใช่ gap list).
ต่างจาก batch ก่อน: เติม term ใหม่เข้าคลังถ้ายังไม่มี (คลัง = source of truth) แล้ว sync config.
รัน: python scripts/_vocab_approve_batch3.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from apply_vocab_review import sync_into_configs

ROOT = Path(__file__).parent.parent
VOCAB = ROOT / "config" / "construction_vocab.json"
WT = ROOT / "config" / "work_type_keywords.json"
MP = ROOT / "config" / "matching_preferences.json"
BACKUP = ROOT / "backups"

# คำชัวร์จาก UNKNOWN sample (data/work_type_unknown_sample.txt) — เลือกเฉพาะที่ map หมวดชัด + เลี่ยงคำโลภ
BATCH = {
    # อาคาร (สิ่งปลูกสร้าง/สิ่งอำนวยความสะดวก)
    "เสาธง": "อาคาร", "ที่จอดรถ": "อาคาร", "ตลาดสด": "อาคาร",
    "ลานเอนกประสงค์": "อาคาร", "โดม": "อาคาร",
    "ผนังกันดิน": "อาคาร",
    "ทางลาดสำหรับ": "อาคาร", "ทางลาดผู้พิการ": "อาคาร", "ทางลาดคนพิการ": "อาคาร",
    # แหล่งน้ำ/ชลประทาน
    "ทางน้ำล้น": "แหล่งน้ำ/ชลประทาน", "คันพนัง": "แหล่งน้ำ/ชลประทาน",
    "หอถัง": "แหล่งน้ำ/ชลประทาน", "ถังเก็บน้ำ": "แหล่งน้ำ/ชลประทาน",
    # รางระบายน้ำ/ท่อ
    "ทางระบายน้ำ": "รางระบายน้ำ/ท่อ",
    # สะพาน (box culvert)
    "บล็อกคอนเวิร์ส": "สะพาน",
    # ถนน (เส้นทางจักรยาน) — ใช้ "ทางจักรยาน" เลี่ยงชน "จักรยานยนต์"
    "ทางจักรยาน": "ถนน",
    # ไฟฟ้า/ส่องสว่าง
    "ระบบจำหน่าย": "ไฟฟ้า/ส่องสว่าง", "ฟีดเดอร์": "ไฟฟ้า/ส่องสว่าง", "โซล่าเซลล์": "ไฟฟ้า/ส่องสว่าง",
    # OTHER (สนามกีฬา)
    "สนามเด็กเล่น": "OTHER", "สนามฟุตบอล": "OTHER",
    "สนามวอลเลย์บอล": "OTHER", "สนามบาสเกตบอล": "OTHER",
}


def main():
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    present = {e["term"] for e in vocab["terms"]}
    added_new = []
    for term, cat in BATCH.items():
        if term in present:
            for e in vocab["terms"]:
                if e["term"] == term:
                    e["category"] = cat
                    e["status"] = "approved"
        else:
            vocab["terms"].append({
                "term": term, "category": cat, "status": "approved",
                "freq": None, "source": "unknown_sample_n84",
            })
            added_new.append(term)
    approved = [e for e in vocab["terms"] if e["status"] == "approved"]
    rejected = [e for e in vocab["terms"] if e["status"] == "rejected"]
    VOCAB.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")

    BACKUP.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(WT, BACKUP / f"work_type_keywords_{ts}.json")
    shutil.copy(MP, BACKUP / f"matching_preferences_{ts}.json")
    wt = json.loads(WT.read_text(encoding="utf-8"))
    mp = json.loads(MP.read_text(encoding="utf-8"))
    before = (sum(len(v) for v in wt["categories"].values()) + len(wt["other_keywords"]), len(mp["keywords"]))
    sync_into_configs(approved, rejected, wt, mp)
    after = (sum(len(v) for v in wt["categories"].values()) + len(wt["other_keywords"]), len(mp["keywords"]))
    WT.write_text(json.dumps(wt, ensure_ascii=False, indent=2), encoding="utf-8")
    MP.write_text(json.dumps(mp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"batch3: {len(BATCH)} คำ ({len(added_new)} ใหม่เข้าคลัง) | approved รวม {len(approved)} | "
          f"classifier kw {before[0]}→{after[0]} | matcher kw {before[1]}→{after[1]}")
    print("ใหม่เข้าคลัง:", ", ".join(added_new))


if __name__ == "__main__":
    main()
