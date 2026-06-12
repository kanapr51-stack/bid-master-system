# Audit View v2 — Enhancements Design Spec

**วันที่:** 2026-06-12
**สถานะ:** approved design → pending implementation
**ต่อยอดจาก:** `2026-06-12-price-prediction-audit-view-design.md` (v1 deployed)

---

## 1. ปัญหา / สิ่งที่ขอเพิ่ม

หน้า `/audit` v1 ใช้งานได้แล้ว แต่กัญจน์ขอเพิ่ม 4 อย่างเพื่อ human-check ง่ายขึ้น:
1. แสดง **ชื่องาน** (ไม่ใช่แค่ project_id)
2. แสดง **stage** ว่างานถึงขั้นไหน (B0→D0→PRELIM→W0)
3. แสดง **ราคาเบื้องต้น PRELIM + คาด vs จริง(เบื้องต้น)** (ตอนนี้ไม่เก็บเลย)
4. แสดง **หมวด / หมวดย่อย / ประเภท(สร้างใหม่-ปรับปรุง) / ระบอบตลาด**

## 2. แหล่งข้อมูล (ยืนยันจาก codebase แล้ว)

| ข้อ | แหล่ง | สถานะ |
|---|---|---|
| ชื่องาน | `projects_seen.project_name` (join project_id) | มีอยู่ |
| stage | `followed_jobs.last_stage_notified` (B0/D0/PRELIM/W0, per customer→เอาก้าวหน้าสุด) | มีอยู่ |
| หมวด/ย่อย/ประเภท/ตลาด | `explain_json.classify` (subtype/work_kind/nature/market) + `inputs.work_type` | มีใน snapshot แล้ว |
| ราคา PRELIM | **ไม่มี** — provisional ไม่เขียน DB | ต้องเพิ่ม |

## 3. Data Model — เพิ่ม prelim columns (migration v127)

แยกจากคอลัมน์ทางการเด็ดขาด (กันปน official vs preliminary):

```sql
ALTER TABLE price_predictions ADD COLUMN prelim_price    INTEGER;
ALTER TABLE price_predictions ADD COLUMN prelim_in_range INTEGER;
ALTER TABLE price_predictions ADD COLUMN prelim_error_pct REAL;
ALTER TABLE price_predictions ADD COLUMN prelim_at       TEXT;
```

## 4. Capture PRELIM

- เพิ่มฟังก์ชัน `Sebastian_Customer_DB.update_prediction_prelim(project_id, prelim_price, in_range, error_pct)`
  → UPDATE เฉพาะ `prelim_*` (ไม่แตะ prediction/official)
- เรียกที่จุด prelim notification (`Sebastian_LINE_Sender.py` ราว 674 — มี `pr["lowest_price"]` + `compare_prediction_provisional` คืน in_range/error)
- fail-open: prelim save พัง → ไม่กระทบการแจ้ง prelim ปกติ
- forward-looking: เก็บเฉพาะงานที่ถึง PRELIM **หลัง deploy** (เหมือน explain v1)

## 5. Display — List (`/audit`)

คอลัมน์ใหม่: **ชื่องาน** + **stage(ป้ายไทย)** เพิ่มจากเดิม

| ชื่องาน | stage | ช่วงราคาคาด | ผลจริง(W0) |
|---|---|---|---|

- ID ยังเป็นลิงก์ (อยู่ใต้/คู่ชื่องาน)
- query: `price_predictions` LEFT JOIN `projects_seen` (name) + subquery stage จาก `followed_jobs`

## 6. Display — Detail (`/audit/{id}`)

เพิ่ม/ปรับ 3 บล็อก:

**A. หัว:** `<ชื่องาน>` + (`project_id`)

**B. บล็อก "หมวดงาน" (ใหม่):**
- หมวดงาน: work_type
- หมวดย่อย: subtype → ไทย (concrete_road=ถนนคอนกรีต, asphalt_road=ถนนแอสฟัลต์, water_*=งานน้ำ.., None=—)
- ประเภท: work_kind → (new=สร้างใหม่, reno=ปรับปรุง/ซ่อม, None=—)
- ระบอบตลาด: market → (local=ท้องถิ่น อปท., provincial=อบจ., central=ส่วนกลาง กรม, None=—)

**C. บล็อกผลประมูล — แยก 2 ชั้นชัดเจน:**
```
🟡 ราคาเบื้องต้น (ยังไม่ทางการ): {prelim_price}
   คาด {area_price_med} · เบื้องต้น {prelim_price} · ต่าง {prelim_error_pct}% [ยังไม่ทางการ]
   (ถ้าไม่มี prelim → ไม่แสดงบล็อกนี้)
───
🟢 คาด vs จริง (ทางการ W0): {actual_price} หรือ ⏳ รอผล   ← บล็อกเดิม v1
```

> วิธีคิด (classify→scope→analysis→formula) + ตารางงานอ้างอิงดิบ = คงเดิมจาก v1

## 7. Label maps (codes → ไทย) — helper เดียว reuse

```
STAGE: B0=🟣รับฟังคำวิจารณ์ · D0=🔵ประกาศ/ยื่นซอง · PRELIM=🟡ราคาเบื้องต้น · W0=🟢ประกาศผู้ชนะ
WORK_KIND: new=สร้างใหม่ · reno=ปรับปรุง/ซ่อม
MARKET: local=ท้องถิ่น(อปท.) · provincial=อบจ. · central=ส่วนกลาง(กรม)
SUBTYPE: concrete_road=ถนนคอนกรีต · asphalt_road=ถนนแอสฟัลต์ · water_dredge=ขุดลอก · water_structure=ฝาย/โครงสร้างน้ำ
```
(ค่าที่ไม่รู้จัก/None → แสดง "—" หรือ code ดิบ ไม่ crash)

## 8. YAGNI

- ❌ filter/search · ❌ backfill prelim ของเก่า · ❌ official login (คง shared secret)
- ❌ ไม่ทำให้ stage column ใน list ต้อง realtime perfect (best-effort จาก last_stage_notified)

## 9. Acceptance Criteria

- [ ] migration v127 เพิ่ม 4 prelim cols (idempotent)
- [ ] `update_prediction_prelim` เขียนเฉพาะ prelim_* — re-save prediction/official ไม่ถูกแตะ (invariant test)
- [ ] list แสดง ชื่องาน + ป้าย stage ไทย (มี name จาก projects_seen)
- [ ] detail แสดงบล็อกหมวดงาน 4 บรรทัด (จาก explain.classify) เป็นไทย
- [ ] detail แสดงบล็อก PRELIM (ถ้ามี prelim_price) แยกจากบล็อก W0 ทางการ ชัดเจน
- [ ] label ค่าที่ไม่รู้จัก/None → ไม่ crash
- [ ] dispatch Sophia: prelim_* ไม่ทำให้ official actual_price/explain เพี้ยน
