# ยกเลิกติดตามจากหน้างานทั้งหมด Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ปุ่ม "ติดตามแล้ว" บน /portal/jobs กดเพื่อยกเลิกติดตามได้ (toggle) — ต่อยอด N+197

**Architecture:** engine endpoint ใหม่ `POST /api/portal/unfollow` (mirror follow, เรียก `_record_unfollow` เดิม) → web relay route ใหม่ → ปุ่ม toggle optimistic สองทิศ

**Spec:** `docs/superpowers/specs/2026-07-12-unfollow-from-all-jobs-design.md`

## Global Constraints
- เส้น follow เดิม (engine + relay) ห้ามแตะ · ไม่มี confirm dialog
- copy ปุ่ม: "ติดตาม" / "ติดตามแล้ว" เดิม · deploy VPS + Vercel (approved)

---

### Task 1: engine — POST /api/portal/unfollow

**Files:** Modify `scripts/bms_api.py` (วางถัดจาก `portal_follow_job` ~1715), Test `scripts/test_portal_all_jobs_api.py`

- [ ] Step 1: เพิ่ม test ใน `main()` ของ test_portal_all_jobs_api.py (ก่อน `print("PASS...")`):
```python
    # N+197.1: unfollow → followed=false → follow กลับ → true (toggle roundtrip)
    r = await bms_api.portal_unfollow_job_json(_req({"line_user_id": "U1", "project_id": "P1"}), x_bms_secret="t")
    assert r == {"ok": True, "followed": False}, r
    r = await bms_api.portal_all_jobs_json(line_user_id='U1', x_bms_secret='t')
    assert {j["project_id"]: j["followed"] for j in r["jobs"]}['P1'] is False, r
    with bms_api.get_conn() as conn:
        st = conn.execute("SELECT status FROM followed_jobs WHERE customer_id=1 AND project_id='P1'").fetchone()[0]
    assert st == 'unfollowed', st
    r = await bms_api.portal_follow_job(_req({"line_user_id": "U1", "project_id": "P1"}), x_bms_secret="t")
    assert r["ok"] is True, r
    r = await bms_api.portal_all_jobs_json(line_user_id='U1', x_bms_secret='t')
    assert {j["project_id"]: j["followed"] for j in r["jobs"]}['P1'] is True, r
    # 403 / 404
    try:
        await bms_api.portal_unfollow_job_json(_req({"line_user_id": "U1", "project_id": "P1"}), x_bms_secret="bad")
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403
    try:
        await bms_api.portal_unfollow_job_json(_req({"line_user_id": "U9", "project_id": "P1"}), x_bms_secret="t")
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404
```
พร้อม helper `_req` (json body mock) ต้นไฟล์:
```python
class _req:
    def __init__(self, body): self._b = body
    async def json(self): return self._b
```
- [ ] Step 2: รัน → fail (no attribute portal_unfollow_job_json)
- [ ] Step 3: implement ใน bms_api.py ถัดจาก portal_follow_job:
```python
@app.post("/api/portal/unfollow")
async def portal_unfollow_job_json(
    request: Request,
    x_bms_secret=Header(default=None),
):
    """ยกเลิกติดตาม (N+197.1) — mirror /api/portal/follow แต่เรียก _record_unfollow
    (status='unfollowed' — เส้นเดียวกับปุ่มบนหน้า follow Board A). กดติดตามซ้ำ = กลับ active ได้."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    line_user_id = (body.get("line_user_id") or "").strip()
    project_id = (body.get("project_id") or "").strip()
    if not line_user_id or not project_id:
        raise HTTPException(status_code=400, detail="line_user_id + project_id required")
    res = _record_unfollow(line_user_id, project_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True, "followed": False}
```
- [ ] Step 4: รัน PASS + commit `feat(api): POST /api/portal/unfollow — ยกเลิกติดตามจาก Board B (N+197.1)`

### Task 2: web — relay + ปุ่ม toggle

**Files:** Create `dashboard/web/src/app/api/portal/unfollow/route.ts` (copy follow/route.ts เปลี่ยน path `/api/portal/unfollow` + comment), Modify `jobs/_client.tsx`

- [ ] Step 1: สร้าง relay route (copy จาก follow เปลี่ยน endpoint)
- [ ] Step 2: `_client.tsx` — ปุ่ม: ลบ `disabled`, `onClick` เรียก `onToggle`; `SentJobCard` รับ `onToggle`;
  `AllJobsClient`: `handleToggle(pid)` — ถ้าอยู่ใน Set → optimistic delete + POST unfollow, revert=add กลับ;
  ไม่อยู่ → optimistic add + POST follow, revert=delete (รวม handleFollow เดิมเข้า handleToggle)
- [ ] Step 3: `npx tsc --noEmit` ผ่าน + commit `feat(portal): ปุ่มติดตามแล้ว กดยกเลิกติดตามได้ (N+197.1)`

### Task 3: deploy + verify + บันทึก

- [ ] push → VPS pull+restart+health · Vercel deploy --prod
- [ ] verify VPS: follow→unfollow roundtrip งานเก่า (won/cancelled) ของลูกค้าจริงผ่าน endpoint จริง → DB status ตรงทุกขั้น → จบที่สถานะเดิมก่อน verify
- [ ] progress_log N+197.1 + push + Discord
