"""work_type_classifier.py — จัดหมวดงานก่อสร้างจากชื่องาน (rule-based, pure functions).
ดู design: docs/superpowers/specs/2026-06-04-work-type-classifier-design.md

classify_work_type(title) -> {"primary", "secondary", "all", "version"}
  primary   = หมวด score สูงสุด (tie → priority list → ตำแหน่ง keyword เร็วสุด)
  secondary = หมวด core อื่น score>=1 (เรียงตาม score)
  all       = [primary, *secondary]
  score     = จำนวน keyword "ตัวที่ไม่ซ้ำ" ต่อหมวดที่เจอในชื่อ (distinct, กันคำซ้ำ inflate)

ถัง: OTHER = match other_keywords (ไม่ใช่ core), UNKNOWN = ไม่ match keyword ใดเลย.
guard ภาษาไทย: keyword เสี่ยง substring (ราง/ท่อ) ใช้ regex จาก config['guards'] (INC-002/L-007).
"""
import json
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CFG = json.loads((_ROOT / "config" / "work_type_keywords.json").read_text(encoding="utf-8"))

WORK_TYPE_VERSION = _CFG["version"]
_CATEGORIES = _CFG["categories"]
_OTHER_KW = _CFG["other_keywords"]
_PRIORITY = _CFG["priority"]
_GUARDS = {k: re.compile(v) for k, v in _CFG.get("guards", {}).items()}


def _first_pos(k: str, title: str) -> int:
    """ตำแหน่งแรกที่ keyword โผล่ (เคารพ guard) — ใช้ tie-break ชั้น 3."""
    g = _GUARDS.get(k)
    if g:
        m = g.search(title)
        return m.start() if m else -1
    return title.find(k)


def _hit(k: str, title: str) -> bool:
    g = _GUARDS.get(k)
    return bool(g.search(title)) if g else (k in title)


def classify_work_type(title: str) -> dict:
    title = title or ""

    # 1) score ต่อหมวด = จำนวน keyword distinct ที่ hit
    scores = {}      # cat -> distinct keyword count
    earliest = {}    # cat -> ตำแหน่ง keyword เร็วสุด
    for cat, kws in _CATEGORIES.items():
        hits = [k for k in kws if _hit(k, title)]
        if hits:
            # ยุบ keyword ซ้อน (ส่องสว่าง ⊂ ไฟฟ้าส่องสว่าง) — กัน 1 ช่วงข้อความ inflate score (spec §4)
            distinct = [k for k in hits if not any(k != o and k in o for o in hits)]
            scores[cat] = len(distinct)
            earliest[cat] = min(p for k in distinct if (p := _first_pos(k, title)) >= 0)

    if scores:
        # tie-break: score สูงสุด → ตำแหน่ง keyword เร็วสุด (head-noun = งานหลัก) → priority (fallback)
        # NOTE: position มาก่อน priority (แก้จาก spec §4 เดิม) — validation 617K พิสูจน์ว่า landmark
        # เช่น "สะพาน/โรงเรียน/ประปา" มักโผล่ท้ายชื่อเป็นจุดอ้างอิง งานจริงอยู่ต้นชื่อ (calibrate 2026-06-04)
        def sort_key(cat):
            pri = _PRIORITY.index(cat) if cat in _PRIORITY else len(_PRIORITY)
            return (-scores[cat], earliest[cat], pri)

        ordered = sorted(scores, key=sort_key)
        primary = ordered[0]
        secondary = ordered[1:]
        return {
            "primary": primary,
            "secondary": secondary,
            "all": [primary, *secondary],
            "version": WORK_TYPE_VERSION,
        }

    if any(k in title for k in _OTHER_KW):
        return {"primary": "OTHER", "secondary": [], "all": ["OTHER"], "version": WORK_TYPE_VERSION}

    return {"primary": "UNKNOWN", "secondary": [], "all": ["UNKNOWN"], "version": WORK_TYPE_VERSION}
