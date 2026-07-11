# Follow จากหน้า "งานทั้งหมด" (/portal/jobs) — Design Spec

**วันที่:** 2026-07-12 · **สถานะ:** approved โดยคุณกัญจน์ (แชท 2026-07-12 "โอเค")
**Requirement:** "ตรงดูงานทั้งหมด สามารถกดติดตามงานได้จากตรงนั้นเลย"

## 1. Goal

การ์ดแต่ละงานในหน้า `/portal/jobs` (งานทั้งหมดที่เคยส่ง LINE) มีปุ่ม **🔔 ติดตาม** กดได้ทันที
โดยไม่ต้องเข้าหน้ารายละเอียดงานก่อน — เข้า `followed_jobs` เส้นเดียวกับปุ่มบนหน้า world

## 2. Behavior

- งานยังไม่ติดตาม → ปุ่ม `p-btn-primary` "🔔 ติดตาม" → POST `/api/portal/follow` (มีอยู่แล้ว)
  → optimistic เปลี่ยนเป็น "ติดตามแล้ว" (disabled) · ล้มเหลว → revert (pattern เดียวกับ `handleFollow` ของ world)
- งานติดตามอยู่แล้ว (`followed=true` จาก engine) → ปุ่ม disabled "ติดตามแล้ว" ตั้งแต่ SSR
- ปุ่มอยู่ในการ์ดที่ห่อด้วย `<Link>` → ต้อง `e.preventDefault()` + `e.stopPropagation()` กันเด้งหน้า detail
- ไม่มีปุ่มยกเลิกติดตาม (world ก็ไม่มี — YAGNI)

## 3. Touchpoints

| ไฟล์ | แก้อะไร |
|---|---|
| `scripts/bms_api.py` (`/api/portal/all-jobs` ~1909) | เพิ่ม 1 query: `SELECT project_id FROM followed_jobs WHERE customer_id=? AND status='active'` → job dict เพิ่ม key `"followed": bool` |
| `dashboard/web/src/lib/portal-all-jobs.ts` | `SentJob` เพิ่ม `followed: boolean` |
| `dashboard/web/src/app/portal/jobs/_client.tsx` | `SentJobCard` เพิ่มปุ่ม + `AllJobsClient` เก็บ state `followed: Set<string>` + `handleFollow` |

Endpoint follow ฝั่ง web/engine **ไม่แตะ** (มีครบแล้ว)

## 4. Success criteria

1. engine test: all-jobs คืน `followed=true` เฉพาะงานที่มีแถว followed_jobs active ของลูกค้าคนนั้น
2. `tsc` ผ่าน + regression test_portal_jobs.py เดิมเขียว
3. งานจริงหลัง deploy: เปิด /portal/jobs → งานที่ติดตามแล้วขึ้น "ติดตามแล้ว", กดติดตามงานใหม่ →
   แถว followed_jobs โผล่ใน DB + ปุ่มเปลี่ยนสถานะโดยไม่ reload
4. Deploy: VPS (engine) + Vercel (web) — approved ใน design แล้ว
