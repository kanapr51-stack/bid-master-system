# Portal Interest Star (⭐ ที่สนใจ) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่มดาว "ที่สนใจ" ชั้นที่สอง (แยกจาก ⭐ ติดตามเดิมที่กดผ่าน LINE) ให้กับงานในกลุ่มที่ติดตามอยู่แล้ว เพื่อกรองดูเฉพาะงานที่สนใจที่สุดใน BMS Bid Board.

**Architecture:** ตารางใหม่ `job_stars(customer_id, project_id, created_at)` แยกจาก `followed_jobs`. Toggle ผ่าน server-rendered redirect route (ไม่มี JS/fetch ในระบบนี้) `GET /portal/star_toggle?t=&pid=&back=board|job`. UI = ปุ่มดาวบนการ์ด Bid Board + หน้ารายละเอียดงาน, ชิป filter "⭐ ที่สนใจ" เป็น toggle อิสระ AND กับ filter เดิม (client-side JS, ไม่มี state ค้างเพราะ toggle = full page reload).

**Tech Stack:** Python 3, FastAPI (`scripts/bms_api.py`), raw HTML string rendering (`scripts/portal_views.py`), SQLite (`bms_customers.db`). ไม่มี test framework — test files เป็น plain script (`assert` + `print("OK ...")`), รันตรงด้วย `python scripts/test_x.py`.

## Global Constraints

- ห้ามแก้ความหมาย ⭐ เดิม (`followed_jobs.starred_at`, LINE postback `star:<project_id>`) — คนละระบบเด็ดขาด ตาม spec `docs/superpowers/specs/2026-06-21-portal-interest-star-design.md`
- ทุก dynamic value ที่ลง HTML ต้องผ่าน `html.escape()` (`_h.escape`) ตาม pattern เดิมในไฟล์
- ทุก SQL ต้อง parameterized (`?`) ห้าม string-format ค่าเข้า SQL ตรงๆ
- Toggle route ต้อง validate `back` เป็น `"board"`/`"job"` เท่านั้น (ป้องกัน open redirect)
- ไม่ guard ว่า project ต้องอยู่ใน `followed_jobs` ก่อน star ได้ (YAGNI — ตาม spec)
- ห้าม push/deploy อัตโนมัติ — commit ทุก task แต่ push/deploy ต้องรอคำสั่งคุณกัญจน์แยก
- รัน Sophia sanity audit ก่อน task สุดท้าย (commit รวม) ตาม CLAUDE.md Sanity Check Protocol

---

### Task 1: Schema migration — ตาราง `job_stars`

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py:313-314` (เพิ่มเรียก migration ใหม่ + bump version string)
- Modify: `scripts/Sebastian_Customer_DB.py:317` (เพิ่ม `_migrate_v131` ก่อน `_migrate_v130`)

**Interfaces:**
- Produces: ตาราง `job_stars(customer_id INTEGER NOT NULL, project_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(customer_id, project_id))` — ใช้โดย Task 2

- [ ] **Step 1: เพิ่มฟังก์ชัน migration**

เปิด `scripts/Sebastian_Customer_DB.py` หาบรรทัด:
```python
def _migrate_v130():
    """customers +company_tin — บริษัทของ tenant (ใช้ทำมุมเทียบ head-to-head). NULL = ยังไม่ตั้ง. (2026-06-20)"""
    with get_connection() as conn:
        try:
            conn.execute("ALTER TABLE customers ADD COLUMN company_tin TEXT")
        except sqlite3.OperationalError:
            pass  # already exists
```

เพิ่มฟังก์ชันใหม่ต่อจากนี้ (ก่อน `_migrate_v129`):
```python
def _migrate_v131():
    """job_stars — ดาว 'ที่สนใจ' ชั้นที่สอง แยกจาก followed_jobs.starred_at (⭐ เดิม=เริ่มติดตาม). (2026-06-21)"""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_stars (
                customer_id INTEGER NOT NULL,
                project_id  TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (customer_id, project_id)
            )""")
```

- [ ] **Step 2: เรียก migration ใน `init_schema()` + bump version**

หาบรรทัด:
```python
    _migrate_v130()
    print(f"Schema v1.13 ready: {DB_PATH}")
```
แก้เป็น:
```python
    _migrate_v130()
    _migrate_v131()
    print(f"Schema v1.14 ready: {DB_PATH}")
```

- [ ] **Step 3: รัน migration จริงกับ local DB เพื่อยืนยันไม่พัง**

Run: `cd /c/Bid-Master-System && python -c "import sys; sys.path.insert(0,'scripts'); from Sebastian_Customer_DB import init_schema; init_schema()"`

Expected: พิมพ์ `Schema v1.14 ready: ...bms_customers.db` ไม่มี traceback

Run: `python -c "import sys; sys.path.insert(0,'scripts'); from Sebastian_Customer_DB import get_connection; c=get_connection(); print(c.execute(\"SELECT sql FROM sqlite_master WHERE name='job_stars'\").fetchone()[0])"`

Expected: พิมพ์ `CREATE TABLE job_stars (...)` (ตารางมีจริง)

- [ ] **Step 4: Commit**

```bash
git add scripts/Sebastian_Customer_DB.py
git commit -m "feat(db): add job_stars table for ⭐ ที่สนใจ (secondary star, separate from follow-star)"
```

---

### Task 2: Data layer — `toggle_star` + `starred_project_ids`

**Files:**
- Modify: `scripts/portal_views.py` (เพิ่มฟังก์ชันใหม่หลัง `save_job_overview`, ก่อน `head_to_head` — ปัจจุบันอยู่บรรทัด ~696-699)
- Create: `scripts/test_portal_stars.py`

**Interfaces:**
- Consumes: `conn: sqlite3.Connection` (row_factory=Row), `customer_id: int|None`, `project_id: str`
- Produces:
  - `toggle_star(conn, customer_id, pid) -> bool` — True=ติดดาวแล้วหลัง toggle, False=ไม่ติดดาว/no-op (customer_id falsy)
  - `starred_project_ids(conn, customer_id) -> set[str]` — set ว่างถ้าไม่มี customer
  - ใช้โดย Task 3 (render_job_page), Task 4 (route), Task 5 (`_portal_jobs`)

- [ ] **Step 1: เขียน test ที่ fail ก่อน (ฟังก์ชันยังไม่มี)**

สร้างไฟล์ `scripts/test_portal_stars.py`:
```python
"""test_portal_stars.py — job_stars data layer (toggle_star + starred_project_ids, ⭐ ที่สนใจ ชั้นที่สอง)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _conn():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE job_stars(customer_id INTEGER, project_id TEXT, created_at TEXT, "
              "PRIMARY KEY(customer_id, project_id))")
    return c


c = _conn()
# toggle ครั้งแรก = ติดดาว
assert pv.toggle_star(c, 1, "PA") is True
assert pv.starred_project_ids(c, 1) == {"PA"}
# toggle ครั้งสอง (งานเดิม) = ถอดดาว กลับสถานะเดิม
assert pv.toggle_star(c, 1, "PA") is False
assert pv.starred_project_ids(c, 1) == set()
# ดาวหลายงาน
pv.toggle_star(c, 1, "PA")
pv.toggle_star(c, 1, "PB")
assert pv.starred_project_ids(c, 1) == {"PA", "PB"}
# cross-customer isolation: คนละคนไม่เห็นดาวกัน
assert pv.starred_project_ids(c, 2) == set()
pv.toggle_star(c, 2, "PA")
assert pv.starred_project_ids(c, 1) == {"PA", "PB"} and pv.starred_project_ids(c, 2) == {"PA"}
# customer None → no-op, คืนค่าว่างเสมอ
assert pv.toggle_star(c, None, "PA") is False
assert pv.starred_project_ids(c, None) == set()
# ไม่มี duplicate (customer_id, project_id) — PK กันระดับ DB
n = c.execute("SELECT COUNT(*) FROM job_stars WHERE customer_id=1 AND project_id='PA'").fetchone()[0]
assert n == 1, f"ต้องมีแถวเดียว เจอ {n}"
print("OK test_portal_stars")
```

- [ ] **Step 2: รัน test ยืนยันว่า fail (ฟังก์ชันยังไม่มี)**

Run: `python scripts/test_portal_stars.py`
Expected: `AttributeError: module 'portal_views' has no attribute 'toggle_star'`

- [ ] **Step 3: เพิ่มฟังก์ชันจริงใน `portal_views.py`**

หาบรรทัด (ท้ายฟังก์ชัน `save_job_overview`, ก่อน `def head_to_head`):
```python
    if cur.rowcount == 0:
        conn.execute(
            "INSERT INTO job_overview (customer_id, project_id, note, created_at, updated_at) "
            "VALUES (?,?,?,?,?)", (customer_id, pid, note, now, now))


def head_to_head(conn, our_tin, competitor_tin):
```

แทรกฟังก์ชันใหม่ระหว่างสองส่วนนี้:
```python
    if cur.rowcount == 0:
        conn.execute(
            "INSERT INTO job_overview (customer_id, project_id, note, created_at, updated_at) "
            "VALUES (?,?,?,?,?)", (customer_id, pid, note, now, now))


def toggle_star(conn, customer_id, pid):
    """สลับ ⭐ 'ที่สนใจ' (ชั้นที่ 2, แยกจาก followed_jobs.starred_at) ของ (customer, project).
    คืนสถานะใหม่ (True=ติดดาวแล้ว). no-op คืน False ถ้าไม่มี customer."""
    if not customer_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM job_stars WHERE customer_id=? AND project_id=?", (customer_id, pid)).fetchone()
    if row:
        conn.execute("DELETE FROM job_stars WHERE customer_id=? AND project_id=?", (customer_id, pid))
        return False
    conn.execute("INSERT INTO job_stars (customer_id, project_id, created_at) VALUES (?,?,?)",
                 (customer_id, pid, _now_th()))
    return True


def starred_project_ids(conn, customer_id):
    """set ของ project_id ที่ user ติดดาว 'ที่สนใจ' ไว้. คืน set() ถ้าไม่มี customer."""
    if not customer_id:
        return set()
    rows = conn.execute("SELECT project_id FROM job_stars WHERE customer_id=?", (customer_id,)).fetchall()
    return {r["project_id"] for r in rows}


def head_to_head(conn, our_tin, competitor_tin):
```

- [ ] **Step 4: รัน test ยืนยันว่า pass**

Run: `python scripts/test_portal_stars.py`
Expected: `OK test_portal_stars`

- [ ] **Step 5: รัน regression เดิมไม่พัง**

Run: `python scripts/test_portal_notes.py && python scripts/test_portal_views.py`
Expected: `OK test_portal_notes` และ `OK render_job_page` ... ตามด้วย `OK` ทุกบรรทัดจนจบไฟล์ ไม่มี `AssertionError`

- [ ] **Step 6: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_stars.py
git commit -m "feat(portal): toggle_star + starred_project_ids data layer (⭐ ที่สนใจ)"
```

---

### Task 3: ปุ่มดาวในหน้ารายละเอียดงาน (`/portal/job`)

**Files:**
- Modify: `scripts/portal_views.py` (`_CSS` เพิ่ม `.star`, `render_job_page` เพิ่ม param `starred` + ปุ่ม)
- Modify: `scripts/test_portal_views.py` (เพิ่ม assertion ท้ายไฟล์)

**Interfaces:**
- Consumes: `toggle_star`/`starred_project_ids` จาก Task 2 (ใช้ใน route, ไม่ใช่ในไฟล์นี้)
- Produces: `render_job_page(data, token, exp, notes=None, overview="", starred=False)` — เพิ่ม keyword `starred` ใหม่ (default `False` ไม่กระทบ caller เดิมที่เรียกแบบ positional ≤5 args) — ใช้โดย Task 6

- [ ] **Step 1: เขียน test ที่ fail ก่อน**

เปิด `scripts/test_portal_views.py` ต่อท้ายไฟล์ (หลังบรรทัดสุดท้าย `print("OK render_job_page_overview")` ที่มีอยู่) เพิ่ม:
```python
# --- render_job_page: ปุ่มดาว "ที่สนใจ" (ชั้นที่ 2, แยกจาก ⭐ ติดตามเดิม) ---
c = _seed()
d = pv.job_detail(c, "69010000001")
h_on = pv.render_job_page(d, "TOK", 0, [], "", True)
assert "⭐" in h_on, "ติดดาวแล้วต้องโชว์ ⭐ เต็ม"
assert "/portal/star_toggle?t=TOK&pid=69010000001&back=job" in h_on, h_on
h_off = pv.render_job_page(d, "TOK", 0, [], "", False)
assert "☆" in h_off and "star_toggle" in h_off, "ไม่ติดดาวต้องโชว์ ☆ ว่าง"
print("OK render_job_page_star")
```

- [ ] **Step 2: รัน test ยืนยันว่า fail**

Run: `python scripts/test_portal_views.py`
Expected: `TypeError: render_job_page() takes from 3 to 5 positional arguments but 6 were given`

- [ ] **Step 3: เพิ่ม CSS `.star`**

เปิด `scripts/portal_views.py` หาบรรทัดสุดท้ายของ `_CSS` (ก่อน `)`):
```python
    ".rstation.today::before{background:#f7941d}"
    ".rdate.today{color:#f7941d}"
    ".rstation.past::before{background:#d9534f}"
    ".rdate.past{color:#d9534f}"
    ".pastlist summary{color:#d9534f}"
)
```
แก้เป็น:
```python
    ".rstation.today::before{background:#f7941d}"
    ".rdate.today{color:#f7941d}"
    ".rstation.past::before{background:#d9534f}"
    ".rdate.past{color:#d9534f}"
    ".pastlist summary{color:#d9534f}"
    ".star{font-size:20px;text-decoration:none;margin-left:8px;vertical-align:middle}"
)
```

- [ ] **Step 4: เพิ่ม param + ปุ่มดาวใน `render_job_page`**

หาบรรทัด:
```python
def render_job_page(data, token, exp, notes=None, overview=""):
    tok = _h.escape(token)
    head = _HEAD("รายละเอียดงาน")
    back = f"<a class=\"back\" href=\"/portal?t={tok}\">← งานที่ติดตาม</a>"
    if not data:
        return head + back + "<div class=\"msg\">ไม่พบรายละเอียดงานนี้</div>" + _FOOT
    j = data["job"]
    b = [back, f"<div class=\"h\">🏗️ {_h.escape(j['name'])}</div>",
         f"<div class=\"jid\">🆔 {_h.escape(str(j['project_id']))}</div>"]
```
แก้เป็น:
```python
def render_job_page(data, token, exp, notes=None, overview="", starred=False):
    tok = _h.escape(token)
    head = _HEAD("รายละเอียดงาน")
    back = f"<a class=\"back\" href=\"/portal?t={tok}\">← งานที่ติดตาม</a>"
    if not data:
        return head + back + "<div class=\"msg\">ไม่พบรายละเอียดงานนี้</div>" + _FOOT
    j = data["job"]
    pid_esc = _h.escape(str(j["project_id"]))
    star_href = f"/portal/star_toggle?t={tok}&pid={pid_esc}&back=job"
    star_icon = "⭐" if starred else "☆"
    b = [back, f"<div class=\"h\">🏗️ {_h.escape(j['name'])}<a class=\"star\" href=\"{star_href}\">{star_icon}</a></div>",
         f"<div class=\"jid\">🆔 {pid_esc}</div>"]
```

- [ ] **Step 5: รัน test ยืนยันว่า pass**

Run: `python scripts/test_portal_views.py`
Expected: ทุกบรรทัด `OK ...` จบด้วย `OK render_job_page_star` ไม่มี `AssertionError`/`TypeError`

- [ ] **Step 6: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): ปุ่ม ⭐ ที่สนใจ ในหน้ารายละเอียดงาน"
```

---

### Task 4: Route `/portal/star_toggle`

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่ม route ใหม่ก่อน `@app.get("/portal/job")` ที่บรรทัด ~1001)
- Modify: `scripts/test_portal_routes.py` (เพิ่ม assertion ท้ายไฟล์)

**Interfaces:**
- Consumes: `portal_views.toggle_star(conn, cid, pid)` จาก Task 2, `follow_token.verify_token(t)`, `get_conn()`
- Produces: route async function `portal_star_toggle_get(t, pid, back)` เรียกตรงได้แบบ `asyncio.run(api.portal_star_toggle_get(t=tok, pid="X", back="board"))` — ใช้ทดสอบใน Task 5/6

- [ ] **Step 1: เขียน test ที่ fail ก่อน**

เปิด `scripts/test_portal_routes.py` ต่อท้ายไฟล์ (หลังบรรทัดสุดท้าย `print("OK portal_company_h2h")`) เพิ่ม:
```python
# --- /portal/star_toggle: toggle ⭐ ที่สนใจ + redirect กลับ board/job ---
r1 = asyncio.run(api.portal_star_toggle_get(t=tok, pid="69010000001", back="board"))
assert r1.status_code == 303 and r1.headers["location"] == f"/portal?t={tok}", r1.headers
with _db.get_connection() as _c:
    n = _c.execute("SELECT COUNT(*) FROM job_stars WHERE project_id='69010000001'").fetchone()[0]
assert n == 1, "toggle ครั้งแรกต้อง insert"
# หน้า job ต้องโชว์ ⭐ เต็มแล้ว
bj = asyncio.run(api.portal_job_get(t=tok, pid="69010000001")).body.decode("utf-8")
assert "⭐" in bj, "หลังติดดาวต้องโชว์ ⭐ ในหน้า job"
# toggle อีกครั้ง back=job → ถอดดาว + redirect ไปหน้า job
r2 = asyncio.run(api.portal_star_toggle_get(t=tok, pid="69010000001", back="job"))
assert r2.status_code == 303 and r2.headers["location"] == f"/portal/job?t={tok}&pid=69010000001", r2.headers
with _db.get_connection() as _c:
    n2 = _c.execute("SELECT COUNT(*) FROM job_stars WHERE project_id='69010000001'").fetchone()[0]
assert n2 == 0, "toggle ครั้งสองต้องลบ"
# back ที่ไม่รู้จัก → fallback ไป board (กัน open-redirect)
r3 = asyncio.run(api.portal_star_toggle_get(t=tok, pid="69010000001", back="evil"))
assert r3.headers["location"] == f"/portal?t={tok}", "back ไม่รู้จักต้อง fallback board"
# token ผิด → ไม่ toggle อะไร
rbad = asyncio.run(api.portal_star_toggle_get(t="BAD", pid="69010000001", back="board"))
assert "ลิงก์ไม่ถูกต้อง" in rbad.body.decode("utf-8") or "ใช้ไม่ได้" in rbad.body.decode("utf-8")
print("OK portal_star_toggle")
```

- [ ] **Step 2: รัน test ยืนยันว่า fail**

Run: `python scripts/test_portal_routes.py`
Expected: `AttributeError: module 'bms_api' has no attribute 'portal_star_toggle_get'`

- [ ] **Step 3: เพิ่ม route จริง**

เปิด `scripts/bms_api.py` หาบรรทัด:
```python
@app.get("/portal/job")
async def portal_job_get(t: str = "", pid: str = ""):
```
แทรก route ใหม่ก่อนหน้านี้:
```python
@app.get("/portal/star_toggle")
async def portal_star_toggle_get(t: str = "", pid: str = "", back: str = "board"):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        cid = cust["id"] if cust else None
        portal_views.toggle_star(conn, cid, pid)
    from urllib.parse import quote
    if back == "job":
        return RedirectResponse(f"/portal/job?t={quote(t)}&pid={quote(pid)}", status_code=303)
    return RedirectResponse(f"/portal?t={quote(t)}", status_code=303)


@app.get("/portal/job")
async def portal_job_get(t: str = "", pid: str = ""):
```

- [ ] **Step 4: รัน test ยืนยันว่า pass**

Run: `python scripts/test_portal_routes.py`
Expected: ทุกบรรทัด `OK ...` จบด้วย `OK portal_star_toggle` ไม่มี error

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_routes.py
git commit -m "feat(portal): route /portal/star_toggle — toggle ⭐ ที่สนใจ + redirect กลับ board/job"
```

---

### Task 5: ส่งสถานะดาวจาก route เข้าหน้ารายละเอียดงาน

**Files:**
- Modify: `scripts/bms_api.py:1002-1012` (`portal_job_get`)

**Interfaces:**
- Consumes: `portal_views.starred_project_ids` (Task 2), `render_job_page(..., starred=...)` (Task 3)

- [ ] **Step 1: แก้ route ให้ query สถานะดาวแล้วส่งเข้า `render_job_page`**

หาบรรทัด:
```python
@app.get("/portal/job")
async def portal_job_get(t: str = "", pid: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        cid = cust["id"] if cust else None
        data = portal_views.job_detail(conn, pid)
        notes = portal_views.list_job_notes(conn, cid, pid) if cid else []
        overview = portal_views.get_job_overview(conn, cid, pid) if cid else ""
    return HTMLResponse(portal_views.render_job_page(data, t, v[2], notes, overview))
```
แก้เป็น:
```python
@app.get("/portal/job")
async def portal_job_get(t: str = "", pid: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        cid = cust["id"] if cust else None
        data = portal_views.job_detail(conn, pid)
        notes = portal_views.list_job_notes(conn, cid, pid) if cid else []
        overview = portal_views.get_job_overview(conn, cid, pid) if cid else ""
        starred = bool(cid) and pid in portal_views.starred_project_ids(conn, cid)
    return HTMLResponse(portal_views.render_job_page(data, t, v[2], notes, overview, starred))
```

- [ ] **Step 2: รัน test ยืนยันว่า pass (test นี้เขียนไว้แล้วใน Task 4 Step 1 — `bj` assertion ต้องผ่านจริงตอนนี้)**

Run: `python scripts/test_portal_routes.py`
Expected: `OK portal_star_toggle` (เหมือน Task 4 แต่ตอนนี้ assertion `"⭐" in bj` ผ่านเพราะ wiring ครบจริง — ถ้า Task 4 ทำ Step ตามลำดับ test นี้ผ่านไปแล้วตั้งแต่ Task 4; ขั้นนี้คือ sanity-rerun ยืนยันอีกครั้งหลังแก้ route)

- [ ] **Step 3: Commit**

```bash
git add scripts/bms_api.py
git commit -m "feat(portal): /portal/job ส่งสถานะ ⭐ ที่สนใจ เข้า render_job_page"
```

---

### Task 6: ปุ่มดาว + ชิป filter ใน Bid Board (`/portal`)

**Files:**
- Modify: `scripts/bms_api.py:384-458` (`_portal_jobs` — เติม `job["starred"]`)
- Modify: `scripts/bms_api.py:461-587` (`_portal_page_html` — CSS, chip filter, `_card`, JS)
- Modify: `scripts/test_portal_page.py` (เพิ่ม assertion)

**Interfaces:**
- Consumes: `portal_views.starred_project_ids` (Task 2)
- Produces: job dict มี key `starred: bool` เพิ่มจากเดิม

- [ ] **Step 1: เขียน test ที่ fail ก่อน**

เปิด `scripts/test_portal_page.py` ต่อท้ายไฟล์ (หลังบรรทัดสุดท้าย `print("OK test_portal_page")`) เพิ่ม:
```python
# --- ⭐ ที่สนใจ: ปุ่มดาวบนการ์ด + ชิป filter อิสระ ---
groups2 = dict(groups)
groups2["bidding"] = [dict(groups["bidding"][0], starred=True)]
groups2["pre"] = [dict(groups["pre"][0], starred=False)]
h2 = api._portal_page_html(groups2, 2000000000, "TOK")
assert "id=\"starchip\"" in h2 and "⭐ ที่สนใจ" in h2, "ต้องมีชิป filter ดาว"
assert "data-starred=\"1\"" in h2 and "data-starred=\"0\"" in h2, h2
assert "/portal/star_toggle?t=TOK&pid=PD&back=board" in h2, "ต้องมีลิงก์ toggle จากการ์ด"
assert "class=\"stagechip\"" in h2, "ชิป stage เดิมต้องมี class แยกจากดาว"
print("OK test_portal_page_star")
```

- [ ] **Step 2: รัน test ยืนยันว่า fail**

Run: `python scripts/test_portal_page.py`
Expected: `AssertionError: ต้องมีชิป filter ดาว`

- [ ] **Step 3: แก้ `_portal_jobs` ให้เติม `starred`**

หาบรรทัด (ท้ายฟังก์ชัน `_portal_jobs`):
```python
            elif ann == "D0":
                groups["bidding"].append(job)
            else:
                groups["pre"].append(job)
        return groups
```
แก้เป็น:
```python
            elif ann == "D0":
                groups["bidding"].append(job)
            else:
                groups["pre"].append(job)
        starred = portal_views.starred_project_ids(conn, cid)
        for g in groups.values():
            for job in g:
                job["starred"] = job["project_id"] in starred
        return groups
```

- [ ] **Step 4: แก้ CSS ใน `_portal_page_html`**

หาบรรทัด:
```python
        ".job{background:#fff;border-radius:14px;padding:14px 16px;margin:8px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}"
```
แก้เป็น:
```python
        ".job{position:relative;background:#fff;border-radius:14px;padding:14px 16px;margin:8px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}"
        ".star{position:absolute;top:10px;right:12px;font-size:18px;text-decoration:none;line-height:1;z-index:1}"
```

- [ ] **Step 5: แก้ chip-building block**

หาบรรทัด:
```python
    # ชิปเลือกประเภทงานที่อยากดู (single-select แบบแท็บ) — "ทั้งหมด" default, กดประเภท=ดูอันเดียว
    chips = []
    for key, clabel in (("bidding", "🔵 ยื่นซอง"), ("prelim", "📊 สรุปราคา"),
                        ("pre", "🟣 ประชาวิจารณ์"), ("won", "🏆 ผู้ชนะ")):
        if groups.get(key):
            chips.append(f"<button type=\"button\" class=\"fchip\" data-key=\"{key}\">{clabel}</button>")
    if len(chips) > 1:
        allchip = "<button type=\"button\" class=\"fchip on\" data-key=\"all\">ทั้งหมด</button>"
        body.append("<div class=\"filters\">" + allchip + "".join(chips) + "</div>")
    body.append("<div id=\"nohit\" class=\"nohit\">ไม่พบงานที่ตรงกับคำค้น</div>")
```
แก้เป็น:
```python
    # ชิปเลือกประเภทงานที่อยากดู (single-select แบบแท็บ) — "ทั้งหมด" default, กดประเภท=ดูอันเดียว
    chips = []
    for key, clabel in (("bidding", "🔵 ยื่นซอง"), ("prelim", "📊 สรุปราคา"),
                        ("pre", "🟣 ประชาวิจารณ์"), ("won", "🏆 ผู้ชนะ")):
        if groups.get(key):
            chips.append(f"<button type=\"button\" class=\"fchip stagechip\" data-key=\"{key}\">{clabel}</button>")
    filter_html = ""
    if len(chips) > 1:
        allchip = "<button type=\"button\" class=\"fchip stagechip on\" data-key=\"all\">ทั้งหมด</button>"
        filter_html += allchip + "".join(chips)
    # ⭐ ที่สนใจ — toggle อิสระ ไม่รวมกับ single-select stage ด้านบน (คนละชั้นกับ ⭐ ติดตามเดิม)
    filter_html += "<button type=\"button\" id=\"starchip\" class=\"fchip\">⭐ ที่สนใจ</button>"
    body.append("<div class=\"filters\">" + filter_html + "</div>")
    body.append("<div id=\"nohit\" class=\"nohit\">ไม่พบงานที่ตรงกับคำค้น</div>")
```

- [ ] **Step 6: แก้ `_card`**

หาบรรทัด (ท้ายฟังก์ชัน `_card`):
```python
        if kind != "won":
            L.append("<div class=\"more\">ดูรายละเอียด →</div>")
        href = f"/portal/job?t={_h.escape(token)}&pid={_h.escape(str(j['project_id']))}"
        return f"<a class=\"job joblink\" href=\"{href}\">" + "".join(L) + "</a>"
```
แก้เป็น:
```python
        if kind != "won":
            L.append("<div class=\"more\">ดูรายละเอียด →</div>")
        pid_esc = _h.escape(str(j["project_id"]))
        href = f"/portal/job?t={_h.escape(token)}&pid={pid_esc}"
        star_href = f"/portal/star_toggle?t={_h.escape(token)}&pid={pid_esc}&back=board"
        star_icon = "⭐" if j.get("starred") else "☆"
        star_link = f"<a class=\"star\" href=\"{star_href}\">{star_icon}</a>"
        joblink = f"<a class=\"joblink\" href=\"{href}\">" + "".join(L) + "</a>"
        starred_attr = "1" if j.get("starred") else "0"
        return f"<div class=\"job\" data-starred=\"{starred_attr}\">{star_link}{joblink}</div>"
```

- [ ] **Step 7: แก้ JS filter script**

หาบรรทัด:
```python
    body.append(
        "<script>(function(){"
        "var q=document.getElementById('q'),nh=document.getElementById('nohit');"
        "var chips=Array.prototype.slice.call(document.querySelectorAll('.fchip')),sel='all';"
        "function apply(){"
        "var s=q?q.value.trim().toLowerCase():'',tot=0;"
        "document.querySelectorAll('.gw').forEach(function(g){"
        "var k=g.getAttribute('data-key'),v=0;"
        "g.querySelectorAll('.job').forEach(function(c){"
        "var hit=!s||c.textContent.toLowerCase().indexOf(s)>=0;"
        "c.style.display=hit?'':'none';if(hit)v++;});"
        "var show=(sel==='all'||sel===k)&&v>0;"
        "g.style.display=show?'':'none';if(show)tot+=v;});"
        "if(nh)nh.style.display=tot?'none':'block';}"
        "if(q)q.addEventListener('input',apply);"
        "chips.forEach(function(c){c.addEventListener('click',function(){"
        "sel=c.getAttribute('data-key');"
        "chips.forEach(function(x){x.classList.toggle('on',x===c);});apply();});});"
        "apply();})();</script>")
```
แก้เป็น:
```python
    body.append(
        "<script>(function(){"
        "var q=document.getElementById('q'),nh=document.getElementById('nohit');"
        "var chips=Array.prototype.slice.call(document.querySelectorAll('.stagechip')),sel='all';"
        "var starchip=document.getElementById('starchip'),starOnly=false;"
        "function apply(){"
        "var s=q?q.value.trim().toLowerCase():'',tot=0;"
        "document.querySelectorAll('.gw').forEach(function(g){"
        "var k=g.getAttribute('data-key'),v=0;"
        "g.querySelectorAll('.job').forEach(function(c){"
        "var hit=(!s||c.textContent.toLowerCase().indexOf(s)>=0)&&(!starOnly||c.getAttribute('data-starred')==='1');"
        "c.style.display=hit?'':'none';if(hit)v++;});"
        "var show=(sel==='all'||sel===k)&&v>0;"
        "g.style.display=show?'':'none';if(show)tot+=v;});"
        "if(nh)nh.style.display=tot?'none':'block';}"
        "if(q)q.addEventListener('input',apply);"
        "chips.forEach(function(c){c.addEventListener('click',function(){"
        "sel=c.getAttribute('data-key');"
        "chips.forEach(function(x){x.classList.toggle('on',x===c);});apply();});});"
        "if(starchip)starchip.addEventListener('click',function(){"
        "starOnly=!starOnly;starchip.classList.toggle('on',starOnly);apply();});"
        "apply();})();</script>")
```

- [ ] **Step 8: รัน test ยืนยันว่า pass**

Run: `python scripts/test_portal_page.py`
Expected: `OK test_portal_page` แล้วต่อด้วย `OK test_portal_page_star`

- [ ] **Step 9: รัน regression เต็มของไฟล์ที่แก้ทั้งหมด**

Run: `python scripts/test_portal_notes.py && python scripts/test_portal_views.py && python scripts/test_portal_page.py && python scripts/test_portal_routes.py && python scripts/test_portal_stars.py`
Expected: ทุกไฟล์พิมพ์ `OK ...` ไม่มี `Traceback`/`AssertionError`

- [ ] **Step 10: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_page.py
git commit -m "feat(portal): ปุ่ม ⭐ ที่สนใจ + ชิป filter อิสระ ใน Bid Board"
```

---

### Task 7: Sophia sanity audit + ปิดงาน

**Files:** ไม่มีไฟล์ใหม่ — เป็น verification step

- [ ] **Step 1: Dispatch Sophia**

ใช้ Agent tool, `subagent_type: "sophia"`, prompt สรุปว่าแก้อะไรไปบ้าง (Task 1-6 ข้างบน) — เน้นให้ตรวจ:
- SQL ทุกจุดใน `job_stars` related code parameterized ครบ (ไม่มี string-format ใส่ SQL ตรง)
- `_h.escape` ครบทุกจุดที่ผู้ใช้ควบคุมได้ (project_id, token) ก่อนลง HTML
- `back` param validate เป็น `"board"`/`"job"` เท่านั้น ไม่เป็น open-redirect vector
- customer-scoping ถูกต้อง (toggle/read ผ่าน `cid` จาก token เสมอ ไม่รับ customer_id จาก query ตรงๆ)
- ไม่กระทบ `followed_jobs.starred_at` / LINE `star:<project_id>` postback เดิม

Expected: verdict `SAFE` (ถ้า `STOP` ต้องแก้ตามที่ Sophia ระบุก่อนไปต่อ)

- [ ] **Step 2: รัน regression สุดท้ายรวมทุกไฟล์ที่แก้**

Run: `python scripts/test_portal_notes.py && python scripts/test_portal_views.py && python scripts/test_portal_page.py && python scripts/test_portal_routes.py && python scripts/test_portal_stars.py`
Expected: ทุกไฟล์ `OK ...` ครบ

- [ ] **Step 3: บันทึก progress_log.md**

เพิ่ม entry ใหม่ใน `progress_log.md` ตามฟอร์แมตโปรเจกต์ (สถานะ ✅ เสร็จ, root cause/สิ่งที่ทำ = สรุป Task 1-6, fix/ผล = ตาราง+route+UI ใหม่, followup = รอ push/deploy)

- [ ] **Step 4: แจ้ง Discord**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "✅ ⭐ ที่สนใจ (Bid Board) เสร็จ — table job_stars + toggle route + ปุ่มดาว/ชิป filter, Sophia SAFE, test ผ่านครบ. รอคำสั่ง push/deploy")
```

**หมายเหตุ:** ไม่ commit ใน task นี้ (ไม่มีไฟล์โค้ดเปลี่ยนเพิ่ม) — push/deploy ขึ้น VPS ต้องรอคำสั่งคุณกัญจน์แยกตามปกติ
