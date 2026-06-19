# Portal หน้า detail งาน + ประวัติบริษัท (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่ม 2 หน้าใหม่ใน portal — `/portal/job` (รายละเอียดผู้ยื่นทุกราย + ส่วนลดจากราคากลาง) และ `/portal/company` (ประวัติบริษัท: สถิติ + กราฟ + timeline รายปี) แล้วเปลี่ยนการ์ดกลุ่มผู้ชนะให้ลิงก์ไปหน้า job แทน expand inline.

**Architecture:** โมดูลใหม่ `scripts/portal_views.py` ถือ data layer (query `bms_customers.db`) + render layer (HTML มือถือ-first, กราฟ inline CSS bar). `bms_api.py` เพิ่ม 2 route ที่ verify token เดิมแล้วเรียก `portal_views` (ส่ง `conn` เข้าไป กัน circular import). แก้ `_portal_page_html` ให้การ์ด won เป็นลิงก์.

**Tech Stack:** Python 3, FastAPI (route เดิม), sqlite3 (`bms_customers.db`), follow_token (signed token เดิม). ไม่มี dependency ใหม่. กราฟ = CSS `<div>` width%. เทสต์ = standalone assert script (โปรเจกต์ไม่มี pytest) รันด้วย `python scripts/<test>.py`.

## Global Constraints

- DB live = `bms_customers.db` (SQLite) เท่านั้น — ห้ามใช้ Postgres/`db_client`/`bid_history_queries.py` หรือ `winner_history.db`
- ตาราง: `bid_results(project_id, bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme)`, `projects_seen(project_id, project_name, budget, province)`, `project_locations(project_id, moi_name, province_name)`
- ปี = `project_id[:2]` → `2500+int` (เช่น `69`→2569); parse ไม่ได้ → กลุ่ม "ไม่ทราบปี" (key 0) ท้ายสุด
- ส่วนลด = `round((1 - price/budget)*100, 1)` เฉพาะ `budget > 0`; ไม่งั้น `None`
- `portal_views` **ห้าม import `bms_api`** (กัน circular) — data layer รับ `conn` เป็น argument
- escape ทุก field ที่มาจาก DB ด้วย `html.escape`
- เทสต์รันด้วย `PYTHONIOENCODING=utf-8 python scripts/<test>.py` คาดหวัง print `OK <name>` ตอนผ่าน
- token verify: `follow_token.verify_token(t)` → `(user_id, project_id, exp)` หรือ `None`; invalid → `_follow_page_html(t, "invalid", {}, "", 0)`

---

### Task 1: portal_views — helpers + `job_detail`

**Files:**
- Create: `scripts/portal_views.py`
- Test: `scripts/test_portal_views.py`

**Interfaces:**
- Produces:
  - `_to_float(v) -> float | None`
  - `_year_th(pid: str) -> int | None`
  - `_discount(price, budget) -> float | None`
  - `job_detail(conn, pid: str) -> dict | None` →
    `{"job": {"project_id","name","location","budget"}, "bidders": [{"name","tin","price","agree","is_winner","is_sme","discount"}]}`
    (bidders เรียง winner ก่อน→ราคา asc; `None` ถ้าไม่มีทั้ง bid_results และ projects_seen)

- [ ] **Step 1: Write the failing test** (`scripts/test_portal_views.py`)

```python
"""test_portal_views.py — job_detail + company_profile + render (Portal detail/company)."""
import os, sys, sqlite3, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _seed():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE projects_seen(project_id TEXT, project_name TEXT, budget REAL, province TEXT)")
    c.execute("CREATE TABLE bid_results(project_id TEXT, bidder_name TEXT, bidder_tin TEXT, "
              "price_proposal TEXT, price_agree TEXT, is_winner INT, is_sme INT)")
    c.execute("CREATE TABLE project_locations(project_id TEXT, moi_name TEXT, province_name TEXT)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000001','งานถนน A',1000000,'นครพนม')")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.เอ','T1','900000','900000',1,0)")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.บี','T2','800000','',0,1)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000002','งานไม่มีราคากลาง',0,'บึงกาฬ')")
    c.execute("INSERT INTO bid_results VALUES ('69010000002','หจก.เอ','T1','500000','',0,0)")
    return c


# --- job_detail ---
c = _seed()
d = pv.job_detail(c, "69010000001")
assert d["job"]["budget"] == 1000000 and d["job"]["name"] == "งานถนน A", d["job"]
assert len(d["bidders"]) == 2, d["bidders"]
assert d["bidders"][0]["is_winner"] and d["bidders"][0]["name"] == "หจก.เอ", d["bidders"]
assert d["bidders"][0]["discount"] == 10.0, d["bidders"][0]      # 1 - 900000/1000000
assert d["bidders"][1]["is_sme"] is True, d["bidders"][1]
d2 = pv.job_detail(c, "69010000002")
assert d2["bidders"][0]["discount"] is None, d2                  # budget=0
assert pv.job_detail(c, "NOPE") is None
print("OK job_detail")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'portal_views'`

- [ ] **Step 3: Write minimal implementation** (`scripts/portal_views.py`)

```python
"""portal_views.py — หน้า detail งาน + ประวัติบริษัท (Portal Phase 2b / Phase 1).
Query bms_customers.db (bid_results + projects_seen) — รับ conn จาก caller (กัน circular import).
Render มือถือ-first, กราฟ inline CSS bar (ไม่พึ่ง chart lib)."""
import html as _h
import sqlite3


def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _year_th(pid):
    s = str(pid or "")
    if len(s) >= 2 and s[:2].isdigit():
        return 2500 + int(s[:2])
    return None


def _discount(price, budget):
    if price and budget and budget > 0:
        return round((1 - price / budget) * 100, 1)
    return None


def job_detail(conn, pid):
    ps = conn.execute(
        "SELECT project_name, budget, province FROM projects_seen WHERE project_id=?",
        (pid,)).fetchone()
    rows = conn.execute(
        "SELECT bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme "
        "FROM bid_results WHERE project_id=?", (pid,)).fetchall()
    if not rows and not ps:
        return None
    budget = (ps["budget"] if ps else 0) or 0
    loc = ""
    try:
        l = conn.execute(
            "SELECT moi_name, province_name FROM project_locations WHERE project_id=?",
            (pid,)).fetchone()
        if l:
            moi = (l["moi_name"] or "") if "moi_name" in l.keys() else ""
            prov = (l["province_name"] or "") if "province_name" in l.keys() else ""
            loc = ((f"ต.{moi} " if moi else "") + (f"จ.{prov}" if prov else "")).strip()
    except sqlite3.OperationalError:
        loc = ""
    if not loc and ps and ps["province"]:
        loc = f"จ.{ps['province']}"
    bidders = []
    for r in rows:
        price = _to_float(r["price_proposal"])
        bidders.append({
            "name": r["bidder_name"] or "", "tin": r["bidder_tin"] or "",
            "price": price, "agree": _to_float(r["price_agree"]),
            "is_winner": bool(r["is_winner"]),
            "is_sme": bool(r["is_sme"] if "is_sme" in r.keys() else 0),
            "discount": _discount(price, budget)})
    bidders.sort(key=lambda b: (not b["is_winner"], b["price"] is None, b["price"] or 0))
    return {"job": {"project_id": pid, "name": (ps["project_name"] if ps else "") or pid,
                    "location": loc, "budget": budget}, "bidders": bidders}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: PASS — prints `OK job_detail`

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): portal_views.job_detail + helpers (Phase1 t1)"
```

---

### Task 2: portal_views — `company_profile`

**Files:**
- Modify: `scripts/portal_views.py` (append function)
- Test: `scripts/test_portal_views.py` (append cases)

**Interfaces:**
- Consumes: `_to_float`, `_year_th`, `_discount` (Task 1)
- Produces: `company_profile(conn, tin: str) -> dict | None` →
  `{"name","tin","is_sme","total_bids","wins","win_rate","provinces":[...],
    "discount_hist":[{"lo","hi","count"}], "discount_avg", "by_year":[{"year","bids","wins","jobs":[{"project_id","name","is_winner","price","discount"}]}]}`
  (by_year ปีใหม่→เก่า, ปีไม่ทราบ key0 ท้ายสุด; jobs ในปีเรียง project_id DESC; `None` ถ้าไม่มี bid)

- [ ] **Step 1: Write the failing test** (append to `scripts/test_portal_views.py` ก่อนบรรทัด `print("OK job_detail")` ออก แล้วต่อท้ายไฟล์)

```python
# --- company_profile ---
c = _seed()
c.execute("INSERT INTO projects_seen VALUES ('68010000003','งานเก่า',2000000,'นครพนม')")
c.execute("INSERT INTO bid_results VALUES ('68010000003','หจก.เอ','T1','1600000','1600000',1,0)")
p = pv.company_profile(c, "T1")
assert p["name"] == "หจก.เอ" and p["total_bids"] == 3, p          # T1 อยู่ 3 งาน
assert p["wins"] == 2 and p["win_rate"] == round(2/3*100, 1), p
assert set(p["provinces"]) == {"นครพนม", "บึงกาฬ"}, p["provinces"]
years = [g["year"] for g in p["by_year"]]
assert years == [2569, 2568], years                              # ใหม่→เก่า
assert sum(g["bids"] for g in p["by_year"]) == p["total_bids"], p["by_year"]
assert p["discount_avg"] is not None, p
assert sum(h["count"] for h in p["discount_hist"]) >= 1, p["discount_hist"]
assert pv.company_profile(c, "NOPE") is None
print("OK company_profile")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: FAIL — `AttributeError: module 'portal_views' has no attribute 'company_profile'`

- [ ] **Step 3: Write minimal implementation** (append to `scripts/portal_views.py`)

```python
def company_profile(conn, tin):
    rows = conn.execute(
        "SELECT br.project_id, br.bidder_name, br.price_proposal, br.is_winner, br.is_sme, "
        "ps.project_name, ps.budget, ps.province "
        "FROM bid_results br LEFT JOIN projects_seen ps ON ps.project_id=br.project_id "
        "WHERE br.bidder_tin=?", (tin,)).fetchall()
    if not rows:
        return None
    name = next((r["bidder_name"] for r in rows if r["bidder_name"]), "") or ""
    is_sme = any(bool(r["is_sme"]) for r in rows)
    total = len(rows)
    wins = sum(1 for r in rows if r["is_winner"])
    win_rate = round(wins / total * 100, 1) if total else 0.0
    provinces = sorted({r["province"] for r in rows if r["province"]})
    discs = []
    for r in rows:
        d = _discount(_to_float(r["price_proposal"]), (r["budget"] or 0))
        if d is not None:
            discs.append(d)
    hist = []
    for lo in range(0, 40, 5):
        hist.append({"lo": lo, "hi": lo + 5, "count": sum(1 for d in discs if lo <= d < lo + 5)})
    hist.append({"lo": 40, "hi": None, "count": sum(1 for d in discs if d >= 40)})
    disc_avg = round(sum(discs) / len(discs), 1) if discs else None
    years = {}
    for r in rows:
        y = _year_th(r["project_id"])
        g = years.setdefault(y or 0, {"year": y, "bids": 0, "wins": 0, "jobs": []})
        g["bids"] += 1
        if r["is_winner"]:
            g["wins"] += 1
        g["jobs"].append({"project_id": r["project_id"], "name": r["project_name"] or r["project_id"],
                          "is_winner": bool(r["is_winner"]), "price": _to_float(r["price_proposal"]),
                          "discount": _discount(_to_float(r["price_proposal"]), (r["budget"] or 0))})
    by_year = []
    for key in sorted(years, key=lambda k: (k == 0, -(k or 0))):
        g = years[key]
        g["jobs"].sort(key=lambda j: j["project_id"], reverse=True)
        by_year.append(g)
    return {"name": name, "tin": tin, "is_sme": is_sme, "total_bids": total, "wins": wins,
            "win_rate": win_rate, "provinces": provinces, "discount_hist": hist,
            "discount_avg": disc_avg, "by_year": by_year}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: PASS — prints `OK job_detail` then `OK company_profile`

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): portal_views.company_profile (Phase1 t2)"
```

---

### Task 3: portal_views — CSS/head + `render_job_page`

**Files:**
- Modify: `scripts/portal_views.py` (append constants + render fn)
- Test: `scripts/test_portal_views.py` (append render cases)

**Interfaces:**
- Consumes: `job_detail` output
- Produces:
  - `_HEAD(title) -> str`, `_FOOT -> str`, `_baht(x) -> str`
  - `render_job_page(data: dict | None, token: str, exp: int) -> str`

- [ ] **Step 1: Write the failing test** (append to `scripts/test_portal_views.py`)

```python
# --- render_job_page ---
c = _seed()
d = pv.job_detail(c, "69010000001")
h = pv.render_job_page(d, "TOK", 2000000000)
assert "งานถนน A" in h and "🆔 69010000001" in h, h
assert "ราคากลาง 1,000,000" in h, h
assert "/portal/company?t=TOK&tin=T1" in h and "from=69010000001" in h, h   # ลิงก์บริษัท
assert "ส่วนลด 10.0%" in h, h
assert "/portal?t=TOK" in h, "ไม่มีปุ่มกลับ"
h0 = pv.render_job_page(None, "TOK", 0)
assert "ไม่พบรายละเอียดงานนี้" in h0, h0
print("OK render_job_page")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: FAIL — `AttributeError: ... 'render_job_page'`

- [ ] **Step 3: Write minimal implementation** (append to `scripts/portal_views.py`)

```python
_CSS = (
    "body{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:18px;background:#f5f6f8;color:#222}"
    ".wrap{max-width:480px;margin:0 auto}"
    ".back{display:inline-block;font-size:14px;color:#1d72b4;text-decoration:none;margin:0 0 12px}"
    ".h{font-size:18px;font-weight:700;margin:2px 0 4px}"
    ".jid{font-size:12px;color:#aaa;margin:0 0 6px}"
    ".meta{font-size:13px;color:#777;margin:3px 0}"
    ".msg{font-size:15px;color:#555;margin:14px 0}"
    ".bidhead{font-size:14px;font-weight:700;color:#555;margin:16px 0 6px}"
    ".brow{display:flex;justify-content:space-between;gap:10px;font-size:13px;padding:8px 0;border-bottom:1px solid #eee}"
    ".brow .bn{flex:1;color:#333;text-decoration:none}.brow .bp{white-space:nowrap;text-align:right;color:#555}"
    ".brow .bp small{color:#999}"
    ".blink{color:#1d72b4 !important}"
    ".bwin{font-weight:700}.bwin .bn,.bwin .blink{color:#1a7f37 !important}.bwin .bp{color:#1a7f37}"
    ".card{background:#fff;border-radius:14px;padding:14px 16px;margin:8px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}"
    ".stats{display:flex;gap:8px;margin:10px 0}"
    ".stat{flex:1;background:#fff;border-radius:12px;padding:10px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.05)}"
    ".stat b{display:block;font-size:18px;color:#1d72b4}.stat span{font-size:11px;color:#888}"
    ".chart{background:#fff;border-radius:12px;padding:12px 14px;margin:10px 0;box-shadow:0 2px 8px rgba(0,0,0,.05)}"
    ".chart .ct{font-size:13px;font-weight:700;color:#555;margin:0 0 8px}"
    ".br2{display:flex;align-items:center;gap:8px;font-size:12px;margin:4px 0}"
    ".br2 .lab{width:64px;color:#666;white-space:nowrap}"
    ".br2 .track{flex:1;background:#eef0f3;border-radius:6px;height:14px;overflow:hidden}"
    ".br2 .fill{display:block;height:100%}"
    ".br2 .val{width:54px;text-align:right;color:#555;white-space:nowrap}"
    ".yhead{font-size:14px;font-weight:700;color:#333;margin:14px 0 4px}"
    ".jrow{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:6px 0;border-bottom:1px solid #f2f2f2}"
    ".jrow .jn{flex:1;color:#1d72b4;text-decoration:none}.jrow .jp{white-space:nowrap;text-align:right;color:#666}"
)


def _HEAD(title):
    return ("<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title><style>{_CSS}</style></head><body><div class=\"wrap\">")


_FOOT = "</div></body></html>"


def _baht(x):
    return f"{x:,.0f}" if x else "-"


def render_job_page(data, token, exp):
    tok = _h.escape(token)
    head = _HEAD("รายละเอียดงาน")
    back = f"<a class=\"back\" href=\"/portal?t={tok}\">← งานที่ติดตาม</a>"
    if not data:
        return head + back + "<div class=\"msg\">ไม่พบรายละเอียดงานนี้</div>" + _FOOT
    j = data["job"]
    b = [back, f"<div class=\"h\">🏗️ {_h.escape(j['name'])}</div>",
         f"<div class=\"jid\">🆔 {_h.escape(str(j['project_id']))}</div>"]
    if j["location"]:
        b.append(f"<div class=\"meta\">📍 {_h.escape(j['location'])}</div>")
    if j["budget"]:
        b.append(f"<div class=\"meta\">💰 ราคากลาง {_baht(j['budget'])} บาท</div>")
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
    return head + "".join(b) + _FOOT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: PASS — adds `OK render_job_page`

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): render_job_page + page CSS (Phase1 t3)"
```

---

### Task 4: portal_views — `render_company_page` (สถิติ + กราฟ + timeline)

**Files:**
- Modify: `scripts/portal_views.py` (append render fn + chart helper)
- Test: `scripts/test_portal_views.py` (append cases)

**Interfaces:**
- Consumes: `company_profile` output, `_HEAD/_FOOT/_baht` (Task 3)
- Produces:
  - `_bar(lab, value, maxv, color, val_txt) -> str` (CSS bar row)
  - `render_company_page(data: dict | None, token: str, from_pid: str, exp: int) -> str`

- [ ] **Step 1: Write the failing test** (append to `scripts/test_portal_views.py`)

```python
# --- render_company_page ---
c = _seed()
c.execute("INSERT INTO projects_seen VALUES ('68010000003','งานเก่า',2000000,'นครพนม')")
c.execute("INSERT INTO bid_results VALUES ('68010000003','หจก.เอ','T1','1600000','1600000',1,0)")
p = pv.company_profile(c, "T1")
h = pv.render_company_page(p, "TOK", "69010000001", 2000000000)
assert "หจก.เอ" in h, h
assert "ยื่น" in h and "ชนะ" in h and "win-rate" in h.lower() or "Win" in h or "ชนะ" in h, h
assert "ปี 2569" in h and "ปี 2568" in h, h                       # timeline แยกปี
assert "class=\"fill\"" in h, "ไม่มีกราฟ bar"
assert "/portal/job?t=TOK&pid=69010000001" in h, "ปุ่มกลับไปงานเดิม"
assert "/portal/job?t=TOK&pid=68010000003" in h, "ลิงก์งานใน timeline"
h0 = pv.render_company_page(None, "TOK", "", 0)
assert "ไม่พบประวัติบริษัทนี้" in h0, h0
print("OK render_company_page")
print("OK test_portal_views")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: FAIL — `AttributeError: ... 'render_company_page'`

- [ ] **Step 3: Write minimal implementation** (append to `scripts/portal_views.py`)

```python
def _bar(lab, value, maxv, color, val_txt):
    pct = int(value / maxv * 100) if maxv else 0
    return (f"<div class=\"br2\"><span class=\"lab\">{_h.escape(str(lab))}</span>"
            f"<span class=\"track\"><span class=\"fill\" style=\"width:{pct}%;background:{color}\"></span></span>"
            f"<span class=\"val\">{val_txt}</span></div>")


def render_company_page(data, token, from_pid, exp):
    tok = _h.escape(token)
    head = _HEAD("ประวัติบริษัท")
    if from_pid:
        back = f"<a class=\"back\" href=\"/portal/job?t={tok}&pid={_h.escape(str(from_pid))}\">← กลับไปงาน</a>"
    else:
        back = f"<a class=\"back\" href=\"/portal?t={tok}\">← งานที่ติดตาม</a>"
    if not data:
        return head + back + "<div class=\"msg\">ไม่พบประวัติบริษัทนี้</div>" + _FOOT
    sme = " 🏷SME" if data["is_sme"] else ""
    b = [back, f"<div class=\"h\">🏢 {_h.escape(data['name'] or '(ไม่ระบุชื่อ)')}{sme}</div>",
         f"<div class=\"jid\">{_h.escape(data['tin'])}</div>"]
    # stat cards
    b.append("<div class=\"stats\">"
             f"<div class=\"stat\"><b>{data['total_bids']}</b><span>ยื่น</span></div>"
             f"<div class=\"stat\"><b>{data['wins']}</b><span>ชนะ</span></div>"
             f"<div class=\"stat\"><b>{data['win_rate']:.0f}%</b><span>win-rate</span></div>"
             f"<div class=\"stat\"><b>{len(data['provinces'])}</b><span>จังหวัด</span></div>"
             "</div>")
    # chart 1: ยื่น/ชนะ รายปี
    maxb = max([g["bids"] for g in data["by_year"]] or [1])
    rows1 = []
    for g in data["by_year"]:
        ylab = f"ปี {g['year']}" if g["year"] else "ไม่ทราบปี"
        rows1.append(_bar(ylab, g["bids"], maxb, "#1d72b4", f"ยื่น {g['bids']}"))
        rows1.append(_bar("", g["wins"], maxb, "#1a7f37", f"ชนะ {g['wins']}"))
    b.append("<div class=\"chart\"><div class=\"ct\">📊 ยื่น–ชนะ รายปี</div>" + "".join(rows1) + "</div>")
    # chart 2: ส่วนลดที่ชอบเสนอ
    maxh = max([x["count"] for x in data["discount_hist"]] or [1])
    rows2 = []
    for x in data["discount_hist"]:
        lab = f"{x['lo']}-{x['hi']}%" if x["hi"] is not None else f"≥{x['lo']}%"
        rows2.append(_bar(lab, x["count"], maxh, "#c2410c", str(x["count"])))
    avg = f" (เฉลี่ย {data['discount_avg']:.1f}%)" if data["discount_avg"] is not None else ""
    b.append(f"<div class=\"chart\"><div class=\"ct\">💸 ส่วนลดที่ชอบเสนอ{avg}</div>" + "".join(rows2) + "</div>")
    # timeline แยกรายปี
    for g in data["by_year"]:
        ylab = f"ปี {g['year']}" if g["year"] else "ไม่ทราบปี"
        b.append(f"<div class=\"yhead\">{ylab} — ยื่น {g['bids']} ชนะ {g['wins']}</div>")
        b.append("<div class=\"card\">")
        for j in g["jobs"]:
            mark = "✅" if j["is_winner"] else "▫️"
            disc = f"ส่วนลด {j['discount']:.1f}%" if j["discount"] is not None else "—"
            link = f"/portal/job?t={tok}&pid={_h.escape(str(j['project_id']))}"
            b.append(f"<div class=\"jrow\"><a class=\"jn\" href=\"{link}\">{mark} {_h.escape(j['name'])}</a>"
                     f"<span class=\"jp\">{_baht(j['price'])}<br><small>{disc}</small></span></div>")
        b.append("</div>")
    return head + "".join(b) + _FOOT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_views.py`
Expected: PASS — adds `OK render_company_page` + `OK test_portal_views`

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): render_company_page + inline charts (Phase1 t4)"
```

---

### Task 5: bms_api — routes `/portal/job` + `/portal/company`

**Files:**
- Modify: `scripts/bms_api.py` (import + 2 routes; `from fastapi import ... Query`)
- Test: `scripts/test_portal_routes.py`

**Interfaces:**
- Consumes: `portal_views.job_detail/company_profile/render_job_page/render_company_page`, `follow_token.verify_token`, `get_conn`, `_follow_page_html`
- Produces: async route handlers `portal_job_get(t, pid)`, `portal_company_get(t, tin, from_)`

- [ ] **Step 1: Write the failing test** (`scripts/test_portal_routes.py`) — seed tmp DB เหมือน `test_portal_jobs.py`

```python
"""test_portal_routes.py — /portal/job + /portal/company ผ่าน async handler + token เดิม."""
import os, sys, asyncio, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as c:
    c.execute("INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('U','n','trial',1,'t','t')")
    c.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
              "VALUES ('69010000001','งานถนน A','D0','นครพนม',1000000,'t')")
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,is_sme,fetched_at) "
              "VALUES ('69010000001','หจก.เอ','T1','900000','900000',1,0,'t')")

import bms_api as api
import follow_token
tok = follow_token.make_token("U", None)

r = asyncio.run(api.portal_job_get(t=tok, pid="69010000001"))
body = r.body.decode("utf-8")
assert "งานถนน A" in body and "หจก.เอ" in body and "ส่วนลด 10.0%" in body, body[:400]

rc = asyncio.run(api.portal_company_get(t=tok, tin="T1", from_="69010000001"))
bodyc = rc.body.decode("utf-8")
assert "หจก.เอ" in bodyc and "ยื่น" in bodyc, bodyc[:400]

rbad = asyncio.run(api.portal_job_get(t="BAD", pid="69010000001"))
assert "ลิงก์ไม่ถูกต้อง" in rbad.body.decode("utf-8") or "ใช้ไม่ได้" in rbad.body.decode("utf-8")
print("OK test_portal_routes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_routes.py`
Expected: FAIL — `AttributeError: module 'bms_api' has no attribute 'portal_job_get'`

- [ ] **Step 3: Write minimal implementation**

3a. แก้ import บรรทัด `from fastapi import FastAPI, Request, Header, HTTPException` → เพิ่ม `Query`:

```python
from fastapi import FastAPI, Request, Header, HTTPException, Query
```

3b. เพิ่ม import โมดูลใกล้ `import follow_token`:

```python
import portal_views  # noqa: E402
```

3c. เพิ่ม 2 route ต่อจาก `portal_get` (หลังบรรทัด `return HTMLResponse(_portal_page_html(jobs, v[2]))`):

```python
@app.get("/portal/job")
async def portal_job_get(t: str = "", pid: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        data = portal_views.job_detail(conn, pid)
    return HTMLResponse(portal_views.render_job_page(data, t, v[2]))


@app.get("/portal/company")
async def portal_company_get(t: str = "", tin: str = "", from_: str = Query("", alias="from")):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        data = portal_views.company_profile(conn, tin)
    return HTMLResponse(portal_views.render_company_page(data, t, from_, v[2]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_routes.py`
Expected: PASS — prints `OK test_portal_routes`

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_routes.py
git commit -m "feat(portal): routes /portal/job + /portal/company (Phase1 t5)"
```

---

### Task 6: bms_api — การ์ด won → ลิงก์ (เลิก expand inline)

**Files:**
- Modify: `scripts/bms_api.py` — `_portal_page_html` (เพิ่มพารามิเตอร์ `token`, won card เป็นลิงก์, ลบ JS `.clickable`), caller `portal_get`
- Modify: `scripts/test_portal_page.py` (won = ลิงก์ ไม่ใช่ expand)

**Interfaces:**
- Consumes: `portal_views` (ทางอ้อมผ่านลิงก์ URL)
- Produces: `_portal_page_html(groups, exp_epoch=0, token="")` — signature เปลี่ยน (เพิ่ม token ท้าย)

- [ ] **Step 1: Update test first** (`scripts/test_portal_page.py`) — แทน assert ชุด clickable/detail เดิม

แก้บรรทัดเรียก: `h = api._portal_page_html(groups, 2000000000)` → `h = api._portal_page_html(groups, 2000000000, "TOK")`
ลบ 3 บรรทัด assert เดิม:
```python
assert "job clickable" in h and "ดูผู้ยื่นทั้งหมด (2 ราย)" in h, h
assert "class=\"detail\"" in h and "🏷SME" in h and "752,000" in h, h
assert "querySelectorAll('.clickable')" in h, "ไม่มี JS toggle"
```
ใส่แทน:
```python
# won card = ลิงก์ไปหน้า detail (ไม่ใช่ expand inline)
assert "/portal/job?t=TOK&pid=PW" in h, "การ์ด won ต้องลิงก์ไป detail"
assert "ดูผู้ยื่นทั้งหมด" in h and "querySelectorAll('.clickable')" not in h, h
assert "class=\"detail\"" not in h, "ต้องไม่มี expand inline แล้ว"
```
และแก้ assert หน้าว่างให้ส่ง token:
```python
h0 = api._portal_page_html({"won": [], "bidding": [], "pre": []}, 0, "TOK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_page.py`
Expected: FAIL — `_portal_page_html() takes ... positional arguments` หรือ assert ลิงก์ไม่เจอ

- [ ] **Step 3: Implement**

3a. เปลี่ยน signature:
```python
def _portal_page_html(groups: dict, exp_epoch: int = 0, token: str = "") -> str:
```

3b. ใน `_card` แทนทั้ง block `elif kind == "won":` (ตั้งแต่ badge ถึงก่อน `else:`) ด้วย:
```python
        elif kind == "won":
            L.append("<div class=\"dots\">●━━●━━●<span class=\"badge bw\">ประกาศผู้ชนะทางการ</span></div>")
            if j["winner"]:
                disc = f" (ลด {j['winner_disc']:.0f}%)" if j["winner_disc"] is not None else ""
                L.append(f"<div class=\"win\">🏆 {_h.escape(j['winner'])} · {_baht(j['winner_price'])}{disc}</div>")
            L.append("<div class=\"more\">ดูผู้ยื่นทั้งหมด →</div>")
```

3c. เปลี่ยน return ของ `_card` — won เป็นลิงก์ `<a>`:
```python
        if kind == "won":
            href = f"/portal/job?t={_h.escape(token)}&pid={_h.escape(str(j['project_id']))}"
            return f"<a class=\"job joblink\" href=\"{href}\">" + "".join(L) + "</a>"
        return "<div class=\"job\">" + "".join(L) + "</div>"
```
(ลบบรรทัดเดิม `cls = "job clickable" if ...` และ `return f"<div class=\"{cls}\">...`)

3d. เพิ่ม CSS `.joblink` ใกล้ `.clickable` (ลบ `.clickable/.more/.detail/.brow*/.bwin*` ที่เพิ่มใน N+149 ออก ยกเว้น `.more` ที่ reuse):
แก้บล็อก CSS ที่ N+149 เพิ่ม — แทนทั้งกลุ่มด้วย:
```python
        ".joblink{text-decoration:none;color:inherit;display:block}"
        ".more{font-size:13px;font-weight:600;color:#1d72b4;margin:8px 0 0}"
```
(เอา `.clickable .detail .brow .bwin` ออก — ไม่ใช้แล้ว)

3e. ลบ JS `.clickable` handler ในบล็อก `<script>` — เหลือเฉพาะ search filter:
แทน 6 บรรทัดท้าย script (ตั้งแต่ `"if(nh)nh.style.display=tot?'none':'block';});}"`) ด้วย:
```python
        "if(nh)nh.style.display=tot?'none':'block';});}})();</script>")
```
(ลบ `document.querySelectorAll('.clickable')...` ทั้งหมด)

3f. แก้ caller `portal_get`:
```python
    return HTMLResponse(_portal_page_html(jobs, v[2], t))
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 python scripts/test_portal_page.py && PYTHONIOENCODING=utf-8 python scripts/test_portal_jobs.py`
Expected: PASS ทั้งคู่
Run JS guard: render หน้าแล้ว `node --check` (สคริปต์เดียวกับ N+149) — ต้อง `JS SYNTAX OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_page.py
git commit -m "feat(portal): won card ลิงก์ไปหน้า detail (เลิก expand inline) (Phase1 t6)"
```

---

### Task 7: Deploy VPS + verify ของจริง

**Files:** ไม่มีไฟล์โค้ดใหม่ — deploy `bms_api.py` + `portal_views.py`

- [ ] **Step 1: เช็ค VPS == HEAD ก่อน (normalize CRLF)**

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "tr -d '\r' < /opt/bms/app/scripts/bms_api.py | sha256sum"
git show HEAD:scripts/bms_api.py | tr -d '\r' | sha256sum
```
Expected: hash ตรงกัน (ไม่มี hotfix ค้าง). ถ้าไม่ตรง — หยุด สืบก่อน

- [ ] **Step 2: backup + scp 2 ไฟล์**

```bash
TS=$(date +%Y%m%d_%H%M%S)
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cp /opt/bms/app/scripts/bms_api.py /opt/bms/app/scripts/bms_api.py.bak_$TS"
scp -i ~/.ssh/bms_vps scripts/bms_api.py scripts/portal_views.py root@45.76.156.166:/opt/bms/app/scripts/
```

- [ ] **Step 3: restart + verify import + hash**

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "tr -d '\r' < /opt/bms/app/scripts/bms_api.py | sha256sum && systemctl restart bms-api && sleep 2 && systemctl is-active bms-api && cd /opt/bms/app && sudo -u bms /opt/bms/venv/bin/python -c 'import sys;sys.path.insert(0,\"scripts\");import bms_api,portal_views;print(\"import OK\")'"
git show HEAD:scripts/bms_api.py | tr -d '\r' | sha256sum
```
Expected: `active`, `import OK`, hash bms_api == HEAD

- [ ] **Step 4: render หน้าใหม่กับ data จริง (read-only)**

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cd /opt/bms/app && sudo -u bms /opt/bms/venv/bin/python -c '
import sys; sys.path.insert(0,\"scripts\")
import sqlite3, portal_views as pv
c=sqlite3.connect(\"file:/opt/bms/data/bms_customers.db?mode=ro\",uri=True); c.row_factory=sqlite3.Row
pid=c.execute(\"SELECT project_id FROM bid_results WHERE is_winner=1 LIMIT 1\").fetchone()[0]
d=pv.job_detail(c,pid); print(\"job:\",len(d[\"bidders\"]),\"ผู้ยื่น\")
tin=d[\"bidders\"][0][\"tin\"]; p=pv.company_profile(c,tin)
print(\"company:\",p[\"name\"][:24],\"| ยื่น\",p[\"total_bids\"],\"ชนะ\",p[\"wins\"],\"| ปี\",[g[\"year\"] for g in p[\"by_year\"]])
print(\"render ok:\", \"กลับไปงาน\" in pv.render_company_page(p,\"TOK\",pid,0))
'"
```
Expected: เห็นจำนวนผู้ยื่น + ชื่อบริษัท + สถิติ + ปี + `render ok: True`

- [ ] **Step 5: progress_log + Discord + commit**

เพิ่ม entry `progress_log.md` (N+150) สรุป Phase 1 + ส่ง Discord `📝 Commit + deploy — Portal Phase 2b/1 (หน้า detail งาน + ประวัติบริษัท)`. ไม่ commit โค้ด (deploy แล้ว) — commit เฉพาะ progress_log:

```bash
git add progress_log.md && git commit -m "docs(progress): N+150 Portal Phase2b/1 detail+company deployed"
```

---

## Self-Review

**Spec coverage:**
- §5 หน้า job → Task 1 (data) + Task 3 (render) + Task 5 (route) ✓
- §6 หน้า company (สถิติ/กราฟ/timeline รายปี/ส่วนลด) → Task 2 + Task 4 + Task 5 ✓
- §7 แก้การ์ด won เป็นลิงก์ + เพิ่ม token param + ลบ inline → Task 6 ✓
- §4 โมดูลใหม่ portal_views, conn เป็น argument → Task 1-5 ✓
- §8 edge cases (budget=0, name ว่าง, ปี parse ไม่ได้, tin/pid ไม่พบ, token หมดอายุ) → ครอบใน Task 1/2/3/4/5 tests ✓
- §9 testing → test_portal_views + test_portal_routes + แก้ test_portal_page ✓
- §10 deploy 2 ไฟล์ + verify จริง → Task 7 ✓

**Placeholder scan:** ไม่มี TBD/“handle edge cases” ลอย — ทุก step มีโค้ดจริง ✓

**Type consistency:** `job_detail`→`render_job_page` (key job/bidders/discount), `company_profile`→`render_company_page` (key by_year/discount_hist/win_rate/provinces) ตรงกันทุก task; route เรียกชื่อฟังก์ชันตรง (`job_detail/company_profile/render_job_page/render_company_page`) ✓

**หมายเหตุ:** `_card` ใน N+149 มี `j["bidders"]` ที่ยังคงถูกสร้างใน `_portal_jobs` — Task 6 เลิกใช้ใน render (won เป็นลิงก์) แต่ไม่ลบ field ออกจาก data layer (คง `test_portal_jobs` bidders assertion ไว้ — surgical, ไม่กระทบ)
