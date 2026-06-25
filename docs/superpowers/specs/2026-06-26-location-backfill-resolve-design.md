# Design: Location Backfill + Forward Resolve (province_api ตำบล/พิกัด)

**วันที่:** 2026-06-26
**สถานะ:** approved (design) → spec → plan → TDD

---

## ที่มา (Problem)

งานในกลุ่ม "ยื่นซอง" บน Board ขึ้นแค่ "จ.X" ไม่มี "ต." ต่างจากกลุ่มอื่นที่ขึ้น "ต.X จ.Y" ครบ

### Root cause
ไม่ใช่ bug ที่การ์ด — การ์ด (`bms_api.py:565`) render `location` เหมือนกันทุกกลุ่ม. ปัญหาคือ **`moi_name` (ตำบล) ว่าง** ในข้อมูล:
- งานจาก **province_api** ลงทะเบียนด้วย `enrichment_status='failed'` (placeholder — สถานะจริงอยู่ใน `qualification_status`) และ `moi_name=NULL`
- การดึง location ตัวจริง (`get_procurement_detail`) เกิดเฉพาะใน pass แจ้งเตือน (`qualify_province_api` บรรทัด 400-412) ที่มี gate `RESOLVED and is_open()` + matching on
- งานที่ไม่ผ่าน gate นั้น → ค้าง `moi_name=NULL` → board ขึ้นแค่จังหวัด

### ขนาดปัญหา (ข้อมูลจริง VPS 2026-06-26)
- **1,117 / 2,781 แถว (40%)** ใน `project_locations` มี province แต่ `moi_name=NULL` — **ทั้งหมด source=province_api**
- จังหวัด: นครพนม 750 + บึงกาฬ 367 (แค่ 2 จังหวัดเป้าหมาย)
- ช่วงเวลา: 30 พ.ค. – 24 มิ.ย. 2026 (< 1 เดือน — **ไม่ใช่** winner_history 10 ปี)
- เดือน มิ.ย. มีงานใหม่ตกหล่นเพิ่ม 42 → รอยรั่วยังไหล ถ้าไม่อุดต้นทาง

### พิสูจน์ว่า getProcurementDetail มีข้อมูลจริง (test สดงาน NULL-moi)
- `69069203920` → moi='นาทม' district_moi_id='481100' lat/lng ครบ
- `69069186724` → moi='โพนแพง' district_moi_id='480500' lat/lng ครบ
→ ข้อมูลตำบลมีใน eGP, แค่เราไม่เคยดึงมา. dept_name fallback ให้ตำบลเดียวกัน (อบต.ตั้งชื่อตามตำบล) แต่ getProcurementDetail ดีกว่า (ที่ตั้งงานจริง + อำเภอ + พิกัด + ครอบทุกหน่วยงาน)

---

## ขอบเขต (ยืนยันกับ user)

- **จังหวะ:** drain ผ่าน enrichment worker ค่อยๆ ทำ (rate-disciplined, INC-001) — ไม่ one-shot burst
- **แหล่งหลัก:** getProcurementDetail (authoritative) · dept_name = fallback (code มีอยู่แล้ว)
- **แก้ทั้ง backfill ของเก่า + งานใหม่** ด้วยกลไกเดียว

---

## สถาปัตยกรรม

เพิ่ม **pass เดียว** ใน `Sebastian_Enrichment_Worker.py` ที่กวาดงาน province_api ที่ `moi_name=NULL` → resolve location → save. selector จับทั้งของเก่า (1,117) และงานใหม่ที่ moi ว่างโดยอัตโนมัติ (self-healing).

### Component: `resolve_missing_locations(store, log, resolve_detail=None) -> int`

**Selector** (ต่อรอบ worker):
```sql
SELECT pl.project_id, ps.dept_name, pl.enrichment_attempts
FROM project_locations pl
LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
WHERE pl.source='province_api' AND pl.moi_name IS NULL
  AND pl.enrichment_attempts < 3
  AND (pl.next_retry_at IS NULL OR pl.next_retry_at <= ?)
ORDER BY pl.enrichment_attempts ASC, pl.created_at ASC
LIMIT ?   -- BMS_LOCFILL_BATCH default 8
```

**ต่องาน:**
1. `d = resolve_detail(pid)` (= `get_procurement_detail`, inject ได้เพื่อ test)
2. ถ้า `d.get("valid")` และ `d.get("moi_name")` → `save_project_location_raw(pid, d["district_moi_id"], d["moi_name"], d["latitude"], d["longitude"])` ✅ หลุด selector
3. ไม่มี moi แต่ `tambon_from_dept(dept_name)` ได้ค่า → `save_project_location_raw(pid, "", tb, "", "")` (fallback)
4. ไม่ได้ทั้งคู่ → `enrichment_attempts += 1` + `next_retry_at = now + backoff` (กัน hammer; เลิกถาวรหลัง 3 ครั้ง)
5. `sleep 1.5s` ระหว่างงาน (rate discipline)

### เสียบเข้า `main()` (หลัง Pass 3 qualify, ก่อน RSS batch)
- เคารพ **resolve-plane cooldown gate เดิม** (`_resolve_in_cooldown()`) — ถ้า cooldown active → skip ทั้ง pass
- ใช้ batch เล็ก (8/รอบ) แชร์ budget eGP กับ pass อื่น → ไม่ burst
- worker timer ~ทุก 2 นาที (เมื่อ api HEALTHY + ไม่ cooldown) → drain 1,117 ใน ~ชั่วโมง-วัน, board ทยอยเต็ม

### Board — ไม่ต้องแก้
`_portal_jobs` (`bms_api.py:435`) สร้าง `location` จาก `moi_name` + `province` อยู่แล้ว → พอ moi เต็ม การ์ดขึ้น "ต.X จ.Y" เองทุกกลุ่ม

---

## Data flow

```
enrichment worker (timer ~2 นาที, api HEALTHY + ไม่ cooldown)
  └─ Pass: resolve_missing_locations (batch 8)
       └─ getProcurementDetail(pid)
            ├─ มี moi → save_project_location_raw (ตำบล+อำเภอ+พิกัด) → หลุด selector
            ├─ ไม่มี moi + dept=อบต.X → save moi=X (fallback)
            └─ ไม่ได้ → attempts+1 + backoff (เลิกหลัง 3)
  → Board: moi_name เต็ม → "ต.X จ.Y" อัตโนมัติ
```

---

## Error handling / safety

- `get_procurement_detail` error/`valid=False` → ถือว่ายังไม่ได้ → attempts+1 + backoff (fail-safe ไม่ corrupt)
- cooldown gate (INC-001): pass skip ทันทีถ้า resolve-plane cooldown → ไม่ยิง eGP ตอน WAF ร้อน
- idempotent: moi_name เซฟแล้วหลุด selector → รันซ้ำปลอดภัย
- `enrichment_attempts` ไม่ชน RSS pass (RSS เลือก `enrichment_status='pending'`; province_api เป็น `'failed'`)

---

## Tests (TDD)

| Test | ตรวจ |
|---|---|
| resolve มี moi | mock resolve_detail คืน {valid, moi_name, district, lat, lng} → save_project_location_raw ถูกเรียกด้วยค่าตรง; row หลุด selector |
| dept fallback | resolve คืน valid แต่ไม่มี moi + dept="องค์การบริหารส่วนตำบลนาทม" → save moi='นาทม' |
| ไม่ได้ทั้งคู่ | resolve invalid + dept non-อบต → enrichment_attempts+1, next_retry_at ตั้ง, ไม่ลูปไม่จบ |
| stop หลัง 3 | enrichment_attempts=3 → ไม่อยู่ใน selector |
| selector กรอง | ข้าม row ที่ moi_name เต็มแล้ว + ข้าม source!='province_api' |
| cooldown gate | `_resolve_in_cooldown()`=True → resolve_missing_locations ไม่ถูกเรียก (หรือคืน 0 ทันที) |

### Success criteria (verifiable)
- mock detail มี moi → `save_project_location_raw` ถูกเรียก, count NULL-moi ลด
- mock dept อบต. → moi = ชื่อตำบล
- หลัง deploy + drain: `SELECT COUNT(*) ... moi_name IS NULL AND source='province_api'` ลดลงเรื่อยๆ เข้าใกล้ (เหลือเฉพาะที่ eGP ไม่มี + non-อบต, attempts=3)
- Board: `69069203920` แสดง "ต.นาทม จ.นครพนม"

---

## ตัดออก (YAGNI)

- ❌ ไม่แสดง "อำเภอ" บน board (district เป็น moiId code ต้อง resolve→ชื่อ; ขอแค่ตำบล)
- ❌ ไม่ทำ one-shot backfill script แยก (worker pass ครอบทั้งหมด)
- ❌ ไม่แตะ winner_history 10 ปี / 4 จังหวัด (คนละชุดข้อมูล)
- ❌ ไม่แก้ board render (moi เต็มแล้วขึ้นเอง)

---

## ไฟล์ที่กระทบ

| ไฟล์ | การเปลี่ยนแปลง |
|---|---|
| `scripts/Sebastian_Enrichment_Worker.py` | เพิ่ม `resolve_missing_locations()` + เสียบใน `main()` หลัง Pass 3 |
| `scripts/test_resolve_missing_locations.py` | tests ตามตารางด้านบน (ใหม่) |

reuse (ไม่แก้): `save_project_location_raw` (Customer_DB:88), `tambon_from_dept` (job_matcher:135), `get_procurement_detail` (process5_http_client), `_resolve_in_cooldown` (worker)
