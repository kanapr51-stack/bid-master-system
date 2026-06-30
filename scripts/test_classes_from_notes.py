"""test_classes_from_notes.py — รวม keyword/งบ ราย user จาก notes.classes[]."""
import os, sys, json, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import bms_api

# union keywords (+defaultKeywords) unique, budget_min=min(>0), budget_max=max(>0)
notes = json.dumps({"classes": [
    {"keywords": ["คอนกรีต", "ท่อ"], "defaultKeywords": ["ถนน"], "budgetMinBaht": 1000000, "budgetMaxBaht": 20000000},
    {"keywords": ["ท่อ", "ราง"], "budgetMinBaht": 500000, "budgetMaxBaht": 50000000},
]})
r = bms_api._classes_from_notes(notes)
assert r["keywords"] == ["คอนกรีต", "ท่อ", "ถนน", "ราง"], r["keywords"]
assert r["budget_min"] == 500000, r["budget_min"]
assert r["budget_max"] == 50000000, r["budget_max"]

# notes ว่าง / พังต้องไม่ระเบิด
assert bms_api._classes_from_notes("") == {"keywords": [], "budget_min": 0, "budget_max": 0}
assert bms_api._classes_from_notes("not json") == {"keywords": [], "budget_min": 0, "budget_max": 0}

# ไม่มี budget → 0
r2 = bms_api._classes_from_notes(json.dumps({"classes": [{"keywords": ["ถนน"]}]}))
assert r2["budget_min"] == 0 and r2["budget_max"] == 0 and r2["keywords"] == ["ถนน"], r2

print("PASS test_classes_from_notes")
