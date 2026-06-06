# ⭐ Follow/Star Lifecycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** แทน feedback 👍/🤔/👎 ด้วย ⭐ติดตามงาน — แจ้งเมื่องานที่ติดตามเปิดประมูล (B0→D0) + ประกาศผู้ชนะ (→W0) พร้อมราคาคู่แข่งทุกราย + เก็บ competitive-intel DB

**Architecture:** followed_jobs (watchlist) + bid_results (intel). Phase 1 = ⭐/❌ buttons + watchlist + B0→D0 notify (reuse discovery/enrichment). Phase 2 = winner poller (getProcureResult via AES-token) + bid_results + winner notify. Reuse `fetch_bid_history.fetch_procure_result` (แตก bidders+priceProposal).

**Tech Stack:** Python 3 (stdlib), SQLite, FastAPI (bms_api webhook), systemd timer, LINE Messaging API (flex/postback).

**Spec:** `docs/superpowers/specs/2026-06-06-follow-star-lifecycle-design.md`

**Test convention (โปรเจกต์นี้):** ไฟล์ `scripts/test_*.py` รันตรง `python scripts/test_<x>.py` (ไม่ใช้ pytest), assert + print ✅/❌ + sys.exit(1) เมื่อ fail. dev ใช้ `BMS_ENV=dev` (bms_paths fail-loud).

---

## File Structure
- `scripts/Sebastian_Customer_DB.py` — + migrate v115 (followed_jobs) + v116 (bid_results) + helpers
- `scripts/Sebastian_LINE_Sender.py` — เปลี่ยน FB_ACTIONS→star buttons, build_postback_data, format winner
- `scripts/bms_api.py` — postback handler `star:` / คง `fb:irrelevant`
- `scripts/Sebastian_Enrichment_Worker.py` — hook B0→D0 transition notify (ใน D0 path เดิม)
- `scripts/Sebastian_Winner_Poller.py` — **ใหม่** poll getProcureResult → bid_results + notify (Phase 2)
- `scripts/_probe_procure_token.py` — **ใหม่** probe getProcureResult via AES-token (Phase 2 gate)
- `deploy/systemd/bms-winner-poller.{service,timer}` — **ใหม่**
- tests: `test_followed_jobs.py`, `test_star_buttons.py`, `test_bid_results.py`, `test_winner_format.py`

---

# PHASE 1 — ⭐/❌ buttons + watchlist + B0→D0 notify (เบา, ส่งคุณค่าเร็ว)

## Task 1.1: followed_jobs table + helpers

**Files:** Modify `scripts/Sebastian_Customer_DB.py` · Test `scripts/test_followed_jobs.py`

- [ ] **Step 1: Write failing test**
```python
"""test_followed_jobs.py — watchlist upsert + stage dedup."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
s = db.SubscriptionStore()
# add follow
s.add_follow(customer_id=2, project_id="P1", starred_stage="B0", now="2026-06-06T10:00:00")
act = s.get_active_follows()
assert any(f["project_id"]=="P1" and f["customer_id"]==2 for f in act), act
assert [f for f in act if f["project_id"]=="P1"][0]["last_stage_notified"]=="B0"
# upsert idempotent (กดซ้ำ)
s.add_follow(2, "P1", "B0", "2026-06-06T11:00:00")
assert len([f for f in s.get_active_follows() if f["project_id"]=="P1" and f["customer_id"]==2])==1
# mark stage notified
s.mark_stage_notified(2, "P1", "D0")
assert [f for f in s.get_active_follows() if f["project_id"]=="P1"][0]["last_stage_notified"]=="D0"
# close → ไม่อยู่ active
s.close_follow("P1", 2)
assert not any(f["project_id"]=="P1" and f["customer_id"]==2 for f in s.get_active_follows())
print("✅ PASS followed_jobs")
```

- [ ] **Step 2: Run → FAIL** — `BMS_ENV=dev python scripts/test_followed_jobs.py` → AttributeError (no add_follow)

- [ ] **Step 3: เพิ่ม migrate v115 + helpers**

ใน `init_schema()` หลัง `_migrate_v114()` เพิ่ม `_migrate_v115()`. เพิ่มฟังก์ชัน:
```python
def _migrate_v115():
    """followed_jobs — ⭐ watchlist (ติดตามงานข้าม stage)."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS followed_jobs (
                customer_id INTEGER NOT NULL,
                project_id  TEXT NOT NULL,
                starred_at  TEXT NOT NULL,
                starred_stage TEXT,
                last_stage_notified TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                PRIMARY KEY (customer_id, project_id)
            )""")
```
ใน `SubscriptionStore` เพิ่ม methods:
```python
def add_follow(self, customer_id, project_id, starred_stage, now=None):
    now = now or _now()
    with get_connection() as conn:
        conn.execute("""INSERT INTO followed_jobs
            (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status)
            VALUES (?,?,?,?,?,'active')
            ON CONFLICT(customer_id,project_id) DO UPDATE SET status='active'""",
            (customer_id, project_id, now, starred_stage, starred_stage))

def get_active_follows(self):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM followed_jobs WHERE status='active'")]

def mark_stage_notified(self, customer_id, project_id, stage):
    with get_connection() as conn:
        conn.execute("UPDATE followed_jobs SET last_stage_notified=? WHERE customer_id=? AND project_id=?",
                     (stage, customer_id, project_id))

def close_follow(self, project_id, customer_id):
    with get_connection() as conn:
        conn.execute("UPDATE followed_jobs SET status='closed' WHERE customer_id=? AND project_id=?",
                     (customer_id, project_id))
```
(เพิ่ม `_migrate_v115()` ใน init_schema chain)

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git commit -m "feat(follow): followed_jobs watchlist + helpers (Phase 1 Task 1.1)"`

## Task 1.2: ⭐/❌ buttons (LINE)

**Files:** Modify `scripts/Sebastian_LINE_Sender.py:48-99` · Test `scripts/test_star_buttons.py`

- [ ] **Step 1: Write failing test**
```python
"""test_star_buttons.py — postback data star/irrelevant."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_LINE_Sender import build_postback_data, build_job_flex
assert build_postback_data("star","P9")=="star:P9", build_postback_data("star","P9")
flex = build_job_flex("P9","งานถนน","รายละเอียด", with_feedback=True)
labels = [b["action"]["label"] for b in flex["footer"]["contents"]]
assert any("ติดตาม" in l for l in labels) and any("ไม่เกี่ยว" in l for l in labels), labels
assert not any("น่าสน" in l for l in labels), "เอา 🤔 ออกแล้ว"
print("✅ PASS star buttons")
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: เปลี่ยน buttons** ใน `Sebastian_LINE_Sender.py` (แทน FB_ACTIONS + build_postback_data):
```python
FB_ACTIONS = {
    "star":       "⭐ ติดตามงานนี้",
    "irrelevant": "❌ ไม่เกี่ยว",
}
def build_postback_data(action: str, project_id: str) -> str:
    # star → prefix star:<pid> (handler ใหม่) · อื่นๆ → fb:<action>:<pid> (handler เดิม)
    return f"star:{project_id}" if action == "star" else f"fb:{action}:{project_id}"
```
build_job_flex footer loop เดิม iterate FB_ACTIONS อยู่แล้ว → ได้ 2 ปุ่ม (⭐/❌) อัตโนมัติ.
**ปรับ parse_postback_data:** เดิม validate `action not in FB_ACTIONS` — เพิ่มรองรับ data ขึ้นต้น `star:` ด้วย (หรือ handler ฝั่ง bms_api parse เอง — ดู Task 1.3 ซึ่ง parse `star:` ตรงๆ ไม่ผ่าน parse_postback_data). ใน LINE_Sender แค่ buttons พอ.

- [ ] **Step 4: Run → PASS** · **Step 5: Commit**

## Task 1.3: postback handler `star:`

**Files:** Modify `scripts/bms_api.py:537-564`

- [ ] **Step 1: เพิ่ม handler ก่อน block `fb:`** (ใน postback elif):
```python
            # ⭐ ติดตามงาน: star:<project_id>
            if data.startswith("star:"):
                project_id = data.split(":", 1)[1]
                if project_id:
                    cid = _customer_id(user_id)  # helper เดิมหา customer จาก line_user_id
                    ann = _project_announce_type(project_id)  # 'B0'/'D0' จาก projects_seen
                    if cid:
                        SubscriptionStore().add_follow(cid, project_id, ann, _now())
                    if reply_token:
                        await reply_raw(reply_token, [{"type":"text",
                          "text":"⭐ ติดตามงานนี้แล้ว — จะแจ้งเมื่อเปิดประมูล/ประกาศผู้ชนะ"}])
                continue
```
- [ ] **Step 2: เพิ่ม helper** `_project_announce_type(pid)` (อ่าน projects_seen.announce_type, default 'D0') + ยืนยัน `_customer_id`/`SubscriptionStore` import มีแล้ว
- [ ] **Step 3: smoke** `BMS_ENV=dev python -c "import sys;sys.path.insert(0,'scripts');import bms_api;print('ok')"`
- [ ] **Step 4: Commit**

> หมายเหตุ: `fb:irrelevant:` ใช้ handler เดิม (record_feedback_by_project) — ❌ ทำงานทันที ไม่ต้องแก้

## Task 1.4: B0→D0 transition notify

**Files:** Modify `scripts/Sebastian_Enrichment_Worker.py` (ใน D0 path, หลัง enqueue ปกติ) · Test `scripts/test_followed_jobs.py` (เพิ่มเคส)

- [ ] **Step 1: Write failing test** (helper บริสุทธิ์ `tor_to_bid_followers`)
```python
# เพิ่มใน test_followed_jobs.py: followers ที่ติดดาวตอน B0 + ยังไม่แจ้ง D0
s.add_follow(3, "P2", "B0", "2026-06-06T09:00:00")
import job_followups as jf  # helper module ใหม่
due = jf.followers_due_for_stage(s, "P2", "D0")   # คืน [customer_id] ที่ last=B0
assert due == [3], due
s.mark_stage_notified(3, "P2", "D0")
assert jf.followers_due_for_stage(s, "P2", "D0") == []
print("✅ PASS B0→D0 followers")
```
- [ ] **Step 2: Run → FAIL** (no job_followups)
- [ ] **Step 3: สร้าง `scripts/job_followups.py`**:
```python
"""job_followups.py — ตัดสินว่าใครต้องแจ้ง stage transition ของงานที่ติดตาม (pure-ish)."""
_STAGE_ORDER = {"B0": 0, "D0": 1, "W0": 2}
def followers_due_for_stage(store, project_id, new_stage):
    """customer_ids ที่ติดตาม project นี้ + ยังไม่แจ้งถึง new_stage (last < new)."""
    nv = _STAGE_ORDER.get(new_stage, 99)
    return [f["customer_id"] for f in store.get_active_follows()
            if f["project_id"] == project_id
            and _STAGE_ORDER.get(f["last_stage_notified"] or "", -1) < nv]
```
- [ ] **Step 4: wire ใน Enrichment_Worker D0 path** — หลัง enqueue D0 สำเร็จ (announce_type ขึ้น D, mode live) เพิ่ม:
```python
    import job_followups as jf
    for fcid in jf.followers_due_for_stage(store, pid, "D0"):
        store.enqueue_notifications({**base_payload, "source_stage":"followed_bid_open"}, min_confidence="high")
        store.mark_stage_notified(fcid, pid, "D0")
```
(base_payload = dict เดียวกับ enqueue D0 + announce_type='D0')
- [ ] **Step 5: LINE label** `Sebastian_LINE_Sender.format_notification`: เพิ่ม `source_stage=="followed_bid_open"` → header "⭐ งานที่ติดตาม — เปิดประมูลแล้ว!"
- [ ] **Step 6: Run test + compile + Commit**

**✅ EXIT Phase 1:** ⭐/❌ ทำงาน · ติดดาวเก็บ followed_jobs · B0→D0 แจ้ง "เปิดประมูล" · test เขียว · deploy (git pull) + เปลี่ยน buttons live

---

# PHASE 2 — winner poller + competitive intel

## Task 2.0: PROBE getProcureResult via AES-token (GATE — verify ก่อนสร้าง poller)

**Files:** Create `scripts/_probe_procure_token.py`

- [ ] **Step 1:** ลองเรียก getProcureResult ด้วย AES-token (ไม่ผ่าน browser) กับงานที่ชนะแล้ว 1 งาน (จาก winner_history) → ดูว่าได้ bidders+priceProposal ไหม. reuse token mint จาก `probe_generate_token.py`/`process5_http_client.py` (AES key RDCrypto)
- [ ] **Step 2:** ถ้าได้ → Phase 2 ใช้ token path (เบา). ถ้าไม่ได้ → ต้องใช้ Playwright (หนักกว่า, รันบน VPS ที่มี browser) → **flag + ปรับ Task 2.2 ก่อนทำต่อ**
- [ ] **Step 3:** จดผลใน progress_log + commit probe

> ⚠️ ห้ามสร้าง Task 2.2 (poller) จนกว่า 2.0 ยืนยัน path ที่ใช้ได้บน VPS

## Task 2.1: bid_results table + record helper

**Files:** Modify `scripts/Sebastian_Customer_DB.py` (migrate v116) · Test `scripts/test_bid_results.py`

- [ ] **Step 1: Write failing test**
```python
"""test_bid_results.py — เก็บ bidders + idempotent."""
import os,tempfile,sys; from pathlib import Path
os.environ["BMS_DATA_DIR"]=tempfile.mkdtemp()
sys.path.insert(0,str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db; db.init_schema(); s=db.SubscriptionStore()
bidders=[{"bidder_name":"A","bidder_tin":"111","price_proposal":"100","price_agree":"95","is_winner":"TRUE"},
         {"bidder_name":"B","bidder_tin":"222","price_proposal":"110","price_agree":"","is_winner":"FALSE"}]
s.record_bid_results("P1", bidders, "2026-06-06")
got=s.get_bid_results("P1")
assert len(got)==2 and [g for g in got if g["is_winner"]][0]["bidder_name"]=="A", got
s.record_bid_results("P1", bidders, "2026-06-07")  # idempotent (UNIQUE project+tin)
assert len(s.get_bid_results("P1"))==2
print("✅ PASS bid_results")
```
- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: migrate v116 + helpers**
```python
def _migrate_v116():
    with get_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS bid_results (
            project_id TEXT NOT NULL, bidder_name TEXT, bidder_tin TEXT,
            price_proposal TEXT, price_agree TEXT, is_winner TEXT, is_sme TEXT,
            result_flag TEXT, fetched_at TEXT,
            PRIMARY KEY (project_id, bidder_tin))""")
```
+ `record_bid_results(self, project_id, bidders, fetched_at)` (INSERT OR REPLACE ต่อ bidder) + `get_bid_results(self, project_id)` (row→dict). เพิ่ม `_migrate_v116()` ใน chain.
- [ ] **Step 4: Run → PASS · Commit**

## Task 2.2: Winner_Poller

**Files:** Create `scripts/Sebastian_Winner_Poller.py` · reuse `fetch_bid_history.fetch_procure_result` (หรือ token path จาก 2.0)

- [ ] **Step 1:** poller logic: get_active_follows ที่ last_stage_notified in (B0,D0) + starred_at เก่าพอ (>0 วัน) → สำหรับแต่ละ project_id (unique): fetch result
  - มีผล (bidders + winner) → `record_bid_results` + สำหรับ follower แต่ละคน enqueue winner notify (source_stage='followed_winner') + mark_stage_notified('W0') + close_follow
  - ไม่มีผล + starred_at > BMS_WINNER_POLL_MAX_DAYS(60) → close_follow (give up)
  - rate-limit: cooldown ระหว่าง project (เหมือน discovery), abort on rate-limit
- [ ] **Step 2:** test stop-condition (mock fetch คืน no-result + starred 61 วัน → close) ใน `test_winner_poller.py`
- [ ] **Step 3: Commit**

## Task 2.3: winner notification format

**Files:** Modify `scripts/Sebastian_LINE_Sender.py` · Test `scripts/test_winner_format.py`

- [ ] **Step 1: Write failing test**
```python
from Sebastian_LINE_Sender import format_winner
msg = format_winner("งานถนน", winner="บ.A", price_agree="950000",
        competitors=[{"name":"บ.B","price":"1100000"},{"name":"บ.C","price":"1050000"}])
assert "ประกาศผู้ชนะ" in msg and "บ.A" in msg and "บ.B" in msg and "1,100,000" in msg
print("✅ PASS winner format")
```
- [ ] **Step 2-4:** implement `format_winner(...)` → "⭐ ประกาศผู้ชนะ: [winner] ฿[price] · คู่แข่ง: B ฿.., C ฿.." + commit

## Task 2.4: systemd timer

**Files:** Create `deploy/systemd/bms-winner-poller.{service,timer}` (OnCalendar ทุก 6 ชม.) + ติดตั้ง VPS (scp + enable, ต้อง root) + จด README

**✅ EXIT Phase 2:** probe ผ่าน · bid_results เก็บ · poller แจ้งผู้ชนะ+คู่แข่ง · competitive intel DB เริ่มสะสม

---

## Definition of Done
- [ ] ⭐/❌ แทน 👍🤔👎 บน LINE จริง
- [ ] ติดดาว → followed_jobs · B0→D0 แจ้ง "เปิดประมูล" · W0 แจ้ง "ผู้ชนะ+คู่แข่ง+ราคา"
- [ ] bid_results สะสม (competitive intel)
- [ ] dedup (last_stage_notified) ไม่แจ้งซ้ำ · poller stop ≤60 วัน
- [ ] test ทุก unit เขียว · deploy git-pull

## Rollback
Phase 1 = revert commit + git pull (buttons กลับ); followed_jobs ปล่อยว่างได้. Phase 2 = stop bms-winner-poller.timer + revert.
