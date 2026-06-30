# Design: บอร์ด /portal/world โชว์งานจริง (Phase 1: section "งานที่ติดตาม")

วันที่: 2026-06-30
ที่มา: บอร์ด BMS Bid Board (`bid-master-dashboard.vercel.app/portal/world`) ยังโชว์ `SEED_JOBS` (งานปลอม) → ⭐ ไป "ติดดาวงานปลอม" และคนละที่กับ `job_stars` ของ engine. ดู [[project_customer_store_split]]
อนุมัติ (กัญจน์ 2026-06-30): บอร์ดเป็น "ทั้งสอง section" (งานที่ติดตาม + งานใหม่ที่แมตช์), **เริ่ม section งานที่ติดตามก่อน**

## เป้าหมาย Phase 1
แทน `SEED_JOBS` ด้วย **งานที่ลูกค้าติดตามจริง** (followed_jobs) บนหน้า `/portal/world` พร้อม ⭐ ที่ผูก `project_id` จริงและเขียน `job_stars` (ชุดเดียวกับ ⭐ จากลิงก์ LINE)

## Success criteria (วัดได้)
1. `/portal/world` ของลูกค้าที่มี followed_jobs โชว์งานจริง (ชื่อ/พื้นที่/deadline/stage ตรงกับ DB) ไม่มี `SEED_JOBS` เหลือบนหน้า
2. ลูกค้าที่ไม่มี followed_jobs เห็น empty state (ไม่ error, ไม่โชว์งานปลอม)
3. กด ⭐ บนบอร์ด → row ใน `job_stars` เปลี่ยนจริง; เปิดใหม่ดาวคงอยู่; ตรงกับดาวที่กดจากลิงก์ LINE
4. `SEED_JOBS` ถูกลบออกจาก path ของหน้า world (เหลือไว้ได้ถ้า section discovery ยังอ้าง แต่ Phase 1 ไม่ใช้)

## ขอบเขต (เฉพาะ Phase 1)
**ใน:** section งานที่ติดตาม (จาก `_portal_jobs`), ⭐→job_stars, empty state
**ไม่ใน (Phase ถัดไป):** section "งานใหม่ที่แมตช์" (discovery), matchedKeywords/ระยะทาง/sme บนการ์ด, หน้า HTML `/portal` เดิม (ไม่แตะ — แค่ reuse logic)

## สถาปัตยกรรม / Data flow
```
browser (LINE LIFF)
  → Next.js world/page.tsx (server, มี session line_user_id)
      → lib/engine-client.ts  fetch(BMS_API_URL + X-BMS-Secret)
          → bms_api GET /api/portal/jobs?line_user_id=  → _portal_jobs() → SQLite
  → WorldClient render การ์ดงานจริง
  ⭐ toggle → POST /api/portal/star {line_user_id, project_id} → toggle job_stars
```
ทางที่ตัด: Next.js query SQLite ตรง = ทำไม่ได้ (DB อยู่ VPS, Neon คนละตัว). caching = เลื่อน (query เบา + region sin1).

## Backend (bms_api.py บน VPS)
ใช้ pattern เดียวกับ `/api/portal/customer` (X-BMS-Secret guard, keyed line_user_id):

### `GET /api/portal/jobs?line_user_id=`
- verify secret → หา customer จาก line_user_id (ไม่เจอ → `{ok:true, jobs:{won:[],prelim:[],bidding:[],pre:[],cancelled:[]}}` คือ groups ว่าง — web โชว์ empty state)
- เรียก `_portal_jobs(line_user_id)` (logic เดิม) → คืน JSON groups: `{won, prelim, bidding, pre, cancelled}`
- แต่ละ job map → TrackedJob (ดูล่าง) + `starred` (จาก job_stars ของ customer นี้)

### `POST /api/portal/star {line_user_id, project_id}`
- verify secret → หา customer_id → `portal_views.toggle_star(conn, cid, pid)` (logic เดิม)
- คืน `{ok:true, starred: bool}` (สถานะหลัง toggle)

## รูปข้อมูล TrackedJob (JSON)
```
{
  project_id: string
  name: string
  location: string        // "ต.x อ.y จ.z"
  deadline: string        // วันยื่นซอง (อาจว่าง)
  deadline_time: string   // เวลายื่นซอง (อาจว่าง)
  // days_left: คำนวณฝั่ง web จาก deadline (ไม่ส่งจาก engine — ให้ countdown สดเสมอ)
  budget: number          // ราคากลาง (อาจ 0)
  pred_lo: number|null    // ช่วงราคาคาดการณ์
  pred_hi: number|null
  stage: 'won'|'prelim'|'bidding'|'pre'|'cancelled'
  winner: string|null     // ถ้า won
  winner_price: number|null
  starred: boolean        // จาก job_stars
}
```

## Frontend (dashboard/web)
- `lib/engine-client.ts` (มีอยู่จาก customer): เพิ่ม `getPortalJobs(lineUserId)` + `togglePortalStar(lineUserId, projectId)`
- `world/page.tsx`: ดึง jobs จริงแทน `SEED_JOBS` (server-side), ส่ง initialStarred จาก jobs ที่ starred
- `world/_client.tsx`: ปรับ JobCard/section ให้แสดงตาม TrackedJob + stage; `toggleStar` ยิง POST /api/portal/star (ผ่าน route `/api/portal/star` ฝั่ง Next ที่ relay ไป engine ด้วย secret) แทน `/api/portal/save`(notes.starred)
- เลิกอ่าน/เขียน `notes.starred` บนบอร์ด (notes ยังเก็บ classes/tier เหมือนเดิม)

### UI sections (เรียงตามความสำคัญ)
🔵 ยื่นซองได้ (bidding) · 🟡 รอผล (prelim) · 🏆 รู้ผลแล้ว (won) · ⚪ ระยะวางแผน (pre) · ❌ ยกเลิก (cancelled, ย่อ/ท้ายสุด)
การ์ดสรุปด้านบน: นับจำนวนต่อ stage + จำนวน ⭐. Empty state ถ้าไม่มีงาน: ข้อความ "ยังไม่มีงานที่ติดตาม — ระบบจะเพิ่มให้เมื่อเจองานตรงพื้นที่/หมวดของท่าน"

## Auth / security
line_user_id จาก session cookie (server-side) + X-BMS-Secret (env Vercel ↔ VPS .env, ตั้งไว้แล้ว). ไม่ส่ง secret ออก client — fetch เกิดฝั่ง server/route handler เท่านั้น

## Error handling
- engine ล่ม/secret ผิด → หน้า world โชว์ empty state + log (ไม่ crash, เหมือน try/catch เดิมตอนเรียก getCustomerByLineId)
- ⭐ toggle ล้มเหลว → revert UI + เงียบ (ไม่ block)

## Testing
- bms_api: test `/api/portal/jobs` (มี follow → คืน groups, ไม่มี customer → ว่าง, secret ผิด → 403), `/api/portal/star` (toggle on/off, ไม่มี customer → 404)
- ใช้ followed_jobs จริง 30 งาน (3 ราย) บน prod เป็น smoke test (read-only)
- web: tsc ผ่าน, สร้าง throwaway ⭐ ผ่านบอร์ด → เช็ค job_stars → ลบ

## Deploy
scp `bms_api.py` → VPS + restart bms-api; `vercel deploy --prod` (เว็บ). commit+push + reconcile VPS git (stash+ff-pull) เหมือนงานก่อน

## Out of scope / defer
- discovery section (งานใหม่ที่แมตช์) → Phase 2 (ต้องสร้าง matching query บน projects_seen)
- การ์ด matchedKeywords/ระยะทาง/sme (discovery)
- รวม notes.starred เดิมเข้า job_stars (ดาวบนงานปลอมเดิม — ทิ้งได้ ไม่มีค่า)
