# Portal Real Jobs — Phase 1 (section "งานที่ติดตาม") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** หน้า `/portal/world` โชว์งานที่ลูกค้าติดตามจริง (followed_jobs) แทน `SEED_JOBS` และ ⭐ ผูก `project_id` จริงเขียน `job_stars`

**Architecture:** เพิ่ม JSON endpoint บน `bms_api` (VPS) ที่ reuse `_portal_jobs()`/`toggle_star()` ที่มีอยู่ → Next.js (`dashboard/web`) ดึงผ่าน lib ฝั่ง server แล้ว render ตาม stage. Auth = line_user_id (session) + X-BMS-Secret เหมือน `/api/portal/customer`

**Tech Stack:** FastAPI (bms_api.py, Python venv VPS) · Next.js 16/React 19/TS (dashboard/web, Vercel) · SQLite bms_customers.db

## Global Constraints
- bms_api endpoint ใหม่ต้อง guard `x_bms_secret != BMS_INTERNAL_SECRET → 403` (ค่าจาก env, ตั้งไว้แล้วทั้ง VPS .env + Vercel)
- ห้าม assume schema — ตารางที่ใช้มีจริง: `followed_jobs, projects_seen, project_locations, project_enrichments, price_predictions, bid_results, job_stars` (ยืนยันบน prod แล้ว)
- Thai ต้องเก็บ/ส่งเป็น UTF-8 (FastAPI default ปลอดภัย)
- ทดสอบ Python ฝั่ง engine: ใช้ asyncio เรียก handler ตรง + scratch DB copy (`BMS_DATA_DIR`/`BMS_DB_PATH` ชี้ scratch) — **ห้ามรันบน prod DB / ห้าม seed test data ลง prod**
- Frontend ไม่มี JS test runner → verify ด้วย `npx tsc --noEmit` + smoke (curl/บอร์ดจริง)
- Deploy: scp ไฟล์ → VPS + restart `bms-api`; `vercel deploy --prod`; commit+push + reconcile VPS git (stash+ff-pull) — **ทุก deploy/push หลัง confirm**
- `_portal_jobs(user_id)` คืน dict `{won, prelim, bidding, pre, cancelled}`; แต่ละ job มี key: `project_id, name, location, deadline, deadline_time, pred_lo, pred_hi, winner, winner_price, winner_disc, competitors, bidders, prelim_low, prelim_n` (+ `starred` เติมท้าย). **budget ยังไม่อยู่ใน dict** → Task 1 เติม

---

## Task 1: Backend — เติม budget ใน _portal_jobs + GET /api/portal/jobs

**Files:**
- Modify: `scripts/bms_api.py` (ใน `_portal_jobs`: เติม `"budget"` ลง job dict; เพิ่ม endpoint ใหม่หลัง `portal_upsert_customer`)
- Test: `scripts/test_portal_jobs_api.py` (สร้างใหม่)

**Interfaces:**
- Consumes: `_portal_jobs(user_id) -> dict`, `get_conn()`, `BMS_INTERNAL_SECRET`
- Produces: `GET /api/portal/jobs?line_user_id=&x_bms_secret(header)` → `{"ok":true,"jobs":{won:[],prelim:[],bidding:[],pre:[],cancelled:[]}}` โดยแต่ละ job = TrackedJob dict (มี `budget`, `starred`)

- [ ] **Step 1: เติม budget ลง job dict ใน _portal_jobs**

ใน `scripts/bms_api.py` หา block สร้าง `job = {...}` ใน `_portal_jobs` (มี key `"pred_hi"`) แล้วเพิ่ม `"budget"`:

```python
            job = {"project_id": pid, "name": ps["project_name"] or pid, "location": location,
                   "deadline": deadline, "deadline_time": deadline_time,
                   "budget": budget,
                   "pred_lo": pr["area_price_lo"] if pr else None,
                   "pred_hi": pr["area_price_hi"] if pr else None,
                   "winner": None, "winner_price": None, "winner_disc": None, "competitors": [],
                   "bidders": [], "prelim_low": None, "prelim_n": 0}
```

(`budget` เป็น local var อยู่แล้วเหนือบรรทัดนี้ = `ps["budget"] or 0`)

- [ ] **Step 2: เพิ่ม endpoint GET /api/portal/jobs**

ต่อท้ายฟังก์ชัน `portal_upsert_customer` (จบที่ `return {"ok": True, "is_new": is_new, "customer_id": cid}`) เพิ่ม:

```python
@app.get("/api/portal/jobs")
async def portal_get_jobs(
    line_user_id: str = Query(...),
    x_bms_secret=Header(default=None),
):
    """งานที่ลูกค้าติดตามจริง (followed_jobs) จัดกลุ่ม stage — สำหรับบอร์ด Next.js."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    empty = {"won": [], "prelim": [], "bidding": [], "pre": [], "cancelled": []}
    groups = _portal_jobs(line_user_id)
    if groups is None:
        return {"ok": True, "jobs": empty}
    return {"ok": True, "jobs": groups}
```

- [ ] **Step 3: เขียน test (asyncio direct, scratch DB)**

สร้าง `scripts/test_portal_jobs_api.py`:

```python
"""test_portal_jobs_api.py — GET /api/portal/jobs (reuse _portal_jobs) + 403 guard."""
import os, sys, asyncio, sqlite3, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
src = Path(__file__).parent.parent / "data" / "bms_customers.db"
shutil.copy(src, SCRATCH / "bms_customers.db")
os.environ["BMS_DATA_DIR"] = str(SCRATCH)
os.environ["BMS_DB_PATH"] = str(SCRATCH / "bms_customers.db")
os.environ["BMS_INTERNAL_SECRET"] = "t"
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException

def setup_follow():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UJOBS','x','trial',1,'2026-06-01T10:00:00+07:00','2026-06-01T10:00:00+07:00')")
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='UJOBS'").fetchone()[0]
    c.execute("INSERT OR IGNORE INTO projects_seen (project_id,announce_type,province,budget,project_name,first_seen_at) "
              "VALUES ('P1','D0','นครพนม',1000000,'งานทดสอบถนน','2026-06-01T10:00:00+07:00')")
    c.execute("INSERT OR IGNORE INTO followed_jobs (customer_id,project_id,starred_stage,status,created_at,updated_at) "
              "VALUES (?,?,?,?,?,?)", (cid, 'P1', 'D0', 'active', 't', 't'))
    c.commit()
    return cid

async def main():
    cid = setup_follow()
    # 403
    try:
        await bms_api.portal_get_jobs(line_user_id='UJOBS', x_bms_secret='wrong'); assert False, "no 403"
    except HTTPException as e:
        assert e.status_code == 403
    # no customer → empty groups
    r0 = await bms_api.portal_get_jobs(line_user_id='UNONE', x_bms_secret='t')
    assert r0["ok"] and r0["jobs"]["bidding"] == [], r0
    # real follow → P1 ใน bidding (D0) + budget + starred=False
    r = await bms_api.portal_get_jobs(line_user_id='UJOBS', x_bms_secret='t')
    bidding = r["jobs"]["bidding"]
    assert any(j["project_id"] == 'P1' for j in bidding), r["jobs"]
    j = next(j for j in bidding if j["project_id"] == 'P1')
    assert j["budget"] == 1000000 and j["name"] == 'งานทดสอบถนน' and j["starred"] is False, j
    print("PASS test_portal_jobs_api")

asyncio.run(main())
```

- [ ] **Step 4: รัน test ให้ FAIL ก่อน (ยังไม่เพิ่ม endpoint — สลับลำดับ: รันหลังเขียนจริง)**

> หมายเหตุ TDD: ในทางปฏิบัติ ทำ Step 1-2 (เพิ่มโค้ด) แล้ว Step 3-5. ถ้าต้องการ red-first: comment endpoint ออก รัน → `AttributeError: module 'bms_api' has no attribute 'portal_get_jobs'`

Run: `cd /c/Bid-Master-System && PYTHONUTF8=1 python scripts/test_portal_jobs_api.py`
Expected (ก่อนเพิ่ม endpoint): FAIL `AttributeError ... portal_get_jobs`

- [ ] **Step 5: รัน test ให้ PASS**

Run: `cd /c/Bid-Master-System && PYTHONUTF8=1 python scripts/test_portal_jobs_api.py`
Expected: `PASS test_portal_jobs_api`

- [ ] **Step 6: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_jobs_api.py
git commit -m "feat(portal): GET /api/portal/jobs — งานที่ติดตามจริงเป็น JSON (+budget ใน _portal_jobs)"
```

---

## Task 2: Backend — POST /api/portal/star (toggle job_stars)

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่ม endpoint หลัง `portal_get_jobs`)
- Test: `scripts/test_portal_star_api.py` (สร้างใหม่)

**Interfaces:**
- Consumes: `portal_views.toggle_star(conn, customer_id, pid)`, `portal_views.starred_project_ids(conn, cid)`, `get_conn()`, `BMS_INTERNAL_SECRET`
- Produces: `POST /api/portal/star {line_user_id, project_id}` → `{"ok":true,"starred":bool}` (สถานะหลัง toggle); ไม่มี customer → 404

- [ ] **Step 1: เพิ่ม endpoint POST /api/portal/star**

```python
@app.post("/api/portal/star")
async def portal_star_toggle_json(
    request: Request,
    x_bms_secret=Header(default=None),
):
    """Toggle ⭐ (job_stars) จากบอร์ด Next.js — keyed line_user_id."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    line_user_id = (body.get("line_user_id") or "").strip()
    project_id = (body.get("project_id") or "").strip()
    if not line_user_id or not project_id:
        raise HTTPException(status_code=400, detail="line_user_id + project_id required")
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (line_user_id,)).fetchone()
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found")
        cid = cust["id"]
        portal_views.toggle_star(conn, cid, project_id)
        starred = project_id in portal_views.starred_project_ids(conn, cid)
    return {"ok": True, "starred": starred}
```

- [ ] **Step 2: เขียน test**

สร้าง `scripts/test_portal_star_api.py`:

```python
"""test_portal_star_api.py — POST /api/portal/star toggle job_stars."""
import os, sys, asyncio, sqlite3, tempfile, shutil
from pathlib import Path
SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException

class FakeReq:
    def __init__(self, d): self._d = d
    async def json(self): return self._d

async def main():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('USTAR','x','trial',1,'t','t')"); c.commit()
    # 404 ไม่มี customer
    try:
        await bms_api.portal_star_toggle_json(FakeReq({'line_user_id':'UNONE','project_id':'P9'}), x_bms_secret='t'); assert False
    except HTTPException as e: assert e.status_code == 404
    # toggle on
    r1 = await bms_api.portal_star_toggle_json(FakeReq({'line_user_id':'USTAR','project_id':'P9'}), x_bms_secret='t')
    assert r1["starred"] is True, r1
    # toggle off
    r2 = await bms_api.portal_star_toggle_json(FakeReq({'line_user_id':'USTAR','project_id':'P9'}), x_bms_secret='t')
    assert r2["starred"] is False, r2
    print("PASS test_portal_star_api")

asyncio.run(main())
```

- [ ] **Step 3: รัน test ให้ PASS**

Run: `cd /c/Bid-Master-System && PYTHONUTF8=1 python scripts/test_portal_star_api.py`
Expected: `PASS test_portal_star_api`

- [ ] **Step 4: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_star_api.py
git commit -m "feat(portal): POST /api/portal/star — toggle job_stars จากบอร์ด"
```

---

## Task 3: Frontend — lib/portal-jobs.ts (engine client งาน + ดาว)

**Files:**
- Create: `dashboard/web/src/lib/portal-jobs.ts`

**Interfaces:**
- Consumes: env `BMS_API_URL`, `BMS_INTERNAL_SECRET`; engine `GET /api/portal/jobs`
- Produces: type `TrackedJob`, `JobGroups`; `getPortalJobs(lineUserId): Promise<JobGroups>`

- [ ] **Step 1: สร้างไฟล์**

```typescript
/**
 * portal-jobs.ts — ดึงงานที่ลูกค้าติดตามจริงจาก engine (bms_api) สำหรับบอร์ด /portal/world
 */
const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export type JobStage = "won" | "prelim" | "bidding" | "pre" | "cancelled";

export interface TrackedJob {
  project_id: string;
  name: string;
  location: string;
  deadline: string;
  deadline_time: string;
  budget: number;
  pred_lo: number | null;
  pred_hi: number | null;
  winner: string | null;
  winner_price: number | null;
  winner_disc: number | null;
  starred: boolean;
}

export type JobGroups = Record<JobStage, TrackedJob[]>;

const EMPTY: JobGroups = { won: [], prelim: [], bidding: [], pre: [], cancelled: [] };

export async function getPortalJobs(lineUserId: string): Promise<JobGroups> {
  if (!lineUserId) return EMPTY;
  const url = `${BMS_API_URL}/api/portal/jobs?line_user_id=${encodeURIComponent(lineUserId)}`;
  const res = await fetch(url, {
    headers: { "X-BMS-Secret": BMS_SECRET },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine GET jobs failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; jobs: JobGroups };
  return data.jobs ?? EMPTY;
}
```

- [ ] **Step 2: typecheck**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: exit 0 (ไม่มี error)

- [ ] **Step 3: Commit**

```bash
git add dashboard/web/src/lib/portal-jobs.ts
git commit -m "feat(portal): lib/portal-jobs.ts — engine client ดึงงานติดตาม"
```

---

## Task 4: Frontend — route /api/portal/star (relay session → engine)

**Files:**
- Create: `dashboard/web/src/app/api/portal/star/route.ts`

**Interfaces:**
- Consumes: `parseSessionCookie`, `COOKIE_NAME` (`@/lib/session`); engine `POST /api/portal/star`
- Produces: `POST /api/portal/star {project_id}` (session ให้ line_user_id) → `{ok, starred}`

- [ ] **Step 1: สร้าง route**

```typescript
/**
 * POST /api/portal/star { project_id } — toggle ⭐ (job_stars) ของงานจริง
 * line_user_id มาจาก session; relay ไป engine ด้วย X-BMS-Secret (ไม่หลุด client)
 */
import { NextRequest, NextResponse } from "next/server";
import { parseSessionCookie, COOKIE_NAME } from "@/lib/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export async function POST(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ ok: false, error: "Invalid session" }, { status: 401 });

  let projectId = "";
  try { projectId = ((await req.json()).project_id ?? "").toString().trim(); }
  catch { return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 }); }
  if (!projectId) return NextResponse.json({ ok: false, error: "project_id required" }, { status: 400 });

  try {
    const r = await fetch(`${BMS_API_URL}/api/portal/star`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET },
      body: JSON.stringify({ line_user_id: session.lineUserId, project_id: projectId }),
      cache: "no-store",
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : r.status });
  } catch (e) {
    console.error("[/api/portal/star]", e);
    return NextResponse.json({ ok: false, error: "engine unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 2: typecheck**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add dashboard/web/src/app/api/portal/star/route.ts
git commit -m "feat(portal): route /api/portal/star relay session→engine job_stars"
```

---

## Task 5: Frontend — world/page.tsx ดึงงานจริง + _client.tsx render ตาม stage

**Files:**
- Modify: `dashboard/web/src/app/portal/world/page.tsx`
- Modify: `dashboard/web/src/app/portal/world/_client.tsx`

**Interfaces:**
- Consumes: `getPortalJobs` + `TrackedJob`/`JobGroups` (Task 3); route `/api/portal/star` (Task 4)
- Produces: บอร์ดแสดง TrackedJob จริงตาม stage; ⭐ → job_stars

- [ ] **Step 1: page.tsx — ดึงงานจริงแทน SEED_JOBS**

ใน `world/page.tsx` แทน import `SEED_JOBS` และการส่ง `jobs={SEED_JOBS}`:

```tsx
import { getPortalJobs, type JobGroups } from '@/lib/portal-jobs';
// ...ใน component หลังได้ session.lineUserId:
let jobGroups: JobGroups = { won: [], prelim: [], bidding: [], pre: [], cancelled: [] };
try { jobGroups = await getPortalJobs(session.lineUserId); } catch { /* engine ล่ม → ว่าง */ }
```

แล้วเปลี่ยน prop ที่ส่งให้ `WorldClient` จาก `jobs={SEED_JOBS}` + `initialStarred={notes.starred ?? []}` เป็น:

```tsx
      jobGroups={jobGroups}
```

(ลบ `jobs={SEED_JOBS}` และ `initialStarred=...`; ลบ `SEED_JOBS` ออกจาก import `@/lib/portal-data`)

- [ ] **Step 2: _client.tsx — รับ jobGroups + render ตาม stage**

แก้ `WorldClientProps`: ลบ `jobs: PortalJob[]` และ `initialStarred?`, เพิ่ม `jobGroups: JobGroups`. import `type { JobGroups, TrackedJob, JobStage } from '@/lib/portal-jobs'`.

แทน logic เดิม (biddingJobs/pretorJobs/jobsByClass ที่อิง PortalJob) ด้วยการ render ตาม stage. โครงขั้นต่ำ:

```tsx
const STAGE_META: { key: JobStage; label: string; icon: string }[] = [
  { key: 'bidding', label: 'ยื่นซองได้', icon: '🔵' },
  { key: 'prelim',  label: 'รอผล',      icon: '🟡' },
  { key: 'won',     label: 'รู้ผลแล้ว',  icon: '🏆' },
  { key: 'pre',     label: 'ระยะวางแผน', icon: '⚪' },
  { key: 'cancelled', label: 'ยกเลิก',  icon: '❌' },
];

function daysLeftOf(deadline: string): number | null {
  if (!deadline) return null;
  const d = new Date(deadline);
  if (isNaN(d.getTime())) return null;
  return Math.max(0, Math.ceil((d.getTime() - Date.now()) / 86400000));
}
```

`starred` state เริ่มจากงานที่ `starred===true` ใน jobGroups:

```tsx
const allJobs = STAGE_META.flatMap(s => jobGroups[s.key]);
const [starred, setStarred] = useState<Set<string>>(
  () => new Set(allJobs.filter(j => j.starred).map(j => j.project_id))
);

const toggleStar = async (projectId: string) => {
  const next = new Set(starred);
  if (next.has(projectId)) next.delete(projectId); else next.add(projectId);
  setStarred(next);
  try {
    await fetch('/api/portal/star', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId }),
    });
  } catch { /* non-critical: revert */ setStarred(starred); }
};
```

การ์ดงาน (ต่อ TrackedJob): โชว์ `name`, `location`, ราคากลาง (`budget`), นับถอยหลัง (`daysLeftOf(deadline)`), ช่วงราคาคาด (`pred_lo`–`pred_hi`), ผู้ชนะ (`winner` ถ้า stage won), ปุ่ม ⭐ (`starred.has(project_id)` → `toggleStar(project_id)`).

แต่ละ stage section: render เฉพาะที่ `jobGroups[key].length > 0`. ถ้า `allJobs.length === 0` → empty state: `"ยังไม่มีงานที่ติดตาม — ระบบจะเพิ่มให้เมื่อเจองานตรงพื้นที่/หมวดของท่าน"`.

> หมายเหตุ: ลบส่วนที่อ้าง `PortalJob`, `matchedClassId`, `distance`, `feedTab`/`pretor` (discovery — Phase 2). คง TopBar/Tier banner/QuotaRing เดิมได้.

- [ ] **Step 3: typecheck**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: exit 0 (แก้ทุก type error ที่อ้าง PortalJob/SEED_JOBS/initialStarred จนหมด)

- [ ] **Step 4: ยืนยันไม่มี SEED_JOBS เหลือใน path world**

Run: `cd dashboard/web && grep -rn "SEED_JOBS\|initialStarred\|matchedClassId" src/app/portal/world/`
Expected: ไม่มีผลลัพธ์ (ว่าง)

- [ ] **Step 5: Commit**

```bash
git add dashboard/web/src/app/portal/world/page.tsx dashboard/web/src/app/portal/world/_client.tsx
git commit -m "feat(portal): world board โชว์งานติดตามจริงตาม stage + ⭐→job_stars (เลิก SEED_JOBS)"
```

---

## Task 6: Deploy + verify (prod)

**Files:** (deploy เท่านั้น — confirm กัญจน์ก่อน)

- [ ] **Step 1: Deploy engine (scp + restart)**

```bash
scp -i ~/.ssh/bms_vps scripts/bms_api.py root@45.76.156.166:/opt/bms/app/scripts/
ssh -i ~/.ssh/bms_vps root@45.76.156.166 'chown bms:bms /opt/bms/app/scripts/bms_api.py && systemctl restart bms-api.service && sleep 2 && systemctl is-active bms-api.service'
```
Expected: `active`

- [ ] **Step 2: Smoke test engine (real follow, read-only)**

```bash
S=<BMS_INTERNAL_SECRET>
curl -s -H "X-BMS-Secret: $S" "https://api.butler-bms.com/api/portal/jobs?line_user_id=<real_id_ที่มี follow>" | head -c 300
```
Expected: JSON มี `"jobs"` และมีงานใน bidding/won

- [ ] **Step 3: Deploy web**

```bash
cd dashboard/web && vercel deploy --prod --yes
```
Expected: READY, aliased `bid-master-dashboard.vercel.app`

- [ ] **Step 4: Smoke test ⭐ E2E (throwaway → cleanup)**

ใช้ throwaway pid กับ real customer ผ่าน `/api/portal/star` (มี session ไม่ได้จาก curl — แทนด้วยยิงตรง engine ด้วย \u-safe), เช็ค `job_stars`, แล้วลบ row ทดสอบ (เหมือน pattern งาน N+176)

- [ ] **Step 5: Commit/push + reconcile VPS git**

```bash
git push origin main
ssh -i ~/.ssh/bms_vps root@45.76.156.166 'cd /opt/bms/app && git fetch origin main && [ -z "$(git diff --ignore-cr-at-eol origin/main -- scripts/bms_api.py)" ] && git stash push -- scripts/bms_api.py && git pull --ff-only origin main && git stash drop'
```

- [ ] **Step 6: Sophia sanity + วัด TTFB บอร์ด**

dispatch Sophia (followed_jobs/job_stars ไม่เพี้ยน, ไม่มี test row ค้าง) + วัด `/portal/world` TTFB

---

## Self-review notes
- Spec coverage: SC#1 (Task5 step1-2 + Task6 smoke), SC#2 empty state (Task5 step2), SC#3 ⭐→job_stars (Task2+4+5+6 smoke), SC#4 ไม่มี SEED_JOBS (Task5 step4). ครบ
- ⭐ semantics: บอร์ดเขียน job_stars ผ่าน Task4 route → Task2 endpoint → `toggle_star` เดิม. ชุดเดียวกับลิงก์ LINE ✅
- defer: discovery section + matchedKeywords/distance/sme (Phase 2)
