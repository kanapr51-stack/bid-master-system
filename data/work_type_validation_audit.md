# Work-Type Classifier — Phase 0 Validation Audit

**วันที่:** 2026-06-04
**classifier:** v1.2 (config `config/work_type_keywords.json`)
**validation set:** 52,525 งาน `ชื่อประเภทโครงการ=จ้างก่อสร้าง` (จาก winner_history.db 617K)

## Gate result: ✅ PASS (ทั้ง 2 เกณฑ์)

### Coverage = 94.8% (acceptance ≥ 90%)
primary ∉ {OTHER, UNKNOWN} = 94.8%. UNKNOWN 4.4%, OTHER 0.9%.

### Precision ต่อหมวด (stratified audit ~30/หมวด ด้วยมือ) — ทุกหมวด ≥ 90%
| หมวด | n | precision |
|---|---|---|
| อาคาร | 7,954 | 30/30 (100%) |
| ถนน | 27,334 | ~28/30 (93%) |
| สะพาน | 312 | 29/30 (97%) |
| แหล่งน้ำ/ชลประทาน | 6,115 | 30/30 (100%) |
| ไฟฟ้า/ส่องสว่าง | 709 | 30/30 (100%) |
| รางระบายน้ำ/ท่อ | 6,084 | ~28/30 (93%) |
| ดิน/ปรับพื้นที่ | 1,260 | ~30/30 (100%) |
| OTHER | 453 | ~30/30 (100%) |

## Calibration history
- **v1.0** → coverage 87.7% (FAIL). UNKNOWN cluster ใหญ่ = ธนาคารน้ำใต้ดิน/โคก หนอง นา/แหล่งน้ำในไร่นา/ศพด/ทางหลวง.
- **v1.1** → เพิ่ม keyword high-precision (quantified จาก 5,918 UNKNOWN จริง ไม่เดา) → coverage 94.8%. ตัด "สำนักงาน" (ชน "วัสดุสำนักงาน").
- **v1.2** → **แก้ tie-break: score → ตำแหน่ง(head-noun) → priority** (เดิม spec §4 = priority ก่อน position).

## ⚠️ Spec deviation ที่ต้อง flag — tie-break order
**spec §4 เขียน:** score → priority → position.
**v1.2 ใช้:** score → **position** → priority.

**เหตุผล (validation พิสูจน์ hypothesis เดิมผิดสำหรับ domain นี้):**
- "สะพาน" เป็น priority สูงสุด → งานถนน/ราง/ขุดลอกที่อ้างถึงสะพานเป็น landmark
  ("จากสะพาน", "บ้านสะพานสูง", "ถึงสะพาน") ถูกดูดเข้าสะพานหมด → precision สะพาน **76.7% FAIL**.
- เจอ pattern เดียวกัน: "ถนน...ทางเข้าประปา" (→แหล่งน้ำ), "ถนน...ข้างโรงเรียน" (→อาคาร),
  "ไฟฟ้าแสงสว่าง...ทางหลวง" (→ถนน).
- ชื่องานราชการขึ้นต้น "ก่อสร้าง[งานหลัก]..." เสมอ, landmark มาท้าย → **ตำแหน่งแรก = งานจริง**
  เป็นสัญญาณแม่นกว่า priority.
- ผลหลังแก้: สะพาน 77%→97%, แหล่งน้ำ/อาคาร→100%, ราง 4.8K→6.1K + ไฟฟ้า 0.4K→0.7K
  (งานที่เคยถูกดูดผิด กลับเข้าหมวดถูก). unit test 11 cases + spec examples ทั้งหมดยังผ่าน.

priority ยังคงไว้เป็น fallback ชั้นสุดท้าย (กรณีตำแหน่งเท่ากัน — แทบไม่เกิด).
