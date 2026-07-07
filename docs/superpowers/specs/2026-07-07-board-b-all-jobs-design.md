# Board B "งานทั้งหมด" — Design (2026-07-07)

## เป้าหมาย

กัญจน์: "ทุกงานที่ส่งต่อจากนี้ต้องขึ้น Board B ด้วย + การ์ดใหม่ 'งานทั้งหมด' ไว้ไล่ดูงาน
ง่ายๆ ไม่ต้องเลื่อน LINE". ตัดสินใจแล้ว (2026-07-07): **รวมงานย้อนหลังที่เคยส่งด้วย** +
**หน้าใหม่แยก** (ไม่โผล่ในหน้าหลัก).

## หลักการ

ระบบบันทึกทุกการส่ง LINE ลง `notification_queue` อยู่แล้ว (สถานะ sent + snapshot
ชื่องาน/จังหวัด/dept + `source_stage` + `created_at`) → อ่านจากตารางนี้ตรงๆ:
งานเก่าขึ้นทันที, งานใหม่ขึ้นอัตโนมัติ, **ไม่แตะระบบส่ง LINE เลย**.

## สถาปัตยกรรม (แพทเทิร์น N+187/188 เป๊ะ)

### Engine — `GET /api/portal/all-jobs?line_user_id&limit=500` (read-only)

- แหล่ง: `notification_queue` WHERE `customer_id=cid AND status='sent' AND is_test_data=0`
- **dedup ต่อ project_id** — เอาแถว `created_at` ล่าสุด (= ป้าย stage สะท้อนขั้นล่าสุดที่แจ้ง)
- field ต่อรายการ: `project_id, name (snapshot→projects_seen→pid), province (snapshot→ps),
  budget (join projects_seen live; ไม่มี=0), sent_at (created_at ล่าสุด), stage, starred`
- `stage` map จาก source_stage: `followed_winner→won · followed_prelim→prelim ·
  followed_cancelled→cancelled · province_tor_review*→pre · อื่นๆ (province_qualified/
  province_soft_location/api_enriched/followed_bid_open/manual_rebroadcast)→bidding`
- เรียง sent_at DESC, `limit` (default 500); คืน `{ok, count, jobs}` — `count` = จำนวน
  project ทั้งหมด (ไม่ติด limit) ให้การ์ด world ใช้ (world เรียก `limit=1` เอาแค่ count)
- guard `X-BMS-Secret` เหมือนทุกตัว

### Web

- `src/lib/portal-all-jobs.ts` — types + `getAllJobs(lineUserId, limit?)`
- `src/app/portal/jobs/page.tsx` + `_client.tsx` — หน้า "งานทั้งหมด" ธีม B:
  TopBar (back → world) → ช่องค้นหา (กรอง client-side จากชื่อ+จังหวัด) →
  รายการการ์ด: ชื่องาน (ลิงก์ `/portal/job/<pid>`) · 📍จังหวัด · 💰งบ (ถ้ามี) ·
  วันที่ส่งแจ้งเตือน · ป้าย stage (🔵 ยื่นซอง / 🟡 รอผล / 🏆 รู้ผลแล้ว / ⚪ วางแผน / ❌ ยกเลิก
  — ชุดเดียวกับ STAGE_META ของ world) · ⭐ ถ้าติดดาว
- `world/_client.tsx` + `page.tsx`: การ์ดใหม่ "📋 งานทั้งหมด" (Icons.Doc) ใน summary grid
  value = count, `href=/portal/jobs` (engine ล่ม → ซ่อนการ์ด ไม่ crash)

## Error handling

- engine ล่ม → หน้า jobs โชว์การ์ดแจ้ง + ปุ่มกลับ (แพทเทิร์นเดิม); การ์ด world ซ่อน
- งานที่ไม่มีใน projects_seen แล้ว → ใช้ snapshot ล้วน (budget = —)

## Testing / success criteria

1. `test_portal_all_jobs_api.py`: 403 secret ผิด; dedup (project ซ้ำหลายแถว → 1 รายการ
   stage ล่าสุด); ไม่รวม status≠sent + is_test_data=1; เรียงใหม่→เก่า; count ไม่ติด limit;
   stage map ถูก; serialize ได้ — ทุก assert ผ่าน
2. `npm run build` ผ่าน; SSR e2e: seed queue จริง → `/portal/jobs` render รายการ+ค้นหา,
   การ์ด world โชว์ count, ลิงก์เข้า detail ถูก
3. ระบบส่ง LINE / หน้า A: diff = 0
