# แผน: รวม customer store ของเว็บ → DB ของ engine (เลิก Google Sheets)

วันที่: 2026-06-30
ที่มา: สอบสวนเว็บ BMS Bid Board (`bid-master-dashboard.vercel.app/portal/world`) ช้า → พบ cold start 9s จาก `googleapis` + บั๊กเงียบ "ปุ่มหลอก" (ค่าที่ตั้งบนเว็บลง Google Sheets อย่างเดียว engine ไม่เห็น). ดู [[project_customer_store_split]]
Decision (กัญจน์ 2026-06-30): **Option A — เว็บเขียนตรงเข้า DB ของ engine ผ่าน bms_api, เลิก Sheets**

## Success criteria (วัดได้จริง)
1. `/portal/world` cold start TTFB < 2.5s (baseline 8.99s)
2. เปลี่ยน business class/จังหวัดบนเว็บ → row ใน `subscription_provinces` (SQLite) เปลี่ยนตามจริง
3. `googleapis` หลุดออกจาก `dashboard/web/package.json`
4. ลูกค้าเดิมใน Sheets ถูก migrate เข้า SQLite ครบ ไม่หาย/ไม่ซ้ำ (Sophia SAFE)
5. ไม่มี duplicate customers / line_user_id ใน SQLite หลัง migrate

## สถาปัตยกรรมปัจจุบัน (ยืนยันแล้ว)
- เว็บ (Next.js/Vercel) เขียน customer ทั้งหมด → Google Sheets ผ่าน `dashboard/web/src/lib/customers.ts` (`googleapis`). routes: `/api/portal/save`, `/api/line/customer`
- เว็บ **ไม่เคยเรียก bms_api เลย** (grep ยืนยัน)
- engine (VPS) อ่าน/เขียน SQLite `/opt/bms/data/bms_customers.db`; register ผ่าน LINE follow (`bms_api.py:1190`); จังหวัดตั้งผ่านแชต LINE → `_save_provinces` → `subscription_provinces`
- bms_api มี `POST /api/preferences` (X-BMS-Secret) รออยู่ — ไม่มีใครเรียก
- การ match ขับด้วย `subscription_provinces` JOIN ใน `enqueue_notifications` (`Sebastian_Customer_DB.py:1154`) + `subscriptions.work_categories/min_budget/announce_types`
- schema `customers` (สำเนา local 14มิ.ย.) = id, line_user_id, display_name, tier, active, created_at, updated_at, is_test_data → **ไม่มีช่อง notes/email/phone/keywords** (ต้องยืนยัน schema prod บน VPS อีกที)

## งานที่ต้องทำ

### Phase 0 — ยืนยัน schema prod + backup (บน VPS, ต้องการกัญจน์)
- ดู schema จริงของ `customers/subscriptions` บน VPS (อาจ migrate ไปแล้วต่างจาก local)
- `backups/bms_customers_<ts>.db` ก่อนแตะ schema

### Phase 1 — ขยาย schema engine ให้เก็บโปรไฟล์เว็บ
- เพิ่มคอลัมน์ `customers`: `email`, `phone`, `notes` (TEXT, เก็บ JSON ก้อนเดียวกับที่เว็บใช้: classes/starred/tier/documents/contact)
- ใช้ `init_schema()` แบบ idempotent (ALTER TABLE ADD COLUMN IF NOT EXISTS-style) — ห้ามรัน script มั่วบน prod (ดู feedback_migration_no_seed)

### Phase 2 — bms_api endpoints (CRUD customer profile + notes)
- `GET /api/portal/customer?line_user_id=` → profile + notes JSON (X-BMS-Secret)
- `POST /api/portal/customer` → upsert profile + notes; **และ** แตก notes.classes → เขียน `subscription_provinces` + `subscriptions.work_categories/min_budget` (นี่คือส่วนที่ทำให้ "ขับ match จริง")
- reuse logic `_save_provinces` ที่มีอยู่

### Phase 3 — เปลี่ยนฝั่งเว็บ (ทิ้ง googleapis)
- เขียน `lib/engine-client.ts` คุย bms_api (fetch + X-BMS-Secret จาก env)
- แทนที่การเรียกใน `customers.ts` / `/api/portal/save` / `/api/line/customer` → engine-client
- ลบ `googleapis` จาก deps → cold start หาย
- env ใหม่บน Vercel: `BMS_API_URL`, `BMS_INTERNAL_SECRET`

### Phase 4 — Perf เพิ่ม (ทำพร้อมกันได้)
- Vercel region → `sin1` (ใกล้ผู้ใช้ไทย + ใกล้ VPS สิงคโปร์)
- ทบทวน `force-dynamic` 6 หน้า → cache โปรไฟล์เท่าที่ปลอดภัย

### Phase 5 — Migrate ข้อมูลเดิม + verify
- one-shot: อ่าน Sheets customers → POST เข้า bms_api (หรือ insert ตรง) ครั้งเดียว
- Sophia sanity (ไม่หาย/ไม่ซ้ำ/notes ครบ)
- วัด TTFB ใหม่เทียบ 9s
- **ไม่ deploy/push โดยไม่ confirm กัญจน์**

## ความเสี่ยง
- แตะ schema prod customers → backup ก่อนเสมอ
- auth Vercel↔VPS: secret ต้องตั้งทั้ง 2 ฝั่ง; bms_api ต้องเปิดรับจาก Vercel (CORS/firewall)
- เว็บเก็บ classes ละเอียด (geo radius/tambon) มากกว่าที่ engine ใช้ → Phase 2 mapping ต้องตัดสินว่าแปลงระดับไหน (จังหวัด? อำเภอ?) — อาจเริ่มที่ระดับจังหวัดก่อน (ตรงกับ subscription_provinces)

## สิ่งที่ต้องการจากกัญจน์ก่อนเริ่มเขียนโค้ด prod
1. สิทธิ์เข้า VPS (รัน schema check + backup + deploy bms_api) — หรือกัญจน์รันให้ผ่าน `!`
2. ยืนยัน: เริ่มที่ mapping ระดับ "จังหวัด" ก่อนพอไหม (ง่าย/ปลอดภัยสุด) แล้วค่อยขยายอำเภอ
