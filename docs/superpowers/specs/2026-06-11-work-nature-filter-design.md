# Spec: Work-Nature Filter (จ้างก่อสร้าง vs ซื้อ) — แก้ช่วงคาดราคากว้างเกินไป

**วันที่:** 2026-06-11 · **สถานะ:** approved (กัญจน์ 2026-06-11)

## ปัญหา
ช่วง %ส่วนลดที่คาดกว้างเกินใช้งานไม่ได้ (เช่น งาน 69059327097 ต.นาทม → ลด 5–32% → ราคา 770k–1.08M).
สาเหตุจริง: reference set เอา **งาน "ซื้อ" (วัสดุ: เหล็ก/คอนกรีตผสมเสร็จ ลด ~0–2%)** มาปนกับ
**งาน "จ้างก่อสร้างถนน" (ลด ~25–38%)** เพราะชื่อมี "คอนกรีต/ถนน" เหมือนกัน — คนละลักษณะงาน (ซื้อ vs จ้าง).

## หลักฐาน (นครพนม+บึงกาฬ 3ปี, competitive road/concrete)
| reference | n | p25 | median | p75 |
|---|---|---|---|---|
| ปนกัน | 982 | 0.3% | 10.3% | 32.7% |
| เฉพาะ "ซื้อ" | 111 | 0.1% | 2.8% | 14% |
| เฉพาะ "จ้าง" | 870 | 0.4% | 13.2% | 34.3% |

งานกำกวม (มีทั้ง ซื้อ+จ้าง) = 1 งาน → แยกสะอาด.

## Design
เพิ่มมิติ "ลักษณะงาน" คู่กับ `road_subtype` ที่มีอยู่:

1. **`work_nature(project_name)`** → `'purchase'` (ชื่อมี "ซื้อ") | `'construction'` (อื่นๆ).
   classifier เล็ก คู่กับ `road_subtype`.
2. **`intel_context`** คำนวณ nature ของงานจริง → ส่งผ่าน `_build_intel` → `_fetch` (เหมือน subtype).
3. **`_fetch`** กรอง reference ให้ตรง nature:
   - construction → `project_name NOT LIKE '%ซื้อ%'`
   - purchase → `project_name LIKE '%ซื้อ%'`
   - None → ไม่กรอง (back-compat)
4. **`competitor_trend._area_where`** กรองแบบเดียวกัน (recency series สอดคล้อง).

## Edge cases
- งานกำกวม (ซื้อ+จ้าง, 1 งาน) → มี "ซื้อ" = purchase → ตัดออกจาก construction. negligible.
- งานจริง nature ไม่ชัด → default `construction` (ตัด "ซื้อ"). งานที่ติดตามส่วนใหญ่เป็นก่อสร้าง.

## ผลคาด
งานถนนนาทม → ~25–38% (median ~36%) แทน 2–38%.

## Step 2: Contested-Focus Prediction (approved 2026-06-11)

### หลักฐาน (research: docs/research_discount_factors_2026_06_11.md)
ส่วนลด **bimodal**: งานไม่มีคู่แข่ง (~0%) vs แข่งจริง (~32–36%). งานใหญ่/อบจ/>10ลบ. = โหมดต่ำทั้งหมด
→ โฟกัสกลุ่มแข่งจริงจะตัดออกอัตโนมัติ (ไม่ต้องกรอง agency/budget แยก). เคสกัญจน์ อบต 1-3ลบ.: 82% แข่งจริง ลด 31-42%.

### Design
1. `CONTESTED_MIN_DISCOUNT = 15` (config) — งานถนนชนะด้วยส่วนลด <15% ≈ ไม่มีคู่แข่งจริง (gap ใน data ~9-17%)
2. `_fetch(contested_only=True)` → เพิ่ม `discount_pct >= 15`. thread ผ่าน `_fetch_scope` → `_build_intel` (เฉพาะ path คาดราคา) + `competitor_trend`
3. บล็อก + คาดราคา ใช้กลุ่ม contested. label "(งานแข่งจริง)". เพิ่ม median ใน predict_winning_price/predict_lines
4. Output:
```
🏘 ในตำบลนาทม (งานแข่งจริง) — 7 งาน
   📊 ส่วนลด 32–38%
💵 ถ้ามีคู่แข่ง ผู้ชนะลด: 32–38% (ปกติ ~35%)
   → ราคา 707k–775k (ปกติ 741k)
```
5. **Fallback:** ไม่มี contested ในพื้นที่เลย (แข่งน้อยจริง) → `intel_context` retry contested_only=False + ป้าย "⚠️ พื้นที่นี้แข่งขันน้อย"
6. ขอบเขต: เฉพาะ path คาดราคา D0. analyze_bidders Round 2 ไม่แตะ

### Test
- `_fetch(contested_only=True)` ตัด discount<15 ออก
- `predict_winning_price`/`predict_lines` มี median
- `_build_intel(contested_only=True)` label งานแข่งจริง + prediction จากกลุ่ม contested
- `intel_context` fallback เมื่อไม่มี contested → ป้ายแข่งน้อย

## Test (TDD)
- `work_nature`: "ประกวดราคาซื้อคอนกรีตผสมเสร็จ..."→purchase · "จ้างก่อสร้างถนน..."→construction
- `_fetch` nature=construction → ตัดงาน "ซื้อ" ออก · nature=purchase → เหลือเฉพาะ "ซื้อ"
- regression: เดิม (nature=None) ไม่เปลี่ยน
