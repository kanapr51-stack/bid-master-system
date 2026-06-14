# Discovery WAF/JA3 Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ทำให้ Discovery บน VPS เลี่ยง Cloudflare Turnstile challenge ได้ถาวร โดยเปลี่ยน HTTP layer เป็น curl_cffi (เลียนแบบ JA3 ของ Chrome) + retry/backoff กันเหนียว

**Architecture:** จุด HTTP เดียว `_get()` ใน `Sebastian_Province_Discovery.py` — เปลี่ยน `requests.get` → `cffi_requests.get(impersonate="chrome120")`, เพิ่ม `_is_challenge()` ตรวจ Cloudflare challenge (body marker ก่อน status), retry แบบ exponential backoff + jitter, exception handling ที่ไม่กลืน bug, และ metric `CF_CHALLENGE`/`CF_RECOVERED`. ไม่แตะ catch-up/deadman/data. circuit breaker เดิมใน `fetch_all_d0` รับ persistent challenge

**Tech Stack:** Python, curl_cffi==0.15.0 (pin), eGP API. Test = plain `assert` + `__main__` runner (convention เดิม `scripts/test_*.py`, ไม่มี pytest)

**Spec:** `docs/superpowers/specs/2026-06-14-discovery-waf-ja3-fix-design.md`

---

## File Structure

- **Modify:** `scripts/Sebastian_Province_Discovery.py`
  - imports: ลบ `import requests`, เพิ่ม `from curl_cffi import requests as cffi_requests` + `import random`
  - HEADERS: ลบ `User-Agent` (+ ตัวแปร `UA`)
  - เพิ่ม constants `MAX_CHALLENGE_RETRY`, `CHALLENGE_BACKOFF_BASE`
  - เพิ่มฟังก์ชัน `_is_challenge(resp)`
  - rewrite `_get()`
- **Modify:** `requirements.txt:6` — pin `curl_cffi>=0.15` → `curl_cffi==<VPS version>`
- **Create:** `scripts/test_discovery_http.py` — unit tests (`_is_challenge` + `_get`)

---

## Task 0: Precondition — verify + pin curl_cffi (BLOCKER)

> spec §0: **ห้ามเริ่ม Task อื่นจน verify VPS version + pin เสร็จ**. เหตุ: spec อิง behavior RSS — version drift = พัง

**Files:**
- Modify: `requirements.txt:6`

- [ ] **Step 1: เช็ค curl_cffi version บน VPS** (กัญจน์รันผ่าน `!`)

Run:
```
ssh -i ~/.ssh/bms_vps root@45.76.156.166 '/opt/bms/venv/bin/pip show curl_cffi | grep -i version'
```
Expected: บรรทัด `Version: X.Y.Z` (คาด `0.15.0`). จดค่าไว้เป็น `<VPS_VER>`

- [ ] **Step 2: ยืนยัน RSS ใช้ venv เดียวกัน**

Run:
```
ssh -i ~/.ssh/bms_vps root@45.76.156.166 'head -3 /etc/systemd/system/bms-province-discovery.service 2>/dev/null; grep -i execstart /etc/systemd/system/bms-province-discovery.service'
```
Expected: `ExecStart=/opt/bms/venv/bin/python ...` (venv เดียวกับที่ pip show เช็ค) → ยืนยัน discovery จะใช้ curl_cffi version เดียวกับที่ pin

- [ ] **Step 3: pin requirements.txt**

แก้ `requirements.txt` บรรทัด 6 จาก:
```
curl_cffi>=0.15
```
เป็น (แทน `<VPS_VER>` ด้วยค่าจริงจาก Step 1):
```
curl_cffi==<VPS_VER>
```
> ถ้า `<VPS_VER>` = `0.15.0` → `curl_cffi==0.15.0` (ตรงกับ local ที่ verify code ในแผนนี้). ถ้าต่างจาก 0.15.0 → ต้องรัน unit test (Task 1-2) ซ้ำบน version นั้นก่อน push เพราะ `impersonate` behavior อาจต่าง

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): pin curl_cffi==<VPS_VER> (discovery JA3 fix precondition)"
```

---

## Task 1: `_is_challenge()` — ตรวจ Cloudflare challenge (body > status)

**Files:**
- Create: `scripts/test_discovery_http.py`
- Modify: `scripts/Sebastian_Province_Discovery.py` (เพิ่มฟังก์ชันก่อน `_get`, ~line 126)

- [ ] **Step 1: เขียน test ที่ fail** — สร้าง `scripts/test_discovery_http.py`

```python
"""test_discovery_http.py — _is_challenge + _get (curl_cffi + retry/backoff + metrics)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Province_Discovery as spd


class FakeResp:
    def __init__(self, status=200, text="{}", ctype="application/json",
                 json_data=None, json_raises=False):
        self.status_code = status
        self.text = text
        self.headers = {"content-type": ctype}
        self.ok = 200 <= status < 400
        self._json = json_data if json_data is not None else {}
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("not json")
        return self._json


def test_is_challenge():
    # (a) JSON ปกติ → False
    assert spd._is_challenge(FakeResp(200, '{"data":{}}', "application/json")) is False
    # (b) 200 OK แต่ body "Just a moment" → True (body > status)
    assert spd._is_challenge(FakeResp(200, "<html>Just a moment...</html>", "text/html")) is True
    # marker อื่น
    assert spd._is_challenge(FakeResp(200, "cf-mitigated", "text/html")) is True
    assert spd._is_challenge(FakeResp(403, "challenge-platform", "text/html")) is True
    # (c) 403 + text/html ไม่มี marker → True (status + ไม่ใช่ json)
    assert spd._is_challenge(FakeResp(403, "blocked", "text/html")) is True
    assert spd._is_challenge(FakeResp(503, "", "text/html")) is True
    # (d) 403 + application/json (error จริงของ API) → False (content-type กัน false positive)
    assert spd._is_challenge(FakeResp(403, '{"error":"x"}', "application/json")) is False
    print("✅ test_is_challenge")


if __name__ == "__main__":
    test_is_challenge()
    print("\n✅ ALL test_discovery_http PASS")
```

- [ ] **Step 2: รัน test ให้เห็น fail**

Run: `python scripts/test_discovery_http.py`
Expected: FAIL — `AttributeError: module 'Sebastian_Province_Discovery' has no attribute '_is_challenge'`

- [ ] **Step 3: เพิ่มฟังก์ชัน `_is_challenge`** ใน `scripts/Sebastian_Province_Discovery.py` — วางก่อน `def _get` (หลัง `class RateLimited`)

```python
def _is_challenge(resp) -> bool:
    """ตรวจ Cloudflare challenge — priority: body marker > status
    (CF ส่ง 200 OK + body 'Just a moment' ได้ → อย่า rely status อย่างเดียว)"""
    text = (resp.text or "").lower()
    markers = ("just a moment", "cf-mitigated", "turnstile", "challenge-platform")
    if any(m in text for m in markers):
        return True
    # content-type เสริม: block status + ไม่ใช่ JSON = ไม่ใช่ error ปกติของ API → challenge
    # (กัน false positive: 403 ที่เป็น JSON error จริงจะไม่ retry เปล่า)
    ctype = resp.headers.get("content-type", "").lower()
    if resp.status_code in (403, 503) and "application/json" not in ctype:
        return True
    return False
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `python scripts/test_discovery_http.py`
Expected: `✅ test_is_challenge` + `✅ ALL test_discovery_http PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_Province_Discovery.py scripts/test_discovery_http.py
git commit -m "feat(discovery): _is_challenge — detect Cloudflare challenge (body > status)"
```

---

## Task 2: rewrite `_get()` — curl_cffi + retry/backoff + exceptions + metrics

**Files:**
- Modify: `scripts/Sebastian_Province_Discovery.py` (imports ~line 26-43, `_get` ~line 127-141)
- Modify: `scripts/test_discovery_http.py` (เพิ่ม test)

- [ ] **Step 1: เขียน test ที่ fail** — เพิ่มใน `scripts/test_discovery_http.py` (ก่อน `if __name__`)

```python
class FakeRequestsError(Exception):
    pass


class FakeCffi:
    """แทน spd.cffi_requests — get() คืน item ถัดไปใน queue (response หรือ raise ถ้าเป็น Exception)"""
    RequestsError = FakeRequestsError

    def __init__(self, items):
        self._items = list(items)
        self.calls = 0

    def get(self, *a, **k):
        item = self._items[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _patch(items):
    """ติดตั้ง FakeCffi + no-op sleep/jitter, คืน (fake, restore_fn, printed_lines)"""
    fake = FakeCffi(items)
    orig = (spd.cffi_requests, spd.time.sleep, spd.random.uniform, spd.print)
    printed = []
    spd.cffi_requests = fake
    spd.time.sleep = lambda *a, **k: None
    spd.random.uniform = lambda a, b: 0.0

    def restore():
        spd.cffi_requests, spd.time.sleep, spd.random.uniform = orig[0], orig[1], orig[2]
    return fake, restore, printed


def test_get_success():
    fake, restore, _ = _patch([FakeResp(200, '{"data":1}', json_data={"data": 1})])
    try:
        assert spd._get("tok", {}) == {"data": 1}
        assert fake.calls == 1
    finally:
        restore()
    print("✅ test_get_success")


def test_get_recovered_after_challenge():
    # challenge 2 ครั้งแล้วสำเร็จ → คืน JSON ที่ attempt 2
    items = [FakeResp(200, "just a moment", "text/html"),
             FakeResp(403, "blocked", "text/html"),
             FakeResp(200, '{"ok":1}', json_data={"ok": 1})]
    fake, restore, _ = _patch(items)
    try:
        assert spd._get("tok", {"page": "3"}) == {"ok": 1}
        assert fake.calls == 3
    finally:
        restore()
    print("✅ test_get_recovered_after_challenge")


def test_get_persistent_challenge_returns_none():
    # challenge ตลอด → None หลัง MAX_CHALLENGE_RETRY (=3) → เรียก get 4 ครั้ง (1+3)
    items = [FakeResp(503, "just a moment", "text/html")] * (spd.MAX_CHALLENGE_RETRY + 1)
    fake, restore, _ = _patch(items)
    try:
        assert spd._get("tok", {}) is None
        assert fake.calls == spd.MAX_CHALLENGE_RETRY + 1
    finally:
        restore()
    print("✅ test_get_persistent_challenge_returns_none")


def test_get_ratelimit_propagates():
    fake, restore, _ = _patch([FakeResp(200, "Rate limit exceeded", "text/plain")])
    try:
        raised = False
        try:
            spd._get("tok", {})
        except spd.RateLimited:
            raised = True
        assert raised, "RateLimited ต้อง propagate ไม่ถูกกลืน"
    finally:
        restore()
    print("✅ test_get_ratelimit_propagates")


def test_get_network_error_returns_none():
    fake, restore, _ = _patch([FakeRequestsError("dns fail")])
    try:
        assert spd._get("tok", {}) is None
    finally:
        restore()
    print("✅ test_get_network_error_returns_none")


def test_get_json_error_logged_not_swallowed():
    # response ok แต่ json() พัง → คืน None + ต้อง print (ไม่กลืนเงียบ)
    fake, restore, _ = _patch([FakeResp(200, "weird", json_raises=True)])
    logs = []
    orig_print = spd.print
    spd.print = lambda *a, **k: logs.append(" ".join(str(x) for x in a))
    try:
        assert spd._get("tok", {}) is None
        assert any("JSON decode error" in m for m in logs), logs
    finally:
        spd.print = orig_print
        restore()
    print("✅ test_get_json_error_logged_not_swallowed")
```

อัปเดต `__main__` runner ให้เรียก test ใหม่:
```python
if __name__ == "__main__":
    test_is_challenge()
    test_get_success()
    test_get_recovered_after_challenge()
    test_get_persistent_challenge_returns_none()
    test_get_ratelimit_propagates()
    test_get_network_error_returns_none()
    test_get_json_error_logged_not_swallowed()
    print("\n✅ ALL test_discovery_http PASS")
```

- [ ] **Step 2: รัน test ให้เห็น fail**

Run: `python scripts/test_discovery_http.py`
Expected: FAIL — `AttributeError: ... has no attribute 'cffi_requests'` (หรือ `MAX_CHALLENGE_RETRY`) เพราะยังไม่แก้ `_get`/imports

- [ ] **Step 3: แก้ imports** ใน `scripts/Sebastian_Province_Discovery.py`

ลบบรรทัด `import requests` (line 32) แล้วเพิ่มแทนที่ด้วย:
```python
import random
from curl_cffi import requests as cffi_requests
```

- [ ] **Step 4: ลบ User-Agent ออกจาก HEADERS** (line ~37-43)

จาก:
```python
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}
```
เป็น (ตัด UA + User-Agent — ปล่อย impersonate="chrome120" ตั้ง UA ให้ตรง JA3):
```python
HEADERS = {
    # ไม่ตั้ง User-Agent เอง — curl_cffi impersonate="chrome120" ตั้งให้ตรงกับ TLS fingerprint
    # (UA ไม่ตรง JA3 = ธงเตือนเอง)
    "Referer": "https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}
```

- [ ] **Step 5: เพิ่ม constants** — วางใกล้ constants อื่นด้านบนไฟล์ (เช่นหลัง `HEADERS`)

```python
# Cloudflare challenge retry (spec 2026-06-14): transient challenge → retry; persistent → circuit breaker เดิม
MAX_CHALLENGE_RETRY = 3
CHALLENGE_BACKOFF_BASE = 2   # วินาที → 2, 4, 8 (+ jitter)
```

- [ ] **Step 6: rewrite `_get`** (แทนที่ทั้งฟังก์ชัน line ~127-141)

```python
def _get(token: str, params: dict, path: str = "") -> dict | None:
    # Safe to retry because discovery requests are idempotent GETs.
    url = API + path
    hdrs = {**HEADERS, "X-Announcement-Token": token}
    challenged = False   # เคยเจอ challenge ใน call นี้ไหม → log CF_RECOVERED ถ้าหลังจากนั้นสำเร็จ
    pg = params.get("page", "-")
    for attempt in range(MAX_CHALLENGE_RETRY + 1):
        try:
            r = cffi_requests.get(url, params=params, headers=hdrs,
                                  timeout=TIMEOUT, impersonate="chrome120")
        except RateLimited:
            raise
        except cffi_requests.RequestsError:   # network/transport error → graceful None
            return None
        except Exception as e:                # bug จริง — อย่ากลืนเงียบ ต้องเห็นใน journald
            print(f"❌ _get unexpected error (path={path or '/'} page={pg}): {e}")
            return None

        # rate limit = plain text เดิม — แยกจาก challenge, ไม่แตะ logic
        if "rate limit" in (r.text or "").lower():
            raise RateLimited()

        if _is_challenge(r):
            challenged = True
            print(f"⚠️ CF_CHALLENGE attempt={attempt} path={path or '/'} page={pg}")
            if attempt < MAX_CHALLENGE_RETRY:
                time.sleep(CHALLENGE_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1))
                continue
            return None     # persistent — ยอมแพ้หลัง retry → no_data path เดิม (circuit breaker เดิมรับต่อ)

        if not r.ok:
            return None
        if challenged:
            print(f"✅ CF_RECOVERED attempt={attempt} path={path or '/'} page={pg}")
        try:
            return r.json()
        except Exception as e:                # JSON decode ผิดปกติ (ไม่ใช่ challenge) — log ให้เห็น
            print(f"❌ _get JSON decode error (path={path or '/'} page={pg}): {e}")
            return None
    return None
```

- [ ] **Step 7: รัน test ให้ผ่านทั้งหมด**

Run: `python scripts/test_discovery_http.py`
Expected: ทุกบรรทัด `✅` + `✅ ALL test_discovery_http PASS`

- [ ] **Step 8: เช็ค `requests` ไม่ถูกอ้างที่อื่นแล้ว** (กัน NameError หลังลบ import)

Run: `grep -n "requests\." scripts/Sebastian_Province_Discovery.py`
Expected: เจอแต่ `cffi_requests.get(...)` — ไม่มี `requests.get`/`requests.xxx` เปล่าๆ. ถ้าเจอ `requests.` เปล่า ให้แก้เป็น `cffi_requests.`

- [ ] **Step 9: py_compile**

Run: `python -m py_compile scripts/Sebastian_Province_Discovery.py`
Expected: ไม่มี error

- [ ] **Step 10: Commit**

```bash
git add scripts/Sebastian_Province_Discovery.py scripts/test_discovery_http.py
git commit -m "feat(discovery): _get via curl_cffi impersonate + retry/backoff + metrics

แก้ JA3 root cause (requests → cffi_requests chrome120) + retry/jitter เมื่อเจอ Turnstile
+ exception ไม่กลืน bug + CF_CHALLENGE/CF_RECOVERED metric. spec 2026-06-14"
```

---

## Task 3: Smoke test (dry-run) + verify no regression

**Files:** ไม่มี (รันอย่างเดียว)

- [ ] **Step 1: dry-run discovery ด้วย token สด** (กัญจน์รัน — ต้องมี Chrome 9222 หรือ token)

Run (local, dry-run ไม่เขียน DB):
```
python scripts/Sebastian_Province_Discovery.py --provider chrome9222 --dry-run
```
หรือถ้าเทสบน VPS:
```
ssh -i ~/.ssh/bms_vps root@45.76.156.166 'cd /opt/bms/app && BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python scripts/Sebastian_Province_Discovery.py --worker --dry-run'
```
Expected: `🔑 token OK ...` → `📊 รวม N รายการ (...active...)` โดยไม่มี `❌ server reject` (= curl_cffi ผ่าน Cloudflare). ถ้าเห็น `⚠️ CF_CHALLENGE` ตามด้วย `✅ CF_RECOVERED` = retry ทำงาน. ถ้า scan ได้ปกติ = ไม่ regression

- [ ] **Step 2: ตรวจ metric tags ปรากฏใน output ถูก format**

Run: `python scripts/Sebastian_Province_Discovery.py --provider chrome9222 --dry-run 2>&1 | grep -E "CF_CHALLENGE|CF_RECOVERED|รวม.*รายการ"`
Expected: เห็นบรรทัด `📊 รวม ... รายการ` (และ CF_* ถ้ามี challenge) — ยืนยัน scan สำเร็จ

---

## Task 4: Push + deploy + post-deploy metric

> ตามกฎ: push เฉพาะเมื่อกัญจน์ confirm · deploy = กัญจน์รันบน VPS

- [ ] **Step 1: Push (รอ confirm)**

```bash
git push origin main
```

- [ ] **Step 2: Deploy VPS** (กัญจน์รัน)

```
ssh -i ~/.ssh/bms_vps root@45.76.156.166 'cd /opt/bms/app && git pull && /opt/bms/venv/bin/pip install -r requirements.txt && bash scripts/deploy.sh'
```
> `pip install -r requirements.txt` สำคัญ — ให้ curl_cffi ตรง pin (ถ้า VPS เคยมี version อื่น)
Expected: deploy สำเร็จ, services restart

- [ ] **Step 3: เก็บ baseline + วัดผล 1-2 วัน**

Run (เทียบจำนวน challenge ต่อวัน):
```
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "journalctl -u 'bms-province-discovery*' --since today | grep -c CF_CHALLENGE; journalctl -u 'bms-province-discovery*' --since today | grep -c CF_RECOVERED"
```
Expected: challenge ลดเข้าใกล้ศูนย์ (หรือ recovered ≈ challenge = retry กลืนหมด, persistent ~0). ยืนยัน heartbeat ไม่ no_data:
```
ssh -i ~/.ssh/bms_vps root@45.76.156.166 'cat /opt/bms/data/last_discovery_run.json'
```
Expected: `"status": "ok"`

- [ ] **Step 4: Discord สรุปผล** (ตาม CLAUDE.md — แก้ bug ใหญ่เสร็จ)

ส่งข้อความสรุป challenge/day ก่อน-หลัง + ยืนยัน root cause = JA3 → defer ADR-003

---

## Self-Review (เทียบ plan กับ spec)

- **§0 Precondition (pin)** → Task 0 ✅
- **§3.1 curl_cffi + ตัด UA** → Task 2 Step 3-4 ✅
- **§3.2 _is_challenge (body>status + content-type)** → Task 1 ✅
- **§3.3 retry/backoff + jitter** → Task 2 Step 6 ✅
- **§3.4 CF_CHALLENGE + CF_RECOVERED** → Task 2 Step 6 + test ✅
- **§3.5 exception policy (ไม่กลืน bug)** → Task 2 Step 6 + test_get_json_error/network_error ✅
- **§4 reuse circuit breaker** → ไม่แตะ `fetch_all_d0` (return None เข้า path เดิม) ✅
- **§5 dependency pin** → Task 0 ✅
- **§6 testing (5 _is_challenge + retry + exception)** → Task 1 + Task 2 tests ✅
- **§7 rollout** → Task 4 ✅
- **§8 rollback** → ไม่ใช่ task; เป็น runbook ถ้า trigger (git revert) — อยู่ใน spec แล้ว
- **§9 out of scope (full-sweep cooldown, ADR-003)** → ไม่อยู่ใน plan ✅ (ถูกต้อง)

ครบทุก spec requirement. ไม่มี placeholder. ชื่อ symbol สอดคล้อง (`_is_challenge`, `MAX_CHALLENGE_RETRY`, `CHALLENGE_BACKOFF_BASE`, `cffi_requests`, `RequestsError`)
