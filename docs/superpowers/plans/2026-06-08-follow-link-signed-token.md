# Follow-link (signed-token toggle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** แทน quick-reply ⭐ ด้วยลิงก์ติดตามต่องาน (signed token) ในเนื้อข้อความ D0 → หน้าเว็บ toggle (ติดตาม/ยกเลิก) ตามสถานะจริง — อุด multi-job quick-reply gap (N+108) โดยไม่ใช้ LIFF

**Architecture:** Sender มินต์ HMAC token (userId+projectId+exp) แทรกเป็นลิงก์ `https://api.butler-bms.com/follow?t=…` รายคน → FastAPI ตัวเดิม (bms_api.py) เพิ่ม GET/POST `/follow` verify token → แสดงหน้า HTML toggle → POST บันทึก `followed_jobs` (reuse `_record_follow`, เพิ่ม `_record_unfollow`). Token stateless ไม่เก็บ DB; ข้อมูล follow อยู่ถาวรใน DB ไม่ขึ้นกับ token expiry.

**Tech Stack:** Python 3, FastAPI, sqlite3 (stdlib), hmac/hashlib/base64 (stdlib). ไม่เพิ่ม dependency (POST parse ด้วย `urllib.parse.parse_qs` เลี่ยง python-multipart)

**Spec:** `docs/superpowers/specs/2026-06-08-follow-link-signed-token-design.md`

**Environment notes:**
- ทุก test = standalone script รันด้วย `python scripts\test_X.py` (exit 0 + print OK = ผ่าน) ตาม convention เดิม (`test_followed_jobs.py`)
- VPS **ไม่มี sqlite3 CLI** → sanity/inspection ใช้ `python3 -c …`
- VPS env: `bms-api.service` + `bms-line-sender.service` ใช้ `EnvironmentFile=/opt/bms/app/.env`, `WorkingDirectory=/opt/bms/app`
- ❌ ห้าม push remote โดยไม่ confirm กัญจน์ (CLAUDE.md) — Task 6 มี gate

---

### Task 1: `follow_token.py` — stateless HMAC token

**Files:**
- Create: `scripts/follow_token.py`
- Test: `scripts/test_follow_token.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_follow_token.py`:

```python
"""test_follow_token.py — HMAC token mint/verify: roundtrip, tamper, expiry, portal token."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import follow_token as ft

SECRET = "test-secret-123"
EXP = 1000 + 120 * 86400

# roundtrip (follow token มี project_id)
t = ft.make_token("Uabc", "P1", secret=SECRET, now=1000)
assert ft.verify_token(t, secret=SECRET, now=1000) == ("Uabc", "P1", EXP), ft.verify_token(t, secret=SECRET, now=1000)

# tamper 1 char → reject
bad = t[:-1] + ("A" if t[-1] != "A" else "B")
assert ft.verify_token(bad, secret=SECRET, now=1000) is None

# wrong secret → reject
assert ft.verify_token(t, secret="other", now=1000) is None

# expired → reject
assert ft.verify_token(t, secret=SECRET, now=EXP + 1) is None

# portal token (p=None) → roundtrip
pt = ft.make_token("Uabc", None, secret=SECRET, now=1000)
assert ft.verify_token(pt, secret=SECRET, now=1000) == ("Uabc", None, EXP)

# garbage / empty → None (ไม่ throw)
assert ft.verify_token("", secret=SECRET) is None
assert ft.verify_token("no-dot-here", secret=SECRET) is None

# missing secret → make_token raises
try:
    ft.make_token("Uabc", "P1", secret="")
    assert False, "should raise RuntimeError"
except RuntimeError:
    pass

print("OK test_follow_token")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_follow_token.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'follow_token'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/follow_token.py`:

```python
"""follow_token.py — stateless signed token สำหรับ follow-link (HMAC, ไม่เก็บ DB).

payload = {"u": user_id, "p": project_id|None, "e": exp_epoch}
token   = base64url(json(payload)) + "." + base64url(hmac_sha256(secret, payload_b64))

p=None  → portal-level token (Phase 2). follow-link ส่ง project_id เสมอ.
secret  = env BMS_FOLLOW_SECRET (sender มินต์ + bms_api verify แชร์ secret เดียวกัน).
"""
import base64
import hashlib
import hmac
import json
import os
import time

_SECRET = os.getenv("BMS_FOLLOW_SECRET", "")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_b64: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(sig)


def make_token(user_id: str, project_id: str = None, ttl_days: int = 120,
               secret: str = None, now: int = None) -> str:
    secret = _SECRET if secret is None else secret
    if not secret:
        raise RuntimeError("BMS_FOLLOW_SECRET not set")
    now = int(time.time()) if now is None else now
    payload = {"u": user_id, "p": project_id, "e": now + ttl_days * 86400}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return payload_b64 + "." + _sign(payload_b64, secret)


def verify_token(token: str, secret: str = None, now: int = None):
    """คืน (user_id, project_id, exp_epoch) หรือ None ถ้า sig ผิด/หมดอายุ/รูปแบบเสีย."""
    secret = _SECRET if secret is None else secret
    if not secret or not token or "." not in token:
        return None
    payload_b64, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload_b64, secret), sig):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        return None
    e = payload.get("e")
    if not isinstance(e, int):
        return None
    now = int(time.time()) if now is None else now
    if e <= now:
        return None
    return payload.get("u"), payload.get("p"), e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_follow_token.py`
Expected: `OK test_follow_token` (exit 0)

- [ ] **Step 5: Commit**

```bash
git add scripts/follow_token.py scripts/test_follow_token.py
git commit -m "feat(follow): follow_token.py — stateless HMAC signed token + tests"
```

---

### Task 2: `bms_api.py` — DB_PATH override + follow status/record/render helpers

**Files:**
- Modify: `scripts/bms_api.py` (DB_PATH ~line 24; add `import sys`/`HTMLResponse`; new helpers after `_record_follow` ~line 237)
- Test: `scripts/test_bms_follow.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_bms_follow.py`:

```python
"""test_bms_follow.py — _follow_status / _record_follow / _record_unfollow / _follow_page_html."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id, display_name, tier, active, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?)", ("Uabc", "Test", "trial", 1, "2026-06-08T10:00:00", "2026-06-08T10:00:00"))
    conn.execute("INSERT INTO projects_seen (project_id, project_name, announce_type, province, budget) "
                 "VALUES (?,?,?,?,?)", ("P1", "งานทดสอบถนน", "D0", "นครพนม", 5000000))

import bms_api as api

# ยังไม่ติดตาม → inactive
assert api._follow_status("Uabc", "P1") == "inactive"
# follow → active
api._record_follow("Uabc", "P1")
assert api._follow_status("Uabc", "P1") == "active"
# unfollow → inactive (status='unfollowed')
res = api._record_unfollow("Uabc", "P1")
assert res and res[1] == "P1", res
assert api._follow_status("Uabc", "P1") == "inactive"
# re-follow → active อีกครั้ง (ON CONFLICT reactivate)
api._record_follow("Uabc", "P1")
assert api._follow_status("Uabc", "P1") == "active"
# ลูกค้าไม่รู้จัก → no_customer
assert api._follow_status("Uxxx", "P1") == "no_customer"

# HTML render — 3 สถานะ
d = api._project_detail("P1")
h_active = api._follow_page_html("tok", "active", d, "8 มิ.ย. 09:00", 2000000000)
assert "ยกเลิกการติดตาม" in h_active and "งานทดสอบถนน" in h_active and "ลิงก์นี้ใช้ได้ถึง" in h_active
h_inactive = api._follow_page_html("tok", "inactive", d, "", 2000000000)
assert "ติดตามงานนี้" in h_inactive and "ยกเลิกการติดตาม" not in h_inactive
h_nocust = api._follow_page_html("tok", "no_customer", {}, "", 2000000000)
assert "เพิ่มเพื่อน" in h_nocust
h_invalid = api._follow_page_html("tok", "invalid", {}, "", 0)
assert ("หมดอายุ" in h_invalid) or ("ไม่ถูกต้อง" in h_invalid)

print("OK test_bms_follow")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_bms_follow.py`
Expected: FAIL — `AttributeError: module 'bms_api' has no attribute '_follow_status'` (หรือ DB_PATH ชี้ /opt/bms ไม่เจอ)

- [ ] **Step 3a: Make DB_PATH overridable + add imports**

In `scripts/bms_api.py`, change line 24:

```python
DB_PATH              = Path("/opt/bms/data/bms_customers.db")
```

to:

```python
DB_PATH              = Path(os.getenv("BMS_DB_PATH", "/opt/bms/data/bms_customers.db"))
```

Add `import sys` to the import block (after `import os`, ~line 14) and add the FastAPI response import + follow_token import. Change:

```python
import httpx
from fastapi import FastAPI, Request, Header, HTTPException
```

to:

```python
import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).parent))
import follow_token  # noqa: E402
```

- [ ] **Step 3b: Add helpers after `_record_follow` (after ~line 237)**

Insert immediately after the `_record_follow` function:

```python
def _record_unfollow(user_id: str, project_id: str):
    """ยกเลิกติดตาม → followed_jobs.status='unfollowed' (แยกจาก system 'closed'). คืน (pname, pid) | None."""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return None
        conn.execute(
            "UPDATE followed_jobs SET status='unfollowed' WHERE customer_id=? AND project_id=?",
            (cust["id"], project_id))
        row = conn.execute(
            "SELECT project_name FROM projects_seen WHERE project_id=?", (project_id,)).fetchone()
        pname = (row["project_name"] if row else "") or project_id
    return pname, project_id


def _follow_status(user_id: str, project_id: str) -> str:
    """'active' (กำลังติดตาม) | 'inactive' (unfollowed/closed/ไม่มี row) | 'no_customer'."""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return "no_customer"
        row = conn.execute(
            "SELECT status FROM followed_jobs WHERE customer_id=? AND project_id=?",
            (cust["id"], project_id)).fetchone()
    return "active" if (row and row["status"] == "active") else "inactive"


def _fmt_exp_th(exp_epoch: int) -> str:
    """epoch → 'D ด. YYYY' (พ.ศ.) สำหรับแสดงวันหมดอายุลิงก์."""
    if not exp_epoch:
        return ""
    dt = datetime.fromtimestamp(exp_epoch, TZ_TH)
    months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    return f"{dt.day} {months[dt.month]} {dt.year + 543}"


def _follow_page_html(token: str, state: str, d: dict, deadline: str, exp_epoch: int) -> str:
    """HTML มือถือ-first. state: 'active' | 'inactive' | 'no_customer' | 'invalid'."""
    import html as _html
    head = (
        "<!doctype html><html lang=\"th\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>ติดตามงาน</title><style>"
        "body{font-family:-apple-system,'Segoe UI',sans-serif;margin:0;padding:24px;"
        "background:#f5f6f8;color:#222}"
        ".card{max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:24px;"
        "box-shadow:0 2px 12px rgba(0,0,0,.08)}"
        ".h{font-size:18px;font-weight:700;margin:0 0 12px}"
        ".name{font-size:16px;font-weight:600;margin:8px 0}"
        ".meta{font-size:13px;color:#888;margin:4px 0}"
        ".dl{font-size:13px;color:#d9534f;margin:4px 0}"
        "button{width:100%;padding:16px;font-size:17px;font-weight:700;border:0;border-radius:12px;"
        "margin-top:20px;color:#fff}"
        ".follow{background:#1db446}.unfollow{background:#d9534f}"
        ".exp{font-size:11px;color:#bbb;margin-top:18px;text-align:center}"
        ".msg{font-size:15px;color:#555;margin:12px 0}"
        "</style></head><body><div class=\"card\">"
    )
    foot = "</div></body></html>"

    if state == "invalid":
        return head + "<div class=\"h\">ลิงก์ไม่ถูกต้องหรือหมดอายุ</div>" \
            "<div class=\"msg\">ลิงก์ติดตามนี้ใช้ไม่ได้แล้ว กรุณาเปิดจากข้อความแจ้งเตือนล่าสุดครับ</div>" + foot
    if state == "no_customer":
        return head + "<div class=\"h\">ยังไม่ได้เพิ่มเพื่อน</div>" \
            "<div class=\"msg\">กรุณาเพิ่มเพื่อน Sebastian ก่อนติดตามงานครับ</div>" + foot

    name = _html.escape(d.get("project_name", ""))
    info = _html.escape(_detail_info_line(d))
    body = [f"<div class=\"name\">🏗️ {name}</div>", f"<div class=\"meta\">{info}</div>"]
    if deadline:
        body.append(f"<div class=\"dl\">⏰ ยื่นซอง {_html.escape(deadline)}</div>")

    tok = _html.escape(token)
    if state == "active":
        body.insert(0, "<div class=\"h\">✅ งานนี้ติดตามอยู่แล้ว</div>")
        body.append(
            f"<form method=\"post\" action=\"/follow\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"unfollow\">"
            f"<button class=\"unfollow\" type=\"submit\">ยกเลิกการติดตาม</button></form>")
    else:  # inactive
        body.insert(0, "<div class=\"h\">ติดตามงานนี้?</div>")
        body.append(
            f"<form method=\"post\" action=\"/follow\">"
            f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">"
            f"<input type=\"hidden\" name=\"action\" value=\"follow\">"
            f"<button class=\"follow\" type=\"submit\">⭐ ติดตามงานนี้</button></form>")

    exp_str = _fmt_exp_th(exp_epoch)
    if exp_str:
        body.append(f"<div class=\"exp\">🔗 ลิงก์นี้ใช้ได้ถึง {exp_str} — ข้อมูลที่ติดตามไม่หาย</div>")
    return head + "".join(body) + foot
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_bms_follow.py`
Expected: `OK test_bms_follow` (exit 0)

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_bms_follow.py
git commit -m "feat(follow): bms_api follow status/unfollow/page-html helpers + DB_PATH env override"
```

---

### Task 3: `bms_api.py` — GET/POST `/follow` routes

**Files:**
- Modify: `scripts/bms_api.py` (add 2 routes after `/health`, before `/webhook/line` ~line 451)

> Route handlers เป็น thin wrapper บน helper ของ Task 2 — verify ทาง unit ไม่คุ้ม (ต้อง FastAPI runtime); ตรวจจริงด้วย curl end-to-end ใน Task 6 หลัง deploy.

- [ ] **Step 1: Add the routes**

In `scripts/bms_api.py`, insert after the `health()` function (after ~line 450, before `@app.post("/webhook/line")`):

```python
@app.get("/follow")
async def follow_get(t: str = ""):
    v = follow_token.verify_token(t)
    if not v or not v[1]:           # invalid/expired หรือ portal token (ไม่มี project_id)
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", v[2] if v else 0))
    user_id, project_id, exp = v
    state = _follow_status(user_id, project_id)
    if state == "no_customer":
        return HTMLResponse(_follow_page_html(t, "no_customer", {}, "", exp))
    d = _project_detail(project_id)
    return HTMLResponse(_follow_page_html(t, state, d, _follow_deadline(project_id), exp))


@app.post("/follow")
async def follow_post(request: Request):
    from urllib.parse import parse_qs
    form = parse_qs((await request.body()).decode("utf-8"))
    t = (form.get("t") or [""])[0]
    action = (form.get("action") or [""])[0]
    v = follow_token.verify_token(t)
    if not v or not v[1]:
        raise HTTPException(status_code=400, detail="invalid token")
    user_id, project_id, exp = v
    if action == "follow":
        _record_follow(user_id, project_id)
    elif action == "unfollow":
        _record_unfollow(user_id, project_id)
    state = _follow_status(user_id, project_id)
    if state == "no_customer":
        return HTMLResponse(_follow_page_html(t, "no_customer", {}, "", exp))
    d = _project_detail(project_id)
    return HTMLResponse(_follow_page_html(t, state, d, _follow_deadline(project_id), exp))
```

- [ ] **Step 2: Verify import sanity locally (ไม่รัน server)**

Run: `python -c "import os; os.environ['BMS_DB_PATH']='x'; import sys; sys.path.insert(0,'scripts'); import bms_api; print([r.path for r in bms_api.app.routes if getattr(r,'path','')=='/follow'])"`
Expected: `['/follow', '/follow']` (GET + POST ลงทะเบียนแล้ว ไม่มี import error)

- [ ] **Step 3: Commit**

```bash
git add scripts/bms_api.py
git commit -m "feat(follow): GET/POST /follow routes (token verify → toggle page)"
```

---

### Task 4: `Sebastian_LINE_Sender.py` — แทรกลิงก์ + เอา quick-reply ออก

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (add const + import ~line 41; add `build_follow_link` near `_quick_reply_items`; เปลี่ยน D0 branch ~line 658-670)
- Test: `scripts/test_follow_link.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_follow_link.py`:

```python
"""test_follow_link.py — sender build_follow_link มินต์ token ที่ bms_api verify ได้."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_FOLLOW_SECRET"] = "test-secret-123"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

import Sebastian_LINE_Sender as snd
import follow_token as ft

url = snd.build_follow_link("Uabc", "P1")
assert url.startswith("https://api.butler-bms.com/follow?t="), url
tok = url.split("t=", 1)[1]
v = ft.verify_token(tok, secret="test-secret-123")
assert v is not None and v[0] == "Uabc" and v[1] == "P1", v

print("OK test_follow_link")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_follow_link.py`
Expected: FAIL — `AttributeError: module 'Sebastian_LINE_Sender' has no attribute 'build_follow_link'`

- [ ] **Step 3a: Add const + import**

In `scripts/Sebastian_LINE_Sender.py`, after the `import follow_token` (add it after line 31's import block) and add the base-URL const. After line 31 (`)` closing the Customer_DB import), add:

```python
import follow_token  # noqa: E402
```

After `TZ_TH = timezone(timedelta(hours=7))` (~line 41), add:

```python
PUBLIC_BASE_URL = os.getenv("BMS_PUBLIC_BASE_URL", "https://api.butler-bms.com")
```

- [ ] **Step 3b: Add `build_follow_link` (after `_quick_reply_items`, ~line 312)**

```python
def build_follow_link(line_user_id: str, project_id: str) -> str:
    """ลิงก์ติดตามงาน (signed token, ต่อคน-ต่องาน). คืน '' ถ้า make_token พลาด (ห้ามทำ D0 พัง)."""
    try:
        return PUBLIC_BASE_URL.rstrip("/") + "/follow?t=" + \
            follow_token.make_token(line_user_id, project_id)
    except Exception as e:
        log(f"  follow_token error (ส่งต่อไม่มีลิงก์): {e}")
        return ""
```

- [ ] **Step 3c: เปลี่ยน D0 branch (lines 658-670)**

แทนที่บล็อก:

```python
    # Step 5: send live
    full_name = _clean_project_name(item.get("project_name") or "") or item["project_id"]
    if (item.get("announce_type") or "") == "D0":
        # งานเปิดยื่นซองทุกงานที่ match → text ธรรมดา + intel (ไม่ truncate) + ปุ่มลอย
        # ⭐ ติดตาม (ถ้ายังไม่ตาม) / ❌ ไม่เกี่ยว — อุด follow-timing gap. กัญจน์เลือก 2026-06-08
        try:
            from Sebastian_Customer_DB import is_following
            following = is_following(item["customer_id"], item["project_id"])
        except Exception:
            following = False
        qr = _quick_reply_items(item["project_id"], following)
        success, error_type, error_msg = send_line_push(
            token, item["line_user_id"], full_name + "\n" + text, quick_reply=qr)
```

ด้วย:

```python
    # Step 5: send live
    full_name = _clean_project_name(item.get("project_name") or "") or item["project_id"]
    if (item.get("announce_type") or "") == "D0":
        # งานเปิดยื่นซองทุกงานที่ match → text ธรรมดา + intel + ลิงก์ติดตาม (signed token).
        # ลิงก์อยู่ในเนื้อข้อความ → เลื่อนกดงานเก่าได้ไม่หาย (แทน quick-reply ที่หายเมื่อหลายงาน).
        # N+108 follow-link. กัญจน์เลือก 2026-06-08
        link = build_follow_link(item["line_user_id"], item["project_id"])
        link_block = ("\n\n⭐ ติดตามงานนี้:\n" + link) if link else ""
        success, error_type, error_msg = send_line_push(
            token, item["line_user_id"], full_name + "\n" + text + link_block, quick_reply=None)
```

> `_quick_reply_items` คงไว้ในไฟล์ (ไม่ลบ) เผื่ออนาคต — แค่เลิกเรียก. `is_following` import เดิมในบล็อกนี้ถูกเอาออกพร้อมกัน (ไม่ใช้แล้ว).

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_follow_link.py`
Expected: `OK test_follow_link` (exit 0)

- [ ] **Step 5: Regression — รัน test เดิมที่แตะ followed_jobs/quick-reply**

Run: `python scripts\test_followed_jobs.py`
Expected: ผ่าน (ไม่มี output error / exit 0) — ยืนยันไม่ทำ follow logic เดิมพัง

- [ ] **Step 6: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/test_follow_link.py
git commit -m "feat(follow): D0 แทรก follow-link แทน quick-reply (อุด multi-job gap, N+108)"
```

---

### Task 5: Local full sanity (ทุก test รวด)

**Files:** none (verification only)

- [ ] **Step 1: รัน test ทั้งชุด**

Run แต่ละตัว ต้องได้ `OK …` ครบ:
```bash
python scripts\test_follow_token.py
python scripts\test_bms_follow.py
python scripts\test_follow_link.py
python scripts\test_followed_jobs.py
```
Expected: ทุกตัว print OK / exit 0

- [ ] **Step 2: Idempotent toggle check (เพิ่มเติม spec sanity #2)**

Run:
```bash
python -c "import os,sys,tempfile; from pathlib import Path; t=tempfile.mkdtemp(); os.environ['BMS_DATA_DIR']=t; os.environ['BMS_DB_PATH']=str(Path(t)/'bms_customers.db'); sys.path.insert(0,'scripts'); import Sebastian_Customer_DB as db; db.init_schema();  c=db.get_connection(); c.execute(\"INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) VALUES ('U','n','trial',1,'t','t')\"); c.commit(); import bms_api as a; [(_ ) for _ in [a._record_follow('U','P'),a._record_unfollow('U','P'),a._record_follow('U','P')]]; n=db.get_connection().execute(\"SELECT COUNT(*) FROM followed_jobs WHERE customer_id=(SELECT id FROM customers WHERE line_user_id='U') AND project_id='P'\").fetchone()[0]; print('rows:',n); assert n==1, n; print('OK idempotent')"
```
Expected: `rows: 1` + `OK idempotent` (follow→unfollow→follow คง 1 row/(cust,proj))

---

### Task 6: Deploy VPS + end-to-end sanity

**Files:** none (ops). ⚠️ **ต้อง confirm กัญจน์ก่อน push** (CLAUDE.md: ห้าม push remote โดยไม่ confirm)

- [ ] **Step 1: ขอ confirm push + เตรียม secret**

ถามกัญจน์: "push commits ขึ้น main แล้ว deploy VPS ได้ไหม" — รอตอบ OK
สร้าง secret (เก็บไว้ใช้ step 3):
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

- [ ] **Step 3: ตั้ง env บน VPS (.env) — secret จาก step 1**

```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "grep -q '^BMS_FOLLOW_SECRET=' /opt/bms/app/.env || echo 'BMS_FOLLOW_SECRET=<SECRET_FROM_STEP_1>' >> /opt/bms/app/.env; grep -q '^BMS_PUBLIC_BASE_URL=' /opt/bms/app/.env || echo 'BMS_PUBLIC_BASE_URL=https://api.butler-bms.com' >> /opt/bms/app/.env; echo DONE"
```
แทน `<SECRET_FROM_STEP_1>` ด้วยค่าจริง. Expected: `DONE`

- [ ] **Step 4: Pull + restart bms-api**

```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main && sudo systemctl restart bms-api && sleep 2 && systemctl is-active bms-api"
```
Expected: `active` (bms-line-sender ไม่ต้อง restart — timer รันรอบใหม่หยิบ env เอง; ถ้าอยากทันที: `sudo systemctl restart bms-line-sender.timer`)

- [ ] **Step 5: Health + invalid-token page**

```bash
curl -s https://api.butler-bms.com/health
curl -s "https://api.butler-bms.com/follow?t=bad.token" | grep -o "ลิงก์ไม่ถูกต้องหรือหมดอายุ"
```
Expected: health `{"ok":true,…}` + grep เจอข้อความ invalid

- [ ] **Step 6: End-to-end follow flow (มินต์ token จริงบน VPS แล้วยิง)**

> มินต์ token บน VPS (ใช้ secret ตัวจริงใน env) สำหรับ customer ที่มีอยู่จริง + project จริง

```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "/opt/bms/venv/bin/python -c \"
import sys; sys.path.insert(0,'/opt/bms/app/scripts')
import follow_token as ft
print(ft.make_token('REPLACE_LINE_USER_ID','REPLACE_PROJECT_ID'))
\""
```
เอา token ที่ได้ไปยิง (แทน `<TOKEN>`):
```bash
# GET → หน้า toggle (ควรเจอปุ่มติดตาม หรือ 'ติดตามอยู่แล้ว' ถ้าเคยตาม)
curl -s "https://api.butler-bms.com/follow?t=<TOKEN>" | grep -oE "ติดตามงานนี้|งานนี้ติดตามอยู่แล้ว"
# POST follow
curl -s -X POST https://api.butler-bms.com/follow -d "t=<TOKEN>&action=follow" | grep -o "ยกเลิกการติดตาม"
# POST unfollow
curl -s -X POST https://api.butler-bms.com/follow -d "t=<TOKEN>&action=unfollow" | grep -o "ติดตามงานนี้?"
```
Expected: GET เจอหัวข้อ · follow → เจอ "ยกเลิกการติดตาม" · unfollow → เจอ "ติดตามงานนี้?"

- [ ] **Step 7: ยืนยัน DB state + downstream filter (ไม่มี sqlite3 → ใช้ python3)**

```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "/opt/bms/venv/bin/python -c \"
import sqlite3; c=sqlite3.connect('/opt/bms/data/bms_customers.db'); c.row_factory=sqlite3.Row
r=c.execute(\\\"SELECT status,COUNT(*) n FROM followed_jobs GROUP BY status\\\").fetchall()
print('followed_jobs by status:', {x['status']:x['n'] for x in r})
\""
```
Expected: เห็น `unfollowed` แยกจาก `active`/`closed` (ยืนยัน get_active_follows/is_following ตัด unfollowed ออกแล้วโดยอัตโนมัติ เพราะ filter `status='active'`)

- [ ] **Step 8: เก็บกวาด test follow ที่ยิงไป**

ถ้า REPLACE_PROJECT_ID เป็นงานจริงที่ไม่อยากให้ค้างสถานะ test → ตั้งกลับตามต้องการ (หรือปล่อย 'unfollowed' ก็ได้ ไม่กระทบ delivery). บันทึกผลลง progress_log.

---

### Task 7: Progress log + memory + Discord

**Files:**
- Modify: `progress_log.md`, `MEMORY.md` + memory file, Discord notify

- [ ] **Step 1: progress_log entry**

เพิ่ม section `## งานที่ N+109: follow-link signed-token toggle (LIVE) (2026-06-08)` — root cause (multi-job quick-reply gap), fix (token link + toggle page), ผล (test ผ่าน, deploy, end-to-end curl), followup (Portal Phase 2).

- [ ] **Step 2: อัปเดต memory**

แก้ `project_event_centric_queue.md` (หรือ `project_client_surface_decision.md`): follow-link signed-token LIVE แทน quick-reply, token เผื่อ portal Phase 2. อัปเดตบรรทัดใน `MEMORY.md` ให้ตรง.

- [ ] **Step 3: Discord notify**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); t, ch = get_credentials()
send(t, ch, "✅ follow-link signed-token toggle LIVE — D0 แทรกลิงก์ติดตามต่องาน (แทน quick-reply), หน้าเว็บ toggle ติดตาม/ยกเลิก, end-to-end curl ผ่าน. Portal = Phase 2")
```

- [ ] **Step 4: Commit**

```bash
git add progress_log.md
git commit -m "docs(progress): N+109 — follow-link signed-token toggle LIVE"
```

---

## Self-Review

**Spec coverage:**
- Token (make/verify, HMAC, exp, portal-compat) → Task 1 ✅
- GET/POST /follow + toggle by state → Task 3 ✅
- `_record_unfollow` (status='unfollowed') + `_follow_status` → Task 2 ✅
- HTML page + footer วันหมดอายุ (verify_token คืน exp) → Task 2 (`_follow_page_html`, `_fmt_exp_th`) ✅
- Sender แทรกลิงก์ + เอา quick-reply ออก + `format_notification` ไม่แตะ → Task 4 ✅
- env BMS_FOLLOW_SECRET / BMS_PUBLIC_BASE_URL (สองที่ใช้ .env เดียว) → Task 6 ✅
- Security: POST-only side-effect (form), HMAC, exp, secret ไม่ commit → Task 3 (form POST) + Task 6 (.env) ✅
- Sanity: token tamper/expiry, idempotent, downstream filter, end-to-end → Task 1/5/6 ✅
- Forward-compat portal token (p=None) → Task 1 (make_token/verify_token) ✅

**Placeholder scan:** ไม่มี TBD/“handle errors” — โค้ดครบทุก step. `<SECRET_FROM_STEP_1>` / `<TOKEN>` / `REPLACE_*` เป็น runtime value ที่ตั้งใจให้ engineer แทนตอน deploy (ไม่ใช่ code placeholder) — มีคำสั่งสร้างค่าจริงให้แล้ว.

**Type consistency:** `verify_token` คืน `(u, p, e)` 3-tuple — ใช้สม่ำเสมอใน Task 3 (`v[1]`, `v[2]`, unpack) และ test Task 1. `_follow_page_html(token, state, d, deadline, exp_epoch)` signature ตรงกันทุกที่เรียก (Task 2 test + Task 3 routes). `_follow_status` คืน 'active'/'inactive'/'no_customer' ตรงกับ state ที่ `_follow_page_html` รับ ('invalid' มาจาก route เมื่อ token เสีย). `build_follow_link(line_user_id, project_id)` ตรงกับ test Task 4.
