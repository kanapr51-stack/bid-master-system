"""นับ row ใน all_jobs ที่ schema เลื่อน (project_status ขึ้นต้นด้วย 'province:' หรือ 'keyword:')"""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

ws = open_sheet("1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps", "all_jobs")
rows = ws.get_all_values()
headers = rows[0]
h_idx = {h: i for i, h in enumerate(headers)}
ps_i = h_idx["project_status"]
sk_i = h_idx["search_keyword"]
tu_i = h_idx["tor_url"]
prov_i = h_idx["province"]

misaligned = 0
ok_status_values = set()
empty_search_keyword = 0
tor_url_new = 0

for r in rows[1:]:
    ps = r[ps_i] if ps_i < len(r) else ""
    sk = r[sk_i] if sk_i < len(r) else ""
    tu = r[tu_i] if tu_i < len(r) else ""

    if ps.startswith("province:") or ps.startswith("keyword:"):
        misaligned += 1
    else:
        ok_status_values.add(ps)

    if not sk:
        empty_search_keyword += 1
    if tu == "new":
        tor_url_new += 1

print(f"Total rows: {len(rows) - 1}")
print(f"Misaligned (project_status starts with province:/keyword:): {misaligned}")
print(f"Empty search_keyword: {empty_search_keyword}")
print(f"tor_url == 'new': {tor_url_new}")
print()
print("Distinct OK project_status values:")
for v in sorted(ok_status_values):
    print(f"  {v!r}")
