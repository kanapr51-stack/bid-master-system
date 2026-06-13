# All-Bidders Backfill Engine (2A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** สร้าง `scripts/backfill_bidders.py` ดึง full-bidder list ของงานแข่งจริง (นครพนม+บึงกาฬ, competitive set, FY2567-2569) จาก `cgd_winners` → `getProcureResult` → เก็บลง `bid_results` เพื่อสะสม evidence ให้ predictor (2B)

**Architecture:** Writer ล้วน, รันบน VPS, sequential + politeness sleep (rate-limit retry มีใน `_get` แล้ว) + resumable ผ่าน `backfill_seen.json` + fail-open ต่องาน. `fetched_at = announce_date` ของงาน (ไม่ใช่ now) เพื่อ recency ถูกต้อง. reuse `record_bid_results` (1b) + `get_procure_result` เดิม. ไม่แตะ predictor read (เป็นของ 2B)

**Tech Stack:** Python, sqlite3, argparse, pytest-style assert scripts (รัน `BMS_ENV=dev PYTHONIOENCODING=utf-8 python <file>`)

**Spec:** `docs/superpowers/specs/2026-06-13-allbidders-backfill-2a-design.md`

---

## File Structure

- Create: `scripts/backfill_bidders.py` — selector + fetch/store + run loop + CLI (ไฟล์เดียว, ~120 บรรทัด, 1 ความรับผิดชอบ = backfill)
- Create: `scripts/test_backfill_bidders.py` — TDD tests (in-memory temp DB)
- Runtime: `data/backfill_seen.json` — checkpoint set (สร้างตอน run, gitignored ผ่าน data/)

**Error/status model:** `backfill_one` คืน status ∈ {`"stored"`, `"empty"`, `"error"`}:
- `get_procure_result(pid)` คืน `{}` (ไม่มี key `"bidders"`) หรือโยน exception → `"error"` (ไม่ mark seen → retry รอบหน้า)
- คืน `{"bidders": []}` → `"empty"` (mark seen, ไม่ write)
- คืน `{"bidders": [...]}` มีราย → `record_bid_results` + mark seen → `"stored"`

---

### Task 1: select_candidates — filter + dedup + skip-seen

**Files:**
- Create: `scripts/backfill_bidders.py`
- Create: `scripts/test_backfill_bidders.py`

- [ ] **Step 1: เขียน failing test** สร้าง `scripts/test_backfill_bidders.py`

```python
"""test_backfill_bidders.py — backfill engine: select / fetch-store / run loop."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import backfill_bidders as bb

def _seed_cgd():
    """cgd_winners: 2 งานเป้าหมาย (P1,P2) + นอกเกณฑ์ (จังหวัดผิด/proc ผิด/win_price=0)."""
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, win_price, budget, announce_date) "
            "VALUES (?,?,?,?,?,?,?)",
            [("P1", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2568", 100, 200, "2568-01-01"),
             ("P2", "บึงกาฬ", "สอบราคา", "2567", 100, 200, "2567-05-05"),
             ("PX", "ขอนแก่น", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2568", 100, 200, "2568-01-01"),  # จังหวัดผิด
             ("PY", "นครพนม", "เฉพาะเจาะจง", "2568", 100, 200, "2568-01-01"),                          # proc ผิด
             ("PZ", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2568", 0, 200, "2568-01-01")])    # win_price=0

def test_select_filters_and_dedup():
    _seed_cgd()
    prov = ["นครพนม", "บึงกาฬ"]; fy = ["2567", "2568", "2569"]
    with db.get_connection() as conn:
        got = bb.select_candidates(conn, prov, fy, seen=set())
    ids = {pid for pid, _date in got}
    assert ids == {"P1", "P2"}, ids                          # นอกเกณฑ์ถูกตัด
    assert dict(got)["P1"] == "2568-01-01"                   # คืน announce_date ด้วย
    # dedup: P1 มีใน bid_results แล้ว → ไม่คืน
    db.SubscriptionStore().record_bid_results("P1", [{"receiveNameTh": "ก", "receiveTin": "1"}])
    with db.get_connection() as conn:
        ids2 = {pid for pid, _ in bb.select_candidates(conn, prov, fy, seen=set())}
    assert ids2 == {"P2"}, ids2
    print("✅ select_candidates filter + dedup")

test_select_filters_and_dedup()
print("ALL PASS backfill_bidders")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_backfill_bidders.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backfill_bidders'`

- [ ] **Step 3: สร้าง `scripts/backfill_bidders.py`** (skeleton + select_candidates)

```python
"""backfill_bidders.py — เติม bid_results ด้วย full-bidder list ของงานที่จบแล้ว (2A).
รันบน VPS: ดึง projectId งานแข่งจริงจาก cgd_winners → getProcureResult → record_bid_results.
sequential + politeness sleep + resumable (backfill_seen.json) + fail-open ต่องาน.
fetched_at = announce_date ของงาน (recency ถูกต้องสำหรับ 2B). ดู spec 2026-06-13-allbidders-backfill-2a."""
import os, sys, json, time, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from process5_http_client import get_procure_result
from Sebastian_Customer_DB import SubscriptionStore, get_connection
from cgd_intel import COMPETITIVE_SET

DATA_DIR = Path(os.environ.get("BMS_DATA_DIR", "data"))
SEEN_PATH = DATA_DIR / "backfill_seen.json"
SLEEP = 1.5            # politeness ต่องาน (rate-limit retry อยู่ใน _get แล้ว)
CHECKPOINT_EVERY = 50


def log(msg: str):
    print(msg, flush=True)


def select_candidates(conn, provinces: list, fy: list, seen: set, limit=None) -> list:
    """คืน [(project_id, announce_date)] จาก cgd_winners ตาม scope, ตัดที่มีใน bid_results + seen.
    เรียง announce_date ใหม่→เก่า (งานสดก่อน). limit=None → ทั้งหมด."""
    pv = ",".join("?" for _ in provinces)
    fyp = ",".join("?" for _ in fy)
    ct = ",".join("?" for _ in COMPETITIVE_SET)
    sql = (f"SELECT project_id, COALESCE(announce_date,'') FROM cgd_winners "
           f"WHERE province IN ({pv}) AND proc_type IN ({ct}) AND fiscal_year IN ({fyp}) "
           f"AND win_price>0 AND project_id NOT IN (SELECT DISTINCT project_id FROM bid_results) "
           f"ORDER BY announce_date DESC")
    params = [*provinces, *COMPETITIVE_SET, *fy]
    rows = [(pid, d) for pid, d in conn.execute(sql, params) if pid not in seen]
    return rows[:limit] if limit else rows
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_backfill_bidders.py`
Expected: PASS — `✅ select_candidates filter + dedup`

- [ ] **Step 5: commit**

```bash
git add scripts/backfill_bidders.py scripts/test_backfill_bidders.py
git commit -m "feat(backfill): 2A select_candidates — scope filter + dedup + skip-seen"
```

---

### Task 2: backfill_one — fetch + store + empty/error status

**Files:**
- Modify: `scripts/backfill_bidders.py`
- Modify: `scripts/test_backfill_bidders.py`

- [ ] **Step 1: เพิ่ม failing test** ต่อท้าย `scripts/test_backfill_bidders.py` (ก่อน print "ALL PASS")

```python
def test_backfill_one_status():
    store = db.SubscriptionStore()
    # stored: มี bidder → เขียน + fetched_at = announce_date ที่ส่งเข้า
    bb.get_procure_result = lambda pid: {"winner": "ก", "bidders": [
        {"receiveNameTh": "ก", "receiveTin": "1", "priceAgree": "90", "priceProposal": "90"},
        {"receiveNameTh": "ข", "receiveTin": "2", "priceProposal": "110"}]}
    assert bb.backfill_one(store, "Q1", "2568-03-03") == "stored"
    rows = store.get_bid_results("Q1")
    assert len(rows) == 2 and all(r["fetched_at"] == "2568-03-03" for r in rows), rows
    # empty: bidders ว่าง → ไม่เขียน
    bb.get_procure_result = lambda pid: {"bidders": []}
    assert bb.backfill_one(store, "Q2", "2568-01-01") == "empty"
    assert store.get_bid_results("Q2") == []
    # error: ไม่มี key bidders ({}) → error
    bb.get_procure_result = lambda pid: {}
    assert bb.backfill_one(store, "Q3", "2568-01-01") == "error"
    # error: exception → error (fail-open, ไม่โยนต่อ)
    def _boom(pid): raise RuntimeError("net")
    bb.get_procure_result = _boom
    assert bb.backfill_one(store, "Q4", "2568-01-01") == "error"
    print("✅ backfill_one stored/empty/error")

test_backfill_one_status()
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_backfill_bidders.py`
Expected: FAIL — `AttributeError: module 'backfill_bidders' has no attribute 'backfill_one'`

- [ ] **Step 3: เพิ่ม `backfill_one`** ใน `scripts/backfill_bidders.py` (วางหลัง `select_candidates`)

```python
def backfill_one(store, pid: str, announce_date: str) -> str:
    """ดึง 1 งาน → เก็บ bidders. คืน 'stored'|'empty'|'error'.
    fetched_at = announce_date (งานเก่า ไม่ใช่ now → recency ถูก). fail-open: exception → 'error'."""
    try:
        res = get_procure_result(pid)
    except Exception as e:
        log(f"  {pid} fetch พลาด: {type(e).__name__}: {e}")
        return "error"
    if "bidders" not in res:          # {} = API error/rate หลัง retry ใน _get → ไม่ mark seen
        return "error"
    bidders = res["bidders"]
    if not bidders:
        return "empty"
    store.record_bid_results(pid, bidders, fetched_at=announce_date or None)
    return "stored"
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_backfill_bidders.py`
Expected: PASS — `✅ backfill_one stored/empty/error`

- [ ] **Step 5: commit**

```bash
git add scripts/backfill_bidders.py scripts/test_backfill_bidders.py
git commit -m "feat(backfill): 2A backfill_one — fetch+store, fetched_at=announce_date, fail-open"
```

---

### Task 3: run loop — checkpoint (resume) + idempotent + seen persistence

**Files:**
- Modify: `scripts/backfill_bidders.py`
- Modify: `scripts/test_backfill_bidders.py`

- [ ] **Step 1: เพิ่ม failing test** ต่อท้าย `scripts/test_backfill_bidders.py` (ก่อน print "ALL PASS")

```python
def test_run_resume_and_failopen():
    import json as _json
    # reset bid_results + seen file ให้ test นี้สะอาด
    with db.get_connection() as conn:
        conn.execute("DELETE FROM bid_results")
    if bb.SEEN_PATH.exists():
        bb.SEEN_PATH.unlink()
    _seed_cgd()  # candidate = R-set ใหม่: ใช้ P1,P2 (นครพนม/บึงกาฬ ในเกณฑ์)
    calls = []
    def fake(pid):
        calls.append(pid)
        if pid == "P2":
            raise RuntimeError("boom")        # 1 งานพัง → fail-open
        return {"bidders": [{"receiveNameTh": "ก", "receiveTin": "1", "priceProposal": "90"}]}
    bb.get_procure_result = fake
    stats = bb.run(["นครพนม", "บึงกาฬ"], ["2567", "2568", "2569"], sleep=0)
    assert stats["stored"] == 1 and stats["error"] == 1, stats     # P1 stored, P2 error
    assert db.SubscriptionStore().get_bid_results("P1"), "P1 ต้องถูกเก็บ"
    seen = set(_json.loads(bb.SEEN_PATH.read_text(encoding="utf-8")))
    assert "P1" in seen and "P2" not in seen, seen                 # error ไม่ mark seen → retry รอบหน้า
    # resume: รอบ 2 — P1 อยู่ใน bid_results แล้ว (select ตัด), เหลือ retry P2
    calls.clear()
    bb.run(["นครพนม", "บึงกาฬ"], ["2567", "2568", "2569"], sleep=0)
    assert "P1" not in calls and "P2" in calls, calls              # ไม่ดึง P1 ซ้ำ
    print("✅ run resume + fail-open + idempotent")

test_run_resume_and_failopen()
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_backfill_bidders.py`
Expected: FAIL — `AttributeError: module 'backfill_bidders' has no attribute 'run'`

- [ ] **Step 3: เพิ่ม `load_seen` / `save_seen` / `run`** ใน `scripts/backfill_bidders.py` (วางหลัง `backfill_one`)

```python
def load_seen() -> set:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            return set()
    return set()


def save_seen(seen: set):
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def run(provinces: list, fy: list, limit=None, dry_run=False, sleep=SLEEP) -> dict:
    """loop backfill ทุก candidate. resumable (seen) + fail-open. คืน stats dict."""
    seen = load_seen()
    with get_connection() as conn:
        cands = select_candidates(conn, provinces, fy, seen, limit)
    log(f"candidates: {len(cands)} งาน (seen={len(seen)}, dry_run={dry_run})")
    stats = {"stored": 0, "empty": 0, "error": 0}
    if dry_run:
        return stats
    store = SubscriptionStore()
    for i, (pid, adate) in enumerate(cands, 1):
        status = backfill_one(store, pid, adate)
        stats[status] += 1
        if status != "error":          # error ไม่ mark seen → retry รอบหน้า
            seen.add(pid)
        if i % CHECKPOINT_EVERY == 0:
            save_seen(seen)
            log(f"  [{i}/{len(cands)}] stored={stats['stored']} empty={stats['empty']} error={stats['error']}")
        if sleep:
            time.sleep(sleep)
    save_seen(seen)
    log(f"✅ เสร็จ: stored={stats['stored']} empty={stats['empty']} error={stats['error']}")
    return stats
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_backfill_bidders.py`
Expected: PASS — `✅ run resume + fail-open + idempotent` + `ALL PASS backfill_bidders`

- [ ] **Step 5: commit**

```bash
git add scripts/backfill_bidders.py scripts/test_backfill_bidders.py
git commit -m "feat(backfill): 2A run loop — checkpoint resume + fail-open + idempotent"
```

---

### Task 4: CLI main() + smoke

**Files:**
- Modify: `scripts/backfill_bidders.py`

- [ ] **Step 1: เพิ่ม `main()`** ท้าย `scripts/backfill_bidders.py`

```python
def main():
    ap = argparse.ArgumentParser(description="Backfill full-bidder list (2A) จาก cgd_winners → bid_results")
    ap.add_argument("--provinces", default="นครพนม,บึงกาฬ", help="คั่นด้วย ,")
    ap.add_argument("--fy", default="2567,2568,2569", help="ปีงบ คั่นด้วย ,")
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนงาน (probe run)")
    ap.add_argument("--dry-run", action="store_true", help="นับ candidate อย่างเดียว ไม่ดึง API")
    args = ap.parse_args()
    run([p.strip() for p in args.provinces.split(",") if p.strip()],
        [f.strip() for f in args.fy.split(",") if f.strip()],
        limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: smoke — dry-run บน dev** (ไม่ยิง API; ดูว่า CLI + select ทำงาน ไม่ error)

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/backfill_bidders.py --dry-run`
Expected: พิมพ์ `candidates: <N> งาน ...` ไม่ traceback (N อาจ 0 บน dev เพราะ cgd_winners ว่าง — OK)

- [ ] **Step 3: commit**

```bash
git add scripts/backfill_bidders.py
git commit -m "feat(backfill): 2A CLI main() (--provinces/--fy/--limit/--dry-run)"
```

---

### Task 5: Deploy + run บน VPS (manual — กัญจน์)

- [ ] **Step 1: push**

```bash
git push origin main
```

- [ ] **Step 2: deploy + verify candidate count (risk R1)** บน VPS

```bash
cd /opt/bms/app && bash scripts/deploy.sh
# R1: cgd_winners บน VPS มี target rows ครบไหม
BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python scripts/backfill_bidders.py --dry-run
```
Expected: `candidates: ~3000-4000 งาน`. ถ้า << คาด (เช่น <500) → STOP, cgd_winners ไม่ครบ → ทบทวน Approach B (source winner_history.db) ก่อนรันจริง

- [ ] **Step 3: probe run 100 งานก่อน full** (วัด rate-limit จริง + % error/empty)

```bash
BMS_DATA_DIR=/opt/bms/data nohup /opt/bms/venv/bin/python scripts/backfill_bidders.py --limit 100 > /tmp/backfill_probe.log 2>&1 &
sleep 200; tail -20 /tmp/backfill_probe.log
```
Expected: `stored` เป็นส่วนใหญ่, `error` ต่ำ (<10%). ถ้า error สูง → ดู log rate-limit ก่อนไปต่อ

- [ ] **Step 4: full run** (background, ~2-3 ชม.)

```bash
BMS_DATA_DIR=/opt/bms/data nohup /opt/bms/venv/bin/python scripts/backfill_bidders.py > /tmp/backfill_full.log 2>&1 &
```

- [ ] **Step 5: verify หลังจบ** (spec §8)

```bash
BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "import sqlite3; c=sqlite3.connect('/opt/bms/data/bms_customers.db'); print('jobs:', c.execute('SELECT COUNT(DISTINCT project_id) FROM bid_results').fetchone()[0]); print('losers:', c.execute('SELECT COUNT(*) FROM bid_results WHERE is_winner=0').fetchone()[0]); print('sample 67129346506:', c.execute('SELECT COUNT(*) FROM bid_results WHERE project_id=?', ('67129346506',)).fetchone()[0])"
```
Expected: `jobs` ≈ candidate count; `losers` > 0 (มีผู้แพ้จริง ไม่ใช่แค่ winner)

---

## Self-Review

**Spec coverage:**
- §3 scope (จังหวัด/proc_type/fy/win_price>0) → Task 1 `select_candidates` ✅
- §4 components: selector→T1 · fetcher(get_procure_result)→T2 · writer(record_bid_results)→T2 · checkpoint(seen)→T3 · CLI runner→T4 ✅
- §5 idempotency (skip already-done) → T1 dedup + T3 resume test ✅ · 1 call/job → T2 ✅
- §6 error handling (fail-open/empty/crash-resume) → T2 status model + T3 resume/fail-open test ✅
- §7 testing (5 เคส) → T1 (filter+dedup) · T2 (stored/empty/error 4 sub) · T3 (resume+fail-open+idempotent) ครบ ✅
- §8 verification → T5 step 5 ✅
- §10 R1 (cgd_winners ครบไหม) → T5 step 2 dry-run gate ✅ · R3 (rate-limit) → T5 step 3 probe ✅
- §9 out-of-scope (budget COALESCE, dominant-detection) → ไม่มีใน plan ✅

**Placeholder scan:** ไม่มี TBD/TODO — ทุก step มีโค้ด+คำสั่งจริง ✅ (เพิ่มเติมจาก spec: `fetched_at=announce_date` เพื่อ recency — ลงรายละเอียดใน T2)

**Type consistency:**
- `select_candidates(conn, provinces, fy, seen, limit=None)` → คืน `list[(pid, announce_date)]`; เรียกใน `run` ด้วย args ตรง ✅
- `backfill_one(store, pid, announce_date)` → คืน str status; เรียกใน `run` loop unpack `(pid, adate)` ✅
- `run(provinces, fy, limit, dry_run, sleep)` → test เรียกด้วย `sleep=0` (kwarg มี default) ✅
- `record_bid_results(pid, bidders, fetched_at=None)` — signature เดิม (1b) ไม่เปลี่ยน; `fetched_at=announce_date or None` ✅
- `get_procure_result` import เป็น module-level → test monkeypatch `bb.get_procure_result` resolve ตอนเรียก ✅
- `COMPETITIVE_SET` import จาก `cgd_intel` — ใช้ใน SQL placeholder + params ตรงจำนวน ✅
- `SEEN_PATH` ขึ้นกับ `BMS_DATA_DIR` (test set temp) → load/save_seen + test อ่าน `bb.SEEN_PATH` ตรงกัน ✅
