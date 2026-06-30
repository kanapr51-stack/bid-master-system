# Portal Discovery "งานใหม่ที่แมตช์" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่ม section "งานใหม่ที่แมตช์" บนบอร์ด `/portal/world` ที่กรองงานจาก `projects_seen` ตาม keyword+พื้นที่+งบ ราย user แล้วให้กด "ติดตาม" ดึงเข้า `followed_jobs` ได้

**Architecture:** โมดูล matching แยก (`discovery_match.py`, pure) + 2 endpoint บน `bms_api` (GET discover, POST follow) + section UI ใหม่บน Next.js. Read-only/additive ทั้งหมด — **ไม่แตะ `config/matching_preferences.json` หรือ LINE pipeline** (per-user matching เกิดใน discovery query เท่านั้น)

**Tech Stack:** Python (FastAPI, sqlite3, asyncio) ฝั่ง engine; Next.js (App Router, TypeScript) ฝั่งเว็บ. Tests = plain scripts (`python scripts/test_x.py`, scratch DB copy + asyncio direct call, `print("PASS")`)

## Global Constraints

- **ห้ามแตะ prod DB ในเทสต์** — copy ไป scratch dir + `BMS_DATA_DIR`/`BMS_DB_PATH` (ดู pattern `scripts/test_portal_jobs_api.py`)
- **ห้ามแก้** `config/matching_preferences.json`, `job_matcher.match_job`, LINE pipeline, หรือ logic ที่ส่ง LINE notification
- Endpoint ใหม่ใช้ guard เดียวกับเดิม: `if x_bms_secret != BMS_INTERNAL_SECRET: raise HTTPException(403)`
- JSON field = **snake_case** (ตรง Phase 1: `project_id`, `deadline_time`, `matched_keywords`)
- deadline เก็บเป็น ISO `YYYY-MM-DD` (Gregorian) — string-comparable กับ `date.today().isoformat()`
- ฝั่งเว็บ: อ่าน `node_modules/next/dist/docs/` ที่เกี่ยวข้องก่อนเขียน (per `dashboard/web/AGENTS.md` — Next.js version นี้มี breaking changes)
- commit เล็ก บ่อย; secret ไม่ออก client (fetch ฝั่ง server/route handler)

---

## File Structure

- **Create** `scripts/discovery_match.py` — pure matching function (province AND, keyword OR + guards, negative, budget). reuse `job_matcher._kw_hit`
- **Create** `scripts/test_discovery_match.py` — unit test (pure)
- **Create** `scripts/test_classes_from_notes.py` — unit test helper
- **Create** `scripts/test_portal_discover_api.py` — endpoint test (scratch DB)
- **Create** `scripts/test_portal_follow_api.py` — endpoint test (scratch DB)
- **Modify** `scripts/bms_api.py` — เพิ่ม `_classes_from_notes`, `_job_location_deadline` (extract จาก `_portal_jobs`), `GET /api/portal/discover`, `POST /api/portal/follow`
- **Modify** `dashboard/web/src/lib/portal-jobs.ts` — `DiscoverJob` type + `getDiscoverJobs()`
- **Create** `dashboard/web/src/app/api/portal/follow/route.ts` — relay session→engine
- **Modify** `dashboard/web/src/app/portal/world/page.tsx` — fetch discover server-side
- **Modify** `dashboard/web/src/app/portal/world/_client.tsx` — section "งานใหม่ที่แมตช์" + DiscoverCard + handleFollow

---

### Task 1: โมดูล `discovery_match.py` (pure matching)

**Files:**
- Create: `scripts/discovery_match.py`
- Test: `scripts/test_discovery_match.py`

**Interfaces:**
- Consumes: `job_matcher._kw_hit(k, name)`, `job_matcher.load_config()`, `text_normalize.normalize_thai`
- Produces: `discovery_match.match(project_name, project_province, project_budget, user_provinces, user_keywords, budget_min=0, budget_max=0, neg_keywords=None) -> tuple[bool, list[str]]`

- [ ] **Step 1: Write the failing test** — `scripts/test_discovery_match.py`

```python
"""test_discovery_match.py — pure per-user matching for board discovery."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discovery_match as dm


def t(name, prov, budget, provs, kws, bmin=0, bmax=0, neg=None):
    return dm.match(name, prov, budget, provs, kws, bmin, bmax, neg if neg is not None else [])


# keyword OR + province AND → match + คืนคำที่โดน
ok, hits = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 1000000, ["นครพนม"], ["คอนกรีต", "ท่อ"])
assert ok and hits == ["คอนกรีต"], (ok, hits)

# province ไม่อยู่ใน subscribe → ตัด
ok, _ = t("ก่อสร้างถนนคอนกรีต", "ชลบุรี", 1000000, ["นครพนม"], ["คอนกรีต"])
assert not ok, "province ไม่ตรงต้องตัด"

# ไม่มี keyword โดน → ตัด
ok, _ = t("ซื้อเวชภัณฑ์", "นครพนม", 1000000, ["นครพนม"], ["คอนกรีต"])
assert not ok, "ไม่มี keyword ต้องตัด"

# guard: "ท่อ" ห้ามชน "ท่องเที่ยว"
ok, _ = t("ส่งเสริมการท่องเที่ยว", "นครพนม", 1000000, ["นครพนม"], ["ท่อ"])
assert not ok, "ท่อ ต้องไม่ชน ท่องเที่ยว"
# แต่ "ท่อระบายน้ำ" ต้องโดน
ok, hits = t("วางท่อระบายน้ำ", "นครพนม", 1000000, ["นครพนม"], ["ท่อ"])
assert ok and hits == ["ท่อ"], (ok, hits)

# budget range: ต่ำกว่า min → ตัด, สูงกว่า max → ตัด
ok, _ = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 500000, ["นครพนม"], ["คอนกรีต"], 1000000, 0)
assert not ok, "ต่ำกว่า budget_min ต้องตัด"
ok, _ = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 99000000, ["นครพนม"], ["คอนกรีต"], 0, 20000000)
assert not ok, "สูงกว่า budget_max ต้องตัด"

# budget=0 (ไม่รู้ราคากลาง) → ไม่ตัด แม้ตั้งช่วงงบ
ok, _ = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 0, ["นครพนม"], ["คอนกรีต"], 1000000, 20000000)
assert ok, "budget=0 ต้องผ่าน"

# negative safety net → ตัด
ok, _ = t("ก่อสร้างถนนคอนกรีต ครุภัณฑ์", "นครพนม", 1000000, ["นครพนม"], ["คอนกรีต"], neg=["ครุภัณฑ์"])
assert not ok, "negative ต้องตัด"

print("PASS test_discovery_match")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_discovery_match.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery_match'`

- [ ] **Step 3: Write minimal implementation** — `scripts/discovery_match.py`

```python
"""discovery_match.py — per-user matching สำหรับ section discovery บนบอร์ด.

Pure function: ตัดสินว่า project 1 row match preference ของ user 1 คนไหม + คืนคำที่โดน.
ไม่แตะ DB / ไม่เรียก API. reuse keyword guard จาก job_matcher (ไม่เขียน guard ซ้ำ).
SCOPE: board discovery เท่านั้น — แยกจาก LINE pipeline (job_matcher.match_job ไม่ถูกแตะ).
ดู spec: docs/superpowers/specs/2026-06-30-portal-discovery-design.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_normalize import normalize_thai  # noqa: E402
import job_matcher  # noqa: E402


def match(project_name, project_province, project_budget,
          user_provinces, user_keywords,
          budget_min=0, budget_max=0, neg_keywords=None):
    """คืน (matched: bool, matched_keywords: list[str]).

    - province AND: project_province ต้องอยู่ใน user_provinces
    - negative safety net: ชื่อมี neg_keyword ใด → ไม่ match
    - keyword OR: คำใน user_keywords ที่ _kw_hit(k, ชื่อ normalize) → เก็บใน matched_keywords
    - budget: budget>0 + นอกช่วง [budget_min, budget_max] → ตัด (budget=0 = ไม่รู้ → ผ่าน)
    matched = province✓ AND keyword≥1 AND ไม่ติด negative AND อยู่ในช่วงงบ
    """
    name = normalize_thai(project_name or "")
    prov = (project_province or "").strip()

    if prov not in set(user_provinces or []):
        return False, []

    if neg_keywords is None:
        neg_keywords = job_matcher.load_config().get("negative_keywords", [])
    if any(n in name for n in neg_keywords):
        return False, []

    hits = [k for k in (user_keywords or []) if k and job_matcher._kw_hit(k, name)]
    if not hits:
        return False, []

    b = project_budget or 0
    if b > 0:
        if budget_min and b < budget_min:
            return False, []
        if budget_max and b > budget_max:
            return False, []

    return True, hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_discovery_match.py`
Expected: `PASS test_discovery_match`

- [ ] **Step 5: Commit**

```bash
git add scripts/discovery_match.py scripts/test_discovery_match.py
git commit -m "feat(discovery): discovery_match pure matcher (province+keyword+budget+negative)"
```

---

### Task 2: helper `_classes_from_notes` ใน bms_api

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่มฟังก์ชันถัดจาก `_provinces_from_notes`, ~line 1433)
- Test: `scripts/test_classes_from_notes.py`

**Interfaces:**
- Produces: `bms_api._classes_from_notes(notes_str: str) -> dict` คืน `{"keywords": list[str], "budget_min": int, "budget_max": int}`

- [ ] **Step 1: Write the failing test** — `scripts/test_classes_from_notes.py`

```python
"""test_classes_from_notes.py — รวม keyword/งบ ราย user จาก notes.classes[]."""
import os, sys, json, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import bms_api

# union keywords (+defaultKeywords) unique, budget_min=min(>0), budget_max=max(>0)
notes = json.dumps({"classes": [
    {"keywords": ["คอนกรีต", "ท่อ"], "defaultKeywords": ["ถนน"], "budgetMinBaht": 1000000, "budgetMaxBaht": 20000000},
    {"keywords": ["ท่อ", "ราง"], "budgetMinBaht": 500000, "budgetMaxBaht": 50000000},
]})
r = bms_api._classes_from_notes(notes)
assert r["keywords"] == ["คอนกรีต", "ท่อ", "ถนน", "ราง"], r["keywords"]
assert r["budget_min"] == 500000, r["budget_min"]
assert r["budget_max"] == 50000000, r["budget_max"]

# notes ว่าง / พังต้องไม่ระเบิด
assert bms_api._classes_from_notes("") == {"keywords": [], "budget_min": 0, "budget_max": 0}
assert bms_api._classes_from_notes("not json") == {"keywords": [], "budget_min": 0, "budget_max": 0}

# ไม่มี budget → 0
r2 = bms_api._classes_from_notes(json.dumps({"classes": [{"keywords": ["ถนน"]}]}))
assert r2["budget_min"] == 0 and r2["budget_max"] == 0 and r2["keywords"] == ["ถนน"], r2

print("PASS test_classes_from_notes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_classes_from_notes.py`
Expected: FAIL — `AttributeError: module 'bms_api' has no attribute '_classes_from_notes'`

- [ ] **Step 3: Write minimal implementation** — เพิ่มหลัง `_provinces_from_notes` ใน `scripts/bms_api.py`

```python
def _classes_from_notes(notes_str: str) -> dict:
    """รวม preference ราย user จาก notes.classes[] → {keywords, budget_min, budget_max}.
    keywords = union ของ classes[].keywords + defaultKeywords (unique, รักษาลำดับ);
    budget_min = min ของ budgetMinBaht ที่ >0; budget_max = max ของ budgetMaxBaht ที่ >0.
    provinces ไม่ดึงที่นี่ — ใช้ subscription_provinces (source of truth) แทน."""
    out = {"keywords": [], "budget_min": 0, "budget_max": 0}
    if not notes_str:
        return out
    try:
        data = json.loads(notes_str)
    except (ValueError, TypeError):
        return out
    kws, mins, maxs = [], [], []
    for cls in (data.get("classes") or []):
        for k in list(cls.get("keywords") or []) + list(cls.get("defaultKeywords") or []):
            k = (k or "").strip()
            if k and k not in kws:
                kws.append(k)
        bmin, bmax = cls.get("budgetMinBaht"), cls.get("budgetMaxBaht")
        if isinstance(bmin, (int, float)) and bmin > 0:
            mins.append(int(bmin))
        if isinstance(bmax, (int, float)) and bmax > 0:
            maxs.append(int(bmax))
    out["keywords"] = kws
    out["budget_min"] = min(mins) if mins else 0
    out["budget_max"] = max(maxs) if maxs else 0
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_classes_from_notes.py`
Expected: `PASS test_classes_from_notes`

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_classes_from_notes.py
git commit -m "feat(discovery): _classes_from_notes helper (รวม keyword/งบ ราย user)"
```

---

### Task 3: extract `_job_location_deadline` + `GET /api/portal/discover`

**Files:**
- Modify: `scripts/bms_api.py` (extract helper จาก `_portal_jobs` ~line 414-445; เพิ่ม endpoint ถัดจาก `portal_get_jobs` ~line 1558)
- Test: `scripts/test_portal_discover_api.py`

**Interfaces:**
- Consumes: `discovery_match.match`, `_classes_from_notes`, `job_matcher.load_config`, `job_matcher.tor_is_fresh`
- Produces:
  - `bms_api._job_location_deadline(conn, pid: str, prov: str) -> tuple[str, str, str]` คืน `(location, deadline, deadline_time)`
  - `bms_api.portal_discover_jobs(line_user_id, x_bms_secret)` (async) คืน `{"ok": True, "jobs": {"biddable": [...], "planning": [...]}}`; การ์ด = `{project_id, name, location, province, deadline, deadline_time, budget, matched_keywords, stage}`

- [ ] **Step 1: Write the failing test** — `scripts/test_portal_discover_api.py`

```python
"""test_portal_discover_api.py — GET /api/portal/discover (per-user matching, ตัด followed)."""
import os, sys, json, sqlite3, asyncio, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException

FUTURE = "2099-12-31"   # deadline ยังไม่หมด
FRESH = bms_api._now()  # B0 first_seen วันนี้ → tor_is_fresh ผ่าน


def setup():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at,notes) "
              "VALUES ('UDISC','x','trial',1,?,?,?)",
              (FRESH, FRESH, json.dumps({"classes": [{"keywords": ["คอนกรีต", "ท่อ"], "budgetMinBaht": 1000000, "budgetMaxBaht": 50000000}]})))
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='UDISC'").fetchone()[0]
    c.execute("INSERT OR IGNORE INTO subscriptions (customer_id,active,created_at,updated_at) VALUES (?,1,?,?)", (cid, FRESH, FRESH))
    sid = c.execute("SELECT id FROM subscriptions WHERE customer_id=?", (cid,)).fetchone()[0]
    c.execute("INSERT OR IGNORE INTO subscription_provinces (subscription_id,province) VALUES (?,'นครพนม')", (sid,))
    # งานในพื้นที่ + keyword + งบ → ควรเข้า
    rows = [
        ('D_MATCH', 'D0', 'นครพนม', 5000000, 'ก่อสร้างถนนคอนกรีตสาย 1'),     # biddable
        ('D_FOLLOWED', 'D0', 'นครพนม', 5000000, 'วางท่อระบายน้ำคอนกรีต'),     # ตาม followed แล้ว → ตัด
        ('D_OTHERPROV', 'D0', 'ชลบุรี', 5000000, 'ก่อสร้างถนนคอนกรีต'),       # นอกพื้นที่ → ตัด
        ('D_NOKW', 'D0', 'นครพนม', 5000000, 'ซื้อเวชภัณฑ์'),                  # ไม่มี keyword → ตัด
        ('D_LOWBUDGET', 'D0', 'นครพนม', 100000, 'ก่อสร้างถนนคอนกรีต'),        # ต่ำกว่างบ → ตัด
        ('B_FRESH', 'B0', 'นครพนม', 5000000, 'ก่อสร้างถนนคอนกรีต (ร่าง TOR)'), # planning
    ]
    for pid, ann, prov, bud, name in rows:
        c.execute("INSERT OR IGNORE INTO projects_seen (project_id,announce_type,province,budget,project_name,first_seen_at) "
                  "VALUES (?,?,?,?,?,?)", (pid, ann, prov, bud, name, FRESH))
        if ann == 'D0':
            c.execute("INSERT OR IGNORE INTO project_enrichments (project_id,bid_submit_date,bid_submit_time) VALUES (?,?,?)",
                      (pid, FUTURE, "10:00"))
    c.execute("INSERT OR IGNORE INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
              "VALUES (?,?,?,?,?,'active')", (cid, 'D_FOLLOWED', FRESH, 'D0', 'D0'))
    c.commit()


async def main():
    setup()
    # 403
    try:
        await bms_api.portal_discover_jobs(line_user_id='UDISC', x_bms_secret='bad'); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # no customer → empty
    r0 = await bms_api.portal_discover_jobs(line_user_id='UNONE', x_bms_secret='t')
    assert r0["jobs"] == {"biddable": [], "planning": []}, r0
    # real
    r = await bms_api.portal_discover_jobs(line_user_id='UDISC', x_bms_secret='t')
    bid_ids = {j["project_id"] for j in r["jobs"]["biddable"]}
    plan_ids = {j["project_id"] for j in r["jobs"]["planning"]}
    assert bid_ids == {'D_MATCH'}, bid_ids
    assert plan_ids == {'B_FRESH'}, plan_ids
    j = next(x for x in r["jobs"]["biddable"] if x["project_id"] == 'D_MATCH')
    assert j["matched_keywords"] == ["คอนกรีต"] and j["stage"] == "biddable" and j["budget"] == 5000000, j
    print("PASS test_portal_discover_api")


asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_portal_discover_api.py`
Expected: FAIL — `AttributeError: module 'bms_api' has no attribute 'portal_discover_jobs'`

- [ ] **Step 3a: Extract helper จาก `_portal_jobs`** — ใน `scripts/bms_api.py`

เพิ่มฟังก์ชันใหม่ก่อน `def _portal_jobs` (~line 394):

```python
def _job_location_deadline(conn, pid: str, prov: str):
    """คืน (location, deadline, deadline_time) ของงาน 1 row.
    location = 'ต.x อ.y จ.z' (เท่าที่ resolve ได้); deadline จาก project_locations → project_enrichments.
    ใช้ร่วม _portal_jobs + discover (DRY)."""
    try:
        loc = conn.execute(
            "SELECT moi_name, deadline, deadline_time FROM project_locations WHERE project_id=?", (pid,)).fetchone()
    except sqlite3.OperationalError:
        loc = None
    moi = (loc["moi_name"] if loc and "moi_name" in loc.keys() else "") or ""
    deadline = (loc["deadline"] if loc and "deadline" in loc.keys() else "") or ""
    deadline_time = (loc["deadline_time"] if loc and "deadline_time" in loc.keys() else "") or ""
    if not deadline or not deadline_time:
        try:
            er = conn.execute(
                "SELECT bid_submit_date, bid_submit_time FROM project_enrichments WHERE project_id=?", (pid,)).fetchone()
            if er:
                if not deadline:
                    deadline = (er["bid_submit_date"] or "") if "bid_submit_date" in er.keys() else ""
                if not deadline_time:
                    deadline_time = (er["bid_submit_time"] or "") if "bid_submit_time" in er.keys() else ""
        except sqlite3.OperationalError:
            pass
    amphoe = ""
    if moi and prov:
        try:
            import geo_reverse
            _ams = geo_reverse.amphoes_of_tambon(prov, moi)
            if len(_ams) == 1:
                amphoe = _ams[0]
        except Exception:
            pass
    location = ((f"ต.{moi} " if moi else "") + (f"อ.{amphoe} " if amphoe else "")
                + (f"จ.{prov}" if prov else "")).strip()
    return location, deadline, deadline_time
```

จากนั้น **แทนที่** block ใน `_portal_jobs` (เดิม ~line 415-445, ตั้งแต่ `try:` ที่ query project_locations จนถึงบรรทัด `location = ...`) ด้วย:

```python
            prov = ps["province"] or ""
            location, deadline, deadline_time = _job_location_deadline(conn, pid, prov)
```

ลบตัวแปร `loc`, `moi`, `amphoe`, และ block fallback enrichments เดิมที่ถูกย้ายไป helper แล้ว (ระวัง: `prov` ยังถูกใช้ต่อด้านล่าง — คงไว้). ตรวจว่าไม่มีการอ้าง `moi`/`amphoe` ที่อื่นใน `_portal_jobs`

- [ ] **Step 3b: Verify ไม่ทำ regression** — `_portal_jobs` ยังทำงาน

Run: `python scripts/test_portal_jobs_api.py`
Expected: `PASS test_portal_jobs_api` (helper extract ไม่เปลี่ยนพฤติกรรม)

- [ ] **Step 3c: เพิ่ม endpoint `portal_discover_jobs`** — ถัดจาก `portal_get_jobs` (~line 1558) ใน `scripts/bms_api.py`

```python
@app.get("/api/portal/discover")
async def portal_discover_jobs(
    line_user_id: str = Query(...),
    x_bms_secret=Header(default=None),
):
    """งานใหม่ที่แมตช์ (per-user keyword+พื้นที่+งบ) ที่ยังไม่ติดตาม — บอร์ด Next.js.
    SCOPE: read-only discovery query เท่านั้น — ไม่แตะ LINE pipeline / global config."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    import discovery_match
    empty = {"biddable": [], "planning": []}
    with get_conn() as conn:
        cust = conn.execute("SELECT id, notes FROM customers WHERE line_user_id=?", (line_user_id,)).fetchone()
        if not cust:
            return {"ok": True, "jobs": empty}
        cid = cust["id"]
        provinces = [r["province"] for r in conn.execute(
            "SELECT sp.province FROM subscription_provinces sp "
            "JOIN subscriptions s ON s.id=sp.subscription_id WHERE s.customer_id=?", (cid,)).fetchall()]
        pref = _classes_from_notes(cust["notes"] or "")
        keywords = pref["keywords"]
        if not provinces or not keywords:
            return {"ok": True, "jobs": empty}
        followed = {r["project_id"] for r in conn.execute(
            "SELECT project_id FROM followed_jobs WHERE customer_id=?", (cid,)).fetchall()}
        neg = job_matcher.load_config().get("negative_keywords", [])
        qmarks = ",".join("?" * len(provinces))
        rows = conn.execute(
            f"SELECT project_id, project_name, announce_type, province, budget, first_seen_at "
            f"FROM projects_seen WHERE province IN ({qmarks})", provinces).fetchall()
        today = datetime.now(THAI_TZ).date().isoformat()
        biddable, planning = [], []
        for r in rows:
            pid = r["project_id"]
            if pid in followed:
                continue
            matched, hits = discovery_match.match(
                r["project_name"] or "", r["province"] or "", r["budget"] or 0,
                provinces, keywords, pref["budget_min"], pref["budget_max"], neg)
            if not matched:
                continue
            ann = (r["announce_type"] or "")
            location, deadline, deadline_time = _job_location_deadline(conn, pid, r["province"] or "")
            card = {"project_id": pid, "name": r["project_name"] or pid,
                    "location": location, "province": r["province"] or "",
                    "deadline": deadline, "deadline_time": deadline_time,
                    "budget": r["budget"] or 0, "matched_keywords": hits}
            if ann == "D0":
                if deadline and deadline >= today:
                    card["stage"] = "biddable"
                    biddable.append((deadline, card))
            elif ann.startswith("B"):
                if job_matcher.tor_is_fresh(r["first_seen_at"], days=14):
                    card["stage"] = "planning"
                    planning.append((r["first_seen_at"] or "", card))
        biddable.sort(key=lambda x: x[0])              # deadline ใกล้สุดก่อน
        planning.sort(key=lambda x: x[0], reverse=True)  # ใหม่สุดก่อน
        out = {"biddable": [c for _, c in biddable[:30]], "planning": [c for _, c in planning[:30]]}
    return {"ok": True, "jobs": out}
```

หมายเหตุ: ตรวจว่า `import job_matcher` มีที่ top ของ bms_api แล้ว (Phase นี้ใช้ `job_matcher.load_config`/`tor_is_fresh`); ถ้ายังไม่มี เพิ่ม `import job_matcher` ในกลุ่ม import. ตรวจว่า `THAI_TZ` มีอยู่ (ใช้ใน `_now()`); ถ้าชื่อ tz ต่าง ใช้ตามที่ `_now()` ใช้

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_portal_discover_api.py`
Expected: `PASS test_portal_discover_api`

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_discover_api.py
git commit -m "feat(discovery): GET /api/portal/discover + extract _job_location_deadline (DRY)"
```

---

### Task 4: `POST /api/portal/follow`

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่ม endpoint ถัดจาก `portal_star_toggle_json` ~line 1581)
- Test: `scripts/test_portal_follow_api.py`

**Interfaces:**
- Consumes: `_record_follow(user_id, project_id)` (มีอยู่แล้ว ~line 227)
- Produces: `bms_api.portal_follow_job(request, x_bms_secret)` (async) คืน `{"ok": True, "followed": True}`

- [ ] **Step 1: Write the failing test** — `scripts/test_portal_follow_api.py`

```python
"""test_portal_follow_api.py — POST /api/portal/follow → followed_jobs active + ตัดออกจาก discover."""
import os, sys, json, sqlite3, asyncio, tempfile, shutil
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"), BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


class FakeReq:
    def __init__(self, body): self._b = body
    async def json(self): return self._b


def setup():
    now = bms_api._now()
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UFOL','x','trial',1,?,?)", (now, now))
    c.execute("INSERT OR IGNORE INTO projects_seen (project_id,announce_type,province,budget,project_name,first_seen_at) "
              "VALUES ('PFOL','D0','นครพนม',5000000,'ก่อสร้างถนนคอนกรีต',?)", (now,))
    c.commit()


async def main():
    setup()
    # 403
    try:
        await bms_api.portal_follow_job(FakeReq({"line_user_id": "UFOL", "project_id": "PFOL"}), x_bms_secret='bad'); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # no customer → 404
    try:
        await bms_api.portal_follow_job(FakeReq({"line_user_id": "UNONE", "project_id": "PFOL"}), x_bms_secret='t'); assert False
    except HTTPException as e:
        assert e.status_code == 404
    # happy → followed_jobs active
    r = await bms_api.portal_follow_job(FakeReq({"line_user_id": "UFOL", "project_id": "PFOL"}), x_bms_secret='t')
    assert r["ok"] and r["followed"] is True, r
    c = sqlite3.connect(bms_api.DB_PATH)
    st = c.execute("SELECT status FROM followed_jobs fj JOIN customers cu ON cu.id=fj.customer_id "
                   "WHERE cu.line_user_id='UFOL' AND fj.project_id='PFOL'").fetchone()
    assert st and st[0] == 'active', st
    print("PASS test_portal_follow_api")


asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_portal_follow_api.py`
Expected: FAIL — `AttributeError: module 'bms_api' has no attribute 'portal_follow_job'`

- [ ] **Step 3: Write minimal implementation** — ถัดจาก `portal_star_toggle_json` ใน `scripts/bms_api.py`

```python
@app.post("/api/portal/follow")
async def portal_follow_job(
    request: Request,
    x_bms_secret=Header(default=None),
):
    """ดึงงาน discovery เข้า followed_jobs (status active) — จากปุ่ม 'ติดตาม' บนบอร์ด.
    reuse _record_follow (เส้นเดียวกับ follow จากลิงก์ LINE)."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    line_user_id = (body.get("line_user_id") or "").strip()
    project_id = (body.get("project_id") or "").strip()
    if not line_user_id or not project_id:
        raise HTTPException(status_code=400, detail="line_user_id + project_id required")
    res = _record_follow(line_user_id, project_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True, "followed": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_portal_follow_api.py`
Expected: `PASS test_portal_follow_api`

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_follow_api.py
git commit -m "feat(discovery): POST /api/portal/follow (reuse _record_follow)"
```

---

### Task 5: web client lib — `getDiscoverJobs` + follow route

**Files:**
- Modify: `dashboard/web/src/lib/portal-jobs.ts`
- Create: `dashboard/web/src/app/api/portal/follow/route.ts`

**Interfaces:**
- Produces:
  - `DiscoverJob` interface + `DiscoverGroups` (`{ biddable: DiscoverJob[]; planning: DiscoverJob[] }`)
  - `getDiscoverJobs(lineUserId: string): Promise<DiscoverGroups>`
  - route `POST /api/portal/follow` (body `{ project_id }`) → relay engine

- [ ] **Step 1: อ่าน docs ที่เกี่ยวข้องก่อนเขียน web**

Run: ดู `node_modules/next/dist/docs/` ที่เกี่ยวกับ Route Handlers (App Router) — ยืนยัน signature `export async function POST(req: NextRequest)` + `runtime`/`dynamic` exports ตรงกับ version นี้ (เทียบกับ `app/api/portal/star/route.ts` ที่มีอยู่)

- [ ] **Step 2: เพิ่ม type + `getDiscoverJobs`** ใน `dashboard/web/src/lib/portal-jobs.ts` (ต่อท้ายไฟล์)

```typescript
export interface DiscoverJob {
  project_id: string;
  name: string;
  location: string;
  province: string;
  deadline: string;
  deadline_time: string;
  budget: number;
  matched_keywords: string[];
  stage: "biddable" | "planning";
}

export interface DiscoverGroups {
  biddable: DiscoverJob[];
  planning: DiscoverJob[];
}

const EMPTY_DISCOVER: DiscoverGroups = { biddable: [], planning: [] };

export async function getDiscoverJobs(lineUserId: string): Promise<DiscoverGroups> {
  if (!lineUserId) return EMPTY_DISCOVER;
  const url = `${BMS_API_URL}/api/portal/discover?line_user_id=${encodeURIComponent(lineUserId)}`;
  const res = await fetch(url, { headers: { "X-BMS-Secret": BMS_SECRET }, cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET discover failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; jobs: DiscoverGroups };
  return data.jobs ?? EMPTY_DISCOVER;
}
```

- [ ] **Step 3: สร้าง route** `dashboard/web/src/app/api/portal/follow/route.ts` (mirror `star/route.ts`)

```typescript
/**
 * POST /api/portal/follow { project_id } — ดึงงาน discovery เข้า followed_jobs
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
  try {
    projectId = ((await req.json()).project_id ?? "").toString().trim();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  if (!projectId) return NextResponse.json({ ok: false, error: "project_id required" }, { status: 400 });

  try {
    const r = await fetch(`${BMS_API_URL}/api/portal/follow`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET },
      body: JSON.stringify({ line_user_id: session.lineUserId, project_id: projectId }),
      cache: "no-store",
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : r.status });
  } catch (e) {
    console.error("[/api/portal/follow]", e);
    return NextResponse.json({ ok: false, error: "engine unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 4: ตรวจ tsc**

Run: `cd dashboard/web && npx tsc --noEmit`
Expected: ไม่มี error

- [ ] **Step 5: Commit**

```bash
git add dashboard/web/src/lib/portal-jobs.ts dashboard/web/src/app/api/portal/follow/route.ts
git commit -m "feat(discovery): web getDiscoverJobs + /api/portal/follow relay route"
```

---

### Task 6: web UI — section "งานใหม่ที่แมตช์" + ปุ่มติดตาม

**Files:**
- Modify: `dashboard/web/src/app/portal/world/page.tsx`
- Modify: `dashboard/web/src/app/portal/world/_client.tsx`

**Interfaces:**
- Consumes: `getDiscoverJobs`, `DiscoverGroups`, `DiscoverJob` (Task 5); `POST /api/portal/follow`
- Produces: prop `discoverGroups: DiscoverGroups` ส่งเข้า `WorldClient`

- [ ] **Step 1: page.tsx — fetch discover server-side**

ใน `dashboard/web/src/app/portal/world/page.tsx`:
- เพิ่ม import: `import { getPortalJobs, getDiscoverJobs, type JobGroups, type DiscoverGroups } from '@/lib/portal-jobs';`
- หลัง block `try { jobGroups = await getPortalJobs(...) }` เพิ่ม:

```typescript
  let discoverGroups: DiscoverGroups = { biddable: [], planning: [] };
  try {
    discoverGroups = await getDiscoverJobs(session.lineUserId);
  } catch { /* engine unavailable — show empty discovery */ }
```

- ใน `<WorldClient ... />` เพิ่ม prop: `discoverGroups={discoverGroups}`

- [ ] **Step 2: _client.tsx — props + handleFollow + section**

ใน `dashboard/web/src/app/portal/world/_client.tsx`:
- import: เพิ่ม `DiscoverGroups, DiscoverJob` ใน import จาก `@/lib/portal-jobs`
- `WorldClientProps`: เพิ่ม `discoverGroups: DiscoverGroups;`
- signature `WorldClient`: เพิ่ม `discoverGroups` ใน destructure
- ใน body (หลัง `toggleStar`) เพิ่ม state + handler:

```typescript
  const [discover, setDiscover] = useState<DiscoverGroups>(discoverGroups);
  const [following, setFollowing] = useState<Set<string>>(new Set());

  const handleFollow = async (projectId: string) => {
    setFollowing(prev => new Set(prev).add(projectId));
    try {
      const r = await fetch('/api/portal/follow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!r.ok) throw new Error('follow failed');
      // ติดตามสำเร็จ → เอาออกจาก discovery (จะไปโผล่ tracked รอบหน้า)
      setDiscover(prev => ({
        biddable: prev.biddable.filter(j => j.project_id !== projectId),
        planning: prev.planning.filter(j => j.project_id !== projectId),
      }));
    } catch {
      setFollowing(prev => { const n = new Set(prev); n.delete(projectId); return n; });
    }
  };
```

- [ ] **Step 3: _client.tsx — DiscoverCard component**

เพิ่ม component ก่อน `function WorldClient` (วาง pattern เดียวกับ `TrackedJobCard`):

```typescript
function DiscoverCard({ job, following, onFollow, starred, onStar }: {
  job: DiscoverJob; following: boolean; onFollow: () => void; starred: boolean; onStar: () => void;
}) {
  const dl = daysLeftOf(job.deadline);
  const urgency = dl === null ? 'outline' : dl <= 5 ? 'wine' : dl <= 10 ? 'gold' : 'outline';
  return (
    <div className="p-card" style={{ padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          {job.location && <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.location}</div>}
          <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.name}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          <button onClick={e => { e.stopPropagation(); onStar(); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: starred ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 18, padding: '0 2px', lineHeight: 1 }}>
            {starred ? '★' : '☆'}
          </button>
          {job.stage === 'biddable' && dl !== null && (
            <Chip tone={urgency} icon={<Icons.Clock size={11} />}>{dl} วัน</Chip>
          )}
          {job.stage === 'planning' && <Chip tone="outline">วางแผน</Chip>}
        </div>
      </div>
      {job.matched_keywords.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {job.matched_keywords.map(k => <Chip key={k} tone="gold" icon={<Icons.Tag size={10} />}>{k}</Chip>)}
        </div>
      )}
      <div style={{ display: 'flex', gap: 16, marginTop: 10, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        {job.budget > 0 && (
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ราคากลาง</div>
            <div className="p-serif" style={{ fontSize: 16, fontWeight: 500 }}>
              <span className="p-fg-accent">{fmtBaht(job.budget)}</span> <span className="p-fg-dim" style={{ fontSize: 11 }}>บาท</span>
            </div>
          </div>
        )}
        <button className="p-btn p-btn-primary" disabled={following} onClick={onFollow}
          style={{ height: 34, padding: '0 14px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icons.Bell size={13} />{following ? 'ติดตามแล้ว' : 'ติดตาม'}
        </button>
      </div>
      {job.deadline && job.stage === 'biddable' && (
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 8 }}>
          ยื่นซอง: {job.deadline}{job.deadline_time ? ` ${job.deadline_time}` : ''}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: _client.tsx — render section**

หลัง block "Tracked jobs by stage" (`</div>` ปิด section tracked ~line ที่จบ STAGE_META.map) เพิ่ม section discovery:

```tsx
        {/* Discovery: งานใหม่ที่แมตช์ */}
        {(() => {
          const discoverAll = [...discover.biddable, ...discover.planning];
          const hasPrefs = provincesCount > 0 && totalKeywords > 0;
          return (
            <div style={{ marginTop: 26 }}>
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
                <div>
                  <div className="p-smallcaps p-fg-mute">งานใหม่ที่แมตช์</div>
                  <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>✨ Matched For You</div>
                </div>
                {discoverAll.length > 0 && <Chip tone="gold" icon={<Diamond size={5} />}>{discoverAll.length} งาน</Chip>}
              </div>
              {!hasPrefs ? (
                <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                  <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                    ตั้งค่าพื้นที่และคำค้นในหน้า “บริษัทของฉัน” เพื่อให้ระบบหางานที่ตรงให้ท่านครับ
                  </div>
                  <Link href="/portal/classes"><button className="p-btn p-btn-primary" style={{ marginTop: 12, height: 34, padding: '0 16px', fontSize: 13 }}>ไปตั้งค่า</button></Link>
                </div>
              ) : discoverAll.length === 0 ? (
                <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                  <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                    ยังไม่มีงานใหม่ที่ตรงเกณฑ์วันนี้ — ระบบจะอัปเดตให้เมื่อมีงานเข้าครับ
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {discoverAll.map(job => (
                    <DiscoverCard
                      key={job.project_id}
                      job={job}
                      following={following.has(job.project_id)}
                      onFollow={() => handleFollow(job.project_id)}
                      starred={starred.has(job.project_id)}
                      onStar={() => toggleStar(job.project_id)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })()}
```

- [ ] **Step 5: ตรวจ tsc + build**

Run: `cd dashboard/web && npx tsc --noEmit && npx next build`
Expected: tsc ไม่มี error; build ผ่าน (ถ้า build หนักเกิน รัน `npx tsc --noEmit` อย่างเดียวพอ — vercel build จะตรวจตอน deploy)

- [ ] **Step 6: Commit**

```bash
git add dashboard/web/src/app/portal/world/page.tsx dashboard/web/src/app/portal/world/_client.tsx
git commit -m "feat(discovery): section 'งานใหม่ที่แมตช์' บนบอร์ด + ปุ่มติดตาม + empty states"
```

---

### Task 7: deploy + sanity + verify (prod)

**Files:** ไม่มี code change — deploy + verify

- [ ] **Step 1: Sanity (Sophia)** — dispatch agent `sophia` ตรวจหลังแก้ bms_api ก่อน deploy

prompt: "แก้ bms_api: เพิ่ม discover/follow endpoint + extract _job_location_deadline + _classes_from_notes (Phase 2 discovery). ตรวจว่า customers ยัง 5/0 test, ไม่มี duplicate, queue/followed_jobs ไม่เพี้ยน, ไม่มี silent error. คืน SAFE/STOP"
Expected: verdict SAFE

- [ ] **Step 2: รัน test ทั้งหมดอีกรอบ (regression)**

Run:
```bash
python scripts/test_discovery_match.py && python scripts/test_classes_from_notes.py && \
python scripts/test_portal_discover_api.py && python scripts/test_portal_follow_api.py && \
python scripts/test_portal_jobs_api.py
```
Expected: PASS ทั้ง 5

- [ ] **Step 3: scp engine files → VPS + restart**

```bash
scp -i ~/.ssh/bms_vps scripts/bms_api.py scripts/discovery_match.py root@45.76.156.166:/opt/bms/scripts/
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "systemctl restart bms-api.service && sleep 2 && systemctl is-active bms-api.service"
```
Expected: `active`

- [ ] **Step 4: smoke test endpoint บน prod** (กัญจน์ Ua0d90e8 — read-only)

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "curl -s -H 'X-BMS-Secret: '\$(grep BMS_INTERNAL_SECRET /opt/bms/.env | cut -d= -f2) 'http://localhost:8000/api/portal/discover?line_user_id=Ua0d90e8...' | head -c 500"
```
(แทน line_user_id เต็มของกัญจน์) Expected: `{"ok":true,"jobs":{"biddable":[...],"planning":[...]}}` (อาจว่างถ้าไม่มีงานตรงเกณฑ์วันนี้ — ปกติ)

- [ ] **Step 5: deploy web (Vercel)**

```bash
cd dashboard/web && vercel deploy --prod --yes
```
Expected: deploy สำเร็จ + URL

- [ ] **Step 6: push + reconcile VPS git**

```bash
git push origin main
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cd /opt/bms && git stash && git pull --ff-only && git stash drop 2>/dev/null; git log --oneline -1"
```
(ถ้า reconcile เจอ diff: ตรวจด้วย `git diff --ignore-cr-at-eol` ก่อน — CRLF หลอก ดู [[project_deploy_debt]])
Expected: VPS HEAD = origin/main

- [ ] **Step 7: verify E2E บนบอร์ดจริง** (กัญจน์ login)

เปิด `https://bid-master-dashboard.vercel.app/portal/world` → section "✨ งานใหม่ที่แมตช์" แสดง; ถ้ามีงาน กด "ติดตาม" 1 งาน (throwaway) → งานหายจาก discovery; reload → โผล่ใน "งานที่ติดตาม"; ลบ followed_jobs row ที่ test ออก (cleanup):
```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "sqlite3 /opt/bms/data/bms_customers.db \"UPDATE followed_jobs SET status='unfollowed' WHERE project_id='<test_pid>' AND customer_id=(SELECT id FROM customers WHERE line_user_id='Ua0d90e8...')\""
```
Expected: ครบ success criteria 1-7 ใน spec

- [ ] **Step 8: progress_log + Discord notify**

- เพิ่ม entry `## งานที่ N+181: Phase 2 discovery บอร์ด B` ใน `progress_log.md` (สถานะ ✅, สิ่งที่ทำ, verify, followup)
- Discord: "✅ Phase 2 บอร์ด B เสร็จ — section 'งานใหม่ที่แมตช์' (per-user keyword+พื้นที่+งบ) + ปุ่มติดตาม DEPLOYED"
- commit progress_log: `git add progress_log.md && git commit -m "docs(progress): N+181 Phase 2 discovery บอร์ด B DEPLOYED" && git push`

---

## Self-Review

**Spec coverage:**
- discovery_match (province/keyword/budget/negative) → Task 1 ✓
- per-user keyword/budget จาก notes.classes → Task 2 (`_classes_from_notes`) ✓
- GET /api/portal/discover (2 stage, freshness B0, ตัด followed, limit 30, sort) → Task 3 ✓
- extract location helper (DRY) → Task 3 Step 3a ✓
- POST /api/portal/follow (reuse _record_follow) → Task 4 ✓
- web lib + relay route → Task 5 ✓; section UI + ปุ่มติดตาม + empty states → Task 6 ✓
- ⭐ แยกจากติดตาม → Task 6 (DiscoverCard มีทั้ง ⭐ + ปุ่มติดตาม) ✓
- ไม่แตะ LINE pipeline/global config → ไม่มี task แก้ไฟล์เหล่านั้น; verify Task 7 Step 1 (Sophia) ✓
- testing ครบ + scratch DB → Task 1-4 tests ✓; deploy + reconcile → Task 7 ✓
- success criteria 1-7 → verify Task 7 Step 7 ✓

**Placeholder scan:** ไม่มี TODO/TBD; ทุก step มี code/command จริง ✓ (`<test_pid>`/line_user_id เต็ม = ค่า runtime ที่ต้องแทนตอน execute — ระบุชัดว่าแทนอะไร)

**Type consistency:** `match() -> (bool, list[str])` ใช้ตรงกัน Task 1↔3; `matched_keywords` (snake) ใช้ตรงกัน engine↔web (`DiscoverJob.matched_keywords`); `stage` ∈ `biddable|planning` ตรงกัน Task 3↔5↔6; `_job_location_deadline -> (location, deadline, deadline_time)` ใช้ตรงใน `_portal_jobs` (refactor) + discover ✓

## Execution Handoff

(ดูตอนท้ายข้อความ)
