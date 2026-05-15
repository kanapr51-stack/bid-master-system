"""ลบ sheet 'TOR Analysis' จาก Google Spreadsheet"""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet
import gspread

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"

gc = gspread.service_account(filename=str(Path(__file__).parent.parent / "credentials" / "service_account.json"))
spreadsheet = gc.open_by_key(SPREADSHEET_ID)

print("Sheets ทั้งหมด:")
for ws in spreadsheet.worksheets():
    print(f"  - {ws.title} (id={ws.id})")

target = None
for ws in spreadsheet.worksheets():
    if "tor" in ws.title.lower() or "analysis" in ws.title.lower():
        target = ws
        print(f"\nพบ: '{ws.title}' → จะลบ")

if target:
    spreadsheet.del_worksheet(target)
    print(f"ลบ '{target.title}' เรียบร้อย")
else:
    print("\nไม่พบ sheet ที่ชื่อ TOR Analysis")
