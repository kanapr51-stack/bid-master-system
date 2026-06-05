"""test_vocab_sync.py — sync ต้อง additive + idempotent + ไม่ทำลาย key เดิม."""
import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from apply_vocab_review import sync_into_configs  # noqa: E402


def main():
    wt = {"version": "v1", "categories": {"ถนน": ["ถนน"], "ดิน/ปรับพื้นที่": []},
          "other_keywords": ["ป้าย"], "guards": {}, "priority": ["ถนน"]}
    mp = {"keywords": ["รางระบาย"], "target_tambons": ["บ้านแพง"], "negative_keywords": []}
    approved = [
        {"term": "ผนังกันดิน", "category": "ดิน/ปรับพื้นที่", "guard": None, "status": "approved"},
        {"term": "สนามกีฬา", "category": "OTHER", "guard": None, "status": "approved"},
        {"term": "ถนน", "category": "ถนน", "guard": None, "status": "approved"},  # มีแล้ว
    ]
    wt2, mp2 = copy.deepcopy(wt), copy.deepcopy(mp)
    sync_into_configs(approved, wt2, mp2)
    fails = []
    if "ผนังกันดิน" not in wt2["categories"]["ดิน/ปรับพื้นที่"]:
        fails.append("ดิน ไม่ได้ ผนังกันดิน")
    if "สนามกีฬา" not in wt2["other_keywords"]:
        fails.append("OTHER ไม่ได้ สนามกีฬา")
    # matcher = ทุก term approved (company-agnostic, recall กว้าง)
    if "ผนังกันดิน" not in mp2["keywords"] or "สนามกีฬา" not in mp2["keywords"]:
        fails.append("matcher ไม่ได้ทุก term approved")
    if wt2["categories"]["ถนน"].count("ถนน") != 1:
        fails.append("ถนน ซ้ำ (ไม่ idempotent)")
    if mp2["keywords"].count("ถนน") != 1:
        fails.append("matcher ถนน ซ้ำ (ไม่ idempotent)")
    if mp2["target_tambons"] != ["บ้านแพง"]:
        fails.append("target_tambons เปลี่ยน (ทำลาย key เดิม)")
    # idempotent: รันซ้ำผลเท่าเดิม
    wt3, mp3 = copy.deepcopy(wt2), copy.deepcopy(mp2)
    sync_into_configs(approved, wt3, mp3)
    if wt3 != wt2 or mp3 != mp2:
        fails.append("รันซ้ำผลเปลี่ยน (ไม่ idempotent)")
    if fails:
        print("❌ FAIL:\n" + "\n".join("  " + f for f in fails)); sys.exit(1)
    print("✅ PASS sync additive + idempotent + คง key เดิม")


if __name__ == "__main__":
    main()
