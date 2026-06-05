"""_vocab_approve_batch.py — approve candidate ชุดที่มั่นใจ (ตรงเข้าคลัง + sync config).
ใช้ sync_into_configs เดิม (approved เติม, rejected ลบ). validate ต่อหลังรัน.
รัน: python scripts/_vocab_approve_batch.py
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

BATCH = {
    # อาคาร
    "ห้อง": "อาคาร", "สำนักงาน": "อาคาร", "ซ่อมแซมห้อง": "อาคาร", "ปรับปรุงห้อง": "อาคาร",
    "เมรุเผาศพ": "อาคาร", "ก่อสร้างเมรุ": "อาคาร", "โรงเรือน": "อาคาร", "ก่อสร้างโรงเรือน": "อาคาร",
    "ห้องเรียน": "อาคาร", "ห้องปฏิบัติการ": "อาคาร", "โรงฆ่าสัตว์": "อาคาร", "ลานจอดรถ": "อาคาร",
    "ลานคสล": "อาคาร", "ลานอเนกประสงค์": "อาคาร", "สำนักงานเทศบาลตำบล": "อาคาร",
    # แหล่งน้ำ/ชลประทาน
    "ริมแม่น้ำ": "แหล่งน้ำ/ชลประทาน", "ริมแม่น้ำโขง": "แหล่งน้ำ/ชลประทาน", "ซ่อมแซมเขื่อน": "แหล่งน้ำ/ชลประทาน",
    "ก่อสร้างเขื่อน": "แหล่งน้ำ/ชลประทาน", "ระบบสูบน้ำ": "แหล่งน้ำ/ชลประทาน", "ลำห้วย": "แหล่งน้ำ/ชลประทาน",
    # ดิน/ปรับพื้นที่
    "ที่ดิน": "ดิน/ปรับพื้นที่", "แปลง": "ดิน/ปรับพื้นที่",
    # OTHER
    "ขยะ": "OTHER",
}


def main():
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    present = {e["term"] for e in vocab["terms"]}
    applied = [t for t in BATCH if t in present]
    for e in vocab["terms"]:
        if e["term"] in BATCH:
            e["category"] = BATCH[e["term"]]
            e["status"] = "approved"
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
    print(f"approve batch {len(applied)}/{len(BATCH)} | approved รวม {len(approved)} | "
          f"classifier kw {before[0]}→{after[0]} | matcher kw {before[1]}→{after[1]}")


if __name__ == "__main__":
    main()
