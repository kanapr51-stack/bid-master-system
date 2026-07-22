# Sebastian Chat Feed — หน้าประวัติแจ้งเตือนสไตล์แชท — Design (2026-07-23)

## เป้าหมาย

กัญจน์: บอร์ดแจ้งเตือนได้แล้ว (web push LIVE) แต่ยังไม่มี "ประวัติการแจ้งเตือน" — อยากได้
หน้าใหม่ที่โชว์ประวัติแบบ Sebastian ทักข้อความมาแจ้ง (เหมือนเปิดดูแชท LINE เก่าๆ กับบอท)
ตัดสินใจแล้วระหว่าง brainstorm:

1. **หน้าใหม่แยกต่างหาก** — ไม่ปนกับหน้า "งานทั้งหมด" (`/portal/jobs`) เดิมที่เป็น card list
2. **1 ข้อความต่อ 1 งาน** (dedup, ไม่นับ retry/สถานะเปลี่ยนซ้ำ)
3. **เนื้อหา bubble = ข้อความ LINE จริงทุกบรรทัด** (ไม่ใช่สรุปย่อ) — reuse `format_notification()`
   ตรงๆ ไม่เขียน logic จัดข้อความซ้ำฝั่งเว็บ
4. **กด bubble → ไปหน้ารายละเอียดงาน** `/portal/job/<id>` (ไม่มี action button ฝังใน bubble)
5. **แท็บเมนูล่างชื่อ "Sebastian"** ตำแหน่งเดิมของ "เอกสาร" ที่เพิ่งเอาออก (ต่อจาก "ตั้งค่า")

## หลักการ

ระบบมี `notification_queue` เก็บทุกงานที่แจ้งลูกค้าอยู่แล้ว (เหมือนที่ `/api/portal/all-jobs`
ใช้) — เพิ่ม endpoint คู่กันที่ต่างแค่ field เนื้อหา: reconstruct ข้อความเต็มด้วยฟังก์ชัน
`format_notification()` เดิมจาก `Sebastian_LINE_Sender.py` (single source of truth — ถ้าแก้
format ข้อความจริงในอนาคต หน้าแชทนี้ตามเองอัตโนมัติ ไม่ต้อง sync 2 ที่)

ข้อมูล budget/dept_name อ่านจาก `projects_seen` (แคชที่มีอยู่แล้ว), deadline อ่านจาก
`project_locations.deadline/deadline_time` (แคชเดียวกับที่ `_deadline_from_db()` fallback
ใช้ตอนส่งจริง) — **ไม่ยิง live PDF/API enrichment เพิ่ม** (หน้านี้ read-only ต้องเร็ว, ข้อมูล
enrichment สดๆ ไม่จำเป็นสำหรับ "ดูประวัติ")

## สถาปัตยกรรม

### Engine — `GET /api/portal/sebastian-feed?line_user_id&limit=500` (read-only)

- แหล่ง: `notification_queue` WHERE `customer_id=cid AND status!='cancelled' AND is_test_data=0`
  (เกณฑ์เดียวกับ `/api/portal/all-jobs` — ไม่ผูกผลส่ง LINE)
- dedup ต่อ `project_id` เอาแถว `created_at` ล่าสุด (เหมือน all-jobs)
- ต่อรายการ เรียก `Sebastian_LINE_Sender.format_notification()` ด้วยฟิลด์จาก
  `projects_seen` (province/budget/project_name/dept_name/announce_type) +
  `project_locations` (bid_submit_date/time) แล้วห่อด้วย logic เดียวกับ `_plain_text_body`
  (หัวข้อขึ้นก่อน + ชื่อโครงการเต็ม + ส่วนที่เหลือ) — ใช้กับทุก stage เหมือนกันหมด (ไม่แยก
  flex-card เหมือนตอนส่งจริง เพราะหน้าแชทนี้เป็น plain text ล้วน)
- คืนต่อรายการ: `{project_id, message (string, multi-line), sent_at, stage, starred}`
  (`stage` ใช้ mapping เดิมจาก all-jobs)
- เรียง `created_at` ASC (เก่า→ใหม่ — ตรงข้ามกับ all-jobs ที่ DESC เพราะ all-jobs เป็น list
  แต่อันนี้เป็นแชท), `limit` default 500
- guard `X-BMS-Secret` เหมือนทุก endpoint

### Web

- `src/lib/portal-sebastian-feed.ts` — types (`SebastianMessage`, `SebastianFeed`) +
  `getSebastianFeed(lineUserId, limit?)` (pattern เดียวกับ `portal-all-jobs.ts`)
- `src/app/portal/sebastian/page.tsx` — server component, auth cookie เหมือนหน้าอื่น,
  redirect `/portal/login` ถ้าไม่มี session, fetch feed → ส่งให้ `_client.tsx`
- `src/app/portal/sebastian/_client.tsx`:
  - หัวเธรด: ไอคอน `Icons.Bot` (มีอยู่แล้ว ไม่สร้างใหม่) + ชื่อ "Sebastian"
  - จัดกลุ่มตามวัน (วันนี้/เมื่อวาน/วันที่ไทย) — **extract `dayKey`/`dayLabel` helper จาก
    `jobs/_client.tsx` ไปไว้ `src/lib/portal-day-groups.ts`** แล้วให้ทั้งสองหน้า import
    ใช้ร่วมกัน (ใช้ซ้ำเป็นครั้งที่ 2 แล้ว คุ้มกับการแยก — เดิมอยู่ใน `jobs/_client.tsx` บรรทัด
    ~32-49)
  - แต่ละ bubble: ข้อความหลายบรรทัดจาก `message`, timestamp เวลาไทย, ★ ถ้า starred,
    ทั้ง bubble เป็น `<Link href="/portal/job/<id>">`
  - เรียงเก่า→ใหม่บนลงล่าง (แชทจริง)
- `_shell.tsx`: เพิ่ม `{ href: '/portal/sebastian', label: 'Sebastian', Icon: BotIcon }` ใน
  `NAV_ITEMS` ตำแหน่งที่ 3 (ต่อจาก "ตั้งค่า" — ตำแหน่งเดิมของ "เอกสาร") — เพิ่มฟังก์ชัน
  `BotIcon` local ในไฟล์นี้ (มิเรอร์ path เดียวกับ `Icons.Bot` ใน `_ui.tsx` ให้ตรงกัน)

## Error handling

- engine ล่ม → หน้า sebastian โชว์การ์ดแจ้ง engine ไม่พร้อม (แพทเทิร์นเดิมจาก jobs page)
  ไม่ crash
- งานที่ไม่มีใน `projects_seen`/`project_locations` แล้ว (ลบ/ข้อมูลหาย) →
  `format_notification()` graceful อยู่แล้ว (budget=0→"ไม่ระบุ", deadline ว่าง→ไม่โชว์บรรทัด
  นั้น) ไม่ crash
- customer ไม่มีงานเลย → โชว่ข้อความว่าง "ยังไม่มีการแจ้งเตือน"

## Testing / success criteria

1. `test_portal_sebastian_feed_api.py` (ใหม่): 403 secret ผิด; dedup ต่อ project (แถวซ้ำ
   หลายรอบ → 1 ข้อความ, เนื้อหาใช้ snapshot ล่าสุด); ไม่รวม status='cancelled' + is_test_data=1;
   เรียงเก่า→ใหม่ (ASC); เนื้อหา `message` ตรงกับผล `format_notification()` จริงเป๊ะ (byte
   ต่อ byte สำหรับ input เดียวกัน — กัน message drift จาก 2 จุดจัดข้อความ); graceful เมื่อ
   projects_seen/project_locations ไม่มีแถว
2. `npx tsc --noEmit` ผ่าน; `npm run build` ผ่าน; SSR e2e: seed queue จริง →
   `/portal/sebastian` render bubble ครบ, จัดกลุ่มวันถูก, กด bubble ไปหน้า job ถูก id,
   nav bar โชว์แท็บ Sebastian ตำแหน่งถูก
3. ระบบส่ง LINE / endpoint `/api/portal/all-jobs` เดิม — diff = 0 (endpoint ใหม่ไม่แตะของเดิม)
