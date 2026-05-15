"""
Sebastian_JSON_Merger.py — ผนวก JSON จาก ปร.4/5 + TOR → Combined JSON
แล้วบันทึกลง Sheet 2 (job_specs)

Pipeline position: หลัง PR45_Parser + TOR_Analyzer
"""

import sys
import re
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

# ================================================================
# MERGE LOGIC
# ================================================================

def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


def merge_job_json(
    pr4: dict,
    pr5: dict,
    tor: dict,
    raw_job: dict,
) -> dict:
    """
    ผนวก JSON จาก ปร.4, ปร.5, TOR + raw_job → Combined JSON

    Priority สำหรับ dimensions: TOR > ปร.4 > ชื่องาน
    Priority สำหรับ ราคา: ปร.5 > raw_job budget
    """

    # ---- Dimensions ----
    # พยายามดึงจาก title ถ้า TOR ไม่มี
    W = _safe_float(tor.get("width_m"))       or _dim_from_title(raw_job.get("title", ""), "กว้าง")
    L = _safe_float(tor.get("length_m"))      or _dim_from_title(raw_job.get("title", ""), "ยาว")
    T = _safe_float(tor.get("thickness_m"))   or _dim_from_title(raw_job.get("title", ""), "หนา")
    St = _safe_float(tor.get("shoulder_width_m"))

    # ---- Materials ----
    concrete_grade = tor.get("concrete_grade") or "unknown"

    dowel = tor.get("dowel_bar") or {}
    tie   = tor.get("tie_bar") or {}

    # ---- Joints ----
    # ปร.5 ไม่มี joint data, ใช้จาก TOR
    cj = _safe_float(tor.get("joint_CJ_count"))
    ej = _safe_float(tor.get("joint_EJ_count"))

    # ---- Budget ----
    budget = (
        _safe_float(pr5.get("budget_price")) or
        _safe_float(pr5.get("total_price")) or
        _safe_float(raw_job.get("budget_raw")) or
        0
    )

    boq_total = _safe_float(pr4.get("total_price")) or 0

    # ---- Quality flags ----
    has_pr4 = bool(pr4 and not pr4.get("error") and pr4.get("item_count", 0) > 0)
    has_pr5 = bool(pr5 and not pr5.get("error") and pr5.get("total_price"))
    has_tor = bool(tor and not tor.get("error") and tor.get("confidence") != "low")

    # ---- Tier ----
    title = raw_job.get("title", "")
    _tier1_kw = ["ถนนคอนกรีต", "คอนกรีตเสริมเหล็ก", "ปูคอนกรีต"]
    tier = "Tier 1" if any(k in title for k in _tier1_kw) else "Tier 2"

    # ---- Budget fallback: ใช้ raw_job budget ถ้าไม่มีจาก ปร.5 ----
    budget = (
        _safe_float(pr5.get("budget_price")) or
        _safe_float(pr5.get("total_price")) or
        _safe_float(raw_job.get("budget_raw")) or
        _safe_float(raw_job.get("budget")) or
        0
    )

    return {
        # Identity
        "job_id":            str(raw_job.get("job_id", "")),
        "title":             raw_job.get("title", ""),
        "department":        raw_job.get("department", ""),
        "province":          raw_job.get("province", ""),
        "district":          raw_job.get("district", ""),
        "publish_date":      raw_job.get("publish_date", ""),
        "deadline":          raw_job.get("deadline", ""),
        "procurement_type":  raw_job.get("procurement_type", ""),
        "tor_url":           raw_job.get("tor_url", ""),
        "tier":              tier,

        # Dimensions
        "W":  W,
        "L":  L,
        "T":  T,
        "St": St,   # shoulder width

        # Concrete
        "concrete_grade": concrete_grade,

        # Reinforcement
        "dowel_dia_mm":     _safe_float(dowel.get("diameter_mm")),
        "dowel_len_mm":     _safe_float(dowel.get("length_mm")),
        "dowel_spacing_mm": _safe_float(dowel.get("spacing_mm")),
        "tie_bar_dia_mm":   _safe_float(tie.get("diameter_mm")),
        "tie_bar_len_mm":   _safe_float(tie.get("length_mm")),
        "wire_mesh":        tor.get("wire_mesh"),

        # Joints
        "joint_CJ": cj,
        "joint_EJ": ej,

        # Budget (budget คำนวณไว้แล้วข้างบน)
        "budget":     budget,
        "boq_total":  boq_total,
        "direct_cost":   _safe_float(pr5.get("direct_cost")),
        "overhead_pct":  _safe_float(pr5.get("overhead_pct")),
        "profit_pct":    _safe_float(pr5.get("profit_pct")),

        # Duration & Warranty
        "construction_duration_days": _safe_float(tor.get("construction_duration_days")),
        "delivery_period_days":       _safe_float(tor.get("delivery_period_days")),
        "warranty_period_days":       _safe_float(tor.get("warranty_period_days")),

        # TOR Conditions
        "required_tests":                tor.get("required_tests"),
        "required_delivery_documents":   tor.get("required_delivery_documents"),
        "special_conditions":            tor.get("special_conditions"),

        # Quality
        "tor_confidence": tor.get("confidence", "low"),
        "tor_notes":      tor.get("notes"),
        "has_pr4":        has_pr4,
        "has_pr5":        has_pr5,
        "has_tor":        has_tor,

        # BOQ items (เก็บไว้ใน notes column ย่อๆ)
        "boq_summary": _boq_summary(pr4.get("items", [])),

        "merged_at": datetime.now().isoformat(),
    }


def _dim_from_title(title: str, keyword: str) -> float | None:
    """ดึงตัวเลขมิติจากชื่องาน เช่น 'กว้าง 5.00 เมตร'"""
    import re
    pattern = keyword + r'\s*([\d.]+)\s*(?:เมตร|ม\.)?'
    m = re.search(pattern, title)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass
    return None


def _boq_summary(items: list) -> str:
    """สรุป BOQ items สั้นๆ สำหรับใส่ใน cell"""
    if not items:
        return ""
    lines = []
    for item in items[:10]:  # แสดงแค่ 10 รายการแรก
        desc = item.get("description", "")[:50]
        qty = item.get("quantity")
        unit = item.get("unit", "")
        if qty:
            lines.append(f"{desc}: {qty} {unit}")
        else:
            lines.append(desc)
    return " | ".join(lines)


# ================================================================
# SHEET LOOKUP
# ================================================================

def get_raw_job_from_sheet(job_id: str) -> dict:
    """ดึง raw_job จาก raw_jobs_bidding Sheet 1 โดยตรง"""
    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet
    SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
    ws = open_sheet(SPREADSHEET_ID, "raw_jobs_bidding")
    rows = ws.get_all_records()
    for row in rows:
        if str(row.get("job_id", "")) == str(job_id):
            return row
    return {}


# ================================================================
# FOLDER LOOKUP
# ================================================================

def find_job_dir(download_dir: str | Path, job_id: str) -> Path | None:
    """หา job folder จาก job_id — รองรับทั้ง '69019077732' และ '2026-05-07-69019077732-...' """
    download_dir = Path(download_dir)
    exact = download_dir / job_id
    if exact.exists():
        return exact
    matches = list(download_dir.glob(f"*{job_id}*"))
    return matches[0] if matches else None


# ================================================================
# PROCESS JOB FOLDER
# ================================================================

def process_job(job_dir: str | Path, raw_job: dict = None) -> dict:
    """
    อ่านไฟล์จาก job folder → merge → return combined JSON
    raw_job จะถูกดึงจาก Sheet 1 เสมอ เพื่อให้ข้อมูลตรง
    """
    from Sebastian_PR45_Parser import parse_job_docs
    from Sebastian_TOR_Analyzer import analyze_job_tor

    job_dir = Path(job_dir)

    # ดึง job_id จาก folder name หรือ raw_job
    job_id = None
    if raw_job:
        job_id = str(raw_job.get("job_id", ""))
    if not job_id:
        # หา job_id จากชื่อ folder เช่น "2026-05-07-69019077732-ชื่องาน"
        import re as _re
        m = _re.search(r'(\d{11})', job_dir.name)
        if m:
            job_id = m.group(1)

    # ดึงข้อมูลจาก Sheet 1 เสมอ (แหล่งข้อมูลจริง)
    if job_id:
        sheet_raw = get_raw_job_from_sheet(job_id)
        if sheet_raw:
            raw_job = sheet_raw
            raw_job["job_id"] = str(job_id)
    if not raw_job:
        raw_job = {}

    # 1. Parse ปร.4 และ ปร.5
    pr_results = parse_job_docs(job_dir)
    pr4 = pr_results.get("pr4", {})
    pr5 = pr_results.get("pr5", {})

    # 2. Analyze TOR
    tor = analyze_job_tor(job_dir, raw_job)

    # 3. Merge
    combined = merge_job_json(pr4, pr5, tor, raw_job)

    # 4. บันทึก combined JSON ไว้ใน job folder
    out_path = job_dir / "combined.json"
    out_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 5. Rename folder → YYYY-MM-DD-<job_id>-<title> (ถ้ายังไม่ได้ rename)
    job_id  = str(raw_job.get("job_id", ""))
    title   = str(raw_job.get("title", ""))
    if job_id and title and job_dir.name == job_id:
        safe_title = re.sub(r'[\\/:*?"<>|]', "", title).strip()[:60]
        new_name   = f"{datetime.now().strftime('%Y-%m-%d')}-{job_id}-{safe_title}"
        new_dir    = job_dir.parent / new_name
        try:
            job_dir.rename(new_dir)
            print(f"  rename folder: {job_id} → {new_name}", flush=True)
        except Exception as e:
            print(f"  rename folder error: {e}", flush=True)

    return combined


# ================================================================
# BATCH PROCESS
# ================================================================

def process_all_jobs(download_dir: str | Path, raw_jobs: list[dict]) -> list[dict]:
    """
    วน loop งานทั้งหมดที่มี status='docs_downloaded'
    Return list ของ combined JSONs
    """
    download_dir = Path(download_dir)
    raw_job_map = {str(j.get("job_id", "")): j for j in raw_jobs}

    results = []
    for job_id, raw_job in raw_job_map.items():
        job_dir = find_job_dir(download_dir, job_id)
        if not job_dir:
            continue

        # ข้ามถ้า combined.json มีอยู่แล้ว
        if (job_dir / "combined.json").exists():
            existing = json.loads((job_dir / "combined.json").read_text(encoding="utf-8"))
            results.append(existing)
            continue

        print(f"[merge] {job_id}: {raw_job.get('title', '')[:50]}", flush=True)
        try:
            combined = process_job(job_dir, raw_job)
            results.append(combined)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)

    return results


if __name__ == "__main__":
    # Test standalone merge
    sample_pr4 = {
        "doc_type": "pr4",
        "items": [{"no": "1", "description": "งานดิน", "quantity": 100, "unit": "ม.³", "unit_price": 50, "total": 5000}],
        "item_count": 1,
        "total_price": 5000,
    }
    sample_pr5 = {
        "doc_type": "pr5",
        "total_price": 500000,
        "budget_price": 500000,
        "overhead_pct": 15,
        "profit_pct": 5,
    }
    sample_tor = {
        "width_m": 5.0,
        "length_m": 100.0,
        "thickness_m": 0.15,
        "concrete_grade": "240",
        "confidence": "high",
    }
    sample_raw = {
        "job_id": "TEST001",
        "title": "ก่อสร้างถนนคอนกรีต กว้าง 5.00 เมตร ยาว 100.00 เมตร",
        "budget_raw": 500000,
    }

    result = merge_job_json(sample_pr4, sample_pr5, sample_tor, sample_raw)
    print(json.dumps(result, ensure_ascii=False, indent=2))
