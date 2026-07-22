# Sebastian Chat Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "Sebastian" tab to the portal that shows the customer's notification history as a chat feed — one message bubble per job, worded exactly like the real LINE notifications, oldest at top / newest at bottom.

**Architecture:** A new read-only backend endpoint (`GET /api/portal/sebastian-feed`) dedupes `notification_queue` rows per project (same rule as the existing `/api/portal/all-jobs`) and reconstructs each job's message text by calling the *same* `format_notification()` function the real sender uses — no message-formatting logic is duplicated in TypeScript. The frontend renders those messages as chat bubbles grouped by day, oldest-to-newest, in a new `/portal/sebastian` route reachable from a new bottom-nav tab.

**Tech Stack:** Python 3 / FastAPI (`scripts/bms_api.py`), SQLite (`bms_customers.db`), Next.js App Router / TypeScript (`dashboard/web`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-23-sebastian-chat-feed-design.md` — every requirement in it must map to a task below.
- Reuse `format_notification()` verbatim for message content — do not re-implement message formatting in TypeScript.
- No live PDF/API enrichment calls from the new endpoint — read only what's already cached in `projects_seen` / `project_locations`.
- `bms-api.service` is a **persistent** uvicorn process (unlike the oneshot notify scripts fixed in N+208/209) — any backend change here requires `systemctl restart bms-api` on deploy, not just a `git pull`.
- Follow existing patterns exactly: auth (`parseSessionCookie`/`COOKIE_NAME`), the `X-BMS-Secret` header guard, the "engine down" card pattern from `/portal/jobs`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/Sebastian_LINE_Sender.py` | *(modify)* `format_notification()` gains `record_prediction: bool = True` param so read-only reconstructions don't re-log closed-loop predictions |
| `scripts/test_format_notification_record_prediction.py` | *(new)* proves the flag works, proves default behavior unchanged |
| `scripts/bms_api.py` | *(modify)* new `GET /api/portal/sebastian-feed` endpoint |
| `scripts/test_portal_sebastian_feed_api.py` | *(new)* endpoint test — dedup, ordering, message parity, secret/404 handling |
| `dashboard/web/src/lib/portal-sebastian-feed.ts` | *(new)* types + fetch wrapper for the new endpoint |
| `dashboard/web/src/lib/portal-day-groups.ts` | *(new)* shared day-grouping helpers, extracted from `jobs/_client.tsx` (now used twice) |
| `dashboard/web/src/app/portal/jobs/_client.tsx` | *(modify)* import day-grouping helpers from the new shared lib instead of defining them locally |
| `dashboard/web/src/app/portal/sebastian/page.tsx` | *(new)* server component — auth, fetch, render |
| `dashboard/web/src/app/portal/sebastian/_client.tsx` | *(new)* chat bubble UI |
| `dashboard/web/src/app/portal/portal.css` | *(modify)* add `.p-chat-bubble` styles |
| `dashboard/web/src/app/portal/_shell.tsx` | *(modify)* add `BotIcon` + `Sebastian` nav entry |

---

### Task 1: `format_notification()` gains a `record_prediction` flag

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py:232-314` (function signature + the closed-loop save block)
- Test: `scripts/test_format_notification_record_prediction.py`

**Interfaces:**
- Consumes: nothing new (pure addition to an existing function)
- Produces: `format_notification(..., record_prediction: bool = True) -> str` — when `False`, skips the `save_prediction()` side effect entirely. Task 2 relies on being able to pass `record_prediction=False`.

**Why this task exists:** `format_notification()` currently *always* writes to `price_predictions` (closed-loop win-rate tracking) whenever it renders a D0 job with a resolvable prediction. The new chat-history endpoint calls this function to *redisplay* old messages every time the customer opens the tab — without this flag, every page view would silently re-log a duplicate prediction row for the same project. This must be fixed before Task 2 exists, not after.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_format_notification_record_prediction.py`:

```python
"""test_format_notification_record_prediction.py — record_prediction=False (Sebastian chat
feed, N+211) ต้องไม่เขียน price_predictions ซ้ำตอน reconstruct ข้อความมาโชว์ในหน้าประวัติ"""
import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls
import Sebastian_Customer_DB as db
import cgd_intel as _ci

_PRED_CTX = {"lines": ["💡 TEST"], "prediction": {"budget": 100}, "explain": None}


def test_default_record_prediction_true_still_saves():
    _ci.intel_context = lambda *a, **k: dict(_PRED_CTX)
    with patch.object(db, "save_prediction") as mock_save:
        ls.format_notification("P1", province="นครพนม", project_name="ถนน", announce_type="D0")
        mock_save.assert_called_once()
    print("✅ default (ไม่ระบุ record_prediction) ยังบันทึกเหมือนเดิม")


def test_record_prediction_false_skips_save():
    _ci.intel_context = lambda *a, **k: dict(_PRED_CTX)
    with patch.object(db, "save_prediction") as mock_save:
        ls.format_notification("P2", province="นครพนม", project_name="ถนน", announce_type="D0",
                               record_prediction=False)
        mock_save.assert_not_called()
    print("✅ record_prediction=False ไม่เขียน price_predictions ซ้ำ")


test_default_record_prediction_true_still_saves()
test_record_prediction_false_skips_save()
print("ALL PASS format_notification record_prediction flag")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts && python test_format_notification_record_prediction.py`
Expected: FAIL — `TypeError: format_notification() got an unexpected keyword argument 'record_prediction'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/Sebastian_LINE_Sender.py`, change the function signature at line 232:

```python
def format_notification(project_id: str, province: str = "",
                         announce_type: str = "D0", budget: float = 0,
                         project_name: str = "", dept_name: str = "",
                         deliver_day: int = 0, report_date: str = "",
                         bid_submit_date: str = "", bid_submit_time: str = "",
                         is_backfill: bool = False,
                         source_stage: str = "api_enriched",
                         record_prediction: bool = True) -> str:
```

And change the closed-loop block at line ~293-304 from:

```python
    # competitive intel — closed-loop prediction logging ยังทำเหมือนเดิม (resolve ไว้ข้างบนแล้ว)
    if intel_ctx:
        if intel_ctx.get("prediction") and project_id:   # เก็บคำทำนายไว้เทียบตอนประกาศผล (closed-loop)
            try:
                from Sebastian_Customer_DB import save_prediction
                _pp = {"project_id": project_id, **intel_ctx["prediction"]}
                if intel_ctx.get("explain") is not None:
                    import json as _json
                    _pp["explain_json"] = _json.dumps(intel_ctx["explain"], ensure_ascii=False)
                save_prediction(_pp)
            except Exception:
                pass
        # บล็อกวิเคราะห์เต็มอยู่ใน Bid Board (ดูได้หลังกดติดตามงานนี้ — ลิงก์อยู่หน้า /follow ไม่ใช่ในข้อความนี้)
```

to:

```python
    # competitive intel — closed-loop prediction logging ยังทำเหมือนเดิม (resolve ไว้ข้างบนแล้ว)
    # record_prediction=False: ใช้ตอน reconstruct ข้อความเก่ามาโชว์ (เช่น Sebastian chat feed)
    # — ห้ามเขียน price_predictions ซ้ำทุกครั้งที่ลูกค้าเปิดดูประวัติ
    if intel_ctx and record_prediction:
        if intel_ctx.get("prediction") and project_id:   # เก็บคำทำนายไว้เทียบตอนประกาศผล (closed-loop)
            try:
                from Sebastian_Customer_DB import save_prediction
                _pp = {"project_id": project_id, **intel_ctx["prediction"]}
                if intel_ctx.get("explain") is not None:
                    import json as _json
                    _pp["explain_json"] = _json.dumps(intel_ctx["explain"], ensure_ascii=False)
                save_prediction(_pp)
            except Exception:
                pass
        # บล็อกวิเคราะห์เต็มอยู่ใน Bid Board (ดูได้หลังกดติดตามงานนี้ — ลิงก์อยู่หน้า /follow ไม่ใช่ในข้อความนี้)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts && python test_format_notification_record_prediction.py`
Expected: `ALL PASS format_notification record_prediction flag`

- [ ] **Step 5: Run the existing intel test to confirm no regression**

Run: `cd scripts && python test_cgd_intel.py`
Expected: `ALL PASS (moi location disambiguation)` (or whatever its final print is) — no new failures, `test_wiring_format_notification` still passes unmodified.

- [ ] **Step 6: Commit**

```bash
cd /c/Bid-Master-System
git add scripts/Sebastian_LINE_Sender.py scripts/test_format_notification_record_prediction.py
git commit -m "feat(notify): format_notification รับ record_prediction flag (กัน closed-loop เขียนซ้ำตอน reconstruct ประวัติ)"
```

---

### Task 2: Backend endpoint `GET /api/portal/sebastian-feed`

**Files:**
- Modify: `scripts/bms_api.py` (add new endpoint after `portal_all_jobs_json`, i.e. after line 1980)
- Test: `scripts/test_portal_sebastian_feed_api.py`

**Interfaces:**
- Consumes: `format_notification(project_id, province, announce_type, budget, project_name, dept_name, bid_submit_date, bid_submit_time, is_backfill, source_stage, record_prediction) -> str` and `_clean_project_name(name) -> str` and `_plain_text_body(text, full_name) -> str` from `Sebastian_LINE_Sender` (Task 1); `_alljobs_stage(source_stage) -> str` and `get_conn()` and `portal_views.starred_project_ids(conn, cid)` already in `bms_api.py`.
- Produces: `GET /api/portal/sebastian-feed?line_user_id&limit` → `{"ok": true, "count": int, "messages": [{"project_id": str, "message": str, "sent_at": str, "stage": str, "starred": bool}]}`, oldest message first. Task 3 (frontend) consumes this exact shape.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_portal_sebastian_feed_api.py`:

```python
"""test_portal_sebastian_feed_api.py — GET /api/portal/sebastian-feed (แท็บ Sebastian, ประวัติ
แจ้งเตือนสไตล์แชท): dedup ต่อ project เอารอบล่าสุด (เกณฑ์เดียวกับ all-jobs), เรียงเก่า→ใหม่,
message เนื้อหาตรงกับ format_notification() จริงเป๊ะ, ไม่เขียน price_predictions ซ้ำ."""
import os, sys, json, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


def seed():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                     "VALUES ('U1','ทดสอบ','trial','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, "
                     "project_name, dept_name, first_seen_at) VALUES "
                     "('P1', 'D0', 'นครพนม', 5000000, 'ถนน คสล. สายหนึ่ง', 'อบต.ทดสอบ', '2026-07-01')")
        conn.execute("INSERT INTO project_locations (project_id, deadline, deadline_time, created_at) "
                     "VALUES ('P1', '2026-08-03', '09.00-12.00 น.', '2026-07-01')")
        q = ("INSERT INTO notification_queue (customer_id, project_id, status, created_at, "
             "province_snapshot, project_name_snapshot, dept_name_snapshot, source_stage, is_test_data) "
             "VALUES (?,?,?,?,?,?,?,?,?)")
        # P1 ส่ง 2 รอบ: D0 ก่อน แล้วค่อยประกาศผล → ต้องเหลือ 1 ข้อความ stage=won, ใช้ snapshot ล่าสุด
        conn.execute(q, (1, 'P1', 'sent', '2026-07-01T08:00:00', 'นครพนม', 'ถนน คสล. สายหนึ่ง', 'อบต.ทดสอบ', 'province_qualified', 0))
        conn.execute(q, (1, 'P1', 'sent', '2026-07-05T08:00:00', 'นครพนม', 'ถนน คสล. สายหนึ่ง', 'อบต.ทดสอบ', 'followed_winner', 0))
        # P2: snapshot ล้วน (ไม่มีใน projects_seen/project_locations)
        conn.execute(q, (1, 'P2', 'sent', '2026-07-06T08:00:00', 'บึงกาฬ', 'อาคารเรียนสองชั้น', 'สพฐ.ทดสอบ', 'province_tor_review', 0))
        # P3: LINE ส่งไม่สำเร็จ (quota เต็ม) → ยังต้องขึ้น (ไม่ผูกผลส่ง LINE)
        conn.execute(q, (1, 'P3', 'failed', '2026-07-06T09:00:00', 'นครพนม', 'งานที่ส่งพลาด', '', 'province_qualified', 0))
        # P4: test data → ไม่ขึ้น
        conn.execute(q, (1, 'P4', 'sent', '2026-07-06T10:00:00', 'นครพนม', 'งานทดสอบระบบ', '', 'province_qualified', 1))
        # P5: queue status='cancelled' → ไม่ขึ้น
        conn.execute(q, (1, 'P5', 'cancelled', '2026-07-06T09:15:00', 'นครพนม', 'แถวคิวถูกยกเลิก', '', 'province_qualified', 0))
        # ดาว P1
        conn.execute("INSERT INTO job_stars (customer_id, project_id, created_at) VALUES (1,'P1','2026-07-05')")


async def main():
    seed()
    # 403 secret ผิด
    try:
        await bms_api.portal_sebastian_feed_json(line_user_id='U1', x_bms_secret='bad')
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403

    r = await bms_api.portal_sebastian_feed_json(line_user_id='U1', x_bms_secret='t')
    assert r["ok"] and r["count"] == 3, r  # P1(dedup), P2, P3(failed ก็ขึ้น) — ไม่มี P4(test)/P5(cancelled)
    msgs = r["messages"]
    # เรียงเก่า→ใหม่ (แชท): P1(07-01 dedup ใช้ created_at ล่าสุด 07-05) ไม่ใช่ — ลำดับตาม created_at ที่ใช้แสดง
    assert [m["project_id"] for m in msgs] == ['P1', 'P2', 'P3'], msgs  # เก่า→ใหม่ ตาม sent_at ล่าสุดของแต่ละ project
    byid = {m["project_id"]: m for m in msgs}
    assert byid['P1']["stage"] == 'won' and byid['P1']["sent_at"] == '2026-07-05T08:00:00', byid['P1']
    assert byid['P1']["starred"] is True and byid['P2']["starred"] is False, byid

    # message เนื้อหาตรงกับ format_notification() จริงเป๊ะ (byte ต่อ byte) — กัน message drift
    from Sebastian_LINE_Sender import format_notification, _clean_project_name, _plain_text_body
    expected_text = format_notification(
        project_id='P1', province='นครพนม', announce_type='D0', budget=5000000,
        project_name='ถนน คสล. สายหนึ่ง', dept_name='อบต.ทดสอบ',
        bid_submit_date='2026-08-03', bid_submit_time='09.00-12.00 น.',
        source_stage='followed_winner', record_prediction=False,
    )
    expected_full_name = _clean_project_name('ถนน คสล. สายหนึ่ง')
    expected_message = _plain_text_body(expected_text, expected_full_name)
    assert byid['P1']["message"] == expected_message, (byid['P1']["message"], expected_message)
    assert '⏰ ยื่นซอง 3 ส.ค.' in byid['P1']["message"], byid['P1']["message"]

    # P2 ไม่มี projects_seen/project_locations → graceful (budget=0 "ไม่ระบุ", ไม่มี deadline)
    assert 'ไม่ระบุ' in byid['P2']["message"] or '💰' in byid['P2']["message"], byid['P2']["message"]
    assert '⏰' not in byid['P2']["message"], byid['P2']["message"]

    json.dumps(r, ensure_ascii=False)

    # record_prediction=False จริง — ต้องไม่มี row ใน price_predictions หลังเรียก endpoint
    with bms_api.get_conn() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM price_predictions").fetchone()[0]
    assert cnt == 0, cnt

    # ลูกค้าไม่มี → ก้อนว่าง ไม่ crash
    r = await bms_api.portal_sebastian_feed_json(line_user_id='U9', x_bms_secret='t')
    assert r == {"ok": True, "count": 0, "messages": []}, r

    print("PASS test_portal_sebastian_feed_api")


asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts && python test_portal_sebastian_feed_api.py`
Expected: FAIL with `AttributeError: module 'bms_api' has no attribute 'portal_sebastian_feed_json'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/bms_api.py`, add this new endpoint immediately after `portal_all_jobs_json` (after the line `return {"ok": True, "count": len(jobs), "jobs": jobs[:limit]}`, before `@app.post("/api/portal/push-subscribe")`):

```python
@app.get("/api/portal/sebastian-feed")
async def portal_sebastian_feed_json(
    line_user_id: str = Query(...),
    limit: int = 500,
    x_bms_secret=Header(default=None),
):
    """ประวัติแจ้งเตือนสไตล์แชท (แท็บ 'Sebastian') — ข้อความเหมือน LINE จริงทุกบรรทัด
    (reuse format_notification ตรงๆ — single source of truth, ไม่เขียน logic ซ้ำฝั่งเว็บ).
    dedup ต่อ project เอารอบล่าสุด (เกณฑ์เดียวกับ all-jobs, ไม่ผูกผลส่ง LINE) แต่เรียง
    เก่า→ใหม่ (แชทจริง ตรงข้ามกับ all-jobs ที่ใหม่→เก่า). ไม่ยิง live PDF/API enrichment
    เพิ่ม — อ่านแคช projects_seen/project_locations ที่มีอยู่แล้วเท่านั้น.
    record_prediction=False กัน closed-loop เขียนซ้ำทุกครั้งที่ลูกค้าเปิดหน้านี้. read-only."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    limit = max(1, min(int(limit or 500), 500))
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?",
                            (line_user_id.strip(),)).fetchone()
        if not cust:
            return {"ok": True, "count": 0, "messages": []}
        cid = cust["id"]
        rows = conn.execute(
            "SELECT nq.project_id, nq.project_name_snapshot, nq.province_snapshot, "
            "       nq.dept_name_snapshot, nq.source_stage, nq.created_at, nq.is_backfill, "
            "       ps.project_name, ps.province, ps.budget, ps.dept_name, ps.announce_type, "
            "       pl.deadline, pl.deadline_time "
            "FROM notification_queue nq "
            "LEFT JOIN projects_seen ps ON ps.project_id = nq.project_id "
            "LEFT JOIN project_locations pl ON pl.project_id = nq.project_id "
            "WHERE nq.customer_id=? AND nq.status!='cancelled' AND COALESCE(nq.is_test_data,0)=0 "
            "ORDER BY nq.created_at DESC", (cid,)).fetchall()
        starred_ids = portal_views.starred_project_ids(conn, cid)

    from Sebastian_LINE_Sender import format_notification, _clean_project_name, _plain_text_body

    messages, seen = [], set()
    for r in rows:  # DESC — แถวแรกของแต่ละ project = รอบส่งล่าสุด (dedup, เหมือน all-jobs)
        pid = r["project_id"]
        if pid in seen:
            continue
        seen.add(pid)
        name = r["project_name_snapshot"] or r["project_name"] or pid
        try:
            text = format_notification(
                project_id=pid,
                province=r["province_snapshot"] or r["province"] or "",
                announce_type=r["announce_type"] or "D0",
                budget=r["budget"] or 0,
                project_name=name,
                dept_name=r["dept_name_snapshot"] or r["dept_name"] or "",
                bid_submit_date=(r["deadline"] or "")[:10],
                bid_submit_time=r["deadline_time"] or "",
                is_backfill=bool(r["is_backfill"]),
                source_stage=r["source_stage"] or "",
                record_prediction=False,
            )
            full_name = _clean_project_name(name) or pid
            message = _plain_text_body(text, full_name)
        except Exception:
            message = name  # กัน endpoint พังถ้า format_notification ล้มสำหรับแถวใดแถวหนึ่ง
        messages.append({
            "project_id": pid,
            "message": message,
            "sent_at": r["created_at"],
            "stage": _alljobs_stage(r["source_stage"]),
            "starred": pid in starred_ids,
        })
    total = len(messages)
    messages = messages[:limit]
    messages.reverse()  # เก่า→ใหม่ (แชท) — dedup scan ด้านบนเป็น DESC
    return {"ok": True, "count": total, "messages": messages}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts && python test_portal_sebastian_feed_api.py`
Expected: `PASS test_portal_sebastian_feed_api`

- [ ] **Step 5: Run the existing all-jobs test to confirm no regression**

Run: `cd scripts && python test_portal_all_jobs_api.py`
Expected: unchanged pass output (this task didn't touch `portal_all_jobs_json` or `_alljobs_stage`)

- [ ] **Step 6: Commit**

```bash
cd /c/Bid-Master-System
git add scripts/bms_api.py scripts/test_portal_sebastian_feed_api.py
git commit -m "feat(portal): endpoint /api/portal/sebastian-feed (ประวัติแจ้งเตือนสไตล์แชท)"
```

---

### Task 3: Frontend data lib — `portal-sebastian-feed.ts`

**Files:**
- Create: `dashboard/web/src/lib/portal-sebastian-feed.ts`

**Interfaces:**
- Consumes: `SentJobStage` type from `dashboard/web/src/lib/portal-all-jobs.ts` (already defined: `"bidding" | "prelim" | "won" | "pre" | "cancelled"`); backend response shape from Task 2.
- Produces: `SebastianMessage`, `SebastianFeed` types + `getSebastianFeed(lineUserId, limit?) -> Promise<SebastianFeed>`. Task 5 (page.tsx) consumes this function.

- [ ] **Step 1: Create the file**

```typescript
/**
 * portal-sebastian-feed.ts — ประวัติแจ้งเตือนสไตล์แชท (แท็บ Sebastian)
 * อ่านจาก engine /api/portal/sebastian-feed (notification_queue + format_notification, เก่า→ใหม่)
 */
import type { SentJobStage } from "./portal-all-jobs";

const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export interface SebastianMessage {
  project_id: string;
  message: string; // ข้อความเต็มหลายบรรทัด เหมือน LINE จริง
  sent_at: string; // ISO
  stage: SentJobStage;
  starred: boolean;
}

export interface SebastianFeed {
  count: number;
  messages: SebastianMessage[];
}

export async function getSebastianFeed(lineUserId: string, limit = 500): Promise<SebastianFeed> {
  if (!lineUserId) return { count: 0, messages: [] };
  const url = `${BMS_API_URL}/api/portal/sebastian-feed?line_user_id=${encodeURIComponent(lineUserId)}&limit=${limit}`;
  const res = await fetch(url, { headers: { "X-BMS-Secret": BMS_SECRET }, cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET sebastian-feed failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; count?: number; messages?: SebastianMessage[] };
  return { count: data.count ?? 0, messages: data.messages ?? [] };
}
```

- [ ] **Step 2: Type-check**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: no errors mentioning `portal-sebastian-feed.ts`

- [ ] **Step 3: Commit**

```bash
cd /c/Bid-Master-System
git add dashboard/web/src/lib/portal-sebastian-feed.ts
git commit -m "feat(portal): types + fetch wrapper สำหรับ sebastian-feed"
```

---

### Task 4: Extract shared day-grouping helper

**Files:**
- Create: `dashboard/web/src/lib/portal-day-groups.ts`
- Modify: `dashboard/web/src/app/portal/jobs/_client.tsx:32-49` (remove local definitions, import from new lib), and lines 227-228 (use new helper functions)

**Interfaces:**
- Produces: `BKK_TZ`, `dayKey(s: string) -> string`, `dayLabel(key, todayKey, yesterdayKey) -> string`, `getTodayKey() -> string`, `getYesterdayKey() -> string`. Task 5's `_client.tsx` consumes these too (this is *why* the extraction is worth doing now — used by 2 pages).

- [ ] **Step 1: Create the shared lib**

```typescript
/**
 * portal-day-groups.ts — จัดกลุ่มรายการตามวัน (เวลาไทย) ใช้ร่วมกันระหว่าง
 * /portal/jobs (card list) และ /portal/sebastian (chat feed)
 */
export const BKK_TZ = 'Asia/Bangkok';

export function dayKey(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return 'unknown';
  return d.toLocaleDateString('en-CA', { timeZone: BKK_TZ });
}

export function dayLabel(key: string, todayKey: string, yesterdayKey: string): string {
  if (key === 'unknown') return 'ไม่ระบุวัน';
  const thai = new Date(`${key}T00:00:00+07:00`).toLocaleDateString('th-TH', {
    day: 'numeric', month: 'short', year: '2-digit', timeZone: BKK_TZ,
  });
  if (key === todayKey) return `วันนี้ · ${thai}`;
  if (key === yesterdayKey) return `เมื่อวาน · ${thai}`;
  return thai;
}

export function getTodayKey(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: BKK_TZ });
}

export function getYesterdayKey(): string {
  return new Date(Date.now() - 86400000).toLocaleDateString('en-CA', { timeZone: BKK_TZ });
}
```

- [ ] **Step 2: Update `jobs/_client.tsx` to use it**

Remove these lines (currently lines 32-49):

```typescript
// จัดกลุ่มต่อวัน (เวลาไทย) — key = YYYY-MM-DD ใช้เทียบวันนี้/เมื่อวาน
const BKK_TZ = 'Asia/Bangkok';

function dayKey(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return 'unknown';
  return d.toLocaleDateString('en-CA', { timeZone: BKK_TZ });
}

function dayLabel(key: string, todayKey: string, yesterdayKey: string): string {
  if (key === 'unknown') return 'ไม่ระบุวัน';
  const thai = new Date(`${key}T00:00:00+07:00`).toLocaleDateString('th-TH', {
    day: 'numeric', month: 'short', year: '2-digit', timeZone: BKK_TZ,
  });
  if (key === todayKey) return `วันนี้ · ${thai}`;
  if (key === yesterdayKey) return `เมื่อวาน · ${thai}`;
  return thai;
}
```

Replace with:

```typescript
import { dayKey, dayLabel, getTodayKey, getYesterdayKey } from '@/lib/portal-day-groups';
```

(add this import near the top of the file, alongside the other imports at the top — e.g. right after `import type { AllJobs, SentJob, SentJobStage } from '@/lib/portal-all-jobs';`)

Then find these two lines inside the render function (currently around line 227-228):

```typescript
              const todayKey = new Date().toLocaleDateString('en-CA', { timeZone: BKK_TZ });
              const yesterdayKey = new Date(Date.now() - 86400000).toLocaleDateString('en-CA', { timeZone: BKK_TZ });
```

Replace with:

```typescript
              const todayKey = getTodayKey();
              const yesterdayKey = getYesterdayKey();
```

- [ ] **Step 3: Type-check**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Visual regression check (manual)**

Run: `cd dashboard/web && npm run build` — if it builds cleanly, the extraction didn't break the existing `/portal/jobs` page. (Full manual click-through happens in Task 7.)

- [ ] **Step 5: Commit**

```bash
cd /c/Bid-Master-System
git add dashboard/web/src/lib/portal-day-groups.ts dashboard/web/src/app/portal/jobs/_client.tsx
git commit -m "refactor(portal): แยก day-grouping helper ไปใช้ร่วมกัน (jobs + sebastian)"
```

---

### Task 5: Sebastian chat page (`page.tsx` + `_client.tsx` + CSS)

**Files:**
- Create: `dashboard/web/src/app/portal/sebastian/page.tsx`
- Create: `dashboard/web/src/app/portal/sebastian/_client.tsx`
- Modify: `dashboard/web/src/app/portal/portal.css` (append `.p-chat-bubble` rules)

**Interfaces:**
- Consumes: `getSebastianFeed` (Task 3), `dayKey`/`dayLabel`/`getTodayKey`/`getYesterdayKey` (Task 4), `TopBar`/`Icons` from `../_ui`, `parseSessionCookie`/`COOKIE_NAME` from `@/lib/session`.
- Produces: the `/portal/sebastian` route. Task 6 (nav) links to this route.

- [ ] **Step 1: Create `page.tsx`**

```typescript
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getSebastianFeed, type SebastianFeed } from '@/lib/portal-sebastian-feed';
import { SebastianClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function SebastianPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let data: SebastianFeed | null = null;
  let engineDown = false;
  try {
    data = await getSebastianFeed(session.lineUserId);
  } catch {
    engineDown = true; // engine ล่ม — แสดงการ์ดแจ้ง ไม่ crash
  }

  return <SebastianClient data={data} engineDown={engineDown} />;
}
```

- [ ] **Step 2: Create `_client.tsx`**

```typescript
'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { TopBar, Icons } from '../_ui';
import type { SebastianFeed, SebastianMessage } from '@/lib/portal-sebastian-feed';
import { dayKey, dayLabel, getTodayKey, getYesterdayKey } from '@/lib/portal-day-groups';

function fmtTime(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok' });
}

function MessageBubble({ msg }: { msg: SebastianMessage }) {
  return (
    <Link href={`/portal/job/${encodeURIComponent(msg.project_id)}`} style={{ textDecoration: 'none', color: 'inherit' }}>
      <div className="p-chat-bubble">
        {msg.starred && (
          <div style={{ color: 'var(--accent)', fontSize: 12, marginBottom: 4 }}>★ ติดดาวไว้</div>
        )}
        <div style={{ fontSize: 13.5, lineHeight: 1.55, whiteSpace: 'pre-line' }}>{msg.message}</div>
        <div className="p-fg-dim" style={{ fontSize: 10.5, marginTop: 6 }}>{fmtTime(msg.sent_at)}</div>
      </div>
    </Link>
  );
}

export function SebastianClient({ data, engineDown }: { data: SebastianFeed | null; engineDown: boolean }) {
  const dayGroups = useMemo(() => {
    const m = new Map<string, SebastianMessage[]>();
    for (const msg of data?.messages ?? []) {
      const k = dayKey(msg.sent_at);
      const arr = m.get(k);
      if (arr) arr.push(msg); else m.set(k, [msg]);
    }
    return [...m.entries()];
  }, [data]);

  if (!data) {
    return (
      <div className="p-enter">
        <TopBar title="Sebastian" subtitle="ประวัติการแจ้งเตือน" />
        <div className="p-page p-page-topbar">
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              {engineDown ? 'ดึงข้อมูลไม่ได้ชั่วคราว — ลองใหม่อีกครั้งครับ' : 'ยังไม่มีข้อมูล'}
            </div>
            <Link href="/portal/world">
              <button className="p-btn p-btn-ghost" style={{ marginTop: 14, height: 36, padding: '0 16px', fontSize: 13 }}>
                กลับหน้าหลัก
              </button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-enter">
      <TopBar title="Sebastian" subtitle="ประวัติการแจ้งเตือน" right={<Icons.Bot size={20} />} />
      <div className="p-page p-page-topbar">
        {data.messages.length === 0 ? (
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              ยังไม่มีการแจ้งเตือน — เมื่อ Sebastian พบงานที่ตรงกับท่าน จะทักมาที่นี่ครับ
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(() => {
              const todayKey = getTodayKey();
              const yesterdayKey = getYesterdayKey();
              return dayGroups.map(([key, dayMsgs]) => (
                <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ marginTop: 8, textAlign: 'center' }}>
                    <span className="p-fg-dim" style={{ fontSize: 11.5 }}>{dayLabel(key, todayKey, yesterdayKey)}</span>
                  </div>
                  {dayMsgs.map(msg => <MessageBubble key={msg.project_id} msg={msg} />)}
                </div>
              ));
            })()}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add chat bubble CSS**

Append to `dashboard/web/src/app/portal/portal.css` (after the `.p-card` rule block, around line 145):

```css
/* ── Sebastian chat bubble ── */
[data-portal] .p-chat-bubble {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px 14px 14px 14px;
  padding: 12px 14px;
  max-width: 92%;
  cursor: pointer;
  transition: border-color 0.15s;
}
[data-portal] .p-chat-bubble:hover {
  border-color: var(--accent-deep);
}
```

- [ ] **Step 4: Type-check + build**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: no errors

Run: `cd dashboard/web && npm run build`
Expected: build succeeds, `/portal/sebastian` appears in the route list output

- [ ] **Step 5: Commit**

```bash
cd /c/Bid-Master-System
git add dashboard/web/src/app/portal/sebastian dashboard/web/src/app/portal/portal.css
git commit -m "feat(portal): หน้า /portal/sebastian — ประวัติแจ้งเตือนสไตล์แชท"
```

---

### Task 6: Nav bar entry

**Files:**
- Modify: `dashboard/web/src/app/portal/_shell.tsx`

**Interfaces:**
- Consumes: nothing new
- Produces: bottom-nav link to `/portal/sebastian`, visible on every portal page (this is the last task — after this, the feature is reachable end-to-end)

- [ ] **Step 1: Add `BotIcon` function**

In `dashboard/web/src/app/portal/_shell.tsx`, add this function after `GearIcon` (after line 62, before the `// ── Nav items ──` comment... actually the comment is *above* `GearIcon` — add `BotIcon` right after the `GearIcon` function closes, before the `NAV_ITEMS` constant):

```typescript
function BotIcon({ size = 20, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      <line x1="12" y1="3" x2="12" y2="7" />
      <circle cx="9" cy="16" r="1" fill="currentColor" />
      <circle cx="15" cy="16" r="1" fill="currentColor" />
    </svg>
  );
}
```

- [ ] **Step 2: Add the nav entry**

Change `NAV_ITEMS` from:

```typescript
const NAV_ITEMS = [
  { href: '/portal/world',     label: 'หน้าหลัก', Icon: HomeIcon },
  { href: '/portal/settings',  label: 'ตั้งค่า',   Icon: GearIcon },
  { href: '/portal/history',   label: 'ประวัติ',   Icon: ClockIcon },
  { href: '/portal/profile',   label: 'โปรไฟล์',  Icon: UserIcon },
  { href: '/portal/packages',  label: 'แพ็กเกจ',  Icon: CrownIcon },
];
```

to:

```typescript
const NAV_ITEMS = [
  { href: '/portal/world',     label: 'หน้าหลัก', Icon: HomeIcon },
  { href: '/portal/settings',  label: 'ตั้งค่า',   Icon: GearIcon },
  { href: '/portal/sebastian', label: 'Sebastian', Icon: BotIcon },
  { href: '/portal/history',   label: 'ประวัติ',   Icon: ClockIcon },
  { href: '/portal/profile',   label: 'โปรไฟล์',  Icon: UserIcon },
  { href: '/portal/packages',  label: 'แพ็กเกจ',  Icon: CrownIcon },
];
```

- [ ] **Step 3: Type-check + build**

Run: `cd dashboard/web && npx tsc --noEmit && npm run build`
Expected: both succeed

- [ ] **Step 4: Commit**

```bash
cd /c/Bid-Master-System
git add dashboard/web/src/app/portal/_shell.tsx
git commit -m "feat(portal): เพิ่มแท็บ Sebastian ในแถบเมนูล่าง"
```

---

### Task 7: Full verification + deploy

**Files:** none (verification + deploy only)

- [ ] **Step 1: Run the full backend test suite**

```bash
cd /c/Bid-Master-System/scripts
export BMS_ENV=dev
python test_format_notification_record_prediction.py
python test_portal_sebastian_feed_api.py
python test_portal_all_jobs_api.py
python test_cgd_intel.py
python test_webpush_mirror.py
```

Expected: every file prints its `PASS`/`ALL PASS` line, no tracebacks.

- [ ] **Step 2: Run the full frontend build**

```bash
cd /c/Bid-Master-System/dashboard/web
npx tsc --noEmit
npm run build
```

Expected: both exit 0. Confirm `/portal/sebastian` is listed in the build's route output.

- [ ] **Step 3: Manual smoke test (local dev server)**

```bash
cd /c/Bid-Master-System/dashboard/web
npm run dev
```

Open `http://localhost:3000/portal/sebastian` (after logging in via the normal portal login flow) and verify:
- Bottom nav shows "Sebastian" tab between "ตั้งค่า" and "ประวัติ"
- Chat bubbles render, grouped by day, oldest at top
- Clicking a bubble navigates to `/portal/job/<id>`
- Stop the dev server (Ctrl+C) when done.

- [ ] **Step 4: Dispatch Sophia for a sanity audit**

Before deploying, dispatch the `sophia` agent (per this project's `CLAUDE.md` protocol — any change touching `notification_queue`/pricing/`format_notification` must be reviewed before deploy) summarizing: the new `record_prediction` flag, the new endpoint, and confirmation that `price_predictions` is never written by the new read path. Get a SAFE verdict before proceeding to Step 5.

- [ ] **Step 5: Push and deploy backend**

```bash
cd /c/Bid-Master-System
git push origin main
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cd /opt/bms/app && sudo -u bms git pull --ff-only origin main"
```

Then **restart bms-api** (it's a persistent uvicorn process — unlike the oneshot scripts from N+208/209, code changes here need an explicit restart to take effect):

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "systemctl restart bms-api && sleep 2 && curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8000/health"
```

Expected: `health=200`

- [ ] **Step 6: Verify the new endpoint live on the VPS**

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "curl -s -H 'X-BMS-Secret: <read from /opt/bms/app/.env BMS_INTERNAL_SECRET>' 'http://127.0.0.1:8000/api/portal/sebastian-feed?line_user_id=Ua0d90e8491ca50ba39a053ca78dd2962&limit=5'"
```

Expected: valid JSON with `"ok": true` and a `messages` array (possibly empty if this exact customer's queue is empty after the `limit`/dedup rules — that's fine, just confirm it's not a 500 or connection error).

- [ ] **Step 7: Deploy frontend**

```bash
cd /c/Bid-Master-System/dashboard/web
vercel --prod
```

Expected: `readyState: READY`, aliased to `bid-master-dashboard.vercel.app`.

- [ ] **Step 8: Update progress_log.md and Discord**

Add a new `งานที่ N+XXX` entry to `progress_log.md` describing what shipped (endpoint, page, nav entry, the `record_prediction` fix and why it mattered), following this project's existing entry format. Send a Discord notification via `scripts/Sebastian_Discord_Notify.py` summarizing the same, per this project's `CLAUDE.md` notification protocol. Commit the `progress_log.md` update and push.
