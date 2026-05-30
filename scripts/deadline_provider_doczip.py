"""
deadline_provider_doczip.py — DocZipPdfDeadlineProvider (Tier B-2 SUCCESS, 2026-05-30)

Resolver path (พิสูจน์ end-to-end — pure process5 API, ไม่ต้อง browser/process3):
  1. GET  egp-approval-service/apv-common/infoProcureDocAnnounZip?projectId=X
         → data.buildName2 = templateId (UUID)
  2. POST egp-template-service/dant/view-pdf?templateId=<tid> {}
         → JSON {data: base64(PDF)}
  3. base64 decode → pdfplumber → regex (keyword + Thai/numeric date) → deadline (BE→CE)

token: AES generateToken (p._get_token, server-side mint, ไม่ติด Turnstile) → รัน VPS ได้
parser: reuse logic จาก patch_deadlines (inline = self-contained, เลี่ยง sheets_client dependency)
staged outcome (Caveat 2): NO_DOCUMENT / DOWNLOAD_FAILED / PARSE_FAILED / DEADLINE_NOT_FOUND / RESOLVED
"""
import os
import sys
import io
import re
import time
import base64
from datetime import date
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
import process5_http_client as p
from deadline_service import IDeadlineProvider, DeadlineResult, DeadlineOutcome

INFO_URL = "https://process5.gprocurement.go.th/egp-approval-service/apv-common/infoProcureDocAnnounZip"
VIEWPDF_URL = "https://process5.gprocurement.go.th/egp-template-service/dant/view-pdf"
TIMEOUT = 30

_THAI_MONTH = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_THAI_DATE_RE = re.compile(r"(\d{1,2})\s+(" + "|".join(_THAI_MONTH.keys()) + r")\s+(\d{4})")
_NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b")
_DEADLINE_KEYWORDS = [
    "ยื่นข้อเสนอ", "กำหนดยื่น", "เสนอราคา", "ยื่นซอง",
    "ปิดรับซอง", "สิ้นสุดรับซอง", "ปิดรับการเสนอราคา", "กำหนดส่ง",
]


def _be_to_ce(year: int) -> int:
    return year - 543 if year > 2400 else year


def parse_deadline_from_pdf(pdf_bytes: bytes) -> Tuple[Optional[date], str]:
    """คืน (date|None, stage). stage: 'ok' | 'no_text' | 'no_date' | 'pdf_error'"""
    try:
        import pdfplumber
    except Exception:
        return None, "pdf_error"
    got_text = False
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for pg in pdf.pages:
                text = (pg.extract_text() or "").translate(_THAI_DIGITS)
                if text.strip():
                    got_text = True
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if any(kw in line for kw in _DEADLINE_KEYWORDS):
                        block = "\n".join(lines[i:i + 4])
                        m = _NUMERIC_DATE_RE.search(block)
                        if m:
                            d, mo, y = int(m.group(1)), int(m.group(2)), _be_to_ce(int(m.group(3)))
                            try:
                                return date(y, mo, d), "ok"
                            except ValueError:
                                continue
                        m2 = _THAI_DATE_RE.search(block)
                        if m2:
                            d = int(m2.group(1)); mo = _THAI_MONTH[m2.group(2)]; y = _be_to_ce(int(m2.group(3)))
                            try:
                                return date(y, mo, d), "ok"
                            except ValueError:
                                continue
    except Exception:
        return None, "pdf_error"
    return None, ("no_date" if got_text else "no_text")


class DocZipPdfDeadlineProvider(IDeadlineProvider):
    name = "doczip"

    def _hdrs(self, token: str) -> dict:
        h = p.HEADERS_NO_AUTH.copy()
        h["X-Announcement-Token"] = token
        return h

    def resolve(self, project_id: str, **ctx) -> DeadlineResult:
        t0 = time.time()
        def done(outcome, deadline=None, tid=None, err=None):
            return DeadlineResult(project_id, outcome, deadline=deadline, provider=self.name,
                                  latency_ms=int((time.time() - t0) * 1000),
                                  source_doc=tid, error=err)
        try:
            token = p._get_token(project_id)
            if not token:
                return done(DeadlineOutcome.PROVIDER_ERROR, err="no AES token")
            # 1) projectId → templateId
            r = requests.get(INFO_URL, params={"projectId": project_id},
                             headers=self._hdrs(token), timeout=TIMEOUT)
            if "rate limit" in (r.text or "").lower():
                return done(DeadlineOutcome.PROVIDER_ERROR, err="rate_limited")
            data = (r.json().get("data") or {}) if r.ok else {}
            tid = data.get("buildName2")
            if not tid:
                return done(DeadlineOutcome.NO_DOCUMENT, err="no buildName2 (templateId)")
            # 2) templateId → PDF (base64 ใน JSON.data)
            rp = requests.post(VIEWPDF_URL, params={"templateId": tid}, json={},
                               headers=self._hdrs(token), timeout=TIMEOUT)
            if not rp.ok:
                return done(DeadlineOutcome.DOWNLOAD_FAILED, tid=tid, err=f"http_{rp.status_code}")
            b64 = (rp.json().get("data") or "")
            if not b64:
                return done(DeadlineOutcome.DOWNLOAD_FAILED, tid=tid, err="no pdf data")
            try:
                pdf_bytes = base64.b64decode(b64)
            except Exception:
                return done(DeadlineOutcome.DOWNLOAD_FAILED, tid=tid, err="base64 decode fail")
            # 3) PDF → deadline
            dl, stage = parse_deadline_from_pdf(pdf_bytes)
            if dl is not None:
                return done(DeadlineOutcome.RESOLVED, deadline=dl, tid=tid)
            if stage in ("no_text", "pdf_error"):
                return done(DeadlineOutcome.PARSE_FAILED, tid=tid, err=stage)
            return done(DeadlineOutcome.DEADLINE_NOT_FOUND, tid=tid, err="no date near keyword")
        except Exception as e:
            return done(DeadlineOutcome.PROVIDER_ERROR, err=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    import json
    pid = sys.argv[1] if len(sys.argv) > 1 else "69059341206"
    r = DocZipPdfDeadlineProvider().resolve(pid)
    print(json.dumps({
        "project_id": r.project_id, "outcome": r.outcome.value, "success": r.success,
        "deadline": r.deadline.isoformat() if r.deadline else None,
        "is_open": r.is_open() if r.success else None,
        "source_doc": r.source_doc, "latency_ms": r.latency_ms, "error": r.error,
    }, ensure_ascii=False, indent=2))
