"""
Sebastian_RSS_Scraper.py — Discovery-mode RSS scraper + incremental catalog growth
(ไม่ติด Cloudflare → ทดแทน/เสริม process5 scraper)

Two functions every run:
  1) Poll known active depts (catalog) → harvest D0 active_bidding items
  2) Probe N random unknown deptIds → grow catalog incrementally (ไม่ทำให้โดน 429)

Mode 1: discovery (default)
  - Poll known + probe unknown
  - Compare projectIds กับ seen_ids.json + all_jobs
  - Output report (new vs known, missed-by-process5)

Mode 2: queue (--queue)
  - เพิ่มเติม: เขียน new projectIds ลง data/rss_queue.json
    → refresh_active_jobs.py สามารถ pickup เพื่อ fetch detail

Output:
  - data/rss_run_<timestamp>.json — รายงาน + raw items
  - data/rss_seen_ids.json         — projectIds ที่ RSS เคยเห็น (cumulative)
  - data/rss_queue.json            — pending lookup queue (mode queue)
  - data/egp_deptid_catalog.json   — auto-updated เมื่อ probe เจอ new dept
"""
import os
import re
import sys
import json
import time
import random
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from curl_cffi import requests as cffi_requests

from Sebastian_Telemetry import check_breaker, record_poll

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

RSS_URL = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"
TARGET_FILE = DATA_DIR / "target_deptids.json"
RSS_SEEN_FILE = DATA_DIR / "rss_seen_ids.json"
RSS_QUEUE_FILE = DATA_DIR / "rss_queue.json"
SCRAPER_SEEN_FILE = DATA_DIR / "seen_ids.json"
DEPT_FAIL_STATE_FILE = DATA_DIR / "dept_failure_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}

# Poll all known depts in parallel
# 2026-05-20: 4 → 8 workers — server เริ่มช้า ทำให้ poll 2111 depts ใช้ 10+ นาที
# ครึ่งหนึ่งของ workflow timeout (25 min) → ต้องเพิ่ม parallelism
POLL_WORKERS = 8
POLL_TIMEOUT = 8   # connect + read timeout — fail-fast เมื่อ server stuck
# Probe sample size per run (incremental discovery)
PROBE_SAMPLE_SIZE = 100
PROBE_WORKERS = 1
DEPT_ID_RANGE = (1, 9999)
# Negative cache: skip depts confirmed empty within this many days
NEGATIVE_CACHE_DAYS = 3

# Blacklist: skip depts ที่ timeout/error N ครั้งติด (full_poll เท่านั้น)
BLACKLIST_THRESHOLD     = 5



_LOG_FILE = None


def _init_log_file():
    """เปิดไฟล์ log + redirect stdout/stderr (เฉพาะตอนรันบน local cron — ไม่ใช่ CI)
    Fallback chain (resilient to missing env after PC sleep):
      1. env BMS_RSS_LOG_DIR
      2. project_root/logs/rss (default)
      3. stderr only (if all fails)

    Skip redirect ใน CI (GitHub Actions etc.) เพื่อให้ console log แสดงสด
    — debug ง่ายขึ้นมาก
    """
    if os.environ.get("CI", "").lower() in ("true", "1"):
        return  # CI/GHA — keep stdout/stderr on console
    global _LOG_FILE
    log_dir = os.environ.get("BMS_RSS_LOG_DIR", "").strip()
    if not log_dir:
        # Self-recovery: derive from script location (works after PC sleep)
        log_dir = str(Path(__file__).parent.parent / "logs" / "rss")
    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _LOG_FILE = open(log_path / f"rss_{ts}.log", "w", encoding="utf-8", buffering=1)
        sys.stdout = _LOG_FILE
        sys.stderr = _LOG_FILE
    except Exception:
        # ถ้าเปิด log file ไม่ได้ → fallback ใช้ stderr (จะ show ตอน schtasks /Run interactive)
        pass


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def decode_thai(raw: bytes) -> str:
    # "windows-874" is unknown on Linux — use cp874 (same codec) instead
    for enc in ["tis-620", "cp874", "utf-8"]:
        try:
            text = raw.decode(enc)
            if any("฀" <= c <= "๿" for c in text):
                return text
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_items(xml_text: str) -> list[dict]:
    items = []
    for item_xml in re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL):
        item = {}
        for tag in ["title", "description", "link", "pubDate"]:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", item_xml, re.DOTALL)
            if m:
                item[tag] = m.group(1).strip()
        if "description" in item:
            # Pre-TOR (P0) projectIds prefixed "P" e.g., P69050012229
            # Other stages use plain digits e.g., 69049437914
            pid_match = re.search(r"(P?\d{11,12})", item["description"])
            item["projectId"] = pid_match.group(1) if pid_match else None
        items.append(item)
    return items


# ================================================================
# Stage codes (discovered 2026-05-18 — see docs/rss_full_coverage_discovery.md)
# ================================================================
# Param: anounceType (typo! รัฐบาลพิมพ์ขาด 'n')
STAGE_CODES = {
    "P0": "pre_tor",         # แผนการจัดซื้อจัดจ้าง
    "B0": "tor_review",      # ร่างเอกสารประกวดราคา
    "D0": "active_bidding",  # ประกาศเชิญชวน
    "D1": "cancelled",       # ยกเลิกประกาศเชิญชวน
    "W0": "awarded",         # ประกาศผู้ชนะ
}


def _classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "timed out" in msg or "timeout" in msg:
        return "timeout"
    if "tls" in msg or "ssl" in msg or "certificate" in msg:
        return "tls_error"
    if "connection" in msg:
        return "connection_error"
    return "unknown_error"


def fetch_dept(dept_id: str, anounce_type: str | None = None,
               timeout: int | None = None, retries: int = 2,
               record_telemetry: bool = False) -> tuple[int, list[dict]]:
    """Return (http_status, items). Retries on timeout with backoff.
    anounce_type: P0/B0/D0/W0/D1 (None = D0 default behavior)
    timeout: override POLL_TIMEOUT (ใช้ PROBE_ALL_TIMEOUT สำหรับ bulk probe)
    record_telemetry: True สำหรับ global poll — บันทึก circuit breaker + poll_log
    Note: param name is 'anounceType' (typo by government)
    """
    params: dict[str, str] = {}
    if dept_id:  # global poll: dept_id='' → no deptId param
        params["deptId"] = dept_id
    if anounce_type:
        params["anounceType"] = anounce_type
    _timeout = timeout if timeout is not None else POLL_TIMEOUT

    for attempt in range(retries + 1):
        t_start = time.time()
        try:
            # curl_cffi เลียนแบบ Chrome 120 TLS fingerprint
            # — process.gprocurement.go.th block python-requests' JA3 fingerprint via TLS hang
            # GHA IPs blocked by server (consistent 0 bytes) → RSS ต้องรันจาก local cron
            r = cffi_requests.get(
                RSS_URL, params=params, headers=HEADERS,
                timeout=_timeout, impersonate="chrome120",
            )
            response_time_ms = (time.time() - t_start) * 1000
            if r.status_code != 200:
                if record_telemetry:
                    record_poll(
                        endpoint=RSS_URL, dept_id=dept_id or "",
                        anounce_type=anounce_type or "D0",
                        success=False, http_status=r.status_code,
                        response_time_ms=response_time_ms, ttfb_ms=response_time_ms,
                        bytes_received=0, items_count=0,
                        failure_reason=f"http_{r.status_code}",
                    )
                return r.status_code, []
            text = decode_thai(r.content)
            items = parse_items(text)
            stage_tag = STAGE_CODES.get(anounce_type or "D0", "active_bidding")
            for it in items:
                it["deptId"] = dept_id
                it["anounceType"] = anounce_type or "D0"
                it["stage"] = stage_tag
            if record_telemetry:
                record_poll(
                    endpoint=RSS_URL, dept_id=dept_id or "",
                    anounce_type=anounce_type or "D0",
                    success=True, http_status=200,
                    response_time_ms=response_time_ms, ttfb_ms=response_time_ms,
                    bytes_received=len(r.content), items_count=len(items),
                )
            return 200, items
        except Exception as e:
            response_time_ms = (time.time() - t_start) * 1000
            is_timeout = "timed out" in str(e).lower() or "timeout" in str(e).lower()
            if attempt < retries and is_timeout:
                time.sleep(1 + attempt)  # 1s, 2s backoff
                continue
            log(f"  ⚠️ {dept_id} ({anounce_type or 'D0'}): {e}")
            if record_telemetry:
                record_poll(
                    endpoint=RSS_URL, dept_id=dept_id or "",
                    anounce_type=anounce_type or "D0",
                    success=False, http_status=-1,
                    response_time_ms=response_time_ms, ttfb_ms=None,
                    bytes_received=0, items_count=0,
                    failure_reason=_classify_error(e),
                )
            return -1, []
    return -1, []




# ================================================================
# Catalog management
# ================================================================

def load_catalog() -> dict:
    if not CATALOG_FILE.exists():
        return {}
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_catalog(catalog: dict):
    CATALOG_FILE.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_target_depts(catalog: dict, active_only: bool = True,
                      use_negative_cache: bool = False) -> list[str]:
    """Pick which depts to poll.

    active_only=True  → only depts with item_count > 0 (rotate mode)
    active_only=False + use_negative_cache=True → full_poll แต่ข้าม depts ที่
        scan ไปแล้วว่าว่าง ภายใน NEGATIVE_CACHE_DAYS วัน
        (active depts + never-scanned + stale-empty เท่านั้น)
    """
    if TARGET_FILE.exists():
        try:
            data = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return sorted(set(str(x) for x in data))
            if isinstance(data, dict) and data:
                return sorted(data.keys())
        except json.JSONDecodeError:
            pass

    if active_only:
        return sorted(
            d for d, v in catalog.items()
            if isinstance(v, dict) and v.get("item_count", 0) > 0
        )

    if use_negative_cache:
        from datetime import timezone
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - __import__('datetime').timedelta(days=NEGATIVE_CACHE_DAYS)
        result = []
        for d, v in catalog.items():
            if not isinstance(v, dict):
                result.append(d)
                continue
            if v.get("item_count", 0) > 0:
                result.append(d)  # active — always re-check
                continue
            scanned = v.get("scanned_at")
            if not scanned:
                result.append(d)  # never scanned — include
                continue
            try:
                scanned_dt = datetime.fromisoformat(scanned)
                if scanned_dt < cutoff:
                    result.append(d)  # stale cache — re-check
            except ValueError:
                result.append(d)
        return sorted(result)

    return sorted(catalog.keys())


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(str(x) for x in data)
    except json.JSONDecodeError:
        pass
    return set()


def save_seen(path: Path, seen: set[str]):
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def queue_for_lookup(items_to_queue: list[dict]):
    """items_to_queue: list of dicts ที่มี projectId, title, deptId, pubDate"""
    queue: list[dict] = []
    if RSS_QUEUE_FILE.exists():
        try:
            queue = json.loads(RSS_QUEUE_FILE.read_text(encoding="utf-8"))
            if not isinstance(queue, list):
                queue = []
        except json.JSONDecodeError:
            queue = []
    existing_ids = {q.get("projectId") for q in queue}
    now = datetime.now().isoformat(timespec="seconds")
    added = 0
    for item in items_to_queue:
        pid = item.get("projectId")
        if not pid or pid in existing_ids:
            continue
        # P-prefix = แผนการจัดซื้อ (Pre-TOR) — ไม่มี eGP detail page → ข้ามไม่ใส่ queue
        if str(pid).upper().startswith("P"):
            continue
        queue.append({
            "projectId": pid,
            "title": item.get("title", ""),
            "deptId": item.get("deptId", ""),
            "pubDate": item.get("pubDate", ""),
            "link": item.get("link", ""),
            "queued_at": now,
            "source": "rss",
            # anounceType (camelCase) จาก fetch_dept → เก็บเป็น anounce_type (snake_case)
            # ให้ refresh_active_jobs.py ใช้ p0 fallback ได้
            "anounce_type": item.get("anounceType", ""),
        })
        added += 1
    RSS_QUEUE_FILE.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"📥 Queue: {len(queue)} items pending (added {added} new)")


# ================================================================
# Incremental probe (catalog growth)
# ================================================================

PROBE_ALL_WORKERS    = 20  # concurrent workers สำหรับ --probe-all
PROBE_ALL_TIMEOUT    = 5   # seconds — full_poll แค่เช็คมี/ไม่มี, 9942 inactive จะ timeout ทิ้ง
PROBE_ALL_SAVE_EVERY = 500 # save catalog ทุก N depts กัน crash

PROBE_429_WORKERS    = 8   # ลดลงมากเพื่อหลีกเลี่ยง rate limit
PROBE_429_TIMEOUT    = 5   # timeout นานขึ้นเพื่อรองรับ server ช้า
PROBE_429_DELAY      = 0.3 # seconds หน่วงระหว่าง submit tasks
PROBE_429_SAVE_EVERY = 200

TARGET_KEYWORDS = ["นครพนม", "บึงกาฬ", "บ้านแพง", "บึงโขงหลง",
                   "ศรีสงคราม", "นาแก", "ท่าอุเทน", "ธาตุพนม"]
TARGET_FILE = DATA_DIR / "target_deptids.json"


def pick_probe_candidates(catalog: dict, n: int) -> list[str]:
    """เลือก deptId ที่ยังไม่มีใน catalog (random sample)"""
    known = set(catalog.keys())
    pool = [
        f"{i:04d}" for i in range(DEPT_ID_RANGE[0], DEPT_ID_RANGE[1] + 1)
        if f"{i:04d}" not in known
    ]
    if not pool:
        return []
    return random.sample(pool, min(n, len(pool)))


W0_CATALOG_FILE = DATA_DIR / "egp_w0_catalog.json"


def probe_all_depts(catalog: dict, anounce_type: str = "D0",
                    force_all: bool = False, save_all_w0: bool = False) -> dict:
    """
    Probe dept IDs 0001-9999 ด้วย cffi_requests

    Args:
        anounce_type: "D0" (active bidding) หรือ "W0" (award — ดูย้อนหลัง)
        force_all: True = probe ทุก ID แม้อยู่ใน catalog แล้ว (ใช้กับ W0)
        save_all_w0: True = บันทึก ALL depts ที่มี items ลง egp_w0_catalog.json
                     (ไม่กรอง keyword) เพื่อ post-process ทีหลัง

    Returns: {"found": int, "target_area": list[str], "total_probed": int}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    known = set(catalog.keys())
    if force_all:
        candidates = sorted(f"{i:04d}" for i in range(DEPT_ID_RANGE[0], DEPT_ID_RANGE[1] + 1))
    else:
        candidates = sorted(
            f"{i:04d}" for i in range(DEPT_ID_RANGE[0], DEPT_ID_RANGE[1] + 1)
            if f"{i:04d}" not in known
        )
    total = len(candidates)
    if not total:
        log("✅ probe-all: catalog ครบแล้ว (ไม่มี ID ที่ยังไม่ได้ probe)")
        return {"found": 0, "target_area": [], "total_probed": 0}

    log(f"🔍 probe-all [{anounce_type}]: {total} dept IDs (workers={PROBE_ALL_WORKERS})"
        + (" [save_all_w0]" if save_all_w0 else ""))
    t0 = time.time()
    found_active = 0
    target_depts: list[str] = []
    w0_catalog: dict[str, dict] = {}  # deptId → {item_count, projectIds[]}
    done = 0

    def _probe_one(dept_id: str):
        status, items = fetch_dept(dept_id, anounce_type, timeout=PROBE_ALL_TIMEOUT)
        return dept_id, status, items

    with ThreadPoolExecutor(max_workers=PROBE_ALL_WORKERS) as ex:
        futs = {ex.submit(_probe_one, did): did for did in candidates}
        for fut in as_completed(futs):
            dept_id, status, items = fut.result()
            done += 1

            if status == 200:
                if items:
                    found_active += 1
                    if save_all_w0:
                        # เก็บทุก dept ที่มี items ไม่กรอง keyword
                        w0_catalog[dept_id] = {
                            "item_count": len(items),
                            "projectIds": [it.get("projectId") for it in items
                                           if it.get("projectId")][:10],
                            "scanned_at": datetime.now().isoformat(timespec="seconds"),
                        }
                        log(f"  📦 {dept_id}: {len(items)} items · {items[0].get('title','')[:50]}")
                    else:
                        title_blob = " ".join(it.get("title", "") for it in items)
                        is_target = any(kw in title_blob for kw in TARGET_KEYWORDS)
                        if is_target:
                            target_depts.append(dept_id)
                            log(f"  🎯 TARGET {dept_id}: {items[0].get('title','')[:70]}")
                        else:
                            log(f"  📦 {dept_id}: {len(items)} items · {items[0].get('title','')[:50]}")

                # อัปเดต catalog เฉพาะ D0 probe
                if not force_all:
                    entry = {
                        "item_count": len(items),
                        "projectIds": [it.get("projectId") for it in items if it.get("projectId")][:15],
                        "titles":    [it.get("title", "")[:120] for it in items[:5]],
                        "pubDates":  [it.get("pubDate", "") for it in items[:3]],
                        "scanned_at": datetime.now().isoformat(timespec="seconds"),
                        "note": "probe_all",
                    }
                    catalog[dept_id] = entry
            else:
                # timeout/error → mark as scanned (empty) เฉพาะ D0 probe
                if not force_all:
                    catalog[dept_id] = {
                        "item_count": 0, "projectIds": [], "titles": [],
                        "scanned_at": datetime.now().isoformat(timespec="seconds"),
                        "note": f"probe_all_err_{status}",
                    }

            # save progress ทุก N entries กัน crash (เฉพาะ D0 probe)
            if not force_all and done % PROBE_ALL_SAVE_EVERY == 0:
                save_catalog(catalog)
                elapsed = time.time() - t0
                log(f"  ↳ progress {done}/{total} ({elapsed:.0f}s) active={found_active}")

    if save_all_w0:
        W0_CATALOG_FILE.write_text(
            json.dumps(w0_catalog, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"💾 egp_w0_catalog.json: {len(w0_catalog)} depts saved")
    elif not force_all:
        save_catalog(catalog)

    elapsed = time.time() - t0
    log(f"\n✅ probe-all [{anounce_type}] เสร็จ: {done}/{total} probed, {found_active} active, "
        f"{len(target_depts)} target-area depts ({elapsed:.0f}s)")

    # อัปเดต target_deptids.json ถ้าเจอ target area depts (keyword mode เท่านั้น)
    if target_depts and not save_all_w0:
        existing: list[str] = []
        if TARGET_FILE.exists():
            try:
                existing = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        merged = sorted(set(existing) | set(target_depts))
        TARGET_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"🎯 target_deptids.json: {len(merged)} depts saved")

    return {"found": found_active, "target_area": target_depts, "total_probed": done}


def probe_429_depts(catalog: dict) -> dict:
    """Re-probe deptIds ที่เคยโดน 429 (rate limit) ด้วย workers น้อยลง + delay
    Returns: {"found": int, "total_probed": int}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    candidates = sorted(
        d for d, v in catalog.items()
        if "err_429" in str(v.get("note", ""))
    )
    total = len(candidates)
    if not total:
        log("✅ probe-429: ไม่มี dept ที่โดน 429")
        return {"found": 0, "total_probed": 0}

    log(f"🔄 probe-429: {total} depts (workers={PROBE_429_WORKERS}, delay={PROBE_429_DELAY}s)")
    t0 = time.time()
    found_active = 0
    done = 0

    def _probe_one(dept_id: str):
        status, items = fetch_dept(dept_id, "D0", timeout=PROBE_429_TIMEOUT)
        return dept_id, status, items

    with ThreadPoolExecutor(max_workers=PROBE_429_WORKERS) as ex:
        futs = {}
        for did in candidates:
            futs[ex.submit(_probe_one, did)] = did
            time.sleep(PROBE_429_DELAY)  # หน่วงก่อน submit task ถัดไป

        for fut in as_completed(futs):
            dept_id, status, items = fut.result()
            done += 1

            if status == 200:
                entry = {
                    "item_count": len(items),
                    "projectIds": [it.get("projectId") for it in items if it.get("projectId")][:15],
                    "titles":    [it.get("title", "")[:120] for it in items[:5]],
                    "pubDates":  [it.get("pubDate", "") for it in items[:3]],
                    "scanned_at": datetime.now().isoformat(timespec="seconds"),
                    "note": "probe_429_retry",
                }
                catalog[dept_id] = entry
                if items:
                    found_active += 1
                    log(f"  ✅ {dept_id}: {len(items)} items · {items[0].get('title','')[:60]}")
            elif status == 429:
                catalog[dept_id]["note"] = "probe_429_still_limited"
                log(f"  ⚠️ {dept_id}: ยังโดน 429")
            else:
                catalog[dept_id] = {
                    "item_count": 0, "projectIds": [], "titles": [],
                    "scanned_at": datetime.now().isoformat(timespec="seconds"),
                    "note": f"probe_429_retry_err_{status}",
                }

            if done % PROBE_429_SAVE_EVERY == 0:
                save_catalog(catalog)
                elapsed = time.time() - t0
                log(f"  ↳ {done}/{total} ({elapsed:.0f}s) active={found_active}")

    save_catalog(catalog)
    elapsed = time.time() - t0
    log(f"\n✅ probe-429 เสร็จ: {done}/{total} probed, {found_active} newly active ({elapsed:.0f}s)")
    return {"found": found_active, "total_probed": done}


def probe_unknown_depts(catalog: dict) -> int:
    """Probe N unknown deptIds via cffi_requests. Mutate catalog in place. Return new dept count."""
    candidates = pick_probe_candidates(catalog, PROBE_SAMPLE_SIZE)
    if not candidates:
        return 0
    new_found = 0
    with ThreadPoolExecutor(max_workers=PROBE_ALL_WORKERS) as ex:
        futs = {ex.submit(fetch_dept, d, "D0", PROBE_ALL_TIMEOUT): d for d in candidates}
        for fut in as_completed(futs):
            dept_id = futs[fut]
            status, items = fut.result()
            if status == 200:
                catalog[dept_id] = {
                    "item_count": len(items),
                    "projectIds": [
                        it.get("projectId") for it in items if it.get("projectId")
                    ][:15],
                    "titles": [it.get("title", "")[:120] for it in items[:5]],
                    "pubDates": [it.get("pubDate", "") for it in items[:3]],
                    "scanned_at": datetime.now().isoformat(timespec="seconds"),
                    "note": "incremental_probe",
                }
                if items:
                    new_found += 1
                    log(f"  🔍 probe {dept_id}: {len(items)} items · {items[0].get('title', '')[:50]}")
    return new_found


# ================================================================
# Dept failure tracking — blacklist depts ที่ timeout/error ติดกัน
# ================================================================

def load_dept_fail_state() -> dict:
    """{dept_id: {"consec_fails": N, "last_status": int, "last_attempt": iso}}"""
    if not DEPT_FAIL_STATE_FILE.exists():
        return {}
    try:
        return json.loads(DEPT_FAIL_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_dept_fail_state(state: dict) -> None:
    DEPT_FAIL_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_blacklisted_depts(state: dict) -> set[str]:
    return {d for d, s in state.items()
            if isinstance(s, dict) and s.get("consec_fails", 0) >= BLACKLIST_THRESHOLD}


# ================================================================
# Main
# ================================================================

def run(queue_new: bool = False, skip_probe: bool = False,
        anounce_type: str | None = None, full_poll: bool = False) -> dict:
    """anounce_type: P0/B0/D0/W0/D1 (None = D0 default).
    full_poll: poll ALL depts (default False = active-only, 50x faster).
    Multi-stage support discovered 2026-05-18.
    """
    catalog = load_catalog()
    targets = load_target_depts(catalog, active_only=not full_poll,
                                use_negative_cache=full_poll)

    if not targets:
        log("⚠️ ไม่มี target depts — initialize catalog with seed data")
        return {"error": "no_targets"}

    stage_label = STAGE_CODES.get(anounce_type or "D0", "active_bidding")
    log(f"=== RSS Discovery Run · stage={anounce_type or 'D0'} ({stage_label}) ===")
    log(f"Catalog: {len(catalog)} depts known · Target: {len(targets)}")

    # Blacklist: skip depts ที่ fail >= threshold ใน full_poll mode
    fail_state = load_dept_fail_state()
    blacklisted = get_blacklisted_depts(fail_state)
    if full_poll and blacklisted:
        before = len(targets)
        targets = [d for d in targets if d not in blacklisted]
        log(f"Blacklist: skipped {before - len(targets)} depts (consec_fails ≥ {BLACKLIST_THRESHOLD})")

    # Pass 1: Poll target depts via direct cffi_requests (no browser — RSS is plain XML)
    all_items: list[dict] = []
    poll_started = time.time()
    poll_errors = 0

    # full_poll (9999 depts): more workers, short timeout, NO retry — move on ทันที
    # rotate (57 active depts): fewer workers, longer timeout, retry 2x
    _workers = PROBE_ALL_WORKERS if full_poll else POLL_WORKERS
    _timeout = PROBE_ALL_TIMEOUT if full_poll else POLL_TIMEOUT
    _retries = 0 if full_poll else 2
    _done = 0
    now_iso = datetime.now().isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=_workers) as ex:
        futs = {ex.submit(fetch_dept, d, anounce_type, _timeout, _retries): d for d in targets}
        for fut in as_completed(futs):
            dept_id = futs[fut]
            status, items = fut.result()
            _done += 1
            if status != 200:
                poll_errors += 1
                if full_poll:
                    st = fail_state.setdefault(dept_id, {"consec_fails": 0})
                    st["consec_fails"] = int(st.get("consec_fails", 0)) + 1
                    st["last_status"]  = status
                    st["last_attempt"] = now_iso
                continue
            # success → reset fail count
            if full_poll and dept_id in fail_state:
                fail_state[dept_id]["consec_fails"] = 0
                fail_state[dept_id]["last_status"]  = 200
                fail_state[dept_id]["last_attempt"] = now_iso
            if items:
                all_items.extend(items)
                catalog[dept_id] = {
                    "item_count": len(items),
                    "projectIds": [
                        it.get("projectId") for it in items if it.get("projectId")
                    ][:15],
                    "titles": [it.get("title", "")[:120] for it in items[:5]],
                    "pubDates": [it.get("pubDate", "") for it in items[:3]],
                    "scanned_at": datetime.now().isoformat(timespec="seconds"),
                }
            if full_poll and _done % 1000 == 0:
                log(f"  ↳ {_done}/{len(targets)} polled · items={len(all_items)}")

    poll_elapsed = time.time() - poll_started
    log(f"Polled {len(targets)} depts in {poll_elapsed:.1f}s · {len(all_items)} items · {poll_errors} errors")

    # Save updated fail state + log new blacklist additions
    if full_poll:
        new_bl = get_blacklisted_depts(fail_state) - blacklisted
        if new_bl:
            log(f"  ⛔ {len(new_bl)} new depts blacklisted (consec_fails ≥ {BLACKLIST_THRESHOLD})")
        save_dept_fail_state(fail_state)

    # Pass 2: Probe unknowns (catalog growth)
    new_depts = 0
    if not skip_probe:
        new_depts = probe_unknown_depts(catalog)
        log(f"Probe: {new_depts} new active depts discovered")

    save_catalog(catalog)

    # Compute deltas
    rss_seen = load_seen(RSS_SEEN_FILE)
    scraper_seen = load_seen(SCRAPER_SEEN_FILE)

    all_pids = {it["projectId"] for it in all_items if it.get("projectId")}
    new_to_rss = all_pids - rss_seen
    missed_by_scraper = all_pids - scraper_seen

    rss_seen.update(all_pids)
    save_seen(RSS_SEEN_FILE, rss_seen)

    # Group by dept
    by_dept: dict[str, int] = {}
    for it in all_items:
        if it.get("projectId"):
            by_dept[it["deptId"]] = by_dept.get(it["deptId"], 0) + 1

    if queue_new and new_to_rss:
        # Build queue items with full context (title, deptId, pubDate)
        items_for_queue = [
            it for it in all_items
            if it.get("projectId") and it["projectId"] in new_to_rss
        ]
        queue_for_lookup(items_for_queue)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_file = DATA_DIR / f"rss_run_{ts}.json"
    run_data = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "poll_elapsed_sec": round(poll_elapsed, 1),
        "depts_polled": len(targets),
        "poll_errors": poll_errors,
        "total_items": len(all_items),
        "unique_project_ids": len(all_pids),
        "new_to_rss_count": len(new_to_rss),
        "missed_by_process5_count": len(missed_by_scraper),
        "scraper_seen_size": len(scraper_seen),
        "rss_seen_size": len(rss_seen),
        "probe_new_depts": new_depts,
        "catalog_size": len(catalog),
        "by_dept_counts": dict(sorted(by_dept.items(), key=lambda kv: -kv[1])),
        "new_project_ids_sample": sorted(new_to_rss)[:30],
        "missed_by_process5_sample": sorted(missed_by_scraper)[:30],
    }
    run_file.write_text(
        json.dumps(run_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log("")
    log("=== Summary ===")
    log(f"  Polled: {len(targets)} depts · {poll_elapsed:.1f}s")
    log(f"  Items: {len(all_items)} · Unique pids: {len(all_pids)}")
    log(f"  New to RSS (ครั้งแรก): {len(new_to_rss)}")
    log(f"  Missed by process5 scraper: {len(missed_by_scraper)} ⭐")
    log(f"  Catalog grew: +{new_depts} new active depts · total {len(catalog)}")
    log(f"  Report: {run_file}")

    return run_data


def poll_global_rss(anounce_types: list[str] | None = None,
                    queue_new: bool = False) -> dict:
    """Poll global RSS (no deptId) สำหรับ anounceTypes ที่ระบุ.

    ครอบคลุม dept ใหม่ที่ถูก negative-cache skip อยู่ —
    ทุก dept ที่ post วันนี้จะปรากฏในfeed นี้อัตโนมัติ.

    Returns: {"total_items": int, "new_to_rss": int, "types_polled": list, "breaker": str}
    """
    if anounce_types is None:
        anounce_types = ["D0", "P0", "W0"]

    # ── Circuit breaker check ──────────────────────────────────────────────
    breaker = check_breaker(RSS_URL)
    if breaker == "OPEN":
        log(f"⛔ Circuit breaker OPEN — skip global RSS poll (cooldown active)")
        return {"total_items": 0, "new_to_rss": 0, "types_polled": [], "breaker": "OPEN"}
    if breaker == "HALF_OPEN":
        log(f"🟡 Circuit breaker HALF_OPEN — probe 1 type then decide")
        anounce_types = anounce_types[:1]   # probe แค่ type เดียว
    # ──────────────────────────────────────────────────────────────────────

    rss_seen = load_seen(RSS_SEEN_FILE)
    all_items: list[dict] = []
    types_ok: list[str] = []

    for atype in anounce_types:
        status, items = fetch_dept("", anounce_type=atype, timeout=12, retries=1,
                                   record_telemetry=True)
        if status == 200 and items:
            for it in items:
                it["deptId"] = ""
                it["anounceType"] = atype
                it["stage"] = STAGE_CODES.get(atype, "active_bidding")
            all_items.extend(items)
            types_ok.append(atype)
            log(f"  🌐 global {atype}: {len(items)} items")
        else:
            log(f"  ⚠️ global {atype}: status={status} (skip)")
        time.sleep(1)

    all_pids = {it["projectId"] for it in all_items if it.get("projectId")}
    new_to_rss = all_pids - rss_seen
    rss_seen.update(all_pids)
    save_seen(RSS_SEEN_FILE, rss_seen)

    if queue_new and new_to_rss:
        items_for_queue = [
            it for it in all_items
            if it.get("projectId") and it["projectId"] in new_to_rss
        ]
        queue_for_lookup(items_for_queue)

    final_breaker = check_breaker(RSS_URL)
    log(f"🌐 Global RSS: {len(all_items)} items · {len(new_to_rss)} new · breaker={final_breaker}")
    return {
        "total_items": len(all_items),
        "new_to_rss": len(new_to_rss),
        "types_polled": types_ok,
        "breaker": final_breaker,
    }


STAGE_ROTATION = list(STAGE_CODES.keys())  # ['P0', 'B0', 'D0', 'D1', 'W0']
ROTATION_STATE_FILE = DATA_DIR / "rss_stage_rotation.json"


def get_next_stage() -> str:
    """Read state file → rotate to next stage. Persist updated state.
    Cycle: D0 → P0 → B0 → W0 → D1 → D0 ... (D0 first since most important)
    """
    rotation = ["D0", "P0", "B0", "W0", "D1"]
    state = {"index": 0, "last_run": ""}
    if ROTATION_STATE_FILE.exists():
        try:
            state = json.loads(ROTATION_STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    idx = state.get("index", 0) % len(rotation)
    stage = rotation[idx]
    state["index"] = (idx + 1) % len(rotation)
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state["last_stage"] = stage
    ROTATION_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stage


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sebastian RSS Scraper (discovery)")
    parser.add_argument(
        "--queue", action="store_true",
        help="เขียน new projectIds ลง rss_queue.json",
    )
    parser.add_argument(
        "--no-probe", action="store_true",
        help="ข้าม probe unknown depts (เร็วขึ้น แต่ catalog ไม่โต)",
    )
    parser.add_argument(
        "--stage",
        choices=list(STAGE_CODES.keys()) + ["all", "rotate"],
        default="rotate",
        help="anounceType: P0/B0/D0/W0/D1 หรือ all (sequential), rotate (1 stage per run จาก state file)",
    )
    parser.add_argument(
        "--full-poll", action="store_true",
        help="Poll ALL depts in catalog (default: active-only, 50x faster). "
             "Use this 1-2x per day for periodic re-check of empty depts.",
    )
    parser.add_argument(
        "--probe-all", action="store_true",
        help="Probe ALL unchecked dept IDs 0001-9999 ด้วย 20 workers (cffi, ไม่ใช้ Playwright) "
             "→ ขยาย catalog ให้ครบในครั้งเดียว (~1-2 นาที). "
             "รัน workflow_dispatch จาก GHA หรือ manual เท่านั้น",
    )
    parser.add_argument(
        "--probe-w1", action="store_true",
        help="Probe ทุก dept ID 0001-9999 ด้วย anounceType=W0 (ประกาศผู้ชนะ) "
             "→ หา target-area depts จากข้อมูลย้อนหลัง แม้ตอนนี้ไม่มี active bid "
             "→ save ลง target_deptids.json. "
             "รัน workflow_dispatch จาก GHA หรือ manual เท่านั้น",
    )
    parser.add_argument(
        "--probe-429", action="store_true",
        help="Re-probe deptIds ที่เคยโดน 429 rate limit ด้วย workers น้อยลง + delay "
             "→ อัปเดต catalog ให้ครบ. รัน GHA mode=d0_repair",
    )
    parser.add_argument(
        "--probe-w0-full", action="store_true",
        help="Probe ทุก dept ID 0001-9999 ด้วย W0 → บันทึก egp_w0_catalog.json "
             "(ทุก dept ที่มี items, ไม่กรอง keyword) เพื่อ post-process "
             "→ map deptSubName → จังหวัด ทีหลัง. "
             "รัน workflow_dispatch จาก GHA หรือ manual เท่านั้น",
    )
    parser.add_argument(
        "--global", dest="global_poll", action="store_true",
        help="Poll global RSS (ไม่ระบุ deptId) สำหรับ D0+P0+W0 "
             "→ ครอบคลุม dept ใหม่ที่ถูก negative-cache skip "
             "→ ดีสำหรับ real-time monitoring ทุก dept ในประเทศไทย",
    )
    args = parser.parse_args()
    _init_log_file()

    # ── global mode: poll global RSS (no deptId) สำหรับ real-time monitoring ──
    if args.global_poll:
        log("=" * 60)
        log("GLOBAL RSS MODE: poll ไม่ระบุ deptId → ครอบคลุมทุก dept อัตโนมัติ")
        log("=" * 60)
        result = poll_global_rss(anounce_types=["D0", "P0", "W0"], queue_new=args.queue)
        log(f"\nสรุป: items={result['total_items']}, new={result['new_to_rss']}, "
            f"types={result['types_polled']}")
        sys.exit(0)

    # ── probe-all mode (ทำก่อน แล้วออก — ไม่รัน normal pipeline) ──
    if args.probe_all:
        log("=" * 60)
        log("PROBE-ALL MODE: ขยาย catalog 0001-9999 ด้วย cffi_requests")
        log("=" * 60)
        catalog = load_catalog()
        result = probe_all_depts(catalog)
        log(f"\nสรุป: found={result['found']}, target_area={result['target_area']}, "
            f"probed={result['total_probed']}")
        sys.exit(0)

    # ── probe-429 mode: re-probe depts ที่โดน rate limit ──
    if args.probe_429:
        log("=" * 60)
        log("PROBE-429 MODE: re-probe depts ที่โดน 429 ด้วย workers น้อยลง")
        log("=" * 60)
        catalog = load_catalog()
        result = probe_429_depts(catalog)
        log(f"\nสรุป: found={result['found']}, probed={result['total_probed']}")
        sys.exit(0)

    # ── probe-w1 mode: หา target-area depts จาก W0 ย้อนหลัง (keyword filter) ──
    if args.probe_w1:
        log("=" * 60)
        log("PROBE-W0 MODE: หา target-area depts จาก anounceType=W0 (ประกาศผู้ชนะ ย้อนหลัง)")
        log("=" * 60)
        catalog = load_catalog()
        result = probe_all_depts(catalog, anounce_type="W0", force_all=True)
        log(f"\nสรุป W0: found={result['found']}, target_area={result['target_area']}, "
            f"probed={result['total_probed']}")
        sys.exit(0)

    # ── probe-w0-full mode: เก็บ ALL depts ที่มี W0 items → post-process ทีหลัง ──
    if args.probe_w0_full:
        log("=" * 60)
        log("PROBE-W0-FULL MODE: เก็บ egp_w0_catalog.json ทุก dept (ไม่กรอง keyword)")
        log("  → ใช้ build_target_deptids.py ทีหลังเพื่อ map deptSubName → จังหวัด")
        log("=" * 60)
        catalog = load_catalog()
        result = probe_all_depts(catalog, anounce_type="W0", force_all=True, save_all_w0=True)
        log(f"\nสรุป W0-full: found={result['found']}, probed={result['total_probed']}")
        log(f"  → egp_w0_catalog.json พร้อมให้ build_target_deptids.py ประมวลผล")
        sys.exit(0)

    if args.stage == "all":
        # Sequential through all stages
        any_error = False
        for code in STAGE_CODES.keys():
            log(f"\n┌─── STAGE {code} ({STAGE_CODES[code]}) ───")
            result = run(queue_new=args.queue, skip_probe=True,
                         anounce_type=code, full_poll=args.full_poll)
            if result.get("error"):
                any_error = True
        sys.exit(1 if any_error else 0)
    elif args.stage == "rotate":
        # Cron-friendly: pick next stage from rotation state
        next_stage = get_next_stage()
        log(f"\n🔄 ROTATE → stage={next_stage}")
        # probe ทุก rotate รอบ (catalog growth) — ยกเว้นถ้าสั่ง --no-probe
        result = run(queue_new=args.queue, skip_probe=args.no_probe,
                     anounce_type=next_stage, full_poll=args.full_poll)

        sys.exit(0 if not result.get("error") else 1)
    else:
        result = run(queue_new=args.queue, skip_probe=args.no_probe,
                     anounce_type=args.stage, full_poll=args.full_poll)
        sys.exit(0 if not result.get("error") else 1)
