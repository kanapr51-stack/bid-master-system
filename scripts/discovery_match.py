"""discovery_match.py — per-user matching สำหรับ section discovery บนบอร์ด.

Pure function: ตัดสินว่า project 1 row match preference ของ user 1 คนไหม + คืนคำที่โดน.
ไม่แตะ DB / ไม่เรียก API. reuse keyword guard จาก job_matcher (ไม่เขียน guard ซ้ำ).
SCOPE: board discovery เท่านั้น — แยกจาก LINE pipeline (job_matcher.match_job ไม่ถูกแตะ).
ดู spec: docs/superpowers/specs/2026-06-30-portal-discovery-design.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_normalize import normalize_thai  # noqa: E402
import job_matcher  # noqa: E402


def match(project_name, project_province, project_budget,
          user_provinces, user_keywords,
          budget_min=0, budget_max=0, neg_keywords=None):
    """คืน (matched: bool, matched_keywords: list[str]).

    - province AND: project_province ต้องอยู่ใน user_provinces
    - negative safety net: ชื่อมี neg_keyword ใด → ไม่ match
    - keyword OR: คำใน user_keywords ที่ _kw_hit(k, ชื่อ normalize) → เก็บใน matched_keywords
      · user_keywords ว่าง = ไม่มีงานแมตช์เลย (N+206 — ต้องตั้ง keyword เองก่อนถึงจะเห็นงาน,
        พลิกกลับ N+198 ที่เคยให้ว่าง=เห็นทั้งจังหวัด)
    - budget: budget>0 + นอกช่วง [budget_min, budget_max] → ตัด (budget=0 = ไม่รู้ → ผ่าน)
    matched = province✓ AND keyword ชน≥1 AND ไม่ติด negative AND อยู่ในช่วงงบ
    """
    name = normalize_thai(project_name or "")
    prov = (project_province or "").strip()

    if prov not in set(user_provinces or []):
        return False, []

    if neg_keywords is None:
        neg_keywords = job_matcher.load_config().get("negative_keywords", [])
    if any(n in name for n in neg_keywords):
        return False, []

    if not (user_keywords or []):
        return False, []
    hits = [k for k in user_keywords if k and job_matcher._kw_hit(k, name)]
    if not hits:
        return False, []

    b = project_budget or 0
    if b > 0:
        if budget_min and b < budget_min:
            return False, []
        if budget_max and b > budget_max:
            return False, []

    return True, hits
