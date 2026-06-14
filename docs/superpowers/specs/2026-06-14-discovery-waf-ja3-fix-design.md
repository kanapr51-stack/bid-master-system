# Discovery WAF/Turnstile durable fix — JA3 (curl_cffi) + retry/backoff

**วันที่:** 2026-06-14
**สถานะ:** design (รอ implementation plan)
**Scope:** แก้ `scripts/Sebastian_Province_Discovery.py` (HTTP layer) เท่านั้น
**เกี่ยวข้อง:** memory `project_discovery_nodata_waf_turnstile`, `project_incident_control_plane` (INC-001), `feedback_rss_test_method`

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
    text = (resp.text or "").lower()
    markers = ("just a moment", "cf-mitigated", "turnstile", "challenge-platform")
    if any(m in text for m in markers):
        return True
    if resp.status_code in (403, 503):
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

### 3.4 Logging / metric (condition #5)
ทุกครั้งที่เจอ challenge → log บรรทัด **tag คงที่ greppable** (วัด challenge/day ก่อน-หลัง deploy ได้):
```python
print(f"⚠️ CF_CHALLENGE attempt={attempt} path={path or '/'} page={params.get('page','-')}")
```
> เลือก `print` tag (ไม่ใช่ `logging` module) ให้เข้ากับ pattern เดิมของไฟล์ (print ล้วน, ไม่มี logging setup). journald เก็บ stdout → นับได้ด้วย:
> `journalctl -u 'bms-province-discovery*' --since today | grep -c CF_CHALLENGE`
> (ถ้ากัญจน์อยากได้ logging module จริงๆ ปรับได้ตอน plan)

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
    for attempt in range(MAX_CHALLENGE_RETRY + 1):
        try:
            r = cffi_requests.get(url, params=params, headers=hdrs,
                                  timeout=TIMEOUT, impersonate="chrome120")
            if "rate limit" in (r.text or "").lower():
                raise RateLimited()
            if _is_challenge(r):
                print(f"⚠️ CF_CHALLENGE attempt={attempt} path={path or '/'} page={params.get('page','-')}")
                if attempt < MAX_CHALLENGE_RETRY:
                    time.sleep(CHALLENGE_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1))
                    continue
                return None     # ยอมแพ้หลัง retry → no_data path เดิม
            if not r.ok:
                return None
            return r.json()
        except RateLimited:
            raise
        except Exception:
            return None
    return None
```

---

## 4. Error handling — พึ่ง circuit breaker เดิม (reuse, ไม่แตะ)
- **transient** challenge → retry/backoff ใน `_get` กลืน
- **persistent** challenge → `_get` คืน None → `fetch_page` คืน `[]` → `consec_empty` breaker เดิมใน `fetch_all_d0` (MAX_CONSEC_EMPTY) → raise `RateLimited` → abort → partial/no_data (graceful, ไม่ balloon)
- worst case = degrade แบบเดิมทุกอย่าง (no_data heartbeat → alert tier-1 ที่ accurate แล้ว)

---

## 5. Dependency (condition #4 — pin version)
- `requirements.txt` ปัจจุบัน: `curl_cffi>=0.15` (**ไม่ pin = เสี่ยง drift**; `impersonate="chrome120"` behavior อาจเปลี่ยนข้าม major version)
- local verified = `0.15.0`
- **Action (pre-impl, ใน plan):**
  1. ยืนยัน version บน VPS: `ssh -i ~/.ssh/bms_vps root@45.76.156.166 '/opt/bms/venv/bin/pip show curl_cffi'`
  2. pin `requirements.txt` เป็น `==<version ที่ VPS รันจริง>` (น่าจะ `==0.15.0`) — RSS+discovery ใช้ venv เดียวกัน → discovery จะได้ behavior เดียวกับ RSS ที่พิสูจน์แล้ว

---

## 6. Testing
- **unit `_is_challenge`:** sample 4 แบบ — (a) JSON ปกติ → False, (b) 200 + body "just a moment" → True (body>status), (c) 403 body ว่าง → True, (d) plain "rate limit exceeded" → จัดการโดย RateLimited ไม่ใช่ challenge
- **unit retry:** mock `cffi_requests.get` — challenge 2 ครั้งแล้ว success → คืน JSON (attempt 3); challenge ตลอด → คืน None หลัง MAX_CHALLENGE_RETRY; นับ sleep ถูกเรียกตามจำนวน
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

## 8. Out of scope / followup
- full-sweep catch-up cooldown (lines 113-129 ใน catchup) — secondary, ทำถ้า spam
- ADR-003 residential IP — defer จนมีหลักฐาน (§7.5)
