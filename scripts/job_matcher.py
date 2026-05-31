"""
job_matcher.py — กรองงานตาม preference (keyword + tambon) — Step 2 matching (2026-05-31)

อ่าน config/matching_preferences.json → ตัดสิน 3 ทาง: send / cut / soft_include
ดู design: memory/project_matching_design.md

decision:
  send         = keyword ✓ + ตำบล ∈ เป้าหมาย (รู้พื้นที่ชัด)
  cut          = ไม่มี keyword | จังหวัดไม่ subscribe | ตำบลรู้แต่ ∉ เป้าหมาย
  soft_include = keyword ✓ + จังหวัดตรง + ระบุตำบลไม่ได้ (งานถนน) → ส่ง+ป้าย "⚠️ พื้นที่ไม่ชัด · ถนนสาย <code>"

location resolution (caller อาจ resolve field→name→PDF แล้วส่ง tambon มา):
  field (moiName) → ถ้ามี (target/non-target ตัดสินได้เลย)
  ถ้า field ว่าง → เช็คชื่องานมี target tambon ไหม (substring — reliable per experiment)
  ถ้ายังไม่เจอ → soft_include
location_source เก็บไว้ audit (field/name/unknown) — กัน silent wrong-location
"""
import os
import re
import json
from typing import Tuple

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "matching_preferences.json")

# รหัสถนน: บก./นพ. + เลข 3-4 หลัก (ไทย/อารบิก) เช่น "นพ.4036", "บก ๓๐๙"
_ROAD_CODE_RE = re.compile(r"(?:บก|นพ)\.?\s?[๐-๙\d]{3,4}")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm_tambon(s: str) -> str:
    s = (s or "").strip()
    for p in ("ตำบล", "ต.", "ต "):
        if s.startswith(p):
            return s[len(p):].strip()
    return s


def extract_road_code(name: str) -> str:
    m = _ROAD_CODE_RE.search(name or "")
    return m.group(0).strip() if m else ""


def tambon_from_dept(dept_name: str) -> str:
    """ตำบลจากชื่อหน่วยงานท้องถิ่น (ฟรี) — อบต./เทศบาลตำบล"""
    d = dept_name or ""
    for pat in ("องค์การบริหารส่วนตำบล", "เทศบาลตำบล"):
        if pat in d:
            return d.split(pat)[-1].strip()
    return ""


def tambon_from_api(project_id: str) -> str:
    """getProcurementDetail moiName (= ตำบลที่ทำงานจริง). graceful — คืน '' ถ้า error"""
    try:
        import process5_http_client as p
        import requests
        tok = p._get_token(project_id)
        h = p.HEADERS_NO_AUTH.copy()
        h["X-Announcement-Token"] = tok
        url = ("https://process5.gprocurement.go.th/egp-atpj27-service/"
               "pb/a-egp-allt-project/announcement/getProcurementDetail")
        d = (requests.get(url, params={"projectId": project_id}, headers=h, timeout=15)
             .json() or {}).get("data") or {}
        return d.get("moiName") or ""
    except Exception:
        return ""


def resolve_tambon(project_id: str, dept_name: str = "", project_name: str = "") -> str:
    """ตำบลของงาน: getProcurementDetail moiName (ground truth งานจริง) → dept_name (fallback).
    API ก่อน = แม่นกว่า (dept = ตำบลที่ตั้งสำนักงาน proxy). '' = ระบุไม่ได้"""
    tb = tambon_from_api(project_id)
    return tb if tb else tambon_from_dept(dept_name)


def match_job(project_name: str, province: str, tambon_field: str = "",
              dept_name: str = "", cfg: dict = None) -> Tuple[str, dict]:
    """คืน (decision, detail). decision ∈ {'send','cut','soft_include'}"""
    cfg = cfg if cfg is not None else load_config()
    name = project_name or ""
    targets = cfg.get("target_tambons", {}).get(province, [])

    if not targets:
        return "cut", {"reason": "province_not_subscribed", "province": province}

    kw = next((k for k in cfg.get("keywords", []) if k in name), None)
    if not kw:
        return "cut", {"reason": "no_keyword"}
    neg = next((n for n in cfg.get("negative_keywords", []) if n in name), None)
    if neg:
        return "cut", {"keyword": kw, "negative": neg, "reason": "negative_keyword"}

    # location resolution
    loc, src = "", ""
    tf = _norm_tambon(tambon_field)
    if tf:
        loc, src = tf, "field"                       # field ระบุตำบล (จะ target หรือไม่)
    else:
        hit = next((t for t in targets if t in name), None)
        if hit:
            loc, src = hit, "name"                   # ชื่องานมี target tambon

    if loc and loc in targets:
        return "send", {"keyword": kw, "tambon": loc, "location_source": src,
                        "reason": "tambon_match"}
    if loc and loc not in targets:
        return "cut", {"keyword": kw, "tambon": loc, "location_source": src,
                       "reason": "tambon_not_target"}

    # location unknown → soft-include (keyword✓ + province✓)
    si = cfg.get("soft_include", {})
    if not si.get("enabled", False):
        return "cut", {"keyword": kw, "reason": "location_unknown_softinclude_off"}
    code = extract_road_code(name)
    label = (si.get("label_roadcode", "⚠️ พื้นที่ไม่ชัด · ถนนสาย {code}").format(code=code)
             if code else si.get("label_default", "⚠️ พื้นที่ไม่ชัด"))
    return "soft_include", {"keyword": kw, "label": label, "road_code": code,
                            "location_source": "unknown", "reason": "location_unknown"}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    print(f"config: {len(cfg['keywords'])} keywords, "
          f"{sum(len(v) for v in cfg['target_tambons'].values())} tambons, "
          f"soft_include={cfg.get('soft_include', {}).get('enabled')}")
