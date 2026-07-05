# Board B Job Detail Page — Design (2026-07-06)

## เป้าหมาย

การ์ดงานบน Board B (`/portal/world`) กด "ดูรายละเอียด" แล้วเด้งไปหน้า detail ของ engine
(ธีม Board A เดิม) — ธีมไม่กลมกลืน. สร้าง **หน้ารายละเอียดงานใหม่ใน Next.js portal**
ธีมเดียวกับ Board B ทั้งหมด แล้วชี้การ์ดมาหน้าใหม่นี้. **ไม่แตะหน้า Board A เดิม**
(LINE links ยังใช้หน้าเดิมต่อ).

การตัดสินใจของกัญจน์ (2026-07-06):
- ฟีเจอร์**จัดเต็มเท่าหน้าเดิม** ตั้งแต่รอบแรก
- ชื่อบริษัทคู่แข่ง/ผู้ยื่น **ลิงก์ไปหน้าบริษัทเดิมของธีม A ไปก่อน** (ข้อมูลครบ h2h/portfolio)
- ทำจนจบ autonomous (commit local, ไม่ push จนกว่าจะ confirm)

## สถาปัตยกรรม

ตามแพทเทิร์นที่มีอยู่แล้ว: Next.js (Vercel) ↔ engine FastAPI (VPS) ผ่าน
`X-BMS-Secret`, ระบุตัวลูกค้าด้วย `line_user_id` จาก session cookie (LINE login).

### Engine (`scripts/bms_api.py`) — endpoint JSON ใหม่ 3 ตัว

1. `GET /api/portal/job-detail?line_user_id&pid`
   → `{ok, data}` โดย data มาจาก `portal_views.job_detail()` เดิม +:
   - `notes` (ไทม์ไลน์), `overview`, `starred`
   - `company_tables[].companies[].href` และ `bidders[].href` = ลิงก์ absolute
     ไปหน้าบริษัทธีม A (`{PUBLIC_BASE_URL}/portal/company?t=<token>&tin=..`)
     — engine mint follow_token เอง (แพทเทิร์นเดียวกับ board-token) URL logic อยู่ที่เดียว
2. `POST /api/portal/job-note` `{line_user_id, pid, action(add|edit|delete|save_overview), note_id?, entry_date?, note?}`
   → `{ok, notes, overview}` (คืน state ใหม่เลย ไม่ต้อง refetch)
3. `POST /api/portal/job-calc` `{line_user_id, pid, my_price, selected_names[], extra_names[]}`
   → `{ok, custom_calc}` (โครงเดียวกับที่ `job_detail(calc_params)` คืน)

ดาว⭐ ใช้ `POST /api/portal/star` ที่มีอยู่แล้ว. ทุก endpoint guard secret เหมือนตัวอื่น.

### Web (`dashboard/web`)

- `src/lib/portal-job-detail.ts` — types + fetcher server-side
- `src/app/portal/job/[pid]/page.tsx` — server component: session guard → fetch engine →
  ส่ง props เข้า client (engine ล่ม → การ์ดแจ้ง "ดึงข้อมูลไม่ได้" + ปุ่มกลับ)
- `src/app/portal/job/[pid]/_client.tsx` — UI ธีม Board B (class `p-*` + `_ui.tsx` เดิม):
  TopBar(back) → การ์ดหัวงาน (ชื่อ/pid/พื้นที่/ดาว) → ตัวเลขหลัก (ราคากลาง/คาดราคา/เดดไลน์+countdown)
  → ตารางคู่แข่งต่อ scope → ตารางโอกาสชนะ → เครื่องคำนวณโอกาสชนะ (interactive, ไม่ reload)
  → ผู้ยื่นทั้งหมด (ผู้ชนะไฮไลต์ทอง) → โน้ตภาพรวม → ไทม์ไลน์ (เพิ่ม/แก้/ลบ)
- Next API proxy (session → secret, แพทเทิร์นเดียวกับ `api/portal/star`):
  `api/portal/job-detail` ไม่ต้อง (server component fetch ตรง), เพิ่ม
  `api/portal/job-note/route.ts` + `api/portal/job-calc/route.ts`
- `world/_client.tsx`: `detailHrefOf` → `/portal/job/<pid>` (ลิงก์ภายใน);
  ตัด `detailBase`/board-token fetch ออกจาก world page (ไม่ใช้แล้ว — endpoint engine ยังอยู่ให้ระบบอื่น)
- ตาราง: เพิ่ม class `p-table` เล็กๆ ใน `portal.css` (additive)

## Error handling

- engine ล่ม/ไม่พบงาน → หน้าแสดงการ์ดข้อความ + ลิงก์กลับ world (ไม่ crash)
- note/calc fetch fail → แสดงข้อความสั้นใต้ฟอร์ม, ดาว revert (แพทเทิร์น world เดิม)

## Testing / success criteria (verifiable)

1. `scripts/test_portal_job_detail_api.py` (scratch DB แพทเทิร์น test_portal_board_token):
   403 เมื่อ secret ผิด; job-detail คืนโครงครบ (job/bidders/notes/starred/href);
   job-note add→edit→delete→save_overview คืน state ถูก; job-calc คืน custom_calc — **ทุก assert ผ่าน**
2. `npm run build` ผ่าน (typecheck + Next 16 conventions)
3. การ์ดบน world ชี้ `/portal/job/<pid>` (ไม่มี board-token ใน href แล้ว)
4. หน้า Board A เดิม (`/portal/job` engine) diff = 0 บรรทัด
