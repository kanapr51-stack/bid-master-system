"""customer_keywords.py — แกะ personal keyword list จาก customers.notes (classes[].keywords).

Single source ให้ทั้ง LINE enqueue gate (Sebastian_Customer_DB.enqueue_notifications) และ
board discovery (discovery_match) ใช้ตัวเดียวกัน — เดิมสองระบบแกะเองคนละที่คนละ policy
ว่างเปล่า (N+198 vs การใช้งานจริง) ทำให้ผลไม่ตรงกัน (N+206 แก้).
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
