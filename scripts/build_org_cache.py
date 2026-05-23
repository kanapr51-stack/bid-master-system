"""
build_org_cache.py — สร้าง cgd_org_province_cache.json จาก CGD Open Data

หลักการเลี่ยงกับดัก "HQ-province":
  CGD field `จังหวัด` = จังหวัดสำนักงานใหญ่ (ไม่ใช่ที่ตั้งงานจริง)
  → แต่ถ้า filter เอาเฉพาะ records ที่ `จังหวัด`=<จังหวัดเป้าหมาย>
    จะได้เฉพาะหน่วยงาน "ท้องถิ่น" ของจังหวัดนั้น (อบต./เทศบาล/โรงเรียน/รพ.)
    ซึ่งหน่วยงานท้องถิ่น admin-province = work-province เสมอ → ปลอดภัย
  หน่วยงานใหญ่ (admin=กรุงเทพ) จะไม่ติด filter จังหวัดต่างจังหวัด → ไม่เข้า cache

กฎ 90%: ถ้าชื่อหน่วยงานเดียวกันโผล่หลายจังหวัด (เช่น "กองช่าง") →
  เก็บเฉพาะถ้าจังหวัดใดจังหวัดหนึ่ง ≥90% ของ records ของชื่อนั้น ไม่งั้นทิ้ง
"""
import sys
import json
import time
from pathlib import Path
from collections import defaultdict

import requests

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent / ".env"
OUT_FILE = DATA_DIR / "cgd_org_province_cache.json"

API_URL = "https://opend.data.go.th/get-ckan/datastore_search"
# file-1, file-2 ของ egp-contact-2568 (พอสำหรับ enumerate หน่วยงานท้องถิ่น)
RESOURCE_IDS = [
    "e4eaa1b4-eb1a-4534-b227-988ee25b898d",
    "9ae119c4-73b9-4bb6-9b71-7b355269bc00",
]
PAGE = 1000
MAX_PAGES_PER_FILE = 6   # 6000 records/file/province พอครอบคลุม
AGREE_THRESHOLD = 0.90

# ชื่อหน่วยงานย่อย generic ที่ทุก อปท. มีเหมือนกัน → ห้าม cache (กำกวมข้ามจังหวัด)
GENERIC_BLOCKLIST = {
    "กองช่าง", "กองคลัง", "กองการศึกษา", "กองสาธารณสุข",
    "กองสาธารณสุขและสิ่งแวดล้อม", "กองสวัสดิการสังคม", "กองวิชาการและแผนงาน",
    "กองยุทธศาสตร์และงบประมาณ", "สำนักงานปลัด", "สำนักปลัด",
    "สำนักปลัดเทศบาล", "สำนักงานปลัดเทศบาล", "กองการประปา",
    "กองส่งเสริมการเกษตร", "หน่วยตรวจสอบภายใน", "กองสารสนเทศ",
    "กองช่างสุขาภิบาล", "กองการเจ้าหน้าที่", "กองสวัสดิการ",
    "งานพัสดุ", "ฝ่ายพัสดุ", "งานการเงิน",
}
MIN_NAME_LEN = 6  # ชื่อสั้นกว่านี้มักเป็น generic

# จังหวัดเป้าหมาย Phase 1 (ขยายเป็น 77 ได้ภายหลังด้วย --provinces)
DEFAULT_PROVINCES = ["นครพนม", "บึงกาฬ"]


def load_token() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPEND_USER_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("ไม่พบ OPEND_USER_TOKEN ใน .env")


def fetch_province(token: str, province: str) -> list[tuple[str, str]]:
    """คืน list ของ (sub_agency_name, province) จาก records ของจังหวัดนี้"""
    headers = {"api-key": token}
    pairs = []
    for rid in RESOURCE_IDS:
        offset = 0
        for _ in range(MAX_PAGES_PER_FILE):
            params = {
                "resource_id": rid,
                "filters": json.dumps({"จังหวัด": province}, ensure_ascii=False),
                "limit": PAGE,
                "offset": offset,
            }
            try:
                r = requests.get(API_URL, headers=headers, params=params, timeout=30)
                r.raise_for_status()
                result = r.json().get("result", {})
            except Exception as e:
                print(f"  ⚠️ {province} rid={rid[:8]} offset={offset}: {e}")
                break
            records = result.get("records", [])
            if not records:
                break
            for rec in records:
                sub = (rec.get("ชื่อหน่วยงานย่อย") or "").strip()
                if sub:
                    pairs.append((sub, province))
            total = result.get("total", 0)
            offset += PAGE
            if offset >= total:
                break
            time.sleep(0.3)
    return pairs


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--provinces", nargs="*", default=DEFAULT_PROVINCES,
                        help="รายชื่อจังหวัดที่จะ build (default: นครพนม บึงกาฬ)")
    args = parser.parse_args()

    token = load_token()
    # นับ (sub_name → {province: count})
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for prov in args.provinces:
        print(f"ดึง CGD จังหวัด {prov} ...")
        pairs = fetch_province(token, prov)
        print(f"  ได้ {len(pairs)} records")
        for sub, p in pairs:
            counts[sub][p] += 1

    # ใช้กฎ 90% agreement
    cache: dict[str, str] = {}
    dropped = 0
    for sub, prov_counts in counts.items():
        if sub in GENERIC_BLOCKLIST or len(sub) < MIN_NAME_LEN:
            dropped += 1
            continue
        total = sum(prov_counts.values())
        best_prov, best_n = max(prov_counts.items(), key=lambda kv: kv[1])
        if best_n / total >= AGREE_THRESHOLD:
            cache[sub] = best_prov
        else:
            dropped += 1

    # merge กับ cache เดิม (ถ้ามี) — ไม่ทับของเดิมที่ดีอยู่แล้ว
    existing = {}
    if OUT_FILE.exists():
        existing = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    existing.update(cache)

    OUT_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n✅ {OUT_FILE.name}: {len(existing)} หน่วยงาน "
          f"(+{len(cache)} ใหม่/อัปเดต, ทิ้ง {dropped} ที่ชื่อกำกวม)")
    # ตัวอย่าง
    for sub in list(cache)[:10]:
        print(f"   {cache[sub]} ← {sub}")


if __name__ == "__main__":
    main()
