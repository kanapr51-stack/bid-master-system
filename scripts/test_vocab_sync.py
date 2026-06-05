"""test_vocab_sync.py — sync ต้อง additive (approved) + remove (rejected) + idempotent + คง key เดิม."""
import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from apply_vocab_review import sync_into_configs  # noqa: E402


def base():
    wt = {"version": "v1",
          "categories": {"ถนน": ["ถนน"], "ดิน/ปรับพื้นที่": [], "อาคาร": ["เก่าทิ้ง", "ห้องน้ำ"]},
          "other_keywords": ["ป้าย", "เก่าอื่น"], "guards": {}, "priority": ["ถนน"]}
    mp = {"keywords": ["รางระบาย", "เก่าทิ้ง"], "target_tambons": ["บ้านแพง"], "negative_keywords": []}
    return wt, mp


def main():
    approved = [
        {"term": "ผนังกันดิน", "category": "ดิน/ปรับพื้นที่", "guard": None, "status": "approved"},
        {"term": "สนามกีฬา", "category": "OTHER", "guard": None, "status": "approved"},
        {"term": "ถนน", "category": "ถนน", "guard": None, "status": "approved"},  # มีแล้ว
    ]
    rejected = [{"term": "เก่าทิ้ง"}, {"term": "เก่าอื่น"}]  # เคยอยู่ใน config → ต้องถูกลบ

    wt2, mp2 = base()
    sync_into_configs(approved, rejected, wt2, mp2)
    fails = []
    # additive
    if "ผนังกันดิน" not in wt2["categories"]["ดิน/ปรับพื้นที่"]:
        fails.append("ดิน ไม่ได้ ผนังกันดิน")
    if "สนามกีฬา" not in wt2["other_keywords"]:
        fails.append("OTHER ไม่ได้ สนามกีฬา")
    if "ผนังกันดิน" not in mp2["keywords"] or "สนามกีฬา" not in mp2["keywords"]:
        fails.append("matcher ไม่ได้ทุก term approved")
    # remove (rejected)
    if "เก่าทิ้ง" in wt2["categories"]["อาคาร"]:
        fails.append("rejected เก่าทิ้ง ยังอยู่ใน classifier")
    if "เก่าอื่น" in wt2["other_keywords"]:
        fails.append("rejected เก่าอื่น ยังอยู่ใน other_keywords")
    if "เก่าทิ้ง" in mp2["keywords"]:
        fails.append("rejected เก่าทิ้ง ยังอยู่ใน matcher")
    # ไม่ทำลายของเดิม
    if "ห้องน้ำ" not in wt2["categories"]["อาคาร"] or "ถนน" not in wt2["categories"]["ถนน"]:
        fails.append("ลบของเดิมผิด")
    if wt2["categories"]["ถนน"].count("ถนน") != 1 or mp2["keywords"].count("ถนน") != 1:
        fails.append("ซ้ำ (ไม่ idempotent)")
    if mp2["target_tambons"] != ["บ้านแพง"]:
        fails.append("target_tambons เปลี่ยน (ทำลาย key เดิม)")
    # idempotent: รันซ้ำผลเท่าเดิม
    wt3, mp3 = copy.deepcopy(wt2), copy.deepcopy(mp2)
    sync_into_configs(approved, rejected, wt3, mp3)
    if wt3 != wt2 or mp3 != mp2:
        fails.append("รันซ้ำผลเปลี่ยน (ไม่ idempotent)")
    if fails:
        print("❌ FAIL:\n" + "\n".join("  " + f for f in fails)); sys.exit(1)
    print("✅ PASS sync additive + remove(rejected) + idempotent + คง key เดิม")


if __name__ == "__main__":
    main()
