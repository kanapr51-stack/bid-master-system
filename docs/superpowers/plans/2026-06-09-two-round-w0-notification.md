# Two-Round W0 Notification + Detailed Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** แจ้งงานที่ลูกค้าติดตาม 2 รอบ — Round 1 (สรุปราคาเบื้องต้น, ทันทีที่เปิดเผย ~เที่ยง) + Round 2 (ผู้ชนะทางการ + วิเคราะห์ละเอียด) ทั้งคู่มี closed-loop เทียบ prediction จาก "กรอบบนของราคา".

**Architecture:** ขยาย `Sebastian_Winner_Poller` เดิมให้มี stage machine D0→PRELIM→W0. เพิ่ม `prelim_summary.py` (ดึง+parse PDF สรุปราคาเบื้องต้น ผ่าน API chain ที่ RE แล้ว). Round 1/2 format ใน `Sebastian_LINE_Sender`. วิเคราะห์รอบ 2 อ่านประวัติจาก `cgd_winners` (read-only). closed-loop เทียบ `area_price_hi` + `save_prediction` upsert.

**Tech Stack:** Python 3, sqlite3 (stdlib), requests, pdfplumber, pycryptodome (มีแล้ว). ทุก test = standalone script `python scripts\test_X.py` (exit 0 + print OK = ผ่าน). VPS ไม่มี sqlite3 CLI → ใช้ `python3 -c`.

**Spec:** `docs/superpowers/specs/2026-06-09-two-round-w0-notification-design.md`
**API chain doc:** `docs/research/2026-06-09-prelim-bid-summary-api.md`

**Environment notes:**
- ทดสอบ DB ใช้ `:memory:` หรือ `BMS_DB_PATH` env (ตาม convention `test_bms_follow.py`). บาง test ต้อง `BMS_DATA_DIR` (bms_paths) → ตั้ง env ก่อน import
- ❌ Task 10 deploy: confirm กัญจน์ก่อน `git push` (CLAUDE.md)
- implementation log = N+112

---

### Task 1: `save_prediction` upsert (เก็บค่า prediction ล่าสุดที่ส่งจริง)

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py` (`save_prediction` ~line 110-118)
- Test: `scripts/test_save_prediction_upsert.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_save_prediction_upsert.py`:

```python
"""test_save_prediction_upsert.py — save_prediction upsert ทับ prediction แต่ไม่ลบ actual."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()

# save ครั้งแรก (ค่า pooled)
db.save_prediction({"project_id": "P1", "budget": 1000000, "area_disc_lo": 5, "area_disc_hi": 30,
                    "area_price_lo": 700000, "area_price_hi": 950000, "top_name": "A", "top_disc": 20, "top_price": 800000})
# verify actual (W0)
db.update_prediction_actual("P1", 740000, 1, 1.5)
# save ครั้งสอง (ค่า concrete ที่โชว์จริง) → ต้องทับ prediction
db.save_prediction({"project_id": "P1", "budget": 1000000, "area_disc_lo": 24, "area_disc_hi": 41,
                    "area_price_lo": 590000, "area_price_hi": 760000, "top_name": "B", "top_disc": 30, "top_price": 700000})

p = db.get_prediction("P1")
assert p["area_price_hi"] == 760000, p          # prediction ทับแล้ว
assert p["area_disc_lo"] == 24, p
assert p["top_name"] == "B", p
assert p["actual_price"] == 740000, p           # actual ไม่ถูกลบ
assert p["in_range"] == 1 and p["error_pct"] == 1.5, p
assert p["verified_at"] is not None, p
print("OK test_save_prediction_upsert")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_save_prediction_upsert.py`
Expected: FAIL — `assert p["area_price_hi"] == 760000` (เดิม INSERT OR IGNORE → ค่ายังเป็น 950000)

- [ ] **Step 3: Implement upsert**

Replace `save_prediction` (lines 110-118) with:

```python
def save_prediction(p: dict) -> None:
    """เก็บคำทำนายราคาตอน D0 — upsert ทับด้วยค่าล่าสุดที่ส่งจริง (กันค่าเก่าค้าง).
    ON CONFLICT ทับเฉพาะคอลัมน์ prediction — ไม่แตะ actual_price/in_range/error_pct/verified_at."""
    cols = ("project_id", "budget", "area_disc_lo", "area_disc_hi", "area_price_lo",
            "area_price_hi", "top_name", "top_disc", "top_price")
    upd = [c for c in cols if c != "project_id"] + ["predicted_at"]
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO price_predictions ({','.join(cols)}, predicted_at) "
            f"VALUES ({','.join('?' for _ in cols)}, ?) "
            f"ON CONFLICT(project_id) DO UPDATE SET "
            + ", ".join(f"{c}=excluded.{c}" for c in upd),
            tuple(p.get(c) for c in cols) + (_now(),))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_save_prediction_upsert.py`
Expected: `OK test_save_prediction_upsert`

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_Customer_DB.py scripts/test_save_prediction_upsert.py
git commit -m "fix(prediction): save_prediction upsert ทับค่าล่าสุด (ไม่ลบ actual) — closed-loop ใช้ค่าที่โชว์จริง"
```

---

### Task 2: `compare_prediction` เทียบกรอบบน + provisional (display-only)

**Files:**
- Modify: `scripts/cgd_intel.py` (`compare_prediction` ~line 318)
- Test: `scripts/test_compare_upper_bound.py`

ความหมายใหม่: วัดเทียบ `area_price_hi` (กรอบบนราคา). `held = actual <= hi` (อยู่ในกรอบ). `error_pct = (actual-hi)/hi*100` (มีเครื่องหมาย: + = จริงสูงกว่ากรอบบน).

- [ ] **Step 1: Write the failing test**

Create `scripts/test_compare_upper_bound.py`:

```python
"""test_compare_upper_bound.py — compare_prediction เทียบกรอบบน + provisional ไม่เขียน DB."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import cgd_intel as ci

db.save_prediction({"project_id": "P1", "budget": 1000000, "area_disc_lo": 28, "area_disc_hi": 33,
                    "area_price_lo": 670000, "area_price_hi": 730000, "top_name": "A", "top_disc": 30, "top_price": 700000})

# formal: actual 740000 > hi 730000 → นอกกรอบ (สูงกว่า) error +1.37%
v = ci.compare_prediction("P1", 740000)
assert v and v["held"] is False, v
assert abs(v["error_pct"] - 1.37) < 0.1, v       # (740000-730000)/730000*100
assert v["upper"] == 730000, v
# commit แล้ว (verified)
p = db.get_prediction("P1")
assert p["actual_price"] == 740000 and p["verified_at"] is not None, p
assert p["in_range"] == 0, p                      # held=False → in_range=0

# provisional (Round 1): ไม่เขียน DB
db.save_prediction({"project_id": "P2", "budget": 1000000, "area_disc_lo": 28, "area_disc_hi": 33,
                    "area_price_lo": 670000, "area_price_hi": 730000, "top_name": "A", "top_disc": 30, "top_price": 700000})
vp = ci.compare_prediction_provisional("P2", 720000)   # 720000 <= 730000 → held
assert vp and vp["held"] is True and vp["upper"] == 730000, vp
p2 = db.get_prediction("P2")
assert p2["actual_price"] is None and p2["verified_at"] is None, p2   # ไม่เขียน

print("OK test_compare_upper_bound")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_compare_upper_bound.py`
Expected: FAIL — `compare_prediction_provisional` ไม่มี / key `held`/`upper` ไม่มี

- [ ] **Step 3: Implement**

In `scripts/cgd_intel.py`, replace the body of `compare_prediction` (เดิมคำนวณ mid/in_range) — find the block:

```python
    lo, hi = p["area_price_lo"], p["area_price_hi"]
    in_range = lo <= actual <= hi
    mid = (lo + hi) / 2
    error_pct = round(abs(actual - mid) / actual * 100, 1)
    update_prediction_actual(project_id, round(actual), 1 if in_range else 0, error_pct)
    return {"in_range": in_range, "error_pct": error_pct,
            "area_price_lo": lo, "area_price_hi": hi, "actual": round(actual)}
```

แทนด้วย (เทียบกรอบบน + แยก commit ออกเป็น helper):

```python
    return _compare_core(project_id, p, actual, commit=True)
```

แล้วเพิ่ม 2 ฟังก์ชันใหม่ ใต้ `compare_prediction` (ก่อน `predict_lines`):

```python
def compare_prediction_provisional(project_id: str, actual_price, conn=None):
    """เทียบเบื้องต้น (Round 1) — เหมือน compare_prediction แต่ไม่เขียน DB/สถิติ."""
    from Sebastian_Customer_DB import get_prediction
    try:
        actual = float(actual_price)
    except (TypeError, ValueError):
        return None
    if not actual:
        return None
    p = get_prediction(project_id)
    if not p or p.get("area_price_hi") is None:
        return None
    return _compare_core(project_id, p, actual, commit=False)


def _compare_core(project_id: str, p: dict, actual: float, commit: bool) -> dict:
    """core เทียบกรอบบน. held = actual <= area_price_hi. error% = (actual-hi)/hi (มีเครื่องหมาย)."""
    from Sebastian_Customer_DB import update_prediction_actual
    hi = p["area_price_hi"]
    held = actual <= hi
    error_pct = round((actual - hi) / hi * 100, 1)
    if commit:
        update_prediction_actual(project_id, round(actual), 1 if held else 0, error_pct)
    return {"held": held, "error_pct": error_pct, "upper": hi,
            "area_price_lo": p["area_price_lo"], "area_price_hi": hi, "actual": round(actual)}
```

> `compare_prediction` signature เดิม `(project_id, actual_price, conn=None)` คงไว้ — แค่เปลี่ยน return เป็น `{"held",...}`. ผู้เรียก (verify_hook ใน Winner_Poller) อ่าน `v["in_range"]` เดิม → **ต้องแก้ verify_hook ใน Task 8** ให้ใช้ `v["held"]`.

ในตัว `compare_prediction` เก็บ guard เดิม (try float, get_prediction, ตรวจ area_price_hi None) แล้วจบด้วย `return _compare_core(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_compare_upper_bound.py`
Expected: `OK test_compare_upper_bound`

- [ ] **Step 5: Regression — closed-loop test เดิม**

Run: `python scripts\test_price_prediction.py`
Expected: ผ่าน (ถ้า assert `in_range` เดิมพัง → แก้ test ให้ใช้ `held` ตามความหมายใหม่ — เป็น test ของเราเอง)

- [ ] **Step 6: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_compare_upper_bound.py scripts/test_price_prediction.py
git commit -m "feat(closed-loop): เทียบ prediction จากกรอบบน (area_price_hi) + provisional display-only"
```

---

### Task 3: `prelim_summary` — parse PDF สรุปราคาเบื้องต้น

**Files:**
- Create: `scripts/prelim_summary.py` (parse functions)
- Test: `scripts/test_prelim_summary.py`

แยก parse (pure, testable) ออกจาก fetch (network, Task 4).

- [ ] **Step 1: Write the failing test**

Create `scripts/test_prelim_summary.py`:

```python
"""test_prelim_summary.py — parse_prelim_text: ราคา/จำนวนผู้เสนอ/เวลาเปิดเผย + 2-ซอง."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import prelim_summary as ps

# งานหลักเกณฑ์ราคา (มีราคา) — ตัวเลขไทย
TXT_PRICE = """สรุปข้อมูลการเสนอราคาเบื้องต้น
เลขที่โครงการ : ๖๙๐๕๙๐๗๕๔๕๔
จำนวนผู้เสนอราคา : ๓ ราย
หลักเกณฑ์การพิจารณา : หลักเกณฑ์ราคา
การเสนอราคาเบื้องต้น
รายการพิจารณา ราคาต่ำสุดที่เสนอ
รายการพิจารณาที่ ๑ ก่อสร้างถนนคอนกรีตเสริมเหล็ก ๗๔๐,๐๐๐.๐๐
เปิดเผย ณ วันที่ ๙ มิถุนายน ๒๕๖๙ เวลา ๑๒:๐๒ น."""

r = ps.parse_prelim_text(TXT_PRICE)
assert r["has_price"] is True, r
assert r["lowest_price"] == 740000.0, r
assert r["num_bidders"] == 3, r
assert r["revealed_at"] and "12:02" in r["revealed_at"], r

# งานเกณฑ์ขั้นต่ำ 2 ซอง — ไม่แสดงราคา
TXT_TWOENV = """สรุปข้อมูลการเสนอราคาเบื้องต้น
จำนวนผู้เสนอราคา : ๒ ราย
หลักเกณฑ์การพิจารณา : เกณฑ์ราคาประกอบเกณฑ์อื่น
การเสนอราคาแบบเกณฑ์ขั้นต่ำ (๒ ซอง) จะไม่มีการแสดงข้อมูลราคา
เปิดเผย ณ วันที่ ๙ มิถุนายน ๒๕๖๙ เวลา ๑๔:๐๐ น."""
r2 = ps.parse_prelim_text(TXT_TWOENV)
assert r2["has_price"] is False and r2["lowest_price"] is None, r2
assert r2["num_bidders"] == 2, r2

# garbage → ปลอดภัย
r3 = ps.parse_prelim_text("ไม่มีข้อมูล")
assert r3["num_bidders"] is None and r3["lowest_price"] is None, r3

print("OK test_prelim_summary")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_prelim_summary.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'prelim_summary'`

- [ ] **Step 3: Implement parse**

Create `scripts/prelim_summary.py`:

```python
"""prelim_summary.py — ดึง+parse "สรุปข้อมูลการเสนอราคาเบื้องต้น" (ราคาต่ำสุด early signal).
API chain: ดู docs/research/2026-06-09-prelim-bid-summary-api.md. graceful — ห้ามทำ poller ล่ม."""
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_NUM_RE = re.compile(r"([\d,]+\.\d{2})")
_BIDDERS_RE = re.compile(r"จำนวนผู้เสนอราคา\s*:?\s*(\d+)")
_REVEAL_RE = re.compile(r"เปิดเผย ณ วันที่\s*(\d{1,2})\s*([ก-๙฀-๿]+)\s*(\d{4})\s*เวลา\s*(\d{1,2}:\d{2})")


def parse_prelim_text(text: str) -> dict:
    """parse ข้อความ PDF → {has_price, lowest_price, num_bidders, revealed_at}."""
    t = (text or "").translate(_THAI_DIGITS)
    out = {"has_price": False, "lowest_price": None, "num_bidders": None, "revealed_at": None}
    mb = _BIDDERS_RE.search(t)
    if mb:
        out["num_bidders"] = int(mb.group(1))
    # 2-ซอง → ไม่แสดงราคา
    two_env = "ไม่มีการแสดงข้อมูลราคา" in t or "เกณฑ์ขั้นต่ำ" in t and "ราคาต่ำสุดที่เสนอ" not in t
    if "ราคาต่ำสุดที่เสนอ" in t and not ("ไม่มีการแสดงข้อมูลราคา" in t):
        # หาเลขราคาในบรรทัด "รายการพิจารณาที่ ..."
        for line in t.split("\n"):
            if "รายการพิจารณาที่" in line:
                m = _NUM_RE.search(line)
                if m:
                    out["lowest_price"] = float(m.group(1).replace(",", ""))
                    out["has_price"] = True
                    break
    mr = _REVEAL_RE.search(t)
    if mr:
        out["revealed_at"] = f"{mr.group(1)} {mr.group(2)} {mr.group(3)} {mr.group(4)}"
    return out


def parse_prelim_pdf(pdf_bytes: bytes) -> dict:
    """pdf → text → parse_prelim_text. graceful: error → ฟิลด์ None."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
            for pg in doc.pages:
                text += (pg.extract_text() or "") + "\n"
        return parse_prelim_text(text)
    except Exception:
        return {"has_price": False, "lowest_price": None, "num_bidders": None, "revealed_at": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_prelim_summary.py`
Expected: `OK test_prelim_summary`

- [ ] **Step 5: Commit**

```bash
git add scripts/prelim_summary.py scripts/test_prelim_summary.py
git commit -m "feat(prelim): parse_prelim_text/pdf — สรุปราคาเบื้องต้น (ราคาต่ำสุด/ผู้เสนอ/เวลา)"
```

---

### Task 4: `prelim_summary` — fetch chain (network) + gate

**Files:**
- Modify: `scripts/prelim_summary.py` (เพิ่ม `fetch_prelim_summary` + `_has_price_announcement`)
- Test: integration sanity (รันจริง 1 งาน — ไม่ unit เพราะ network)

- [ ] **Step 1: เพิ่ม fetch chain**

Append to `scripts/prelim_summary.py`:

```python
import requests
import process5_http_client as p

PASSKEY = "0b3464ada27f4a3baaf863dc3e68f8b9"
APIKEY_UUID = "0b3464ad-a27f-4a3b-aaf8-63dc3e68f8b9"
MERCHANT_GENPRICE = "https://process5.gprocurement.go.th/egp-merchant-ebidding-service/common/genReportPrice"
VIEWPDF = "https://process5.gprocurement.go.th/egp-template-service/FileViewer/viewPdf"
TIMEOUT = 25


def _hdr(token):
    h = p.HEADERS_NO_AUTH.copy()
    h["X-Announcement-Token"] = token
    return h


def _has_price_announcement(pid: str, token: str, method_id: str) -> bool:
    """gate: greenBook list มี announceType 'price' ไหม (สรุปราคาเปิดเผยแล้ว)."""
    try:
        b = p._get(f"{p.API_BASE}/greenBook",
                   {"mode": "LINK", "methodId": method_id, "tempProjectId": pid, "pageAnnounceType": "B0"},
                   token=token)
        docs = ((b or {}).get("data") or {}).get("greenBookAnnouncementTypeLinkDto") or []
        return any((d.get("announceType") == "price") for d in docs)
    except Exception:
        return False


def fetch_prelim_summary(pid: str, method_id: str = "16") -> dict:
    """ดึงสรุปราคาเบื้องต้น (pure-API). คืน {"has_summary", + ฟิลด์จาก parse}. graceful."""
    base = {"has_summary": False, "has_price": False, "lowest_price": None,
            "num_bidders": None, "revealed_at": None}
    try:
        token = p._get_token(pid)
        if not token or not _has_price_announcement(pid, token, method_id):
            return base
        h = _hdr(token)
        enc_pid = requests.get(f"{p.API_BASE}/encryptApiKey",
                               params={"passKey": PASSKEY, "sDataValue": pid}, headers=h, timeout=TIMEOUT).json().get("data")
        enc_api = requests.get(f"{p.API_BASE}/encryptApiKey",
                               params={"passKey": PASSKEY, "sDataValue": APIKEY_UUID}, headers=h, timeout=TIMEOUT).json().get("data")
        if not enc_pid or not enc_api:
            return base
        uuid = requests.get(MERCHANT_GENPRICE, params={"projectId": enc_pid, "apiKey": enc_api},
                            headers=h, timeout=TIMEOUT).json().get("data")
        if not uuid:
            return base
        import base64
        b64 = requests.post(f"{VIEWPDF}/{uuid}", json={}, headers=h, timeout=TIMEOUT).json().get("data")
        if not b64:
            return base
        parsed = parse_prelim_pdf(base64.b64decode(b64))
        parsed["has_summary"] = True
        return parsed
    except Exception as e:
        print(f"[prelim] fetch error {pid}: {type(e).__name__}: {e}", file=sys.stderr)
        return base
```

- [ ] **Step 2: Integration sanity (รันบน VPS — มี token/network)**

Run บน VPS:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "set -a; . /opt/bms/app/.env; set +a; cd /opt/bms/app && BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c \"import sys; sys.path.insert(0,'scripts'); import prelim_summary as ps; print(ps.fetch_prelim_summary('69059075454'))\""
```
Expected: `{'has_summary': True, 'has_price': True, 'lowest_price': 740000.0, 'num_bidders': 3, 'revealed_at': '9 ...'}`

- [ ] **Step 3: Commit**

```bash
git add scripts/prelim_summary.py
git commit -m "feat(prelim): fetch_prelim_summary pure-API chain (encryptApiKey→genReportPrice→viewPdf) + greenBook gate"
```

---

### Task 5: Round 2 analysis helpers ใน `cgd_intel`

**Files:**
- Modify: `scripts/cgd_intel.py` (เพิ่ม `company_area_history`, `analyze_bidders`)
- Test: `scripts/test_round2_analysis.py`

`analyze_bidders` รับ bidders (จาก bid_results) + scope → คืน list เรียงราคา + ประวัติพื้นที่ + ป้าย.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_round2_analysis.py`:

```python
"""test_round2_analysis.py — company_area_history + analyze_bidders (ranking, ประวัติ, ป้าย)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    rows = [  # หจก.X เคยลดในตำบลโพนทอง 2 ครั้ง (24,26→median25)
        ("h1", "ถนน คสล. โพนทอง", "หจก.X", 24.0, "บ้านแพง", "โพนทอง"),
        ("h2", "ถนน คสล. โพนทอง", "หจก.X", 26.0, "บ้านแพง", "โพนทอง"),
        ("h3", "ถนน คสล. นาแก", "หจก.Y", 30.0, "นาแก", "พิมาน"),   # Y นอกตำบลโพนทอง
    ]
    for pid, name, win, disc, dist, sub in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", name, win, 100000, disc, "2567", EB, dist, sub))
    c.commit(); return c


def test_company_area_history():
    c = _conn()
    h = ci.company_area_history(c, "นครพนม", ["ถนน"], "หจก.X", "โพนทอง", "บ้านแพง")
    assert h["scope"] == "ตำบล" and h["n"] == 2 and abs(h["median"] - 25) < 0.01, h
    h2 = ci.company_area_history(c, "นครพนม", ["ถนน"], "หจก.Y", "โพนทอง", "บ้านแพง")
    assert h2["scope"] == "นอกตำบล" and h2["n"] == 1, h2   # Y ไม่มีในโพนทอง → fallback ทั้งจังหวัด
    h3 = ci.company_area_history(c, "นครพนม", ["ถนน"], "หจก.Z", "โพนทอง", "บ้านแพง")
    assert h3["n"] == 0, h3                                  # หน้าใหม่
    print("✅ company_area_history")


def test_analyze_bidders():
    c = _conn()
    bidders = [  # จาก bid_results: name, price_proposal, is_winner
        {"bidder_name": "หจก.X", "price_proposal": "738000", "is_winner": 1},
        {"bidder_name": "หจก.Y", "price_proposal": "752000", "is_winner": 0},
        {"bidder_name": "หจก.Z", "price_proposal": "760000", "is_winner": 0},
    ]
    warned = ["หจก.X"]   # top-3 intel ที่เตือนตอน D0
    out = ci.analyze_bidders(c, "นครพนม", ["ถนน"], "โพนทอง", "บ้านแพง", 1017000, bidders, warned)
    assert [b["name"] for b in out] == ["หจก.X", "หจก.Y", "หจก.Z"], out   # เรียงราคา
    assert out[0]["is_winner"] and out[0]["tag"] == "warned", out          # X เตือนแล้ว
    assert out[1]["tag"] == "regular_missed", out                          # Y มีประวัติ(นอกตำบล) แต่ไม่เตือน
    assert out[2]["tag"] == "newcomer", out                                # Z หน้าใหม่
    assert out[0]["hist"]["n"] == 2, out                                   # X ประวัติตำบล 2 ครั้ง
    print("✅ analyze_bidders")


if __name__ == "__main__":
    test_company_area_history()
    test_analyze_bidders()
    print("\n✅ ALL test_round2_analysis PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_round2_analysis.py`
Expected: FAIL — `AttributeError: module 'cgd_intel' has no attribute 'company_area_history'`

- [ ] **Step 3: Implement helpers**

In `scripts/cgd_intel.py`, add after `_fetch` (ใช้ `_fetch` + `_pct` ที่มี):

```python
def company_area_history(conn, province, tokens, company, subdistrict, district) -> dict:
    """ประวัติส่วนลดของบริษัทในพื้นที่ (competitive-set). ตำบลก่อน ไม่มี→ทั้งจังหวัด.
    คืน {scope:'ตำบล'|'นอกตำบล'|'', n, median}."""
    trows = [r for r in _fetch(conn, province, tokens, subdistrict=subdistrict, district=district)
             if r.get("winner") == company]
    if trows:
        discs = [r["discount_pct"] for r in trows if r.get("discount_pct") is not None]
        return {"scope": "ตำบล", "n": len(trows), "median": _pct(discs, 50)}
    prows = [r for r in _fetch(conn, province, tokens) if r.get("winner") == company]
    if prows:
        discs = [r["discount_pct"] for r in prows if r.get("discount_pct") is not None]
        return {"scope": "นอกตำบล", "n": len(prows), "median": _pct(discs, 50)}
    return {"scope": "", "n": 0, "median": None}


def analyze_bidders(conn, province, tokens, subdistrict, district, budget, bidders, warned) -> list:
    """วิเคราะห์ผู้ยื่นทุกราย: เรียงราคา + ส่วนลดครั้งนี้ + ประวัติพื้นที่ + เทรนด์ + ป้าย.
    bidders: list[{bidder_name, price_proposal, is_winner}]. warned: ชื่อ top-3 ที่เตือนตอน D0.
    tag: 'warned' | 'regular_missed' (มีประวัติแต่ไม่เตือน) | 'newcomer'."""
    def _price(b):
        try:
            return float(b.get("price_proposal") or 0)
        except (TypeError, ValueError):
            return 0.0
    ranked = sorted([b for b in bidders if _price(b) > 0], key=_price)
    out = []
    b_ = float(budget) if budget else 0
    for b in ranked:
        name = b.get("bidder_name") or "?"
        price = _price(b)
        disc = round((1 - price / b_) * 100, 1) if b_ > 0 else None
        hist = company_area_history(conn, province, tokens, name, subdistrict, district)
        trend = None
        if hist["median"] is not None and disc is not None:
            trend = "↑" if disc > hist["median"] + 1 else "↓" if disc < hist["median"] - 1 else "→"
        if name in warned:
            tag = "warned"
        elif hist["n"] > 0:
            tag = "regular_missed"
        else:
            tag = "newcomer"
        out.append({"name": name, "price": price, "discount": disc, "is_winner": bool(b.get("is_winner")),
                    "hist": hist, "trend": trend, "tag": tag})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_round2_analysis.py`
Expected: `✅ ALL test_round2_analysis PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_round2_analysis.py
git commit -m "feat(intel): company_area_history + analyze_bidders (Round 2 — ranking/ประวัติ/ป้ายเจ้าประจำหลุด top3)"
```

---

### Task 6: Round 1 message — `format_prelim_notification`

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (เพิ่มฟังก์ชัน ใกล้ `format_winner` ~line 369)
- Test: `scripts/test_format_prelim.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_format_prelim.py`:

```python
"""test_format_prelim.py — format_prelim_notification (มีราคา + closed-loop / 2-ซอง)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as snd

# มีราคา + cmp (จาก compare_prediction_provisional)
prelim = {"has_price": True, "lowest_price": 740000.0, "num_bidders": 3, "revealed_at": "9 มิ.ย. 2569 12:02"}
cmp = {"held": False, "error_pct": 1.4, "upper": 730000, "area_price_lo": 670000, "area_price_hi": 730000}
txt = snd.format_prelim_notification("ถนนคอนกรีต ต.โพธิ์หมากแข้ง", 1017000, prelim, cmp, "P1")
assert "เบื้องต้น" in txt and "740,000" in txt and "3 ราย" in txt, txt
assert "กรอบบน" in txt and "730,000" in txt, txt
assert "รอประกาศผู้ชนะ" in txt and "P1" in txt, txt

# 2-ซอง (ไม่มีราคา) → ไม่มีบรรทัดเทียบ
prelim2 = {"has_price": False, "lowest_price": None, "num_bidders": 2, "revealed_at": ""}
txt2 = snd.format_prelim_notification("งาน", 1000000, prelim2, None, "P2")
assert "2 ราย" in txt2 and "ยังไม่เปิดเผย" in txt2, txt2
assert "กรอบบน" not in txt2, txt2
print("OK test_format_prelim")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_format_prelim.py`
Expected: FAIL — `AttributeError: ... 'format_prelim_notification'`

- [ ] **Step 3: Implement**

In `scripts/Sebastian_LINE_Sender.py`, add before `format_winner` (~line 369):

```python
def format_prelim_notification(project_name: str, budget, prelim: dict, cmp: dict, project_id: str = "") -> str:
    """Round 1 — สรุปราคาเบื้องต้น (ยังไม่ทางการ). cmp = compare_prediction_provisional หรือ None."""
    lines = ["🔔 ผลเสนอราคาเบื้องต้น (ยังไม่ทางการ)"]
    if project_name:
        lines.append(f"🏗 {project_name[:80]}")
    lines.append(f"💰 ราคากลาง {_fmt_baht(budget)} บาท")
    n = prelim.get("num_bidders")
    if prelim.get("has_price") and prelim.get("lowest_price"):
        low = prelim["lowest_price"]
        lines.append(f"📊 ราคาต่ำสุดที่เสนอ: {_fmt_baht(low)} บาท · ผู้เสนอ {n} ราย")
        if cmp and cmp.get("upper"):
            side = "สูงกว่า" if not cmp["held"] else "ต่ำกว่า/เท่า"
            lines.append(f"🎯 เทียบกรอบบนที่เราคาด {_fmt_baht(cmp['upper'])}: "
                         f"จริง {_fmt_baht(low)} → {side} {abs(cmp['error_pct']):.1f}%")
            try:
                d = (1 - float(low) / float(budget)) * 100
                lines.append(f"   (ส่วนลดจริง {d:.0f}%)")
            except (ValueError, TypeError, ZeroDivisionError):
                pass
    else:
        lines.append(f"📊 มีผู้เสนอ {n} ราย · ราคายังไม่เปิดเผย (เกณฑ์ 2 ซอง) · รอผลทางการ")
    lines.append("⏳ รอประกาศผู้ชนะทางการ — จะแจ้งรายชื่อ + คู่แข่งอีกครั้ง")
    if project_id:
        lines.append(f"🔑 {project_id}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_format_prelim.py`
Expected: `OK test_format_prelim`

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/test_format_prelim.py
git commit -m "feat(round1): format_prelim_notification — ราคาต่ำสุด + closed-loop เบื้องต้น (2-ซอง graceful)"
```

---

### Task 7: Round 2 detailed message — `format_winner_detailed`

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (เพิ่ม `format_winner_detailed` ใกล้ `format_winner`)
- Test: `scripts/test_format_winner_detailed.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_format_winner_detailed.py`:

```python
"""test_format_winner_detailed.py — Round 2: ผู้ชนะ + ความแม่น + breakdown ต่อราย + ป้าย."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as snd

analyzed = [
    {"name": "หจก.X", "price": 738000, "discount": 27.4, "is_winner": True,
     "hist": {"scope": "ตำบล", "n": 2, "median": 25.0}, "trend": "↑", "tag": "warned"},
    {"name": "หจก.Y", "price": 752000, "discount": 26.1, "is_winner": False,
     "hist": {"scope": "นอกตำบล", "n": 4, "median": 30.0}, "trend": "↓", "tag": "regular_missed"},
    {"name": "หจก.Z", "price": 760000, "discount": 25.3, "is_winner": False,
     "hist": {"scope": "", "n": 0, "median": None}, "trend": None, "tag": "newcomer"},
]
cmp = {"held": False, "error_pct": 1.1, "upper": 730000}
acc = {"verified": 5, "in_range": 4, "in_range_pct": 80.0}
txt = snd.format_winner_detailed("ถนนคอนกรีต", "หจก.X", 738000, 1017000, analyzed, cmp, acc, 28.0, "P1")
assert "ผู้ชนะ: หจก.X" in txt and "738,000" in txt, txt
assert "เทียบกรอบบน" in txt and "อยู่ในกรอบ 4/5" in txt, txt
assert "หจก.Y" in txt and "เจ้าประจำ" in txt, txt          # ป้าย regular_missed
assert "หน้าใหม่" in txt, txt                                # Z
assert "ตลาดตำบล 28" in txt, txt
print("OK test_format_winner_detailed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_format_winner_detailed.py`
Expected: FAIL — no attribute `format_winner_detailed`

- [ ] **Step 3: Implement**

In `scripts/Sebastian_LINE_Sender.py`, add after `format_winner`:

```python
_TAG_LABEL = {"warned": "✅เราเตือน", "regular_missed": "🔸เจ้าประจำที่หลุด top3", "newcomer": "หน้าใหม่"}


def format_winner_detailed(project_name, winner, price_agree, budget, analyzed, cmp, acc, market_disc, project_id=""):
    """Round 2 — ผู้ชนะ + ความแม่น(กรอบบน)+สะสม + breakdown ต่อราย(ประวัติ/ป้าย) + ส่วนลด vs ตลาด.
    analyzed = cgd_intel.analyze_bidders(...). cmp = compare_prediction(...). acc = prediction_accuracy_summary()."""
    lines = ["⭐ งานที่ติดตาม — ประกาศผู้ชนะแล้ว"]
    if project_name:
        lines.append(f"🏗 {project_name[:80]}")
    win_disc = ""
    try:
        win_disc = f" (ลด {(1 - float(price_agree)/float(budget))*100:.1f}%)"
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    lines.append(f"🏆 ผู้ชนะ: {winner} · {_fmt_baht(price_agree)}{win_disc}")
    if cmp and cmp.get("upper"):
        side = "สูงกว่า" if not cmp["held"] else "ต่ำกว่า/เท่า"
        line = f"🎯 ความแม่น (เทียบกรอบบน {_fmt_baht(cmp['upper'])}): จริง {_fmt_baht(price_agree)} → {side} {abs(cmp['error_pct']):.1f}%"
        if acc and acc.get("verified"):
            line += f" · สะสมอยู่ในกรอบ {acc['in_range']}/{acc['verified']}"
        lines.append(line)
    if analyzed:
        lines.append(f"📊 ผู้ยื่น {len(analyzed)} ราย (เรียงราคา · เทียบประวัติพื้นที่):")
        for i, b in enumerate(analyzed, 1):
            crown = "🏆" if b["is_winner"] else "  "
            h = b["hist"]
            if h["n"] > 0:
                hist_s = f"{h['scope']}เคย~{h['median']:.0f}%({h['n']}ครั้ง) {b['trend'] or ''}"
            else:
                hist_s = "ไม่มีประวัติ"
            d = f"ลด{b['discount']:.0f}%" if b["discount"] is not None else ""
            lines.append(f" {i}){crown} {b['name'][:24]} {_fmt_baht(b['price'])} {d} · {hist_s} · {_TAG_LABEL.get(b['tag'],'')}")
    if market_disc is not None and analyzed:
        wd = next((b["discount"] for b in analyzed if b["is_winner"]), None)
        if wd is not None:
            rel = "มากกว่า" if wd > market_disc + 1 else "น้อยกว่า" if wd < market_disc - 1 else "พอๆกัน"
            lines.append(f"📉 ผู้ชนะลด {wd:.0f}% vs ตลาดตำบล {market_disc:.0f}% ({rel})")
    if project_id:
        lines.append(f"🔑 {project_id}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_format_winner_detailed.py`
Expected: `OK test_format_winner_detailed`

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/test_format_winner_detailed.py
git commit -m "feat(round2): format_winner_detailed — breakdown ต่อราย + ความแม่นกรอบบน+สะสม + vs ตลาด"
```

---

### Task 8: Winner_Poller stage machine (prelim pass + formal pass)

**Files:**
- Modify: `scripts/Sebastian_Winner_Poller.py` (`poll_winners` + `verify_hook`)
- Test: `scripts/test_winner_poller_prelim.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_winner_poller_prelim.py`:

```python
"""test_winner_poller_prelim.py — stage machine D0→PRELIM→W0 (inject resolvers)."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
                 "VALUES ('U','n','trial',1,'t','t')")
    conn.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
                 "VALUES ('PA','งานA','D0','นครพนม',1000000,'t')")
import Sebastian_Winner_Poller as wp
store = db.SubscriptionStore()
store.add_follow(1, "PA", "D0")   # follow @ D0

# รอบ 1: prelim มี → Round 1 + mark PRELIM
stats = wp.poll_winners(store, lambda pid: {},   # formal ยังไม่มี
                        resolve_prelim=lambda pid: {"has_summary": True, "has_price": True,
                                                    "lowest_price": 740000, "num_bidders": 3, "revealed_at": "x"})
with db.get_connection() as c:
    q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='PA' AND source_stage='followed_prelim'").fetchone()[0]
    st = c.execute("SELECT last_stage_notified FROM followed_jobs WHERE project_id='PA'").fetchone()[0]
assert q == 1 and st == "PRELIM", (q, st)

# รอบ 2: formal มี → Round 2 + mark W0 + close
stats2 = wp.poll_winners(store, lambda pid: {"winner": "หจก.X", "winning_price": "738000",
                                             "bidders": [{"bidder_name": "หจก.X", "is_winner": True}]},
                         resolve_prelim=lambda pid: {"has_summary": False})
with db.get_connection() as c:
    qw = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='PA' AND source_stage='followed_winner'").fetchone()[0]
    active = c.execute("SELECT COUNT(*) FROM followed_jobs WHERE project_id='PA' AND status='active'").fetchone()[0]
assert qw == 1 and active == 0, (qw, active)   # ยิง winner + ปิด follow
print("OK test_winner_poller_prelim")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_winner_poller_prelim.py`
Expected: FAIL — `poll_winners()` ไม่รับ `resolve_prelim`

- [ ] **Step 3: Implement stage machine**

In `scripts/Sebastian_Winner_Poller.py`, replace `poll_winners` signature + add prelim pass. เปลี่ยน def เป็น:

```python
def poll_winners(store, resolve_result, now: str = None, log=print,
                 max_days: int = MAX_DAYS, sleep_sec: int = 0, verify_hook=None,
                 resolve_prelim=None) -> dict:
```

ก่อน loop `for pid, fs in by_pid.items()` เดิม (ซึ่ง filter `last == "D0"`) — เปลี่ยน filter ให้รวม PRELIM สำหรับ formal pass, และเพิ่ม prelim pass. แทนบล็อก `follows = [...]` + `by_pid` เดิมด้วย:

```python
    mode = os.environ.get("BMS_PROVINCE_NOTIFY_MODE", "preview")
    all_active = store.get_active_follows()
    # formal pass: poll งานที่ stage D0 หรือ PRELIM
    formal_follows = [f for f in all_active if (f.get("last_stage_notified") or "") in ("D0", "PRELIM")]
    # prelim pass: เฉพาะ stage D0 ที่ยังไม่เคยแจ้งเบื้องต้น
    prelim_follows = [f for f in all_active if (f.get("last_stage_notified") or "") == "D0"]
    by_pid = {}
    for f in formal_follows:
        by_pid.setdefault(f["project_id"], []).append(f)
    prelim_by_pid = {}
    for f in prelim_follows:
        prelim_by_pid.setdefault(f["project_id"], []).append(f)
```

จากนั้นก่อน formal loop เพิ่ม **prelim pass** (ใช้ names ที่ query ไว้แล้ว — ย้าย names query ขึ้นมาก่อน ครอบทั้ง by_pid+prelim_by_pid keys):

```python
    # --- Prelim pass (Round 1) ---
    if resolve_prelim is not None:
        for pid, fs in prelim_by_pid.items():
            try:
                pr = resolve_prelim(pid) or {}
            except Exception as e:
                log(f"  prelim {pid} error: {type(e).__name__}: {e}"); pr = {}
            if not pr.get("has_summary"):
                continue
            meta = names.get(pid, {})
            for f in fs:
                cid = f["customer_id"]
                if mode == "live":
                    store.enqueue_for_customer(cid, {
                        "project_id": pid, "province": meta.get("province", ""),
                        "project_name": meta.get("project_name", ""),
                        "source_stage": "followed_prelim"})
                    store.mark_stage_notified(cid, pid, "PRELIM")
                    log(f"  📊→ prelim ENQUEUED {pid} cust{cid} low={pr.get('lowest_price')}")
                else:
                    log(f"  [SHADOW] prelim {pid} cust{cid}: {pr.get('lowest_price')} / {pr.get('num_bidders')} ราย")
            stats["notified_prelim"] = stats.get("notified_prelim", 0) + 1
            if sleep_sec:
                time.sleep(sleep_sec)
```

เพิ่ม `"notified_prelim": 0` ใน `stats` dict ตอน init. **สำคัญ:** ย้ายบล็อก `names = {}` + query projects_seen ขึ้นมา**ก่อน** prelim pass และ union keys: `qpids = set(by_pid) | set(prelim_by_pid)` ใช้ qpids ใน WHERE IN.

(formal loop เดิมคงไว้ — มันใช้ `by_pid` ที่ตอนนี้รวม PRELIM-stage follows แล้ว)

- [ ] **Step 4: แก้ verify_hook ใช้ held**

In `main()` `verify_hook`, เปลี่ยน `verdict` line จาก `v["in_range"]` → `v["held"]`:

```python
        verdict = "✅ อยู่ในกรอบ" if v["held"] else "❌ นอกกรอบ"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python scripts\test_winner_poller_prelim.py`
Expected: `OK test_winner_poller_prelim`

- [ ] **Step 6: Regression**

Run: `python scripts\test_winner_poller.py`
Expected: ผ่าน (formal pass เดิมไม่ regress)

- [ ] **Step 7: Commit**

```bash
git add scripts/Sebastian_Winner_Poller.py scripts/test_winner_poller_prelim.py
git commit -m "feat(poller): stage machine D0→PRELIM→W0 (prelim pass Round1 + formal pass รวม PRELIM)"
```

---

### Task 9: Wire — sender route + poller resolve_prelim live

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (followed_prelim branch + followed_winner ใช้ detailed)
- Modify: `scripts/Sebastian_Winner_Poller.py` (`main` ส่ง resolve_prelim จริง + prelim closed-loop)

- [ ] **Step 1: Sender — route followed_prelim + detailed winner**

In `scripts/Sebastian_LINE_Sender.py` ก่อนบล็อก `if item.get("source_stage") == "followed_winner":` (~line 525) เพิ่ม:

```python
    if item.get("source_stage") == "followed_prelim":
        import prelim_summary as _ps
        import cgd_intel as _ci
        pid = item["project_id"]
        budget = item.get("budget") or 0
        pr = _ps.fetch_prelim_summary(pid)
        cmp = _ci.compare_prediction_provisional(pid, pr.get("lowest_price")) if pr.get("has_price") else None
        pname = _clean_project_name(item.get("project_name") or "") or pid
        text = format_prelim_notification(pname, budget, pr, cmp, pid)
        success, error_type, error_msg = send_line_push(token, item["line_user_id"], text, quick_reply=None)
        store.mark_delivery_result(queue_id=item["id"], customer_id=item["customer_id"],
                                   project_id=pid, status="sent" if success else "failed",
                                   error_type=error_type, error_message=error_msg, worker_id=item["worker_id"])
        return
```

(ปรับ args `mark_delivery_result` ให้ตรง signature เดิมในไฟล์ — ดูบล็อก followed_winner เป็นแบบอย่าง)

In the `followed_winner` block, เปลี่ยนจาก `_winner_card_from_results` (flex) → ใช้ `format_winner_detailed` (text). ดึง analysis:

```python
        # Round 2 detailed
        import cgd_intel as _ci
        from Sebastian_Customer_DB import prediction_accuracy_summary, get_connection
        results = store.get_bid_results(item["project_id"])
        win = next((b for b in results if b.get("is_winner")), None)
        winner_name = (win or {}).get("bidder_name", "?")
        price_agree = (win or {}).get("price_agree") or (win or {}).get("price_proposal") or 0
        budget = item.get("budget") or 0
        pname = _clean_project_name(item.get("project_name") or "") or item["project_id"]
        with get_connection() as _c:
            ctx = _ci.intel_context(item.get("province",""), item.get("project_name",""), item.get("dept_name",""),
                                    item["project_id"], budget, _c)
            tokens = _ci.match_keywords(item.get("project_name",""))
            loc = _ci.resolve_location(item["project_id"], item.get("project_name",""), item.get("dept_name",""),
                                       item.get("province",""), _c)
            warned = _round2_warned_names(_c, item.get("province",""), tokens, loc)   # top-3 ที่เตือน
            analyzed = _ci.analyze_bidders(_c, item.get("province",""), tokens, loc["tambon"], loc["amphoe"],
                                           budget, results, warned)
            market_disc = _round2_market_disc(ctx)
        cmp = _ci.compare_prediction(item["project_id"], float(price_agree) if price_agree else 0)
        acc = prediction_accuracy_summary()
        text = format_winner_detailed(pname, winner_name, price_agree, budget, analyzed, cmp, acc, market_disc, item["project_id"])
        success, error_type, error_msg = send_line_push(token, item["line_user_id"], text, quick_reply=None)
        store.mark_delivery_result(queue_id=item["id"], customer_id=item["customer_id"],
                                   project_id=item["project_id"], status="sent" if success else "failed",
                                   error_type=error_type, error_message=error_msg, worker_id=item["worker_id"])
        return
```

เพิ่ม helper (ใกล้ฟังก์ชัน format):

```python
def _round2_warned_names(conn, province, tokens, loc) -> list:
    """ชื่อ top-3 คู่แข่งที่เตือนตอน D0 (= top3 ของ scope block ตำบล/อำเภอ/จังหวัด)."""
    import cgd_intel as _ci
    try:
        rows, _scope, _lv = _ci.select_competitors(province, tokens, loc.get("tambon",""), loc.get("amphoe"), conn)
        from collections import Counter
        return [w for w, _ in Counter(r["winner"] for r in rows if r.get("winner")).most_common(_ci.SHOW_N)]
    except Exception:
        return []


def _round2_market_disc(ctx):
    """ส่วนลดตลาด (median p50 ของ scope ตำบล) จาก prediction. None ถ้าไม่มี."""
    if not ctx or not ctx.get("prediction"):
        return None
    p = ctx["prediction"]
    lo, hi = p.get("area_disc_lo"), p.get("area_disc_hi")
    return round((lo + hi) / 2, 1) if lo is not None and hi is not None else None
```

> ตรวจ signature `mark_delivery_result` + `send_line_push` ในไฟล์จริงก่อน — ปรับ args ให้ตรง (อ้างบล็อก followed_winner เดิมเป็น template).

- [ ] **Step 2: Poller main — resolve_prelim จริง**

In `scripts/Sebastian_Winner_Poller.py` `main()`, เพิ่มก่อนเรียก `poll_winners`:

```python
    def resolve_prelim(pid):
        from prelim_summary import fetch_prelim_summary
        return fetch_prelim_summary(pid)
```

และเพิ่ม arg: `poll_winners(store, get_procure_result, log=log, sleep_sec=POLL_SLEEP_SEC, verify_hook=verify_hook, resolve_prelim=resolve_prelim)`

- [ ] **Step 3: Sanity — import + route ไม่พัง**

Run: `python -c "import os,sys,tempfile; os.environ['BMS_DATA_DIR']=tempfile.mkdtemp(); sys.path.insert(0,'scripts'); import Sebastian_LINE_Sender, Sebastian_Winner_Poller, prelim_summary; print('import OK')"`
Expected: `import OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/Sebastian_Winner_Poller.py
git commit -m "feat(wire): followed_prelim→Round1, followed_winner→detailed + poller resolve_prelim live"
```

---

### Task 10: Local sanity + deploy + e2e + docs

**Files:** none (verification) + progress/memory

- [ ] **Step 1: รัน test ทั้งชุด**

```bash
python scripts\test_save_prediction_upsert.py
python scripts\test_compare_upper_bound.py
python scripts\test_prelim_summary.py
python scripts\test_round2_analysis.py
python scripts\test_format_prelim.py
python scripts\test_format_winner_detailed.py
python scripts\test_winner_poller_prelim.py
```
แล้ว regression (ตั้ง `BMS_DATA_DIR`):
```bash
$env:BMS_DATA_DIR=(New-Item -ItemType Directory -Path "$env:TEMP\bmst$(Get-Random)").FullName
python scripts\test_cgd_intel.py; python scripts\test_price_prediction.py; python scripts\test_winner_poller.py; python scripts\test_followed_jobs.py
```
Expected: ทุกตัว OK/PASS

- [ ] **Step 2: ขอ confirm push (GATE)**

ถามกัญจน์: "push + deploy ราคา 2 รอบ ขึ้น VPS ได้ไหม" — รอ OK

- [ ] **Step 3: Push + VPS pull**

```bash
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main 2>&1 | tail -4"
```

- [ ] **Step 4: ปรับ cadence timer 6h→2h**

```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "grep -i OnCalendar /etc/systemd/system/bms-winner-poller.timer"
```
ดู interval เดิม → แก้เป็นทุก 2 ชม. (`OnCalendar=*-*-* 00/2:15:00` หรือ `OnUnitActiveSec=2h` ตามรูปแบบเดิม) → `sudo systemctl daemon-reload && sudo systemctl restart bms-winner-poller.timer && systemctl list-timers bms-winner-poller.timer --no-pager | head -3`

- [ ] **Step 5: e2e — รัน poller จริง 1 รอบ (งาน 69059075454 ติดตามอยู่)**

```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "set -a; . /opt/bms/app/.env; set +a; cd /opt/bms/app && BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python scripts/Sebastian_Winner_Poller.py 2>&1 | tail -8"
```
Expected: เห็น `📊→ prelim ENQUEUED 69059075454` (Round 1) → แล้ว LINE sender (timer) ส่งให้กัญจน์. ตรวจ:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c \"import sys; sys.path.insert(0,'/opt/bms/app/scripts'); from Sebastian_Customer_DB import get_connection; c=get_connection(); print([dict(r) for r in c.execute(\\\"SELECT source_stage,status FROM notification_queue WHERE project_id='69059075454' AND source_stage='followed_prelim'\\\")])\""
```
ยืนยัน Round 1 ถึงกัญจน์จริงในแอป LINE (ราคาต่ำสุด 740,000 + เทียบกรอบบน)

- [ ] **Step 6: progress_log + memory + Discord**

- progress_log: `## งานที่ N+112: แจ้ง W0 2 รอบ + วิเคราะห์ละเอียด LIVE`
- memory: อัปเดต `project_event_centric_queue` (stage D0→PRELIM→W0) + `reference_egp_prelim_summary_api` (LIVE). MEMORY.md
- Discord: "✅ แจ้ง W0 2 รอบ LIVE — Round1 สรุปราคาเบื้องต้น (closed-loop เบื้องต้น) + Round2 วิเคราะห์ละเอียด (breakdown ต่อราย)"

```bash
git add progress_log.md
git commit -m "docs(progress): N+112 — แจ้ง W0 2 รอบ + วิเคราะห์ละเอียด LIVE"
```

---

## Self-Review

**Spec coverage:**
- prelim fetch (API chain) → Task 3+4 ✅
- stage machine D0→PRELIM→W0 → Task 8 ✅
- Round 1 (ราคาต่ำสุด + closed-loop provisional + 2-ซอง) → Task 6 ✅
- Round 2 (breakdown ต่อราย + ป้าย🔸เจ้าประจำหลุด top3 + ประวัติ in/out tambon + ranking + ส่วนลด vs ตลาด + ความแม่นสะสม) → Task 5+7 ✅
- closed-loop เทียบกรอบบน + save_prediction upsert → Task 1+2 ✅
- cadence 2h → Task 10 ✅
- edge cases (2-ซอง, formal ก่อน prelim, parse fail) → Task 3/4/6/8 ✅

**Placeholder scan:** ไม่มี TBD. โค้ดครบทุก step. `_round2_warned_names`/`_round2_market_disc` นิยามใน Task 9. หมายเหตุ "ปรับ args ให้ตรง signature" = ต้องตรวจไฟล์จริง (mark_delivery_result/send_line_push) — มีคำสั่งให้ตรวจ ไม่ใช่ placeholder code.

**Type consistency:** `compare_prediction`/`compare_prediction_provisional` คืน `{held, error_pct, upper, area_price_lo, area_price_hi, actual}` ใช้ตรงกันใน Task 2/6/7. `analyze_bidders` คืน list[{name, price, discount, is_winner, hist{scope,n,median}, trend, tag}] ตรงกับ Task 5 test + Task 7 format. `fetch_prelim_summary` คืน {has_summary, has_price, lowest_price, num_bidders, revealed_at} ตรงกับ Task 4/8/9. `format_prelim_notification(project_name, budget, prelim, cmp, project_id)` + `format_winner_detailed(project_name, winner, price_agree, budget, analyzed, cmp, acc, market_disc, project_id)` ตรงทุกที่เรียก.

**ความเสี่ยงที่ engineer ต้องระวัง (ไม่ใช่ placeholder):** Task 9 wiring แตะ delivery loop จริง — ต้องตรวจ `mark_delivery_result`/`send_line_push` signature ในไฟล์ก่อนแก้ (มี followed_winner เดิมเป็น template). Round 2 ต้องการ formal results ที่ยังไม่มีในงานทดสอบ → e2e Round 2 รอผลทางการจริง (Round 1 ทดสอบ e2e ได้เลย).
