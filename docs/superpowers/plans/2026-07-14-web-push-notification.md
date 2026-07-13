# Web Push Notification (บอร์ด B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ลูกค้าบอร์ด B รับแจ้งเตือนงานผ่าน browser (Web Push/VAPID, self-hosted) ครบทุกประเภทเหมือน LINE — ส่งคู่กับ LINE ช่วงทดลอง เริ่มที่คุณกัญจน์คนเดียว

**Architecture:** ตัวส่งเดิม (`Sebastian_LINE_Sender.py` + สคริปต์ยิงตรง) mirror ข้อความทุกอันเข้า `webpush_send.py` ผ่าน choke point `send_line_push`/`send_line_flex` (ทุก call site ได้ฟรี) → pywebpush ยิงไปทุกเครื่องใน `push_subscriptions` → log ลง `webpush_delivery_log` (แยกจาก `delivery_log` เด็ดขาด) บอร์ด Next.js เพิ่มการ์ด 🔔 + service worker + API relay

**Tech Stack:** pywebpush (VAPID) ฝั่ง VPS · Service Worker + PushManager ฝั่งบอร์ด (dashboard/web, Next.js บน Vercel) · SQLite (Sebastian_Customer_DB)

**Spec:** `docs/superpowers/specs/2026-07-13-web-push-notification-design.md`

## Global Constraints

- **ห้ามกระทบ LINE path**: exception ฝั่ง webpush ต้องถูกกลืนก่อนออกจาก `webpush_send` เสมอ (คืน `(0,0)`) — สถานะคิว sent/failed/dedup ยึดผล LINE เดิมเป๊ะ
- **ห้ามเขียนอะไรลง `delivery_log`** จากโค้ด webpush — `bid_open.undelivered_backlog` (`scripts/bid_open.py:37`) อ่านตารางนั้นตัดสินงานค้าง
- Env names ตายตัว: `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (VPS `/opt/bms/app/.env` + local `.env`), `NEXT_PUBLIC_VAPID_PUBLIC_KEY` (Vercel + `dashboard/web/.env.local`), kill switch `BMS_WEBPUSH_DISABLED=1`
- URL บอร์ด: `https://bid-master-dashboard.vercel.app` (override ได้ด้วย env `BMS_BOARD_BASE_URL`) · engine: `https://api.butler-bms.com`
- Python tests = สคริปต์ standalone `scripts/test_*.py` รันด้วย `python scripts/test_X.py` จบด้วย print "PASS ..." (pattern เดิมของ repo)
- ทุก commit → entry ใน `progress_log.md` ก่อน + Discord notify หลัง (กฎ CLAUDE.md) — งานนี้รวมเป็น entry N+203 เดียว อัปเดตท้าย commit สุดท้าย
- **ห้าม push origin / deploy โดยไม่ confirm คุณกัญจน์** (Task 8 มี gate)
- VPS: repo `/opt/bms/app`, venv `/opt/bms/venv`, services `bms-api.service` + `bms-line-sender.timer` (ทุกนาที), ทั้งคู่ใช้ `EnvironmentFile=/opt/bms/app/.env`

---

### Task 1: Dependencies + VAPID keys

**Files:**
- Modify: `requirements.txt` (เพิ่มบรรทัด `pywebpush`)
- Modify: `.env` (local — gitignored), `dashboard/web/.env.local` (gitignored)
- Create: `scripts/gen_vapid_keys.py` (one-off helper, commit ได้)

**Interfaces:**
- Produces: env vars `VAPID_PRIVATE_KEY` (base64url raw EC key), `VAPID_SUBJECT=mailto:kanapr51@gmail.com`, `NEXT_PUBLIC_VAPID_PUBLIC_KEY` (base64url uncompressed point — ใช้เป็น `applicationServerKey` ฝั่ง browser และคู่กับ private ฝั่งส่ง)

- [ ] **Step 1: ติดตั้ง pywebpush ในเครื่อง dev**

Run: `pip install pywebpush`
Expected: ติดตั้งสำเร็จ (ลาก py_vapid + cryptography มาด้วย)

- [ ] **Step 2: เขียน generator**

```python
# scripts/gen_vapid_keys.py
"""สร้าง VAPID key pair ครั้งเดียว — print ออก stdout เท่านั้น (ห้าม write ไฟล์/commit key)"""
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from py_vapid.utils import b64urlencode

v = Vapid02()
v.generate_keys()
priv = b64urlencode(
    v.private_key.private_numbers().private_value.to_bytes(32, "big"))
pub = b64urlencode(
    v.public_key.public_bytes(serialization.Encoding.X962,
                              serialization.PublicFormat.UncompressedPoint))
print("VAPID_PRIVATE_KEY=" + priv)
print("VAPID_SUBJECT=mailto:kanapr51@gmail.com")
print("NEXT_PUBLIC_VAPID_PUBLIC_KEY=" + pub)
```

- [ ] **Step 3: รัน + เก็บ keys**

Run: `python scripts/gen_vapid_keys.py`
Expected: 3 บรรทัด env — เอา 2 บรรทัดแรก append เข้า `.env` (local), บรรทัดสุดท้าย append เข้า `dashboard/web/.env.local`. **key ห้ามลง git** (ทั้งสองไฟล์ gitignored อยู่แล้ว — ตรวจด้วย `git check-ignore .env dashboard/web/.env.local` ต้องขึ้นทั้งคู่)

- [ ] **Step 4: เพิ่ม dependency + commit**

`requirements.txt` เพิ่มบรรทัด `pywebpush` แล้ว:

```bash
git add requirements.txt scripts/gen_vapid_keys.py
git commit -m "chore(webpush): เพิ่ม pywebpush + VAPID key generator (N+203)"
```

---

### Task 2: ตาราง push_subscriptions + webpush_delivery_log

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py` — เพิ่ม 2 CREATE TABLE ใน `init_schema()` (executescript block ที่เริ่มบรรทัด ~184, แปะต่อท้ายก่อนปิด `"""`)
- Test: `scripts/test_webpush_schema.py`

**Interfaces:**
- Produces: ตาราง `push_subscriptions(id, customer_id, endpoint UNIQUE, p256dh, auth, user_agent, created_at, last_ok_at, disabled_at)` และ `webpush_delivery_log(id, subscription_id, customer_id, project_id, source_stage, status, error, attempted_at)` — Task 3/5 ใช้ตรงๆ

- [ ] **Step 1: เขียน failing test**

```python
# scripts/test_webpush_schema.py
"""ตาราง push_subscriptions + webpush_delivery_log ถูกสร้างโดย init_schema + insert/select ได้"""
import os, sys, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"))
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db
db.init_schema()

with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                 "VALUES ('UPUSH', 'x', 'trial', '2026-07-14T00:00:00+07:00', '2026-07-14T00:00:00+07:00')")
    cid = conn.execute("SELECT id FROM customers WHERE line_user_id='UPUSH'").fetchone()["id"]
    conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, user_agent, created_at) "
                 "VALUES (?, 'https://push.example/ep1', 'pk', 'ak', 'UA', '2026-07-14T00:00:00+07:00')", (cid,))
    sid = conn.execute("SELECT id FROM push_subscriptions WHERE endpoint='https://push.example/ep1'").fetchone()["id"]
    conn.execute("INSERT INTO webpush_delivery_log (subscription_id, customer_id, project_id, source_stage, status, error, attempted_at) "
                 "VALUES (?, ?, 'P1', 'api_enriched', 'sent', '', '2026-07-14T00:00:01+07:00')", (sid, cid))
    row = conn.execute("SELECT status FROM webpush_delivery_log WHERE subscription_id=?", (sid,)).fetchone()
    assert row["status"] == "sent", row
    # endpoint UNIQUE
    import sqlite3
    try:
        conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, created_at) "
                     "VALUES (?, 'https://push.example/ep1', 'pk2', 'ak2', 'x')", (cid,))
        assert False, "endpoint UNIQUE ไม่ทำงาน"
    except sqlite3.IntegrityError:
        pass

print("PASS test_webpush_schema")
```

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_webpush_schema.py`
Expected: FAIL `sqlite3.OperationalError: no such table: push_subscriptions`

- [ ] **Step 3: เพิ่มตารางใน init_schema**

ใน executescript block ของ `init_schema()` เพิ่มก่อนปิด `"""`:

```sql
            -- Web Push (บอร์ด B) — spec 2026-07-13-web-push-notification-design.md
            -- 1 ลูกค้ามีได้หลายเครื่อง; disabled_at = เพิกถอน (404/410) ไม่ยิงซ้ำ
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                endpoint    TEXT NOT NULL UNIQUE,
                p256dh      TEXT NOT NULL,
                auth        TEXT NOT NULL,
                user_agent  TEXT,
                created_at  TEXT NOT NULL,
                last_ok_at  TEXT,
                disabled_at TEXT
            );

            -- log ผลส่ง webpush — จงใจแยกจาก delivery_log (backlog digest อ่านตารางนั้น)
            CREATE TABLE IF NOT EXISTS webpush_delivery_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL REFERENCES push_subscriptions(id),
                customer_id     INTEGER NOT NULL,
                project_id      TEXT NOT NULL DEFAULT '',
                source_stage    TEXT NOT NULL DEFAULT '',
                status          TEXT NOT NULL CHECK(status IN ('sent','failed')),
                error           TEXT,
                attempted_at    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_webpush_log_customer
                ON webpush_delivery_log(customer_id, attempted_at);
```

- [ ] **Step 4: รันให้ pass**

Run: `python scripts/test_webpush_schema.py`
Expected: `PASS test_webpush_schema`

- [ ] **Step 5: sanity — test เดิมไม่พัง + commit**

Run: `python scripts/test_portal_jobs_api.py && python scripts/test_queue_stage_dedup.py`
Expected: PASS ทั้งคู่

```bash
git add scripts/Sebastian_Customer_DB.py scripts/test_webpush_schema.py
git commit -m "feat(webpush): ตาราง push_subscriptions + webpush_delivery_log (N+203)"
```

---

### Task 3: module `webpush_send.py`

**Files:**
- Create: `scripts/webpush_send.py`
- Test: `scripts/test_webpush_send.py`

**Interfaces:**
- Consumes: ตารางจาก Task 2, `Sebastian_Customer_DB.get_connection`
- Produces (Task 4/5 เรียก):
  - `send_to_user(line_user_id: str, title: str, body: str, url: str, project_id: str = "", source_stage: str = "") -> tuple[int, int]` — (sent, failed), ไม่ raise
  - `mirror_text(line_user_id: str, text: str, project_id: str = "", source_stage: str = "") -> tuple[int, int]` — หั่น text เป็น title/body แล้วส่ง, ไม่ raise
  - `job_url(project_id: str) -> str`

- [ ] **Step 1: เขียน failing test**

```python
# scripts/test_webpush_send.py
"""webpush_send: ส่งสำเร็จ→log sent+last_ok_at · 410→disable · exception→ไม่ raise · kill switch · split_text"""
import os, sys, tempfile, types
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  VAPID_PRIVATE_KEY="testpriv", VAPID_SUBJECT="mailto:t@t.co")
os.environ.pop("BMS_WEBPUSH_DISABLED", None)
sys.path.insert(0, str(Path(__file__).parent))

# fake pywebpush ก่อน import module (ห้ามยิงเน็ตจริงใน test)
fake = types.ModuleType("pywebpush")
class WebPushException(Exception):
    def __init__(self, msg, response=None):
        super().__init__(msg); self.response = response
CALLS = []
def _webpush_ok(**kw): CALLS.append(kw); return True
fake.webpush = _webpush_ok
fake.WebPushException = WebPushException
sys.modules["pywebpush"] = fake

import Sebastian_Customer_DB as db
db.init_schema()
import webpush_send as wp

NOW = "2026-07-14T00:00:00+07:00"
with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                 "VALUES ('UPUSH','x','trial',?,?)", (NOW, NOW))
    cid = conn.execute("SELECT id FROM customers WHERE line_user_id='UPUSH'").fetchone()["id"]
    conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, created_at) "
                 "VALUES (?, 'https://push.example/ep1', 'pk', 'ak', ?)", (cid, NOW))

# 1) success → log sent + last_ok_at + payload ครบ
sent, failed = wp.send_to_user("UPUSH", "หัวข้อ", "เนื้อหา", "https://board/x", "P1", "api_enriched")
assert (sent, failed) == (1, 0), (sent, failed)
assert CALLS and CALLS[0]["subscription_info"]["endpoint"] == "https://push.example/ep1"
import json
payload = json.loads(CALLS[0]["data"])
assert payload == {"title": "หัวข้อ", "body": "เนื้อหา", "url": "https://board/x"}, payload
with db.get_connection() as conn:
    row = conn.execute("SELECT status, project_id, source_stage FROM webpush_delivery_log").fetchone()
    assert (row["status"], row["project_id"], row["source_stage"]) == ("sent", "P1", "api_enriched"), dict(row)
    assert conn.execute("SELECT last_ok_at FROM push_subscriptions").fetchone()["last_ok_at"]

# 2) 410 Gone → disabled_at + log failed
class _Resp: status_code = 410
def _webpush_410(**kw): raise WebPushException("gone", response=_Resp())
fake.webpush = _webpush_410
sent, failed = wp.send_to_user("UPUSH", "t", "b", "u")
assert (sent, failed) == (0, 1), (sent, failed)
with db.get_connection() as conn:
    assert conn.execute("SELECT disabled_at FROM push_subscriptions").fetchone()["disabled_at"]
    # เครื่องถูก disable แล้ว → ส่งรอบถัดไปไม่ยิงซ้ำ
sent, failed = wp.send_to_user("UPUSH", "t", "b", "u")
assert (sent, failed) == (0, 0), (sent, failed)

# 3) exception แปลกๆ → ไม่ raise
with db.get_connection() as conn:
    conn.execute("UPDATE push_subscriptions SET disabled_at=NULL")
def _webpush_boom(**kw): raise RuntimeError("boom")
fake.webpush = _webpush_boom
sent, failed = wp.mirror_text("UPUSH", "บรรทัดแรก\nบรรทัดสอง", "P2", "followed_winner")
assert (sent, failed) == (0, 1), (sent, failed)

# 4) kill switch
os.environ["BMS_WEBPUSH_DISABLED"] = "1"
assert wp.send_to_user("UPUSH", "t", "b", "u") == (0, 0)
os.environ.pop("BMS_WEBPUSH_DISABLED")

# 5) split_text + job_url
assert wp.split_text("🏗️ งานใหม่ ก่อสร้างถนน\nจังหวัด นครพนม\nงบ 1,000,000") == \
    ("🏗️ งานใหม่ ก่อสร้างถนน", "จังหวัด นครพนม งบ 1,000,000")
assert wp.job_url("P9").endswith("/portal/job/P9")
assert wp.job_url("").endswith("/portal/world")

print("PASS test_webpush_send")
```

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_webpush_send.py`
Expected: FAIL `ModuleNotFoundError: No module named 'webpush_send'`

- [ ] **Step 3: เขียน module**

```python
# scripts/webpush_send.py
"""ส่ง Web Push (VAPID) ไปทุกเครื่องที่ลูกค้า subscribe บนบอร์ด B.

Contract: ไม่ raise ออกนอก module เด็ดขาด (best-effort ขนานกับ LINE — LINE path
ห้ามล้มเพราะ webpush). ผลส่งลง webpush_delivery_log เท่านั้น ห้ามแตะ delivery_log
(bid_open.undelivered_backlog อ่านตารางนั้นตัดสินงานค้าง).
เปิดใช้เมื่อมี VAPID_PRIVATE_KEY + VAPID_SUBJECT ใน env; BMS_WEBPUSH_DISABLED=1 = ปิด.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import get_connection  # noqa: E402

_TZ = timezone(timedelta(hours=7))
TITLE_MAX = 60
BODY_MAX = 180


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _board_base() -> str:
    return os.environ.get("BMS_BOARD_BASE_URL", "https://bid-master-dashboard.vercel.app").rstrip("/")


def job_url(project_id: str) -> str:
    if project_id:
        return f"{_board_base()}/portal/job/{project_id}"
    return f"{_board_base()}/portal/world"


def split_text(text: str) -> tuple[str, str]:
    """หั่นข้อความ LINE เป็น (title, body) สำหรับ notification — บรรทัดแรก = title."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    title = (lines[0] if lines else "BMS Bid Board")[:TITLE_MAX]
    body = " ".join(lines[1:])[:BODY_MAX]
    return title, body


def _log(conn, sub_id: int, customer_id: int, project_id: str, source_stage: str,
         status: str, error: str = "") -> None:
    conn.execute(
        "INSERT INTO webpush_delivery_log "
        "(subscription_id, customer_id, project_id, source_stage, status, error, attempted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sub_id, customer_id, project_id or "", source_stage or "", status, (error or "")[:300], _now()))


def send_to_user(line_user_id: str, title: str, body: str, url: str,
                 project_id: str = "", source_stage: str = "") -> tuple[int, int]:
    """ยิงไปทุก subscription active ของ user. คืน (sent, failed). ไม่ raise."""
    try:
        if os.environ.get("BMS_WEBPUSH_DISABLED") == "1":
            return (0, 0)
        priv = os.environ.get("VAPID_PRIVATE_KEY", "")
        subject = os.environ.get("VAPID_SUBJECT", "")
        if not priv or not subject:
            return (0, 0)  # ยังไม่ config = feature ปิดเงียบๆ
        from pywebpush import webpush, WebPushException
        payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
        sent = failed = 0
        with get_connection() as conn:
            cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?",
                                (line_user_id,)).fetchone()
            if not cust:
                return (0, 0)
            cid = cust["id"]
            subs = conn.execute(
                "SELECT id, endpoint, p256dh, auth FROM push_subscriptions "
                "WHERE customer_id=? AND disabled_at IS NULL", (cid,)).fetchall()
            for s in subs:
                try:
                    webpush(
                        subscription_info={"endpoint": s["endpoint"],
                                           "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                        data=payload,
                        vapid_private_key=priv,
                        vapid_claims={"sub": subject},
                        timeout=10,
                    )
                    conn.execute("UPDATE push_subscriptions SET last_ok_at=? WHERE id=?",
                                 (_now(), s["id"]))
                    _log(conn, s["id"], cid, project_id, source_stage, "sent")
                    sent += 1
                except WebPushException as e:
                    code = getattr(getattr(e, "response", None), "status_code", None)
                    if code in (404, 410):  # เพิกถอน/ลบเบราว์เซอร์ → ปิดถาวร ไม่ยิงซ้ำ
                        conn.execute("UPDATE push_subscriptions SET disabled_at=? WHERE id=?",
                                     (_now(), s["id"]))
                    _log(conn, s["id"], cid, project_id, source_stage, "failed", f"HTTP {code}: {e}")
                    failed += 1
                except Exception as e:  # payload/key เพี้ยน ฯลฯ — log แล้วไปต่อเครื่องถัดไป
                    _log(conn, s["id"], cid, project_id, source_stage, "failed",
                         f"{type(e).__name__}: {e}")
                    failed += 1
        return (sent, failed)
    except Exception:
        return (0, 0)


def mirror_text(line_user_id: str, text: str,
                project_id: str = "", source_stage: str = "") -> tuple[int, int]:
    """Mirror ข้อความ LINE → web push (title/body หั่นจาก text). ไม่ raise."""
    try:
        title, body = split_text(text)
        return send_to_user(line_user_id, title, body, job_url(project_id),
                            project_id, source_stage)
    except Exception:
        return (0, 0)
```

- [ ] **Step 4: รันให้ pass**

Run: `python scripts/test_webpush_send.py`
Expected: `PASS test_webpush_send`

- [ ] **Step 5: Commit**

```bash
git add scripts/webpush_send.py scripts/test_webpush_send.py
git commit -m "feat(webpush): module ส่ง web push + log แยก webpush_delivery_log (N+203)"
```

---

### Task 4: Mirror ที่ choke point `send_line_push` / `send_line_flex`

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py:365-396` (send_line_push), `:597-622` (send_line_flex) + call sites ในไฟล์เดียวกัน `:701, :743, :774, :920, :933`
- Modify: `scripts/test_d0_quickreply.py` (เพิ่ม kill switch 1 บรรทัด)
- Test: `scripts/test_webpush_mirror.py`

**Interfaces:**
- Consumes: `webpush_send.mirror_text` (Task 3)
- Produces: `send_line_push(token, line_user_id, text, quick_reply=None, webpush_ctx=None)` และ `send_line_flex(token, line_user_id, alt_text, flex_contents, webpush_ctx=None)` — signature เดิม backward-compatible (caller เดิมทุกตัวไม่ต้องแก้ก็ได้ mirror ฟรีแบบไม่มี project_id); `webpush_ctx` = `{"project_id": str, "source_stage": str}` ใส่เฉพาะ call site ในคิว

**หมายเหตุ:** สคริปต์ยิงตรง (`Sebastian_BidOpen_Morning.py:99`, `Sebastian_Daily_User_Summary.py:180`, `timeline_reminder.py:133`, `Sebastian_Backlog_Digest.py:89`) เรียก `send_line_push` อยู่แล้ว → ได้ mirror อัตโนมัติ ไม่ต้องแก้ไฟล์พวกนั้น = ครอบ "ครบทุกประเภท" ตาม spec

- [ ] **Step 1: เขียน failing test**

```python
# scripts/test_webpush_mirror.py
"""send_line_push/send_line_flex mirror เข้า webpush_send.mirror_text ทุกครั้ง
(ทั้ง LINE สำเร็จและล้ม) และ webpush พังไม่กระทบผล LINE"""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ["BMS_WEBPUSH_DISABLED"] = "1"  # กัน DB/network จริงตอน import
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_LINE_Sender as ls

def _resp(code):
    m = MagicMock(); m.status_code = code
    m.json.return_value = {"message": "x"}; m.text = "x"
    return m

# 1) LINE 200 → mirror ถูกเรียกพร้อม ctx
with patch.object(ls, "req_lib") as rq, patch.object(ls, "_mirror_webpush") as mw:
    rq.post.return_value = _resp(200)
    ok, et, em = ls.send_line_push("tok", "U1", "hello\nworld",
                                   webpush_ctx={"project_id": "P1", "source_stage": "api_enriched"})
    assert ok is True
    mw.assert_called_once_with("U1", "hello\nworld", {"project_id": "P1", "source_stage": "api_enriched"})

# 2) LINE 429 (quota เต็ม) → mirror ยังถูกเรียก (นี่คือ use case หลัก!)
with patch.object(ls, "req_lib") as rq, patch.object(ls, "_mirror_webpush") as mw:
    rq.post.return_value = _resp(429)
    ok, et, em = ls.send_line_push("tok", "U1", "hi")
    assert ok is False and et == "retryable"
    mw.assert_called_once_with("U1", "hi", None)

# 3) mirror ระเบิด → ผล LINE ไม่กระทบ
with patch.object(ls, "req_lib") as rq, \
     patch.object(ls.webpush_send, "mirror_text", side_effect=RuntimeError("boom")):
    rq.post.return_value = _resp(200)
    ok, et, em = ls.send_line_push("tok", "U1", "hi")
    assert ok is True, (ok, et, em)

# 4) flex → mirror ด้วย alt_text
with patch.object(ls, "req_lib") as rq, patch.object(ls, "_mirror_webpush") as mw:
    rq.post.return_value = _resp(200)
    ok, et, em = ls.send_line_flex("tok", "U1", "alt สรุปงาน", {"type": "bubble"},
                                   webpush_ctx={"project_id": "P2", "source_stage": "province_qualified"})
    assert ok is True
    mw.assert_called_once_with("U1", "alt สรุปงาน", {"project_id": "P2", "source_stage": "province_qualified"})

print("PASS test_webpush_mirror")
```

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_webpush_mirror.py`
Expected: FAIL — `AttributeError` (`_mirror_webpush` ไม่มี) หรือ `TypeError: unexpected keyword argument 'webpush_ctx'`

- [ ] **Step 3: แก้ Sebastian_LINE_Sender.py**

(a) เพิ่ม import ใต้ `import follow_token` (บรรทัด ~32):

```python
import webpush_send  # noqa: E402 — mirror ทุก LINE push → browser (best-effort)
```

(b) เพิ่ม helper เหนือ `send_line_push` (บรรทัด ~364):

```python
def _mirror_webpush(line_user_id: str, text: str, ctx: dict | None) -> None:
    """Mirror ข้อความเข้า web push — กลืน error ทั้งหมด ห้ามกระทบ LINE path."""
    try:
        c = ctx or {}
        webpush_send.mirror_text(line_user_id, text,
                                 c.get("project_id", ""), c.get("source_stage", ""))
    except Exception:
        pass
```

(c) `send_line_push` — เปลี่ยน signature + mirror ก่อนคืนผลทุกทาง (โครงเดิมมี return หลายจุด → หุ้มด้วย inner function):

```python
def send_line_push(token: str, line_user_id: str, text: str, quick_reply=None,
                   webpush_ctx=None) -> tuple[bool, str, str]:
    """
    Returns (success, error_type, error_msg).
    error_type: '' | 'retryable' | 'terminal'
    quick_reply: list ของ quick-reply action items (None = ข้อความเปล่า เหมือนเดิม).
    webpush_ctx: {"project_id","source_stage"} → mirror เข้า web push (None = mirror แบบไม่มี ctx)
    """
    def _attempt() -> tuple[bool, str, str]:
        try:
            r = req_lib.post(
                LINE_PUSH_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"to": line_user_id, "messages": [_text_message(text, quick_reply)]},
                timeout=10,
            )
            if r.status_code == 200:
                return True, "", ""
            try:
                detail = r.json().get("message", r.text[:120])
            except Exception:
                detail = r.text[:120]
            if r.status_code == 429:
                return False, "retryable", f"HTTP 429 rate_limit: {detail}"
            if r.status_code >= 500:
                return False, "retryable", f"HTTP {r.status_code}: {detail}"
            # 400/403 — invalid user ID, blocked, unlinked
            return False, "terminal", f"HTTP {r.status_code}: {detail}"
        except req_lib.Timeout:
            return False, "retryable", "timeout"
        except Exception as e:
            return False, "retryable", str(e)[:200]

    result = _attempt()
    _mirror_webpush(line_user_id, text, webpush_ctx)
    return result
```

(d) `send_line_flex` — แบบเดียวกัน (mirror ด้วย `alt_text`):

```python
def send_line_flex(token: str, line_user_id: str, alt_text: str,
                   flex_contents: dict, webpush_ctx=None) -> tuple[bool, str, str]:
    """ส่ง flex message. Returns (success, error_type, error_msg). โครงเดียวกับ send_line_push"""
    def _attempt() -> tuple[bool, str, str]:
        try:
            r = req_lib.post(
                LINE_PUSH_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"to": line_user_id,
                      "messages": [{"type": "flex", "altText": alt_text[:400], "contents": flex_contents}]},
                timeout=10,
            )
            if r.status_code == 200:
                return True, "", ""
            try:
                detail = r.json().get("message", r.text[:120])
            except Exception:
                detail = r.text[:120]
            if r.status_code == 429:
                return False, "retryable", f"HTTP 429 rate_limit: {detail}"
            if r.status_code >= 500:
                return False, "retryable", f"HTTP {r.status_code}: {detail}"
            return False, "terminal", f"HTTP {r.status_code}: {detail}"
        except req_lib.Timeout:
            return False, "retryable", "timeout"
        except Exception as e:
            return False, "retryable", f"{type(e).__name__}: {e}"

    result = _attempt()
    _mirror_webpush(line_user_id, alt_text, webpush_ctx)
    return result
```

(e) call sites ในคิว (5 จุด) — เพิ่ม `webpush_ctx` ให้ log webpush มี project_id ไว้เทียบกับคิว (เกณฑ์เสถียร 3 วัน):

- `:701` (prelim): `send_line_push(token, item["line_user_id"], text, quick_reply=None, webpush_ctx={"project_id": item["project_id"], "source_stage": item.get("source_stage", "")})`
- `:743` (winner): เหมือนกัน
- `:774` (cancelled): เหมือนกัน
- `:920` (ข้อความหลัก D0/qualified): เหมือนกัน
- `:933` (flex): `send_line_flex(token, item["line_user_id"], alt_text, flex, webpush_ctx={"project_id": item["project_id"], "source_stage": item.get("source_stage", "")})`

(เลขบรรทัดจะขยับหลังแก้ (c)/(d) — หา call site ด้วย `grep -n "send_line_push(token" scripts/Sebastian_LINE_Sender.py`)

(f) `scripts/test_d0_quickreply.py` — เพิ่มบรรทัดแรกๆ ก่อน import ls:

```python
import os; os.environ["BMS_WEBPUSH_DISABLED"] = "1"  # กัน mirror ยิงจริงใน test
```

- [ ] **Step 4: รันให้ pass + regression**

Run: `python scripts/test_webpush_mirror.py && python scripts/test_d0_quickreply.py`
Expected: PASS ทั้งคู่

Run dry-run ทั้งตัว (ไม่ยิงจริง): `python scripts/Sebastian_LINE_Sender.py --dry-run`
Expected: exit 0, log ปกติ ไม่มี traceback (คิวว่างจะขึ้น "No pending items — exit" ก็ถือว่าผ่าน)

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/test_webpush_mirror.py scripts/test_d0_quickreply.py
git commit -m "feat(webpush): mirror ทุก LINE push/flex เข้า web push ที่ choke point (N+203)"
```

---

### Task 5: Engine endpoints (bms_api.py)

**Files:**
- Modify: `scripts/bms_api.py` — เพิ่ม 3 endpoints ต่อท้ายกลุ่ม portal endpoints (หลัง `portal_all_jobs_json` ~บรรทัด 1981)
- Test: `scripts/test_push_api.py`

**Interfaces:**
- Consumes: ตาราง Task 2, `webpush_send.send_to_user` (Task 3), pattern guard `X-BMS-Secret` เดิม
- Produces (บอร์ด Task 7 เรียกผ่าน relay):
  - `POST /api/portal/push-subscribe` body `{line_user_id, endpoint, p256dh, auth, user_agent?}` → `{ok: true}` (upsert: endpoint ซ้ำ = update keys + re-enable)
  - `POST /api/portal/push-unsubscribe` body `{line_user_id, endpoint}` → `{ok: true}`
  - `POST /api/portal/push-test` body `{line_user_id}` → `{ok: true, sent: n, failed: m}`

- [ ] **Step 1: เขียน failing test**

```python
# scripts/test_push_api.py
"""POST /api/portal/push-subscribe|unsubscribe|test — 403 guard, upsert, disable, ส่งทดสอบ (mock)"""
import os, sys, asyncio, sqlite3, tempfile, shutil
from pathlib import Path
from unittest.mock import patch

SCRATCH = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent.parent / "data" / "bms_customers.db", SCRATCH / "bms_customers.db")
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_WEBPUSH_DISABLED="1")
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
from fastapi import HTTPException


class FakeReq:
    def __init__(self, body): self._b = body
    async def json(self): return self._b


def setup_customer():
    c = sqlite3.connect(bms_api.DB_PATH)
    c.execute("INSERT OR IGNORE INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('UPUSH','x','trial',1,'2026-07-14T00:00:00+07:00','2026-07-14T00:00:00+07:00')")
    c.commit(); c.close()


async def main():
    setup_customer()
    SUB = {"line_user_id": "UPUSH", "endpoint": "https://push.example/e1",
           "p256dh": "pk", "auth": "ak", "user_agent": "UA1"}
    # 403
    try:
        await bms_api.portal_push_subscribe(FakeReq(SUB), x_bms_secret="wrong"); assert False
    except HTTPException as e:
        assert e.status_code == 403
    # subscribe → row
    r = await bms_api.portal_push_subscribe(FakeReq(SUB), x_bms_secret="t")
    assert r["ok"] is True
    c = sqlite3.connect(bms_api.DB_PATH); c.row_factory = sqlite3.Row
    row = c.execute("SELECT * FROM push_subscriptions WHERE endpoint='https://push.example/e1'").fetchone()
    assert row["p256dh"] == "pk" and row["disabled_at"] is None
    # subscribe ซ้ำ endpoint เดิม (key ใหม่) → update ไม่ duplicate
    r = await bms_api.portal_push_subscribe(FakeReq({**SUB, "p256dh": "pk2"}), x_bms_secret="t")
    rows = c.execute("SELECT p256dh FROM push_subscriptions WHERE endpoint='https://push.example/e1'").fetchall()
    assert len(rows) == 1 and rows[0]["p256dh"] == "pk2", [dict(x) for x in rows]
    # unsubscribe → disabled_at
    r = await bms_api.portal_push_unsubscribe(
        FakeReq({"line_user_id": "UPUSH", "endpoint": "https://push.example/e1"}), x_bms_secret="t")
    assert r["ok"] is True
    row = c.execute("SELECT disabled_at FROM push_subscriptions").fetchone()
    assert row["disabled_at"], dict(row)
    # subscribe อีกรอบ → re-enable
    await bms_api.portal_push_subscribe(FakeReq(SUB), x_bms_secret="t")
    assert c.execute("SELECT disabled_at FROM push_subscriptions").fetchone()["disabled_at"] is None
    # push-test → เรียก webpush_send.send_to_user
    with patch.object(bms_api.webpush_send, "send_to_user", return_value=(2, 0)) as m:
        r = await bms_api.portal_push_test(FakeReq({"line_user_id": "UPUSH"}), x_bms_secret="t")
        assert r == {"ok": True, "sent": 2, "failed": 0}, r
        assert m.call_args[0][0] == "UPUSH"
    c.close()
    print("PASS test_push_api")


asyncio.run(main())
```

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_push_api.py`
Expected: FAIL `AttributeError: module 'bms_api' has no attribute 'portal_push_subscribe'`

- [ ] **Step 3: เพิ่ม endpoints ใน bms_api.py**

เพิ่ม import ใกล้ imports อื่นของไฟล์: `import webpush_send`

ต่อท้ายหลัง `portal_all_jobs_json`:

```python
@app.post("/api/portal/push-subscribe")
async def portal_push_subscribe(request: Request, x_bms_secret=Header(default=None)):
    """ลงทะเบียนเครื่องรับ web push จากบอร์ด — upsert ด้วย endpoint (ซ้ำ = update key + re-enable)."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    line_user_id = (body.get("line_user_id") or "").strip()
    endpoint = (body.get("endpoint") or "").strip()
    p256dh = (body.get("p256dh") or "").strip()
    auth = (body.get("auth") or "").strip()
    user_agent = (body.get("user_agent") or "")[:200]
    if not line_user_id or not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="line_user_id + endpoint + p256dh + auth required")
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (line_user_id,)).fetchone()
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found")
        conn.execute(
            "INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, user_agent, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET "
            "customer_id=excluded.customer_id, p256dh=excluded.p256dh, auth=excluded.auth, "
            "user_agent=excluded.user_agent, disabled_at=NULL",
            (cust["id"], endpoint, p256dh, auth, user_agent, now))
    return {"ok": True}


@app.post("/api/portal/push-unsubscribe")
async def portal_push_unsubscribe(request: Request, x_bms_secret=Header(default=None)):
    """ปิดรับ web push ของเครื่องนั้น (soft — ตั้ง disabled_at)."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    line_user_id = (body.get("line_user_id") or "").strip()
    endpoint = (body.get("endpoint") or "").strip()
    if not line_user_id or not endpoint:
        raise HTTPException(status_code=400, detail="line_user_id + endpoint required")
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "UPDATE push_subscriptions SET disabled_at=? "
            "WHERE endpoint=? AND customer_id=(SELECT id FROM customers WHERE line_user_id=?)",
            (now, endpoint, line_user_id))
    return {"ok": True}


@app.post("/api/portal/push-test")
async def portal_push_test(request: Request, x_bms_secret=Header(default=None)):
    """ส่งข้อความทดสอบไปทุกเครื่องของ user (ปุ่ม 'ส่งทดสอบ' บนบอร์ด)."""
    if x_bms_secret != BMS_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    line_user_id = (body.get("line_user_id") or "").strip()
    if not line_user_id:
        raise HTTPException(status_code=400, detail="line_user_id required")
    sent, failed = webpush_send.send_to_user(
        line_user_id, "🔔 ทดสอบแจ้งเตือน BMS Bid Board",
        "ถ้าเห็นข้อความนี้ = เครื่องนี้พร้อมรับแจ้งเตือนงานแล้ว",
        webpush_send.job_url(""))
    return {"ok": True, "sent": sent, "failed": failed}
```

- [ ] **Step 4: รันให้ pass + regression**

Run: `python scripts/test_push_api.py && python scripts/test_portal_jobs_api.py && python scripts/test_portal_all_jobs_api.py`
Expected: PASS ทั้งหมด

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_push_api.py
git commit -m "feat(webpush): engine endpoints push-subscribe/unsubscribe/test (N+203)"
```

---

### Task 6: บอร์ด — service worker + manifest + icons

**Files:**
- Create: `dashboard/web/public/sw.js`, `dashboard/web/public/manifest.json`, `dashboard/web/public/icon-192.png`, `dashboard/web/public/icon-512.png`
- Modify: `dashboard/web/src/app/layout.tsx` (เพิ่ม `manifest` ใน metadata export ที่มีอยู่)

**Interfaces:**
- Produces: `/sw.js` (Task 7 register), `/manifest.json` (iOS Add-to-Home-Screen), payload contract `{title, body, url}` ตรงกับ `webpush_send.py` (Task 3)

- [ ] **Step 1: เขียน sw.js**

```javascript
// dashboard/web/public/sw.js — Web Push receiver ของ BMS Bid Board
// payload contract: {title, body, url} (ดู scripts/webpush_send.py)
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { /* payload เพี้ยน → แจ้ง default */ }
  const title = data.title || "BMS Bid Board";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    data: { url: data.url || "/portal/world" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/portal/world";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url === url && "focus" in c) return c.focus();
      }
      return clients.openWindow(url);
    })
  );
});
```

- [ ] **Step 2: เขียน manifest.json**

```json
{
  "name": "BMS Bid Board",
  "short_name": "Bid Board",
  "start_url": "/portal/world",
  "display": "standalone",
  "background_color": "#0b1220",
  "theme_color": "#0b1220",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 3: สร้าง icons**

Run (ถ้าไม่มี Pillow: `pip install pillow` ก่อน):

```python
# one-off ใน python REPL หรือไฟล์ชั่วคราวใน scratchpad — ไม่ commit สคริปต์
from PIL import Image, ImageDraw
for size in (192, 512):
    img = Image.new("RGB", (size, size), "#0b1220")
    d = ImageDraw.Draw(img)
    d.ellipse([size*0.15]*2 + [size*0.85]*2, outline="#f59e0b", width=max(4, size//24))
    d.text((size*0.38, size*0.30), "B", fill="#f59e0b")
    img.save(f"dashboard/web/public/icon-{size}.png")
```

Expected: ได้ `icon-192.png` + `icon-512.png` (โลโก้ placeholder — เปลี่ยนทีหลังได้ ไม่ block)

- [ ] **Step 4: ลิงก์ manifest ใน layout**

ใน `dashboard/web/src/app/layout.tsx` — หา `export const metadata` ที่มีอยู่ แล้วเพิ่ม field:

```typescript
export const metadata: Metadata = {
  // ...fields เดิม คงไว้ทั้งหมด...
  manifest: "/manifest.json",
};
```

(ถ้าไฟล์ยังไม่มี metadata export → เพิ่ม `import type { Metadata } from "next";` + export ใหม่มีแค่ manifest)

- [ ] **Step 5: build ผ่าน + commit**

Run: `cd dashboard/web && npm run build`
Expected: build สำเร็จ ไม่มี type error

```bash
git add dashboard/web/public/sw.js dashboard/web/public/manifest.json dashboard/web/public/icon-192.png dashboard/web/public/icon-512.png dashboard/web/src/app/layout.tsx
git commit -m "feat(webpush): service worker + PWA manifest + icons บอร์ด B (N+203)"
```

---

### Task 7: บอร์ด — การ์ด 🔔 + API relay routes

**Files:**
- Create: `dashboard/web/src/components/PushNotifyCard.tsx`
- Create: `dashboard/web/src/app/api/portal/push/subscribe/route.ts`, `.../push/unsubscribe/route.ts`, `.../push/test/route.ts`
- Modify: `dashboard/web/src/app/portal/world/_client.tsx` (mount การ์ด)

**Interfaces:**
- Consumes: engine endpoints Task 5 (ผ่าน relay pattern เดียวกับ `src/app/api/portal/star/route.ts` — session cookie → `X-BMS-Secret`), env `NEXT_PUBLIC_VAPID_PUBLIC_KEY` (Task 1)
- Produces: การ์ด 🔔 บนหน้า world — เปิด/ปิด/ส่งทดสอบ

- [ ] **Step 1: เขียน relay route — subscribe**

```typescript
// dashboard/web/src/app/api/portal/push/subscribe/route.ts
/**
 * POST /api/portal/push/subscribe {endpoint, p256dh, auth, user_agent}
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

  // ช่วงทดลอง: จำกัดเฉพาะบัญชีใน PUSH_ALLOWLIST (comma-separated line_user_id, ว่าง = เปิดทุกคน)
  const allow = (process.env.PUSH_ALLOWLIST ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (allow.length && !allow.includes(session.lineUserId)) {
    return NextResponse.json({ ok: false, error: "not enabled for this account" }, { status: 403 });
  }

  let body: { endpoint?: string; p256dh?: string; auth?: string; user_agent?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  if (!body.endpoint || !body.p256dh || !body.auth) {
    return NextResponse.json({ ok: false, error: "endpoint + keys required" }, { status: 400 });
  }

  try {
    const r = await fetch(`${BMS_API_URL}/api/portal/push-subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET },
      body: JSON.stringify({
        line_user_id: session.lineUserId,
        endpoint: body.endpoint,
        p256dh: body.p256dh,
        auth: body.auth,
        user_agent: body.user_agent ?? "",
      }),
      cache: "no-store",
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : r.status });
  } catch (e) {
    console.error("[/api/portal/push/subscribe]", e);
    return NextResponse.json({ ok: false, error: "engine unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 2: เขียน relay routes — unsubscribe + test**

`unsubscribe/route.ts` — copy โครง subscribe เปลี่ยน: engine path เป็น `/api/portal/push-unsubscribe`, body validation เหลือ `if (!body.endpoint)`, relay body เหลือ `{line_user_id, endpoint: body.endpoint}`, console tag `[/api/portal/push/unsubscribe]`

`test/route.ts` — copy โครงเดียวกัน: engine path `/api/portal/push-test`, ไม่ต้องอ่าน request body เลย (ตัด parse JSON ทิ้ง), relay body `{line_user_id: session.lineUserId}`, console tag `[/api/portal/push/test]`

- [ ] **Step 3: เขียน PushNotifyCard**

```tsx
// dashboard/web/src/components/PushNotifyCard.tsx
"use client";
/**
 * การ์ด 🔔 เปิดรับแจ้งเตือน browser (Web Push) — spec 2026-07-13-web-push-notification-design.md
 * สถานะ: unsupported→ซ่อน · iOS ยังไม่ standalone→สอน Add to Home Screen ·
 * ยังไม่เปิด→ปุ่มเปิด · เปิดแล้ว→✅ + ส่งทดสอบ + ปิด
 */
import { useCallback, useEffect, useState } from "react";

const VAPID_PUBLIC = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

type State = "loading" | "unsupported" | "ios-install" | "off" | "on" | "denied";

export default function PushNotifyCard() {
  const [state, setState] = useState<State>("loading");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !VAPID_PUBLIC) {
        // iOS Safari ที่ยังไม่ Add to Home Screen จะไม่มี PushManager
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        const standalone = window.matchMedia("(display-mode: standalone)").matches
          || (navigator as unknown as { standalone?: boolean }).standalone === true;
        setState(isIOS && !standalone ? "ios-install" : "unsupported");
        return;
      }
      if (Notification.permission === "denied") { setState("denied"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.getSubscription();
      setState(sub ? "on" : "off");
    })().catch(() => setState("unsupported"));
  }, []);

  const enable = useCallback(async () => {
    setBusy(true); setMsg("");
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { setState(perm === "denied" ? "denied" : "off"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC) as BufferSource,
      });
      const json = sub.toJSON();
      const r = await fetch("/api/portal/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          endpoint: sub.endpoint,
          p256dh: json.keys?.p256dh ?? "",
          auth: json.keys?.auth ?? "",
          user_agent: navigator.userAgent,
        }),
      });
      if (r.status === 403) {
        await sub.unsubscribe();
        setState("off"); setMsg("ฟีเจอร์นี้ยังเปิดทดลองเฉพาะบางบัญชี");
        return;
      }
      if (!(await r.json()).ok) throw new Error("save failed");
      setState("on"); setMsg("เปิดรับแจ้งเตือนเครื่องนี้แล้ว ✅");
    } catch {
      setMsg("เปิดไม่สำเร็จ ลองใหม่อีกครั้ง");
    } finally { setBusy(false); }
  }, []);

  const disable = useCallback(async () => {
    setBusy(true); setMsg("");
    try {
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await fetch("/api/portal/push/unsubscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
        await sub.unsubscribe();
      }
      setState("off"); setMsg("ปิดแจ้งเตือนเครื่องนี้แล้ว");
    } catch {
      setMsg("ปิดไม่สำเร็จ ลองใหม่อีกครั้ง");
    } finally { setBusy(false); }
  }, []);

  const sendTest = useCallback(async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch("/api/portal/push/test", { method: "POST" });
      const data = await r.json();
      setMsg(data.ok && data.sent > 0
        ? `ส่งทดสอบแล้ว ${data.sent} เครื่อง — ควรเด้งภายในไม่กี่วินาที`
        : "ส่งไม่สำเร็จ — ลองปิดแล้วเปิดแจ้งเตือนใหม่");
    } catch {
      setMsg("ส่งไม่สำเร็จ — เชื่อมต่อไม่ได้");
    } finally { setBusy(false); }
  }, []);

  if (state === "loading" || state === "unsupported") return null;

  return (
    <div style={{ border: "1px solid #f59e0b44", borderRadius: 12, padding: "12px 16px", margin: "12px 0" }}>
      <div style={{ fontWeight: 600 }}>🔔 แจ้งเตือนผ่านเบราว์เซอร์</div>
      {state === "ios-install" && (
        <p style={{ margin: "6px 0 0", fontSize: 14, opacity: 0.85 }}>
          iPhone/iPad: กดปุ่มแชร์ แล้วเลือก &quot;เพิ่มไปยังหน้าจอโฮม&quot; ก่อน
          จากนั้นเปิดจากไอคอนบนหน้าจอโฮมเพื่อเปิดรับแจ้งเตือน
        </p>
      )}
      {state === "denied" && (
        <p style={{ margin: "6px 0 0", fontSize: 14, opacity: 0.85 }}>
          เบราว์เซอร์นี้ถูกตั้งค่าบล็อกแจ้งเตือนไว้ — ไปที่ตั้งค่าเว็บไซต์ของเบราว์เซอร์
          แล้วอนุญาตการแจ้งเตือน จากนั้นรีเฟรชหน้านี้
        </p>
      )}
      {state === "off" && (
        <button onClick={enable} disabled={busy}
          style={{ marginTop: 8, padding: "8px 16px", borderRadius: 8, cursor: "pointer" }}>
          {busy ? "กำลังเปิด…" : "เปิดรับแจ้งเตือนเครื่องนี้"}
        </button>
      )}
      {state === "on" && (
        <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14 }}>✅ เครื่องนี้รับแจ้งเตือนอยู่</span>
          <button onClick={sendTest} disabled={busy} style={{ padding: "4px 12px", borderRadius: 8, cursor: "pointer" }}>ส่งทดสอบ</button>
          <button onClick={disable} disabled={busy} style={{ padding: "4px 12px", borderRadius: 8, cursor: "pointer" }}>ปิด</button>
        </div>
      )}
      {msg && <p style={{ margin: "6px 0 0", fontSize: 13, opacity: 0.85 }}>{msg}</p>}
    </div>
  );
}
```

(สไตล์ inline ข้างบนเป็น fallback กลางๆ — ตอน mount จริงให้ปรับใช้ class/โทนธีม Board B ที่หน้า world ใช้อยู่ ถ้ามี component card เดิมให้ reuse โครงนั้นแทน div เปล่า)

- [ ] **Step 4: mount บนหน้า world**

ใน `dashboard/web/src/app/portal/world/_client.tsx`: เพิ่ม `import PushNotifyCard from "@/components/PushNotifyCard";` แล้ววาง `<PushNotifyCard />` ไว้ส่วนบนของ render tree หลัก (เหนือ/ใต้ header แรกที่ผู้ใช้เห็นทันทีโดยไม่ต้อง scroll — ดูโครง JSX จริงแล้ววางจุดที่ไม่ทำ layout เพี้ยน)

- [ ] **Step 5: build + ทดสอบ dev + commit**

Run: `cd dashboard/web && npm run build`
Expected: build ผ่าน

Manual check (dev): `npm run dev` → เปิด `http://localhost:3000/portal/world` (login ด้วย LINE ก่อน) → เห็นการ์ด 🔔 → กดเปิด → Chrome ขอ permission → อนุญาต → สถานะเป็น ✅ (ยังส่งทดสอบไม่ได้จนกว่า engine จะ deploy — ปุ่มต้องขึ้น error สุภาพ ไม่ crash)

```bash
git add dashboard/web/src/components/PushNotifyCard.tsx dashboard/web/src/app/api/portal/push dashboard/web/src/app/portal/world/_client.tsx
git commit -m "feat(webpush): การ์ด 🔔 เปิดรับแจ้งเตือน + relay routes บนบอร์ด (N+203)"
```

---

### Task 8: Deploy + E2E จริง (คุณกัญจน์เท่านั้น) + sanity

**Files:**
- Modify: `progress_log.md` (entry N+203), VPS `/opt/bms/app/.env` (VAPID keys), Vercel env

**Interfaces:**
- Consumes: ทุก Task ก่อนหน้า commit ครบแล้วบน local `main`

- [ ] **Step 1: 🛑 GATE — ขอ confirm คุณกัญจน์ก่อน push origin + deploy** (กฎ CLAUDE.md ห้าม push โดยไม่ confirm)

- [ ] **Step 2: push + deploy VPS**

```bash
git push origin main
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "
  cd /opt/bms/app && git pull --ff-only &&
  /opt/bms/venv/bin/pip install pywebpush &&
  printf 'VAPID_PRIVATE_KEY=<ค่าจริงจาก Task 1>\nVAPID_SUBJECT=mailto:kanapr51@gmail.com\n' >> .env &&
  systemctl restart bms-api && systemctl status bms-api --no-pager | head -5"
```

Expected: pull ff-only สำเร็จ, pywebpush installed, bms-api `active (running)`. (line-sender เป็น timer รายนาที — ไม่ต้อง restart ได้โค้ดใหม่รอบถัดไปเอง แต่ env ใหม่มีผลอยู่แล้วเพราะอ่านตอน start ทุกรอบ)

⚠️ ก่อน append .env ตรวจว่ายังไม่มี key ซ้ำ: `grep -c VAPID /opt/bms/app/.env` ต้องเป็น 0 ก่อน append

- [ ] **Step 3: deploy บอร์ด Vercel**

เพิ่ม env บน Vercel (Production):
- `NEXT_PUBLIC_VAPID_PUBLIC_KEY=<ค่าจาก Task 1>`
- `PUSH_ALLOWLIST=<line_user_id ของคุณกัญจน์>` (หาจาก DB: `SELECT line_user_id FROM customers WHERE display_name LIKE '%กัญจน์%'` หรือดูใน `scripts/seed_self_notify.py` — ตอนชวนลูกค้าค่อยเพิ่ม/ล้างค่า)

ผ่าน `cd dashboard/web && npx vercel env add <NAME> production` แล้ว deploy production ตาม flow เดิมของ repo (`npx vercel --prod`)
Expected: deploy READY, หน้า `/portal/world` ขึ้นการ์ด 🔔

- [ ] **Step 4: E2E จริงกับเครื่องคุณกัญจน์**

1. คุณกัญจน์เปิด `https://bid-master-dashboard.vercel.app/portal/world` บน**คอม** → กดเปิดรับแจ้งเตือน → กด "ส่งทดสอบ" → **เด้งภายใน ~5 วิ + กดแล้วเปิด /portal/world** ✅
2. ทำซ้ำบน**มือถือ** ✅
3. ตรวจ DB บน VPS:

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "python3 -c \"
import sqlite3; c = sqlite3.connect('/opt/bms/data/bms_customers.db')
print('subs:', c.execute('SELECT customer_id, substr(endpoint,1,40), disabled_at FROM push_subscriptions').fetchall())
print('log:', c.execute('SELECT status, count(*) FROM webpush_delivery_log GROUP BY 1').fetchall())\""
```

Expected: subscriptions ≥2 (คอม+มือถือ) disabled_at=None, log มี sent ≥2

- [ ] **Step 5: E2E งานจริงจากคิว**

รอ (หรือ trigger) งานใหม่เข้าคิวของ customer คุณกัญจน์ → line-sender รอบถัดไป → browser เด้งการ์ดงาน แม้ LINE จะ fail 429
ตรวจ: `webpush_delivery_log` มีแถว `project_id` ตรงกับ queue item + notification เด้งจริง

- [ ] **Step 6: Sanity check (กฎ CLAUDE.md — dispatch Sophia ถ้า available, ไม่งั้นรันเอง)**

- คิวไม่มี duplicate: `SELECT customer_id, project_id, source_stage, COUNT(*) FROM notification_queue GROUP BY 1,2,3 HAVING COUNT(*)>1` → 0 แถว
- `delivery_log` ไม่มีแถวใหม่จากโค้ด webpush (นับก่อน/หลัง test ต้องเท่ากัน ยกเว้นแถวจาก LINE ปกติ)
- `python scripts/Sebastian_LINE_Sender.py --dry-run` บน VPS → exit 0

- [ ] **Step 7: progress_log entry N+203 + commit + Discord**

เพิ่ม entry N+203 ใน `progress_log.md` (สถานะ LIVE, ตัวเลข subscriptions/log, เกณฑ์เสถียร 3 วันเริ่มนับ) → commit `docs(progress): N+203 web push LIVE` → push (confirm แล้วจาก Step 1) → Discord notify "✅ Web Push บอร์ด B LIVE — เริ่มนับ 3 วันเสถียร"

- [ ] **Step 8: ตั้ง followup ตรวจเสถียร 3 วัน**

บันทึกใน progress_log Followup: ทุกวัน 3 วันติด รัน query เทียบ — ทุก queue item ของ customer ที่มี subscription ต้องมีแถวใน `webpush_delivery_log` (join ด้วย customer_id+project_id+วันที่) → 0 งานหลุด = ผ่าน → ค่อยชวนลูกค้าคนแรก (ทัก LINE manual สอน setup)
