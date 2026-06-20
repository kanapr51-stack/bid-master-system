# Portal Polish B — ไทม์ไลน์งานที่สร้างเอง (รางรถไฟ) + โน้ต Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** เพิ่มส่วน "ไทม์ไลน์ของฉัน" ในหน้า `/portal/job` ที่ user สร้างรายการเอง (วันที่ + สิ่งที่จะทำ) เรียงเป็นรางรถไฟ เพิ่ม/แก้/ลบได้ ต่อ user ต่องาน.

**Architecture:** ตาราง `job_notes` (ผ่าน migration ใน `Sebastian_Customer_DB`). Data layer + render ใน `scripts/portal_views.py` (รับ conn เป็น arg). `bms_api` enrich GET `/portal/job` (resolve customer + notes) + route POST `/portal/job/note` (add/edit/delete → redirect). ไม่มี JS (form POST + `<input type=date>` native).

**Tech Stack:** Python 3, FastAPI, sqlite3, follow_token. ไม่มี dependency ใหม่. เทสต์ = standalone assert script รันด้วย `PYTHONIOENCODING=utf-8 python scripts/<test>.py`.

## Global Constraints

- ตาราง `job_notes(id PK AUTOINCREMENT, customer_id INTEGER, project_id TEXT, entry_date TEXT 'YYYY-MM-DD', note TEXT, created_at TEXT, updated_at TEXT)`
- `portal_views` ห้าม import `bms_api`; data layer รับ `conn` เป็น argument
- เรียง entry ตาม `entry_date ASC, id ASC`
- ownership: edit/delete มี `WHERE id=? AND customer_id=?` เสมอ
- validate: `note` ต้องไม่ว่าง (strip), `entry_date` ต้อง parse 'YYYY-MM-DD' ได้ — ไม่งั้นข้าม (ไม่ INSERT/UPDATE)
- escape ทุก field ที่มาจาก DB/user ด้วย `html.escape` (ทั้ง text content และ value="" attribute)
- ไม่มี JavaScript (form POST ล้วน; date = `<input type="date">`)
- token: `follow_token.verify_token(t)` → `(user_id, project_id, exp)` หรือ `None`; invalid → `_follow_page_html(t, "invalid", {}, "", 0)`
- customer resolve จาก `SELECT id FROM customers WHERE line_user_id=?` (อาจ None → timeline ว่าง, write ข้าม)
- now timestamp = `datetime.now(TZ_TH).isoformat(timespec="seconds")` (TZ_TH มีใน portal_views แล้ว)
- เทสต์ print `OK <name>` เมื่อผ่าน

---

### Task 1: Schema — ตาราง job_notes (migration v128)

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py` (เพิ่ม `_migrate_v128` + เรียกใน `init_schema`)
- Test: `scripts/test_job_notes_schema.py`

**Interfaces:**
- Produces: ตาราง `job_notes` ถูกสร้างเมื่อเรียก `init_schema()`

- [ ] **Step 1: Write the failing test** (`scripts/test_job_notes_schema.py`)

```python
"""test_job_notes_schema.py — init_schema สร้างตาราง job_notes."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as c:
    cols = [r[1] for r in c.execute("PRAGMA table_info(job_notes)")]
assert cols, "ตาราง job_notes ไม่ถูกสร้าง"
for need in ["id", "customer_id", "project_id", "entry_date", "note", "created_at", "updated_at"]:
    assert need in cols, f"ขาดคอลัมน์ {need}: {cols}"
print("OK test_job_notes_schema")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_job_notes_schema.py`
Expected: FAIL — `AssertionError: ตาราง job_notes ไม่ถูกสร้าง`

- [ ] **Step 3: Implement**

3a. เพิ่มฟังก์ชัน migration ใหม่ (วางใกล้ `_migrate_v127`, เหนือมัน):

```python
def _migrate_v128():
    """job_notes — ไทม์ไลน์งานที่ user สร้างเอง (entry_date + note) ต่อ (customer, project). (2026-06-20)"""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_notes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id  INTEGER NOT NULL,
                project_id   TEXT NOT NULL,
                entry_date   TEXT NOT NULL,
                note         TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT
            )""")
```

3b. ใน `init_schema()` เพิ่มบรรทัดเรียก หลัง `_migrate_v127()`:

```python
    _migrate_v127()
    _migrate_v128()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_job_notes_schema.py`
Expected: PASS — `OK test_job_notes_schema`

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_Customer_DB.py scripts/test_job_notes_schema.py
git commit -m "feat(db): job_notes table migration v128 (PolishB t1)"
```

---

### Task 2: Data layer — list/add/edit/delete job notes

**Files:**
- Modify: `scripts/portal_views.py` (append helpers)
- Test: `scripts/test_portal_notes.py`

**Interfaces:**
- Consumes: `TZ_TH`, `datetime` (มีใน portal_views แล้ว)
- Produces:
  - `_valid_date(s) -> bool`
  - `list_job_notes(conn, customer_id, pid) -> list[dict]` (`[{"id","entry_date","note"}]`, sort entry_date asc,id asc; customer_id falsy → `[]`)
  - `add_job_note(conn, customer_id, pid, entry_date, note) -> None`
  - `edit_job_note(conn, customer_id, note_id, entry_date, note) -> None`
  - `delete_job_note(conn, customer_id, note_id) -> None`

- [ ] **Step 1: Write the failing test** (`scripts/test_portal_notes.py`)

```python
"""test_portal_notes.py — job_notes data layer (list/add/edit/delete + ownership)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _conn():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE job_notes(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, "
              "project_id TEXT, entry_date TEXT, note TEXT, created_at TEXT, updated_at TEXT)")
    return c


c = _conn()
# add 2 entries (วันหลังก่อน) → list ต้องเรียง asc
pv.add_job_note(c, 1, "PID", "2026-01-22", "โทรถามรายละเอียด")
pv.add_job_note(c, 1, "PID", "2026-01-21", "โทรหาช่าง")
lst = pv.list_job_notes(c, 1, "PID")
assert [x["entry_date"] for x in lst] == ["2026-01-21", "2026-01-22"], lst
assert lst[0]["note"] == "โทรหาช่าง", lst
# validate: note ว่าง / date ผิด → ไม่เพิ่ม
pv.add_job_note(c, 1, "PID", "2026-01-23", "   ")
pv.add_job_note(c, 1, "PID", "not-a-date", "x")
assert len(pv.list_job_notes(c, 1, "PID")) == 2, "ควรยังมี 2"
# edit ของตัวเอง
nid = lst[0]["id"]
pv.edit_job_note(c, 1, nid, "2026-01-21", "โทรหาช่างปูน")
assert pv.list_job_notes(c, 1, "PID")[0]["note"] == "โทรหาช่างปูน"
# ownership: customer อื่นแก้ไม่ได้
pv.edit_job_note(c, 999, nid, "2026-01-21", "HACKED")
assert pv.list_job_notes(c, 1, "PID")[0]["note"] == "โทรหาช่างปูน", "ห้ามแก้ของคนอื่น"
# delete ของคนอื่น → ไม่หาย ; ของตัวเอง → หาย
pv.delete_job_note(c, 999, nid)
assert len(pv.list_job_notes(c, 1, "PID")) == 2
pv.delete_job_note(c, 1, nid)
assert len(pv.list_job_notes(c, 1, "PID")) == 1
# customer None → []
assert pv.list_job_notes(c, None, "PID") == []
print("OK test_portal_notes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_notes.py`
Expected: FAIL — `AttributeError: ... 'add_job_note'`

- [ ] **Step 3: Implement** (append to `scripts/portal_views.py`)

```python
def _valid_date(s):
    try:
        datetime.strptime(str(s)[:10], "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _now_th():
    return datetime.now(TZ_TH).isoformat(timespec="seconds")


def list_job_notes(conn, customer_id, pid):
    if not customer_id:
        return []
    rows = conn.execute(
        "SELECT id, entry_date, note FROM job_notes WHERE customer_id=? AND project_id=? "
        "ORDER BY entry_date ASC, id ASC", (customer_id, pid)).fetchall()
    return [{"id": r["id"], "entry_date": r["entry_date"], "note": r["note"]} for r in rows]


def add_job_note(conn, customer_id, pid, entry_date, note):
    note = (note or "").strip()
    if not customer_id or not note or not _valid_date(entry_date):
        return
    now = _now_th()
    conn.execute(
        "INSERT INTO job_notes (customer_id, project_id, entry_date, note, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)", (customer_id, pid, str(entry_date)[:10], note, now, now))


def edit_job_note(conn, customer_id, note_id, entry_date, note):
    note = (note or "").strip()
    if not customer_id or not note or not _valid_date(entry_date):
        return
    try:
        note_id = int(note_id)
    except (TypeError, ValueError):
        return
    conn.execute(
        "UPDATE job_notes SET entry_date=?, note=?, updated_at=? WHERE id=? AND customer_id=?",
        (str(entry_date)[:10], note, _now_th(), note_id, customer_id))


def delete_job_note(conn, customer_id, note_id):
    if not customer_id:
        return
    try:
        note_id = int(note_id)
    except (TypeError, ValueError):
        return
    conn.execute("DELETE FROM job_notes WHERE id=? AND customer_id=?", (note_id, customer_id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_notes.py`
Expected: PASS — `OK test_portal_notes`

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_notes.py
git commit -m "feat(portal): job notes data layer + ownership (PolishB t2)"
```

---

### Task 3: Render — ส่วนไทม์ไลน์ (รางรถไฟ) ใน render_job_page

**Files:**
- Modify: `scripts/portal_views.py` (เพิ่ม `_render_timeline`, แก้ `render_job_page`, เพิ่ม CSS)
- Test: `scripts/test_portal_views.py` (append cases)

**Interfaces:**
- Consumes: `list_job_notes` output shape, `_fmt_date_th`
- Produces: `render_job_page(data, token, exp, notes=None)` (เพิ่มพารามิเตอร์ `notes`), `_render_timeline(pid, tok, notes) -> str`

- [ ] **Step 1: Write the failing test** (append to `scripts/test_portal_views.py` ก่อนบรรทัด `print("OK test_portal_views")`)

```python
# --- render_job_page: ไทม์ไลน์ของฉัน (รางรถไฟ) ---
c = _seed()
d = pv.job_detail(c, "69010000001")
notes = [{"id": 7, "entry_date": "2026-01-21", "note": "โทรหาช่าง <x>"}]
ht = pv.render_job_page(d, "TOK", 0, notes)
assert "🚂 ไทม์ไลน์ของฉัน" in ht, ht
assert "action=\"/portal/job/note\"" in ht and "type=\"date\"" in ht, ht   # ฟอร์มเพิ่ม
assert "21 ม.ค. 2569" in ht, ht                                            # วันที่ไทยบนราง
assert "โทรหาช่าง &lt;x&gt;" in ht, "escape โน้ตผิด"
assert "value=\"7\"" in ht, "ไม่มี note_id ในฟอร์มแก้/ลบ"
ht0 = pv.render_job_page(d, "TOK", 0, [])
assert "ยังไม่มีรายการ" in ht0, ht0
# ส่วนผู้ยื่นเดิมยังอยู่
assert "ผู้ยื่นทั้งหมด" in ht, ht
print("OK render_job_page_timeline")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: FAIL — `AssertionError` (ไม่มี "🚂 ไทม์ไลน์ของฉัน") หรือ TypeError (notes arg)

- [ ] **Step 3: Implement**

3a. เพิ่ม CSS rail ใน `_CSS` (ต่อท้ายก่อน `)` ปิด string — แทรกหลังบรรทัด `.jrow ...`):

```python
    ".nadd{display:flex;gap:6px;margin:8px 0;flex-wrap:wrap}"
    ".nadd input[type=text]{flex:1;min-width:120px}"
    ".nadd input,.nedit input,.nadd button,.nedit button,.ndel button{font-size:14px;padding:7px 9px;border:1px solid #ddd;border-radius:8px}"
    ".nadd button{background:#1db446;color:#fff;border:0}"
    ".rail{border-left:3px solid #1d72b4;margin:10px 0 10px 8px}"
    ".rstation{position:relative;padding:6px 0 12px 18px}"
    ".rstation::before{content:'';position:absolute;left:-9px;top:8px;width:13px;height:13px;border-radius:50%;background:#1d72b4;border:2px solid #fff}"
    ".rdate{font-size:13px;font-weight:700;color:#1d72b4;margin:0 0 4px}"
    ".nedit{display:inline-flex;gap:4px;flex-wrap:wrap}.ndel{display:inline}"
```

3b. เพิ่มฟังก์ชัน `_render_timeline` (วางเหนือ `render_job_page`):

```python
def _render_timeline(pid, tok, notes):
    pe = _h.escape(str(pid))
    out = ["<div class=\"bidhead\">🚂 ไทม์ไลน์ของฉัน</div>",
           f"<form class=\"nadd\" method=\"post\" action=\"/portal/job/note\">"
           f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
           f"<input type=\"hidden\" name=\"pid\" value=\"{pe}\">"
           f"<input type=\"hidden\" name=\"action\" value=\"add\">"
           f"<input type=\"date\" name=\"entry_date\" required>"
           f"<input type=\"text\" name=\"note\" placeholder=\"สิ่งที่จะทำ เช่น โทรหาช่าง\" required>"
           f"<button type=\"submit\">➕ เพิ่ม</button></form>"]
    if not notes:
        out.append("<div class=\"msg\">ยังไม่มีรายการ — เพิ่มด้านบนได้เลย</div>")
        return "".join(out)
    out.append("<div class=\"rail\">")
    for nt in notes:
        nid = _h.escape(str(nt["id"]))
        dlabel = _h.escape(_fmt_date_th(nt["entry_date"]))
        dval = _h.escape(str(nt["entry_date"])[:10])
        txt = _h.escape(nt["note"])
        out.append(
            f"<div class=\"rstation\"><div class=\"rdate\">{dlabel}</div>"
            f"<form class=\"nedit\" method=\"post\" action=\"/portal/job/note\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"pid\" value=\"{pe}\">"
            f"<input type=\"hidden\" name=\"note_id\" value=\"{nid}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"edit\">"
            f"<input type=\"date\" name=\"entry_date\" value=\"{dval}\">"
            f"<input type=\"text\" name=\"note\" value=\"{txt}\">"
            f"<button type=\"submit\">💾</button></form>"
            f"<form class=\"ndel\" method=\"post\" action=\"/portal/job/note\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"pid\" value=\"{pe}\">"
            f"<input type=\"hidden\" name=\"note_id\" value=\"{nid}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"delete\">"
            f"<button type=\"submit\">🗑</button></form></div>")
    out.append("</div>")
    return "".join(out)
```

3c. แก้ `render_job_page` — (1) signature เพิ่ม `notes=None`; (2) เลิก early-return ตอน bidders ว่าง — render ส่วนผู้ยื่นแบบมีเงื่อนไข แล้วต่อด้วย timeline เสมอ. แทนบล็อกตั้งแต่ `if not data["bidders"]:` จนถึง `return head + "".join(b) + _FOOT` ด้วย:

```python
    if not data["bidders"]:
        b.append("<div class=\"bidhead\">ยังไม่มีผู้ยื่น</div>")
        b.append("<div class=\"msg\">งานนี้ยังไม่มีข้อมูลผู้ยื่น — รอประมูล/ประกาศผล</div>")
    else:
        b.append(f"<div class=\"bidhead\">ผู้ยื่นทั้งหมด ({len(data['bidders'])} ราย)</div>")
        for i, bid in enumerate(data["bidders"], 1):
            wm = "🏆 " if bid["is_winner"] else ""
            sme = " 🏷SME" if bid["is_sme"] else ""
            nm = _h.escape(bid["name"] or "(ไม่ระบุชื่อ)")
            disc = f"ส่วนลด {bid['discount']:.1f}%" if bid["discount"] is not None else "—"
            cls = "brow bwin" if bid["is_winner"] else "brow"
            if bid["tin"]:
                link = (f"/portal/company?t={tok}&tin={_h.escape(bid['tin'])}"
                        f"&from={_h.escape(str(j['project_id']))}")
                nmhtml = f"<a class=\"bn blink\" href=\"{link}\">{i}. {wm}{nm}{sme}</a>"
            else:
                nmhtml = f"<span class=\"bn\">{i}. {wm}{nm}{sme}</span>"
            b.append(f"<div class=\"{cls}\">{nmhtml}"
                     f"<span class=\"bp\">{_baht(bid['price'])}<br><small>{disc}</small></span></div>")
    b.append(_render_timeline(j["project_id"], tok, notes or []))
    return head + "".join(b) + _FOOT
```

และแก้บรรทัด `def render_job_page(data, token, exp):` → `def render_job_page(data, token, exp, notes=None):`

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: PASS ทุกบรรทัด รวม `OK render_job_page_timeline` (และ `OK render_job_page` / `OK render_job_page_bidding` เดิมยังผ่าน — bidders ว่างไม่ early-return แล้วแต่ยังแสดง "ยังไม่มีผู้ยื่น")

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): timeline rail section in job page (PolishB t3)"
```

---

### Task 4: Routes — enrich GET + POST /portal/job/note

**Files:**
- Modify: `scripts/bms_api.py` (import `RedirectResponse`; แก้ `portal_job_get`; route ใหม่ `portal_job_note_post`)
- Test: `scripts/test_portal_routes.py` (append POST add/delete)

**Interfaces:**
- Consumes: `portal_views.{list_job_notes,add_job_note,edit_job_note,delete_job_note,job_detail,render_job_page}`, `follow_token.verify_token`, `get_conn`, `_follow_page_html`
- Produces: async `portal_job_note_post(request)`; `portal_job_get` ส่ง notes เข้า render

- [ ] **Step 1: Write the failing test** (append to `scripts/test_portal_routes.py` ก่อน `print("OK test_portal_routes")`)

```python
# --- POST /portal/job/note: add + list + delete ---
from starlette.requests import Request as _Req

async def _post(body):
    async def receive():
        return {"type": "http.request", "body": body.encode("utf-8"), "more_body": False}
    req = _Req({"type": "http", "method": "POST", "headers": []}, receive)
    return await api.portal_job_note_post(req)

from urllib.parse import urlencode
r1 = asyncio.run(_post(urlencode({"t": tok, "pid": "69010000001", "action": "add",
                                  "entry_date": "2026-01-21", "note": "โทรหาช่าง"})))
assert r1.status_code == 303, r1.status_code
body = asyncio.run(api.portal_job_get(t=tok, pid="69010000001")).body.decode("utf-8")
assert "โทรหาช่าง" in body and "21 ม.ค. 2569" in body, body[:400]
# delete: หา note_id จาก DB
import Sebastian_Customer_DB as _db
with _db.get_connection() as _c:
    nid = _c.execute("SELECT id FROM job_notes WHERE note='โทรหาช่าง'").fetchone()[0]
asyncio.run(_post(urlencode({"t": tok, "pid": "69010000001", "action": "delete", "note_id": str(nid)})))
body2 = asyncio.run(api.portal_job_get(t=tok, pid="69010000001")).body.decode("utf-8")
assert "โทรหาช่าง" not in body2, "ลบแล้วยังอยู่"
print("OK portal_job_note_post")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_routes.py`
Expected: FAIL — `AttributeError: ... 'portal_job_note_post'`

- [ ] **Step 3: Implement**

3a. แก้ import responses (บรรทัด `from fastapi.responses import HTMLResponse`):

```python
from fastapi.responses import HTMLResponse, RedirectResponse
```

3b. แทน body ของ `portal_job_get` (resolve customer + notes):

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
    return HTMLResponse(portal_views.render_job_page(data, t, v[2], notes))
```

3c. เพิ่ม route POST (วางหลัง `portal_company_get`):

```python
@app.post("/portal/job/note")
async def portal_job_note_post(request: Request):
    from urllib.parse import parse_qs, quote
    form = parse_qs((await request.body()).decode("utf-8"))
    g = lambda k: (form.get(k) or [""])[0]
    t = g("t")
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    pid, action = g("pid"), g("action")
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        cid = cust["id"] if cust else None
        if cid:
            if action == "add":
                portal_views.add_job_note(conn, cid, pid, g("entry_date"), g("note"))
            elif action == "edit":
                portal_views.edit_job_note(conn, cid, g("note_id"), g("entry_date"), g("note"))
            elif action == "delete":
                portal_views.delete_job_note(conn, cid, g("note_id"))
    return RedirectResponse(f"/portal/job?t={quote(t)}&pid={quote(pid)}", status_code=303)
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_routes.py`
Expected: PASS — `OK test_portal_routes` + `OK portal_job_note_post`
Regression: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py` ยังผ่าน

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_routes.py
git commit -m "feat(portal): GET enrich notes + POST /portal/job/note (PolishB t4)"
```

---

### Task 5: Deploy VPS + schema migrate + verify

**Files:** ไม่มีไฟล์ใหม่ — deploy 3 ไฟล์

- [ ] **Step 1: รัน full suite local ก่อน**

```bash
cd C:/Bid-Master-System
for t in test_job_notes_schema test_portal_notes test_portal_views test_portal_routes test_portal_page test_portal_jobs; do PYTHONIOENCODING=utf-8 python scripts/$t.py 2>&1 | tail -1; done
python -m py_compile scripts/portal_views.py scripts/bms_api.py scripts/Sebastian_Customer_DB.py
```
Expected: ทุก suite `OK ...`, compile เงียบ

- [ ] **Step 2: เช็ค VPS == HEAD ก่อน (normalize CRLF) สำหรับ 3 ไฟล์**

```bash
for f in Sebastian_Customer_DB portal_views bms_api; do
  echo "== $f =="
  ssh -i ~/.ssh/bms_vps root@45.76.156.166 "tr -d '\r' < /opt/bms/app/scripts/$f.py | sha256sum"
  git show HEAD:scripts/$f.py | tr -d '\r' | sha256sum
done
```
Expected: แต่ละคู่ hash ตรง (ไม่มี drift). ไม่ตรง — หยุด สืบก่อน

- [ ] **Step 3: backup + scp 3 ไฟล์ + init_schema + restart**

```bash
TS=$(date +%Y%m%d_%H%M%S)
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "for f in Sebastian_Customer_DB portal_views bms_api; do cp /opt/bms/app/scripts/\$f.py /opt/bms/app/scripts/\$f.py.bak_$TS; done"
scp -i ~/.ssh/bms_vps scripts/Sebastian_Customer_DB.py scripts/portal_views.py scripts/bms_api.py root@45.76.156.166:/opt/bms/app/scripts/
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cd /opt/bms/app && sudo -u bms BMS_DATA_DIR=/opt/bms/data BMS_DB_PATH=/opt/bms/data/bms_customers.db /opt/bms/venv/bin/python -c 'import sys;sys.path.insert(0,\"scripts\");import Sebastian_Customer_DB as db;db.init_schema();print(\"schema ok\")' && systemctl restart bms-api && sleep 2 && systemctl is-active bms-api"
```
Expected: `schema ok`, `active`

- [ ] **Step 4: verify schema + hash + import บน VPS**

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cd /opt/bms/app && sudo -u bms /opt/bms/venv/bin/python -c '
import sys; sys.path.insert(0,\"scripts\")
import sqlite3, bms_api, portal_views
c=sqlite3.connect(\"file:/opt/bms/data/bms_customers.db?mode=ro\",uri=True)
print(\"job_notes cols:\", [r[1] for r in c.execute(\"PRAGMA table_info(job_notes)\")])
print(\"import OK\")'"
for f in bms_api portal_views Sebastian_Customer_DB; do ssh -i ~/.ssh/bms_vps root@45.76.156.166 "tr -d '\r' < /opt/bms/app/scripts/$f.py | sha256sum"; git show HEAD:scripts/$f.py | tr -d '\r' | sha256sum; done
```
Expected: job_notes มี 7 คอลัมน์, import OK, แต่ละคู่ hash ตรง

- [ ] **Step 5: progress_log + Discord (schema change) + commit**

เพิ่ม entry `progress_log.md` (N+152) + ส่ง Discord 2 ข้อความ: (1) `🔧 Schema: เพิ่มตาราง job_notes (timeline โน้ตต่องาน)` (2) สรุปฟีเจอร์ LIVE. commit progress:

```bash
git add progress_log.md && git commit -m "docs(progress): N+152 PolishB job timeline+notes deployed"
```

---

## Self-Review

**Spec coverage:**
- §3 schema job_notes → Task 1 ✓
- §4 data layer (list/add/edit/delete + ownership + validate) → Task 2 ✓
- §5 render timeline rail + add/edit/delete forms + empty state → Task 3 ✓
- §6 routes (GET enrich customer+notes, POST add/edit/delete + redirect) → Task 4 ✓
- §7 edge cases (note ว่าง/date ผิด/ownership/customer None/escape) → Task 2+4 tests ✓
- §8 tests → test_job_notes_schema + test_portal_notes + test_portal_views + test_portal_routes ✓
- §9 deploy + init_schema + Discord schema notify → Task 5 ✓

**Placeholder scan:** ไม่มี — ทุก step มีโค้ดจริง

**Type consistency:** `list_job_notes` คืน `{id,entry_date,note}` ↔ `_render_timeline`/test ใช้ key เดียวกัน; `render_job_page(data,token,exp,notes=None)` ↔ route เรียกด้วย 4 args; POST form keys (`t,pid,action,note_id,entry_date,note`) ↔ `_render_timeline` ฟอร์ม + route `g()` ตรงกัน ✓

**หมายเหตุ:** Task 3 แก้ early-return เดิม (Polish A) ตอน bidders ว่าง → ต้องคง assert `render_job_page_bidding` ("ยังไม่มีผู้ยื่น") ให้ผ่าน (ยังแสดงข้อความเดิม แค่ไม่ return ก่อน timeline)
