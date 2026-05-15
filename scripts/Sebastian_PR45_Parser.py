"""
Sebastian_PR45_Parser.py — อ่านเอกสาร ปร.4 และ ปร.5 → JSON

ปร.4 = แบบแสดงรายการก่อสร้าง (BOQ — Bill of Quantities)
ปร.5 = แบบสรุปราคากลางงานก่อสร้าง (Price Summary)

รองรับ: PDF (.pdf) และ Excel (.xlsx, .xls)
- PDF ที่มี text layer: อ่านด้วย pymupdf
- PDF ที่เป็นภาพสแกน: อ่านด้วย Claude Vision (ANTHROPIC_API_KEY ต้องถูก set)
"""

import sys
import re
import json
import base64
import os
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

try:
    import fitz  # pymupdf
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("[warn] pymupdf ไม่ได้ติดตั้ง — ไม่สามารถอ่าน PDF", file=sys.stderr)

try:
    import openpyxl
    EXCEL_SUPPORT = True
except ImportError:
    EXCEL_SUPPORT = False
    print("[warn] openpyxl ไม่ได้ติดตั้ง — ไม่สามารถอ่าน Excel", file=sys.stderr)


# ================================================================
# TEXT EXTRACTION
# ================================================================

def extract_text_pdf(path: Path) -> str:
    if not PDF_SUPPORT:
        return ""
    doc = fitz.open(str(path))
    return "\n".join(page.get_text() for page in doc)


def extract_text_excel(path: Path) -> str:
    if not EXCEL_SUPPORT:
        return ""
    wb = openpyxl.load_workbook(str(path), data_only=True)
    lines = []
    for ws in wb.worksheets:
        lines.append(f"[Sheet: {ws.title}]")
        for row in ws.iter_rows(values_only=True):
            cells = [str(v).strip() for v in row if v is not None]
            if cells:
                lines.append("\t".join(cells))
    return "\n".join(lines)


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_pdf(path)
    elif ext in (".xlsx", ".xls"):
        return extract_text_excel(path)
    return ""


def pdf_is_image_based(path: Path) -> bool:
    """ตรวจว่า PDF เป็นภาพสแกน (ไม่มี text layer)"""
    if not PDF_SUPPORT:
        return False
    doc = fitz.open(str(path))
    for page in doc:
        blocks = page.get_text("blocks")
        if blocks:
            return False
    return True


# ================================================================
# CLAUDE VISION PARSER
# ================================================================

def pdf_to_images_b64(path: Path, max_pages: int = 4) -> list[str]:
    """แปลง PDF pages เป็น PNG base64 strings"""
    if not PDF_SUPPORT:
        return []
    images = []
    doc = fitz.open(str(path))
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        mat = fitz.Matrix(2.0, 2.0)  # zoom 2x เพื่อความชัด
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        images.append(base64.standard_b64encode(img_bytes).decode())
    return images


def parse_pr5_vision(path: Path) -> dict:
    """อ่าน ปร.5 จาก image-based PDF ด้วย Claude Vision"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY ไม่ได้ set", "doc_type": "error"}

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package ไม่ได้ติดตั้ง: pip install anthropic", "doc_type": "error"}

    images = pdf_to_images_b64(path, max_pages=4)
    if not images:
        return {"error": "แปลง PDF เป็นภาพไม่ได้", "doc_type": "error"}

    content = []
    for img_b64 in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64}
        })

    content.append({
        "type": "text",
        "text": (
            "นี่คือเอกสาร ปร.5 (แบบสรุปราคากลางงานก่อสร้าง) ของไทย\n"
            "กรุณาดึงข้อมูลต่อไปนี้และตอบเป็น JSON เท่านั้น ไม่ต้องอธิบายเพิ่ม:\n"
            "{\n"
            '  "direct_cost": <ค่าใช้จ่ายโดยตรง เป็นตัวเลข>,\n'
            '  "overhead_pct": <ค่าใช้จ่ายส่วนกลาง % เป็นตัวเลข>,\n'
            '  "profit_pct": <กำไร % เป็นตัวเลข>,\n'
            '  "total_before_vat": <รวมก่อน VAT เป็นตัวเลข>,\n'
            '  "vat_pct": <VAT % เป็นตัวเลข ปกติ 7>,\n'
            '  "total_price": <รวมทั้งสิ้น เป็นตัวเลข>,\n'
            '  "budget_price": <ราคากลาง เป็นตัวเลข>\n'
            "}\n"
            "ถ้าหาค่าใดไม่พบให้ใส่ null"
        )
    })

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}]
    )

    text = msg.content[0].text.strip()

    # Extract JSON block
    m = re.search(r'\{[\s\S]+?\}', text)
    if m:
        try:
            data = json.loads(m.group())
            data["doc_type"] = "pr5"
            data["source"] = "claude_vision"
            # ถ้าไม่พบ budget_price ใช้ total_price แทน
            if data.get("budget_price") is None:
                data["budget_price"] = data.get("total_price")
            return data
        except Exception:
            pass

    return {
        "error": f"parse JSON ล้มเหลว: {text[:300]}",
        "doc_type": "pr5",
        "source": "claude_vision",
        "raw_response": text,
    }


def parse_pr4_vision(path: Path) -> dict:
    """อ่าน ปร.4 จาก image-based PDF ด้วย Claude Vision"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY ไม่ได้ set", "doc_type": "error"}

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package ไม่ได้ติดตั้ง", "doc_type": "error"}

    images = pdf_to_images_b64(path, max_pages=6)
    if not images:
        return {"error": "แปลง PDF เป็นภาพไม่ได้", "doc_type": "error"}

    content = []
    for img_b64 in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64}
        })

    content.append({
        "type": "text",
        "text": (
            "นี่คือเอกสาร ปร.4 (แบบแสดงรายการก่อสร้าง/BOQ) ของไทย\n"
            "กรุณาดึงรายการงานทั้งหมดและตอบเป็น JSON เท่านั้น:\n"
            "{\n"
            '  "items": [\n'
            '    {"no": "...", "description": "...", "unit": "...", "quantity": ..., "unit_price": ..., "total": ...},\n'
            "    ...\n"
            "  ],\n"
            '  "total_price": <รวมทั้งสิ้น>\n'
            "}\n"
            "ถ้าหาค่าใดไม่พบให้ใส่ null"
        )
    })

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}]
    )

    text = msg.content[0].text.strip()

    m = re.search(r'\{[\s\S]+\}', text)
    if m:
        try:
            data = json.loads(m.group())
            items = data.get("items", [])
            data["doc_type"] = "pr4"
            data["item_count"] = len(items)
            data["source"] = "claude_vision"
            if data.get("total_price") is None:
                data["total_price"] = sum(
                    i.get("total") or 0 for i in items if i.get("total") is not None
                )
            return data
        except Exception:
            pass

    return {
        "error": f"parse JSON ล้มเหลว: {text[:300]}",
        "doc_type": "pr4",
        "source": "claude_vision",
        "items": [],
        "item_count": 0,
        "total_price": None,
    }


# ================================================================
# DOC TYPE DETECTION
# ================================================================

def detect_doc_type(path: Path, text: str) -> str:
    """ตรวจว่าไฟล์คือ ปร.4 หรือ ปร.5"""
    name = path.stem.lower()
    head = text[:500]

    if any(x in name for x in ["pr4", "ปร4", "bor4", "pb4"]):
        return "pr4"
    if any(x in name for x in ["pr5", "ปร5", "bor5", "pb3"]):
        return "pr5"

    if "ปร.4" in head or "แบบแสดงรายการ" in head or "ปริมาณงาน" in head[:200]:
        return "pr4"
    if "ปร.5" in head or "สรุปราคากลาง" in head or "ราคารวมทั้งสิ้น" in head:
        return "pr5"

    parent = path.parent.name.lower()
    if "pr4" in parent:
        return "pr4"
    if "pr5" in parent:
        return "pr5"

    return "unknown"


# ================================================================
# ปร.4 PARSER (text-based)
# ================================================================

UNITS = {
    "ม.", "ม.²", "ม.³", "ตร.ม", "ลบ.ม", "กก.", "ตัน", "คัน", "ชุด",
    "ก้อน", "แผ่น", "ถัง", "ลิตร", "เมตร", "m", "m2", "m3", "kg", "ton",
}


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "").strip())
    except Exception:
        return None


def parse_pr4(text: str) -> dict:
    """แยกรายการงานจาก ปร.4 text"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    items = []
    current = None
    num_pat = re.compile(r'^(\d+(?:\.\d+)?)\s{1,4}(.{3,})')

    for line in lines:
        if any(h in line for h in ["รายการ", "หมายเลข", "ลำดับ", "ราคา/หน่วย", "รวมเงิน"]):
            if current:
                items.append(current)
                current = None
            continue

        m = num_pat.match(line)
        if m:
            if current:
                items.append(current)
            current = {
                "no": m.group(1),
                "description": m.group(2).strip(),
                "unit": "",
                "quantity": None,
                "unit_price": None,
                "total": None,
            }
            nums = re.findall(r'[\d,]+(?:\.\d+)?', line)
            if len(nums) >= 3:
                current["quantity"]   = _to_float(nums[-3])
                current["unit_price"] = _to_float(nums[-2])
                current["total"]      = _to_float(nums[-1])
            elif len(nums) == 1:
                current["quantity"] = _to_float(nums[0])
        elif current:
            nums = re.findall(r'[\d,]+(?:\.\d+)?', line)
            if len(nums) >= 3 and current["total"] is None:
                current["quantity"]   = _to_float(nums[-3])
                current["unit_price"] = _to_float(nums[-2])
                current["total"]      = _to_float(nums[-1])
            for unit in UNITS:
                if unit in line:
                    current["unit"] = unit
                    break
            if len(line) > 5 and not re.match(r'^[\d,.\s]+$', line):
                if len(current["description"]) < 200:
                    current["description"] += " " + line

    if current:
        items.append(current)

    total = sum(i["total"] for i in items if i["total"] is not None)
    return {"doc_type": "pr4", "items": items, "item_count": len(items), "total_price": total}


# ================================================================
# ปร.5 PARSER (text-based)
# ================================================================

def parse_pr5(text: str) -> dict:
    """ดึง summary ราคากลางจาก ปร.5 text"""
    result = {
        "doc_type": "pr5",
        "direct_cost": None,
        "overhead_pct": None,
        "profit_pct": None,
        "vat_pct": 7.0,
        "total_before_vat": None,
        "total_price": None,
        "budget_price": None,
    }

    patterns = [
        ("direct_cost",      r'ค่าใช้จ่ายโดยตรง[^\d]*([\d,]+(?:\.\d+)?)'),
        ("direct_cost",      r'Direct\s*Cost[^\d]*([\d,]+(?:\.\d+)?)'),
        ("overhead_pct",     r'ค่าใช้จ่ายส่วนกลาง.*?([\d.]+)\s*(?:%|เปอร์)'),
        ("overhead_pct",     r'Overhead.*?([\d.]+)\s*%'),
        ("profit_pct",       r'กำไร.*?([\d.]+)\s*(?:%|เปอร์)'),
        ("profit_pct",       r'Profit.*?([\d.]+)\s*%'),
        ("total_price",      r'รวมทั้งสิ้น[^\d]*([\d,]+(?:\.\d+)?)'),
        ("total_price",      r'Total.*?([\d,]+(?:\.\d+)?)'),
        ("budget_price",     r'ราคากลาง[^\d]*([\d,]+(?:\.\d+)?)'),
    ]

    for key, pat in patterns:
        if result[key] is not None:
            continue
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _to_float(m.group(1))
            if val:
                result[key] = val

    if result["budget_price"] is None:
        result["budget_price"] = result["total_price"]

    return result


# ================================================================
# MAIN ENTRY
# ================================================================

def parse_pr45(file_path: str | Path) -> dict:
    """
    Main entry point.
    1. ลอง text extraction ก่อน
    2. ถ้า PDF เป็นภาพสแกน → ใช้ Claude Vision
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"ไม่พบไฟล์: {path}", "doc_type": "error"}

    text = extract_text(path)
    is_image_pdf = path.suffix.lower() == ".pdf" and not text.strip()

    if is_image_pdf:
        # PDF สแกน — ต้องใช้ Vision
        doc_type = detect_doc_type(path, "")
        if doc_type == "pr4":
            result = parse_pr4_vision(path)
        else:
            # default to pr5 สำหรับ pB3.pdf จาก BOQ zip
            result = parse_pr5_vision(path)
    else:
        doc_type = detect_doc_type(path, text)
        if doc_type == "pr4":
            result = parse_pr4(text)
        elif doc_type == "pr5":
            result = parse_pr5(text)
        else:
            r4 = parse_pr4(text)
            r5 = parse_pr5(text)
            result = r4 if r4["item_count"] > 0 else r5
            result["doc_type_guessed"] = True

    result["source_file"] = str(path)
    return result


def parse_job_docs(job_dir: str | Path) -> dict:
    """
    อ่านเอกสารทั้งหมดจาก folder ของงานหนึ่ง
    คืนค่า {"pr4": {...}, "pr5": {...}}
    """
    job_dir = Path(job_dir)
    results = {}

    for doc_type in ("pr4", "pr5"):
        for ext in (".pdf", ".xlsx", ".xls"):
            path = job_dir / f"{doc_type}{ext}"
            if path.exists():
                results[doc_type] = parse_pr45(path)
                break

    # รองรับ pB3.pdf จาก BOQ zip (ถูก save เป็น pr5 โดย downloader)
    if "pr5" not in results:
        pb3 = job_dir / "pB3.pdf"
        if pb3.exists():
            results["pr5"] = parse_pr45(pb3)

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Sebastian_PR45_Parser.py <file_path_or_job_dir>")
        sys.exit(1)

    target = Path(sys.argv[1])
    if target.is_dir():
        result = parse_job_docs(target)
    else:
        result = parse_pr45(target)

    print(json.dumps(result, ensure_ascii=False, indent=2))
