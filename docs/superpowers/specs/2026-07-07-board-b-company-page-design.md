# Board B Company Page — Design (2026-07-07)

## เป้าหมาย

ปิดชุดธีม Board B: หน้า detail งาน (`/portal/job/[pid]`, N+187) ยังลิงก์ชื่อบริษัท
คู่แข่ง/ผู้ยื่นไปหน้าบริษัทของ engine (ธีม Board A). สร้าง **หน้าบริษัทใหม่ใน Next.js portal**
ธีมเดียวกับ Board B แล้วสลับลิงก์มาหน้านี้ — เส้นทางจาก world → job → company กลมกลืน
ธีมเดียวตลอด. **ไม่แตะหน้า Board A เดิม** (`/portal/company` engine — LINE links ใช้ต่อ).

คำสั่งกัญจน์ (2026-07-07): "ทำหน้าบริษัทธีม B ต่อเลยทำชุดเสร็จเลย" — ทำจนจบ autonomous
(commit local, **ไม่ push จนกว่าจะ confirm** — กัญจน์นอนอยู่, แพทเทิร์นเดียวกับ N+187).

## สถาปัตยกรรม

แพทเทิร์นเดียวกับ N+187 ทั้งหมด: Next.js server component (session cookie) → engine
FastAPI ผ่าน `X-BMS-Secret` + `line_user_id`. Reuse ฟังก์ชัน data ของหน้า A ทุกตัว
(`portal_views.company_profile / head_to_head / won_portfolio / area_portfolio`) —
ไม่เขียน query ใหม่.

### Engine (`scripts/bms_api.py`) — endpoint ใหม่ 1 ตัว

`GET /api/portal/company-detail?line_user_id&tin&proc=all&area_ids=&area_label=`
→ `{ok, data}`:

- `profile` = `company_profile(conn, tin)` (name/tin/is_sme/total_bids/wins/win_rate/
  provinces/discount_hist/discount_avg/by_year) — ไม่พบ → `{ok: False, error: "not_found"}`
- `h2h` = `head_to_head(conn, our_tin, tin)` — `our_tin` จาก `customers.company_tin`
  ของ line_user_id (ไม่มี → null)
- `won` = `won_portfolio(conn, profile.name, proc)` (stats เต็มเสมอ, `proc` กรอง job list)
- `area` = `area_portfolio(conn, profile.name, area_ids.split(","))` + ส่ง `area_label`
  กลับ (มาจากลิงก์ scope ในหน้า job detail)

guard secret เหมือน endpoint อื่น. proc filter = server refetch (Link เปลี่ยน
searchParams — แพทเทิร์นเดียวกับหน้า A ที่ reload ทั้งหน้า, ไม่ต้องมี proxy/POST).

### Engine — เปลี่ยน href ใน `_job_detail_payload` (จุดเดียว)

ลิงก์บริษัทใน job-detail JSON เปลี่ยนจาก absolute ธีม A
(`{PUBLIC_BASE_URL}/portal/company?t=<token>&tin=..`) → **relative ภายในเว็บ B**:

- companies: `/portal/company/<tin>?area_ids=..&area_label=..`
- bidders: `/portal/company/<tin>?from=<pid>`

เหตุผล: N+187 ตัดสินใจให้ URL mint อยู่ฝั่ง engine ที่เดียว — คงการตัดสินใจนั้น
เปลี่ยนแค่รูป URL. ไม่ต้อง mint follow_token แล้ว (เว็บ auth ด้วย session เอง).
หน้า A (`portal_job_get` → `render_job_page`) ไม่แตะ — ใช้ token ต่อเหมือนเดิม.

### Web (`dashboard/web`)

- `src/lib/portal-company-detail.ts` — types + fetcher server-side
- `src/app/portal/company/[tin]/page.tsx` — server component: session guard →
  fetch engine (searchParams: `from`, `proc`, `area_ids`, `area_label`) → client
  (engine ล่ม → การ์ดแจ้ง + ปุ่มกลับ, แพทเทิร์น job page)
- `src/app/portal/company/[tin]/_client.tsx` — UI ธีม Board B (`p-*` + `_ui.tsx`):
  1. TopBar "ประวัติบริษัท" subtitle=tin, back → `/portal/job/<from>` ถ้ามี ไม่งั้น router.back()
  2. การ์ดหัว (p-gilt): ชื่อ + SME chip + stat grid ยื่น/ชนะ/win-rate/จังหวัด
  3. ⚔️ เทียบกับเรา (h2h — โชว์เฉพาะมีข้อมูล): stat 4 ช่อง + รายการงานที่เจอกัน (≤10)
  4. 📊 ยื่น–ชนะ รายปี — bar แนวนอน (div fill, สี accent=ยื่น / emerald=ชนะ)
  5. 💸 ส่วนลดที่ชอบเสนอ — histogram bar (สี gold) + ค่าเฉลี่ย
  6. 🏆 ผลงานที่ชนะ (won — โชว์เฉพาะมีข้อมูล): stat ประมูล/เจาะจง/รวม + top 3 +
     chips filter proc (Link ?proc=.. คง param อื่น) + รายชื่องาน (≤50, เปิดอัตโนมัติเมื่อ filter)
  7. 📍 ผลงานในพื้นที่นี้ (area — เฉพาะเข้าจากลิงก์ scope): รายการงาน ลิงก์ `/portal/job/<pid>`
  8. Timeline แยกรายปี: หัวปี + งาน (✅/▫️, ลิงก์ `/portal/job/<pid>`, ราคา + ส่วนลด)
- `job/[pid]/_client.tsx`: **ไม่ต้องแก้** — ใช้ `href` จาก payload อยู่แล้ว (`<a href>`
  รับ relative ได้; เปลี่ยนเป็น `<Link>` เฉพาะถ้าจำเป็น — surgical)
- `src/lib/portal-job-detail.ts`: อัปเดต comment ของ `href` (ธีม B แล้ว)

## Error handling

- engine ล่ม / ไม่พบบริษัท → การ์ดข้อความ + ปุ่มกลับ (ไม่ crash)
- h2h/won/area เป็น null → ซ่อน section นั้น (เหมือนหน้า A)

## Testing / success criteria (verifiable)

1. `scripts/test_portal_company_detail_api.py` (scratch DB แพทเทิร์น test_portal_job_detail_api):
   403 secret ผิด; profile ครบ + win_rate ถูก; h2h นับ our_wins/their_wins ถูก
   (customer มี company_tin); won groups/proc filter ถูก; area กรองตาม ids;
   ไม่พบบริษัท → not_found; `json.dumps` ทั้งก้อนได้ — **ทุก assert ผ่าน**
2. `test_portal_job_detail_api.py` อัปเดต assertion href → `/portal/company/<tin>` แล้ว **ผ่าน**
3. `npm run build` ผ่าน
4. e2e local: engine scratch + next dev → เปิด `/portal/company/<tin>` render ครบ section,
   ลิงก์จากหน้า job detail ชี้หน้าใหม่ (ไม่มี `/portal/company?t=` ใน payload อีก)
5. หน้า Board A เดิม (engine `/portal/company` + `/portal/job`) diff = 0 บรรทัด
