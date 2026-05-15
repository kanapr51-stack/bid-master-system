"""
Backfill raw_jobs columns — แก้ row เก่าที่ data shift ผิด column

ปัญหา: row เก่าเขียนด้วย schema 14 cols [..., tor_url, status, quantity_note, seq_no]
        schema ปัจจุบัน 15 cols [..., tor_deadline, tor_url, status, project_status, quantity_note]
        → data ใน col 11-15 shifted ผิด, Classifier อ่าน project_status='' → ไม่ classify

วิธีตรวจ: ถ้า col 12 (header=tor_url) = "new" และ col 13 (header=status) เริ่มด้วย "province:"
         แสดงว่า row นี้เขียนด้วย OLD schema

วิธีแก้: ย้าย data
  col 12 (=new) → col 13 (status)
  col 13 (=province:... | flow) → col 15 (quantity_note)
  + คำนวณ project_status จาก flow → col 14
  + ล้าง col 12 (tor_url ว่าง)
"""

import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET_NAME     = "raw_jobs"

FLOW_STATUS_MAP = {
    "หนังสือเชิญชวน/ประกาศเชิญชวน":                        "กำลังประมูล",
    "จัดทำสัญญา/บริหารสัญญา":                              "ประมูลแล้ว",
    "อนุมัติสั่งซื้อสั่งจ้างและประกาศผู้ชนะการเสนอราคา":   "ประมูลแล้ว",
    "ยกเลิกโครงการ":                                        "ยกเลิก",
    "จัดทำ TOR":                                             "กำลังเตรียม",
}


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main(dry_run: bool = False):
    log("=" * 60)
    log(f"Backfill raw_jobs columns (dry_run={dry_run})")
    log("=" * 60)

    ws = open_sheet(SPREADSHEET_ID, SHEET_NAME)
    all_vals = ws.get_all_values()
    log(f"Total rows: {len(all_vals)}")

    headers = all_vals[0]
    log(f"Headers ({len(headers)} cols): col12={headers[11]!r}, col13={headers[12]!r}, col14={headers[13]!r}, col15={headers[14] if len(headers)>14 else 'N/A'!r}")

    # ตรวจหา misaligned rows
    misaligned = []
    for row_idx, row in enumerate(all_vals[1:], start=2):  # row 2 onward (1-indexed for sheets)
        if len(row) < 14:
            continue
        col12 = row[11].strip() if len(row) > 11 else ""
        col13 = row[12].strip() if len(row) > 12 else ""
        col14 = row[13].strip() if len(row) > 13 else ""

        # criteria: col12="new" + col13 starts with "province:" with " | "
        if col12 == "new" and col13.startswith("province:") and " | " in col13:
            misaligned.append((row_idx, row))

    log(f"\nพบ misaligned rows: {len(misaligned)} แถว")
    if not misaligned:
        log("ไม่มีอะไรต้องแก้")
        return

    # เตรียม update batch
    updates = []
    sample_logged = 0
    for row_idx, row in misaligned:
        old_col13 = row[12]  # "province:X | flowName"
        # extract flowName
        try:
            flow_name = old_col13.split(" | ", 1)[1].strip()
        except IndexError:
            flow_name = ""
        project_status = FLOW_STATUS_MAP.get(flow_name, flow_name or "")

        # NEW row layout: เก็บ col 1-11 เดิม, แก้ col 12-15
        # col 12 (tor_url) = ""
        # col 13 (status) = "new" (เดิมอยู่ col 12)
        # col 14 (project_status) = project_status (mapped)
        # col 15 (quantity_note) = "province:X | flowName" (เดิมอยู่ col 13)
        new_col_12 = ""
        new_col_13 = "new"
        new_col_14 = project_status
        new_col_15 = old_col13

        # batch update: เขียน L:O (col 12-15) ของ row นี้
        range_name = f"L{row_idx}:O{row_idx}"
        updates.append({
            "range": range_name,
            "values": [[new_col_12, new_col_13, new_col_14, new_col_15]],
        })

        if sample_logged < 3:
            log(f"  row {row_idx} (job_id={row[0]}): flow={flow_name!r} → project_status={project_status!r}")
            sample_logged += 1

    log(f"\nเตรียม batch update: {len(updates)} แถว")

    if dry_run:
        log("DRY RUN — ไม่เขียนจริง")
        return

    # split into chunks (gspread batch limit)
    CHUNK = 500
    for i in range(0, len(updates), CHUNK):
        chunk = updates[i:i+CHUNK]
        ws.batch_update(chunk, value_input_option="USER_ENTERED")
        log(f"  เขียน chunk {i//CHUNK + 1}/{(len(updates)+CHUNK-1)//CHUNK} ({len(chunk)} แถว)")

    log("\n✅ Backfill เสร็จสิ้น")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
