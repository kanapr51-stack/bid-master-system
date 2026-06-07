# MOI/พิกัด Location Disambiguation — Design Spec

**วันที่:** 2026-06-07 · **สถานะ:** APPROVED (brainstorm + System Architect review โดยกัญจน์, 90%→ปรับ MOI ชั้น 1 + confidence) · ต่อยอด [`tambon-competitor-intel`](2026-06-07-tambon-competitor-intel-design.md)

## เป้าหมาย
ปลดล็อก intel ระดับตำบลให้ **แม่นจริง** — แก้ปัญหา "ตำบลซ้ำอำเภอ" (โพนทอง = บ้านแพง + เรณูนคร = พื้นที่ครอบครัว) ที่ปัจจุบัน degrade เป็นจังหวัด ทั้งที่ข้อมูลระบุได้

**Evidence (พ่อยืนยัน 2026-06-07):** (1) intel มีประโยชน์จริง (2) อยากเห็นระดับตำบลที่เป๊ะ → enhancement นี้ evidence-backed (ดู [[project_value_principle]])

## หลักการ (System Architect review)
- **Authoritative > Derived:** MOI code (ข้อมูลทางปกครองโดยตรง) เป็น source of truth ชั้นสูงสุด; lat/lng (อนุมานจากพิกัด) เป็นชั้นรอง
- **ใช้ข้อมูลที่มีให้คุ้มก่อนสร้าง dependency:** ทุก source หลักได้มาฟรีจาก API call ที่ resolve เรียกอยู่แล้ว (0 call เพิ่ม — บทเรียน INC-001)
- **แม่น→หยาบ (graceful):** ไล่ชั้นจากแม่นสุดลงมาจนตอบได้ + เก็บ confidence ทุกชั้น (BMS = decision support)

## Core fix: หยุดทิ้ง location จาก getProcurementDetail
ปัจจุบันงานเป้าหมายที่ resolve ตำบล (`Sebastian_Enrichment_Worker.py:397` ผ่าน `jm.resolve_tambon` → `tambon_from_api`) อ่านแค่ `moiName` **แล้วทิ้ง** `district_moi_id` + `lat/lng` ที่อยู่ใน response เดียวกัน

→ เปลี่ยนเป็นเรียก `process5_http_client.get_procurement_detail` (ตัวเต็ม) แล้ว **persist `moi_name` + `district_moi_id` + `lat/lng` (แก้ swap) ลง `project_locations`** — **0 API call เพิ่ม**

> ⚠️ **lat/lng swap bug:** ปัจจุบัน `latitude` เก็บค่า longitude และกลับกัน (verify: สะเดียง เพชรบูรณ์ → latitude=101.13 ซึ่งคือ lng) → ต้องสลับตอน capture

## resolve_location(project_id, project_name, dept_name) → dict
คืน `{tambon, amphoe, location_confidence, source}` — ไล่ชั้น แม่น→หยาบ:

| ชั้น | source | ตำบล | อำเภอ | location_confidence |
|---|---|---|---|---|
| 1 `moi` | `district_moi_id` → ชื่ออำเภอ (ตาราง TIS) | `moi_name` | TIS lookup | **HIGH** |
| 2 `geo` | lat/lng reverse-geocode (thai_geo_raw) | `moi_name`/nearest | nearest อำเภอ | dist<500m HIGH · <2km MEDIUM · else LOW |
| 3 `tambon` | ตำบลไม่ซ้ำในจังหวัด (thai_geo_raw) | name/dept | geo unique | HIGH |
| 4 `dept` | dept → ตำบลหน่วยงาน → อำเภอ (geo) | name | dept-derived | MEDIUM |
| 5 `province` | degrade | — | — | LOW |

**ชั้น 1 dependency (flag):** `district_moi_id` = รหัส, `cgd_winners.district` = ชื่อไทย → ต้องมีตาราง **TIS-1099 รหัสอำเภอ→ชื่อ** (`data/moi_amphoe_lookup.json`, ยังไม่มี — ต้อง source/build) + **verify ชื่อ match cgd_winners เป๊ะ** (normalize, กัน "เมืองนครพนม"≠"เมือง"). ถ้า name ไม่ match → ตกชั้น 2 อัตโนมัติ (lat/lng = safety net โดยธรรมชาติ)

## Components

### `reverse_geocode(lat, lng) -> (province, amphoe, tambon, distance_km)`
- haversine หา subdistrict centroid ใกล้สุดใน `thai_geo_raw.csv` (7,426 จุด) → คืนชื่อ 3 ระดับ + ระยะ
- O(n) ต่อ call (D0 volume ต่ำ รับได้; KDTree optimize ภายหลังถ้าจำเป็น)
- helper แยกไฟล์ `scripts/geo_reverse.py` (โหลด csv ครั้งเดียว module-level)

### `load_moi_amphoe() -> dict` (`data/moi_amphoe_lookup.json`)
- map รหัสอำเภอ (4 หลักแรกของ MOI / 6 หลักลงท้าย 00) → ชื่ออำเภอ (ตาม TIS-1099)
- ชื่อ normalize ให้ match cgd_winners (จังหวัด+อำเภอ)

### `resolve_location(...)` — orchestrate ชั้น 1-5, อ่าน `project_locations` (district_moi_id/moi_name/lat/lng)

### intel ใช้ผล
`select_competitors(province, tokens, tambon, amphoe, conn)` — รับ `amphoe` ที่ resolve ได้ (เลิก derive จาก data แบบ ambiguous) → query `WHERE subdistrict=tambon AND district=amphoe` → fallback อำเภอ → จังหวัด · `intel_lines` ส่ง `project_id` เพิ่มเพื่อ resolve_location

## Backfill (กัญจน์ approve)
สคริปต์ครั้งเดียว `scripts/backfill_location.py`: งานเป้าหมายที่ยังเปิด (qualification active) + ไม่มี district_moi_id → ยิง `get_procurement_detail` **low-rate** (sleep ≥2s, N น้อย, cooldown ตาม INC-001 envelope) → persist → followed 4 งานได้ทันที

## Schema
`project_locations` มี `district_moi_id`/`moi_name`/`latitude`/`longitude`/`location_confidence` ครบแล้ว → **ไม่ต้อง migrate** (capture เพิ่ม + intel runtime compute)

## Edge / Safety
- ไม่มี lat/lng + ไม่มี code → ชั้น 3-5 (tambon/dept/province)
- TIS name ไม่ match cgd_winners → ตกชั้น 2 (lat/lng) เงียบ — ไม่พัง
- reverse_geocode ระยะไกล (>2km) → LOW confidence แต่ยังใช้ (ไม่ทิ้ง)
- ทุก resolve ห่อ try/except — resolve พังต้อง degrade province ไม่ใช่ทำ intel พัง

## Testing (TDD)
1. `reverse_geocode`: พิกัดโพนทอง-บ้านแพง → อำเภอบ้านแพง · โพนทอง-เรณูนคร → เรณูนคร · คืน distance
2. `load_moi_amphoe` + lookup: รหัส→ชื่ออำเภอ, normalize
3. `resolve_location` ไล่ชั้น: มี code→ชั้น1 HIGH · code-name ไม่ match→ตกชั้น2 · ไม่มี code มี latlng→ชั้น2 ตาม distance · ตำบลไม่ซ้ำ→ชั้น3 · dept→ชั้น4 · เปล่า→ชั้น5 LOW
4. `select_competitors` รับ amphoe → query แม่น (โพนทองบ้านแพง ไม่ปนเรณูนคร)
5. capture persist (swap แก้ถูก) · backfill graceful (rate-limit + N น้อย)

## Rollback
revert capture (กลับไป tambon_from_api), ลบ geo_reverse/moi_amphoe_lookup, resolve_location คืน province เดิม. additive ทั้งหมด

## Future
- KDTree เร่ง reverse_geocode ถ้า volume สูง
- โชว์ location_confidence บนการ์ด / ให้ Sebastian อ้างอิง ("คู่แข่งนี้แข็งที่บ้านแพง · conf 98%")
- เก็บ resolved location ลง project_locations (audit) แทน compute ทุกครั้ง
