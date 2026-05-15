"""
create_new_sheets.py — สร้าง sheet ใหม่สำหรับ pipeline ที่อัปเดต

    pending_award  — งาน e-bidding หมดเขตยื่นซองแล้ว รอประกาศผู้ชนะ
    tor_review     — งาน e-bidding ที่ยังอยู่ในช่วงรับฟังคำวิจารณ์

ใช้ครั้งเดียว: python scripts/create_new_sheets.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import get_client

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"

PENDING_AWARD_HEADERS = [
    "job_id", "title", "department", "province", "district", "subdistrict",
    "procurement_type", "budget",
    "วันที่ประกาศ", "วันยื่นซอง", "เกินกำหนด (วัน)",
    "tor_url", "status", "project_status", "quantity_note",
]

TOR_REVIEW_HEADERS = [
    "job_id", "title", "department", "province", "district", "subdistrict",
    "procurement_type", "budget",
    "วันที่ประกาศ", "สิ้นสุดรับฟังคำวิจารณ์", "เหลือเวลา (วัน)",
    "tor_url", "status", "project_status", "quantity_note",
]

COLOR_HEADER_PENDING  = {"red": 0.55, "green": 0.27, "blue": 0.07}   # น้ำตาล (รอผลประมูล)
COLOR_HEADER_TOR      = {"red": 0.06, "green": 0.35, "blue": 0.55}   # น้ำเงิน (รับฟังคำวิจารณ์)
COLOR_WHITE           = {"red": 1.0,  "green": 1.0,  "blue": 1.0}
COLOR_TEXT_WHITE      = {"red": 1.0,  "green": 1.0,  "blue": 1.0}


def log(msg: str):
    print(f"  {msg}", flush=True)


def _sheet_exists(spreadsheet, name: str) -> bool:
    return any(ws.title == name for ws in spreadsheet.worksheets())


def _apply_header_style(spreadsheet, sheet_id: int, color: dict, n_cols: int):
    """ทำ header row: พื้นหลังสี + ตัวอักษรขาว + bold + freeze"""
    requests = [
        # พื้นหลัง + ตัวอักษร header
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0, "endRowIndex": 1,
                    "startColumnIndex": 0, "endColumnIndex": n_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": color,
                        "textFormat": {
                            "foregroundColor": COLOR_TEXT_WHITE,
                            "bold": True,
                            "fontSize": 10,
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "CLIP",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
            }
        },
        # Freeze row 1
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # ความกว้าง col A (job_id)
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0, "endIndex": 1,
                },
                "properties": {"pixelSize": 120},
                "fields": "pixelSize",
            }
        },
        # ความกว้าง col B (title)
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 1, "endIndex": 2,
                },
                "properties": {"pixelSize": 340},
                "fields": "pixelSize",
            }
        },
        # ความกว้าง col C (department)
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 2, "endIndex": 3,
                },
                "properties": {"pixelSize": 200},
                "fields": "pixelSize",
            }
        },
    ]
    spreadsheet.batch_update({"requests": requests})


def create_sheet(spreadsheet, name: str, headers: list, color: dict):
    if _sheet_exists(spreadsheet, name):
        log(f"'{name}' มีอยู่แล้ว — ข้าม (ไม่ลบข้อมูลเดิม)")
        return

    ws = spreadsheet.add_worksheet(title=name, rows=500, cols=len(headers))
    ws.update([headers], "A1")
    log(f"'{name}' สร้างสำเร็จ — {len(headers)} คอลัมน์")

    _apply_header_style(spreadsheet, ws.id, color, len(headers))
    log(f"'{name}' จัดรูปแบบ header เรียบร้อย")


def main():
    print("=" * 50, flush=True)
    print("สร้าง sheets ใหม่สำหรับ Bid Master Pipeline", flush=True)
    print("=" * 50, flush=True)

    gc = get_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    log(f"เชื่อมต่อ: '{spreadsheet.title}'")
    print()

    print("📋 สร้าง 'pending_award' (รอประกาศผู้ชนะ)...", flush=True)
    create_sheet(spreadsheet, "pending_award", PENDING_AWARD_HEADERS, COLOR_HEADER_PENDING)
    print()

    print("📋 สร้าง 'tor_review' (รับฟังคำวิจารณ์)...", flush=True)
    create_sheet(spreadsheet, "tor_review", TOR_REVIEW_HEADERS, COLOR_HEADER_TOR)
    print()

    print("✅ เสร็จสิ้น — พร้อมรัน pipeline", flush=True)


if __name__ == "__main__":
    main()
