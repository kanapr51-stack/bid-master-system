"""cgd_intel.py — competitive intel จาก cgd_winners: ผู้ชนะงานคล้ายในพื้นที่ + ราคา/ส่วนลด.
descriptive เท่านั้น (ตลาดเป็นยังไง) ไม่ prescriptive (ไม่บอกราคาที่ควรยื่น).
ใช้แนบการ์ด D0 (source_stage=followed_bid_open). intel = value-add — ห้ามทำ notification พัง."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_KW_PATH = Path(__file__).parent.parent / "config" / "matching_preferences.json"


def _load_keywords() -> list:
    return json.load(open(_KW_PATH, encoding="utf-8")).get("keywords", [])


def match_keywords(project_name: str, keywords: list = None) -> list:
    """คืน work-type tokens ที่ปรากฏในชื่องาน (vocab เดียวกับ job_matcher). ไม่ซ้ำ."""
    kws = keywords if keywords is not None else _load_keywords()
    name = project_name or ""
    out = []
    for kw in kws:
        if kw and kw in name and kw not in out:
            out.append(kw)
    return out
