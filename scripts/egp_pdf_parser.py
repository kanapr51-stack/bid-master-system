"""
egp_pdf_parser.py — Extract structured fields from eGP announcement PDFs

Source: process5.gprocurement.go.th/egp-template-service/dwnt/view-pdf-file?templateId=X

Extracts:
  - bid_submit_date  (วันยื่นข้อเสนอ — most important!)
  - bid_submit_time  (เวลายื่น 13.00-16.00)
  - eb_number        (เลขที่ EB ซ.32/2569)
  - announce_date    (ประกาศ ณ วันที่)
  - doc_price        (ค่าซื้อเอกสาร — บาท)
  - doc_buy_start    (วันเริ่มซื้อเอกสาร)
  - doc_buy_end      (วันสิ้นสุดซื้อเอกสาร)
"""
import re
import io
from datetime import datetime
from typing import Optional

try:
    import pdfplumber
    _pdf_available = True
except ImportError:
    _pdf_available = False


THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
THAI_MONTHS = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}


def thai_to_arabic(s: str) -> str:
    """แปลงเลขไทย ๐-๙ → 0-9"""
    return s.translate(THAI_DIGITS) if s else s


def parse_thai_date(text: str) -> Optional[str]:
    """
    'วันที่ ๘ มิถุนายน ๒๕๖๙' → '2026-06-08'
    'วันที่ ๒๗ พฤษภาคม พ.ศ. ๒๕๖๙' → '2026-05-27'
    'วันที่ ๙ มิถุนายน ๒๕๖๙' → '2026-06-09'
    """
    if not text:
        return None
    s = thai_to_arabic(text)
    # match "วันที่ DD MONTH [พ.ศ.] YYYY"
    m = re.search(r"(\d{1,2})\s+(\S+)\s+(?:พ\.ศ\.\s+)?(\d{4})", s)
    if not m:
        return None
    day, month_th, year = m.group(1), m.group(2), m.group(3)
    month = THAI_MONTHS.get(month_th)
    if not month:
        return None
    year_int = int(year)
    if year_int > 2500:  # Buddhist era → AD
        year_int -= 543
    try:
        return f"{year_int:04d}-{month:02d}-{int(day):02d}"
    except ValueError:
        return None


def parse_announcement_pdf(pdf_bytes: bytes) -> dict:
    """
    Parse eGP announcement PDF → structured fields.

    Returns dict (all keys may be None if not found):
      bid_submit_date, bid_submit_time, eb_number, announce_date,
      doc_price, doc_buy_start, doc_buy_end, raw_text (first 500 chars)
    """
    if not _pdf_available:
        return {"error": "pdfplumber not installed"}

    if not pdf_bytes or len(pdf_bytes) < 100:
        return {"error": "empty or invalid pdf"}

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:
        return {"error": f"pdf parse failed: {e}"}

    result = {
        "bid_submit_date":  None,
        "bid_submit_time":  None,
        "eb_number":        None,
        "announce_date":    None,
        "doc_price":        None,
        "doc_buy_start":    None,
        "doc_buy_end":      None,
    }

    # bid_submit_date + time — "ในวันที่ ๘ มิถุนายน ๒๕๖๙ ระหว่างเวลา ๑๓.๐๐ น. ถึง ๑๖.๐๐ น."
    m = re.search(
        r"ในวันที่\s+(\d{1,2}|[๐-๙]{1,2})\s+(\S+)\s+(\d{4}|[๐-๙]{4})\s*"
        r"ระหว่างเวลา\s+([\d๐-๙\.]+)\s*น?\.?\s*ถึง\s*([\d๐-๙\.]+)\s*น?",
        text)
    if m:
        date_part = f"วันที่ {m.group(1)} {m.group(2)} {m.group(3)}"
        result["bid_submit_date"] = parse_thai_date(date_part)
        t_start = thai_to_arabic(m.group(4))
        t_end   = thai_to_arabic(m.group(5))
        result["bid_submit_time"] = f"{t_start}-{t_end} น."

    # eb_number — "เลขที่ EB ซ.๓๒/๒๕๖๙" or "เลขที่ จ.๔๕/๒๕๖๙"
    # Try EB X/Y pattern (flexible: EB ซ.32/2569, EB จ.45/2569, ตามที่เห็นจริง)
    for pat in [
        r"เลขที่\s+(EB\s*\S{1,5}\.?\s*[\d๐-๙]+/[\d๐-๙]+)",
        r"เอกสารประกวดราคา\S*เลขที่\s+([\d๐-๙]+/[\d๐-๙]+)",
        r"เลขที่\s+([\d๐-๙]+/[\d๐-๙]+)",
    ]:
        m = re.search(pat, text)
        if m:
            result["eb_number"] = thai_to_arabic(m.group(1)).strip()
            break

    # announce_date — "ประกาศ ณ วันที่ ๒๗ พฤษภาคม พ.ศ. ๒๕๖๙"
    m = re.search(r"ประกาศ\s+ณ\s+วันที่\s+(\d{1,2}|[๐-๙]{1,2})\s+(\S+)\s+(?:พ\.ศ\.\s+)?(\d{4}|[๐-๙]{4})", text)
    if m:
        date_part = f"วันที่ {m.group(1)} {m.group(2)} {m.group(3)}"
        result["announce_date"] = parse_thai_date(date_part)

    # doc_price — "ในราคาชุดละ ๕๐๐.๐๐ บาท"
    m = re.search(r"ในราคาชุดละ\s+([\d๐-๙,\.]+)\s+บาท", text)
    if m:
        try:
            price_str = thai_to_arabic(m.group(1)).replace(",", "")
            result["doc_price"] = float(price_str)
        except ValueError:
            pass

    # doc_buy_start + end — "ตั้งแต่วันที่ ๙ มิถุนายน ๒๕๖๙ ถึงวันที่ ๑๕ มิถุนายน ๒๕๖๙"
    m = re.search(
        r"ตั้งแต่วันที่\s+(\d{1,2}|[๐-๙]{1,2})\s+(\S+)\s+(\d{4}|[๐-๙]{4})\s+"
        r"ถึงวันที่\s+(\d{1,2}|[๐-๙]{1,2})\s+(\S+)\s+(\d{4}|[๐-๙]{4})",
        text)
    if m:
        start = f"วันที่ {m.group(1)} {m.group(2)} {m.group(3)}"
        end   = f"วันที่ {m.group(4)} {m.group(5)} {m.group(6)}"
        result["doc_buy_start"] = parse_thai_date(start)
        result["doc_buy_end"]   = parse_thai_date(end)

    return result


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    with open("data/announcement_sample.pdf", "rb") as f:
        pdf_bytes = f.read()
    result = parse_announcement_pdf(pdf_bytes)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
