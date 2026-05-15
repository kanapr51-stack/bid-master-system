"""
Sebastian AI Analyzer — เรียก Claude API ครั้งเดียวต่องาน
รับ pre-processed TOR text → วิเคราะห์ → คืน JSON

วิธีใช้:
    python Sebastian_AI_Analyzer.py                  # วิเคราะห์ทุกงานใน raw_jobs ที่ status=new
    python Sebastian_AI_Analyzer.py --job-id abc123  # วิเคราะห์งานเดียว

ต้องการ:
    pip install anthropic
    ANTHROPIC_API_KEY ใน environment หรือไฟล์ .env
"""

import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

import anthropic

# ---- CONFIG ----
SPREADSHEET_ID   = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
MODEL            = "claude-haiku-4-5"
MAX_TOKENS       = 1500
RESULTS_DIR      = Path(__file__).parent.parent / "data" / "ai_results"

# ---- SYSTEM PROMPT ----
SYSTEM_PROMPT = """คุณคือ Sebastian ผู้ช่วยวิเคราะห์ TOR งานประมูลก่อสร้างภาครัฐไทย

งานของคุณ: อ่าน TOR หรือข้อมูลโครงการที่ให้มา แล้วตอบกลับเป็น JSON เพียงอย่างเดียว ห้ามมีข้อความอื่น

ตอบใน JSON format นี้เสมอ:
{
  "project_type": "ถนนคอนกรีต | ท่อระบายน้ำ | อาคาร | สะพาน | อื่นๆ",
  "road_width_m": null,
  "road_length_m": null,
  "concrete_thickness_m": null,
  "sand_base_m": null,
  "shoulder_width_m": null,
  "cj_spacing_m": null,
  "ej_spacing_m": null,
  "concrete_grade": "240 | 280 | 210 | ไม่ระบุ",
  "has_dowel_bar": false,
  "has_tie_bar": false,
  "has_wire_mesh": false,
  "budget_thb": null,
  "duration_days": null,
  "location": "",
  "department": "",
  "confidence": "high | medium | low",
  "notes": "ข้อสังเกตสำคัญที่ไม่มีใน fields อื่น (สั้นๆ)"
}

กฎ:
- ถ้าข้อมูลไม่มีในเอกสาร ให้ใส่ null (ตัวเลข) หรือ "" (string)
- ตอบ JSON เท่านั้น ไม่มี markdown code block
- ถ้า TOR ไม่เกี่ยวกับงานก่อสร้าง ให้ project_type = "ไม่เกี่ยวข้อง"
"""


# ================================================================
# ANTHROPIC CLIENT
# ================================================================

def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"\'')
                    break
    if not api_key:
        raise RuntimeError("ไม่พบ ANTHROPIC_API_KEY — ตั้งค่าใน environment หรือ .env")
    return anthropic.Anthropic(api_key=api_key)


# ================================================================
# AI ANALYSIS
# ================================================================

def analyze_job(client: anthropic.Anthropic, job: dict) -> dict:
    """
    วิเคราะห์งานหนึ่งงาน — เรียก Claude ครั้งเดียว
    คืน dict ที่มีผลการวิเคราะห์
    """
    # สร้าง prompt จากข้อมูลที่มี
    preprocessed = job.get("preprocessed_text", "")
    title        = job.get("title", "ไม่ระบุชื่อ")
    dept         = job.get("department", "")
    budget       = job.get("budget", "")
    publish_date = job.get("publish_date", "")
    deadline     = job.get("deadline", "")

    user_content = f"""วิเคราะห์โครงการต่อไปนี้:

ชื่องาน: {title}
หน่วยงาน: {dept}
งบประมาณ: {budget} บาท
วันประกาศ: {publish_date}
วันยื่นซอง: {deadline}

เนื้อหา TOR / รายละเอียด:
{preprocessed or "(ไม่มีไฟล์ TOR — วิเคราะห์จากชื่องานและหน่วยงานเท่านั้น)"}
"""

    # เรียก Claude
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw_response = message.content[0].text.strip()

    # Parse JSON
    analysis = parse_ai_response(raw_response)
    analysis["_job_id"]        = job.get("job_id", "")
    analysis["_raw_response"]  = raw_response
    analysis["_analyzed_at"]   = datetime.now().isoformat()
    analysis["_input_tokens"]  = message.usage.input_tokens
    analysis["_output_tokens"] = message.usage.output_tokens

    return analysis


def parse_ai_response(text: str) -> dict:
    """Parse JSON จาก AI response — robust กับ edge cases"""
    text = text.strip()

    # ลอง parse ตรง
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ลองหา JSON block ใน response
    json_match = None
    for pattern in [r'\{[\s\S]+\}', r'```json\s*([\s\S]+?)\s*```', r'```\s*([\s\S]+?)\s*```']:
        import re
        m = re.search(pattern, text)
        if m:
            candidate = m.group(1) if m.lastindex else m.group()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # fallback: คืน dict ว่างที่มีข้อมูล error
    return {
        "project_type": "parse_error",
        "confidence": "low",
        "notes": f"AI response parse failed: {text[:200]}",
    }


# ================================================================
# SHEETS INTEGRATION
# ================================================================

def get_new_jobs_from_sheet() -> list[dict]:
    """ดึง jobs ที่ status=new จาก raw_jobs sheet"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet

    ws = open_sheet(SPREADSHEET_ID, "raw_jobs")
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []

    headers = rows[0]
    col = {h: i for i, h in enumerate(headers)}

    jobs = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) <= col.get("สถานะ", 11):
            continue
        status = row[col.get("สถานะ", 11)]
        if status != "new":
            continue

        jobs.append({
            "sheet_row":        i,
            "job_id":           row[col.get("Sebastian Master Database ", 0)],
            "title":            row[col.get("ชื่องาน ", 1)],
            "department":       row[col.get("หน่วยงาน", 2)],
            "province":         row[col.get("จังหวัด", 3)],
            "budget":           row[col.get("งบประมาณ", 7)],
            "publish_date":     row[col.get("วันที่ประกาศ", 8)],
            "deadline":         row[col.get("วันยื่นซอง", 9)],
            "tor_url":          row[col.get("ลิงก์ TOR", 10)],
            "preprocessed_text": "",
        })

    return jobs


def update_job_status(sheet_row: int, status: str):
    """อัปเดต status ของ job ใน raw_jobs"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet

    ws = open_sheet(SPREADSHEET_ID, "raw_jobs")
    ws.update_cell(sheet_row, 12, status)  # column L = สถานะ


def save_analysis_to_tor_sheet(analysis: dict, job: dict):
    """บันทึกผลวิเคราะห์ลง TOR Analysis sheet"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet

    ws = open_sheet(SPREADSHEET_ID, "TOR Analysis ")

    row = [
        job.get("job_id", ""),
        job.get("title", ""),
        job.get("department", ""),
        job.get("budget", ""),
        analysis.get("project_type", ""),
        analysis.get("road_width_m", ""),
        analysis.get("road_length_m", ""),
        analysis.get("concrete_thickness_m", ""),
        analysis.get("sand_base_m", ""),
        analysis.get("shoulder_width_m", ""),
        analysis.get("cj_spacing_m", ""),
        analysis.get("ej_spacing_m", ""),
        analysis.get("concrete_grade", ""),
        "TRUE" if analysis.get("has_dowel_bar") else "FALSE",
        "TRUE" if analysis.get("has_tie_bar") else "FALSE",
        "TRUE" if analysis.get("has_wire_mesh") else "FALSE",
        analysis.get("duration_days", ""),
        analysis.get("confidence", ""),
        analysis.get("notes", ""),
        analysis.get("_analyzed_at", ""),
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")


# ================================================================
# MAIN
# ================================================================

def main():
    parser = argparse.ArgumentParser(description="Sebastian AI Analyzer")
    parser.add_argument("--job-id", help="วิเคราะห์เฉพาะ job_id นี้")
    parser.add_argument("--max", type=int, default=50, help="จำนวนสูงสุดต่อรัน (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="ไม่บันทึกลง sheet")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Sebastian AI Analyzer")
    print("=" * 60)

    client = get_client()
    jobs = get_new_jobs_from_sheet()

    if args.job_id:
        jobs = [j for j in jobs if j["job_id"] == args.job_id]

    jobs = jobs[:args.max]
    print(f"งานที่รอวิเคราะห์: {len(jobs)} รายการ")

    if not jobs:
        print("ไม่มีงานที่ต้องวิเคราะห์")
        return

    # Optional: load preprocessed text จาก file
    download_dir = Path(__file__).parent.parent / "downloads"
    for job in jobs:
        job_id = job.get("job_id", "")
        # หาไฟล์ที่ชื่อขึ้นต้นด้วย job_id
        matches = list(download_dir.glob(f"{job_id}_*"))
        if matches:
            from Sebastian_Preprocessor import preprocess_file
            pp = preprocess_file(matches[0])
            job["preprocessed_text"] = pp["cleaned_text"]

    # วิเคราะห์ทีละงาน
    success = 0
    for i, job in enumerate(jobs, 1):
        job_id = job.get("job_id", "?")
        title  = job.get("title", "?")[:50]
        print(f"\n[{i}/{len(jobs)}] {title}...")

        try:
            analysis = analyze_job(client, job)

            # บันทึกผล JSON local
            result_file = RESULTS_DIR / f"{job_id}.json"
            result_file.write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            if not args.dry_run:
                # บันทึกลง TOR Analysis sheet
                save_analysis_to_tor_sheet(analysis, job)
                # อัปเดต status
                if job.get("sheet_row"):
                    update_job_status(job["sheet_row"], "analyzed")

            tokens_used = analysis.get("_input_tokens", 0) + analysis.get("_output_tokens", 0)
            print(f"   ✅ confidence={analysis.get('confidence')} | tokens={tokens_used}")
            success += 1

        except Exception as e:
            print(f"   ❌ Error: {e}")
            if not args.dry_run and job.get("sheet_row"):
                update_job_status(job["sheet_row"], "error")

        time.sleep(0.5)  # rate limit buffer

    print(f"\n{'='*60}")
    print(f"เสร็จสิ้น: {success}/{len(jobs)} งาน")
    print(f"ผลบันทึกที่: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
