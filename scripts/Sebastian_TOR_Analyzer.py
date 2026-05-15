"""
Sebastian_TOR_Analyzer.py — AI อ่าน TOR → JSON วัสดุและมิติ

ใช้ Claude API วิเคราะห์ขอบเขตงาน (TOR)
Output: W, L, T, grade, dowel, wire_mesh, CJ, EJ, ...

ต้องตั้งค่า .env:
    ANTHROPIC_API_KEY=sk-ant-...
"""

import sys
import os
import re
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

try:
    import fitz  # pymupdf
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"
MAX_CHARS = 8000

# ================================================================
# SYSTEM PROMPT
# ================================================================

SYSTEM_PROMPT = """คุณคือผู้เชี่ยวชาญด้านงานก่อสร้างถนนคอนกรีตในประเทศไทย
อ่านเอกสาร TOR/ขอบเขตงาน แล้วสกัดข้อมูลจำเพาะทางเทคนิคออกมา

กฎ:
- ตอบเป็น JSON เท่านั้น ห้ามมีคำอธิบายหรือ markdown
- ถ้าไม่พบข้อมูล ให้ใส่ null
- ตัวเลขทศนิยมใช้จุด (เช่น 0.15 ไม่ใช่ 0,15)
- ความกว้าง/ยาว/หนา หน่วยเป็น เมตร
- dowel_bar spacing หน่วยเป็น มม.

JSON format (ห้ามเพิ่ม field อื่น):
{
  "road_type": "คอนกรีตเสริมเหล็ก | คอนกรีตล้วน | unknown",
  "width_m": <number | null>,
  "length_m": <number | null>,
  "thickness_m": <number | null>,
  "shoulder_width_m": <number | null>,
  "concrete_grade": "240 | 250 | 280 | 300 | unknown",
  "dowel_bar": {
    "diameter_mm": <number | null>,
    "length_mm": <number | null>,
    "spacing_mm": <number | null>
  },
  "tie_bar": {
    "diameter_mm": <number | null>,
    "length_mm": <number | null>
  },
  "wire_mesh": <"6x6 | 4x4 | ไม่ใช้ | unknown" | null>,
  "joint_CJ_count": <number | null>,
  "joint_EJ_count": <number | null>,
  "drainage_pipe": <"มี | ไม่มี | unknown" | null>,
  "budget_thb": <number | null>,
  "construction_duration_days": <number | null>,
  "delivery_period_days": <number | null>,
  "warranty_period_days": <number | null>,
  "required_tests": <"รายการทดสอบที่กำหนด เช่น core test, compressive strength" | null>,
  "required_delivery_documents": <"เอกสารที่ต้องส่งมอบ เช่น แบบ as-built, ใบรับรองวัสดุ" | null>,
  "special_conditions": <"เงื่อนไขพิเศษ เช่น ห้ามทำงานกลางคืน, ต้องมีวิศวกรควบคุม" | null>,
  "confidence": "high | medium | low",
  "notes": <"ข้อมูลสำคัญอื่นๆ ที่ไม่มี field รองรับ" | null>
}

หมายเหตุ field ระยะเวลา:
- construction_duration_days: ระยะเวลาดำเนินงาน/ก่อสร้าง (วัน)
- delivery_period_days: ระยะเวลาส่งมอบงาน (วัน) — ถ้าไม่ระบุแยกให้ใส่ค่าเดียวกับ construction_duration_days
- warranty_period_days: ระยะเวลาประกันผลงาน (วัน) — มักระบุเป็น "2 ปี" = 730 วัน"""


# ================================================================
# TEXT EXTRACTION
# ================================================================

KEYWORDS_PRIORITY = [
    "ขอบเขต", "วัสดุ", "spec", "คอนกรีต", "กว้าง", "ยาว", "หนา",
    "dowel", "เหล็ก", "ท่อ", "ไหล่ทาง", "รอยต่อ", "grade", "ปูน",
    "มาตรฐาน", "กำลัง", "บด", "บดอัด", "ราคา", "งบประมาณ",
    "ระยะเวลา", "ดำเนินงาน", "ก่อสร้าง", "ส่งมอบ", "วัน", "กำหนดแล้วเสร็จ",
    "ประกัน", "ประกันงาน", "ประกันผลงาน", "รับประกัน",
    "เอกสาร", "หลักฐาน", "ใบรับรอง", "ทดสอบ", "ทดสอบแกน", "core",
    "compressive", "กด", "แรงกด", "lab", "ห้องทดสอบ",
    "เงื่อนไข", "ข้อกำหนด", "พิเศษ", "ข้อบังคับ",
]


def extract_tor_text(path: Path, max_chars: int = MAX_CHARS) -> str:
    """อ่าน TOR PDF → text ที่ clean แล้ว prioritize เนื้อหาสำคัญ"""
    if not PDF_SUPPORT:
        return ""

    doc = fitz.open(str(path))
    pages_text = [page.get_text() for page in doc]
    full_text = "\n".join(pages_text)

    lines = full_text.split("\n")

    # นับความถี่ line (เพื่อลบ header/footer ซ้ำ)
    freq = {}
    for line in lines:
        s = line.strip()
        if s:
            freq[s] = freq.get(s, 0) + 1

    # แยก relevant vs other
    relevant, other = [], []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if freq.get(s, 0) >= 3 and len(s) <= 60:
            continue  # ข้าม header/footer
        if any(kw in s for kw in KEYWORDS_PRIORITY):
            relevant.append(s)
        else:
            other.append(s)

    # ประกอบ text: relevant ก่อน จากนั้น other
    combined = "\n".join(relevant) + "\n---\n" + "\n".join(other)
    return combined[:max_chars]


def extract_tor_text_excel(path: Path) -> str:
    """อ่าน TOR Excel"""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), data_only=True)
        lines = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                cells = [str(v).strip() for v in row if v is not None]
                if cells:
                    lines.append(" ".join(cells))
        return "\n".join(lines)[:MAX_CHARS]
    except Exception:
        return ""


# ================================================================
# AI ANALYSIS
# ================================================================

def call_claude(tor_text: str, job_info: dict) -> dict:
    """เรียก Claude API → JSON"""
    if not CLAUDE_AVAILABLE:
        return {"error": "anthropic package ไม่ได้ติดตั้ง"}
    if not ANTHROPIC_API_KEY:
        return {"error": "ไม่พบ ANTHROPIC_API_KEY ใน .env"}

    job_ctx = ""
    if job_info:
        job_ctx = (
            f"ชื่องาน: {job_info.get('title', '')}\n"
            f"หน่วยงาน: {job_info.get('department', '')}\n"
            f"งบประมาณ: {job_info.get('budget', '')} บาท\n\n"
        )

    user_msg = f"{job_ctx}เอกสาร TOR:\n\n{tor_text}"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = message.content[0].text.strip()

        # แยก JSON จาก response
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            return json.loads(m.group(0))
        return {"error": "ไม่พบ JSON ใน response", "raw": raw[:300]}

    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"error": str(e)}


# ================================================================
# MAIN ENTRY
# ================================================================

def analyze_tor(file_path: str | Path, job_info: dict = None) -> dict:
    """
    Main entry point.
    คืนค่า JSON dict ของ specs จาก TOR
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"ไม่พบไฟล์: {path}", "confidence": "low"}

    ext = path.suffix.lower()
    if ext == ".pdf":
        text = extract_tor_text(path)
    elif ext in (".xlsx", ".xls"):
        text = extract_tor_text_excel(path)
    else:
        return {"error": f"ไม่รองรับ format: {ext}", "confidence": "low"}

    if not text.strip():
        return {"error": "ไม่สามารถอ่าน text ได้", "confidence": "low"}

    result = call_claude(text, job_info or {})
    result["source_file"] = str(path)
    result["analyzed_at"] = datetime.now().isoformat()

    return result


def analyze_job_tor_vision(job_dir: Path, job_info: dict = None) -> dict:
    """
    Fallback: อ่าน pB1.pdf + pB2.pdf จาก BOQ zip ด้วย Claude Vision
    ดึง W, L, T, St, CJ, EJ, concrete_grade, dowel, wire_mesh
    """
    if not CLAUDE_AVAILABLE or not ANTHROPIC_API_KEY:
        return {"error": "Claude ไม่พร้อม", "confidence": "low"}

    import base64
    try:
        import fitz as _fitz
    except ImportError:
        return {"error": "pymupdf ไม่ได้ติดตั้ง", "confidence": "low"}

    # เก็บภาพจาก pB1 + pB2 (spec-heavy pages)
    images = []
    for fname in ("pB1.pdf", "pB2.pdf", "pB3.pdf"):
        fpath = job_dir / fname
        if not fpath.exists():
            continue
        doc = _fitz.open(str(fpath))
        for i, pg in enumerate(doc):
            if i >= 2:
                break
            mat = _fitz.Matrix(2.0, 2.0)
            pix = pg.get_pixmap(matrix=mat)
            images.append(base64.standard_b64encode(pix.tobytes("png")).decode())

    if not images:
        return {"error": "ไม่พบ pB1/pB2/pB3.pdf ใน folder", "confidence": "low"}

    job_ctx = ""
    if job_info:
        job_ctx = (
            f"ชื่องาน: {job_info.get('title', '')}\n"
            f"งบประมาณ: {job_info.get('budget', '')} บาท\n\n"
        )

    content = []
    for b64 in images[:6]:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})

    content.append({
        "type": "text",
        "text": (
            f"{job_ctx}"
            "นี่คือเอกสาร BOQ งานก่อสร้างถนนคอนกรีตเสริมเหล็ก\n"
            "กรุณาดึงข้อมูลจำเพาะทั้งหมดที่เห็น แล้วตอบเป็น JSON เท่านั้น:\n"
            '{\n'
            '  "road_type": "คอนกรีตเสริมเหล็ก | คอนกรีตล้วน | unknown",\n'
            '  "width_m": <กว้าง เมตร>,\n'
            '  "length_m": <ยาวรวม เมตร>,\n'
            '  "thickness_m": <หนา เมตร>,\n'
            '  "shoulder_width_m": <ไหล่ทาง เมตร>,\n'
            '  "subbase_thickness_m": <ชั้นรองพื้น เมตร>,\n'
            '  "concrete_grade": "240 | 250 | 280 | 300 | unknown",\n'
            '  "dowel_bar": {"diameter_mm": null, "length_mm": null, "spacing_mm": null},\n'
            '  "tie_bar": {"diameter_mm": null, "length_mm": null},\n'
            '  "wire_mesh": "6x6 | 4x4 | ไม่ใช้ | unknown",\n'
            '  "joint_CJ_count": <จำนวน CJ>,\n'
            '  "joint_EJ_count": <จำนวน EJ>,\n'
            '  "budget_thb": <ราคารวม บาท>,\n'
            '  "construction_duration_days": <ระยะเวลาดำเนินงาน วัน>,\n'
            '  "delivery_period_days": <ระยะเวลาส่งมอบงาน วัน>,\n'
            '  "warranty_period_days": <ระยะเวลาประกันผลงาน วัน — 2ปี=730>,\n'
            '  "required_tests": <"รายการทดสอบที่กำหนด เช่น core test">,\n'
            '  "required_delivery_documents": <"เอกสารส่งมอบ เช่น as-built, ใบรับรองวัสดุ">,\n'
            '  "special_conditions": <"เงื่อนไขพิเศษ เช่น ห้ามทำงานกลางคืน">,\n'
            '  "confidence": "high | medium | low",\n'
            '  "notes": null\n'
            "}\n"
            "ถ้าหาค่าใดไม่พบให้ใส่ null"
        )
    })

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}]
        )
        raw = msg.content[0].text.strip()
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            result = json.loads(m.group(0))
            result["source"] = "boq_vision"
            result["analyzed_at"] = datetime.now().isoformat()
            return result
        return {"error": f"parse JSON ล้มเหลว: {raw[:200]}", "confidence": "low"}
    except Exception as e:
        return {"error": str(e), "confidence": "low"}


def _rename_tor_file(tor_path: Path, job_info: dict) -> Path:
    """เปลี่ยนชื่อ tor.pdf → YYYY-MM-DD-<job_id>-<title>.pdf หลัง analyze แล้ว"""
    job_id = str(job_info.get("job_id", "") or job_info.get("job_id", ""))
    title  = str(job_info.get("title", ""))

    # sanitize title: เอาเฉพาะตัวอักษร ตัวเลข ไทย ช่องว่าง
    safe_title = re.sub(r'[\\/:*?"<>|]', "", title).strip()
    safe_title = safe_title[:60]  # จำกัดความยาว

    date_str = datetime.now().strftime("%Y-%m-%d")
    new_name = f"{date_str}-{job_id}-{safe_title}{tor_path.suffix}"
    new_path = tor_path.parent / new_name

    try:
        tor_path.rename(new_path)
        return new_path
    except Exception:
        return tor_path


def analyze_job_tor(job_dir: str | Path, job_info: dict = None) -> dict:
    """
    อ่าน TOR จาก folder ของงาน
    1. หา tor.pdf / tor.xlsx ก่อน
    2. Fallback: Claude Vision บน pB1/pB2/pB3.pdf จาก BOQ zip
    หลัง analyze เสร็จจะ rename tor.pdf → YYYY-MM-DD-<job_id>-<title>.pdf
    """
    job_dir = Path(job_dir)

    # ใช้ cached result ถ้ามีอยู่แล้ว
    cached = job_dir / "tor_result.json"
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass

    # หา tor.pdf / tor.xlsx
    tor_path = None
    for ext in (".pdf", ".xlsx", ".xls"):
        p = job_dir / f"tor{ext}"
        if p.exists():
            tor_path = p
            break

    # Fallback: หาไฟล์ที่ rename แล้ว (ชื่อขึ้นต้นด้วย YYYY-MM-DD-<job_id>)
    if tor_path is None and job_info:
        job_id = str(job_info.get("job_id", ""))
        for p in job_dir.glob(f"????-??-??-{job_id}-*.pdf"):
            tor_path = p
            break

    if tor_path is not None:
        result = analyze_tor(tor_path, job_info)
        if job_info and not result.get("error") and tor_path.name == "tor.pdf":
            new_path = _rename_tor_file(tor_path, job_info)
            result["source_file"] = str(new_path)
        # บันทึก cache
        cached.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    # Fallback: BOQ PDFs via Vision
    result = analyze_job_tor_vision(job_dir, job_info)
    if not result.get("error"):
        cached.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Sebastian_TOR_Analyzer.py <tor_pdf_path> [job_title]")
        sys.exit(1)

    job = {"title": sys.argv[2]} if len(sys.argv) > 2 else {}
    result = analyze_tor(sys.argv[1], job)
    print(json.dumps(result, ensure_ascii=False, indent=2))
