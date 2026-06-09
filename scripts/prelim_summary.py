"""prelim_summary.py — ดึง+parse "สรุปข้อมูลการเสนอราคาเบื้องต้น" (ราคาต่ำสุด early signal).
API chain: ดู docs/research/2026-06-09-prelim-bid-summary-api.md. graceful — ห้ามทำ poller ล่ม."""
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_NUM_RE = re.compile(r"([\d,]+\.\d{2})")
_BIDDERS_RE = re.compile(r"จำนวนผู้เสนอราคา\s*:?\s*(\d+)")
_REVEAL_RE = re.compile(r"เปิดเผย ณ วันที่\s*(\d{1,2})\s*([ก-๙฀-๿]+)\s*(\d{4})\s*เวลา\s*(\d{1,2}:\d{2})")


def parse_prelim_text(text: str) -> dict:
    """parse ข้อความ PDF → {has_price, lowest_price, num_bidders, revealed_at}."""
    t = (text or "").translate(_THAI_DIGITS)
    out = {"has_price": False, "lowest_price": None, "num_bidders": None, "revealed_at": None}
    mb = _BIDDERS_RE.search(t)
    if mb:
        out["num_bidders"] = int(mb.group(1))
    if "ราคาต่ำสุดที่เสนอ" in t and not ("ไม่มีการแสดงข้อมูลราคา" in t):
        for line in t.split("\n"):
            if "รายการพิจารณาที่" in line:
                m = _NUM_RE.search(line)
                if m:
                    out["lowest_price"] = float(m.group(1).replace(",", ""))
                    out["has_price"] = True
                    break
    mr = _REVEAL_RE.search(t)
    if mr:
        out["revealed_at"] = f"{mr.group(1)} {mr.group(2)} {mr.group(3)} {mr.group(4)}"
    return out


def parse_prelim_pdf(pdf_bytes: bytes) -> dict:
    """pdf → text → parse_prelim_text. graceful: error → ฟิลด์ None."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
            for pg in doc.pages:
                text += (pg.extract_text() or "") + "\n"
        return parse_prelim_text(text)
    except Exception:
        return {"has_price": False, "lowest_price": None, "num_bidders": None, "revealed_at": None}
