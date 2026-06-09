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


import requests
import process5_http_client as p

PASSKEY = "0b3464ada27f4a3baaf863dc3e68f8b9"
APIKEY_UUID = "0b3464ad-a27f-4a3b-aaf8-63dc3e68f8b9"
MERCHANT_GENPRICE = "https://process5.gprocurement.go.th/egp-merchant-ebidding-service/common/genReportPrice"
VIEWPDF = "https://process5.gprocurement.go.th/egp-template-service/FileViewer/viewPdf"
TIMEOUT = 25


def _hdr(token):
    h = p.HEADERS_NO_AUTH.copy()
    h["X-Announcement-Token"] = token
    return h


def _has_price_announcement(pid: str, token: str, method_id: str) -> bool:
    """gate: greenBook list มี announceType 'price' ไหม (สรุปราคาเปิดเผยแล้ว)."""
    try:
        b = p._get(f"{p.API_BASE}/greenBook",
                   {"mode": "LINK", "methodId": method_id, "tempProjectId": pid, "pageAnnounceType": "B0"},
                   token=token)
        docs = ((b or {}).get("data") or {}).get("greenBookAnnouncementTypeLinkDto") or []
        return any((d.get("announceType") == "price") for d in docs)
    except Exception:
        return False


def fetch_prelim_summary(pid: str, method_id: str = "16") -> dict:
    """ดึงสรุปราคาเบื้องต้น (pure-API). คืน {"has_summary", + ฟิลด์จาก parse}. graceful."""
    base = {"has_summary": False, "has_price": False, "lowest_price": None,
            "num_bidders": None, "revealed_at": None}
    try:
        token = p._get_token(pid)
        if not token or not _has_price_announcement(pid, token, method_id):
            return base
        h = _hdr(token)
        enc_pid = requests.get(f"{p.API_BASE}/encryptApiKey",
                               params={"passKey": PASSKEY, "sDataValue": pid}, headers=h, timeout=TIMEOUT).json().get("data")
        enc_api = requests.get(f"{p.API_BASE}/encryptApiKey",
                               params={"passKey": PASSKEY, "sDataValue": APIKEY_UUID}, headers=h, timeout=TIMEOUT).json().get("data")
        if not enc_pid or not enc_api:
            return base
        uuid = requests.get(MERCHANT_GENPRICE, params={"projectId": enc_pid, "apiKey": enc_api},
                            headers=h, timeout=TIMEOUT).json().get("data")
        if not uuid:
            return base
        import base64
        b64 = requests.post(f"{VIEWPDF}/{uuid}", json={}, headers=h, timeout=TIMEOUT).json().get("data")
        if not b64:
            return base
        parsed = parse_prelim_pdf(base64.b64decode(b64))
        parsed["has_summary"] = True
        return parsed
    except Exception as e:
        print(f"[prelim] fetch error {pid}: {type(e).__name__}: {e}", file=sys.stderr)
        return base
