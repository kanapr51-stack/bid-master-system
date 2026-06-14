# Discovery WAF/Turnstile durable fix — JA3 (curl_cffi) + retry/backoff

**วันที่:** 2026-06-14
**สถานะ:** design (รอ implementation plan)
**Scope:** แก้ `scripts/Sebastian_Province_Discovery.py` (HTTP layer) เท่านั้น
**เกี่ยวข้อง:** memory `project_discovery_nodata_waf_turnstile`, `project_incident_control_plane` (INC-001), `feedback_rss_test_method`

---

## 0. Precondition (BLOCKER — ต้องทำก่อนเริ่ม implementation)

> **Implementation MUST NOT begin until VPS curl_cffi version is verified and pinned.**

เหตุผล: spec อิงกับ behavior ของ RSS ที่พิสูจน์แล้ว. ถ้า RSS=0.15.0 แต่ discovery รันคนละ version → `impersonate="chrome120"` behavior อาจต่าง → spec พังทันที.

ขั้นตอน:
1. `ssh -i ~/.ssh/bms_vps root@45.76.156.166 '/opt/bms/venv/bin/pip show curl_cffi'`
2. pin `requirements.txt`: `curl_cffi>=0.15` → `curl_cffi==<version ที่ VPS รันจริง>` (คาด `==0.15.0`)
3. ยืนยัน RSS + discovery ใช้ venv เดียวกัน (`/opt/bms/venv`)

(รายละเอียด §5)

---

## 1. ปัญหา & Root cause (ยืนยันด้วยหลักฐาน)

Discovery บน VPS โดน Cloudflare Turnstile challenge เป็นพักๆ → `validateCfTurnTile` reject ทั้งที่ token สด (full-nkp log: `🔑 token OK เหลือ 1507s` → `❌ validateCfTurnTile` ทันที).

**Root cause = JA3/TLS fingerprint:** `_get()` ใช้ `requests.get` ธรรมดา → TLS fingerprint เป็นของ Python → Cloudflare ของ `process5.gprocurement.go.th` จับว่าเป็น bot.

**หลักฐานในโค้ดเราเอง:** `Sebastian_RSS_Scraper.py:188-191` เจอปัญหาเดียวกันบนโดเมนเดียวกัน แก้ด้วย `cffi_requests.get(..., impersonate="chrome120")` แล้ว และ **RSS รันบน VPS ได้ปกติ** → พิสูจน์ว่าแก้ JA3 พอ ไม่ต้องย้าย IP (ADR-003).

Tier-1 (commit `e7b9712`, deployed) แก้แล้วเฉพาะ **alert accuracy + catch-up anti-spam** — ยังไม่แก้ต้นตอ. spec นี้ = ต้นตอ.

---

## 2. เป้าหมาย & Non-goals

**เป้าหมาย:** challenge/day ลดลงเข้าใกล้ศูนย์ โดยไม่แตะ architecture. ได้ **หลักฐานเชิงประจักษ์** ว่า JA3 เป็น root cause จริง (ผ่าน metric ก่อน/หลัง) เพื่อ defer ADR-003 อย่างมั่นใจ (YAGNI / observe before optimize).

**Non-goals (ยืนยันไม่ทำ):**
- ❌ ADR-003 residential IP routing — ยังไม่มีหลักฐานว่า IP จำเป็น
- ❌ แตะ `health_deadman.py` / `discovery_catchup.py` — เพิ่ง stabilize (tier 1)
- ❌ เปลี่ยน circuit breaker เดิมใน `fetch_all_d0` — known-good behavior, reuse

---

## 3. Design

### 3.1 เปลี่ยน HTTP layer (แก้ JA3 — เหตุหลัก)
- `_get()`: `requests.get` → `cffi_requests.get(..., impersonate="chrome120")` (string เดียวกับ RSS ที่พิสูจน์แล้ว)
- **ตัด `User-Agent` manual ออกจาก HEADERS ที่ส่ง** — ปล่อย `impersonate` ตั้ง UA ให้ตรงกับ TLS fingerprint (UA ไม่ตรง JA3 = ธงเตือนเอง). คงไว้: `X-Announcement-Token`, `Referer`, `Accept`, `Content-Type`
- เพิ่ม comment กัน dev รุ่นหลัง:
  ```python
  # Safe to retry because discovery requests are idempotent GETs.
  ```

### 3.2 `_is_challenge()` — body marker ก่อน status (condition #1)
**สำคัญ:** Cloudflare บางทีส่ง `200 OK` แต่ body เป็น `<html>Just a moment...` → **อย่า rely status code อย่างเดียว**. ตรวจ body ก่อน:
```python
def _is_challenge(resp) -> bool:
    # priority: body marker > status (CF ส่ง 200 OK + "Just a moment" ได้)
    text = (resp.text or "").lower()
    markers = ("just a moment", "cf-mitigated", "turnstile", "challenge-platform")
    if any(m in text for m in markers):
        return True
    # content-type เสริม: block status + ไม่ใช่ JSON = ไม่ใช่ error ปกติของ API → ถือเป็น challenge
    # (กัน false positive: 403 ที่เป็น JSON error จริงจะไม่ retry เปล่า)
    ctype = resp.headers.get("content-type", "").lower()
    if resp.status_code in (403, 503) and "application/json" not in ctype:
        return True
    return False
```
ลำดับใน `_get`: rate-limit text (เดิม) → `_is_challenge` → `not r.ok` → `r.json()`

### 3.3 retry/backoff (กันเหนียว challenge ที่หลุดมา)
- `MAX_CHALLENGE_RETRY = 3` (1 initial + 3 retries)
- backoff + **random jitter จริง** (condition #3 — กัน thundering herd ถ้ามีหลาย worker):
  ```python
  delay = CHALLENGE_BACKOFF_BASE * (2 ** attempt)   # 2, 4, 8
  delay += random.uniform(0, 1)
  ```
  `CHALLENGE_BACKOFF_BASE = 2`
- ครบ retry แล้วยัง challenge → `return None` → เข้า path `no_data` เดิม (graceful)
- **แยกจาก `RateLimited`** (rate limit = plain text เดิม ไม่แตะ logic)
- retry ปลอดภัยเพราะ GET idempotent (condition #2, ยืนยันแล้ว: discovery ไม่มี POST, ทุก call ผ่าน `_get`)

### 3.4 Logging / metric (condition #5 + Comment 4)
**tag คงที่ greppable 2 ตัว** ให้เห็นภาพ challenge vs recovered vs persistent:
```python
# เจอ challenge (ทุกครั้ง)
print(f"⚠️ CF_CHALLENGE attempt={attempt} path={path or '/'} page={params.get('page','-')}")
# challenge → retry → สำเร็จ (เห็นว่า retry ได้ผล)
print(f"✅ CF_RECOVERED attempt={attempt} path={path or '/'} page={params.get('page','-')}")
```
นับได้:
```
challenge = journalctl -u 'bms-province-discovery*' --since today | grep -c CF_CHALLENGE
recovered = ... | grep -c CF_RECOVERED
persistent = challenge - recovered   # = ที่ retry ไม่ผ่าน → no_data
```
ตัวอย่างที่อยากเห็นหลัง deploy: `challenge=30 recovered=29 persistent=1` (เดิมก่อน curl_cffi อาจ ~47/วัน)
> เลือก `print` tag (ไม่ใช่ `logging` module) ให้เข้ากับ pattern เดิมของไฟล์ (print ล้วน, ไม่มี logging setup). journald เก็บ stdout. (ถ้ากัญจน์อยากได้ logging module จริงๆ ปรับได้ตอน plan)

### 3.5 โครง `_get` ใหม่ (pseudo)
```python
from curl_cffi import requests as cffi_requests
import random

MAX_CHALLENGE_RETRY = 3
CHALLENGE_BACKOFF_BASE = 2

def _get(token, params, path=""):
    # Safe to retry because discovery requests are idempotent GETs.
    url = API + path
    hdrs = {**HEADERS, "X-Announcement-Token": token}   # HEADERS = ไม่มี UA แล้ว
    challenged = False   # เคยเจอ challenge ใน call นี้ไหม → ใช้ log CF_RECOVERED
    pg = params.get("page", "-")
    for attempt in range(MAX_CHALLENGE_RETRY + 1):
        try:
            r = cffi_requests.get(url, params=params, headers=hdrs,
                                  timeout=TIMEOUT, impersonate="chrome120")
        except RateLimited:
            raise
        except cffi_requests.RequestsError:   # network/transport error → graceful None
            return None
        except Exception as e:                # bug จริง (อย่ากลืนเงียบ — ต้องเห็น)
            print(f"❌ _get unexpected error (path={path or '/'} page={pg}): {e}")
            return None

        # rate limit = plain text เดิม — แยกจาก challenge, ไม่แตะ
        if "rate limit" in (r.text or "").lower():
            raise RateLimited()

        if _is_challenge(r):
            challenged = True
            print(f"⚠️ CF_CHALLENGE attempt={attempt} path={path or '/'} page={pg}")
            if attempt < MAX_CHALLENGE_RETRY:
                time.sleep(CHALLENGE_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1))
                continue
            return None     # persistent — ยอมแพ้หลัง retry → no_data path เดิม

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
> **exception policy (Comment 1):** `RateLimited` → propagate; network error (`RequestsError`) → graceful None; unexpected/bug + JSON decode → **print แล้วค่อย None** (ไม่กลืนเงียบ — bug ต้องเห็นใน journald). ชื่อ exception class ของ curl_cffi (`RequestsError`) ต้อง verify กับ version ที่ pin ตอน plan

---

## 4. Error handling — พึ่ง circuit breaker เดิม (reuse, ไม่แตะ)
- **transient** challenge → retry/backoff ใน `_get` กลืน
- **persistent** challenge → `_get` คืน None → `fetch_page` คืน `[]` → `consec_empty` breaker เดิมใน `fetch_all_d0` (MAX_CONSEC_EMPTY) → raise `RateLimited` → abort → partial/no_data (graceful, ไม่ balloon)
- worst case = degrade แบบเดิมทุกอย่าง (no_data heartbeat → alert tier-1 ที่ accurate แล้ว)

---

## 5. Dependency (condition #4 — pin version)
- `requirements.txt` ปัจจุบัน: `curl_cffi>=0.15` (**ไม่ pin = เสี่ยง drift**; `impersonate="chrome120"` behavior อาจเปลี่ยนข้าม major version)
- local verified = `0.15.0`
- **เป็น Precondition/BLOCKER → ดู §0** (ต้อง verify VPS + pin ก่อนเริ่ม)
- RSS + discovery ใช้ venv เดียวกัน (`/opt/bms/venv`) → pin = guarantee discovery ได้ behavior เดียวกับ RSS ที่พิสูจน์แล้ว

---

## 6. Testing
- **unit `_is_challenge`:** sample — (a) JSON ปกติ (200, application/json) → False, (b) 200 + body "just a moment" → True (body>status), (c) 403 + text/html → True, (d) 403 + application/json (error จริง) → False (content-type กัน false positive), (e) plain "rate limit exceeded" → จัดการโดย RateLimited ไม่ใช่ challenge
- **unit retry:** mock `cffi_requests.get` — challenge 2 ครั้งแล้ว success → คืน JSON + print CF_RECOVERED (attempt 2); challenge ตลอด → คืน None หลัง MAX_CHALLENGE_RETRY + print CF_CHALLENGE 4 ครั้ง; นับ `time.sleep`/`random.uniform` ถูกเรียกตามจำนวน
- **unit exception (Comment 1):** `RateLimited` → propagate (ไม่ถูกกลืน); `RequestsError` → None เงียบ; Exception อื่น/JSON decode → คืน None **+ print error** (assert ว่า print ถูกเรียก = ไม่กลืนเงียบ)
- **smoke:** รัน `Sebastian_Province_Discovery.py --dry-run` (มี token สด) → scan ผ่านด้วย curl_cffi, ไม่ regression
- **post-deploy metric:** เทียบ `grep -c CF_CHALLENGE` ก่อน/หลัง → ยืนยัน JA3 เป็น root cause

---

## 7. Rollout
1. pin curl_cffi (§5) + แก้ `_get`/`_is_challenge`/HEADERS
2. unit + smoke ผ่าน → commit (ไม่ push จนกว่ากัญจน์ confirm)
3. push → กัญจน์ deploy VPS (`cd /opt/bms/app && git pull && bash scripts/deploy.sh`)
4. ดู metric 1-2 วัน: challenge/day ใกล้ศูนย์ = สำเร็จ + เป็นหลักฐาน defer ADR-003
5. ถ้ายังเรื้อรังหลัง curl_cffi = ได้หลักฐานว่า IP เป็นปัญหา → ค่อยพิจารณา ADR-003

---

## 8. Rollback
**Trigger** (เงื่อนไขที่บอกว่าต้องถอย):
- `CF_CHALLENGE`/วัน เพิ่มเหนือ baseline ก่อนแก้ (= curl_cffi ทำให้แย่ลง)
- dry-run / scan regression หลัง deploy (discovery ได้ 0 หรือ error)
- RSS หรือ endpoint อื่นได้รับผลกระทบ (เช่น curl_cffi version ที่ pin ชน dependency อื่น)

**Action:** `git revert <commit>` → push → VPS `git pull && bash scripts/deploy.sh`

**Expected outcome:** discovery กลับไปใช้ `requests` เดิมทันที (behavior known-good)

**ทำไม revert ปลอดภัย:** scope แค่ไฟล์เดียว (`Sebastian_Province_Discovery.py`) + `requirements.txt` 1 บรรทัด · ไม่แตะ data/schema/migration · ไม่แตะ deadman/catchup · circuit breaker เดิมยังทำงาน

---

## 9. Out of scope / followup
- full-sweep catch-up cooldown (lines 113-129 ใน catchup) — secondary, ทำถ้า spam
- ADR-003 residential IP — defer จนมีหลักฐาน (§7 ข้อ 5)
