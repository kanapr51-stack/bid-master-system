# Price Prediction Audit View — Design Spec

**วันที่:** 2026-06-12
**สถานะ:** approved design → pending implementation
**ประเภท:** Product feature (internal/operator-facing) — explainability + human-check ของการทำนายราคา

---

## 1. ปัญหา

ทุกครั้งที่ระบบส่งการทำนายราคาให้ลูกค้า (เช่น ส่งงาน A ให้พ่อ) กัญจน์ **ไม่มีที่ดูว่า**:
- งานไหนถูกทำนายเป็นราคาเท่าไหร่ (ภาพรวมทุกการทำนายที่ส่งไป)
- กว่าจะได้ราคานั้น ระบบคิดผ่านอะไร (subtype, ระบอบตลาด, scope, ส่วนลด)
- ใช้ข้อมูลดิบอะไรอ้างอิง (งานผู้ชนะจริงกี่ราย ราคาเท่าไหร่)

ทำให้ human-check ไม่ได้ — ต้องพิมพ์ถาม Claude ทีละคำถาม ไม่รู้ว่าระบบอ้างอิงข้อมูลถูกหรือมีจุดแปลก

## 2. เป้าหมาย

หน้า **internal audit** (เฉพาะกัญจน์) ที่:
- ลิสต์ทุกการทำนายที่ส่งไป + ราคาที่ทำนาย
- คลิกงาน → เห็น **วิธีคิดเบื้องหลัง (analysis) + ข้อมูลดิบอ้างอิง (raw records)** แบบ**แช่แข็ง ณ ตอนทำนาย** (audit-grade)
- เห็น "คาด vs จริง" เมื่อประมูลเสร็จ (closed-loop)

**Success:** กัญจน์เปิดหน้านี้ ตรวจได้ภายในไม่กี่วินาทีว่า งานหนึ่งใช้ข้อมูลอ้างอิงถูกไหม / มีจุดแปลกไหม โดยไม่ต้องถาม Claude

## 3. หลักการออกแบบ (ตัดสินแล้ว)

| ประเด็น | เลือก | เหตุผล |
|---|---|---|
| หลักฐาน frozen หรือ live | **แช่แข็ง ณ ตอนทำนาย** | audit จริง = ต้องตรงกับข้อมูลที่ใช้คิดตอนนั้น ไม่ใช่ recompute (ข้อมูลโตขึ้นเรื่อยๆ) |
| surface | **หน้า internal มี auth** (เฉพาะกัญจน์) | เปิดเผย logic ตั้งราคา = ข้อมูลแข่งขัน ห้ามหลุด public |
| ชั้นหลักฐาน | **2 ชั้น: analysis + raw records** | กัญจน์ระบุชัด อยากเห็นทั้งวิธีคิดและข้อมูลดิบ |
| ความสด | prediction = real-time, closed-loop = ตามรอบ poller | อ่าน live จาก DB; ผลจริงต้องรอประมูลจบ |

## 4. Data Model

เพิ่ม 1 คอลัมน์ใน `price_predictions` (ตารางมีอยู่แล้วใน `bms_customers.db`):

```sql
ALTER TABLE price_predictions ADD COLUMN explain_json TEXT;  -- JSON snapshot, nullable
```

**โครงสร้าง `explain_json`** (เซฟตอนทำนาย — แช่แข็ง):
```json
{
  "schema_version": 1,
  "inputs": {
    "budget": 2500000, "project_name": "...", "work_type": "ถนนคอนกรีต",
    "province": "นครพนม", "tambon": "...", "amphoe": "...", "location_confidence": "HIGH"
  },
  "classify": {
    "subtype": "concrete_road",    "subtype_reason": "ชื่อมี 'คอนกรีต'",
    "work_kind": "new",            "work_kind_reason": "...",
    "market_regime": "local",      "regime_reason": "หน่วยงาน = อบต./เทศบาล"
  },
  "scope": { "level": "tambon", "n": 12, "fallback_reason": "" },
  "analysis": {
    "discount_lo": 0.22, "discount_med": 0.27, "discount_hi": 0.31,
    "floor_applied": 0.15, "competitor_top": {"name": "...", "disc": 0.28, "trend": "ขึ้น"}
  },
  "raw_records": [
    {"project_name": "...", "winner": "...", "win_price": 1980000, "discount": 0.26}
  ],
  "formula": "ราคาคาด = budget × (1 − ส่วนลด), clamp floor 15%",
  "output": { "price_lo": 1725000, "price_med": 1825000, "price_hi": 1950000 }
}
```

> ทุก field มาจากที่ `_build_intel` คำนวณอยู่แล้ว — แค่เก็บแทนที่จะทิ้ง. `raw_records` = เฉพาะงานที่ใช้จริงใน scope (หลักหน่วย–หลายสิบ record) ไม่อ้างถึง winner_history.db 2.6GB ตอน view

## 5. Capture (ตอนทำนาย)

- แก้ `cgd_intel._build_intel` (หรือจุดประกอบ prediction) ให้สร้าง `explain` dict คู่กับผลลัพธ์ปกติ
- ส่ง explain ต่อไปที่ `Sebastian_Customer_DB.save_prediction()` → `json.dumps` เก็บลง `explain_json`
- **ไม่กระทบตัวเลขที่ส่งลูกค้า** — เป็น side-output เพิ่มอย่างเดียว
- ถ้า build explain ล้มเหลว → เก็บ null + log (ห้ามทำให้ prediction/ส่งงานพัง — fail-open สำหรับ explain เท่านั้น)

## 6. API (bms_api — FastAPI, มี auth)

| endpoint | คืนอะไร |
|---|---|
| `GET /audit?key=<secret>` | ลิสต์การทำนายเรียงใหม่→เก่า: project_id, ชื่องาน, ช่วงราคา, predicted_at, สถานะผลจริง (✅ in_range / ❌ / รอผล) |
| `GET /audit/{project_id}?key=<secret>` | detail: parse `explain_json` → แสดง 2 ชั้น (analysis + raw_records) + closed-loop block |

- **Auth:** secret key (env `BMS_AUDIT_KEY`) ตรวจทุก request — ผิด/ไม่มี = 401. (เริ่มแบบ shared secret ก่อน, ยังไม่ทำ user login)
- อ่าน live จาก `bms_customers.db` (connection สดต่อ request — real-time)

## 7. หน้าเว็บ (เสิร์ฟจาก FastAPI)

- HTML เรียบๆ server-rendered (ไม่ต้อง SPA): 
  - หน้าลิสต์: ตารางการทำนาย คลิกแถว → ไป detail
  - หน้า detail: บล็อก "วิธีคิด" (classify→scope→analysis→formula→output) + ตาราง "งานอ้างอิง" (raw_records) + บล็อก "คาด vs จริง"
- ภาษาไทย เน้นอ่านง่าย human-check

## 8. Closed-loop ในหน้า detail

- ถ้า `verified_at` มีค่า → แสดง `predicted` vs `actual_price` + `error_pct` + ป้าย in_range
- ถ้ายัง → "⏳ รอผลประมูล"

## 9. YAGNI (ตัดออก รอบนี้)

- ❌ ลิงก์ราย raw_record ไป eGP/CGD source (ไว้ทีหลัง)
- ❌ filter/search ซับซ้อน (เริ่มแค่ลิสต์เรียงวันที่ + จำกัด N ล่าสุด)
- ❌ user login จริง (เริ่ม shared secret ก่อน)
- ❌ backfill explain_json ของการทำนายเก่า (เก่าไม่มี snapshot = แสดง "ไม่มีข้อมูล explain" ได้)

## 10. Acceptance Criteria

- [ ] `price_predictions.explain_json` ถูกเพิ่ม (migration ผ่าน `init_schema`/`ALTER`)
- [ ] การทำนายใหม่ 1 งาน → มี `explain_json` ครบทุก field ใน §4
- [ ] prediction/ส่งงาน **ไม่พัง** แม้ build explain ล้มเหลว (fail-open)
- [ ] `GET /audit` ไม่มี key → 401; มี key ถูก → ลิสต์การทำนาย
- [ ] `GET /audit/{id}` แสดง analysis + raw_records + closed-loop จาก explain_json จริง
- [ ] อ่าน live (ทำนายใหม่ → refresh เห็นทันที)
- [ ] dispatch **Sophia** ตรวจ: explain_json ไม่ทำให้ price_predictions เพี้ยน + ตัวเลข output ตรงกับที่ส่งลูกค้า
