# ยกเลิกติดตามจากบอร์ด "งานที่ติดตาม" หน้า world — Design Spec + Plan

**วันที่:** 2026-07-12 · **สถานะ:** approved โดยคุณกัญจน์ ("โอเค ลุยเลย")
**Requirement:** ต่อยอด N+197.1 — "ที่หน้า world ตรงงานที่ติดตาม ก็อยากให้ยกเลิกติดตามได้เหมือนกัน"

## Behavior

- `TrackedJobCard` (world/_client.tsx:81) เพิ่มปุ่มแถวล่าง (ข้าง "ดูรายละเอียด", ชิดขวา):
  - สถานะติดตาม (ปกติ) → ปุ่ม ghost "🔔 ติดตามแล้ว" → กด = POST /api/portal/unfollow
  - หลังยกเลิก → **การ์ดคงอยู่** ปุ่มเปลี่ยนเป็น primary "🔔 ติดตาม" (undo ในที่) → กด = POST /api/portal/follow
  - reload ครั้งถัดไปงานที่ unfollowed หายจากบอร์ดเอง (engine กรอง status='active' อยู่แล้ว)
- optimistic + revert on fail (pattern N+197.1) · ไม่มี confirm dialog
- นับเลขหัวข้อ/SumCard ไม่ต้องอัปเดตสด (เปลี่ยนตอน reload — ปุ่มคือ feedback หลัก)

## Touchpoints

- `dashboard/web/src/app/portal/world/_client.tsx` **ไฟล์เดียว**:
  `WorldClient` เพิ่ม state `unfollowed: Set<string>` + `handleTrackedToggle(pid)`;
  `TrackedJobCard` รับ `followed: boolean; onToggle: () => void` + ปุ่ม
- engine + relay routes: **ไม่แตะ** (ครบจาก N+197.1) → deploy Vercel อย่างเดียว

## Success criteria

1. `tsc --noEmit` ผ่าน
2. Vercel deploy READY + เปิดหน้า world เห็นปุ่มบนการ์ด tracked
3. logic toggle ยิงเส้นถูก (unfollow เมื่อกำลังติดตาม / follow เมื่อ undo) — ตรวจจากโค้ด + reuse
   เส้นที่ verify จริงไปแล้วใน N+197.1

## Plan (แก้ไฟล์เดียว — inline)

1. `TrackedJobCard`: props + ปุ่มใต้การ์ด (wrapper flex space-between กับลิงก์ detail)
2. `WorldClient`: state + handler + ส่ง props ที่จุด render (บรรทัด ~385)
3. tsc → commit → vercel deploy --prod → progress_log + Discord
