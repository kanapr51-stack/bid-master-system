"""
build_geo_lookup.py — สร้างไฟล์ lookup สำหรับ province_extractor

อ่าน data/thai_geo_raw.csv (7,426 rows) แล้วสร้าง:
  - data/amphoe_lookup.json   : {อำเภอ: [จังหวัด,...]}  (99.8% มี 1 จังหวัด)
  - data/tambon_lookup.json   : {ตำบล: [จังหวัด,...]}   (87.1% มี 1 จังหวัด)
  - data/geo_exclusion_list.json : [คำที่ห้าม match ใน tier ไม่มี prefix]

หมายเหตุ: เก็บ list จังหวัดทั้งหมดไว้ (ไม่ทิ้งตัวซ้ำ) เพื่อให้ extractor
เช็คได้เองว่าชื่อนี้ unique หรือไม่ (len==1) — ตัดสินใจที่ extractor ไม่ใช่ที่นี่
"""
import csv
import sys
import json
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent.parent / "data"
CSV_FILE = DATA_DIR / "thai_geo_raw.csv"

# คำทั่วไปในงานก่อสร้าง/จัดซื้อ ที่บังเอิญเป็นชื่อตำบล/อำเภอด้วย
# → ห้าม match ใน tier ที่ไม่มี prefix (กัน false positive)
# (ตรวจสอบกับ data จริงแล้ว: ถนน=ปัตตานี, ริม=น่าน, เหนือ=กาฬสินธุ์, ...)
EXCLUSION_CANDIDATES = [
    "ถนน", "สะพาน", "อาคาร", "ดิน", "น้ำ", "ริม", "สาย", "แยก", "ทาง",
    "เหนือ", "ใต้", "ตะวันออก", "ตะวันตก", "กลาง", "ใหม่", "เก่า",
    "ใน", "นอก", "บน", "ล่าง", "หน้า", "หลัง", "ในเมือง", "เมือง",
    "บ้านนา", "บ้านใหม่", "หนองบัว", "ห้วย", "หนอง", "โคก", "ดง",
    "ท่า", "นา", "บ้าน", "วัง", "โพน", "คลอง",
]


def main():
    rows = list(csv.DictReader(CSV_FILE.open(encoding="utf-8")))
    print(f"อ่าน {len(rows)} rows จาก {CSV_FILE.name}")

    amphoe_to_prov: dict[str, set] = defaultdict(set)
    tambon_to_prov: dict[str, set] = defaultdict(set)
    all_geo_names: set[str] = set()

    for r in rows:
        prov = r["province"].strip()
        amp = r["district"].strip()
        tam = r["subdistrict"].strip()
        if amp:
            amphoe_to_prov[amp].add(prov)
            all_geo_names.add(amp)
        if tam:
            tambon_to_prov[tam].add(prov)
            all_geo_names.add(tam)

    amphoe_lookup = {k: sorted(v) for k, v in sorted(amphoe_to_prov.items())}
    tambon_lookup = {k: sorted(v) for k, v in sorted(tambon_to_prov.items())}

    # Exclusion: เฉพาะ candidate ที่เป็นชื่อ geo จริง (ไม่งั้น exclude ไปก็เปล่าประโยชน์)
    exclusion = sorted([w for w in EXCLUSION_CANDIDATES if w in all_geo_names])

    # เขียนไฟล์
    (DATA_DIR / "amphoe_lookup.json").write_text(
        json.dumps(amphoe_lookup, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA_DIR / "tambon_lookup.json").write_text(
        json.dumps(tambon_lookup, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA_DIR / "geo_exclusion_list.json").write_text(
        json.dumps(exclusion, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # สรุป
    amp_unique = sum(1 for v in amphoe_lookup.values() if len(v) == 1)
    tam_unique = sum(1 for v in tambon_lookup.values() if len(v) == 1)
    print(f"\n✅ amphoe_lookup.json : {len(amphoe_lookup)} อำเภอ "
          f"({amp_unique} unique = {amp_unique/len(amphoe_lookup):.1%})")
    print(f"✅ tambon_lookup.json : {len(tambon_lookup)} ตำบล "
          f"({tam_unique} unique = {tam_unique/len(tambon_lookup):.1%})")
    print(f"✅ geo_exclusion_list.json : {len(exclusion)} คำ → {exclusion}")


if __name__ == "__main__":
    main()
