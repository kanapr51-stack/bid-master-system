# Web Push Notification (แจ้งเตือนผ่าน Browser) — Design

**วันที่:** 2026-07-13 · **สถานะ:** approved (คุณกัญจน์ ผ่านทั้ง 5 ส่วน)
**บริบท:** LINE push quota เต็ม 300/300 รอบที่ 2 (24 มิ.ย. + 13 ก.ค.) — อัตราใช้จริง ~23 ข้อความ/วัน free plan ไม่มีทางพอ. คุณกัญจน์เลือกไม่ upgrade แต่เพิ่ม Web Push เป็นช่องแจ้งเตือนของบอร์ด B แทน

## Decision ที่ approve แล้ว

| ประเด็น | คำตอบ |
|---|---|
| บทบาท LINE | ช่วงทดลอง**ส่งคู่กัน** (LINE ติดโควต้าก็ fail ตามระบบเดิม ไม่แตะ) → browser เสถียรแล้วค่อยตัด LINE (งานแยกเฟสหลัง) |
| ขอบเขตเนื้อหา | **ครบทุกประเภทเหมือน LINE** — D0/งานใหม่, bid_open เช้า, prelim, winner, cancelled ฯลฯ ใช้ข้อความชุดเดียวกับ LINE (แต่งครั้งเดียว ส่งสองทาง) |
| กลุ่มเป้าหมายรอบแรก | **คุณกัญจน์คนเดียว** ทดสอบ 2-3 วัน → ผ่านเกณฑ์เสถียรค่อยชวนลูกค้าทีละคน |
| แนวทาง | **A: Web Push มาตรฐาน (VAPID)** self-hosted ทั้งหมด — ไม่ใช้ OneSignal/บริการภายนอก |

## สถาปัตยกรรม

```
notification_queue (เดิม ไม่แตะ)
        ↓
Sebastian_LINE_Sender.py บน VPS — format ข้อความครั้งเดียว
        ↓
   ┌────┴──────────────┐
   send_line_push      send_web_push (ใหม่, pywebpush)
   (เดิม, ชี้สถานะคิว)   (best-effort, log แยก, try/except ครอบแยก
                         — ห้ามทำ LINE path ล้ม)
```

- **สถานะคิวช่วงทดลองยึดผล LINE เท่านั้น** (sent/failed/dedup เดิมเป๊ะ) — webpush ไม่มีสิทธิ์เปลี่ยน semantics คิว
- ผลส่ง webpush ลง**ตาราง log แยก** ไม่ปน `delivery_log` เพราะ `bid_open.undelivered_backlog` อ่าน delivery_log ตัดสินงานค้าง (`scripts/bid_open.py:37`) ถ้าปนจะเข้าใจผิดว่างานส่งแล้ว

## ฝั่งเก็บข้อมูล (engine — Sebastian_Customer_DB.py)

ตารางใหม่ 2 ตาราง:

```sql
push_subscriptions (
  id INTEGER PK,
  customer_id INTEGER NOT NULL,      -- FK customers
  endpoint TEXT NOT NULL UNIQUE,     -- URL ปลายทางของเบราว์เซอร์เครื่องนั้น
  p256dh TEXT NOT NULL,              -- กุญแจเข้ารหัส payload
  auth TEXT NOT NULL,
  user_agent TEXT,                   -- ไว้ดูว่าเครื่องไหน (debug)
  created_at TEXT NOT NULL,
  last_ok_at TEXT,                   -- ครั้งล่าสุดที่ส่งสำเร็จ
  disabled_at TEXT                   -- ปิดเมื่อ 404/410 Gone (เพิกถอน/ลบเบราว์เซอร์)
)

webpush_delivery_log (
  id INTEGER PK,
  subscription_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL,
  project_id TEXT,                   -- '' ได้สำหรับข้อความ digest/ทดสอบ
  source_stage TEXT,
  status TEXT NOT NULL,              -- sent | failed
  error TEXT,
  attempted_at TEXT NOT NULL
)
```

- ลูกค้า 1 คน มีได้หลาย subscription (มือถือ+คอม) — ส่งทุกเครื่องที่ยัง active
- 404/410 → ตั้ง `disabled_at` อัตโนมัติ ไม่ยิงซ้ำ; error อื่น = best-effort ไม่ retry
- VAPID key pair สร้างครั้งเดียว: private → `.env` VPS (`VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`), public → env บอร์ด Vercel (`NEXT_PUBLIC_VAPID_PUBLIC_KEY`)
- เพิ่ม dependency `pywebpush` บน VPS

## ฝั่ง engine API (bms_api.py)

Endpoint ใหม่ (guard `X-BMS-Secret` เหมือน portal endpoints เดิม):

- `POST /api/portal/push-subscribe` — body: line_user_id, endpoint, p256dh, auth, user_agent → upsert subscription (endpoint ซ้ำ = re-enable + update keys)
- `POST /api/portal/push-unsubscribe` — body: line_user_id, endpoint → ตั้ง disabled_at
- `POST /api/portal/push-test` — body: line_user_id → ส่งข้อความทดสอบไปทุกเครื่องของ user นั้นทันที (ให้ปุ่ม "ส่งทดสอบ" ใช้)

## ฝั่งบอร์ด (dashboard/web — Next.js บน Vercel)

- `public/sw.js` — service worker: รับ push → `showNotification(title, {body, data:{url}})`; คลิก → `clients.openWindow(url)`
- `public/manifest.json` — minimal PWA manifest (จำเป็นสำหรับ iOS Add-to-Home-Screen)
- Component การ์ด **"🔔 เปิดรับแจ้งเตือน"** บนหน้าบอร์ด:
  - ยังไม่อนุญาต → ปุ่มเปิด; อนุญาตแล้ว → แสดงสถานะ ✅ + ปุ่ม "ส่งทดสอบ" + ปุ่มปิด
  - กดเปิด → `Notification.requestPermission()` → `pushManager.subscribe({userVisibleOnly:true, applicationServerKey})` → POST `/api/portal/push/subscribe` (บอร์ด)
  - iPhone ที่ยังไม่ standalone → แสดงคำแนะนำ "เพิ่มไปยังหน้าจอโฮมก่อน" (detect `navigator.standalone`/display-mode)
  - เบราว์เซอร์ไม่รองรับ → ซ่อนการ์ดเงียบๆ
- API routes ใหม่ฝั่งบอร์ด (pattern เดียวกับ `src/app/api/portal/star/route.ts`): `push/subscribe`, `push/unsubscribe`, `push/test` — อ่าน lineUserId จาก session cookie → relay ไป engine พร้อม `X-BMS-Secret` (คีย์ไม่หลุด client)

## ฝั่งตัวส่ง (Sebastian_LINE_Sender.py)

- module ใหม่ `scripts/webpush_send.py`: `send_web_push(conn, customer_id, title, body, url, project_id, source_stage)` — โหลด subscriptions active ของ customer → pywebpush ทีละเครื่อง → log ลง webpush_delivery_log → 404/410 disable
- จุดเกี่ยว: ทุกจุดที่ sender ยิง LINE push สำเร็จ/ล้ม → เรียก `send_web_push` ด้วยเนื้อหาเดียวกัน (title = ประเภท+ชื่องานย่อ ใช้ `_shorten_project_name` เดิม, body = จังหวัด/งบ/วันยื่น, url = ลิงก์หน้างานบนบอร์ด)
- **"ครบทุกประเภท" รวมสคริปต์ที่ยิง LINE push ตรงโดยไม่ผ่าน LINE_Sender ด้วย** (เตือนเช้ายื่นซอง `Sebastian_BidOpen_Morning`, สรุปรายวัน `Sebastian_Daily_Digest`) — เรียก module `webpush_send` ตัวเดียวกันข้างจุดยิง LINE ของแต่ละสคริปต์ (implementation plan ต้อง inventory จุดยิง LINE push ทั้งหมดก่อน)
- **ครอบ try/except ทั้งก้อน webpush** — exception ใดๆ ห้ามกระทบ LINE flow และห้ามเปลี่ยนสถานะคิว

## เกณฑ์ผ่าน (verifiable)

1. ปุ่ม "ส่งทดสอบ" → เด้งจริงบนมือถือ + คอมของคุณกัญจน์ ภายใน ~5 วิ, กดแล้วเปิดถูกหน้า
2. งานจริงจากคิว → webpush_delivery_log มี status=sent ในรอบเดียวกับที่คิว process
3. LINE path เดิมไม่กระทบ: test suite เดิมผ่านครบ, คิวไม่มี duplicate (sanity check ก่อน commit)
4. **นิยาม "เสถียร" = 3 วันติดกัน งานใน notification_queue ทุกงานของ user ที่มี subscription มี webpush log ครบ (0 งานหลุด)** → ค่อยเริ่มชวนลูกค้า

## จงใจไม่ทำรอบนี้ (YAGNI)

- ไม่ตัด LINE push (เฟสหลัง หลังผ่านเกณฑ์เสถียร)
- ไม่มีหน้าตั้งค่าเลือกประเภทแจ้งเตือนต่อ user
- ไม่มีรูป/ปุ่ม action ใน notification (ข้อความ + ลิงก์พอ)
- ไม่ทำ backlog digest ฝั่ง webpush
- ไม่สลับตัวชี้สถานะคิวจาก LINE → webpush
