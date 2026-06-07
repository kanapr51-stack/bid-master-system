# MOI/พิกัด Location Disambiguation — Design Spec

**วันที่:** 2026-06-07 · **สถานะ:** APPROVED 9.7/10 (System Architect review โดยกัญจน์ + 3 action items) · ต่อยอด [`tambon-competitor-intel`](2026-06-07-tambon-competitor-intel-design.md)

## เป้าหมาย
ปลดล็อก intel ระดับตำบลให้ **แม่นจริง** — แก้ "ตำบลซ้ำอำเภอ" (โพนทอง = บ้านแพง + เรณูนคร = พื้นที่ครอบครัว) ที่ปัจจุบัน degrade เป็นจังหวัด ทั้งที่ข้อมูลระบุได้

**Evidence (พ่อยืนยัน 2026-06-07):** (1) intel มีประโยชน์จริง (2) อยากเห็นระดับตำบลที่เป๊ะ → evidence-backed (ดู [[project_value_principle]])

## หลักการ (System Architect review)
- **Authoritative > Derived:** MOI code (ทางปกครองโดยตรง) เป็น truth ชั้นสูงสุด; lat/lng (อนุมาน) เป็นชั้นรอง
- **Persist raw / compute derived (action #1):** เก็บลง DB เฉพาะ raw (district_moi_id, moi_name, lat, lng) — `amphoe`/`confidence`/`source`/`trace` เป็นผลของ algorithm → **runtime-compute เสมอ ห้าม persist** (กัน stale เมื่อ threshold/logic เปลี่ยน)
- **ใช้ข้อมูลที่มีให้คุ้มก่อนสร้าง dependency:** source หลักได้ฟรีจาก API call ที่ resolve เรียกอยู่แล้ว (0 call เพิ่ม — INC-001)
- **TIS = enhancement ไม่ใช่ blocker (action #2):** lat/lng แก้ pain ได้เลย → ship ก่อน, MOI decode มาทีหลัง
- **Auditability:** resolve คืน `resolution_trace` ทุกครั้ง (BMS = decision support)

## Phasing (action #2)
| Phase | ทำอะไร | ผล |
|---|---|---|
| **A (rollout เลย)** | capture (MOI+latlng+swap fix) · reverse_geocode · resolve chain (lat/lng เป็นชั้นบนสุดที่ decode ได้) · select(amphoe) · backfill · TDD | แก้ pain "degrade จังหวัด" ได้ทันที |
| **B (enhancement)** | source/build TIS table → decode `district_moi_id` → **promote MOI เป็นชั้น 1** | coverage/ความแม่นเพิ่ม (ไม่ re-fetch — district_moi_id เก็บไว้ตั้งแต่ A) |

> Phase A เก็บ `district_moi_id` ลง DB แล้ว (ฟรี) แต่ยัง **ไม่ decode** จน Phase B มี TIS table

## Core fix: หยุดทิ้ง location จาก getProcurementDetail
งานเป้าหมายที่ resolve ตำบล (`Sebastian_Enrichment_Worker.py:397` → `jm.resolve_tambon` → `tambon_from_api`) อ่านแค่ `moiName` **แล้วทิ้ง** `district_moi_id` + `lat/lng` ใน response เดียวกัน

→ เปลี่ยนเป็น `process5_http_client.get_procurement_detail` (ตัวเต็ม) แล้ว **persist `moi_name` + `district_moi_id` + `lat/lng` (แก้ swap) ลง `project_locations`** — **0 API call เพิ่ม**

> ⚠️ **lat/lng swap bug:** ปัจจุบัน `latitude` เก็บค่า longitude (verify: สะเดียง เพชรบูรณ์ → latitude=101.13 = lng). thai_geo_raw ถูกต้อง (กทม. lat=13.75) → ต้องสลับเฉพาะตอน capture จาก API

## resolve_location(project_id, project_name, dept_name, conn) → dict
**runtime-compute ทั้งหมด** (ไม่ persist). คืน:
```
{tambon, amphoe, location_confidence, source, resolution_trace}
```
ไล่ชั้น แม่น→หยาบ:

| ชั้น | source | ตำบล | อำเภอ | location_confidence | Phase |
|---|---|---|---|---|---|
| 1 `moi` | `district_moi_id` → ชื่ออำเภอ (TIS) | `moi_name` | TIS lookup | HIGH | **B** |
| 2 `geo` | lat/lng reverse-geocode | `moi_name`/nearest | nearest อำเภอ | dist<500m HIGH · <2km MED · else LOW | **A** |
| 3 `tambon` | ตำบลไม่ซ้ำในจังหวัด | name/dept | geo unique | HIGH | A |
| 4 `dept` | dept → ตำบลหน่วยงาน → อำเภอ | name | dept-derived | MEDIUM | A |
| 5 `province` | degrade | — | — | LOW | A |

`resolution_trace` = list ของ attempt เช่น `["moi: no table (phaseA)", "geo: nearest=บ้านแพง dist=312m → HIGH"]` → log + คืนค่า (audit "ทำไม Sebastian บอกบ้านแพง")

## Components
### `scripts/geo_reverse.py` — `reverse_geocode(lat, lng) -> (province, amphoe, tambon, distance_km)`
haversine nearest subdistrict ใน `thai_geo_raw.csv` (7,426 จุด, โหลด module-level ครั้งเดียว). O(n)/call (D0 volume ต่ำ; KDTree ภายหลังถ้าจำเป็น)

### `cgd_intel.resolve_location(...)` — orchestrate ชั้น 1-5 (อ่าน project_locations raw), runtime compute + trace
### `cgd_intel.select_competitors(province, tokens, tambon, amphoe, conn)` — รับ amphoe (เลิก derive ambiguous) → `WHERE subdistrict=tambon AND district=amphoe` → fallback อำเภอ → จังหวัด
### `intel_lines(province, project_name, dept_name, project_id, conn)` — ส่ง project_id เพิ่ม

## confidence — compute + log + audit (action #3, ยังไม่โชว์ UI)
threshold (500m/2km) **ยังไม่ calibrate** → Phase 1 แค่ log (`source=geo distance=312m confidence=HIGH`) เก็บ 100-200 งาน → วัด HIGH/MED/LOW ผิดกี่ % → ค่อยเปิดบนการ์ด. **ห้ามโชว์ confidence บนการ์ดจนกว่า calibrate** (กัน user เชื่อ HIGH ที่ยังไม่ validate)

## Backfill (Phase A)
`scripts/backfill_location.py` ครั้งเดียว: งานเป้าหมายที่ยังเปิด + ไม่มี district_moi_id → `get_procurement_detail` low-rate (sleep ≥2s, N น้อย, cooldown ตาม INC-001) → persist raw → followed 4 งานได้ทันที

## Schema
`project_locations` มี `district_moi_id`/`moi_name`/`latitude`/`longitude` ครบ → **ไม่ต้อง migrate**. **ไม่แตะ column `location_confidence` เดิม** (เป็นของ enrichment hard/soft/unknown คนละความหมาย) — confidence ของ intel = runtime ไม่เก็บ

## Edge / Safety
- ไม่มี latlng + (Phase A) ไม่ decode code → ชั้น 3-5 (tambon/dept/province)
- (Phase B) TIS name ไม่ match cgd_winners → ตกชั้น 2 lat/lng เงียบ
- reverse_geocode ระยะไกล → LOW แต่ยังใช้ (ไม่ทิ้ง) + trace บันทึก
- ทุก resolve ห่อ try/except → degrade province ไม่ทำ intel พัง

## Testing (TDD)
1. `reverse_geocode`: โพนทอง-บ้านแพง→บ้านแพง · โพนทอง-เรณูนคร→เรณูนคร · คืน distance
2. `resolve_location` ไล่ชั้น (Phase A): latlng→ชั้น2 ตาม distance · ตำบลไม่ซ้ำ→ชั้น3 · dept→ชั้น4 · เปล่า→ชั้น5 LOW · **resolution_trace ครบทุก attempt**
3. confidence จาก distance (500m/2km boundary)
4. `select_competitors(amphoe)` query แม่น (โพนทองบ้านแพง ไม่ปนเรณูนคร)
5. capture persist (swap แก้ถูก, persist raw เท่านั้น — ไม่มี amphoe/confidence ใน DB)
6. backfill graceful (rate-limit + N น้อย)

## Rollback
revert capture (กลับ tambon_from_api), ลบ geo_reverse, resolve_location คืน province เดิม. additive ทั้งหมด ไม่แตะ schema

## Future (Phase B+)
- TIS-1099 table → MOI ชั้น 1 (source: build/หา, verify name match cgd_winners)
- calibrate confidence → โชว์บนการ์ด / Sebastian อ้างอิง ("คู่แข่งนี้แข็งที่บ้านแพง · conf 98%")
- KDTree เร่ง reverse_geocode · persist resolved location (ถ้า audit ต้องการ + logic นิ่งแล้ว)
