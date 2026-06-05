# Construction Vocabulary (คลังคำกลาง) — Design Spec

**วันที่:** 2026-06-05
**สถานะ:** design (รอ user review ก่อน writing-plans)
**ที่มา:** กัญจน์อยากเอาประวัติประมูล 617K มา "เทรน" keyword ให้ครอบคลุมงานก่อสร้าง — เป็น foundation ก่อนทำ pricing/อื่นๆ

---

## 1. Goal & Success Criteria

สร้าง **คลังคำกลางของงานก่อสร้าง** (`config/construction_vocab.json`) ที่ขุดจากชื่องานจริง 52,525 งาน
จ้างก่อสร้าง → เป็น **source of truth** ที่ feed ทั้ง 2 ระบบ:
- **classifier** (`work_type_keywords.json`) — จัดหมวด, ลด UNKNOWN
- **matcher** (`matching_preferences.json`) — จับงานที่ BSC ควรเห็น, ไม่พลาด

**Success:**
- หลัง curate + sync รอบแรก: **UNKNOWN (จ้างก่อสร้าง) ลดจาก 4.4% → < 3%**
- matcher ได้ keyword ใหม่ที่ครอบคลุมขึ้น (วัดด้วยจำนวนงานจ้างก่อสร้างที่มี ≥1 keyword match เพิ่มขึ้น)
- **ไม่มีคำขยะหลุดเข้า production** (human-in-loop curation บังคับ)
- คลังคำ + 2 config ยัง consistent (sync ทางเดียวจากคลัง, additive)

## 2. หลักการสำคัญ — 1 คำ แท็ก 2 มิติ

คำเดียวกันรับใช้ 2 ระบบที่ถามคนละคำถาม:
- **`category`** (classifier ถาม "งานนี้หมวดอะไร") → หมวด core 7 / OTHER / "" (ยังไม่ชัด)
- **`bsc_relevant`** (matcher ถาม "BSC ควรเห็นงานนี้ไหม") → true / false

ตัวอย่าง: `สนามกีฬา` = category OTHER + bsc_relevant **false** (ไม่ส่ง user) · `รางระบายน้ำ` = category ราง + **true**

## 3. Architecture & Data Flow

```
52,525 ชื่องาน จ้างก่อสร้าง (winner_history.db)
        │
        ▼  [1] mine_construction_vocab.py  (pythainlp newmm — offline dev tool)
   ตัดคำ → นับ doc-frequency → กรอง stopword/คำที่มีแล้ว → เดา category + bsc_relevant
        │
        ▼  เขียน/อัปเดต (เพิ่มเฉพาะ term ใหม่ status=candidate, ไม่ทับ approved/rejected)
   📚 config/construction_vocab.json   +   📊 Sheet tab "vocab_review"
        │
        ▼  [2] กัญจน์ review ใน Sheet (approve/reject + แก้ category/bsc_relevant)
        │
        ▼  [3] apply_vocab_review.py  (อ่าน Sheet → อัปเดตคลัง → sync เข้า config + backup)
   work_type_keywords.json (เติม kw ต่อหมวด)   matching_preferences.json (เติมเฉพาะ bsc_relevant)
        │
        ▼  [4] validate: รัน validate_work_type.py → UNKNOWN ลดไหม + รายงาน
```

**pythainlp = dev dependency (offline เท่านั้น)** — รันในเครื่อง Windows สร้าง candidate. **ไม่ใส่เข้า
pipeline VPS** (production ยังอ่าน config JSON เหมือนเดิม ไม่พึ่ง pythainlp). [[project_classifier_research]]

## 4. Files

| ไฟล์ | สร้าง/แก้ | หน้าที่ |
|---|---|---|
| `config/construction_vocab.json` | **สร้าง** | คลังคำกลาง (source of truth) — list ของ entry |
| `scripts/mine_construction_vocab.py` | **สร้าง** | ขุด candidate (pythainlp) → อัปเดตคลัง + push Sheet |
| `scripts/apply_vocab_review.py` | **สร้าง** | Sheet → อัปเดตคลัง status → sync เข้า 2 config (backup ก่อน) |
| `scripts/test_vocab_sync.py` | **สร้าง** | test: sync additive/idempotent/ไม่ทำลาย structure |
| `work_type_keywords.json` / `matching_preferences.json` | **แก้ (โดย sync)** | รับ keyword ใหม่จากคลัง |

## 5. Vocab Entry Schema (`construction_vocab.json`)

```json
{
  "version": "v1",
  "updated": "2026-06-05",
  "terms": [
    {
      "term": "ธนาคารน้ำใต้ดิน",
      "freq": 812,
      "examples": ["จ้างโครงการธนาคารน้ำใต้ดิน (แบบเปิด)..."],
      "category": "แหล่งน้ำ/ชลประทาน",
      "bsc_relevant": true,
      "status": "candidate",
      "guard": null
    }
  ]
}
```
- `freq` = จำนวนชื่องาน (จ้างก่อสร้าง) ที่มี term นี้ (document frequency)
- `category` = หมวด core 7 / "OTHER" / "" (รอคน) — mining เดาให้ (majority vote)
- `bsc_relevant` = mining เดา (default: true ถ้า category ∈ core, false ถ้า OTHER/ไม่ชัด) — คนตัดสินจริง
- `status` = `candidate` (ขุดมา) / `approved` (กัญจน์รับ) / `rejected` (กัญจน์ตัด)
- `guard` = regex ถ้า term สั้นเสี่ยง substring ชนคำอื่น (เช่นบทเรียน ราง/ท่อ INC-002) — คนใส่ตอน review

## 6. [1] Mining (`mine_construction_vocab.py`)

1. ดึงชื่องาน `ชื่อประเภทโครงการ=จ้างก่อสร้าง` 52,525 ชื่อ (จาก raw_json)
2. ตัดคำแต่ละชื่อด้วย `pythainlp.tokenize.word_tokenize(engine="newmm")`
3. นับ **document frequency** ต่อ token (กี่ชื่องานมี token นั้น — ไม่นับซ้ำในชื่อเดียว)
4. **กรองทิ้ง:** len<2, ตัวเลขล้วน, pythainlp stopwords, คำ procurement ทั่วไป (จ้าง/โครงการ/ก่อสร้าง/
   ปรับปรุง/ซ่อมแซม/โดยวิธี/เฉพาะเจาะจง/หมู่/ตำบล/อำเภอ/จังหวัด/บ้าน/...), คำที่อยู่ใน config ทั้ง 2 แล้ว
5. เก็บ candidate ที่ `freq >= 20` (ปรับได้) เรียงตามความถี่
6. **เดา category:** ดูชื่องานที่มี term → classify_work_type → หมวดที่ได้บ่อยสุด (ถ้า UNKNOWN ส่วนใหญ่ → "")
7. **เดา bsc_relevant:** true ถ้า category ∈ core, false ถ้า OTHER/""
8. **merge เข้าคลัง:** term ใหม่ → เพิ่ม status=candidate; term ที่มีแล้ว (approved/rejected) → **ไม่แตะ**
   (idempotent, คงผลรีวิวเดิม) แต่ refresh freq/examples ได้
9. push candidate (status=candidate) → Sheet tab `vocab_review` (cols: term, freq, ตัวอย่าง,
   หมวดที่เดา, bsc?, [approve], [แก้หมวด], [แก้ bsc], [guard]) ให้กัญจน์รีวิว

## 7. [2] Review (Sheet, by กัญจน์)

กัญจน์เปิด tab `vocab_review` → ต่อแถว: ใส่ `approve` = ✓/✗, แก้หมวด/bsc/guard ถ้าต้องการ.
รีวิวเรียงตามความถี่ (คำพบบ่อยก่อน = คุ้มสุด). ไม่ต้องรีวิวหมดรอบเดียว — ค้างไว้รอบหน้าได้.

## 8. [3] Apply + Sync (`apply_vocab_review.py`)

1. อ่าน Sheet `vocab_review` → อัปเดต `construction_vocab.json`: approve✓→status=approved (+ category/
   bsc/guard ที่แก้), approve✗→rejected
2. **backup** `work_type_keywords.json` + `matching_preferences.json` → `backups/` (timestamp)
3. **sync เข้า config (additive, idempotent):**
   - classifier: ต่อ term `approved` → เพิ่มเข้า `categories[category]` (หรือ `other_keywords` ถ้า OTHER)
     ถ้ายังไม่มี; ถ้ามี `guard` → เพิ่มเข้า `guards{}`
   - matcher: ต่อ term `approved` + `bsc_relevant=true` → เพิ่มเข้า `keywords[]` ถ้ายังไม่มี
   - **ไม่ลบ ไม่แตะ** key อื่น (priority/target_tambons/soft_include/negative_keywords ฯลฯ คงเดิม)
4. print diff: เพิ่ม classifier +N คำ, matcher +M คำ

## 9. [4] Validation

- รัน `scripts/validate_work_type.py` → **UNKNOWN (จ้างก่อสร้าง) ต้องลด** (เป้า < 3%) + ไม่มีหมวดไหน
  precision ตก (re-audit ถ้าขยับเยอะ)
- `scripts/test_vocab_sync.py`: sync เป็น additive + idempotent (รัน 2 ครั้งผลเท่าเดิม) + ไม่ทำลาย
  key เดิมใน config ทั้ง 2
- รายงาน: matcher keyword 28 → X, classifier 79 → Y, UNKNOWN before/after

## 10. Out of Scope (YAGNI ตอนนี้)

- ❌ Pricing / win-probability / competitor model (Phase ถัดไป — foundation นี้เสร็จก่อน)
- ❌ auto-adopt candidate (ต้อง human curate เสมอ)
- ❌ ใส่ pythainlp เข้า pipeline VPS (offline ขุดเท่านั้น)
- ❌ generate config ใหม่ทั้งไฟล์ (sync แบบ additive เท่านั้น — กัน hand-tuned หาย)
- ❌ ตัดคำงานประเภทอื่น (ซื้อ/จ้างทำของ) — โฟกัสจ้างก่อสร้างก่อน

## 11. Open Questions

1. `freq >= 20` เป็น threshold เริ่มต้น — โอเคไหม หรืออยากเห็นคำหายากด้วย (freq ต่ำกว่า)
2. รีวิวผ่าน **Google Sheet** (ตาม workflow เดิม) โอเคไหม หรืออยากเป็นไฟล์/วิธีอื่น
3. รอบแรกจะมี candidate ค่อนข้างเยอะ (น่าจะ 200-500 คำ) — อยากให้ผมรันขุดเลยแล้วดูจำนวนจริงก่อนไหม
