"""
province_extractor.py — แยกจังหวัดของงานจากชื่องาน + ชื่อหน่วยงาน

วิธี: text matching แบบ cascade 8 ชั้น (ไม่ใช้ ML/coordinate)
หลักการสำคัญ: หาไม่เจอ → คืน "" (ไม่เดา) ดีกว่าเดาผิด

ลำดับชั้น (เจอชั้นไหนก่อน ใช้เลย):
  1. prefix จังหวัด (จังหวัด/จ./อบจ.) + ชื่อจังหวัด
  2. prefix เทศบาลเมือง/นคร + ชื่อ (province ก่อน, ไม่งั้น amphoe)
  3. prefix อำเภอ (อำเภอ/อ./เขต/กิ่งอำเภอ) + อำเภอ unique
  4. prefix ตำบล (ตำบล/ต./แขวง/อบต./เทศบาลตำบล/ทต.) + ตำบล unique
  5. ชื่อจังหวัดตรงๆ ในข้อความ (รวม alias)
  6. อำเภอ unique ไม่มี prefix (≥4 ตัว, ไม่อยู่ใน exclusion)
  7. ตำบล unique ไม่มี prefix (≥5 ตัว, ไม่อยู่ใน exclusion)
  8. org cache (ชื่อหน่วยงาน → จังหวัด จาก CGD/สะสมเอง)

มี combo disambiguation: ตำบลที่ชื่อซ้ำหลายจังหวัด → ถ้า text มีอำเภอ/จังหวัด
ที่ชี้ไปจังหวัดเดียวในกลุ่มนั้น ใช้จังหวัดนั้น
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# ---- prefix groups ----
PROVINCE_PREFIXES = ["จังหวัด", "อบจ.", "อบจ", "องค์การบริหารส่วนจังหวัด", "จ."]
CITY_PREFIXES = ["เทศบาลเมือง", "เทศบาลนคร", "ทม.", "ทน."]
AMPHOE_PREFIXES = ["อำเภอ", "กิ่งอำเภอ", "เขต", "อ."]
TAMBON_PREFIXES = ["เทศบาลตำบล", "องค์การบริหารส่วนตำบล", "ตำบล",
                   "อบต.", "อบต", "ทต.", "แขวง", "ต."]

# หน่วยงานใหญ่ส่วนกลางที่ทำงานข้ามจังหวัด — ถ้าไม่เจอจังหวัดชัดเจน → คืนว่าง
# (ไม่ให้ bare amphoe/tambon เดา token จากชื่อโครงการยาวๆ ผิดจังหวัด)
NATIONAL_ORG_PATTERNS = [
    "สำนักก่อสร้างทาง", "สำนักก่อสร้างสะพาน", "สำนักทางหลวง",
    "สำนักบริหารโครงการ", "สำนักงานบริหารโครงการ", "ฝ่ายโครงการ",
    "การประปานครหลวง", "การประปาส่วนภูมิภาค", "การไฟฟ้าฝ่ายผลิต",
    "กองบัญชาการ", "ยุทธโยธา", "สำนักก่อสร้างชลประทานขนาดใหญ่",
    "กรมการทหาร", "ศูนย์การทหาร",
]

# ---- province aliases (เขียนย่อ/ไม่เป็นทางการ → ชื่อใน CSV) ----
PROVINCE_ALIASES = {
    "กรุงเทพ": "กรุงเทพมหานคร",
    "กรุงเทพฯ": "กรุงเทพมหานคร",
    "กทม.": "กรุงเทพมหานคร",
    "กทม": "กรุงเทพมหานคร",
    "พระนครศรีอยุธยา": "พระนครศรีอยุธยา",
    "อยุธยา": "พระนครศรีอยุธยา",
}

_CACHE = {}


def _load():
    if _CACHE:
        return _CACHE
    amp = json.loads((DATA_DIR / "amphoe_lookup.json").read_text(encoding="utf-8"))
    tam = json.loads((DATA_DIR / "tambon_lookup.json").read_text(encoding="utf-8"))
    excl = set(json.loads((DATA_DIR / "geo_exclusion_list.json").read_text(encoding="utf-8")))

    org_cache_file = DATA_DIR / "cgd_org_province_cache.json"
    org_cache = {}
    if org_cache_file.exists():
        org_cache = json.loads(org_cache_file.read_text(encoding="utf-8"))

    provinces = sorted({p for provs in amp.values() for p in provs}, key=len, reverse=True)
    # จังหวัดชื่อสั้น (≤4 ตัว: ตาก/เลย/น่าน/แพร่/ตรัง/ตราด) → match แบบ bare ไม่ได้
    # (ซ่อนในคำอื่นได้ง่าย เช่น "ตาก" ใน "โพธิ์ตาก") ต้องมี prefix จ./จังหวัด เท่านั้น
    provinces_bare = [p for p in provinces if len(p) >= 5]
    # alias keys ที่ map ไปจังหวัดจริง (ใช้ค้นในข้อความ)
    alias_keys = sorted(PROVINCE_ALIASES.keys(), key=len, reverse=True)

    amp_maxlen = max(len(k) for k in amp)
    tam_maxlen = max(len(k) for k in tam)

    # unique-name sets สำหรับ bare matching (sorted longest-first)
    amp_unique_bare = sorted(
        [k for k, v in amp.items() if len(v) == 1 and len(k) >= 4 and k not in excl],
        key=len, reverse=True,
    )
    tam_unique_bare = sorted(
        [k for k, v in tam.items() if len(v) == 1 and len(k) >= 5 and k not in excl],
        key=len, reverse=True,
    )

    _CACHE.update(dict(
        amp=amp, tam=tam, excl=excl, org_cache=org_cache,
        provinces=provinces, provinces_bare=provinces_bare, alias_keys=alias_keys,
        amp_maxlen=amp_maxlen, tam_maxlen=tam_maxlen,
        amp_unique_bare=amp_unique_bare, tam_unique_bare=tam_unique_bare,
    ))
    return _CACHE


def _norm(text: str) -> str:
    """ลบช่องว่างซ้ำ + อักขระ zero-width"""
    text = text.replace("​", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _lookup_after(after: str, lookup: dict, maxlen: int, minlen: int = 2):
    """หา name ยาวสุดที่ after ขึ้นต้นด้วย → คืน (name, [provinces]) หรือ (None, None)"""
    hi = min(maxlen, len(after))
    for L in range(hi, minlen - 1, -1):
        cand = after[:L]
        if cand in lookup:
            return cand, lookup[cand]
    return None, None


def _find_after_prefixes(text: str, prefixes: list, lookup: dict, maxlen: int):
    """
    หาทุกตำแหน่งของ prefix แล้ว lookup ชื่อที่ตามมา
    คืน list ของ [provinces] ที่เจอ (อาจมีหลายรายการ)
    """
    results = []
    for pre in prefixes:
        start = 0
        while True:
            i = text.find(pre, start)
            if i == -1:
                break
            after = text[i + len(pre):].lstrip(" .")
            name, provs = _lookup_after(after, lookup, maxlen)
            if provs:
                results.append(provs)
            start = i + len(pre)
    return results


def _collect_context(text: str, c: dict):
    """รวบรวมจังหวัดที่ชี้ชัดจาก amphoe-prefix + bare-province เพื่อ disambiguate ตำบล"""
    ctx = set()
    # bare province
    for p in c["provinces"]:
        if p in text:
            ctx.add(p)
    for a in c["alias_keys"]:
        if a in text:
            ctx.add(PROVINCE_ALIASES[a])
    # amphoe (unique only) anywhere
    amphoe_results = _find_after_prefixes(text, AMPHOE_PREFIXES, c["amp"], c["amp_maxlen"])
    for provs in amphoe_results:
        if len(provs) == 1:
            ctx.add(provs[0])
    return ctx


def extract_province(dept_name: str = "", title: str = "", dept_id: str = None) -> str:
    """คืนชื่อจังหวัด หรือ "" ถ้าหาไม่เจอ/ไม่แน่ใจ"""
    c = _load()
    dept_name = _norm(dept_name or "")
    title = _norm(title or "")
    text = f"{dept_name} {title}".strip()
    if not text:
        return ""

    # --- ชั้น 1: prefix จังหวัด → ชื่อที่ตามมาเป็นชื่อจังหวัด ---
    for pre in PROVINCE_PREFIXES:
        idx = 0
        while (i := text.find(pre, idx)) != -1:
            after = text[i + len(pre):].lstrip(" .")
            for p in c["provinces"]:
                if after.startswith(p):
                    return p
            for a in c["alias_keys"]:
                if after.startswith(a):
                    return PROVINCE_ALIASES[a]
            idx = i + len(pre)

    # --- ชั้น 2: เทศบาลเมือง/นคร + ชื่อ (province ก่อน ไม่งั้น amphoe unique) ---
    for pre in CITY_PREFIXES:
        idx = 0
        while (i := text.find(pre, idx)) != -1:
            after = text[i + len(pre):].lstrip(" .")
            matched = None
            for p in c["provinces"]:
                if after.startswith(p):
                    matched = p
                    break
            if not matched:
                name, provs = _lookup_after(after, c["amp"], c["amp_maxlen"])
                if provs and len(provs) == 1:
                    matched = provs[0]
            if matched:
                return matched
            idx = i + len(pre)

    # --- ชั้น 3: prefix อำเภอ + อำเภอ unique ---
    for provs in _find_after_prefixes(text, AMPHOE_PREFIXES, c["amp"], c["amp_maxlen"]):
        if len(provs) == 1:
            return provs[0]

    # --- ชั้น 4: prefix ตำบล + ตำบล (unique → ใช้เลย, ซ้ำ → disambiguate) ---
    tambon_pref_results = _find_after_prefixes(text, TAMBON_PREFIXES, c["tam"], c["tam_maxlen"])
    ctx = None
    for provs in tambon_pref_results:
        if len(provs) == 1:
            return provs[0]
    for provs in tambon_pref_results:
        if len(provs) > 1:
            if ctx is None:
                ctx = _collect_context(text, c)
            inter = ctx & set(provs)
            if len(inter) == 1:
                return next(iter(inter))

    # --- ชั้น 5: org cache (exact dept_name) — ground-truth, มาก่อน bare matching
    #     กัน trap: "ตาก" ใน "โพธิ์ตาก", "มหาราช" ใน "ปิยะมหาราชาลัย" ---
    if dept_name and dept_name in c["org_cache"]:
        return c["org_cache"][dept_name]

    # --- ชั้น 6: ชื่อจังหวัดตรงๆ ในข้อความ (เฉพาะชื่อยาว ≥5 ตัว) ---
    for p in c["provinces_bare"]:
        if p in text:
            return p
    for a in c["alias_keys"]:
        if a in text:
            return PROVINCE_ALIASES[a]

    # national-org guard: ถึงจุดนี้ยังไม่เจอจังหวัดชัดเจน
    # ถ้าเป็นหน่วยงานใหญ่ส่วนกลาง → คืนว่าง (อย่าให้ bare matching เดาผิด)
    if any(pat in dept_name for pat in NATIONAL_ORG_PATTERNS):
        return ""

    # --- ชั้น 7: อำเภอ unique ไม่มี prefix ---
    for name in c["amp_unique_bare"]:
        if name in text:
            return c["amp"][name][0]

    # --- ชั้น 8: ตำบล unique ไม่มี prefix ---
    for name in c["tam_unique_bare"]:
        if name in text:
            return c["tam"][name][0]

    return ""


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    tests = [
        ("เทศบาลตำบลบ้านแพง", "ก่อสร้างถนนคอนกรีต"),
        ("โรงเรียนธาตุพนม", "ซื้อครุภัณฑ์"),
        ("กรมทางหลวง", "ก่อสร้างถนนสาย 212"),
        ("องค์การบริหารส่วนตำบลโคกหินแฮ่", "จ้างเหมา"),
        ("", "ก่อสร้างถนน คสล. หมู่ 5 ต.บึงโขงหลง อ.บึงโขงหลง จ.บึงกาฬ"),
        ("สำนักงานชลประทานที่ 7", "ปรับปรุงคลอง"),
        ("", "ซื้อวัสดุสำนักงาน"),
    ]
    for dept, title in tests:
        r = extract_province(dept, title)
        print(f"  [{r or '(ว่าง)'}]  dept='{dept}' title='{title[:40]}'")
