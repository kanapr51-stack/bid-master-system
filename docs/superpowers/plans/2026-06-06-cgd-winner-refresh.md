# CGD Winner Refresh Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development หรือ superpowers:executing-plans. Steps ใช้ checkbox (`- [ ]`).

**Goal:** ดึง winner ทุกงานจาก CGD (residential node) แบบ incremental → keep winner_history.db สด (ถึง FY2569) + sync subset เป้าหมาย → VPS

**Architecture:** residential node (เครื่องบ้าน→อนาคต mini PC x86) รัน CGD pull (residential IP ผ่าน) → upsert winner_history.db (full, analysis ที่นี่) → scp subset (นครพนม+บึงกาฬ) → VPS table cgd_winners (app). OS-agnostic core + scheduler แยก.

**Tech Stack:** Python (requests, sqlite3), CKAN datastore API, scp. reuse `_winner_history_build` (schema/row_from_rec) + `cgd_discovery._cgd_search`.

**Spec:** `docs/superpowers/specs/2026-06-06-cgd-winner-refresh-design.md`

**Runtime:** **เครื่องบ้าน (residential)** — CGD 403 จาก VPS. test: `BMS_ENV=dev python scripts/test_*.py`. ⚠️ Phase 1 ดึงจริงต้องรันบนเครื่องบ้าน (มี OPEND_USER_TOKEN ใน .env).

---

## File Structure
- `scripts/cgd_resource_catalog.py` (ใหม่) — map ปี→resource_id ผ่าน CKAN package_search (แทน hardcode)
- `scripts/cgd_winner_refresh.py` (ใหม่, OS-agnostic) — incremental pull + upsert winner_history.db
- `scripts/cgd_freshness.py` (ใหม่) — รายงาน max announce_date + count/ปี (วัด lag จริง) + Thai-date parser
- `scripts/cgd_sync_to_vps.py` (ใหม่) — extract subset → scp → VPS merge
- `scripts/Sebastian_Customer_DB.py` (แก้) — migrate cgd_winners table (ฝั่ง VPS)
- tests: `test_cgd_resource_catalog.py`, `test_cgd_winner_refresh.py`, `test_cgd_freshness.py`, `test_cgd_sync.py`

---

# PHASE 1 — refresh winner_history.db ให้ถึง FY2569 (เครื่องบ้าน)

## Task 1.1: cgd_resource_catalog — หา resource_id ตามปี

**Files:** Create `scripts/cgd_resource_catalog.py` · Test `scripts/test_cgd_resource_catalog.py`

- [ ] **Step 1: Write failing test** (inject CKAN search → ไม่ยิงเน็ตจริง)
```python
"""test_cgd_resource_catalog.py — map ปี→resource_id จาก CKAN package."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_resource_catalog as cat

# fake CKAN package_show payload: 1 package มีหลาย resource (ต่อปี)
FAKE_PKG = {"result": {"resources": [
    {"id": "rid-2568", "name": "ข้อมูลจัดซื้อจัดจ้าง ปีงบประมาณ 2568"},
    {"id": "rid-2569", "name": "ข้อมูลจัดซื้อจัดจ้าง ปีงบประมาณ 2569"},
]}}
rid = cat.resource_id_for_year("2569", fetch=lambda pkg_id: FAKE_PKG)
assert rid == "rid-2569", rid
rid68 = cat.resource_id_for_year("2568", fetch=lambda pkg_id: FAKE_PKG)
assert rid68 == "rid-2568", rid68
# ไม่เจอปี → None
assert cat.resource_id_for_year("2570", fetch=lambda pkg_id: FAKE_PKG) is None
print("✅ PASS cgd_resource_catalog")
```

- [ ] **Step 2: Run → FAIL** — `BMS_ENV=dev python scripts/test_cgd_resource_catalog.py` → ModuleNotFoundError

- [ ] **Step 3: Implement**
```python
"""cgd_resource_catalog.py — map ปีงบ → CKAN resource_id (แทน hardcode CGD_CONTRACT_RIDS).
ดึงรายการ resource จาก package เดียว (CGD เผยแพร่ resource ต่อปีใน package เดียว)."""
import os
import requests

CKAN_BASE = "https://opend.data.go.th/get-ckan"
# package id ของชุด "ข้อมูลจัดซื้อจัดจ้าง" CGD (ยืนยันใน Task 1.4 ด้วย package_search)
CGD_PACKAGE_ID = os.environ.get("CGD_PACKAGE_ID", "")


def _fetch_package(pkg_id: str) -> dict:
    tok = os.environ.get("OPEND_USER_TOKEN", "")
    r = requests.get(f"{CKAN_BASE}/package_show", params={"id": pkg_id},
                     headers={"api-key": tok, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def resource_id_for_year(year: str, pkg_id: str = None, fetch=None) -> str | None:
    """คืน resource_id ที่ชื่อมีปีงบ `year` (เช่น '2569'). fetch inject ได้สำหรับ test."""
    fetch = fetch or _fetch_package
    pkg_id = pkg_id or CGD_PACKAGE_ID
    data = fetch(pkg_id)
    for res in (data.get("result", {}) or {}).get("resources", []) or []:
        if year in (res.get("name") or ""):
            return res.get("id")
    return None
```

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `git commit -m "feat(cgd): resource_id_for_year catalog (Phase 1 Task 1.1)"`

## Task 1.2: cgd_winner_refresh — incremental pull + upsert

**Files:** Create `scripts/cgd_winner_refresh.py` · Test `scripts/test_cgd_winner_refresh.py`

- [ ] **Step 1: Write failing test** (inject search → fake CGD records; reuse winner_history schema)
```python
"""test_cgd_winner_refresh.py — incremental upsert winner_history (dedup project_id)."""
import os, tempfile, sys, sqlite3
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_winner_refresh as wr

DB = str(Path(os.environ["BMS_DATA_DIR"]) / "wh_test.db")

def rec(pid, prov, name):
    return {"รหัสโครงการ": pid, "ปีงบประมาณ": "2569", "จังหวัด": prov,
            "ชื่อโครงการ": name, "ชื่อหน่วยงาน": "อบต.x", "วิธีจัดซื้อฯ": "e-bidding",
            "ราคากลาง(บาท)": "1000000", "ราคาตกลงซื้อ/จ้าง": "950000",
            "งบประมาณ(บาท)": "1100000", "วันที่ประกาศ": "9-เม.ย.-69",
            "ผู้เสนอราคาที่ชนะการเสนอราคา": "บ.A"}

# รอบ 1: 2 records → insert 2
calls = {"n": 0}
def fake_search(rid, province, limit, offset):
    if offset > 0: return {"result": {"records": [], "total": 2}}
    return {"result": {"records": [rec("P1", province, "ถนน"), rec("P2", province, "อาคาร")], "total": 2}}

n1 = wr.refresh_year(DB, "2569", "rid-x", ["นครพนม"], search=fake_search)
assert n1 == 2, n1
c = sqlite3.connect(DB)
assert c.execute("SELECT COUNT(*) FROM winner_history").fetchone()[0] == 2
assert c.execute("SELECT win_price FROM winner_history WHERE project_id='P1'").fetchone()[0] == 950000
c.close()

# รอบ 2: records เดิม → INSERT OR IGNORE → ไม่เพิ่ม (idempotent)
n2 = wr.refresh_year(DB, "2569", "rid-x", ["นครพนม"], search=fake_search)
c = sqlite3.connect(DB)
assert c.execute("SELECT COUNT(*) FROM winner_history").fetchone()[0] == 2, "idempotent fail"
c.close()
print("✅ PASS cgd_winner_refresh")
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement** (reuse schema + row_from_rec จาก _winner_history_build)
```python
"""cgd_winner_refresh.py — pull CGD ต่อปี/จังหวัด แบบ incremental → upsert winner_history.db.
OS-agnostic (requests + sqlite3). reuse schema/row_from_rec จาก _winner_history_build.
incremental = INSERT OR IGNORE (project_id PK) + หยุดเมื่อทั้งหน้าซ้ำหมด."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import _winner_history_build as whb
from cgd_discovery import _cgd_search

PAGE = 1000


def refresh_year(db_path: str, year: str, rid: str, provinces: list, search=None) -> int:
    """ดึงทุกจังหวัดใน provinces สำหรับปี/resource นี้ → upsert. คืนจำนวน row ใหม่."""
    search = search or _cgd_search
    conn = _open_db(db_path)   # พก schema เอง (ไม่ผูก DB path คงที่ของ _winner_history_build)
    ph = ",".join("?" * len(whb.COLS.split(",")))
    new = 0
    try:
        for prov in provinces:
            offset = 0
            while True:
                res = search(rid, prov, PAGE, offset)
                recs = ((res or {}).get("result", {}) or {}).get("records", []) or []
                if not recs:
                    break
                rows = [whb.row_from_rec(r, year) for r in recs
                        if str(r.get("รหัสโครงการ") or "").strip()]
                before = conn.total_changes
                conn.executemany(f"INSERT OR IGNORE INTO winner_history ({whb.COLS}) VALUES ({ph})", rows)
                new += conn.total_changes - before
                offset += PAGE
        conn.commit()
    finally:
        conn.close()
    return new


def _open_db(db_path: str) -> sqlite3.Connection:
    """สร้าง winner_history schema ที่ db_path (กรณี _winner_history_build ไม่มี helper แยก path)."""
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS winner_history (
        project_id TEXT PRIMARY KEY, fiscal_year TEXT, province TEXT, district TEXT,
        subdistrict TEXT, project_name TEXT, dept TEXT, proc_type TEXT, winner TEXT,
        winner_tin TEXT, budget INTEGER, mid_price INTEGER, win_price INTEGER,
        discount_pct REAL, price_valid INTEGER, announce_date TEXT, contract_no TEXT,
        sign_date TEXT, status TEXT, source TEXT, raw_json TEXT)""")
    conn.commit()
    return conn
```
> หมายเหตุ implementer: ใช้ `_open_db` (พกพา schema เอง) เพื่อไม่ผูกกับ DB path คงที่ของ `_winner_history_build`. `row_from_rec` + `COLS` reuse ได้ตรงๆ.

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `feat(cgd): cgd_winner_refresh incremental upsert (Task 1.2)`

## Task 1.3: cgd_freshness — วัด lag จริง + Thai-date parser

**Files:** Create `scripts/cgd_freshness.py` · Test `scripts/test_cgd_freshness.py`

- [ ] **Step 1: Write failing test**
```python
"""test_cgd_freshness.py — parse Thai date + รายงาน max date/ปี."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
from cgd_freshness import parse_thai_date
import datetime as dt
assert parse_thai_date("9-เม.ย.-69") == dt.date(2026, 4, 9), parse_thai_date("9-เม.ย.-69")
assert parse_thai_date("15-ม.ค.-68") == dt.date(2025, 1, 15)
assert parse_thai_date("-") is None
assert parse_thai_date("") is None
print("✅ PASS cgd_freshness parser")
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement**
```python
"""cgd_freshness.py — วัดความสด winner_history (max announce_date/ปี) → ตอบ 'CGD lag กี่วัน'."""
import datetime as _dt
import sqlite3
import sys
from pathlib import Path

_TH_MONTH = {"ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
             "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12}


def parse_thai_date(s: str):
    """'9-เม.ย.-69' → date(2026,4,9). ปีเป็น พ.ศ. 2 หลัก (69=2569=2026 ค.ศ.). คืน None ถ้า parse ไม่ได้."""
    s = (s or "").strip()
    if not s or s == "-":
        return None
    try:
        d, mon, yy = s.split("-")
        m = _TH_MONTH.get(mon.strip())
        if not m:
            return None
        year_ce = 2500 + int(yy) - 543  # 69 → 2569 พ.ศ. → 2026 ค.ศ.
        return _dt.date(year_ce, m, int(d))
    except (ValueError, KeyError):
        return None


def report(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    out = {}
    for fy, n in conn.execute("SELECT fiscal_year, COUNT(*) FROM winner_history GROUP BY fiscal_year"):
        out[fy] = {"count": n}
    # max announce_date (parse Thai) ของปีล่าสุด
    latest = None
    for (ad,) in conn.execute("SELECT announce_date FROM winner_history WHERE fiscal_year='2569'"):
        d = parse_thai_date(ad)
        if d and (latest is None or d > latest):
            latest = d
    conn.close()
    out["latest_2569"] = latest.isoformat() if latest else None
    if latest:
        out["lag_days"] = (_dt.date.today() - latest).days
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import os
    db = str(Path(os.environ.get("BMS_DATA_DIR", "data")) / "winner_history.db")
    if not Path(db).exists():
        db = "data/winner_history.db"
    print(report(db))
```

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `feat(cgd): cgd_freshness lag measure + Thai-date parser (Task 1.3)`

## Task 1.4: main() + RUN จริงบนเครื่องบ้าน (FY2569) + วัด lag

**Files:** Modify `scripts/cgd_winner_refresh.py` (เพิ่ม main)

- [ ] **Step 1:** เพิ่ม `main()`: load .env (OPEND_USER_TOKEN) → `resource_id_for_year("2569")` → ถ้าได้ rid: `refresh_year(db, "2569", rid, ["นครพนม","บึงกาฬ"])` → print count + `cgd_freshness.report(db)`
- [ ] **Step 2:** หา `CGD_PACKAGE_ID` จริง — รันบนเครื่องบ้าน: CKAN `package_search?q=จัดซื้อจัดจ้าง` → หา package ที่มี resource รายปี → set ใน .env. **ถ้าไม่มี dataset 2569** → log ชัด + รายงานกัญจน์ (อาจ CGD ยังไม่ publish 2569)
- [ ] **Step 3:** RUN จริง (เครื่องบ้าน): `python scripts/cgd_winner_refresh.py` → ดูว่าเติม FY2569 เข้า winner_history.db ได้กี่งาน + lag_days เท่าไหร่
- [ ] **Step 4:** บันทึกผล (count 2569 + lag จริง) ใน progress_log + commit. **รายงานกัญจน์: "CGD lag = X วัน"**

**✅ EXIT Phase 1:** winner_history.db มี FY2569 + รู้ lag จริง + analytics เดิม (work-type/competitor) จะสดขึ้นอัตโนมัติ

---

# PHASE 2 — sync subset → VPS (ป้อน competitive intel)

## Task 2.1: VPS cgd_winners table

**Files:** Modify `scripts/Sebastian_Customer_DB.py` (migrate v119)

- [ ] **Step 1:** เพิ่ม `_migrate_v119()` + เรียกใน init_schema chain:
```python
def _migrate_v119():
    """cgd_winners — subset ผู้ชนะพื้นที่เป้าหมายจาก CGD (sync จาก residential node) สำหรับ app."""
    with get_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS cgd_winners (
            project_id TEXT PRIMARY KEY, province TEXT, dept TEXT, project_name TEXT,
            winner TEXT, winner_tin TEXT, budget INTEGER, win_price INTEGER,
            discount_pct REAL, announce_date TEXT, fiscal_year TEXT, synced_at TEXT)""")
```
- [ ] **Step 2:** test (เพิ่มใน test_cgd_sync.py Step ถัดไป — verify table สร้าง + upsert) · **Commit**

## Task 2.2: cgd_sync_to_vps — extract subset + merge

**Files:** Create `scripts/cgd_sync_to_vps.py` · Test `scripts/test_cgd_sync.py`

- [ ] **Step 1: Write failing test** (test ตัว merge — รับ list → upsert cgd_winners idempotent)
```python
"""test_cgd_sync.py — merge subset เข้า cgd_winners (idempotent)."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db; db.init_schema()
import cgd_sync_to_vps as sy

rows = [{"project_id": "P1", "province": "นครพนม", "dept": "อบต.x", "project_name": "ถนน",
         "winner": "บ.A", "winner_tin": "1", "budget": 1100000, "win_price": 950000,
         "discount_pct": 5.0, "announce_date": "9-เม.ย.-69", "fiscal_year": "2569"}]
n = sy.merge_winners(rows, now="2026-06-06T00:00:00")
assert n == 1, n
got = sy.get_cgd_winners("นครพนม")
assert len(got) == 1 and got[0]["winner"] == "บ.A", got
sy.merge_winners(rows, now="2026-06-07T00:00:00")  # idempotent
assert len(sy.get_cgd_winners("นครพนม")) == 1
print("✅ PASS cgd_sync merge")
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement** (merge + extract; scp เป็น CLI orchestration)
```python
"""cgd_sync_to_vps.py — extract subset เป้าหมายจาก winner_history → scp → VPS merge.
merge_winners() = ฝั่ง VPS (idempotent upsert). extract+scp = orchestration ใน main()."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import get_connection, _now

TARGET = ["นครพนม", "บึงกาฬ"]


def merge_winners(rows: list, now: str = None) -> int:
    """upsert cgd_winners (idempotent ตาม project_id). ใช้ทั้งฝั่ง VPS รับ + test."""
    now = now or _now()
    n = 0
    with get_connection() as conn:
        for r in rows:
            conn.execute("""INSERT OR REPLACE INTO cgd_winners
                (project_id, province, dept, project_name, winner, winner_tin, budget,
                 win_price, discount_pct, announce_date, fiscal_year, synced_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["project_id"], r.get("province"), r.get("dept"), r.get("project_name"),
                 r.get("winner"), r.get("winner_tin"), r.get("budget"), r.get("win_price"),
                 r.get("discount_pct"), r.get("announce_date"), r.get("fiscal_year"), now))
            n += 1
    return n


def get_cgd_winners(province: str) -> list[dict]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cgd_winners WHERE province=? ORDER BY announce_date DESC", (province,))]


def extract_subset(wh_db_path: str, provinces=TARGET) -> list[dict]:
    """ดึง subset เป้าหมายจาก winner_history (บน residential node) เป็น list[dict] เพื่อส่ง VPS."""
    conn = sqlite3.connect(wh_db_path); conn.row_factory = sqlite3.Row
    qs = ",".join("?" * len(provinces))
    rows = [dict(r) for r in conn.execute(
        f"SELECT project_id, province, dept, project_name, winner, winner_tin, budget, "
        f"win_price, discount_pct, announce_date, fiscal_year FROM winner_history "
        f"WHERE province IN ({qs})", provinces)]
    conn.close()
    return rows
```
> orchestration (main): extract_subset → เขียนเป็น .jsonl → `scp` ไป VPS → VPS รัน merge (อ่าน jsonl → merge_winners). scp pattern เดียวกับ `harvest_and_push.py`.

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `feat(cgd): cgd_sync_to_vps merge + extract subset (Task 2.2)`

## Task 2.3: orchestration + scheduler

**Files:** Modify `cgd_sync_to_vps.py` (main: extract→jsonl→scp→ssh merge) · `deploy/runbooks/cgd-refresh.md` (ใหม่)

- [ ] **Step 1:** main(): extract_subset → write `data/cgd_subset.jsonl` → `scp` ไป VPS → `ssh ... python -c "merge from jsonl"`. reuse host/key จาก harvest_and_push
- [ ] **Step 2:** runbook `deploy/runbooks/cgd-refresh.md`: วิธี schedule บน **เครื่องบ้าน** (Windows Task เพิ่มบรรทัด refresh+sync รายวัน) + วิธีย้ายลง **mini PC/RPi** (cron line) — scheduler แยกจาก logic
- [ ] **Step 3:** Commit

**✅ EXIT Phase 2:** VPS มี cgd_winners (target subset) สด → พร้อมป้อน feature competitive intel ใน LINE

---

## Definition of Done
- [ ] winner_history.db มี FY2569 (refresh จากเครื่องบ้าน) + รู้ lag จริง
- [ ] analytics เดิมสดขึ้น (reuse)
- [ ] VPS cgd_winners table + sync subset ทำงาน (scp incremental)
- [ ] core เป็น Python ล้วน (รันได้ทั้ง Windows/mini PC/RPi) + scheduler แยก
- [ ] test ทุก unit เขียว · incremental idempotent (INSERT OR IGNORE/REPLACE)

## Rollback
Phase 1 = winner_history.db เพิ่ม row เฉยๆ (ไม่ลบของเดิม) — ปลอดภัย, หยุด refresh ได้. Phase 2 = drop cgd_winners + หยุด sync. ไม่กระทบ Follow/Winner Poller (คนละตาราง).

## Open item (Task 1.4 Step 2)
ยืนยัน CGD มี dataset FY2569 จริง + `CGD_PACKAGE_ID` — ถ้าไม่มี → CGD ยังไม่ publish 2569 → fall back: ใช้ eGP สำหรับ 2569 (แต่ rate-limit) หรือรอ CGD
