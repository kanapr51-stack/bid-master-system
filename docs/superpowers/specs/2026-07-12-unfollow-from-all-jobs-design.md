# ยกเลิกติดตามจากหน้า "งานทั้งหมด" — Design Spec

**วันที่:** 2026-07-12 · **สถานะ:** approved โดยคุณกัญจน์ ("โอเค ลุยเลย")
**Requirement:** ต่อยอด N+197 — "เมื่อกดติดตามได้แล้ว ก็อยากให้ยกเลิกติดตามได้ด้วย"

## 1. Behavior (/portal/jobs)

- ปุ่ม "ติดตามแล้ว" **ไม่ disabled แล้ว** → กด = ยกเลิกติดตาม → ปุ่มกลับเป็น "🔔 ติดตาม" (toggle)
- ไม่มี confirm dialog — misclick กู้ได้ด้วยการกดติดตามซ้ำ (upsert กลับ active ทันที)
- optimistic ทั้งสองทิศ + revert เมื่อ fetch fail (pattern N+197)
- ผลจริงของ unfollow: `followed_jobs.status='unfollowed'` → หยุดแจ้งเตือน lifecycle + หายจาก
  บอร์ด "งานที่ติดตาม" หน้า world (พฤติกรรมเดิมของ `_record_unfollow` ที่ Board A ใช้อยู่)

## 2. Touchpoints

| ไฟล์ | แก้อะไร |
|---|---|
| `scripts/bms_api.py` | endpoint ใหม่ `POST /api/portal/unfollow` — mirror `/api/portal/follow` เป๊ะ แต่เรียก `_record_unfollow`; คืน `{"ok": True, "followed": False}` · **ไม่แตะเส้น follow เดิม** |
| `dashboard/web/src/app/api/portal/unfollow/route.ts` | ไฟล์ใหม่ — copy relay ของ follow เปลี่ยน path เดียว |
| `dashboard/web/src/app/portal/jobs/_client.tsx` | ปุ่ม: เอา disabled ออก, `onClick` → followed? handleUnfollow : handleFollow; `handleUnfollow` = optimistic delete จาก Set + POST /api/portal/unfollow + revert on fail |

## 3. Out of scope (YAGNI)

- ปุ่มยกเลิกบนหน้า world (การ์ด discovery หายหลัง follow อยู่แล้ว) · confirm dialog

## 4. Success criteria

1. engine test: unfollow → status='unfollowed' + all-jobs คืน followed=false; follow ซ้ำ → กลับ active/true;
   secret ผิด → 403; ลูกค้าไม่มี → 404
2. tsc ผ่าน + regression test_portal_all_jobs_api เขียว
3. verify จริงบน VPS: ยิง unfollow ลูกค้าจริง 1 งาน → DB status='unfollowed' → follow กลับ → active
4. deploy VPS + Vercel (approved ใน design)
