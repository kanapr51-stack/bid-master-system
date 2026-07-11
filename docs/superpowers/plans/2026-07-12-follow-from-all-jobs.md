# Follow จากหน้างานทั้งหมด Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ปุ่ม 🔔 ติดตาม บนการ์ดแต่ละงานใน `/portal/jobs` — กดติดตามได้จากลิสต์ พร้อมสถานะ "ติดตามแล้ว" ตั้งแต่โหลดหน้า

**Architecture:** engine `/api/portal/all-jobs` เพิ่ม flag `followed` (query followed_jobs active 1 ครั้ง) → web type `SentJob.followed` → ปุ่มบนการ์ด reuse `/api/portal/follow` + optimistic state (pattern `handleFollow` ของ world)

**Tech Stack:** FastAPI engine (script tests) + Next.js Board B (tsc)

**Spec:** `docs/superpowers/specs/2026-07-12-follow-from-all-jobs-design.md`

## Global Constraints
- endpoint follow เดิม (web relay + engine `_record_follow`) **ห้ามแตะ**
- ปุ่มใน `<Link>` ต้อง preventDefault+stopPropagation
- copy: "ติดตาม" / "ติดตามแล้ว" (ตรงหน้า world)
- deploy ครบสองฝั่ง: VPS (engine) + Vercel (web) — approved แล้วใน spec

---

### Task 1: engine — all-jobs เพิ่ม `followed`

**Files:** Modify `scripts/bms_api.py` (~1934), Test `scripts/test_portal_all_jobs_api.py`
**Produces:** job dict ใน all-jobs เพิ่ม key `"followed": bool` (true เฉพาะ status='active')

- [ ] Step 1: แก้ test — ใน `seed()` เพิ่ม:
```python
        # P1 ติดตามอยู่ (active) / P5 เคยติดตามแล้วเลิก (unfollowed) → ต้องเป็น false
        conn.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                     "VALUES (1,'P1','2026-07-05','D0','W0','active')")
        conn.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                     "VALUES (1,'P5','2026-07-06','D0','D0','unfollowed')")
```
และ asserts (หลังบรรทัด byid P1 budget/starred):
```python
    assert byid['P1']["followed"] is True, byid['P1']
    assert byid['P2']["followed"] is False and byid['P5']["followed"] is False, byid
```
- [ ] Step 2: รัน `python scripts/test_portal_all_jobs_api.py` → คาด KeyError/AssertionError `followed`
- [ ] Step 3: implement ใน `portal_all_jobs_json` — หลังบรรทัด `starred_ids = ...`:
```python
        followed_ids = {r["project_id"] for r in conn.execute(
            "SELECT project_id FROM followed_jobs WHERE customer_id=? AND status='active'",
            (cid,)).fetchall()}
```
และใน job dict เพิ่ม `"followed": pid in followed_ids,`
- [ ] Step 4: รัน test → PASS + regression `python scripts/test_portal_jobs.py`
- [ ] Step 5: commit `feat(api): all-jobs ส่ง flag followed — ปุ่มติดตามบนหน้างานทั้งหมด (N+197)`

### Task 2: web — ปุ่มติดตามบนการ์ด

**Files:** Modify `dashboard/web/src/lib/portal-all-jobs.ts`, `dashboard/web/src/app/portal/jobs/_client.tsx`
**Consumes:** `SentJob.followed` (Task 1) · POST `/api/portal/follow` (มีอยู่)

- [ ] Step 1: `portal-all-jobs.ts` — `SentJob` เพิ่ม `followed: boolean;`
- [ ] Step 2: `_client.tsx`:
  - `SentJobCard({ job, followed, onFollow })` — แถว meta ล่างเพิ่มปุ่มขวาสุด:
```tsx
<button
  className={`p-btn ${followed ? 'p-btn-ghost' : 'p-btn-primary'}`}
  disabled={followed}
  onClick={e => { e.preventDefault(); e.stopPropagation(); onFollow(); }}
  style={{ height: 30, padding: '0 12px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5, marginLeft: 'auto' }}
>
  <Icons.Bell size={12} />{followed ? 'ติดตามแล้ว' : 'ติดตาม'}
</button>
```
  - `AllJobsClient`: state `followed` = `Set(jobs ที่ followed)` + `handleFollow(pid)` optimistic add → POST → revert on fail (pattern world 253-270 แต่ add เข้า Set แทน remove การ์ด)
- [ ] Step 3: `cd dashboard/web && npx tsc --noEmit` → ผ่าน
- [ ] Step 4: commit `feat(portal): ปุ่มติดตามงานจากหน้างานทั้งหมด /portal/jobs (N+197)`

### Task 3: deploy + verify + บันทึก

- [ ] Step 1: push origin → VPS pull + restart bms-api + health 200
- [ ] Step 2: Vercel `deploy --prod`
- [ ] Step 3: verify VPS: all-jobs ของลูกค้าจริงมี followed ผสม true/false ตรง followed_jobs
- [ ] Step 4: progress_log entry N+197 + commit + push + Discord
