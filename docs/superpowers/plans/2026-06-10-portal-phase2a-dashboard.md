# Portal Phase 2a — Read-Only Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เว็บหน้าเดียว read-only ที่ user เปิดดูงานที่ติดตามทั้งหมด — จัดกลุ่มตาม stage (กำลังประมูล/ประกาศผล/รับฟัง) + lifecycle + คาดราคา + ผู้ชนะ/คู่แข่ง. เข้าผ่าน LINE command "งานของฉัน".

**Architecture:** ต่อยอด `bms_api.py` (FastAPI) + `follow_token` เดิม. `GET /portal?t=<portal_token p=None>` → `_portal_jobs(user_id)` (query followed_jobs + join) → `_portal_page_html` (server-rendered, reuse style). webhook keyword → reply `_portal_link`.

**Tech Stack:** Python 3, FastAPI, sqlite3 (stdlib), follow_token (HMAC). test = standalone `python scripts\test_X.py`. portal token = `follow_token.make_token(user_id, None)`.

**Spec:** `docs/superpowers/specs/2026-06-10-portal-phase2a-dashboard-design.md`

**Verified facts (bms_api.py):**
- `follow_token` imported แล้ว (follow-link N+110). `verify_token(t)` → `(user_id, project_id, exp)` | None.
- `get_conn()` (sqlite Row), `_follow_page_html(token, state, d, deadline, exp_epoch)` (มี state "invalid"/"no_customer"), `_fmt_exp_th(exp)`, `HTMLResponse` imported.
- `reply_message(reply_token, text)` (line 90), webhook text handler มี `elif text_lower in (...)` chain (line ~700). `_now()`.
- `os` imported. ❌ `PUBLIC_BASE_URL` ยังไม่มีใน bms_api (sender มี) → Task 3 เพิ่ม.
- env Task 5 deploy: confirm กัญจน์ก่อน push. implementation log = N+114.

---

### Task 1: `_portal_jobs(user_id)` — query + group followed jobs

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่ม `_to_float` + `_portal_jobs` หลัง `_follow_page_html` ~line 339)
- Test: `scripts/test_portal_jobs.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_portal_jobs.py`:
```python
"""test_portal_jobs.py — _portal_jobs จัดกลุ่ม followed jobs (won/bidding/pre) + ซ่อน unfollowed."""
import os, sys, tempfile
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
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='U'").fetchone()[0]
    # 3 projects: D0 (bidding), W0 (won via bid_results), B0 (pre) + 1 unfollowed (hidden)
    for pid, ann, nm in [("PD","D0","ถนน D0"),("PW","D0","ถนน W"),("PB","B0","ถนน B0"),("PU","D0","ซ่อน")]:
        c.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
                  "VALUES (?,?,?,?,?,?)", (pid, nm, ann, "บึงกาฬ", 1000000, "t"))
    for pid, st in [("PD","active"),("PW","closed"),("PB","active"),("PU","unfollowed")]:
        c.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                  "VALUES (?,?,?,?,?,?)", (cid, pid, "t", "D0", "D0", st))
    # PW winner + competitors
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,fetched_at) "
              "VALUES ('PW','หจก.X','T1','740000','738000',1,'t')")
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,fetched_at) "
              "VALUES ('PW','หจก.Y','T2','752000','',0,'t')")
    # PD prediction + deadline
    c.execute("INSERT INTO price_predictions (project_id,budget,area_price_lo,area_price_hi,predicted_at) "
              "VALUES ('PD',1000000,679000,730000,'t')")
    try:
        c.execute("INSERT INTO project_locations (project_id,moi_name,deadline,created_at) VALUES ('PD','โพธิ์หมากแข้ง','15 มิ.ย. 2569','t')")
    except Exception:
        c.execute("UPDATE project_locations SET moi_name='โพธิ์หมากแข้ง', deadline='15 มิ.ย. 2569' WHERE project_id='PD'")

import bms_api as api
g = api._portal_jobs("U")
assert g is not None, g
assert [j["project_id"] for j in g["bidding"]] == ["PD"], g["bidding"]
assert [j["project_id"] for j in g["won"]] == ["PW"], g["won"]
assert [j["project_id"] for j in g["pre"]] == ["PB"], g["pre"]
# PU (unfollowed) ซ่อน
allpids = [j["project_id"] for grp in g.values() for j in grp]
assert "PU" not in allpids, allpids
# bidding มี prediction + deadline + location
bd = g["bidding"][0]
assert bd["pred_lo"] == 679000 and bd["pred_hi"] == 730000, bd
assert "15 มิ.ย." in bd["deadline"] and "โพธิ์หมากแข้ง" in bd["location"], bd
# won มี winner + competitor
w = g["won"][0]
assert w["winner"] == "หจก.X" and w["winner_price"] == 738000.0, w
assert w["winner_disc"] == 26.2, w               # (1-738000/1000000)*100
assert w["competitors"] and w["competitors"][0]["name"] == "หจก.Y", w
# ไม่มี customer → None
assert api._portal_jobs("NOPE") is None
print("OK test_portal_jobs")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_portal_jobs.py`
Expected: FAIL — `AttributeError: module 'bms_api' has no attribute '_portal_jobs'`

- [ ] **Step 3: Implement**

In `scripts/bms_api.py`, add after `_follow_page_html` (~line 339):
```python
def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _portal_jobs(user_id: str):
    """งานที่ user ติดตาม (active+closed) จัดกลุ่ม stage. คืน {won,bidding,pre} | None (ไม่มี customer).
    won = มีผู้ชนะ (bid_results) หรือ announce W* · bidding = D0 ยังไม่มีผล · pre = อื่น (B*)."""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return None
        cid = cust["id"]
        follows = conn.execute(
            "SELECT project_id FROM followed_jobs WHERE customer_id=? AND status IN ('active','closed')",
            (cid,)).fetchall()
        groups = {"won": [], "bidding": [], "pre": []}
        for f in follows:
            pid = f["project_id"]
            ps = conn.execute(
                "SELECT project_name, announce_type, province, budget FROM projects_seen WHERE project_id=?",
                (pid,)).fetchone()
            if not ps:
                continue
            try:
                loc = conn.execute(
                    "SELECT moi_name, deadline FROM project_locations WHERE project_id=?", (pid,)).fetchone()
            except sqlite3.OperationalError:
                loc = None
            moi = (loc["moi_name"] if loc and "moi_name" in loc.keys() else "") or ""
            deadline = (loc["deadline"] if loc and "deadline" in loc.keys() else "") or ""
            prov = ps["province"] or ""
            location = ((f"ต.{moi} " if moi else "") + (f"จ.{prov}" if prov else "")).strip()
            budget = ps["budget"] or 0
            pr = conn.execute(
                "SELECT area_price_lo, area_price_hi FROM price_predictions WHERE project_id=?", (pid,)).fetchone()
            results = conn.execute(
                "SELECT bidder_name, price_proposal, price_agree, is_winner FROM bid_results WHERE project_id=?",
                (pid,)).fetchall()
            ann = ps["announce_type"] or ""
            job = {"project_id": pid, "name": ps["project_name"] or pid, "location": location,
                   "deadline": deadline, "pred_lo": pr["area_price_lo"] if pr else None,
                   "pred_hi": pr["area_price_hi"] if pr else None,
                   "winner": None, "winner_price": None, "winner_disc": None, "competitors": []}
            win = next((r for r in results if r["is_winner"]), None)
            if win or ann.startswith("W"):
                if win:
                    wp = _to_float(win["price_agree"]) or _to_float(win["price_proposal"])
                    job["winner"] = win["bidder_name"]
                    job["winner_price"] = wp
                    if wp and budget:
                        job["winner_disc"] = round((1 - wp / budget) * 100, 1)
                    seen = set()
                    for r in results:
                        if r["is_winner"] or not r["bidder_name"] or r["bidder_name"] in seen:
                            continue
                        seen.add(r["bidder_name"])
                        job["competitors"].append({"name": r["bidder_name"], "price": _to_float(r["price_proposal"])})
                    job["competitors"] = job["competitors"][:3]
                groups["won"].append(job)
            elif ann == "D0":
                groups["bidding"].append(job)
            else:
                groups["pre"].append(job)
        return groups
```
(`sqlite3` ถูก import แล้วใน bms_api — ถ้าไม่มี เพิ่ม `import sqlite3` ที่ import block)

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_portal_jobs.py`
Expected: `OK test_portal_jobs`

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_jobs.py
git commit -m "feat(portal): _portal_jobs — followed jobs จัดกลุ่ม stage (won/bidding/pre) + winner/คาดราคา"
```
ต่อท้าย: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 2: `_portal_page_html(groups, exp_epoch)` — render HTML

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่มหลัง `_portal_jobs`)
- Test: `scripts/test_portal_page.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_portal_page.py`:
```python
"""test_portal_page.py — _portal_page_html render 3 กลุ่ม + winner + empty + escape."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_DB_PATH"] = str(Path(os.environ["BMS_DATA_DIR"]) / "x.db")
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import bms_api as api

groups = {
    "bidding": [{"project_id": "PD", "name": "ถนน คสล. บ้านนาสาร", "location": "ต.โพธิ์หมากแข้ง จ.บึงกาฬ",
                 "deadline": "15 มิ.ย. 2569", "pred_lo": 679000, "pred_hi": 730000,
                 "winner": None, "winner_price": None, "winner_disc": None, "competitors": []}],
    "won": [{"project_id": "PW", "name": "ถนน W", "location": "จ.บึงกาฬ", "deadline": "",
             "pred_lo": None, "pred_hi": None, "winner": "หจก.X", "winner_price": 738000.0,
             "winner_disc": 26.2, "competitors": [{"name": "หจก.Y", "price": 752000.0}]}],
    "pre": [{"project_id": "PB", "name": "<script>x</script>", "location": "จ.บึงกาฬ", "deadline": "",
             "pred_lo": None, "pred_hi": None, "winner": None, "winner_price": None,
             "winner_disc": None, "competitors": []}],
}
h = api._portal_page_html(groups, 2000000000)
assert "งานที่คุณติดตาม (3)" in h, h
assert "กำลังประมูล" in h and "ยื่นซอง 15 มิ.ย." in h and "679,000" in h, h
assert "ประกาศผล" in h and "หจก.X" in h and "738,000" in h and "ลด 26%" in h, h
assert "หจก.Y" in h, h
assert "&lt;script&gt;" in h and "<script>x" not in h, "escape ผิด"      # XSS escape
# empty
h0 = api._portal_page_html({"won": [], "bidding": [], "pre": []}, 0)
assert "ยังไม่มีงานที่ติดตาม" in h0, h0
print("OK test_portal_page")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_portal_page.py`
Expected: FAIL — no attribute `_portal_page_html`

- [ ] **Step 3: Implement**

In `scripts/bms_api.py`, add after `_portal_jobs`:
```python
def _portal_page_html(groups: dict, exp_epoch: int = 0) -> str:
    """HTML มือถือ-first — รายการงานติดตามจัดกลุ่ม stage. read-only."""
    import html as _h
    head = (
        "<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>งานที่ติดตาม</title><style>"
        "body{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:18px;background:#f5f6f8;color:#222}"
        ".wrap{max-width:480px;margin:0 auto}"
        ".h{font-size:19px;font-weight:700;margin:4px 0 14px}"
        ".grp{font-size:14px;font-weight:700;color:#555;margin:16px 0 8px}"
        ".job{background:#fff;border-radius:14px;padding:14px 16px;margin:8px 0;box-shadow:0 2px 10px rgba(0,0,0,.06)}"
        ".jn{font-size:15px;font-weight:600;margin:0 0 4px}"
        ".meta{font-size:13px;color:#888;margin:3px 0}"
        ".dl{font-size:13px;color:#d9534f;margin:3px 0}"
        ".win{font-size:14px;font-weight:600;color:#1a7f37;margin:3px 0}"
        ".dots{font-size:12px;color:#999;margin:4px 0}"
        ".badge{font-size:11px;padding:2px 8px;border-radius:10px;color:#fff;margin-left:6px}"
        ".bd{background:#1d72b4}.bw{background:#1a7f37}.bp{background:#b0883b}"
        ".msg{font-size:15px;color:#555;margin:12px 0}"
        ".exp{font-size:11px;color:#bbb;margin-top:18px;text-align:center}"
        "</style></head><body><div class=\"wrap\">"
    )
    foot = "</div></body></html>"
    n = sum(len(v) for v in groups.values())
    body = [f"<div class=\"h\">🗂 งานที่คุณติดตาม ({n})</div>"]
    if n == 0:
        body.append("<div class=\"msg\">ยังไม่มีงานที่ติดตาม — กดดาว ⭐ ในข้อความแจ้งเตือนเพื่อเริ่มติดตามครับ</div>")
        return head + "".join(body) + foot

    def _baht(x):
        return f"{x:,.0f}" if x else "-"

    def _card(j, kind):
        L = [f"<div class=\"jn\">🏗️ {_h.escape((j['name'] or '')[:80])}</div>"]
        if j["location"]:
            L.append(f"<div class=\"meta\">📍 {_h.escape(j['location'])}</div>")
        if kind == "bidding":
            L.append("<div class=\"dots\">●━━●━━○<span class=\"badge bd\">กำลังประมูล</span></div>")
            if j["deadline"]:
                L.append(f"<div class=\"dl\">⏰ ยื่นซอง {_h.escape(j['deadline'])}</div>")
            if j["pred_lo"] and j["pred_hi"]:
                L.append(f"<div class=\"meta\">💵 คาด {_baht(j['pred_lo'])}–{_baht(j['pred_hi'])} บาท</div>")
        elif kind == "won":
            L.append("<div class=\"dots\">●━━●━━●<span class=\"badge bw\">ประกาศผล</span></div>")
            if j["winner"]:
                disc = f" (ลด {j['winner_disc']:.0f}%)" if j["winner_disc"] is not None else ""
                L.append(f"<div class=\"win\">🏆 {_h.escape(j['winner'])} · {_baht(j['winner_price'])}{disc}</div>")
                if j["competitors"]:
                    comp = " · ".join(f"{_h.escape((c['name'] or '')[:18])} {_baht(c['price'])}" for c in j["competitors"])
                    L.append(f"<div class=\"meta\">👥 {comp}</div>")
        else:
            L.append("<div class=\"dots\">●━━○━━○<span class=\"badge bp\">รับฟังความเห็น</span></div>")
        return "<div class=\"job\">" + "".join(L) + "</div>"

    for key, label in (("bidding", "🔵 กำลังประมูล"), ("pre", "⭐ รับฟังความเห็น"), ("won", "🏆 ประกาศผลแล้ว")):
        if groups[key]:
            body.append(f"<div class=\"grp\">{label} ({len(groups[key])})</div>")
            for j in groups[key]:
                body.append(_card(j, key))
    exp_str = _fmt_exp_th(exp_epoch)
    if exp_str:
        body.append(f"<div class=\"exp\">🔗 ลิงก์นี้ใช้ได้ถึง {exp_str}</div>")
    return head + "".join(body) + foot
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_portal_page.py`
Expected: `OK test_portal_page`

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_page.py
git commit -m "feat(portal): _portal_page_html — การ์ดงานติดตามจัดกลุ่ม stage (มือถือ-first, escape)"
```
ต่อท้าย: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 3: `GET /portal` route + `_portal_link` + `PUBLIC_BASE_URL`

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่ม const + helper + route)

- [ ] **Step 1: เพิ่ม const + helper**

In `scripts/bms_api.py`, after `LINE_API = ...` (~line 35) add:
```python
PUBLIC_BASE_URL = os.getenv("BMS_PUBLIC_BASE_URL", "https://api.butler-bms.com")
```
After `_portal_page_html`, add:
```python
def _portal_link(user_id: str) -> str:
    """ลิงก์ portal ต่อ user (portal token p=None)."""
    return PUBLIC_BASE_URL.rstrip("/") + "/portal?t=" + follow_token.make_token(user_id, None)
```

- [ ] **Step 2: เพิ่ม route** — หลัง `@app.get("/follow")`/`follow_get` (ก่อน `@app.post("/follow")` หรือใกล้กัน):
```python
@app.get("/portal")
async def portal_get(t: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    jobs = _portal_jobs(v[0])
    if jobs is None:
        return HTMLResponse(_follow_page_html(t, "no_customer", {}, "", v[2]))
    return HTMLResponse(_portal_page_html(jobs, v[2]))
```

- [ ] **Step 3: import-sanity (route + helper)**

Run: `python -c "import os; os.environ['BMS_DB_PATH']='x'; os.environ.setdefault('BMS_FOLLOW_SECRET','s'); import sys; sys.path.insert(0,'scripts'); import bms_api; print([r.path for r in bms_api.app.routes if getattr(r,'path','')=='/portal'], bms_api._portal_link('U')[:40])"`
Expected: `['/portal'] https://api.butler-bms.com/portal?t=` (route ลงทะเบียน + link ขึ้นต้นถูก)

- [ ] **Step 4: Commit**

```bash
git add scripts/bms_api.py
git commit -m "feat(portal): GET /portal route + _portal_link (portal token p=None) + PUBLIC_BASE_URL"
```
ต่อท้าย: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 4: webhook keyword "งานของฉัน" → reply portal link

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่ม elif ใน webhook text handler ~line 700-725)

- [ ] **Step 1: เพิ่ม keyword branch**

In `scripts/bms_api.py` webhook message handler — ในกลุ่ม `# --- normal commands ---` (หลัง `elif text_lower in ("ตั้งค่า"...)` หรือก่อน else สุดท้าย) เพิ่ม:
```python
            elif text_lower in ("งานของฉัน", "งานที่ติดตาม", "portal", "พอร์ทัล", "ติดตาม"):
                await reply_message(reply_token, "🗂 ดูงานที่ติดตามทั้งหมด:\n" + _portal_link(user_id))
```
(text_lower = text_in.lower(); ภาษาไทย .lower() ไม่เปลี่ยน → match ได้. user_id มีใน scope ของ event loop แล้ว)

- [ ] **Step 2: เพิ่มคำสั่งใน help text** — หา `_help_text()` แล้วเพิ่มบรรทัด "🗂 งานของฉัน — ดูงานที่ติดตามทั้งหมด" (ถ้า _help_text เป็น f-string/list ให้แทรกบรรทัด; ถ้าหาไม่เจอ ข้าม step นี้ได้ ไม่บล็อก)

- [ ] **Step 3: import-sanity**

Run: `python -c "import os; os.environ['BMS_DB_PATH']='x'; os.environ.setdefault('BMS_FOLLOW_SECRET','s'); import sys; sys.path.insert(0,'scripts'); import bms_api; print('import OK')"`
Expected: `import OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/bms_api.py
git commit -m "feat(portal): webhook keyword 'งานของฉัน' → reply ลิงก์ portal"
```
ต่อท้าย: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 5: Local sanity + deploy + e2e + docs

**Files:** none (verification) + progress/memory. ⚠️ **confirm กัญจน์ก่อน push**

- [ ] **Step 1: รัน test ทั้งชุด**
```bash
python scripts\test_portal_jobs.py
python scripts\test_portal_page.py
python scripts\test_bms_follow.py
python scripts\test_follow_token.py
```
Expected: ทุกตัว OK/PASS (regression follow เดิมไม่พัง)

- [ ] **Step 2: confirm push (GATE)** — ถามกัญจน์ "deploy portal ได้ไหม" รอ OK

- [ ] **Step 3: Push + VPS pull + restart bms-api**
```bash
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main 2>&1 | tail -3 && sudo systemctl restart bms-api && sleep 2 && systemctl is-active bms-api"
```
Expected: `active`

- [ ] **Step 4: e2e — portal page จริง (กัญจน์ customer 2)**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "set -a; . /opt/bms/app/.env; set +a; /opt/bms/venv/bin/python -c \"
import sys; sys.path.insert(0,'/opt/bms/app/scripts'); import follow_token as ft
print(ft.make_token('REPLACE_KANJANA_LINE_USER_ID', None))\""
```
เอา token ยิง: `curl -s "https://api.butler-bms.com/portal?t=<TOKEN>" | grep -oE "งานที่คุณติดตาม|กำลังประมูล|ประกาศผล"`
Expected: เจอหัวข้อ + กลุ่ม (กัญจน์ติดตาม 69059075454 อยู่ → ควรเห็น). ยืนยันพิมพ์ "งานของฉัน" ใน LINE จริงได้ลิงก์

- [ ] **Step 5: progress_log + memory + Discord**
- progress_log `## งานที่ N+114: Portal Phase 2a (dashboard read-only) LIVE`
- memory: อัปเดต `project_resume_follow_link` (Portal 2a LIVE, 2b=โน้ต) + MEMORY.md
- Discord: "✅ Portal 2a LIVE — เว็บดูงานติดตามทั้งหมด (กลุ่ม stage + คาดราคา + ผู้ชนะ). พิมพ์ 'งานของฉัน' ใน LINE. โน้ต=2b"
```bash
git add progress_log.md && git commit -m "docs(progress): N+114 — Portal Phase 2a dashboard LIVE"
```

---

## Self-Review

**Spec coverage:**
- `_portal_jobs` (query+group won/bidding/pre, ซ่อน unfollowed) → Task 1 ✅
- `_portal_page_html` (3 กลุ่ม + lifecycle dots + winner + empty + escape) → Task 2 ✅
- `GET /portal` (verify token → portal | invalid/no_customer reuse) + `_portal_link` (p=None) → Task 3 ✅
- webhook keyword "งานของฉัน" → reply link → Task 4 ✅
- deploy + e2e (restart bms-api, curl portal) → Task 5 ✅
- edge cases (no customer→None→no_customer page, empty→empty state, unfollowed ซ่อน, data หาย graceful via _to_float/None checks) → Task 1/2 ✅

**Placeholder scan:** ไม่มี TBD. `REPLACE_KANJANA_LINE_USER_ID` (Task 5) = runtime value (customer 2 line_user_id จริง — query บน VPS ตอน deploy). Task 4 Step 2 (_help_text) มี fallback "ข้ามได้" — ไม่บล็อก.

**Type consistency:** `_portal_jobs` คืน `{won,bidding,pre}` (list ของ job dict {project_id,name,location,deadline,pred_lo,pred_hi,winner,winner_price,winner_disc,competitors}) — ใช้ตรงใน Task 2 `_portal_page_html` (อ่าน key เดียวกัน) + Task 1 test. `_portal_link(user_id)` คืน str — ใช้ใน Task 3 route + Task 4 webhook. `verify_token` คืน `(user_id, project_id, exp)` — Task 3 ใช้ v[0], v[2]. reuse `_follow_page_html(token,state,d,deadline,exp)` states "invalid"/"no_customer" (มีจริง).

**ความเสี่ยง (ไม่ใช่ placeholder):** Task 1 — project_locations schema (moi_name/deadline columns) — test มี try/except + `in loc.keys()` guard กัน column หาย. Task 4 — webhook handler indentation (อยู่ใน for-event/elif chain) — implementer ต้องวาง elif ระดับเดียวกับ command อื่น (อ่าน ~line 700 ก่อน). restart bms-api จำเป็น (route ใหม่ daemon).
