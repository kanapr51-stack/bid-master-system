"""
classifier_tags.py — Rule-based multi-dimensional classifier (Phase 1+2)

Pure functions ที่รับ row dict (all_jobs schema) → 8 tag fields:
  - project_type           : ก่อสร้าง / วัสดุ / อุปกรณ์ / บริการ / IT / อื่นๆ
  - construction_subtype   : ถนน / สะพาน / ระบบน้ำ / อาคาร / ปรับปรุง / อื่นๆ
                             (ว่างเปล่าถ้า project_type != ก่อสร้าง)
  - budget_tier            : micro (<500K) / small (<5M) / medium (<20M) / large (≥20M) / unknown
  - urgency_tier           : critical (<3d) / soon (<7d) / normal (<30d) / planning (≥30d) /
                             expired / unknown
  - method_id              : 03/15/16/18/19 (ตาม eGP method code)
  - sme_suitable           : TRUE / FALSE
  - geographic_precision   : district / province / national
  - unspsc_family          : (Phase 4 — เว้นว่าง)

Reference: docs/classifier_deep_research.md section 4-5
"""

from datetime import date, datetime
from typing import Optional


# ============================================================
# project_type
# ============================================================
# ลำดับสำคัญ — match แรกชนะ (specific keywords first)
PROJECT_TYPE_RULES = [
    # IT — specific tech keywords
    ("IT", [
        "ซอฟต์แวร์", "software", "ระบบสารสนเทศ", "ระบบคอมพิวเตอร์",
        "เว็บไซต์", "แอปพลิเคชัน", "ฐานข้อมูล", "ระบบเครือข่าย",
        "license ซอฟต์แวร์", "ระบบ ERP", "ระบบ MIS",
    ]),
    # บริการ — มาก่อน ก่อสร้าง/อุปกรณ์/วัสดุ เพราะ phrase แบบ "จ้างเหมาบริการ"
    # ระบุชัดว่าซื้อแรงงาน/บริการ ไม่ใช่ของ
    # (ต้องเป็น full phrase เพื่อไม่ false-match กับ "จ้างเหมาก่อสร้างถนน")
    ("บริการ", [
        # บริการแบบเปิดเผย
        "จ้างเหมาบริการ", "จ้างที่ปรึกษา", "ที่ปรึกษา", "ค่าจ้างเหมา",
        "บริการล้าง", "บริการซ่อม", "บริการรักษาความปลอดภัย",
        "บริการทำความสะอาด", "บริการขนส่ง", "บริการประชาสัมพันธ์",
        # จ้างคน / แรงงาน
        "จ้างเหมาบุคคล", "จ้างบุคคลธรรมดา", "จ้างบริการบุคคล",
        "จ้างปฏิบัติงาน", "จ้างเหมาปฏิบัติงาน", "จ้างเหมาบุคคลภายนอก",
        "จ้างจ้างเหมา",
        # อาหาร / ของบริโภคในงาน
        "จ้างเหมาประกอบอาหาร", "ประกอบอาหารกลางวัน",
        # ป้าย/ประชาสัมพันธ์ — งานทำของ
        "จ้างทำป้าย", "จ้างเหมาจัดทำป้าย", "จัดทำป้ายไวนิล",
        # งาน event/สถานที่
        "จ้างเหมาจัดสถานที่", "จ้างจัดกิจกรรม", "จ้างจัดทำ",
        # เหมารถ / ขนส่ง
        "จ้างเหมารถ",
        # สำรวจ/วิเคราะห์/ตรวจ
        "จ้างสำรวจ", "ตรวจวิเคราะห์", "ฝึกอบรม",
        # ซ่อมรถ/ครุภัณฑ์ — ไม่ใช่ก่อสร้าง
        "ซ่อมแซมรถ", "ซ่อมบำรุงรถ", "ซ่อมแซมครุภัณฑ์", "ซ่อมบำรุงครุภัณฑ์",
        # อื่นๆ
        "จ้างเปลี่ยน", "จ้างเหมาสูบ",
        "จ้างเหมาคนงาน", "จ้างเหมาทำอาหาร", "จ้างเหมายานพาหนะ",
        "จ้างเหมาเช่า", "จ้างเหมาเต๊นท์", "จ้างประดับ", "จ้างขนส่ง",
        "เช่านั่งร้าน", "จ้างเช่า",
    ]),
    # ก่อสร้าง — keyword สื่องานก่อสร้าง/ปรับปรุง/ซ่อมแซมในชื่อ
    ("ก่อสร้าง", [
        "ก่อสร้าง", "ปรับปรุง", "ซ่อมแซม", "ขุดลอก", "ปูคอนกรีต",
        "ถมดิน", "ลาดยาง", "ผิวจราจร", "ขยายเขต", "เสริมผิว",
        "งานโยธา", "ปูแอสฟัลต์", "วางท่อ", "ขุดบ่อ", "เทคอนกรีต",
        "ดัดแปลง", "ต่อเติม", "บูรณะ",
    ]),
    # อุปกรณ์ / ครุภัณฑ์
    ("อุปกรณ์", [
        "ครุภัณฑ์", "เครื่องปรับอากาศ", "คอมพิวเตอร์", "เครื่องพิมพ์",
        "รถยนต์", "รถบรรทุก", "รถจักรยานยนต์", "เครื่องจักร",
        "อุปกรณ์สำนักงาน", "เก้าอี้", "โต๊ะทำงาน",
        "ตู้เหล็ก", "ตู้เอกสาร", "ตู้เก็บ",
        "เครื่องถ่ายเอกสาร", "เครื่องสำรองไฟ", "เครื่องเสียง",
        "เครื่องสูบน้ำ", "เครื่องตัด", "เครื่องตัดหญ้า",
        "เต็นท์", "ไฟฟ้าส่องสว่าง", "กล้องตรวจ", "กล้องวงจรปิด",
        "อุปกรณ์ประปา", "อุปกรณ์ระบบ", "ระบบไฟฟ้า",
        "มิเตอร์น้ำ",
    ]),
    # วัสดุ
    ("วัสดุ", [
        "ซื้อวัสดุ", "วัสดุก่อสร้าง", "เครื่องเขียน",
        "น้ำมันเชื้อเพลิง", "วัสดุเชื้อเพลิง",
        "วัสดุการเกษตร", "วัสดุวิทยาศาสตร์", "เคมีภัณฑ์",
        "ปูนซีเมนต์", "เหล็กเส้น", "กระดาษ", "สีน้ำมัน", "สีทาอาคาร",
        # ยา / สารเคมี / อาหารดิบ
        "ซื้อยา", "เวชภัณฑ์", "สารส้ม", "สารตกตะกอน",
        "ซื้ออาหาร", "อาหารว่าง", "อาหารเสริม",
        # แบบฟอร์ม / สิ่งพิมพ์
        "ซื้อแบบพิมพ์", "แบบพิมพ์",
        # อะไหล่
        "ซื้อแบตเตอรี่", "ซื้อยาง", "อะไหล่",
        # ของอุปโภคบริโภค
        "ซื้อน้ำมัน", "ซื้อน้ำดื่ม", "ซื้อวัคซีน", "ซื้อสื่อการเรียน",
        "ซื้อท่อ", "ซื้อผ้า", "เติมผงเคมี",
    ]),
]


def classify_project_type(title: str) -> str:
    t = (title or "").lower()
    if not t:
        return "อื่นๆ"
    for label, keywords in PROJECT_TYPE_RULES:
        for kw in keywords:
            if kw.lower() in t:
                return label
    return "อื่นๆ"


# ============================================================
# construction_subtype (ใช้ได้เฉพาะ project_type == "ก่อสร้าง")
# ============================================================
CONSTRUCTION_SUBTYPE_RULES = [
    ("สะพาน", [
        "สะพาน", "ทางเชื่อม", "ทางต่างระดับ",
    ]),
    ("ถนน", [
        "ถนน", "ลาดยาง", "ผิวจราจร", "ก่อสร้างทาง",
        "ปูแอสฟัลต์", "ไหล่ทาง", "ทางเดินคอนกรีต", "ปูคอนกรีต",
        "เสริมผิว", "คอนกรีตเสริมเหล็ก", "คสล.",
    ]),
    ("ระบบน้ำ", [
        "ประปา", "ระบบส่งน้ำ", "บ่อบาดาล", "เขื่อน", "ฝาย",
        "ท่อระบาย", "รางระบาย", "ขุดลอก", "ขุดบ่อ", "ขุดสระ",
        "อ่างเก็บน้ำ", "วางท่อ", "ระบบประปา",
    ]),
    ("อาคาร", [
        "อาคาร", "สำนักงาน", "ก่อสร้างรั้ว", "กำแพง", "หลังคา",
        "ห้องน้ำ", "ห้องเรียน", "ที่จอดรถ", "บ้านพัก", "ศาลา",
        "โรงเรียน", "โรงพยาบาล", "โรงเก็บ", "หอประชุม",
    ]),
    # ปรับปรุง/ซ่อมแซม — last priority เพราะคำเหล่านี้กว้าง
    ("ปรับปรุง", [
        "ปรับปรุง", "ซ่อมแซม", "บูรณะ", "ทาสี",
    ]),
]


def classify_construction_subtype(title: str, project_type: str = "") -> str:
    if project_type != "ก่อสร้าง":
        return ""
    t = (title or "").lower()
    for label, keywords in CONSTRUCTION_SUBTYPE_RULES:
        for kw in keywords:
            if kw.lower() in t:
                return label
    return "อื่นๆ"


# ============================================================
# budget_tier
# ============================================================
def _parse_budget(budget) -> Optional[float]:
    if budget is None:
        return None
    s = str(budget).replace(",", "").replace("฿", "").replace("บาท", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def classify_budget_tier(budget) -> str:
    val = _parse_budget(budget)
    if val is None or val <= 0:
        return "unknown"
    if val < 500_000:
        return "micro"
    if val < 5_000_000:
        return "small"
    if val < 20_000_000:
        return "medium"
    return "large"


# ============================================================
# urgency_tier
# ============================================================
def _parse_thai_date(s) -> Optional[date]:
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime(s, fmt).date()
            if d.year > 2400:
                d = d.replace(year=d.year - 543)
            return d
        except ValueError:
            continue
    return None


def classify_urgency_tier(deadline, today: Optional[date] = None) -> str:
    if today is None:
        today = date.today()
    d = _parse_thai_date(deadline)
    if d is None:
        return "unknown"
    delta = (d - today).days
    if delta < 0:
        return "expired"
    if delta < 3:
        return "critical"
    if delta < 7:
        return "soon"
    if delta < 30:
        return "normal"
    return "planning"


# ============================================================
# method_id (eGP standard codes)
# ============================================================
METHOD_RULES = [
    ("e-market", "15"),
    ("e-bidding", "16"),
    ("อิเล็กทรอนิกส์", "16"),
    ("เฉพาะเจาะจง", "19"),
    ("คัดเลือก", "18"),
    ("ประกวดราคา", "03"),
    ("ตลาดอิเล็กทรอนิกส์", "15"),
]


def classify_method(procurement_type) -> str:
    pt = (procurement_type or "").strip()
    if not pt:
        return ""
    for keyword, code in METHOD_RULES:
        if keyword in pt:
            return code
    return ""


# ============================================================
# sme_suitable
# ============================================================
def classify_sme_suitable(budget, project_type: str = "") -> bool:
    """
    Heuristic: ราคากลาง < 5M + ประเภท ก่อสร้าง/วัสดุ/อุปกรณ์ → SME-suitable
    (ขนาดงานที่ SME ทั่วไปแข่งได้)
    """
    val = _parse_budget(budget)
    if val is None or val <= 0:
        return False
    if val >= 5_000_000:
        return False
    return project_type in ("ก่อสร้าง", "วัสดุ", "อุปกรณ์")


# ============================================================
# geographic_precision
# ============================================================
def classify_geographic_precision(province, district, subdistrict) -> str:
    if (subdistrict or "").strip() or (district or "").strip():
        return "district"
    if (province or "").strip():
        return "province"
    return "national"


# ============================================================
# Aggregate
# ============================================================
TAG_COLUMNS = [
    "project_type",
    "construction_subtype",
    "budget_tier",
    "urgency_tier",
    "method_id",
    "sme_suitable",
    "geographic_precision",
    "unspsc_family",
]


def classify_all(row: dict, today: Optional[date] = None) -> dict:
    """รับ row dict → คืน dict 8 tag fields"""
    title = row.get("title", "")
    project_type = classify_project_type(title)
    return {
        "project_type":         project_type,
        "construction_subtype": classify_construction_subtype(title, project_type),
        "budget_tier":          classify_budget_tier(row.get("budget", "")),
        "urgency_tier":         classify_urgency_tier(row.get("deadline", ""), today),
        "method_id":            classify_method(row.get("procurement_type", "")),
        "sme_suitable":         "TRUE" if classify_sme_suitable(row.get("budget", ""), project_type) else "FALSE",
        "geographic_precision": classify_geographic_precision(
            row.get("province", ""),
            row.get("district", ""),
            row.get("subdistrict", ""),
        ),
        "unspsc_family":        "",
    }


def tag_values(row: dict, today: Optional[date] = None) -> list:
    """คืน list ตามลำดับ TAG_COLUMNS — สะดวกสำหรับ append เข้า sheet row"""
    tags = classify_all(row, today)
    return [tags[col] for col in TAG_COLUMNS]


if __name__ == "__main__":
    import sys
    import json
    sys.stdout.reconfigure(encoding="utf-8")
    samples = [
        {
            "title": "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สายหมู่ 5 ตำบลบ้านแพง",
            "budget": "1,250,000.00", "deadline": "30/05/2569",
            "procurement_type": "e-bidding",
            "province": "นครพนม", "district": "บ้านแพง", "subdistrict": "บ้านแพง",
        },
        {
            "title": "จ้างเหมาบริการล้างเครื่องปรับอากาศ จำนวน 8 เครื่อง",
            "budget": "5,600.00", "deadline": "08/05/2569",
            "procurement_type": "เฉพาะเจาะจง",
            "province": "", "district": "", "subdistrict": "",
        },
        {
            "title": "ซื้อจัดซื้อเครื่องปรับอากาศ",
            "budget": "33,600.00", "deadline": "",
            "procurement_type": "เฉพาะเจาะจง",
            "province": "นครพนม", "district": "", "subdistrict": "",
        },
        {
            "title": "ก่อสร้างอาคารสำนักงานเทศบาล 3 ชั้น",
            "budget": "25,000,000.00", "deadline": "15/07/2569",
            "procurement_type": "e-bidding",
            "province": "บึงกาฬ", "district": "บึงโขงหลง", "subdistrict": "",
        },
        {
            "title": "ปรับปรุงระบบประปาหมู่บ้าน",
            "budget": "850,000.00", "deadline": "01/06/2569",
            "procurement_type": "e-bidding",
            "province": "นครพนม", "district": "บ้านแพง", "subdistrict": "หนองแวง",
        },
    ]
    for i, s in enumerate(samples, 1):
        tags = classify_all(s)
        print(f"--- Sample {i} ---")
        print(f"  title: {s['title']}")
        print(f"  tags:  {json.dumps(tags, ensure_ascii=False)}")
