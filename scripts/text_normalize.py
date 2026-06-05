"""text_normalize.py — normalize ชื่องานก่อสร้าง ก่อน match keyword (classifier + matcher).
แก้ Unicode เพี้ยนจาก data ภาครัฐ (ยืนยันจาก winner_history 617K):
  - "นํ้า" (น + ํ U+0E4D + ้ U+0E49 + า) → "น้ำ" (น + ้ + ำ U+0E33)  [7% ของ UNKNOWN]
  - ค.ส.ล. / ค.ส.ล / คสล. → คสล
  - ยุบ whitespace ซ้ำ + strip
pure function ไม่มี side effect. ดู spec 2026-06-05-construction-vocab-design.md
"""
import re
import unicodedata

# ค.ส.ล. / ค.ส.ล / คสล. / คสล → คสล  (จุด optional ทุกตำแหน่ง)
_CSL = re.compile(r"ค\.?ส\.?ล\.?")
_WS = re.compile(r"\s+")


def normalize_thai(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFC", s)
    s = s.replace("ํ้า", "้ำ")  # ํ้า → ้ำ (กู้ น้ำ เพี้ยน)
    s = _CSL.sub("คสล", s)
    s = _WS.sub(" ", s).strip()
    return s
