"""สร้าง Google Sheet ผลประมูลย้อนหลัง (นครพนม/บึงกาฬ) + write 156 + share."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from sheets_client import get_client

hits = json.load(open("data/_winner_history_156.json", encoding="utf-8"))
gc = get_client()

MAIN_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
TAB = "ผลประมูลย้อนหลัง"
sh = gc.open_by_key(MAIN_ID)
print("opened main:", sh.title)

# tab ใหม่ (ถ้ามีแล้ว → clear + reuse)
try:
    ws = sh.add_worksheet(title=TAB, rows=len(hits) + 5, cols=9)
    print("created tab:", TAB)
except Exception:
    ws = sh.worksheet(TAB)
    ws.clear()
    print("reuse tab:", TAB)

header = ["ลำดับ", "จังหวัด", "ชื่องาน", "หน่วยงาน", "ผู้ชนะ",
          "ราคาชนะ (บาท)", "ส่วนลด %", "วันประกาศผล", "Project ID"]
rows = []
for i, h in enumerate(hits, 1):
    rows.append([i, h["province"], h["project_name"], h["dept"], h["winner_name"],
                 h["winner_price"], h["discount_pct"], h["award_date"], h["project_id"]])
data = [header] + rows

ws.resize(rows=len(data) + 2, cols=len(header))
ws.update(values=data, range_name="A1")

# format: header bold + freeze + autofilter
ws.format("A1:I1", {"textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5},
                    "horizontalAlignment": "CENTER"})
ws.format("A1:I1", {"textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}})
ws.freeze(rows=1)
try:
    ws.format("F2:F%d" % len(data), {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}})
except Exception as e:
    print("fmt price warn:", e)

# กัญจน์เป็นเจ้าของ spreadsheet หลักอยู่แล้ว — ไม่ต้อง share
total = sum(h["winner_price"] for h in hits)
print("rows written:", len(rows))
print("total value:", f"{total:,}")
print("URL: https://docs.google.com/spreadsheets/d/%s/edit#gid=%s" % (sh.id, ws.id))
