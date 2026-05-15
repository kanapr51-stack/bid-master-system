"""
Sebastian_Cost_Filler.py — ดึงข้อมูลจาก Sheet 2 → เติมใน cost_data_By_Dexter (Sheet 3)

วิธีการ:
  1. อ่านงานจาก Sheet 2 ที่ status='analyzed'
  2. สำหรับแต่ละงาน: เติมค่า C11–C17 ใน cost_data_By_Dexter
  3. อ่าน output (ต้นทุนรวม) จาก summary rows
  4. บันทึกผลลง Ranker input (local JSON)
  5. อัปเดต status ใน Sheet 2 → 'cost_calculated'

Cell mapping ใน cost_data_By_Dexter (Sheet 3):
  C11 = W  (ความกว้าง เมตร)
  C12 = L  (ความยาว เมตร)
  C13 = T  (ความหนา เมตร)
  C14 = St (ไหล่ทาง เมตร)
  C15 = Sh (รูปทรง — ค่าเริ่มต้น 1)
  C16 = CJ (จำนวนรอยต่อก่อสร้าง)
  C17 = EJ (จำนวนรอยต่อขยาย)
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID  = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET2_NAME     = "job_specs"
SHEET3_NAME     = "cost_data_By_Dexter"

# Input cells ใน cost_data_By_Dexter
INPUT_CELL_MAP = {
    "W":  "C11",
    "L":  "C12",
    "T":  "C13",
    "St": "C14",
    "Sh": "C15",   # shape factor (default 1)
    "CJ": "C16",
    "EJ": "C17",
}

# Output cells ใน cost_data_By_Dexter (ตรวจสอบแล้ว 2026-05-01)
OUTPUT_CELLS = {
    "material_cost":  "I77",   # ■ รวมต้นทุนวัตถุดิบ
    "labor_cost":     "I84",   # ■ รวมค่าแรงงาน
    "total_cost":     "G91",   # ● รวมต้นทุนทางตรง (Direct Cost)
    "bid_price":      "G98",   # ● ราคาเสนอประมูล = Direct Cost × Factor F
    "margin_pct":     "G100",  # CHECK: กำไรสุทธิ %
}

DATA_DIR = Path(__file__).parent.parent / "data"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ================================================================
# SHEET OPERATIONS
# ================================================================

def get_sheet2():
    return open_sheet(SPREADSHEET_ID, SHEET2_NAME)


def get_sheet3():
    return open_sheet(SPREADSHEET_ID, SHEET3_NAME)


def read_analyzed_jobs() -> list[dict]:
    """อ่านงานที่ status='analyzed' จาก Sheet 2"""
    ws = get_sheet2()
    rows = ws.get_all_records(expected_headers=ws.row_values(1))
    return [r for r in rows if str(r.get("status", "")).strip() == "analyzed"]


def update_sheet2_status(ws2, job_id: str, new_status: str):
    cell = ws2.find(job_id, in_column=1)
    if cell:
        header = ws2.row_values(1)
        try:
            status_col = header.index("status") + 1
            ws2.update_cell(cell.row, status_col, new_status)
        except ValueError:
            pass


# ================================================================
# COST CALCULATION
# ================================================================

def fill_cost_template(ws3, job: dict) -> dict:
    """
    เติมค่า C11–C17 ใน Sheet 3 แล้วอ่าน output
    คืนค่า dict ของ output values
    """
    def _val(v, default=0):
        try:
            return float(v) if v not in ("", None) else default
        except Exception:
            return default

    # ค่า input
    inputs = {
        "W":  _val(job.get("W"), 0),
        "L":  _val(job.get("L"), 0),
        "T":  _val(job.get("T"), 0),
        "St": _val(job.get("St"), 0.2),
        "Sh": 1,
        # CJ/EJ default: มาตรฐานถนน คสล. ไทย
        "CJ": _val(job.get("joint_CJ"), 10),
        "EJ": _val(job.get("joint_EJ"), 100),
    }

    # เขียนค่า input ลง Sheet 3
    for field, cell in INPUT_CELL_MAP.items():
        try:
            ws3.update([[inputs[field]]], cell)
        except Exception as e:
            log(f"    warn: ไม่สามารถเขียน {cell}: {e}")

    # รอ Sheets recalculate (Google Sheets คำนวณ async)
    time.sleep(3)

    # อ่าน output
    outputs = {}
    for label, cell in OUTPUT_CELLS.items():
        try:
            val = ws3.acell(cell).value
            try:
                outputs[label] = float(str(val).replace(",", "")) if val else 0
            except Exception:
                outputs[label] = 0
        except Exception as e:
            log(f"    warn: อ่าน {cell} ไม่ได้: {e}")
            outputs[label] = 0

    return {**inputs, **outputs}


def calculate_margin(job: dict, outputs: dict) -> float:
    """คำนวณ % margin = (budget - total_cost) / budget * 100"""
    budget = float(job.get("budget") or 0)
    total_cost = outputs.get("total_cost", 0)
    if budget > 0 and total_cost > 0:
        return round((budget - total_cost) / budget * 100, 2)
    return 0.0


# ================================================================
# MAIN
# ================================================================

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 60)
    log("Sebastian Cost Filler — เริ่มต้น")
    log("=" * 60)

    jobs = read_analyzed_jobs()
    log(f"พบ {len(jobs)} งานที่รอคำนวณต้นทุน")

    if not jobs:
        log("ไม่มีงานใหม่ — เสร็จสิ้น")
        return

    ws2 = get_sheet2()
    ws3 = get_sheet3()

    results = []

    for i, job in enumerate(jobs, 1):
        job_id = str(job.get("job_id", ""))
        title = str(job.get("title", ""))[:60]
        log(f"\n[{i}/{len(jobs)}] {job_id}: {title}")

        # ตรวจว่ามีค่า dimension เพียงพอ
        if not job.get("W") or not job.get("L") or not job.get("T"):
            log("  ข้ามเพราะไม่มีข้อมูล W/L/T")
            update_sheet2_status(ws2, job_id, "cost_skip_no_dims")
            continue

        try:
            log(f"  เติม W={job.get('W')}, L={job.get('L')}, T={job.get('T')}")
            outputs = fill_cost_template(ws3, job)
            margin = calculate_margin(job, outputs)

            result = {
                "job_id":       job_id,
                "title":        str(job.get("title", "")),
                "department":   str(job.get("department", "")),
                "province":     str(job.get("province", "")),
                "publish_date": str(job.get("publish_date", "")),
                "W": outputs.get("W"),
                "L": outputs.get("L"),
                "T": outputs.get("T"),
                "budget":           float(job.get("budget") or 0),
                "material_cost":    outputs.get("material_cost", 0),
                "labor_cost":       outputs.get("labor_cost", 0),
                "machinery_cost":   outputs.get("machinery_cost", 0),
                "total_cost":       outputs.get("total_cost", 0),
                "bid_price":        outputs.get("bid_price", 0),
                "margin_pct":       margin,
                "tor_confidence":   str(job.get("tor_confidence", "low")),
                "has_pr4":          job.get("has_pr4") == "Y",
                "has_pr5":          job.get("has_pr5") == "Y",
                "calculated_at":    datetime.now().isoformat(),
            }

            results.append(result)
            log(f"  ต้นทุน: {outputs.get('total_cost', 0):,.0f} บาท | margin: {margin:.1f}%")

            update_sheet2_status(ws2, job_id, "cost_calculated")

        except Exception as e:
            log(f"  ERROR: {e}")
            update_sheet2_status(ws2, job_id, "cost_error")

        time.sleep(1)

    # บันทึก results สำหรับ Ranker
    if results:
        out_path = DATA_DIR / f"cost_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        out_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log(f"\nบันทึก {len(results)} งาน → {out_path}")

    log(f"\nสรุป: คำนวณสำเร็จ {len(results)}/{len(jobs)} งาน")


if __name__ == "__main__":
    main()
