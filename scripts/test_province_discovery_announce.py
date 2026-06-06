"""test_province_discovery_announce.py — discovery รับ announce_type param (B0=1) + default D0=2."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Province_Discovery as d  # noqa: E402

cap = {}
def fake_get(token, params, path=""):
    cap["params"] = dict(params); cap["path"] = path
    if path.endswith("sumProjectMoneyAndCount"):
        return {"data": {"recordsTotal": 7, "totalPages": 1}}
    return {"data": {"data": [{"projectId": "X1", "announceType": "B0", "stepId": "U03",
                              "projectName": "จ้างก่อสร้างถนน", "projectStatus": "A"}]}}
d._get = fake_get
d._rate_limit_tick = lambda: None  # กัน sleep ใน test

fails = []

# B0: count ต้องส่ง announceType=1
rt, pages = d.count_d0("tok", "480000", "2569", announce_type="1")
if cap["params"].get("announceType") != "1": fails.append(f"count B0 announceType={cap['params'].get('announceType')}")
if rt != 7: fails.append(f"count B0 rt={rt}")

# default ยังเป็น D0=2 (backward compat)
d.count_d0("tok", "480000", "2569")
if cap["params"].get("announceType") != "2": fails.append(f"count default announceType={cap['params'].get('announceType')}")

# fetch_page ส่ง announceType=1
items = d.fetch_page("tok", "480000", "2569", 1, announce_type="1")
if cap["params"].get("announceType") != "1": fails.append(f"fetch_page B0 announceType={cap['params'].get('announceType')}")
if not items or items[0].get("announceType") != "B0": fails.append("fetch_page B0 ไม่คืน item")

if fails:
    print("❌ FAIL:"); [print("  " + f) for f in fails]; sys.exit(1)
print("✅ PASS discovery announce_type param (B0=1, default D0=2)")
