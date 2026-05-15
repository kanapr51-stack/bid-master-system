"""ตรวจ 2 jobs ที่ misclassified: 69059074818 + 69039325763"""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
TARGETS = ["69059074818", "69039325763"]

# 1. ดูใน all_jobs (source of truth)
ws = open_sheet(SPREADSHEET_ID, "all_jobs")
rows = ws.get_all_values()
hdrs = rows[0]
h_idx = {h: i for i, h in enumerate(hdrs)}

print("=" * 70)
print("STATE IN all_jobs (source of truth)")
print("=" * 70)
for r in rows[1:]:
    jid = r[0] if r else ""
    if jid in TARGETS:
        print(f"\n--- {jid} ---")
        for h, v in zip(hdrs, r):
            print(f"  {h}: {v[:90]!r}")

# 2. ดูว่าอยู่ใน sheet ไหน
print("\n" + "=" * 70)
print("LOCATION IN DERIVED SHEETS")
print("=" * 70)
for sheet in ["active_bidding", "pending_award", "awarded_jobs"]:
    ws2 = open_sheet(SPREADSHEET_ID, sheet)
    rows2 = ws2.get_all_values()
    h2 = rows2[0]
    for r in rows2[1:]:
        if r and r[0] in TARGETS:
            print(f"\n  ✓ {r[0]} → {sheet}")
            for k in ["deadline", "project_status", "days_remaining", "overdue_days", "winner_name", "award_date"]:
                if k in h2:
                    i = h2.index(k)
                    if i < len(r):
                        print(f"    {k}: {r[i]!r}")

# 3. ตรวจ winner_cache
import json
cache_path = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"
cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
print("\n" + "=" * 70)
print("WINNER CACHE")
print("=" * 70)
for jid in TARGETS:
    if jid in cache:
        print(f"  ✓ {jid}: {cache[jid]}")
    else:
        print(f"  ✗ {jid}: NOT in cache")
