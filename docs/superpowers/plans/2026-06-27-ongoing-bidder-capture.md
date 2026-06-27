# Ongoing Bidder Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เก็บผู้ยื่นทุกราย ทุกงาน (ทุก proc_type รวมเฉพาะเจาะจง) ในนครพนม+บึงกาฬ แบบ going-forward ลง `bid_results` ผ่าน worker ใหม่ 2 pass

**Architecture:** โมดูลใหม่ `scripts/ongoing_bidder_capture.py` รันบน VPS — Pass 1 (LIVE) poll `getProcureResult` ของงานใน `projects_seen` ที่ discovery เจอหลัง deploy; Pass 2 (CGD-FILL) เติมงานจาก `cgd_winners` (เฉพาะเจาะจง = คัดลอกผู้ชนะ ไม่ยิง API; แข่ง = API backstop). คอลัมน์ `source` แยกที่มา. idempotent ผ่าน `NOT IN bid_results` + `INSERT OR REPLACE`.

**Tech Stack:** Python 3, SQLite (`bms_customers.db`), systemd timer, `process5_http_client.get_procure_result`, `Sebastian_Discord_Notify`

## Global Constraints

- จังหวัดเป้าหมาย default: `นครพนม,บึงกาฬ` (คั่น `,`)
- ทุก path เคารพ `BMS_DATA_DIR` (env, default `data`) — ห้าม hardcode `data/`
- Test รันแบบ **direct script** (`python scripts/test_X.py`) ไม่ใช่ pytest; ตั้ง `os.environ["BMS_DATA_DIR"]=tempfile.mkdtemp()` ก่อน import `Sebastian_Customer_DB`, แล้ว `db.init_schema()`; monkeypatch API ด้วยการ assign attribute โมดูล
- Rate discipline (INC-001): sleep 1.5s ต่อ **API call** + cooldown 130s ทุก 25 **API call** — copy path ไม่นับ (ไม่ยิง API)
- `bid_results` PK = (project_id, bidder_tin); `record_bid_results` = INSERT OR REPLACE เขียนทั้งแถว → ทุก field ต้องส่งทุกครั้ง กันค่าหาย
- `winner_tin` เพี้ยน ~99% → copy path ตั้ง `receiveTin=''` ให้ `record_bid_results` ใช้ name-fallback key
- migration ใหม่ต่อท้ายใน `init_schema()` (หลัง `_migrate_v135()` บรรทัด ~318) + อัปเดตข้อความ version print
- `COMPETITIVE_SET` import จาก `cgd_intel` (e-bidding/วิธีการทางอิเล็กทรอนิกส์/สอบราคา/คัดเลือก)

---

## File Structure

- `scripts/Sebastian_Customer_DB.py` (modify) — `_migrate_v136` + `record_bid_results(source=...)`
- `scripts/ongoing_bidder_capture.py` (create) — worker 2 pass + state/seen + main
- `scripts/test_bid_results_source.py` (create) — Task 1
- `scripts/test_ongoing_state.py` (create) — Task 2
- `scripts/test_ongoing_cgd.py` (create) — Task 3
- `scripts/test_ongoing_live.py` (create) — Task 4
- `scripts/test_ongoing_run.py` (create) — Task 5
- `deploy/systemd/bms-ongoing-bidder-capture.service` (create) — Task 6
- `deploy/systemd/bms-ongoing-bidder-capture.timer` (create) — Task 6

---

## Task 1: Schema `source` column + record_bid_results

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py` (เพิ่ม `_migrate_v136`, เรียกใน init_schema ~318, แก้ `record_bid_results` ~1012)
- Test: `scripts/test_bid_results_source.py`

**Interfaces:**
- Produces: `SubscriptionStore.record_bid_results(project_id, bidders, fetched_at=None, source="procure_api") -> int` — เขียนคอลัมน์ `bid_results.source`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_bid_results_source.py
"""bid_results.source column + record_bid_results source param (v136)."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()

def test_source_column_exists():
    with db.get_connection() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(bid_results)")]
    assert "source" in cols, cols
    print("✅ bid_results.source column exists")

def test_default_and_explicit_source():
    store = db.SubscriptionStore()
    store.record_bid_results("A1", [{"receiveNameTh": "ก", "receiveTin": "1", "priceProposal": "90"}])
    store.record_bid_results("A2", [{"receiveNameTh": "ข", "receiveTin": "2", "priceProposal": "80"}],
                             source="cgd_copy")
    rows = {r["project_id"]: r for r in db.SubscriptionStore().get_bid_results("A1")
            + db.SubscriptionStore().get_bid_results("A2")}
    assert rows["A1"]["source"] == "procure_api", rows["A1"]
    assert rows["A2"]["source"] == "cgd_copy", rows["A2"]
    print("✅ default=procure_api, explicit=cgd_copy")

def test_rewrite_keeps_source():
    """INSERT OR REPLACE เขียนทั้งแถว — รันซ้ำด้วย source ใหม่ ต้องอัปเดต ไม่ใช่หาย."""
    store = db.SubscriptionStore()
    store.record_bid_results("A3", [{"receiveNameTh": "ค", "receiveTin": "3", "priceProposal": "70"}],
                             source="cgd_copy")
    store.record_bid_results("A3", [{"receiveNameTh": "ค", "receiveTin": "3", "priceAgree": "70",
                                     "priceProposal": "70"}], source="procure_api")
    rows = db.SubscriptionStore().get_bid_results("A3")
    assert len(rows) == 1 and rows[0]["source"] == "procure_api", rows
    print("✅ rewrite updates source (no loss)")

test_source_column_exists()
test_default_and_explicit_source()
test_rewrite_keeps_source()
print("ALL PASS bid_results source")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_bid_results_source.py`
Expected: FAIL — `AssertionError` ("source" not in cols) หรือ `record_bid_results` ไม่รับ keyword `source`

- [ ] **Step 3: Add `_migrate_v136` and call it**

ใน `scripts/Sebastian_Customer_DB.py` เพิ่มฟังก์ชันต่อจาก `_migrate_v135` (หลังบรรทัด ~395):

```python
def _migrate_v136():
    """bid_results +source — แยกที่มาแถว: 'procure_api' (getProcureResult) vs 'cgd_copy'
    (คัดลอกผู้ชนะจาก cgd_winners สำหรับงานเฉพาะเจาะจง ผู้ยื่นรายเดียว — ongoing_bidder_capture).
    แถวเก่ามาจาก API ทั้งหมด → backfill NULL→'procure_api' (one-time). record_bid_results ต้องเขียน
    source ทุกครั้ง (INSERT OR REPLACE เขียนทั้งแถว ไม่งั้นหายเหมือน normalized_name v135)."""
    with get_connection() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(bid_results)")]
        if "source" not in cols:
            conn.execute("ALTER TABLE bid_results ADD COLUMN source TEXT")
            conn.execute("UPDATE bid_results SET source='procure_api' WHERE source IS NULL")
```

แก้บล็อกเรียก migration (บรรทัด ~317-319):

```python
    _migrate_v134()
    _migrate_v135()
    _migrate_v136()
    print(f"Schema v1.14 ready: {DB_PATH}")
```

- [ ] **Step 4: Update `record_bid_results` to write source**

แก้ signature + INSERT (บรรทัด ~1012-1037). signature:

```python
    def record_bid_results(self, project_id: str, bidders: list, fetched_at: str = None,
                           source: str = "procure_api") -> int:
```

ใน loop เปลี่ยน INSERT ให้มี `source`:

```python
                conn.execute("""
                    INSERT OR REPLACE INTO bid_results
                      (project_id, bidder_name, bidder_tin, price_proposal, price_agree,
                       is_winner, is_sme, result_flag, fetched_at, normalized_name, source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (project_id, name, key, b.get("priceProposal") or "", pa,
                      1 if pa else 0, 1 if b.get("is_sme") else 0,
                      b.get("resultFlag") or "", fetched_at, _pv._norm_name(name), source))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python scripts/test_bid_results_source.py`
Expected: PASS — `ALL PASS bid_results source`

- [ ] **Step 6: Regression — backfill_bidders ยังเขียว**

Run: `python scripts/test_backfill_bidders.py`
Expected: PASS — `ALL PASS backfill_bidders` (record_bid_results default source ไม่ทำของเดิมพัง)

- [ ] **Step 7: Commit**

```bash
git add scripts/Sebastian_Customer_DB.py scripts/test_bid_results_source.py
git commit -m "feat(db): bid_results.source column (v136) + record_bid_results source param"
```

---

## Task 2: Module scaffold — state + seen helpers

**Files:**
- Create: `scripts/ongoing_bidder_capture.py`
- Test: `scripts/test_ongoing_state.py`

**Interfaces:**
- Produces:
  - `ensure_state(today=None) -> dict` — คืน `{"epoch_date": "YYYY-MM-DD", "epoch_fy": int}`; สร้างไฟล์ `STATE_PATH` ครั้งแรก, ครั้งถัดไปอ่านของเดิม (ไม่ overwrite)
  - `load_seen(path) -> set`, `save_seen(path, seen)` — JSON set helpers
  - constants: `STATE_PATH`, `SEEN_CGD_PATH`, `PROVINCES`, `MIN_AGE_DAYS=7`, `MAX_AGE_DAYS=90`, `SLEEP=1.5`, `COOLDOWN_EVERY=25`, `COOLDOWN_SEC=130`, `CHECKPOINT_EVERY=50`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_ongoing_state.py
"""ongoing_bidder_capture: state (epoch) + seen helpers."""
import os, tempfile, sys, json, datetime
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def test_ensure_state_creates_then_persists():
    d = datetime.date(2026, 6, 27)
    st = oc.ensure_state(today=d)
    assert st["epoch_date"] == "2026-06-27", st
    assert st["epoch_fy"] == 2569, st            # ปีงบไทย ก่อน ต.ค. → 2569
    # ครั้งที่ 2 (วันอื่น) ต้องอ่านของเดิม ไม่ overwrite
    st2 = oc.ensure_state(today=datetime.date(2027, 1, 1))
    assert st2 == st, st2
    print("✅ ensure_state create + persist (no overwrite)")

def test_seen_roundtrip():
    p = oc.SEEN_CGD_PATH
    oc.save_seen(p, {"X1", "X2"})
    assert oc.load_seen(p) == {"X1", "X2"}
    # ไฟล์ไม่มี → set ว่าง
    missing = oc.DATA_DIR / "nope.json"
    assert oc.load_seen(missing) == set()
    print("✅ seen save/load roundtrip")

test_ensure_state_creates_then_persists()
test_seen_roundtrip()
print("ALL PASS ongoing_state")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_ongoing_state.py`
Expected: FAIL — `ModuleNotFoundError: ongoing_bidder_capture`

- [ ] **Step 3: Create module scaffold**

```python
# scripts/ongoing_bidder_capture.py
"""ongoing_bidder_capture.py — เก็บผู้ยื่นทุกราย ทุกงาน หลังจากนี้ (นครพนม+บึงกาฬ, ทุก proc_type).
2 pass: LIVE (projects_seen → getProcureResult, แข่งสด) + CGD-FILL (cgd_winners → เฉพาะเจาะจง copy /
แข่ง API backstop). going-forward ไม่ใช่ backfill: epoch_date floor (Pass1) + epoch_fy floor (Pass2).
ดู spec 2026-06-27-ongoing-bidder-capture-design."""
import os, sys, json, time, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from Sebastian_Customer_DB import SubscriptionStore, get_connection
from cgd_intel import COMPETITIVE_SET
import backfill_bidders as bb   # reuse current_fy (DRY)

DATA_DIR = Path(os.environ.get("BMS_DATA_DIR", "data"))
STATE_PATH = DATA_DIR / "ongoing_capture_state.json"
SEEN_CGD_PATH = DATA_DIR / "ongoing_capture_seen_cgd.json"
PROVINCES = ["นครพนม", "บึงกาฬ"]
MIN_AGE_DAYS = 7      # ใหม่กว่านี้ = ยังไม่ award (ไม่ต้อง poll)
MAX_AGE_DAYS = 90     # เก่ากว่านี้ = เลิก poll (กัน loop งานที่ไม่มีผลถาวร)
SLEEP = 1.5
COOLDOWN_EVERY = 25
COOLDOWN_SEC = 130
CHECKPOINT_EVERY = 50


def log(msg: str):
    print(msg, flush=True)


def _today() -> datetime.date:
    return datetime.date.today()


def ensure_state(today: datetime.date = None) -> dict:
    """อ่าน/สร้าง state. epoch = เส้นแบ่ง going-forward (ไม่ backfill ของก่อน deploy).
    epoch_date = วันนี้ (ISO, floor ของ projects_seen.first_seen_at);
    epoch_fy = ปีงบไทยวันนี้ (floor ของ cgd_winners.fiscal_year — announce_date เป็น Thai date เทียบ ISO ไม่ได้)."""
    today = today or _today()
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state = {"epoch_date": today.isoformat(), "epoch_fy": bb.current_fy(today)}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


def load_seen(path: Path) -> set:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            return set()
    return set()


def save_seen(path: Path, seen: set):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_ongoing_state.py`
Expected: PASS — `ALL PASS ongoing_state`

- [ ] **Step 5: Commit**

```bash
git add scripts/ongoing_bidder_capture.py scripts/test_ongoing_state.py
git commit -m "feat(capture): ongoing_bidder_capture scaffold — state(epoch) + seen helpers"
```

---

## Task 3: Pass 2 — CGD-FILL (select + copy/API capture)

**Files:**
- Modify: `scripts/ongoing_bidder_capture.py`
- Test: `scripts/test_ongoing_cgd.py`

**Interfaces:**
- Consumes: `COMPETITIVE_SET`, `SubscriptionStore.record_bid_results(..., source=)`
- Produces:
  - `select_cgd_candidates(conn, provinces, epoch_fy, seen) -> list[tuple]` — คืน `(project_id, proc_type, winner, win_price)` กรอง province + `fiscal_year >= epoch_fy` + NOT IN bid_results + ไม่อยู่ seen
  - `_winner_as_bidder(winner, win_price) -> dict` — bidder dict สังเคราะห์ (receiveTin='')
  - `capture_cgd_one(store, row, get_procure_result) -> str` — `'copied'|'stored'|'empty'|'error'`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_ongoing_cgd.py
"""ongoing_bidder_capture Pass 2: CGD-FILL select + copy/API capture."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def _seed():
    """cgd_winners: เจาะจง(C1) + แข่ง(C2) ปีงบ>=2569; นอกเกณฑ์ ปีเก่า(C3)/จังหวัดผิด(C4)."""
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, winner, win_price, budget) "
            "VALUES (?,?,?,?,?,?,?)",
            [("C1", "นครพนม", "เฉพาะเจาะจง", "2569", "หจก. เอ", 100, 100),
             ("C2", "บึงกาฬ", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2569", "หจก. บี", 90, 100),
             ("C3", "นครพนม", "เฉพาะเจาะจง", "2568", "หจก. ซี", 100, 100),     # ปีเก่า < epoch_fy
             ("C4", "ขอนแก่น", "เฉพาะเจาะจง", "2569", "หจก. ดี", 100, 100)])   # จังหวัดผิด

def test_select_floor_and_province():
    _seed()
    with db.get_connection() as conn:
        got = {r[0] for r in oc.select_cgd_candidates(conn, oc.PROVINCES, 2569, seen=set())}
    assert got == {"C1", "C2"}, got                  # ตัดปีเก่า + จังหวัดผิด
    print("✅ select_cgd floor(fy>=epoch) + province")

def test_capture_copy_no_api():
    _seed()
    store = db.SubscriptionStore()
    called = []
    api = lambda pid: called.append(pid) or {"bidders": []}
    # เฉพาะเจาะจง → copy ไม่เรียก API, source=cgd_copy, is_winner=1
    assert oc.capture_cgd_one(store, ("C1", "เฉพาะเจาะจง", "หจก. เอ", 100), api) == "copied"
    assert called == [], "copy ต้องไม่เรียก API"
    rows = store.get_bid_results("C1")
    assert len(rows) == 1 and rows[0]["source"] == "cgd_copy" and rows[0]["is_winner"] == 1, rows
    assert rows[0]["bidder_name"] == "หจก. เอ", rows
    print("✅ เฉพาะเจาะจง copy (no API, source=cgd_copy)")

def test_capture_competitive_api_then_fallback():
    store = db.SubscriptionStore()
    # แข่ง + API มีผล → stored, source=procure_api
    api_ok = lambda pid: {"bidders": [
        {"receiveNameTh": "บี", "receiveTin": "9", "priceAgree": "90", "priceProposal": "90"},
        {"receiveNameTh": "อี", "receiveTin": "8", "priceProposal": "95"}]}
    assert oc.capture_cgd_one(store, ("K1", "สอบราคา", "บี", 90), api_ok) == "stored"
    r1 = store.get_bid_results("K1")
    assert len(r1) == 2 and all(r["source"] == "procure_api" for r in r1), r1
    # แข่ง + API ล้ม → fallback copy winner, source=cgd_copy
    def boom(pid): raise RuntimeError("net")
    assert oc.capture_cgd_one(store, ("K2", "สอบราคา", "เอฟ", 80), boom) == "copied"
    r2 = store.get_bid_results("K2")
    assert len(r2) == 1 and r2[0]["source"] == "cgd_copy", r2
    print("✅ แข่ง API stored / API ล้ม fallback copy")

test_select_floor_and_province()
test_capture_copy_no_api()
test_capture_competitive_api_then_fallback()
print("ALL PASS ongoing_cgd")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_ongoing_cgd.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'select_cgd_candidates'`

- [ ] **Step 3: Implement Pass 2 functions**

เพิ่มใน `scripts/ongoing_bidder_capture.py`:

```python
def select_cgd_candidates(conn, provinces: list, epoch_fy: int, seen: set) -> list:
    """cgd_winners ในจังหวัดเป้าหมาย, fiscal_year >= epoch_fy (ไม่ backfill ปีเก่า),
    ยังไม่อยู่ bid_results, ไม่อยู่ seen. คืน [(project_id, proc_type, winner, win_price)]."""
    pv = ",".join("?" for _ in provinces)
    sql = (f"SELECT project_id, proc_type, winner, win_price FROM cgd_winners "
           f"WHERE province IN ({pv}) AND CAST(fiscal_year AS INTEGER) >= ? "
           f"AND project_id NOT IN (SELECT DISTINCT project_id FROM bid_results)")
    rows = conn.execute(sql, [*provinces, epoch_fy]).fetchall()
    return [(pid, pt, w, wp) for pid, pt, w, wp in rows if pid not in seen]


def _winner_as_bidder(winner, win_price) -> dict:
    """ผู้ชนะ cgd_winners → bidder dict (ผู้ยื่นรายเดียวงานเฉพาะเจาะจง). receiveTin='' →
    record_bid_results ใช้ name-fallback key (winner_tin เพี้ยน ~99%). priceAgree set → is_winner=1."""
    price = str(win_price) if win_price not in (None, "") else ""
    return {"receiveNameTh": winner or "", "receiveTin": "",
            "priceProposal": price, "priceAgree": price}


def capture_cgd_one(store, row, get_procure_result) -> str:
    """row=(pid, proc_type, winner, win_price). เฉพาะเจาะจง/ไม่แข่ง → copy (ไม่ยิง API);
    แข่ง → getProcureResult (fallback copy ถ้าล้ม/ว่าง). คืน 'copied'|'stored'|'empty'|'error'."""
    pid, proc_type, winner, win_price = row
    if proc_type not in COMPETITIVE_SET:
        if not winner:
            return "empty"
        store.record_bid_results(pid, [_winner_as_bidder(winner, win_price)], source="cgd_copy")
        return "copied"
    try:
        res = get_procure_result(pid)
    except Exception:
        res = {}
    if res.get("bidders"):
        store.record_bid_results(pid, res["bidders"], source="procure_api")
        return "stored"
    if winner:   # API ล้ม/ว่าง → มีผู้ชนะดีกว่าไม่มี
        store.record_bid_results(pid, [_winner_as_bidder(winner, win_price)], source="cgd_copy")
        return "copied"
    return "empty"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_ongoing_cgd.py`
Expected: PASS — `ALL PASS ongoing_cgd`

- [ ] **Step 5: Commit**

```bash
git add scripts/ongoing_bidder_capture.py scripts/test_ongoing_cgd.py
git commit -m "feat(capture): Pass 2 CGD-FILL — เจาะจง copy + แข่ง API backstop"
```

---

## Task 4: Pass 1 — LIVE (select + capture)

**Files:**
- Modify: `scripts/ongoing_bidder_capture.py`
- Test: `scripts/test_ongoing_live.py`

**Interfaces:**
- Consumes: `MIN_AGE_DAYS`, `MAX_AGE_DAYS`
- Produces:
  - `select_live_candidates(conn, provinces, epoch_date, today=None, min_age=MIN_AGE_DAYS, max_age=MAX_AGE_DAYS) -> list[str]` — project_id จาก projects_seen, province + first_seen_at ในช่วง [max(epoch_date, today-max_age), today-min_age] + NOT IN bid_results
  - `capture_live_one(store, pid, get_procure_result) -> str` — `'stored'|'empty'|'error'` (source='procure_api')

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_ongoing_live.py
"""ongoing_bidder_capture Pass 1: LIVE select(age window/epoch/province) + capture."""
import os, tempfile, sys, datetime
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def _seed():
    """projects_seen: first_seen_at ต่างวันเพื่อทดสอบ window/epoch/province."""
    def ins(pid, prov, fs):
        with db.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO projects_seen "
                         "(project_id, province, first_seen_at) VALUES (?,?,?)", (pid, prov, fs))
    ins("L_ok",     "นครพนม", "2026-06-15T00:00:00")   # อายุ 12 วัน (today 6-27) → ในช่วง [7,90]
    ins("L_new",    "นครพนม", "2026-06-25T00:00:00")   # อายุ 2 วัน → ใหม่เกิน (ตัด)
    ins("L_old",    "บึงกาฬ", "2026-02-01T00:00:00")   # อายุ >90 วัน → เก่าเกิน (ตัด)
    ins("L_preepoch","นครพนม","2026-06-10T00:00:00")   # ก่อน epoch_date 6-12 (ตัด แม้ window ผ่าน)
    ins("L_other",  "ขอนแก่น", "2026-06-15T00:00:00")  # จังหวัดผิด (ตัด)

def test_select_window_epoch_province():
    _seed()
    today = datetime.date(2026, 6, 27)
    with db.get_connection() as conn:
        got = set(oc.select_live_candidates(conn, oc.PROVINCES, "2026-06-12", today=today))
    assert got == {"L_ok"}, got     # เหลือแค่ตัวที่ผ่านทั้ง window+epoch+province
    print("✅ select_live window + epoch + province")

def test_select_skips_captured():
    """งานที่มีใน bid_results แล้ว → ไม่คืน (idempotent)."""
    db.SubscriptionStore().record_bid_results("L_ok", [{"receiveNameTh": "ก", "receiveTin": "1"}])
    today = datetime.date(2026, 6, 27)
    with db.get_connection() as conn:
        got = set(oc.select_live_candidates(conn, oc.PROVINCES, "2026-06-12", today=today))
    assert "L_ok" not in got, got
    print("✅ select_live skips captured")

def test_capture_live_status():
    store = db.SubscriptionStore()
    oc_api = lambda pid: {"winner": "ก", "bidders": [
        {"receiveNameTh": "ก", "receiveTin": "1", "priceAgree": "90", "priceProposal": "90"}]}
    assert oc.capture_live_one(store, "M1", oc_api) == "stored"
    assert store.get_bid_results("M1")[0]["source"] == "procure_api"
    assert oc.capture_live_one(store, "M2", lambda pid: {"bidders": []}) == "empty"   # ยังไม่ award
    assert oc.capture_live_one(store, "M3", lambda pid: {}) == "error"                # ไม่มี key
    def boom(pid): raise RuntimeError("net")
    assert oc.capture_live_one(store, "M4", boom) == "error"
    print("✅ capture_live stored/empty/error (source=procure_api)")

test_select_window_epoch_province()
test_select_skips_captured()
test_capture_live_status()
print("ALL PASS ongoing_live")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_ongoing_live.py`
Expected: FAIL — `AttributeError: ... 'select_live_candidates'`

- [ ] **Step 3: Implement Pass 1 functions**

เพิ่มใน `scripts/ongoing_bidder_capture.py`:

```python
def select_live_candidates(conn, provinces: list, epoch_date: str, today: datetime.date = None,
                           min_age: int = MIN_AGE_DAYS, max_age: int = MAX_AGE_DAYS) -> list:
    """projects_seen ในจังหวัดเป้าหมาย, first_seen_at ในช่วง [max(epoch_date, today-max_age), today-min_age],
    ยังไม่อยู่ bid_results. (first_seen_at เป็น ISO timestamp → เทียบ date string แบบ prefix ได้;
    ±1 วันที่ขอบ window ยอมรับได้). คืน [project_id]."""
    today = today or _today()
    lo = max(epoch_date, (today - datetime.timedelta(days=max_age)).isoformat())
    hi = (today - datetime.timedelta(days=min_age)).isoformat()
    pv = ",".join("?" for _ in provinces)
    sql = (f"SELECT project_id FROM projects_seen WHERE province IN ({pv}) "
           f"AND first_seen_at >= ? AND first_seen_at <= ? "
           f"AND project_id NOT IN (SELECT DISTINCT project_id FROM bid_results)")
    return [r[0] for r in conn.execute(sql, [*provinces, lo, hi])]


def capture_live_one(store, pid: str, get_procure_result) -> str:
    """ดึง 1 งานสด → เก็บ bidders. ไม่มีผล (ยังไม่ award) → 'empty' (รอบหน้ายังเป็น candidate ตาม window).
    fail-open. คืน 'stored'|'empty'|'error'."""
    try:
        res = get_procure_result(pid)
    except Exception as e:
        log(f"  {pid} live fetch พลาด: {type(e).__name__}: {e}")
        return "error"
    if "bidders" not in res:
        return "error"
    if not res["bidders"]:
        return "empty"
    store.record_bid_results(pid, res["bidders"], source="procure_api")
    return "stored"
```

> NOTE: `hi` เป็น date (`'2026-06-20'`) เทียบกับ first_seen_at timestamp (`'2026-06-20T..'`) → ตัวที่ first_seen ตรงวัน hi พอดีจะถูกตัด (prefix ใหญ่กว่า) = แก่ขึ้น 1 วันที่ขอบ; ยอมรับได้ตาม spec.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_ongoing_live.py`
Expected: PASS — `ALL PASS ongoing_live`

- [ ] **Step 5: Commit**

```bash
git add scripts/ongoing_bidder_capture.py scripts/test_ongoing_live.py
git commit -m "feat(capture): Pass 1 LIVE — discovery age-window poll → getProcureResult"
```

---

## Task 5: Run loops + main + Discord summary

**Files:**
- Modify: `scripts/ongoing_bidder_capture.py`
- Test: `scripts/test_ongoing_run.py`

**Interfaces:**
- Consumes: ทุกฟังก์ชัน Task 2-4
- Produces:
  - `run_live(provinces, epoch_date, get_procure_result, sleep=SLEEP, today=None, cooldown_every=COOLDOWN_EVERY, cooldown_sec=COOLDOWN_SEC) -> dict` — stats `{stored,empty,error}`; pace ทุก iteration (ยิง API ทุกตัว)
  - `run_cgd(provinces, epoch_fy, get_procure_result, sleep=SLEEP, cooldown_every=COOLDOWN_EVERY, cooldown_sec=COOLDOWN_SEC) -> dict` — stats `{copied,stored,empty,error}`; pace **เฉพาะ API call** (copy ไม่พัก); seen-set กัน re-poll empty/error
  - `main()` — CLI `--provinces`, `--pass {live,cgd,all}`, `--dry-run`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_ongoing_run.py
"""ongoing_bidder_capture: run_live / run_cgd loops — stats, idempotent, API-only pacing."""
import os, tempfile, sys, datetime
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def test_run_cgd_mixed_and_idempotent():
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, winner, win_price, budget) VALUES (?,?,?,?,?,?,?)",
            [("G1", "นครพนม", "เฉพาะเจาะจง", "2569", "เอ", 100, 100),
             ("G2", "บึงกาฬ", "สอบราคา", "2569", "บี", 90, 100)])
    api = lambda pid: {"bidders": [{"receiveNameTh": "บี", "receiveTin": "2", "priceProposal": "90"}]}
    stats = oc.run_cgd(oc.PROVINCES, 2569, api, sleep=0)
    assert stats["copied"] == 1 and stats["stored"] == 1, stats     # G1 copy, G2 API
    # idempotent: รอบ 2 ไม่เก็บซ้ำ (อยู่ bid_results แล้ว)
    stats2 = oc.run_cgd(oc.PROVINCES, 2569, api, sleep=0)
    assert stats2 == {"copied": 0, "stored": 0, "empty": 0, "error": 0}, stats2
    assert len(db.SubscriptionStore().get_bid_results("G1")) == 1
    print("✅ run_cgd mixed copy/API + idempotent")

def test_run_cgd_paces_only_api():
    """copy ไม่ยิง API → ต้องไม่ sleep; เฉพาะ competitive ที่ยิง API ถึงพับ cooldown."""
    if oc.SEEN_CGD_PATH.exists():
        oc.SEEN_CGD_PATH.unlink()
    with db.get_connection() as conn:
        conn.execute("DELETE FROM bid_results")
        conn.execute("DELETE FROM cgd_winners")
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, winner, win_price, budget) VALUES (?,?,?,?,?,?,?)",
            [("P_a", "นครพนม", "เฉพาะเจาะจง", "2569", "เอ", 1, 1),
             ("P_b", "นครพนม", "เฉพาะเจาะจง", "2569", "บี", 1, 1),
             ("P_c", "บึงกาฬ", "สอบราคา", "2569", "ซี", 1, 1)])
    api = lambda pid: {"bidders": [{"receiveNameTh": "ซี", "receiveTin": "3", "priceProposal": "1"}]}
    slept = []
    orig = oc.time.sleep; oc.time.sleep = lambda s: slept.append(s)
    try:
        oc.run_cgd(oc.PROVINCES, 2569, api, sleep=1, cooldown_every=1, cooldown_sec=130)
    finally:
        oc.time.sleep = orig
    # มี API call จริง 1 (P_c) → cooldown_every=1 แต่เป็นงาน API สุดท้าย (ไม่พักหลังตัวสุดท้าย) → ไม่มี 130
    # อย่างน้อยต้องไม่ sleep ตาม copy 2 ตัว: จำนวน sleep ต้อง <= จำนวน API call
    assert slept.count(130) == 0, slept
    assert len([s for s in slept if s == 1]) <= 1, slept
    print("✅ run_cgd paces only on API calls (copy ไม่พัก)")

def test_run_live_stats():
    with db.get_connection() as conn:
        conn.execute("DELETE FROM bid_results")
        conn.execute("INSERT OR REPLACE INTO projects_seen (project_id, province, first_seen_at) "
                     "VALUES ('LV1','นครพนม','2026-06-15T00:00:00')")
    api = lambda pid: {"bidders": [{"receiveNameTh": "ก", "receiveTin": "1", "priceProposal": "9"}]}
    stats = oc.run_live(oc.PROVINCES, "2026-06-12", api, sleep=0, today=datetime.date(2026, 6, 27))
    assert stats["stored"] == 1, stats
    print("✅ run_live stats")

test_run_cgd_mixed_and_idempotent()
test_run_cgd_paces_only_api()
test_run_live_stats()
print("ALL PASS ongoing_run")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_ongoing_run.py`
Expected: FAIL — `AttributeError: ... 'run_cgd'`

- [ ] **Step 3: Implement run loops + main**

เพิ่มใน `scripts/ongoing_bidder_capture.py`:

```python
def run_live(provinces, epoch_date, get_procure_result, sleep=SLEEP, today=None,
             cooldown_every=COOLDOWN_EVERY, cooldown_sec=COOLDOWN_SEC) -> dict:
    """Pass 1: poll งานสดใน window. ยิง API ทุก candidate → pace ทุก iteration."""
    with get_connection() as conn:
        cands = select_live_candidates(conn, provinces, epoch_date, today=today)
    log(f"[live] candidates: {len(cands)}")
    stats = {"stored": 0, "empty": 0, "error": 0}
    store = SubscriptionStore()
    for i, pid in enumerate(cands, 1):
        stats[capture_live_one(store, pid, get_procure_result)] += 1
        if sleep and cooldown_every and i % cooldown_every == 0 and i < len(cands):
            log(f"  💤 cooldown {cooldown_sec}s")
            time.sleep(cooldown_sec)
        elif sleep:
            time.sleep(sleep)
    log(f"[live] stored={stats['stored']} empty={stats['empty']} error={stats['error']}")
    return stats


def run_cgd(provinces, epoch_fy, get_procure_result, sleep=SLEEP,
            cooldown_every=COOLDOWN_EVERY, cooldown_sec=COOLDOWN_SEC) -> dict:
    """Pass 2: เติมจาก cgd_winners. pace เฉพาะ API call (copy ไม่ยิง API → ไม่พัก กันค้างแสน copy).
    seen-set กัน re-poll empty/error; copied/stored ตัดด้วย NOT IN bid_results อยู่แล้ว."""
    seen = load_seen(SEEN_CGD_PATH)
    with get_connection() as conn:
        cands = select_cgd_candidates(conn, provinces, epoch_fy, seen)
    log(f"[cgd] candidates: {len(cands)}")
    stats = {"copied": 0, "stored": 0, "empty": 0, "error": 0}
    store = SubscriptionStore()
    api_calls = 0
    for i, row in enumerate(cands, 1):
        is_competitive = row[1] in COMPETITIVE_SET
        status = capture_cgd_one(store, row, get_procure_result)
        stats[status] += 1
        if status != "error":
            seen.add(row[0])
        if i % CHECKPOINT_EVERY == 0:
            save_seen(SEEN_CGD_PATH, seen)
        if is_competitive:                       # pace เฉพาะที่ยิง API
            api_calls += 1
            remaining_api = sum(1 for r in cands[i:] if r[1] in COMPETITIVE_SET)
            if sleep and cooldown_every and api_calls % cooldown_every == 0 and remaining_api:
                log(f"  💤 cooldown {cooldown_sec}s")
                time.sleep(cooldown_sec)
            elif sleep and remaining_api:
                time.sleep(sleep)
    save_seen(SEEN_CGD_PATH, seen)
    log(f"[cgd] copied={stats['copied']} stored={stats['stored']} "
        f"empty={stats['empty']} error={stats['error']}")
    return stats


def _notify(summary: dict):
    """ส่งสรุป Discord (best-effort — ไม่ให้ล้มงานถ้า notify พัง)."""
    try:
        from Sebastian_Discord_Notify import load_env, get_credentials, send
        load_env(); token, ch = get_credentials()
        parts = [f"{k}: {v}" for k, v in summary.items()]
        send(token, ch, "✅ Ongoing bidder capture เสร็จ — " + " | ".join(parts))
    except Exception as e:
        log(f"discord notify พลาด: {e}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Ongoing bidder capture (going-forward, 2 จังหวัด)")
    ap.add_argument("--provinces", default=",".join(PROVINCES), help="คั่นด้วย ,")
    ap.add_argument("--pass", dest="which", choices=["live", "cgd", "all"], default="all")
    ap.add_argument("--dry-run", action="store_true", help="นับ candidate ไม่เรียก API/ไม่เขียน")
    args = ap.parse_args()
    provinces = [p.strip() for p in args.provinces.split(",") if p.strip()]
    state = ensure_state()
    log(f"epoch_date={state['epoch_date']} epoch_fy={state['epoch_fy']} provinces={provinces}")
    if args.dry_run:
        with get_connection() as conn:
            nl = len(select_live_candidates(conn, provinces, state["epoch_date"]))
            nc = len(select_cgd_candidates(conn, provinces, state["epoch_fy"], load_seen(SEEN_CGD_PATH)))
        log(f"[dry-run] live candidates={nl}, cgd candidates={nc}")
        return
    from process5_http_client import get_procure_result
    summary = {}
    if args.which in ("live", "all"):
        summary["live"] = run_live(provinces, state["epoch_date"], get_procure_result)
    if args.which in ("cgd", "all"):
        summary["cgd"] = run_cgd(provinces, state["epoch_fy"], get_procure_result)
    _notify(summary)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_ongoing_run.py`
Expected: PASS — `ALL PASS ongoing_run`

- [ ] **Step 5: Full regression of capture suite**

Run: `python scripts/test_ongoing_state.py && python scripts/test_ongoing_cgd.py && python scripts/test_ongoing_live.py && python scripts/test_ongoing_run.py && python scripts/test_bid_results_source.py && python scripts/test_backfill_bidders.py`
Expected: ทุกไฟล์ลงท้าย `ALL PASS ...`

- [ ] **Step 6: Dry-run smoke (local, ไม่ยิง API)**

Run: `python scripts/ongoing_bidder_capture.py --dry-run`
Expected: พิมพ์ `epoch_date=... epoch_fy=...` + `[dry-run] live candidates=N, cgd candidates=M` (ไม่ error)

- [ ] **Step 7: Commit**

```bash
git add scripts/ongoing_bidder_capture.py scripts/test_ongoing_run.py
git commit -m "feat(capture): run_live/run_cgd loops + main CLI + Discord summary (API-only pacing)"
```

---

## Task 6: systemd timer + service (deploy artifacts)

**Files:**
- Create: `deploy/systemd/bms-ongoing-bidder-capture.service`
- Create: `deploy/systemd/bms-ongoing-bidder-capture.timer`

**Interfaces:** mirror `bms-backfill-bidders.{service,timer}` (รูปแบบเดียวกัน)

- [ ] **Step 1: Create service unit**

```ini
# deploy/systemd/bms-ongoing-bidder-capture.service
[Unit]
Description=BMS ongoing bidder capture (going-forward, นครพนม+บึงกาฬ, ทุก proc_type)
After=network-online.target

[Service]
Type=oneshot
User=bms
WorkingDirectory=/opt/bms/app
Environment=BMS_DATA_DIR=/opt/bms/data
EnvironmentFile=/opt/bms/app/.env
ExecStart=/opt/bms/venv/bin/python /opt/bms/app/scripts/ongoing_bidder_capture.py
Nice=10
TimeoutStartSec=1800
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 2: Create timer unit**

```ini
# deploy/systemd/bms-ongoing-bidder-capture.timer
[Unit]
Description=BMS ongoing bidder capture daily

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
Unit=bms-ongoing-bidder-capture.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Commit**

```bash
git add deploy/systemd/bms-ongoing-bidder-capture.service deploy/systemd/bms-ongoing-bidder-capture.timer
git commit -m "deploy(capture): systemd timer 03:00 daily for ongoing bidder capture"
```

---

## Deploy & Verify (manual — หลัง implement เสร็จ, ทำตอน confirm push)

> ห้าม push/deploy โดยไม่ confirm กับคุณกัญจน์ (CLAUDE.md). ขั้นตอนเมื่อ approve:

1. `git push origin main`
2. VPS: `cd /opt/bms/app && git pull --ff-only`
3. migrate: `sudo -u bms BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "import sys;sys.path.insert(0,'/opt/bms/app/scripts');import Sebastian_Customer_DB as db;db.init_schema()"` → ยืนยัน `source` column
4. dry-run บน VPS: `sudo -u bms BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python /opt/bms/app/scripts/ongoing_bidder_capture.py --dry-run` → ดู candidate count สมเหตุผล (live น้อย, cgd อาจ 0 ช่วงแรกเพราะ epoch_fy ยังไม่มีใน CGD)
5. install timer: copy unit → `/etc/systemd/system/`, `systemctl daemon-reload`, `systemctl enable --now bms-ongoing-bidder-capture.timer`
6. dispatch **Sophia** ตรวจ bid_results sanity (source distribution, duplicate, idempotent) → verdict SAFE/STOP
7. progress_log N+174 → DEPLOYED + Discord notify

---

## Self-Review (ผู้เขียน plan ตรวจแล้ว)

- **Spec coverage:** Pass 1 (Task 4) · Pass 2 + copy เจาะจง (Task 3) · source column (Task 1) · epoch floor (Task 2: epoch_date+epoch_fy) · idempotency NOT IN bid_results + INSERT OR REPLACE (Task 3-5) · scheduling/coexist (Task 6) · Discord (Task 5) — ครบ
- **Spec deviation (ตั้งใจ):** spec §5 ระบุ Pass 2 floor = announce_date — เปลี่ยนเป็น `fiscal_year >= epoch_fy` เพราะ announce_date เป็น Thai date เทียบ ISO ไม่ได้ (robust กว่า + กัน full-re-push). อัปเดต spec §5 ควบคู่
- **Placeholder scan:** ไม่มี TBD/TODO — โค้ดเต็มทุก step
- **Type consistency:** `record_bid_results(..., source=)`, `capture_cgd_one` คืน copied/stored/empty/error, `capture_live_one` คืน stored/empty/error, `select_*` คืน list — สอดคล้องทุก task
