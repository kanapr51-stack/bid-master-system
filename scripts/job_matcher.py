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
import sys
import json
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_normalize import normalize_thai  # noqa: E402

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "matching_preferences.json")

# รหัสถนน: บก./นพ. + เลข 3-4 หลัก (ไทย/อารบิก) เช่น "นพ.4036", "บก ๓๐๙"
_ROAD_CODE_RE = re.compile(r"(?:บก|นพ)\.?\s?[๐-๙\d]{3,4}")

# ตำบลที่ระบุชัดในชื่องาน เช่น "ตำบลนาแก", "ต.หนองซน" → จับชื่อตำบล (อักษรไทยต่อเนื่อง)
_TAMBON_NAME_RE = re.compile(r"(?:ตำบล|ต\.)\s*([ก-๙]+)")

# keyword สั้นที่ substring ชนคำอื่น → regex guard (ภาษาไทยไม่มีเว้นวรรค). audit ชื่องานจริง 617K 2026-06-04
# "ท่อ" (ท่อระบายน้ำ) ห้าม match "ท่อง"(ท่องเที่ยว) + "ท่อน"(ท่อนพันธุ์/ซุง=เกษตร) — INC-002
#       แต่ "ท่อน้ำ"(ท่อน้ำประปา=ท่อจริง 164 เคส) ต้องเก็บ → (?!น(?!้)) อนุญาตเฉพาะ ท่อน้ำ
# "ราง" (รางระบายน้ำ) ห้าม match "ตาราง"(เมตร, 2,428) + "รางวัล"(ถ้วย/ของ, 349) + "วรางกูร"(พระนาม, 41)
_KEYWORD_GUARDS = {
    "ท่อ": re.compile(r"ท่อ(?!ง)(?!น(?!้))"),
    "ราง": re.compile(r"(?<!ตา)ราง(?!วัล|กูร)"),
}


def _kw_hit(k: str, name: str) -> bool:
    """keyword match — ใช้ regex guard ถ้า keyword นั้นเสี่ยง substring ชนคำอื่น, ไม่งั้น substring ปกติ"""
    g = _KEYWORD_GUARDS.get(k)
    return bool(g.search(name)) if g else (k in name)


# eGP ตั้งชื่องานมาตรฐาน: [วิธีจัดหา]+[ประเภท] เช่น "ประกวดราคาซื้อ...", "สอบราคาจ้างก่อสร้าง..."
# ดูที่ leading-token หลังตัดคำวิธี → ซื้อ = จัดหาสินค้า (ไม่ใช่งานก่อสร้าง) → ตัด
_PROC_METHOD_PREFIXES = ("ประกวดราคาอิเล็กทรอนิกส์", "ประกวดราคา", "สอบราคา")


def is_procurement(name: str) -> bool:
    """True ถ้าเป็นงาน 'ซื้อ' (จัดหาสินค้า) ไม่ใช่ 'จ้าง' (ก่อสร้าง/บริการ).
    ใช้ leading-token (ตัดคำวิธีนำหน้าแล้วดู ซื้อ/จัดซื้อ) → กันงานจ้างที่มีคำ 'ซื้อ' กลางชื่อ."""
    n = (name or "").lstrip()
    for p in _PROC_METHOD_PREFIXES:
        if n.startswith(p):
            n = n[len(p):].lstrip()
            break
    return n.startswith("ซื้อ") or n.startswith("จัดซื้อ")


# 77 จังหวัด — ใช้ anti-province guard (soft-include only): กันงานจังหวัดอื่นที่ระบุชัดในชื่อ
_THAI_PROVINCES = frozenset({
    "กระบี่", "กรุงเทพมหานคร", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี",
    "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "ตรัง", "ตราด", "ตาก", "นครนายก",
    "นครปฐม", "นครพนม", "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส",
    "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี",
    "พระนครศรีอยุธยา", "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "ภูเก็ต", "มหาสารคาม",
    "มุกดาหาร", "ยะลา", "ยโสธร", "ระนอง", "ระยอง", "ราชบุรี", "ร้อยเอ็ด", "ลพบุรี", "ลำปาง",
    "ลำพูน", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร",
    "สระบุรี", "สระแก้ว", "สิงห์บุรี", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "สุโขทัย",
    "หนองคาย", "หนองบัวลำภู", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี",
    "อ่างทอง", "เชียงราย", "เชียงใหม่", "เพชรบุรี", "เพชรบูรณ์", "เลย", "แพร่", "แม่ฮ่องสอน",
})


def foreign_province_in_title(name: str, own_provinces) -> str:
    """คืนชื่อจังหวัดอื่น (≠ ที่ subscribe) ถ้าระบุชัดในชื่อ ('จังหวัด<X>' / 'จ.<X>'), ไม่งั้น ''.
    ใช้ใน soft-include branch เท่านั้น — กันงานข้ามจังหวัดที่ไม่ใช่พื้นที่เรา (INC-002)."""
    own = set(own_provinces)
    for p in _THAI_PROVINCES:
        if p in own:
            continue
        if ("จังหวัด" + p) in name or ("จ." + p) in name or ("จ. " + p) in name:
            return p
    return ""


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


def tambon_from_name(name: str) -> str:
    """ตำบลที่ระบุชัดในชื่องาน ('ตำบล X' / 'ต.X') → ชื่อตำบล. '' ถ้าไม่มี.
    ใช้ตัดสิน non-target: ถ้าชื่อบอกตำบลชัด + ตำบลนั้นไม่อยู่ใน target → cut (ไม่ใช่ soft)"""
    m = _TAMBON_NAME_RE.search(name or "")
    return m.group(1).strip() if m else ""


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


def passes_keyword(project_name: str, cfg: dict = None) -> Tuple[bool, str]:
    """Pre-filter ฟรี (ไม่เรียก API): keyword ผ่าน + ไม่ติด negative ไหม.
    ใช้ทำ keyword-first — กรองก่อน resolve deadline/tambon (ซึ่งแพง = API call).
    คืน (True, kw) ถ้าผ่าน · (False, reason) ถ้าไม่ผ่าน → skip resolve ได้เลย.
    logic ตรงกับ keyword/negative ใน match_job (consistency)."""
    cfg = cfg if cfg is not None else load_config()
    name = normalize_thai(project_name)
    kw = next((k for k in cfg.get("keywords", []) if _kw_hit(k, name)), None)
    if not kw:
        return False, "no_keyword"
    neg = next((n for n in cfg.get("negative_keywords", []) if n in name), None)
    if neg:
        return False, f"negative:{neg}"
    return True, kw


def match_job(project_name: str, province: str, tambon_field: str = "",
              dept_name: str = "", cfg: dict = None) -> Tuple[str, dict]:
    """คืน (decision, detail). decision ∈ {'send','cut','soft_include'}"""
    cfg = cfg if cfg is not None else load_config()
    name = normalize_thai(project_name)
    targets = cfg.get("target_tambons", {}).get(province, [])

    if not targets:
        return "cut", {"reason": "province_not_subscribed", "province": province}

    # proc-aware keyword pool (1 feed เสิร์ฟ 2 ธุรกิจของเจ้าของเดียวกัน):
    #   ซื้อ  → ตรงกับ material_keywords (วัสดุที่ BSC ขาย) = lead ขายของ; ไม่ตรง → ตัด
    #          (กัน false-positive เช่น "ซื้อเครื่องรักษาโรคตา" ที่ชื่อมีคำก่อสร้าง)
    #   จ้าง → ตรงกับ keywords (งานก่อสร้างของยศประทาน) เหมือนเดิม
    if is_procurement(name):
        kw = next((k for k in cfg.get("material_keywords", []) if _kw_hit(k, name)), None)
        if not kw:
            return "cut", {"reason": "no_material_keyword"}
    else:
        kw = next((k for k in cfg.get("keywords", []) if _kw_hit(k, name)), None)
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
            loc, src = hit, "name"                   # ชื่องานมี target tambon (ชนะก่อน — งานเชื่อมหลายตำบล)
        else:
            explicit = tambon_from_name(name)        # ไม่มี target ในชื่อ → ลองหา "ตำบล X" ชัดๆ
            if explicit:
                loc, src = explicit, "name_explicit"  # ระบุตำบลชัด + ไม่ใช่ target → จะ cut

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
    # anti-province guard (INC-002): ถ้าชื่อระบุจังหวัดอื่นชัด + ไม่มีจังหวัดเราในชื่อ → cut
    # (ไม่แตะงานที่รู้ตำบลแล้ว — ถึงตรงนี้ loc ว่างแน่. งาน "นครพนม-สกลนคร" รอด เพราะมีชื่อจังหวัดเรา)
    if province not in name:
        fp = foreign_province_in_title(name, cfg.get("target_tambons", {}).keys())
        if fp:
            return "cut", {"keyword": kw, "foreign_province": fp,
                           "reason": "foreign_province_softinclude"}
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
