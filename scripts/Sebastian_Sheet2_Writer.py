"""
Sebastian_Sheet2_Writer.py — Combined JSON → Sheet 2 (job_specs)

อ่าน combined.json จาก download folders → บันทึกลง job_specs sheet
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET2_NAME    = "job_specs"
SHEET1_NAME    = "raw_jobs_bidding"

# ---- Column layout (ภาษาไทย อ่านเข้าใจง่าย) ----
HEADERS = [
    "รหัสงาน", "ชื่องาน", "หน่วยงาน", "จังหวัด", "อำเภอ",
    "วันที่ประกาศ", "วันสิ้นสุด", "วิธีจัดซื้อ", "ลิงก์ TOR", "ประเภทงาน",
    "กว้าง (ม.)", "ยาว (ม.)", "หนา (ม.)", "ไหล่ทาง (ม.)",
    "เกรดคอนกรีต",
    "Dowel เส้นผ่า (มม.)", "Dowel ยาว (มม.)", "Dowel ระยะห่าง (มม.)",
    "Tie Bar เส้นผ่า (มม.)", "Tie Bar ยาว (มม.)",
    "ตาข่ายลวด",
    "รอยต่อ CJ (จุด)", "รอยต่อ EJ (จุด)",
    "ระยะเวลาก่อสร้าง (วัน)", "ระยะเวลาส่งมอบ (วัน)", "ระยะเวลาประกันงาน (วัน)",
    "การทดสอบที่กำหนด", "เอกสารส่งมอบ", "เงื่อนไขพิเศษ",
    "งบประมาณ (บาท)", "ราคา BOQ รวม (บาท)", "ต้นทุนตรง (บาท)", "Overhead (%)", "กำไร (%)",
    "ความแม่นยำ TOR", "มี ปร.4", "มี ปร.5", "มี TOR",
    "สรุป BOQ",
    "สถานะ",
]

_CONF_MAP = {"high": "สูง", "medium": "กลาง", "low": "ต่ำ"}


# ================================================================
# SHEET OPERATIONS
# ================================================================

def _get_ws():
    return open_sheet(SPREADSHEET_ID, SHEET2_NAME)


def _get_bidding_ids() -> set:
    """ดึง job_id ทั้งหมดจาก raw_jobs_bidding เพื่อ validate"""
    ws = open_sheet(SPREADSHEET_ID, SHEET1_NAME)
    return set(str(v) for v in ws.col_values(1)[1:] if v)


def ensure_headers(ws):
    """สร้างหรืออัปเดต header row ให้ตรงกับ HEADERS ปัจจุบัน"""
    first_row = ws.row_values(1)
    if not first_row or first_row[0] != HEADERS[0] or first_row != HEADERS:
        ws.update("A1", [HEADERS])
        print(f"  อัปเดต header row ({len(HEADERS)} คอลัมน์)", flush=True)


def _col_letter(n: int) -> str:
    if n <= 26:
        return chr(64 + n)
    return chr(64 + n // 26) + chr(64 + n % 26)


def combined_to_row(d: dict) -> list:
    """แปลง combined dict → row list ตาม HEADERS"""
    conf = _CONF_MAP.get(str(d.get("tor_confidence", "")).lower(), d.get("tor_confidence", ""))
    return [
        d.get("job_id", ""),
        d.get("title", ""),
        d.get("department", ""),
        d.get("province", ""),
        d.get("district", ""),
        d.get("publish_date", ""),
        d.get("deadline", ""),
        d.get("procurement_type", ""),
        f'=HYPERLINK("{d["tor_url"]}","ดู TOR")' if d.get("tor_url") and d["tor_url"].startswith("http") else "",
        d.get("tier", "Tier 2"),
        d.get("W", ""),
        d.get("L", ""),
        d.get("T", ""),
        d.get("St", ""),
        d.get("concrete_grade", ""),
        d.get("dowel_dia_mm", ""),
        d.get("dowel_len_mm", ""),
        d.get("dowel_spacing_mm", ""),
        d.get("tie_bar_dia_mm", ""),
        d.get("tie_bar_len_mm", ""),
        d.get("wire_mesh", ""),
        d.get("joint_CJ", ""),
        d.get("joint_EJ", ""),
        d.get("construction_duration_days", ""),
        d.get("delivery_period_days", ""),
        d.get("warranty_period_days", ""),
        d.get("required_tests", ""),
        d.get("required_delivery_documents", ""),
        d.get("special_conditions", ""),
        d.get("budget", ""),
        d.get("boq_total", ""),
        d.get("direct_cost", ""),
        d.get("overhead_pct", ""),
        d.get("profit_pct", ""),
        conf,
        "มี" if d.get("has_pr4") else "ไม่มี",
        "มี" if d.get("has_pr5") else "ไม่มี",
        "มี" if d.get("has_tor") else "ไม่มี",
        d.get("boq_summary", "")[:500],
        d.get("status", "วิเคราะห์แล้ว"),
    ]


def write_to_sheet2(combined_list: list[dict], upsert: bool = True) -> int:
    """
    บันทึก combined JSON list → Sheet 2
    เช็คกับ raw_jobs_bidding ก่อน — ถ้า job ไม่อยู่ใน bidding ให้ข้ามไป
    """
    if not combined_list:
        print("ไม่มีข้อมูลที่จะบันทึก", flush=True)
        return 0

    bidding_ids = _get_bidding_ids()
    ws = _get_ws()
    ensure_headers(ws)

    all_ids = ws.col_values(1)
    id_to_row = {v: i + 1 for i, v in enumerate(all_ids) if v and i > 0}

    new_rows = []
    updated = 0
    skipped = 0

    for d in combined_list:
        job_id = str(d.get("job_id", ""))
        if not job_id:
            continue

        if job_id not in bidding_ids:
            print(f"  ข้าม {job_id} — ไม่อยู่ใน raw_jobs_bidding", flush=True)
            skipped += 1
            continue

        row_data = combined_to_row(d)
        col_range = f"A{{r}}:{_col_letter(len(HEADERS))}{{r}}"

        if job_id in id_to_row and upsert:
            row_num = id_to_row[job_id]
            ws.update(col_range.format(r=row_num), [row_data], value_input_option="USER_ENTERED")
            updated += 1
        elif job_id not in id_to_row:
            new_rows.append(row_data)
            id_to_row[job_id] = 0

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"เพิ่ม {len(new_rows)} งานลง {SHEET2_NAME}", flush=True)
    if updated:
        print(f"อัปเดต {updated} งานใน {SHEET2_NAME}", flush=True)
    if skipped:
        print(f"ข้าม {skipped} งาน (ไม่อยู่ใน raw_jobs_bidding)", flush=True)
    if not new_rows and not updated:
        print("ไม่มีการเปลี่ยนแปลง", flush=True)

    return len(new_rows) + updated


def clear_sheet2():
    """ล้างข้อมูลทั้งหมดใน job_specs (เก็บแค่ header)"""
    ws = _get_ws()
    row_count = ws.row_count
    if row_count > 1:
        ws.delete_rows(2, row_count)
    ensure_headers(ws)
    print(f"ล้าง {SHEET2_NAME} เรียบร้อย", flush=True)


# ================================================================
# READ FROM DOWNLOAD DIR
# ================================================================

def load_combined_from_dir(download_dir: str | Path) -> list[dict]:
    """อ่าน combined.json จาก download directory — เฉพาะ job ที่อยู่ใน raw_jobs_bidding"""
    download_dir = Path(download_dir)
    bidding_ids = _get_bidding_ids()
    results = []
    for combined_path in download_dir.rglob("combined.json"):
        try:
            data = json.loads(combined_path.read_text(encoding="utf-8"))
            job_id = str(data.get("job_id", ""))
            if job_id and job_id not in bidding_ids:
                print(f"  ข้าม {job_id} (ไม่อยู่ใน raw_jobs_bidding)", flush=True)
                continue
            results.append(data)
        except Exception as e:
            print(f"  อ่าน {combined_path} ไม่ได้: {e}", flush=True)
    return results


# ================================================================
# READ FROM SHEET2
# ================================================================

def read_sheet2_jobs(status_filter: str = None) -> list[dict]:
    """อ่าน Sheet 2 กลับมาเป็น list[dict]"""
    ws = _get_ws()
    rows = ws.get_all_records()
    if status_filter:
        rows = [r for r in rows if str(r.get("สถานะ", "")).strip() == status_filter]
    return rows


def update_sheet2_status(job_id: str, new_status: str):
    """อัปเดต สถานะ ของงานใน Sheet 2"""
    ws = _get_ws()
    cell = ws.find(job_id, in_column=1)
    if cell:
        header_row = ws.row_values(1)
        try:
            status_col = header_row.index("สถานะ") + 1
            ws.update_cell(cell.row, status_col, new_status)
        except ValueError:
            pass


# ================================================================
# MAIN
# ================================================================

def main():
    DOWNLOAD_DIR = Path(__file__).parent.parent / "downloads"

    print("=" * 60, flush=True)
    print("Sebastian Sheet2 Writer — เริ่มต้น", flush=True)
    print("=" * 60, flush=True)

    combined_list = load_combined_from_dir(DOWNLOAD_DIR)
    print(f"พบ combined.json: {len(combined_list)} งาน", flush=True)

    added = write_to_sheet2(combined_list)
    print(f"\nสรุป: เพิ่ม/อัปเดต {added} งานลง Sheet 2", flush=True)


if __name__ == "__main__":
    main()
