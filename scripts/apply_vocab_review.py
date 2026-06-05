"""apply_vocab_review.py — อ่าน Sheet vocab_review → อัปเดต construction_vocab.json status
→ sync term approved เข้า work_type_keywords.json + matching_preferences.json (additive, backup ก่อน).
รัน: python scripts/apply_vocab_review.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from sheets_client import get_client

ROOT = Path(__file__).parent.parent
VOCAB = ROOT / "config" / "construction_vocab.json"
WT = ROOT / "config" / "work_type_keywords.json"
MP = ROOT / "config" / "matching_preferences.json"
BACKUP = ROOT / "backups"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"


def sync_into_configs(approved, rejected, wt, mp):
    """sync คลัง → config (idempotent, in-place). approved เติม, rejected ลบ.
    classifier: ตามหมวด (สากล). matcher: ทุกคำงานก่อสร้าง (company-agnostic, recall กว้าง —
    per-company category selection = อนาคต multi-tenant). rejected term มาจากคลัง (mining กรอง
    คำที่มีใน config แล้วออก) → ลบได้ปลอดภัย ไม่โดน keyword ดั้งเดิม."""
    for e in approved:
        term, cat = e["term"], e.get("category") or ""
        if cat and cat != "OTHER" and cat in wt["categories"]:
            if term not in wt["categories"][cat]:
                wt["categories"][cat].append(term)
        elif cat == "OTHER":
            if term not in wt["other_keywords"]:
                wt["other_keywords"].append(term)
        if e.get("guard"):
            wt.setdefault("guards", {})[term] = e["guard"]
        if term not in mp["keywords"]:
            mp["keywords"].append(term)

    # rejected → ลบออกจากทุกที่ (กรณีเคย approve แล้วเปลี่ยนใจ)
    for e in rejected:
        term = e["term"]
        for kws in wt["categories"].values():
            if term in kws:
                kws.remove(term)
        if term in wt["other_keywords"]:
            wt["other_keywords"].remove(term)
        wt.get("guards", {}).pop(term, None)
        if term in mp["keywords"]:
            mp["keywords"].remove(term)


def main():
    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    rows = sh.worksheet("vocab_review").get_all_values()[1:]  # ข้าม header
    # cols: term, freq, gap, ตัวอย่าง, approve, หมวด, guard
    review = {}
    for r in rows:
        if not r or not r[0].strip():
            continue
        approve = (r[4] or "").strip() if len(r) > 4 else ""
        review[r[0].strip()] = {
            "approve": approve in ("✓", "y", "yes", "Y", "ใช่", "1"),
            "reject": approve in ("✗", "x", "n", "no", "ไม่"),
            "category": (r[5].strip() if len(r) > 5 else ""),
            "guard": ((r[6].strip() if len(r) > 6 else "") or None),
        }

    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    approved, rejected = [], []
    for e in vocab["terms"]:
        rv = review.get(e["term"])
        if rv:
            if rv["approve"]:
                e["status"] = "approved"
                e["category"] = rv["category"] or e["category"]
                e["guard"] = rv["guard"]
            elif rv["reject"]:
                e["status"] = "rejected"
        if e["status"] == "approved":
            approved.append(e)
        elif e["status"] == "rejected":
            rejected.append(e)
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
    print(f"✅ approved {len(approved)} | rejected {len(rejected)} | "
          f"classifier kw {before[0]}→{after[0]} | matcher kw {before[1]}→{after[1]}")


if __name__ == "__main__":
    main()
