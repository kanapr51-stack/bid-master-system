# Custom Win% Calculator (เจาะจงคู่แข่ง) — Design Spec

**Date:** 2026-06-22
**Requested by:** คุณกัญจน์
**Status:** Approved (brainstorming complete), ready for implementation plan

## 1. Problem / Goal

ระบบทำนายราคาปัจจุบัน (`cgd_intel.py` + `bid_field.py`) ตอบคำถาม 2 แบบ:
1. "ราคาแนะนำ" (percentile ของ%ลดในประวัติพื้นที่/ประเภทงานเดียวกัน — ไม่เจาะจงบริษัท)
2. "ถ้ามีคนยื่น N คน (ไม่รู้ว่าใคร) ราคานี้ชนะกี่%" (ตาราง win%-by-N-bidders, เพิ่งทำ N+161)

คุณกัญจน์ต้องการคำถามแบบที่ 3 ที่ยังไม่มี: **"ถ้าฉันจะยื่นราคา X และคาดว่าบริษัท A, B จะมาประมูลด้วย — โอกาสชนะของฉันคือเท่าไหร่"** — เจาะจงทั้งราคาที่ตัวเองจะยื่นและตัวคู่แข่ง ไม่ใช่สถิติ generic

## 2. Where it lives

อยู่ในหน้า `/portal/job` เดิม (ไม่ใช่หน้าใหม่แยก) — ต่อจากตาราง win%-ladder ที่มีอยู่แล้ว เพื่อให้ผู้ใช้เห็นทั้งบริบทเดิม (ราคาแนะนำ + win% ทั่วไป) และผลคำนวณเจาะจงในที่เดียว

แสดงเฉพาะเมื่องานนั้นมี `company_tables` อยู่แล้ว (มีคู่แข่งให้เลือกอย่างน้อย 1 บริษัท) — ถ้าพื้นที่ไม่มีข้อมูลคู่แข่งเลย ไม่ต้องแสดงฟอร์มนี้ (ไม่มีอะไรให้เลือก)

## 3. UI / Form Design

ฟอร์มใหม่ (plain HTML `<form method="post">`, **ไม่มี JavaScript** — สอดคล้องกับสถาปัตยกรรมเดิมของ portal ทั้งหมด):

```
🎯 คำนวณโอกาสชนะเจาะจง

คู่แข่งที่คาดว่าจะมา (เลือกจากบริษัทในพื้นที่นี้):
☐ หจก.ABC (ชนะ 5 งาน, ลดเฉลี่ย 14%)
☐ หจก.XYZ (ชนะ 2 งาน, ลดเฉลี่ย 22%)
☐ บริษัท DEF (ชนะ 1 งาน, ลดเฉลี่ย 8%)

หรือพิมพ์ชื่อบริษัทอื่นเพิ่ม (1 ชื่อ/บรรทัด):
[textarea]

ราคาที่จะยื่น: [input] บาท

[คำนวณโอกาสชนะ]
```

- รายชื่อ checkbox มาจาก `company_tables` ที่ resolve ไว้แล้วสำหรับงานนี้ (รวมทุก scope block, dedupe ด้วยชื่อ normalized — บริษัทเดียวอาจโผล่ทั้งบล็อกตำบลและอำเภอ)
- Checkbox `value` = ชื่อบริษัท (ไม่ใช่ tin — เพราะ tin อาจ resolve ไม่ได้สำหรับบางบริษัท แต่ชื่อใช้คำนวณได้เสมอ)
- Textarea สำหรับชื่อที่ไม่อยู่ในลิสต์ — split ด้วย newline, trim, ตัดบรรทัดว่าง
- Submit → POST ไป route ใหม่ `/portal/job/winrate_calc` พร้อม `t` (token), `pid` (project_id), `competitors[]` (checkbox values ที่ติ๊ก), `extra_names` (raw textarea), `my_price`
- Route คำนวณแล้ว **re-render หน้า `/portal/job` เดิมทั้งหน้า** (ไม่ใช่ partial/AJAX — ไม่มี JS) พร้อมผลลัพธ์แสดงต่อจากฟอร์ม + ฟอร์ม pre-fill ด้วยค่าที่กรอกไว้ (ให้แก้ไขแล้วคำนวณใหม่ได้สะดวก)

## 4. Computation Model

### 4.1 แปลงราคาผู้ใช้ → %ส่วนลด
```
my_discount_pct = (budget - my_price) / budget * 100
```
ถ้า `my_price >= budget` → `my_discount_pct = 0` (ไม่มีส่วนลด, ยังคำนวณต่อได้ปกติ — ไม่ error)
ถ้า `my_price <= 0` หรือ parse ไม่ได้ → return error ให้ผู้ใช้กรอกใหม่ (ห้ามคำนวณราคาที่ไม่สมเหตุสมผล)

### 4.2 สถิติต่อคู่แข่ง

สำหรับคู่แข่งที่ "ติ๊กเลือก" จากลิสต์ — ใช้ `{games, median, p25, p75}` ที่ `_company_stats_from_rows()` คำนวณไว้แล้วใน `company_tables` (ไม่ต้อง query ใหม่)

สำหรับคู่แข่งที่ "พิมพ์เพิ่ม" (ชื่อ free text) — ต้อง resolve ใหม่:
1. normalize ชื่อด้วย `portal_views._norm_name()` (logic เดียวกับทุกจุดในระบบ)
2. ค้นใน `rows` ของ **scope ที่กว้างที่สุดที่งานนี้ resolve ได้** (ใช้ `rows` ของบล็อกสุดท้าย/กว้างสุดใน `company_tables` — เช่นถ้างานนี้มีทั้งบล็อกตำบล+อำเภอ ใช้ rows ของอำเภอ เพราะครอบคลุม rows ของตำบลอยู่แล้ว ไม่ต้อง query ซ้ำหลายรอบ) ว่ามีบริษัทชื่อนี้ชนะบ้างไหม
3. ถ้าเจอ ≥2 เกม → ใช้ `_company_stats_from_rows()` เหมือนกัน
4. ถ้าไม่เจอเลย หรือเจอ <2 เกม → **fallback ใช้ค่าเฉลี่ยพื้นที่** (scope block's `p25`/`median`/`p75` ที่คำนวณรวมทุกบริษัทอยู่แล้ว, ตัวเดียวกับที่ใช้ทำนายราคาทั่วไป) — ติดป้าย `has_history: False` ให้ render แสดงคำเตือน

### 4.3 โอกาสที่คู่แข่ง 1 รายจะชนะเรา

ใช้ 3 จุดของ distribution คู่แข่ง `(p25, 25%), (median, 50%), (p75, 75%)` เป็น CDF แบบ piecewise-linear บนแกน %ส่วนลด แล้วประเมิน `CDF(my_discount_pct)`:

- ถ้า `my_discount_pct` อยู่ระหว่างจุดที่รู้ 2 จุด → interpolate เชิงเส้นตรงระหว่าง 2 จุดนั้น
- ถ้า `my_discount_pct < p25` → extrapolate ด้วย slope เดียวกับช่วง p25↔median, **clamp ไม่ให้ต่ำกว่า 5%** (กัน "0% โอกาสเขาชนะ" ซึ่งมั่นใจเกินจริงจาก sample เล็ก)
- ถ้า `my_discount_pct > p75` → extrapolate ด้วย slope เดียวกับช่วง median↔p75, **clamp ไม่ให้เกิน 95%**
- `win_pct_against = round((1 - CDF(my_discount_pct)) * 100)` — นี่คือโอกาสที่ **คู่แข่งรายนี้ชนะเรา** (เขาลดลึกกว่าเรา = เขาชนะ — ราคาต่ำสุดชนะ) ตรงกับที่แสดงในหน้าผลลัพธ์ว่า "หจก.ABC ชนะคุณ ~X%". โอกาส**เรา**ชนะคู่แข่งรายนี้ = `100 - win_pct_against` = `CDF(my_discount_pct) * 100`

⚠️ **เคยเขียนผิดทิศตอน draft แรก** (label บอกว่าเป็นโอกาสเราชนะ ทั้งที่สูตรคือโอกาสเขาชนะ) — แก้ก่อนเขียนโค้ดจริงแล้ว ดู §4.4 ที่ใช้ค่านี้ถูกทิศ

นี่คือ piecewise-linear interpolation อย่างง่าย **คนละโมเดลกับ k_mid/power-law ที่ใช้ในตาราง win%-by-N-bidders เดิม** (โมเดลเดิมใช้ mean/sd ของจำนวนผู้ยื่น ไม่มีข้อมูลระดับบริษัท) — เป็นฟังก์ชันใหม่แยกเฉพาะ ไม่ปนกับโค้ดเดิม

### 4.4 รวมหลายคู่แข่งเป็น 1 ค่า

```
overall_win_pct = product((100 - win_pct_against_i) / 100 for each selected competitor) * 100
```
(`100 - win_pct_against_i` = โอกาส**เรา**ชนะคู่แข่งรายนั้นรายเดียว — คูณทุกรายเข้าด้วยกัน = โอกาสเราชนะ**ทุกราย**พร้อมกัน)

สมมติแต่ละบริษัทตัดสินใจราคาอิสระจากกัน (independence) — สมมติฐานเดียวกับที่โมเดล N-bidders เดิมใช้อยู่แล้ว ไม่ใช่ของใหม่

ถ้าไม่ติ๊ก/พิมพ์คู่แข่งเลย → ไม่คำนวณ, render ข้อความ "เลือกคู่แข่งอย่างน้อย 1 บริษัท หรือดูตาราง win% ทั่วไปด้านบนแทน"

## 5. ข้อจำกัดที่ต้องบอกผู้ใช้ตรงๆ (แสดงในหน้าผลลัพธ์)

สถิติคู่แข่งที่มีอยู่ (`median`/`p25`/`p75`) คำนวณ**จากเกมที่บริษัทนั้นชนะเท่านั้น** — ไม่ใช่จากทุกครั้งที่เขายื่นซอง (ข้อมูลราคาที่ยื่นแล้วไม่ชนะมีอยู่ใน `bid_results.price_proposal` แต่ระบบยังไม่ได้ดึงมาคำนวณแยกเป็นสถิติ "ทุกครั้งที่ยื่น") ตัวเลขนี้บอก "เวลาเขาชนะ เขาลดลึกแค่ไหน" เป็น proxy ที่ดีที่สุดที่มีตอนนี้ ไม่ใช่ความถูกต้อง 100% — ใส่ disclaimer สั้นๆในหน้าผลลัพธ์ (ไม่ปิดบัง) เช่น "*อิงจากสถิติตอนที่บริษัทนั้นชนะในอดีต ไม่ใช่ทุกครั้งที่เขายื่นซอง*"

ปรับปรุงให้ใช้สถิติ "ทุกครั้งที่ยื่น" (ไม่ใช่แค่ตอนชนะ) เป็น **future work** — นอกสโคปนี้ (YAGNI, ต้องมาดูว่า `bid_results` coverage พอไหมก่อน)

## 6. Data Flow / Components

| Component | File | หน้าที่ |
|---|---|---|
| `calc_custom_winrate(rows, scope_block, my_price, budget, selected_names, extra_names)` | `cgd_intel.py` (ฟังก์ชันใหม่) | core logic ข้อ 4 — pure function, รับ `rows` (จาก `_fetch_scope` ที่ resolve ไว้แล้ว) + `scope_block` (สถิติรวมพื้นที่ สำหรับ fallback) คืน `{overall_pct, my_discount_pct, breakdown: [{name, win_pct_against, median, p25, p75, has_history}]}` หรือ `None` ถ้า input ไม่ถูกต้อง |
| `job_detail()` ส่วนขยาย | `portal_views.py` | ถ้ามี POST data → เรียก resolve scope ใหม่ (เหมือนที่ `intel_context()` ทำ) + `calc_custom_winrate()` แล้วแนบผลเข้า dict ที่ส่งให้ `render_job_page()` |
| `_render_custom_calc_form(company_tables, result=None, prefill=None)` | `portal_views.py` (ฟังก์ชันใหม่) | render ฟอร์ม + ผลลัพธ์ (ถ้ามี) |
| `POST /portal/job/winrate_calc` | `bms_api.py` (route ใหม่) | รับ form data → เรียก `job_detail()` แบบมี calc params → render หน้าเดิมกลับ |

ไม่แก้ schema/DB — ใช้ข้อมูลที่มีอยู่แล้วทั้งหมด (`rows`/`company_tables`/scope stats)

## 7. Edge Cases

| กรณี | พฤติกรรม |
|---|---|
| ไม่เลือก/พิมพ์คู่แข่งเลย | แสดงข้อความเตือน ไม่คำนวณ |
| `my_price` ว่าง/parse ไม่ได้/≤0 | แสดงข้อความเตือนให้กรอกราคาใหม่ |
| คู่แข่งพิมพ์เอง ไม่มีประวัติในพื้นที่ | fallback ค่าเฉลี่ยพื้นที่ + ป้าย "ไม่มีประวัติเฉพาะบริษัทนี้" |
| คู่แข่งมีประวัติ <2 เกม (IQR คำนวณไม่ได้) | เหมือนข้างบน — fallback ค่าเฉลี่ยพื้นที่ |
| งานไม่มี `company_tables` เลย (พื้นที่ไม่มีข้อมูลคู่แข่ง) | ไม่แสดงฟอร์มนี้เลย |
| เลือกคู่แข่งซ้ำ (ติ๊ก + พิมพ์ชื่อเดียวกัน) | dedupe ด้วยชื่อ normalized ก่อนคำนวณ — นับครั้งเดียว |
| error ใดๆระหว่างคำนวณ | graceful — ไม่ทำหน้า `/portal/job` พัง (เหมือนทุกจุด intel เดิมที่ wrap try/except) |

## 8. Testing Plan

- `test_calc_custom_winrate_*` (ใน `test_cgd_intel.py`): unit test `calc_custom_winrate()` — เคสมีประวัติ/ไม่มีประวัติ/หลายคู่แข่งรวมกัน/extrapolate เกิน p25-p75/clamp 5%-95%/dedupe ชื่อซ้ำ/ไม่มีคู่แข่งเลย
- `test_render_job_page_custom_calc_form*` (ใน `test_portal_views.py`): render ฟอร์ม checkbox ครบ + textarea + ผลลัพธ์แสดง disclaimer ครบ
- `test_bms_follow.py` หรือไฟล์ route test ที่เหมาะสม: POST route ใหม่ทำงานได้ (manual/smoke เหมือน Task 6 ของแผนก่อนหน้า ถ้าไม่มี automated route test ในระบบ)

## 9. Out of Scope (เลื่อนไว้)

- สถิติ "ทุกครั้งที่ยื่น" (ไม่ใช่แค่ตอนชนะ) — future work
- Joint/correlated competitor modeling (ตอนนี้ independence assumption) — เพียงพอสำหรับ MVP
- Autocomplete แบบ JS (ระบบไม่มี JS เลย คงไว้)
