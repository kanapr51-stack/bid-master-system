# Auto-Competitor Win-Rate (Board B) — Design Spec

**วันที่:** 2026-07-11 · **สถานะ:** approved แนวทาง A โดยคุณกัญจน์ (แชท 2026-07-11)
**เจ้าของ requirement:** คุณกัญจน์ — "ไม่อยากติ๊กชื่อบริษัทเอง อยากให้ระบบคิดเองว่าบริษัทไหนจะมา กี่ % แล้วรวมเป็นโอกาสชนะเลย แต่ยังติ๊กออก/เพิ่มชื่อได้"

---

## 1. Goal

เครื่องคำนวณ "🎯 คำนวณโอกาสชนะเจาะจงคู่แข่ง" บนหน้า `/portal/job/[pid]` (Board B):
เดิมผู้ใช้ต้องติ๊กเลือกคู่แข่งเอง → เปลี่ยนเป็น **ระบบทำนายรายชื่อคู่แข่งที่น่าจะมายื่นให้อัตโนมัติ**
พร้อมเลข "โอกาสมา ~X%" ต่อบริษัท และรวมเป็น "โอกาสชนะรวม Z%" เมื่อใส่ราคา
ผู้ใช้ยังปรับมือได้: ติ๊กออก (= เจ้านี้ไม่มาแน่) / ติ๊กเพิ่มจากรายชื่อรอง หรือพิมพ์ชื่อเพิ่ม (= เจ้านี้มาแน่ 100%)

## 2. Model (คณิตศาสตร์)

ของเดิมทั้งหมดคงอยู่ — เพิ่มชั้น "โอกาสมา" ถ่วงเข้าไปก่อนรวม Gates:

- `p_attend_i` = โอกาสบริษัท i มายื่นสนามนี้ (ดู §3)
- `P_beat_i` = โอกาสเราชนะ i ถ้าเขามา — **ของเดิม** (`_company_bid_dist` + `p_beat` ใน `bid_field.py`)
- **Effective P:** `P_i_eff = 1 − p_attend_i × (1 − P_beat_i)`
  (= เขาไม่มา หรือ มาแล้วเราชนะ; `p_attend=1` → ลดรูปเป็นโมเดลเดิมเป๊ะ)
- รวมด้วย `gates_winrate([P_i_eff])` — ฟังก์ชันเดิม ไม่แก้

**Invariant สำคัญ:** เมื่อทุกบริษัท `p_attend=1.0` ผลลัพธ์ต้องเท่าโมเดลเดิมทุกหลัก (regression test บังคับ)

## 3. Attendance estimation (โอกาสมา)

ฟังก์ชันใหม่ `attendance_probs(...)` ใน `scripts/bid_field.py`:

1. ดึง auctions ของสนามนี้ด้วย `_field_auctions` (population เดียวกับตาราง winrate)
   ใช้ **ladder เดิม**: price-scope (🟢) → อำเภอ (🟡) → จังหวัด (🟠) — ผ่อนเมื่อ
   จำนวน auctions < `MIN_AUCTIONS` (5) ผ่าน `_scope_ids` เหมือน `field_and_winrate`
2. น้ำหนักต่อ auction = `recency_weight(fy)` (fy ของ auction — เอาจาก bid แรกที่มี fy)
3. `p_attend(name) = Σ weight(auctions ที่ name โผล่) / Σ weight(auctions ทั้งหมด)`
   นับ 1 ครั้ง/บริษัท/auction (dedupe ด้วย `_norm_name`)
4. clamp `p_attend` ∈ [0.05, 0.95] (ไม่มีใครมาแน่/หายแน่ 100%)
5. คัดแสดง: `p_attend ≥ 0.15` เรียงมาก→น้อย **cap 10 บริษัท**
6. auctions ทั้ง ladder < MIN_AUCTIONS → คืน `None` = ทำนายไม่ได้ (ดู §5 fallback)

คืนค่า: `{"probs": {name: p_attend}, "conf": None|('🟡','อำเภอ')|('🟠','จังหวัด'), "n_auctions": int}`

## 4. UX / Form flow (no-JS เดิม)

`_render_custom_calc_form` (`portal_views.py:532`) ปรับเป็น:

```
🎯 โอกาสชนะ (ระบบเดาคู่แข่งให้)
คาดว่าจะมายื่น:                        ← pre-ticked จากคำทำนาย
☑ หจก.ก.  โอกาสมา ~80% (ชนะ 5 งาน, ลดเฉลี่ย 12%)
☑ บ.ข.    โอกาสมา ~40%
เจ้าอื่นในพื้นที่ (นานๆ มาที — ติ๊กเพิ่มได้):   ← ของเดิม (company_tables ลบตัวที่ทำนายแล้ว)
☐ หจก.ค. (ชนะ 2 งาน, ลดเฉลี่ย 8%)
+ textarea พิมพ์ชื่อเพิ่ม (มาแน่ 100%)
ราคาที่จะยื่น: [____] [คำนวณโอกาสชนะ]
```

ผลลัพธ์ (หลัง submit): ต่อแถว `ชื่อ — โอกาสมา X% · ถ้ามา ชนะเรา Y%` + `🎯 โอกาสชนะรวม: Z%`
+ note ภาษาบ้านๆ ว่าเลขมาจากประวัติจริง เป็นการประมาณ

**Tick semantics:**
- ติ๊กจากกลุ่ม "คาดว่าจะมายื่น" → ใช้ `p_attend` ที่ทำนาย
- ติ๊กจากกลุ่มรอง / พิมพ์เพิ่ม → `p_attend = 1.0` (ผู้ใช้ยืนยันว่ามา)
- ติ๊กออก → ตัดออกจากการคำนวณทั้งหมด (เจ้านี้ไม่มา)

**Pre-tick state:** GET ครั้งแรก (ไม่มี calc params) → ติ๊กตามคำทำนาย;
หลัง submit → ติ๊กตามที่ผู้ใช้ส่งมา (เคารพการติ๊กออก ไม่ re-tick)

**Flow เดิมไม่แตะ:** POST `/portal/job/calc` → redirect GET พร้อม `calc_*` params →
`job_detail` คำนวณ server-side. คำทำนาย attendance **recompute ตอน GET** (deterministic)
ไม่ต้องเพิ่ม URL param — ชื่อที่ติ๊กมา ถ้าอยู่ใน **predicted set = รายชื่อที่แสดงในกลุ่ม
"คาดว่าจะมายื่น" (ผ่าน threshold+cap แล้วเท่านั้น)** ใช้ p ที่ทำนาย นอกนั้น (กลุ่มรอง/พิมพ์เพิ่ม) = 1.0

## 5. Fallback / edge cases

- ทำนายไม่ได้ (ข้อมูล < MIN_AUCTIONS ทั้ง ladder) → ฟอร์มหน้าตาแบบเดิม (ไม่มี pre-tick)
  + note "ข้อมูลสนามนี้ยังบาง — ระบบเดารายชื่อไม่ได้ เลือกเองได้ด้านล่าง"
- ladder ผ่อน → ป้าย conf เดิม (🟡 อิงอำเภอ / 🟠 อิงจังหวัด) ใต้กลุ่ม "คาดว่าจะมายื่น"
- `calc_custom_winrate` (`cgd_intel.py:867`) รับ param ใหม่ `attend_probs: dict|None`
  (default None = ทุกคน 1.0 → พฤติกรรมเดิม 100% — caller เก่า/test เก่าไม่พัง)
- breakdown เพิ่ม field `attend_pct` (None = มาแน่)

## 6. Touchpoints (surgical)

| ไฟล์ | แก้อะไร |
|---|---|
| `scripts/bid_field.py` | + `attendance_probs()` (ฟังก์ชันใหม่ ไม่แตะของเดิม) |
| `scripts/cgd_intel.py` | `calc_custom_winrate` + param `attend_probs`; effective-P ก่อนเข้า Gates; `intel_context` เพิ่ม key `predicted_attendees` |
| `scripts/portal_views.py` | `job_detail` ส่ง attend map เข้า calc; `_render_custom_calc_form` render 2 กลุ่ม + pre-tick + attend% ใน breakdown |
| `dashboard/web` | **ไม่แตะ** (relay JSON อยู่แล้ว — ฝั่ง engine render HTML เอง) |
| `scripts/bms_api.py` | **ไม่แตะ** (form flow เดิม) |

## 7. Tests + Success criteria (verifiable)

1. `test_winrate.py` เดิมผ่านครบ (calc เดิมไม่มี attend_probs → เลขเดิมเป๊ะ)
2. Unit ใหม่ (`test_attendance.py`): synthetic auctions → p_attend ตรงมือคำนวณ;
   recency ถ่วงถูก; clamp/threshold/cap ทำงาน; < MIN_AUCTIONS → None
3. Effective-P: `p_attend=1.0` ทุกตัว → `overall_win_pct` เท่าโมเดลเดิมทุกหลัก;
   `p_attend=0.05` → กระทบรวม < 3 จุด% (เจ้าที่แทบไม่มา แทบไม่กด)
4. Render: GET แรก pre-tick ตามทำนาย; submit แบบติ๊กออก 1 เจ้า → ไม่ re-tick
5. งานจริง ≥ 1 งานบน Board B (จังหวัดเป้าหมาย): รายชื่อทำนาย non-empty,
   p_attend สมเหตุผล (Σ p_attend ≈ ค่าเฉลี่ยผู้ยื่น n_mean ±50%), หน้าไม่พัง

## 8. Out of scope (YAGNI)

- ไม่ auto-เดาราคายื่น (ผู้ใช้กรอกเอง — ml_band มีการ์ดแยกอยู่แล้ว)
- ไม่แตะการ์ด LINE / ตารางโอกาสชนะตามจำนวนผู้ยื่น (คนละการ์ด)
- ไม่ทำ per-company ML attendance model (นับความถี่ถ่วง recency พอ — เพิ่ม ML เมื่อมี evidence ว่าไม่แม่น)
