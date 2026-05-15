"""
create_calc_sheet.py — สร้าง Google Sheet ชีทคำนวนถนน คสล.

ใช้ครั้งเดียว: python scripts/create_calc_sheet.py
จะสร้าง sheet ชื่อ 'calc_road' ใน Spreadsheet เดียวกับ Bid Master
พ่อกรอก W, L, T, St, Sh, CJ, EJ แล้วเห็นปริมาณวัสดุทันที
"""

import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import get_client

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET_NAME = "calc_road"

# สีที่ใช้ (RGB 0-1)
COLOR_HEADER    = {"red": 0.18, "green": 0.18, "blue": 0.18}   # ดำเข้ม
COLOR_INPUT_BG  = {"red": 1.0,  "green": 0.95, "blue": 0.80}   # เหลืองอ่อน
COLOR_OUTPUT_BG = {"red": 0.85, "green": 0.93, "blue": 1.0}    # ฟ้าอ่อน
COLOR_TOTAL_BG  = {"red": 0.20, "green": 0.60, "blue": 0.30}   # เขียว
COLOR_WHITE     = {"red": 1.0,  "green": 1.0,  "blue": 1.0}
COLOR_LIGHT_GRAY = {"red": 0.95, "green": 0.95, "blue": 0.95}


def log(msg):
    print(f"  {msg}", flush=True)


def get_or_create_sheet(spreadsheet):
    """หา sheet ที่มีอยู่หรือสร้างใหม่"""
    try:
        ws = spreadsheet.worksheet(SHEET_NAME)
        log(f"sheet '{SHEET_NAME}' มีอยู่แล้ว — จะเขียนทับ")
        ws.clear()
        return ws
    except Exception:
        log(f"สร้าง sheet ใหม่: '{SHEET_NAME}'")
        ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=60, cols=10)
        return ws


def col_letter(n):
    """1→A, 2→B, ..."""
    return chr(ord('A') + n - 1)


def build_requests(sheet_id):
    """สร้าง batchUpdate requests สำหรับ format และ freeze"""
    requests = []

    def fmt(row0, col0, row1, col1, bold=False, bg=None, fg=None,
            halign=None, size=None, borders=None):
        """row/col are 0-indexed, end exclusive"""
        cell_fmt = {}
        txt_fmt = {}
        if bold:
            txt_fmt["bold"] = True
        if fg:
            txt_fmt["foregroundColor"] = fg
        if size:
            txt_fmt["fontSize"] = size
        if txt_fmt:
            cell_fmt["textFormat"] = txt_fmt
        if bg:
            cell_fmt["backgroundColor"] = bg
        if halign:
            cell_fmt["horizontalAlignment"] = halign

        r = {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row0,
                    "endRowIndex": row1,
                    "startColumnIndex": col0,
                    "endColumnIndex": col1,
                },
                "cell": {"userEnteredFormat": cell_fmt},
                "fields": "userEnteredFormat(" + ",".join(
                    (["textFormat"] if txt_fmt else []) +
                    (["backgroundColor"] if bg else []) +
                    (["horizontalAlignment"] if halign else [])
                ) + ")",
            }
        }
        requests.append(r)

    # Freeze row 1 (header)
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Column widths
    col_widths = [220, 80, 100, 80, 100, 120, 120]  # A–G
    for i, w in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })

    # Header row (row 1, index 0)
    fmt(0, 0, 1, 7, bold=True, bg=COLOR_HEADER, fg=COLOR_WHITE, halign="CENTER")

    # INPUT section header (row 3, index 2)
    fmt(2, 0, 3, 7, bold=True, bg={"red": 0.4, "green": 0.2, "blue": 0.0},
        fg=COLOR_WHITE, halign="LEFT")

    # Input cells background (rows 4-10, col B = index 1)
    fmt(3, 1, 10, 2, bg=COLOR_INPUT_BG)

    # OUTPUT section header (row 12, index 11)
    fmt(11, 0, 12, 7, bold=True, bg={"red": 0.1, "green": 0.3, "blue": 0.6},
        fg=COLOR_WHITE, halign="LEFT")

    # Output area (rows 13-27, index 12-26)
    fmt(12, 0, 27, 7, bg=COLOR_OUTPUT_BG)

    # สีสลับแถว output
    for i in range(12, 27, 2):
        fmt(i, 0, i + 1, 7, bg={"red": 0.90, "green": 0.95, "blue": 1.0})

    # Total row (row 28, index 27) — เขียวเข้ม
    fmt(27, 0, 28, 7, bold=True, bg=COLOR_TOTAL_BG, fg=COLOR_WHITE)

    # NOTE row (row 30, index 29)
    fmt(29, 0, 31, 7, bg=COLOR_LIGHT_GRAY)

    return requests


def main():
    print("=" * 60)
    print("create_calc_sheet.py — สร้างชีทคำนวนถนน คสล.")
    print("=" * 60)

    gc = get_client()
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    ws = get_or_create_sheet(spreadsheet)
    sheet_id = ws.id

    log("เขียนข้อมูลและสูตร...")

    # ================================================================
    # DATA: เขียนทีละก้อนด้วย batch_update values
    # ================================================================

    # Row 1: Header
    # Row 2: blank
    # Row 3: "INPUT" section
    # Rows 4-10: ตัวแปร input
    # Row 11: blank
    # Row 12: "OUTPUT" section
    # Rows 13-27: ผลคำนวณ
    # Row 28: สรุป (คอนกรีตรวม ลบ.ม.)
    # Row 29: blank
    # Row 30-31: หมายเหตุ

    data = [
        # Row 1 - Header
        ["ชีทคำนวนถนน คสล. — BSC ทรัพย์คอนกรีต / หจก.ยศประทานฯ",
         "", "ค่ากรอก", "", "ผลลัพธ์", "หน่วย", "หมายเหตุ"],

        # Row 2 - blank
        [""] * 7,

        # Row 3 - INPUT header
        [">> กรอกข้อมูลงาน (เซลล์สีเหลือง)", "", "", "", "", "", ""],

        # Row 4: W
        ["W — กว้างถนน (ม.)", "", 4.0, "",
         "=C4", "ม.", "ค่าปกติ: 4.00"],

        # Row 5: L
        ["L — ยาวถนน (ม.)", "", "", "",
         "=C5", "ม.", ""],

        # Row 6: T
        ["T — หนาคอนกรีต (ม.)", "", 0.15, "",
         "=C6", "ม.", "ค่าปกติ: 0.15"],

        # Row 7: St
        ["St — หนาทรายรองพื้น (ม.)", "", 0.05, "",
         "=C7", "ม.", "ค่าปกติ: 0.05"],

        # Row 8: Sh
        ["Sh — กว้างไหล่ทาง ข้างละ (ม.)", "", 0.50, "",
         "=C8", "ม.", "ค่าปกติ: 0.50"],

        # Row 9: CJ
        ["CJ — ระยะ Contraction Joint (ม.)", "", 10, "",
         "=C9", "ม.", "ค่าปกติ: 10"],

        # Row 10: EJ
        ["EJ — ระยะ Expansion Joint (ม.)", "", 100, "",
         "=C10", "ม.", "ค่าปกติ: 100"],

        # Row 11: blank
        [""] * 7,

        # Row 12: OUTPUT header
        [">> ปริมาณวัสดุ (คำนวณอัตโนมัติ)", "", "", "", "", "", ""],

        # Row 13: งานปรับเกลี่ย
        ["งานปรับเกลี่ยแต่งคันทาง",
         "", "", "",
         "=IF(C5=\"\",\"\",($C$4+$C$8*2)*$C$5)",
         "ตร.ม.", "=(W+Sh×2)×L"],

        # Row 14: ทรายรองพื้น
        ["ทรายรองพื้น",
         "", "", "",
         "=IF(C5=\"\",\"\",$C$4*$C$5*$C$7)",
         "ลบ.ม.", "=W×L×St"],

        # Row 15: คอนกรีต
        ["คอนกรีต คสล.",
         "", "", "",
         "=IF(C5=\"\",\"\",$C$4*$C$5*$C$6)",
         "ลบ.ม.", "=W×L×T"],

        # Row 16: Wire Mesh
        ["Wire Mesh",
         "", "", "",
         "=IF(C5=\"\",\"\",$C$4*$C$5)",
         "ตร.ม.", "=W×L"],

        # Row 17: จำนวน EJ
        ["จำนวน Expansion Joint (EJ)",
         "", "", "",
         "=IF(C5=\"\",\"\",MAX(0,FLOOR($C$5/$C$10,1)-1))",
         "ช่วง", "FLOOR(L/EJ,1)-1"],

        # Row 18: จำนวน CJ
        ["จำนวน Contraction Joint (CJ)",
         "", "", "",
         "=IF(C5=\"\",\"\",MAX(0,FLOOR($C$5/$C$9,1)-1-E17))",
         "ช่วง", "FLOOR(L/CJ,1)-1-จำนวนEJ"],

        # Row 19: Dowel Bar 15mm (CJ)
        ["Dowel Bar ∅15mm (Contraction Joint)",
         "", "", "",
         "=IF(C5=\"\",\"\",FLOOR($C$4/0.5,1)*0.5*E18*1.390)",
         "กก.", "@ spacing 0.50ม., 1.390 กก./ม."],

        # Row 20: Dowel Bar 19mm (EJ)
        ["Dowel Bar ∅19mm (Expansion Joint)",
         "", "", "",
         "=IF(C5=\"\",\"\",FLOOR($C$4/0.5,1)*0.5*E17*2.230)",
         "กก.", "@ spacing 0.50ม., 2.230 กก./ม."],

        # Row 21: Metal Cap
        ["Metal Cap (ชุด)",
         "", "", "",
         "=IF(C5=\"\",\"\",FLOOR($C$4/0.5,1)*E17)",
         "ชุด", "= เหล็กต่อ EJ × จำนวน EJ"],

        # Row 22: Joint Filler EJ
        ["Joint Filler (Expansion Joint)",
         "", "", "",
         "=IF(C5=\"\",\"\",$C$4*($C$6-0.025)*E17)",
         "ตร.ม.", "W×(T-0.025)×จำนวนEJ"],

        # Row 23: Joint Sealer EJ
        ["Joint Sealer EJ",
         "", "", "",
         "=IF(C5=\"\",\"\",$C$4*0.025*0.025*1000*E17)",
         "ลิตร", "W×0.025×0.025×1000×จำนวนEJ"],

        # Row 24: Joint Sealer CJ
        ["Joint Sealer CJ",
         "", "", "",
         "=IF(C5=\"\",\"\",$C$4*0.01*0.0375*1000*E18)",
         "ลิตร", "W×0.010×0.0375×1000×จำนวนCJ"],

        # Row 25: ไหล่ทาง
        ["งานไหล่ทาง",
         "", "", "",
         "=IF(C5=\"\",\"\",($C$6+$C$7)*$C$8*$C$5*2)",
         "ลบ.ม.", "(T+St)×Sh×L×2"],

        # Row 26: พื้นที่ผิว
        ["พื้นที่ผิวคอนกรีต",
         "", "", "",
         "=IF(C5=\"\",\"\",$C$4*$C$5)",
         "ตร.ม.", "W×L"],

        # Row 27: blank separator
        [""] * 7,

        # Row 28: สรุปคอนกรีต
        ["สรุป: ปริมาณคอนกรีตรวม",
         "", "", "",
         "=IF(C5=\"\",\"\",E15)",
         "ลบ.ม.", "ใช้สั่งรถโม่"],

        # Row 29: blank
        [""] * 7,

        # Row 30: หมายเหตุ
        ["หมายเหตุ:", "", "", "", "", "", ""],
        ["กรอกเฉพาะ L (แถว 5) — ตัวแปรอื่นมีค่า default แล้ว แก้ได้ตามต้องการ",
         "", "", "", "", "", ""],
    ]

    # เขียนทั้งหมดด้วย batch (range A1:G31)
    cell_range = f"A1:G{len(data)}"
    ws.update(data, cell_range, value_input_option="USER_ENTERED")
    log(f"เขียนข้อมูล {len(data)} แถวแล้ว")

    # ================================================================
    # FORMAT: batch requests
    # ================================================================
    log("จัดรูปแบบ...")
    time.sleep(1)

    requests = build_requests(sheet_id)
    spreadsheet.batch_update({"requests": requests})
    log("จัดรูปแบบแล้ว")

    # ================================================================
    # FREEZE + COLUMN A bold
    # ================================================================
    # ทำให้ column A (labels) เป็น bold ทั้งหมด
    spreadsheet.batch_update({"requests": [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 3,
                    "endRowIndex": 28,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        }
    ]})

    print()
    print("=" * 60)
    print(f"สร้าง '{SHEET_NAME}' เสร็จแล้ว!")
    print()
    print("วิธีใช้:")
    print("  1. เปิด Google Sheet → แท็บ 'calc_road'")
    print("  2. กรอก L (ความยาว) ที่เซลล์ C5")
    print("  3. แก้ W/T/St/Sh/CJ/EJ ถ้าต่างจากค่า default")
    print("  4. ดูผลปริมาณวัสดุที่คอลัมน์ E ทันที")
    print()
    print(f"URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")
    print("=" * 60)


if __name__ == "__main__":
    main()
