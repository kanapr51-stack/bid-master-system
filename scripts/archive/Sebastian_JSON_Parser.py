"""
Sebastian JSON Parser — อ่านผล AI analysis แล้วใส่ข้อมูลลง cost_data_By_Dexter + ranked_jobs

Pipeline: AI results → cost_data_By_Dexter (C11-C17) + ranked_jobs sheet

วิธีใช้:
    python Sebastian_JSON_Parser.py                  # ประมวลผลทุกงานที่ analyzed
    python Sebastian_JSON_Parser.py --job-id abc123  # งานเดียว
"""

import json
import argparse
from pathlib import Path
from datetime import datetime

# ---- CONFIG ----
SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
RESULTS_DIR    = Path(__file__).parent.parent / "data" / "ai_results"

# ---- RANKED_JOBS COLUMNS ----
# A=job_id | B=ชื่องาน | C=หน่วยงาน | D=งบประมาณ | E=ประเภทงาน
# F=กว้าง(m) | G=ยาว(m) | H=หนา(m) | I=estimate_cost | J=margin_est
# K=confidence | L=status | M=notes | N=วันที่วิเคราะห์


def get_sheets_client():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet, get_client
    import gspread
    gc = get_client()
    return gc.open_by_key(SPREADSHEET_ID)


# ================================================================
# COST ESTIMATOR
# ================================================================

def estimate_cost(analysis: dict) -> dict:
    """
    ประมาณต้นทุนเบื้องต้นจาก analysis data
    ใช้ราคาอ้างอิงมาตรฐาน (อัปเดตได้ทีหลัง)
    """
    W  = analysis.get("road_width_m") or 0
    L  = analysis.get("road_length_m") or 0
    T  = analysis.get("concrete_thickness_m") or 0.15
    St = analysis.get("sand_base_m") or 0.05
    Sh = analysis.get("shoulder_width_m") or 0.5

    if not (W and L):
        return {"estimate_cost": None, "margin_est": None, "calc_note": "ไม่มีมิติ W/L"}

    # ราคาอ้างอิง (บาท/หน่วย) — อัปเดตได้ใน config
    PRICES = {
        "concrete_240":    2800,   # บาท/ลบ.ม.
        "sand":             400,   # บาท/ลบ.ม.
        "wire_mesh":        120,   # บาท/ตร.ม.
        "curing_compound":   35,   # บาท/ตร.ม.
        "formwork":         800,   # บาท/ตร.ม.
        "earthwork":         25,   # บาท/ตร.ม.
        "overhead_factor": 1.25,   # overhead + profit
        "factor_f":        1.4054, # กรมบัญชีกลาง
    }

    concrete_vol  = W * L * T
    sand_vol      = W * L * St
    surface_area  = W * L
    shoulder_area = (W + Sh * 2) * L

    material_cost = (
        concrete_vol  * PRICES["concrete_240"] +
        sand_vol      * PRICES["sand"] +
        surface_area  * PRICES["wire_mesh"] +
        surface_area  * PRICES["curing_compound"] +
        (W * T * 2)   * PRICES["formwork"] +  # ขอบแผง
        shoulder_area * PRICES["earthwork"]
    )

    direct_cost = material_cost * PRICES["overhead_factor"]
    bid_price   = direct_cost * PRICES["factor_f"]
    budget      = analysis.get("budget_thb") or 0

    margin_est = None
    if budget and bid_price > 0:
        margin_est = round((budget - bid_price) / budget * 100, 1) if budget > bid_price else None

    return {
        "estimate_cost": round(direct_cost),
        "bid_estimate":  round(bid_price),
        "margin_est":    margin_est,
        "calc_note":     f"W={W}m L={L}m T={T}m | concrete={concrete_vol:.0f}m³",
    }


# ================================================================
# WRITE TO SHEETS
# ================================================================

def write_to_cost_data(analysis: dict, job: dict, spreadsheet) -> bool:
    """
    เติมค่า C11-C17 ใน cost_data_By_Dexter (มิติโครงการ)
    สร้าง tab ใหม่ per-job หรือเติมใน template tab
    """
    try:
        ws = spreadsheet.worksheet("cost_data_By_Dexter")

        updates = []

        def maybe_update(cell, value):
            if value is not None:
                updates.append({"range": cell, "values": [[value]]})

        maybe_update("C11", analysis.get("road_width_m"))
        maybe_update("C12", analysis.get("road_length_m"))
        maybe_update("C13", analysis.get("concrete_thickness_m"))
        maybe_update("C14", analysis.get("sand_base_m"))
        maybe_update("C16", analysis.get("cj_spacing_m"))
        maybe_update("C17", analysis.get("ej_spacing_m"))

        # ชื่องาน + วันที่
        maybe_update("B4", job.get("title", ""))
        maybe_update("B5", job.get("job_id", ""))
        maybe_update("B6", analysis.get("project_type", ""))
        maybe_update("B7", datetime.now().strftime("%d/%m/%Y"))

        if updates:
            ws.batch_update(updates)

        # B column checkboxes ตาม analysis
        _update_checkboxes(ws, analysis)

        return True

    except Exception as e:
        print(f"   ⚠️ cost_data error: {e}")
        return False


def _update_checkboxes(ws, analysis: dict):
    """อัปเดต B column checkboxes ตามผลวิเคราะห์"""
    project_type = analysis.get("project_type", "")
    is_road = "ถนน" in project_type or "concrete" in project_type.lower()

    updates = []

    # Wire Mesh (row 36): TRUE ถ้าเป็นถนนคอนกรีตและมี wire mesh
    if analysis.get("has_wire_mesh") or is_road:
        updates.append({"range": "B36", "values": [["TRUE"]]})

    # DB16 (row 41): TRUE ถ้ามี Dowel Bar
    if analysis.get("has_dowel_bar"):
        updates.append({"range": "B41", "values": [["TRUE"]]})
        updates.append({"range": "B42", "values": [["FALSE"]]})

    if updates:
        ws.batch_update(updates)


def write_to_ranked_jobs(analysis: dict, job: dict, cost_est: dict, spreadsheet) -> bool:
    """บันทึกสรุปลง ranked_jobs sheet"""
    try:
        ws = spreadsheet.worksheet("ranked_jobs")

        # เช็ค duplicate
        existing_ids = ws.col_values(1)[1:]
        job_id = job.get("job_id", "")
        if job_id in existing_ids:
            # Update แทน append
            row_idx = existing_ids.index(job_id) + 2
            pass  # TODO: update existing row
        else:
            row = [
                job_id,
                job.get("title", "")[:100],
                job.get("department", "")[:80],
                job.get("budget", ""),
                analysis.get("project_type", ""),
                analysis.get("road_width_m", ""),
                analysis.get("road_length_m", ""),
                analysis.get("concrete_thickness_m", ""),
                cost_est.get("estimate_cost", ""),
                cost_est.get("margin_est", ""),
                analysis.get("confidence", ""),
                "analyzed",
                analysis.get("notes", ""),
                analysis.get("_analyzed_at", ""),
            ]
            ws.append_row(row, value_input_option="USER_ENTERED")

        return True

    except Exception as e:
        print(f"   ⚠️ ranked_jobs error: {e}")
        return False


# ================================================================
# PROCESS ONE JOB
# ================================================================

def process_job_result(result_file: Path, spreadsheet) -> bool:
    """อ่าน AI result JSON และเขียนลง sheets"""
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ อ่านไฟล์ไม่ได้: {result_file} — {e}")
        return False

    job_id = data.get("_job_id", result_file.stem)
    print(f"Processing: {job_id[:12]}...")

    # สร้าง job dict จาก result data
    job = {
        "job_id": job_id,
        "title":       data.get("_title", ""),
        "department":  data.get("_department", ""),
        "budget":      data.get("budget_thb", ""),
    }

    # ประมาณต้นทุน
    cost_est = estimate_cost(data)

    # เขียนลง sheets
    ok1 = write_to_cost_data(data, job, spreadsheet)
    ok2 = write_to_ranked_jobs(data, job, cost_est, spreadsheet)

    if ok1 and ok2:
        # Mark as processed
        result_file.rename(result_file.with_suffix(".done.json"))
        print(f"   ✅ estimate={cost_est.get('estimate_cost'):,} | margin={cost_est.get('margin_est')}%")
        return True

    return False


# ================================================================
# MAIN
# ================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", help="วิเคราะห์เฉพาะ job_id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Sebastian JSON Parser")
    print("=" * 60)

    if not RESULTS_DIR.exists():
        print(f"ไม่พบ results dir: {RESULTS_DIR}")
        return

    # หา result files ที่ยังไม่ได้ process
    result_files = list(RESULTS_DIR.glob("*.json"))
    result_files = [f for f in result_files if ".done." not in f.name]

    if args.job_id:
        result_files = [f for f in result_files if f.stem == args.job_id]

    print(f"พบ {len(result_files)} ไฟล์รอ process")

    if not result_files:
        return

    if args.dry_run:
        print("DRY RUN — ไม่บันทึกลง sheet")
        for f in result_files[:3]:
            data = json.loads(f.read_text(encoding="utf-8"))
            cost = estimate_cost(data)
            print(f"\n{f.stem}: {json.dumps({**data, **cost}, ensure_ascii=False, indent=2)[:500]}")
        return

    spreadsheet = get_sheets_client()
    success = 0
    for f in result_files:
        if process_job_result(f, spreadsheet):
            success += 1

    print(f"\nเสร็จ: {success}/{len(result_files)}")


if __name__ == "__main__":
    main()
