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

## ออกนอกขอบเขต (Step 2 แยกทีหลัง)
หลังกรองแล้ว ช่วงอาจยังกว้าง (construction p25–p75 = 0.4–34%) เพราะมี single-bidder/งานใหญ่ลดน้อย.
การบีบ band/anchor (max = ส่วนลดลึกสุด, ช่วง ~5%) = ticket แยก ดูช่วงจริงหลังกรองก่อน.

## Test (TDD)
- `work_nature`: "ประกวดราคาซื้อคอนกรีตผสมเสร็จ..."→purchase · "จ้างก่อสร้างถนน..."→construction
- `_fetch` nature=construction → ตัดงาน "ซื้อ" ออก · nature=purchase → เหลือเฉพาะ "ซื้อ"
- regression: เดิม (nature=None) ไม่เปลี่ยน
