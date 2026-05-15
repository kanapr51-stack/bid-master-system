"""Debug ทำไม row A1476 ใน all_jobs ไม่ผ่าน filter"""
import sys
from pathlib import Path
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from Sebastian_Classifier import (
    is_in_target_province, is_construction_job,
    parse_thai_date, ALL_JOBS_HEADERS,
    CONSTRUCTION_INCLUDE, CONSTRUCTION_EXCLUDE,
    TARGET_PROVINCES,
)
from Sebastian_Scraper import DEPT_PROVINCE_MAP

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"

ws = open_sheet(SPREADSHEET_ID, "all_jobs")
all_values = ws.get_all_values()
headers = all_values[0]
print("Headers:", headers)
print()

# row 1476 = index 1475 (sheet is 1-indexed, headers = row 1)
target_idx = 1475
if target_idx >= len(all_values):
    print(f"sheet has only {len(all_values)} rows")
    sys.exit(1)

row = all_values[target_idx]
print(f"=== Row {target_idx + 1} ===")
for h, v in zip(headers, row):
    print(f"  {h}: {v!r}")
print()

# Build dict
h_idx = {h: i for i, h in enumerate(headers)}
def g(key):
    i = h_idx.get(key, -1)
    return row[i] if 0 <= i < len(row) else ""

row_dict = {h: g(h) for h in ALL_JOBS_HEADERS if h in h_idx}

print("=== Filter Trace ===")
print(f"job_id:           {g('job_id')}")
print(f"procurement_type: {g('procurement_type')!r}  → {'PASS' if g('procurement_type') == 'e-bidding' else 'FAIL (not e-bidding)'}")

# Province check trace
prov = str(g("province")).strip()
title = str(g("title"))
print(f"\nprovince field:   {prov!r}")
print(f"title:            {title[:100]}...")

if any(p in prov for p in TARGET_PROVINCES):
    print("  ✅ Case A: province ตรงกับ TARGET")
elif prov:
    print(f"  ⚠️  Case C: province มีค่า({prov}) แต่ไม่ใช่ TARGET → ต้องดู title")
    found = False
    for p in TARGET_PROVINCES:
        if f"จ.{p}" in title or f"จังหวัด{p}" in title:
            print(f"     ✅ title มี 'จ.{p}' หรือ 'จังหวัด{p}'")
            found = True
            break
    if not found:
        print(f"     ❌ title ไม่มี 'จ.X' หรือ 'จังหวัดX' ใดๆ → DROP")
else:
    print("  Case B: province ว่าง → fallback")
    text = title + " " + str(g("department"))
    if any(p in text for p in TARGET_PROVINCES):
        print(f"     ✅ title/dept มีคำ TARGET")
    else:
        print(f"     check search_keyword:")
        kw = str(g("search_keyword")).strip()
        print(f"       search_keyword: {kw!r}")
        if kw:
            matched = False
            for map_key, map_prov in DEPT_PROVINCE_MAP.items():
                if map_key in kw and map_prov in TARGET_PROVINCES:
                    print(f"     ✅ matched: '{map_key}' → {map_prov}")
                    matched = True
                    break
            if not matched:
                print(f"     ❌ ไม่ match DEPT_PROVINCE_MAP → DROP")

result = is_in_target_province(row_dict)
print(f"\n→ is_in_target_province() returns: {result}")

# Construction check
print(f"\n=== Construction filter ===")
matched_inc = [k for k in CONSTRUCTION_INCLUDE if k.lower() in title.lower()]
matched_exc = [k for k in CONSTRUCTION_EXCLUDE if k.lower() in title.lower()]
print(f"  matched INCLUDE: {matched_inc}")
print(f"  matched EXCLUDE: {matched_exc}")
print(f"  → is_construction_job: {is_construction_job(title)}")

# Project status + deadline
print(f"\n=== Status / Deadline ===")
print(f"  project_status: {g('project_status')!r}")
print(f"  deadline:       {g('deadline')!r}")
dl = parse_thai_date(g("deadline"))
print(f"  parsed:         {dl}")
print(f"  today:          {date.today()}")
if dl:
    if dl >= date.today():
        print(f"  → would go to active_bidding ({(dl - date.today()).days} days left)")
    else:
        print(f"  → would go to pending_award ({(date.today() - dl).days} days overdue)")
