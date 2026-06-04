# Work-Type Classifier — Design Spec

**วันที่:** 2026-06-04
**สถานะ:** ✅ ready-for-plans (กัญจน์ approve 2026-06-04 — open questions ปิดครบ)
**Backlog ที่มา:** N+77 item 2 "เทรน classifier จากชื่องาน 617K"

---

## 1. Motivation — ทำไมทำ

จัดหมวดงานก่อสร้างย่อย (ถนน/ราง/อาคาร/สะพาน/…) จาก **ชื่องาน** — ข้อมูลที่
**ไม่มี API ไหนให้** (live API ส่งแค่ `typeId` หยาบ 8 ค่า: ซื้อ/จ้างก่อสร้าง/เช่า/…).

**Reframe สำคัญ:** นี่ไม่ใช่แค่ feature classify — มันเริ่มเปลี่ยน BMS จาก
**"ระบบแจ้งเตือนงาน"** → **"ระบบวิเคราะห์ตลาดก่อสร้าง"**. Insight ที่ปลายทางจะได้:
- บริษัทเราเก่งหมวดไหน / แพ้หมวดไหน
- คู่แข่งรายไหนครองหมวดไหน
- ตำบลไหนมีงานหมวดไหนเยอะใน N ปีหลัง

มูลค่าทางธุรกิจสูงกว่า "วันนี้มีงานใหม่ 3 งาน" มาก.

### ไม่ใช่ ML — calibrate rule
ชื่องานราชการเป็น **template ซ้ำๆ** + **ไม่มี ground-truth label sub-type ใน 617K**
(มีแค่ 8 ค่าหยาบ). ML จะแค่เรียน rule ที่เรา self-label = circular ไม่ได้กำไร + เพิ่ม
artifact/deps. → **rule-based keyword + calibrate กับ 617K** (617K = validation set +
แหล่งค้น keyword ที่ขาด). [[project_classifier_research]]

---

## 2. Scope (Phase 0 + 1 เท่านั้น)

| Phase | ทำใน spec นี้ | สถานะ |
|---|---|---|
| **0 ฐาน** | work_type_classifier.py + config + validate กับ 617K | ✅ spec นี้ |
| **1 Analytics** | work_type column ใน winner_history + Sheet 3 มุม | ✅ spec นี้ |
| 2 Live tagging | wire เข้า notification path | ⏸ spec แยกภายหลัง |
| 3 Per-customer ranking | จัด ranking ตามหมวดที่ user ชอบ | ⏸ defer จนมี preference data (5 users + feedback authority=กัญจน์ → ยังไม่มี signal, [[project_beta_golive_strategy]]) |

---

## 3. Taxonomy (7 หมวด core + 2 ถังพิเศษ)

หมวด core 7 + OTHER + UNKNOWN:

| หมวด | keyword ตัวอย่าง |
|---|---|
| 🌉 สะพาน | สะพาน, ท่อลอดเหลี่ยม, ทางต่างระดับ, ทางเชื่อม |
| 🏞 แหล่งน้ำ/ชลประทาน | ฝาย, ขุดลอก, อ่างเก็บน้ำ, ประตูระบายน้ำ, อาคารบังคับน้ำ, บาดาล, ประปา, สถานีสูบน้ำ |
| 💧 รางระบายน้ำ/ท่อ | รางระบาย, ร่องระบาย, ท่อระบาย, ท่อลอด, บ่อพัก, วางท่อ |
| 🏢 อาคาร | อาคาร, รั้ว, กำแพง, ศาลา, ห้องน้ำ, โรงเรียน, หลังคา, ฝ้าเพดาน, ลานคอนกรีต |
| 🛣 ถนน | ถนน, ลาดยาง, ผิวจราจร, แอสฟัลต์, ลูกรัง, ไหล่ทาง, เสริมผิว |
| ⛰ ดิน/ปรับพื้นที่ | ถมดิน, ปรับพื้นที่, งานดิน, ปรับเกลี่ย |
| ⚡ ไฟฟ้า/ส่องสว่าง | ไฟฟ้าส่องสว่าง, ไฟฟ้าแสงสว่าง, เสาไฟ, โคมไฟ, ไฟกิ่ง, ส่องสว่าง |
| ▫️ **OTHER** | match keyword นอก core: สนามกีฬา, ลานกีฬา, สวนสาธารณะ, ภูมิทัศน์, … (= รู้ว่าไม่ใช่ core) |
| ⬛ **UNKNOWN** | ไม่ match keyword ใดเลย (= ถังขุด keyword ที่ขาด) |

**ไฟฟ้า/ส่องสว่าง = core (กัญจน์ตัดสิน 2026-06-04):** data 617K — ไฟฟ้า 1,069 งาน/600 ลบ.
**จำนวนงานมากกว่า สะพาน (873) และ ดิน (984)** ที่ยอมรับเป็น core อยู่แล้ว → ยกเป็น core
ตั้งแต่รอบแรก (taxonomy ยังไม่ lock, เพิ่มตอนนี้ฟรี vs. เพิ่มหลัง Phase 1 = bump version +
recompute 617K). [[project_classifier_research]]

**OTHER vs UNKNOWN (จุดที่ 3):** ต่างกันชัด — OTHER = จัดได้ว่า "ไม่ใช่ 6 หมวดหลัก"
(มี keyword), UNKNOWN = จัดไม่ได้จริง (ไม่มี keyword). Analytics ใช้ประโยชน์ต่างกัน:
OTHER = งานนอกสายธุรกิจ, UNKNOWN = งานที่ ruleset ยังตามไม่ทัน → loop ปรับ keyword.

keyword ทั้งหมดเก็บใน `config/work_type_keywords.json` — แก้/เพิ่มได้โดยไม่แตะ logic.

---

## 4. Primary selection — กฎ deterministic 3 ชั้น (จุดที่ 1)

งานมีหลายหมวดในตัว (เช่น "ถนน คสล. พร้อมรางระบายน้ำ"). primary เลือกแบบ:

```
1. SCORE   = จำนวน keyword "ตัวที่ไม่ซ้ำ" ต่อหมวดที่เจอในชื่อ → หมวด score สูงสุด = primary
             (นับ distinct keyword ไม่ใช่จำนวนครั้ง — กันคำซ้ำ inflate)
2. TIE     → priority list (เขียนชัดใน config, แก้ได้)
3. STILL   → ตำแหน่ง keyword เร็วสุดในชื่อ (head-noun)
```

**priority list (tie-break, default — แก้ได้ใน config):**
```
สะพาน > แหล่งน้ำ/ชลประทาน > อาคาร > ถนน > รางระบายน้ำ/ท่อ > ไฟฟ้า/ส่องสว่าง > ดิน/ปรับพื้นที่ > OTHER
```
เหตุผล: โครงสร้างเฉพาะ/เด่น (สะพาน) ไม่ถูกกลืนโดยคำ incidental. ถนน อยู่กลางเพราะ
common; วาง **เหนือ ราง** → "ถนนพร้อมราง" tie จะได้ ถนน (งานหลัก=ถนน) ✓.
**ไฟฟ้า/ส่องสว่าง** วาง **ใต้ ถนน** ด้วยเหตุผลเดียวกัน — "ถนนพร้อมไฟส่องสว่าง" tie → ถนน
(ไฟเป็น incidental บนถนน), แต่ "ติดตั้งไฟฟ้าส่องสว่าง" เดี่ยวๆ ยัง classify เป็นไฟฟ้าถูก.

**secondary** = หมวด core อื่นที่ score ≥ 1 (เรียงตาม score) → เก็บครบ ไม่เสียข้อมูล.

**ตัวอย่างผล (เขียนใน spec เพื่อ audit ไม่เถียง):**
| ชื่องาน | score | primary | secondary |
|---|---|---|---|
| ก่อสร้างถนนคสล.พร้อมรางระบายน้ำ | ถนน1 ราง1 → tie → priority | ถนน | [ราง] |
| ก่อสร้างรางระบายน้ำ รูปตัวยู | ราง1 | ราง | [] |
| ก่อสร้างอาคารเรียน 3 ชั้น | อาคาร1 | อาคาร | [] |
| ปรับปรุงผิวจราจรลาดยางแอสฟัลต์ | ถนน3 | ถนน | [] |
| ก่อสร้างสนามกีฬาอเนกประสงค์ | OTHER | OTHER | [] |

**ข้อจำกัดที่ยอมรับ (documented):** "รางระบายน้ำข้างถนนสาย X" → score ราง1 ถนน1 →
priority → **ถนน** (ทั้งที่งานหลักคือราง). ยอมรับได้เพราะ (ก) secondary ยังเก็บราง,
(ข) ปรับ priority/keyword ภายหลังได้, (ค) กฎ fix = ไม่ subjective.

**Output ของ `classify_work_type(title)`:**
```python
{
  "primary":   "ถนน",
  "secondary": ["ราง"],
  "all":       ["ถนน", "ราง"],
  "version":   "v1.0",
}
```

---

## 5. โครงสร้างไฟล์ + interface

**โมดูลใหม่** (ไม่แตะ `classifier_tags.py` เดิม — parallel system, กัน production พัง):

```
scripts/work_type_classifier.py     # pure functions, ไม่มี side effect
config/work_type_keywords.json       # taxonomy + priority + version
```

`config/work_type_keywords.json` schema:
```json
{
  "version": "v1.0",
  "categories": {
    "ถนน": ["ถนน", "ลาดยาง", "ผิวจราจร", "..."],
    "รางระบายน้ำ/ท่อ": ["รางระบาย", "ท่อระบาย", "..."],
    "...": ["..."]
  },
  "other_keywords": ["สนามกีฬา", "ลานกีฬา", "สวนสาธารณะ", "ไฟฟ้าส่องสว่าง", "..."],
  "priority": ["สะพาน", "แหล่งน้ำ/ชลประทาน", "อาคาร", "ถนน", "รางระบายน้ำ/ท่อ", "ไฟฟ้า/ส่องสว่าง", "ดิน/ปรับพื้นที่", "OTHER"]
}
```

interface:
```python
WORK_TYPE_VERSION = "v1.0"   # bump เมื่อ keyword/priority เปลี่ยน (จุดที่ 4)
def classify_work_type(title: str) -> dict   # → {primary, secondary, all, version}
```

guard ภาษาไทย: reuse บทเรียน substring (เช่น "ราง" ห้ามชน "ตาราง/รางวัล") — ใช้ regex
guard แบบเดียวกับ job_matcher ถ้า keyword สั้นเสี่ยงชน. [[L-007]]

---

## 6. Validation (Phase 0 — gate ก่อน Analytics) (จุดที่ 2)

รันกับ 617K (เน้น 52,525 งาน `ชื่อประเภทโครงการ=จ้างก่อสร้าง`):

| metric | นิยาม | acceptance |
|---|---|---|
| **Coverage** | % งานก่อสร้างที่ primary ∉ {OTHER, UNKNOWN} | ≥ 90% |
| **Precision (stratified)** | สุ่ม ~30 งาน/หมวด → audit primary ถูกไหม → precision **ต่อหมวด** | ทุกหมวด ≥ 90% |

**ทำไม stratified:** coverage อย่างเดียว gameable (เหมาเป็นถนนหมด → coverage สูง แต่ผิด).
per-category precision จับเคสนี้ได้ (precision หมวดอื่นจะตก).

**Loop ปรับ:** สุ่มดู UNKNOWN bucket → หา keyword ขาด → เพิ่ม config → bump version →
รันใหม่ จน coverage + precision ผ่านทั้งคู่. บันทึกผลแต่ละรอบลง `data/work_type_validation_*.txt`.

**Gate:** ผ่าน acceptance ทั้ง 2 ก่อน → ค่อยไป Phase 1.

---

## 7. Phase 1 — Analytics (หลัง gate ผ่าน)

1. **เพิ่ม column** `work_type` + `work_type_version` ใน `winner_history.db`
   (migration แบบเดียวกับ method_group: backup snapshot → recompute → ADD COLUMN).
2. **Sheet 3 มุม** (read-only, ไม่แตะ live):
   - **บริษัทเรา × หมวด** — เราชนะ/แพ้หมวดไหน (มูลค่า + จำนวน + ส่วนลด)
   - **คู่แข่ง × หมวด** — top winner ต่อหมวด (ใครครองหมวดไหน)
   - **ตำบล × หมวด** — พื้นที่ × ความต้องการงานแต่ละหมวด
3. apply เฉพาะงานก่อสร้าง (typeId/ชื่อประเภท=จ้างก่อสร้าง) — งานซื้อ/เช่าข้าม.

### ⚠️ Constraint บังคับ (กัญจน์ตัดสิน 2026-06-04): นับ Primary + Secondary
Classifier ตอบ **"งานนี้หลักคืออะไร"** (primary เดี่ยว) — แต่ Analytics ตอบ
**"ธุรกิจเราเกี่ยวข้องกับอะไร"** สองคำถามนี้ **ไม่เหมือนกัน**.

- งาน "ถนน คสล. พร้อมรางระบายน้ำ" → primary=ถนน, secondary=[ราง].
- ถ้ามุม **บริษัทเรา × หมวด** นับ **primary-only** → undercount demand หมวด **ราง**
  ทันที (BSC = ทรัพย์คอนกรีต ผลิตราง/ท่อสำเร็จรูป → ราง คือสินค้าหลัก [[user_profile]]).

**กฎ:**
- **Classification** (จัดงานเข้าหมวด, validation §6) → ใช้ **primary**.
- **Market / company-capability analytics** (Sheet 3 มุม) → นับงานเข้า **ทุกหมวดใน `all`
  (primary + secondary)**. งานหนึ่งงานนับได้หลายหมวด (ไม่ dedup ข้ามหมวด).
- เก็บ metric แยก 2 ชั้น: count ตาม primary (scope หลัก) **และ** count ตาม involvement
  (primary+secondary) → กันการตีความเป็น primary-only โดยไม่ตั้งใจ.

---

## 8. Out of scope (YAGNI)

- ❌ ML model / training
- ❌ Live notification tagging (Phase 2 แยก)
- ❌ Per-customer ranking (Phase 3, defer)
- ❌ แก้ classifier_tags.py เดิม (parallel แทน)

---

## 9. Resolved questions (ปิดครบ — กัญจน์ + ChatGPT review 2026-06-04)

1. **priority order** (§4) — ✅ **คง default `ถนน > ราง`**. data หนุน: ถนน 31.8K งาน/22,879 ลบ.
   vs ราง 7.5K/1,656 ลบ. → ถนนเป็น scope หลักเชิงมูลค่าจริง. การกลืน ราง แก้ที่ชั้น analytics
   (นับ secondary, §7 constraint) ไม่ใช่ที่ priority.
2. **keyword core/OTHER** (§3) — ✅ **เพิ่ม ไฟฟ้า/ส่องสว่าง เป็น core ที่ 7** (data 1,069 งาน
   > สะพาน/ดิน). หมวดอื่นคงเดิม.
3. **acceptance 90/90** — ✅ **คง** Coverage ≥ 90% + Precision ต่อหมวด ≥ 90%. (95/95 ไล่ edge
   case ไม่จบ, 80/80 ต่ำไปสำหรับ analytics ตัดสินใจธุรกิจ — ChatGPT + กัญจน์ เห็นตรงกัน.)
4. **Analytics primary vs primary+secondary** — ✅ **primary+secondary** สำหรับมุมบริษัทเรา/ตลาด
   (§7 constraint). classification ยังใช้ primary.
