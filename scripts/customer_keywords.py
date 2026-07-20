"""customer_keywords.py — แกะ personal keyword list จาก customers.notes (classes[].keywords).

Single source ให้ทั้ง board discovery (discovery_match) และ LINE send-time gate
(Sebastian_LINE_Sender.py, N+207) ใช้ตัวเดียวกัน — กันสองระบบแกะเองคนละที่คนละ policy
ว่างเปล่าแล้วผลไม่ตรงกัน.
"""
import json


def keywords_from_notes(notes_str: str) -> list[str]:
    """union keywords + defaultKeywords จากทุก class ใน notes.classes[], unique รักษาลำดับ.
    notes ว่าง/parse ไม่ได้ → []."""
    if not notes_str:
        return []
    try:
        data = json.loads(notes_str)
    except (ValueError, TypeError):
        return []
    kws: list[str] = []
    for cls in (data.get("classes") or []):
        for k in list(cls.get("keywords") or []) + list(cls.get("defaultKeywords") or []):
            k = (k or "").strip()
            if k and k not in kws:
                kws.append(k)
    return kws


def should_notify(source_stage: str, project_name: str, notes_str: str) -> bool:
    """N+207: ตัดสินว่าควรแจ้งเตือนจริง (LINE/web push) ไหม สำหรับ 1 แถว notification_queue.

    - source_stage ขึ้นต้นด้วย 'followed_' (followed_winner/prelim/cancelled/bid_open) =
      ลูกค้ากดติดตามงานนี้เองแล้ว (opt-in) → แจ้งเสมอ ไม่กรอง
    - ไม่ตั้ง personal keyword (notes.classes[].keywords ว่าง) → แจ้งทุกงาน (ค่า default)
    - ตั้ง personal keyword แล้ว → แจ้งเฉพาะงานที่ชื่อตรงคำใดคำหนึ่ง (งานที่ไม่ตรงยัง enqueue
      อยู่ให้บอร์ด "งานทั้งหมด" เห็น แค่ไม่ยิงแจ้งเตือน — ดู Sebastian_Customer_DB.mark_keyword_skip)
    """
    if (source_stage or "").startswith("followed_"):
        return True
    kws = keywords_from_notes(notes_str)
    if not kws:
        return True
    import job_matcher
    from text_normalize import normalize_thai
    name = normalize_thai(project_name or "")
    return any(job_matcher._kw_hit(k, name) for k in kws if k)
