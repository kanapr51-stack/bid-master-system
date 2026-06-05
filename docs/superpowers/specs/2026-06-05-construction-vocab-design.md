# Construction Vocabulary (คลังคำกลาง) — Design Spec (rev2)

**วันที่:** 2026-06-05
**สถานะ:** design (รอ user review ก่อน writing-plans)
**ที่มา:** กัญจน์อยากเอาประวัติประมูล 617K มา "เทรน" keyword ให้ครอบคลุมงานก่อสร้าง (foundation ก่อน pricing)
**rev2:** หลังรัน 3 probes จริง — ทิ้งแนวทาง "ขุดทุกอย่าง" (noise ท่วม) → **normalize + gap-driven คัดมือ**

---

## 1. Findings จาก probe (เหตุผลที่แก้แนวทาง)

รันขุดจริง 52,525 ชื่องาน 3 รอบ พบว่า:
- **ขุดความถี่แบบครอบคลุม (uni/n-gram) = noise ท่วม** — boilerplate ("โดยวิธีเฉพาะเจาะจง" 42,704),
  เศษชื่อสถานที่ (นา/หนอง/ศรี/โนน), token แตก. freq≥20 = 1,693-9,512 คำ ส่วนใหญ่ขยะ
- **คำหายาก (freq ต่ำ) = ขยะเกือบหมด** (เลขไทย/ชื่อคน/สะกดผิด)
- **🔑 root cause จริงของ UNKNOWN ส่วนหนึ่ง = Unicode เพี้ยน ไม่ใช่ keyword ขาด** — ยืนยัน: 151 งาน (7%
  ของ UNKNOWN) สะกด "นํ้า" (น+ ํ+้+า) แทน "น้ำ" → keyword `ธนาคารน้ำใต้ดิน` ไม่ match (0 งานสะกดถูก)

→ แนวทางที่ถูก = **normalize ข้อความก่อน (กู้ฟรี) + ขุดเฉพาะ gap แบบคัดมือ** (เล็ก เจาะตรง)

## 2. Goal & Success Criteria

ทำให้ keyword ครอบคลุมงานก่อสร้างขึ้น โดย feed ทั้ง classifier + matcher ผ่าน **คลังคำกลาง**
(`config/construction_vocab.json`) — แต่เริ่มด้วยแก้ Unicode ก่อน แล้วค่อยเติมคำที่ขาดจริง

**Success:**
- **Normalize:** UNKNOWN (จ้างก่อสร้าง) ลดทันทีจาก normalize อย่างเดียว (เป้า: กู้ ≥ 7% ของ UNKNOWN = พวก นํ้า)
- **Gap mining:** ได้ candidate ชุด **คัดได้จริง (หลักสิบ ไม่ใช่หลักพัน)** หลังกรอง boilerplate/สถานที่/เลข
- classifier UNKNOWN รวม < 3% · matcher ได้ keyword ครอบคลุมงานพื้นที่เป้าหมายขึ้น
- ไม่มีคำขยะเข้า production (human curate) · classifier precision ไม่ตก (re-validate)

## 3. Two-Step Approach

```
Step 1 — NORMALIZE (กู้ฟรี, เสี่ยงต่ำ)
  text_normalize.normalize_thai(s): นํ้า→น้ำ, ค.ส.ล/คสล.→คสล, ยุบเว้นวรรค, NFC
  → classifier + matcher เรียกก่อน match keyword
  → re-validate: UNKNOWN ลดไหม + precision คงไหม

Step 2 — GAP-DRIVEN MINING (คัดมือ)
  gap jobs = (a) UNKNOWN จ้างก่อสร้าง [classifier gap]
           + (b) จ้างก่อสร้างในตำบลเป้าหมาย ที่ไม่มี matcher keyword [matcher gap]
  → tokenize (newmm) uni+bigram → กรองหนัก (เลข/สถานที่/stopword/boilerplate/คำที่มีแล้ว)
  → rank by freq ใน gap (floor ~10) → candidate หลักสิบ
  → 📚 construction_vocab.json + 📊 Sheet review → กัญจน์คัด → sync เข้า config
```

## 4. Files

| ไฟล์ | สร้าง/แก้ | หน้าที่ |
|---|---|---|
| `scripts/text_normalize.py` | **สร้าง** | `normalize_thai(s)` pure + map ตัวแปร (นํ้า/คสล/เว้นวรรค/NFC) |
| `scripts/test_text_normalize.py` | **สร้าง** | test เคสจริง (นํ้า→น้ำ ฯลฯ) |
| `scripts/work_type_classifier.py` | **แก้** | เรียก `normalize_thai(title)` ก่อน match |
| `scripts/job_matcher.py` | **แก้** | เรียก `normalize_thai(name)` ก่อน match keyword |
| `scripts/mine_vocab_gaps.py` | **สร้าง** | ขุด gap (UNKNOWN+matcher-cut) → candidate → คลัง + Sheet |
| `config/construction_vocab.json` | **สร้าง** | คลังคำกลาง (source of truth) |
| `scripts/apply_vocab_review.py` | **สร้าง** | Sheet → คลัง status → sync เข้า 2 config (backup, additive) |
| `scripts/test_vocab_sync.py` | **สร้าง** | test sync additive/idempotent/ไม่ทำลาย structure |

## 5. Step 1 — text_normalize.py

`normalize_thai(s) -> str` (pure, ไม่มี side effect):
1. `unicodedata.normalize("NFC", s)`
2. แก้ตัวแปรที่ยืนยันจาก data — map (ขยายได้): `"นํ้า"→"น้ำ"`, `"ํ้า"→"้ำ"` (กัน นิคหิต+ไม้โท เพี้ยน),
   `"ค.ส.ล."/"ค.ส.ล"/"คสล."→"คสล"`, ยุบ whitespace ซ้ำ → space เดียว, strip
3. **ไม่** lower-case (ไทยไม่มี case; อังกฤษใน keyword น้อย เก็บไว้)

guard: ยืนยัน map กับ data จริง (grep ตัวแปรใน 617K) ก่อน lock. ใช้ทั้ง classifier + matcher
→ ต้อง re-run `validate_work_type.py` หลังแก้ (precision อาจขยับ — ถ้าตก audit ก่อน commit)

## 6. Step 2 — mine_vocab_gaps.py

1. โหลดชื่องาน จ้างก่อสร้าง (normalize แล้ว)
2. **gap set:**
   - (a) classifier gap = `classify_work_type(name).primary == "UNKNOWN"`
   - (b) matcher gap = name อยู่ในตำบลเป้าหมาย (config target_tambons) แต่ไม่มี matcher keyword
3. tokenize newmm → uni + bigram (จับคำประสม)
4. **กรองหนัก:** ตัวเลข (0-9, ๐-๙), stopword (pythainlp), generic procurement, **boilerplate list**
   (เศรษฐกิจพอเพียง/ภัยแล้ง/ยั่งยืน/ส่งเสริมอาชีพ/ฤดูแล้ง/ปรัชญา/... = คำบรรยายโครงการ ไม่ใช่ประเภทงาน),
   **place stoplist** (จาก DB province/district/subdistrict + token), คำที่มีใน config แล้ว
5. rank by doc-freq ใน gap set, floor ~10 (ปรับได้) → candidate
6. เดา category (ถ้าทำได้จาก secondary signal) + เดา gap-source (classifier/matcher) + bsc_relevant
7. merge เข้าคลัง (term ใหม่=candidate, approved/rejected เดิมไม่แตะ) + push Sheet `vocab_review`

## 7. Vocab Entry Schema (`construction_vocab.json`)

```json
{
  "version": "v1", "updated": "2026-06-05",
  "terms": [
    {"term": "ผนังกันดิน", "freq": 38, "examples": ["จ้างก่อสร้างผนังกันดิน..."],
     "gap": "classifier", "category": "ดิน/ปรับพื้นที่", "bsc_relevant": true,
     "status": "candidate", "guard": null}
  ]
}
```
- `gap` = classifier / matcher / both (ช่องโหว่ที่คำนี้อุด)
- `category` = หมวด core/OTHER/"" · `bsc_relevant` = true/false (matcher) · `status` = candidate/approved/rejected
- `guard` = regex ถ้าเสี่ยง substring ([[INC-002]] ราง/ท่อ)

## 8. Step Review + Apply + Sync

- **Review (Sheet):** กัญจน์เปิด `vocab_review` เรียงตามความถี่ → ใส่ approve ✓/✗ + แก้ category/bsc/guard
- **apply_vocab_review.py:** Sheet → อัปเดตคลัง status → **backup 2 config** → sync additive:
  - classifier: term approved → `categories[category]` (หรือ other_keywords) + guard→`guards{}` ถ้ามี
  - matcher: term approved + bsc_relevant → `keywords[]`
  - **ไม่ลบ ไม่แตะ** priority/target_tambons/soft_include/negative ฯลฯ
- print diff + รัน validate

## 9. Validation

- `test_text_normalize.py`: เคส นํ้า→น้ำ, คสล variants, เว้นวรรค (assert)
- หลัง Step 1: `validate_work_type.py` → UNKNOWN ลด + precision ทุกหมวด ≥ 90% (ไม่ตก)
- `test_vocab_sync.py`: sync additive + idempotent (รัน 2 ครั้งเท่าเดิม) + key เดิมครบ
- รายงาน: UNKNOWN before/after normalize, after mining; matcher kw 28→X; classifier 79→Y

## 10. Out of Scope (YAGNI)

- ❌ ขุดความถี่แบบครอบคลุมทั้ง 52K (พิสูจน์แล้ว noise ท่วม) · ❌ คำหายาก freq ต่ำ (ขยะ)
- ❌ pythainlp เข้า pipeline VPS (offline ขุดเท่านั้น) · ❌ auto-adopt (human curate เสมอ)
- ❌ generate config ใหม่ทั้งไฟล์ (additive sync เท่านั้น)
- ❌ Pricing/win-prob/competitor model (Phase ถัดไป)

## 11. Open Questions

1. floor freq gap ~10 — โอเคไหม (ต่ำกว่านี้เริ่มมีขยะ)
2. boilerplate list (§6.4) — เริ่มจากที่ probe เจอ ขยายได้ตอนรีวิว
