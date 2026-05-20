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

import asyncio
import requests
from curl_cffi import requests as cffi_requests
from playwright.async_api import async_playwright

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

# Playwright settings — ใช้เมื่อ curl_cffi โดน Cloudflare block (2026-05-20)
# Real Chrome browser ผ่าน Cloudflare ได้เสมอ
PW_CONCURRENCY = 4      # concurrent pages ต่อ browser
PW_TIMEOUT = 30_000     # ms — รอ Cloudflare JS challenge ผ่าน


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
    for enc in ["tis-620", "cp874", "windows-874", "utf-8"]:
        try:
            text = raw.decode(enc)
            if any("฀" <= c <= "๿" for c in text):
                return text
        except UnicodeDecodeError:
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


def fetch_dept(dept_id: str, anounce_type: str | None = None,
               timeout: int | None = None) -> tuple[int, list[dict]]:
    """Return (http_status, items)
    anounce_type: P0/B0/D0/W0/D1 (None = D0 default behavior)
    timeout: override POLL_TIMEOUT (ใช้ PROBE_ALL_TIMEOUT สำหรับ bulk probe)
    Note: param name is 'anounceType' (typo by government)
    """
    params: dict[str, str] = {"deptId": dept_id}
    if anounce_type:
        params["anounceType"] = anounce_type
    _timeout = timeout if timeout is not None else POLL_TIMEOUT
    try:
        # ใช้ curl_cffi เลียนแบบ Chrome 120 TLS fingerprint
        # — process.gprocurement.go.th block python-requests' JA3 fingerprint
        r = cffi_requests.get(
            RSS_URL, params=params, headers=HEADERS,
            timeout=_timeout, impersonate="chrome120",
        )
        if r.status_code != 200:
            return r.status_code, []
        text = decode_thai(r.content)
        items = parse_items(text)
        # Annotate stage in items
        stage_tag = STAGE_CODES.get(anounce_type or "D0", "active_bidding")
        for it in items:
            it["deptId"] = dept_id
            it["anounceType"] = anounce_type or "D0"
            it["stage"] = stage_tag
        return 200, items
    except Exception as e:
        log(f"  ⚠️ {dept_id} ({anounce_type or 'D0'}): {e}")
        return -1, []


# ================================================================
# Playwright batch fetch (ใช้เมื่อ curl_cffi โดน Cloudflare block)
# ================================================================

async def _pw_fetch_one(context, sem, dept_id, anounce_type):
    params = f"deptId={dept_id}"
    if anounce_type:
        params += f"&anounceType={anounce_type}"
    url = f"{RSS_URL}?{params}"
    async with sem:
        page = await context.new_page()
        try:
            resp = await page.goto(url, timeout=PW_TIMEOUT, wait_until="networkidle")
            if resp is None or resp.status != 200:
                return dept_id, resp.status if resp else -1, []
            body = await resp.body()
            text = decode_thai(body)
            items = parse_items(text)
            stage_tag = STAGE_CODES.get(anounce_type or "D0", "active_bidding")
            for it in items:
                it["deptId"] = dept_id
                it["anounceType"] = anounce_type or "D0"
                it["stage"] = stage_tag
            return dept_id, 200, items
        except Exception as e:
            log(f"  ⚠️ {dept_id} ({anounce_type or 'D0'}) PW: {type(e).__name__}: {str(e)[:80]}")
            return dept_id, -1, []
        finally:
            await page.close()


async def _fetch_all_pw_async(targets, anounce_type=None):
    sem = asyncio.Semaphore(PW_CONCURRENCY)
    results = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=HEADERS["User-Agent"],
            extra_http_headers={k: v for k, v in HEADERS.items() if k != "User-Agent"},
        )
        tasks = [_pw_fetch_one(context, sem, d, anounce_type) for d in targets]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        for item in done:
            if isinstance(item, Exception):
                continue
            dept_id, status, items = item
            results[dept_id] = (status, items)
        await browser.close()
    return results


def fetch_all_playwright(targets, anounce_type=None):
    """Sync wrapper — launch one Chrome browser, fetch all targets concurrently."""
    return asyncio.run(_fetch_all_pw_async(targets, anounce_type))


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


def load_target_depts(catalog: dict, active_only: bool = True) -> list[str]:
    """Pick which depts to poll.

    Args:
        catalog: full catalog dict
        active_only: if True (default), return only depts with item_count > 0.
            ~41 active vs ~2111 total → 50x faster poll. Probe still discovers new ones.

    Resolution order:
        1) target_deptids.json (curated, overrides active_only)
        2) catalog filtered by active_only
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
        queue.append({
            "projectId": pid,
            "title": item.get("title", ""),
            "deptId": item.get("deptId", ""),
            "pubDate": item.get("pubDate", ""),
            "link": item.get("link", ""),
            "queued_at": now,
            "source": "rss",
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
PROBE_ALL_TIMEOUT    = 3   # seconds — สั้นกว่า POLL_TIMEOUT (8s) เพราะ probe แค่ว่ามี/ไม่มี
PROBE_ALL_SAVE_EVERY = 500 # save catalog ทุก N depts กัน crash

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


def probe_unknown_depts(catalog: dict) -> int:
    """Probe N unknown deptIds, mutate catalog in place. Return new dept count."""
    candidates = pick_probe_candidates(catalog, PROBE_SAMPLE_SIZE)
    if not candidates:
        return 0
    new_found = 0
    pw_results = fetch_all_playwright(candidates, "D0")
    for dept_id, (status, items) in pw_results.items():
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
# Main
# ================================================================

def run(queue_new: bool = False, skip_probe: bool = False,
        anounce_type: str | None = None, full_poll: bool = False) -> dict:
    """anounce_type: P0/B0/D0/W0/D1 (None = D0 default).
    full_poll: poll ALL depts (default False = active-only, 50x faster).
    Multi-stage support discovered 2026-05-18.
    """
    catalog = load_catalog()
    targets = load_target_depts(catalog, active_only=not full_poll)

    if not targets:
        log("⚠️ ไม่มี target depts — initialize catalog with seed data")
        return {"error": "no_targets"}

    stage_label = STAGE_CODES.get(anounce_type or "D0", "active_bidding")
    log(f"=== RSS Discovery Run · stage={anounce_type or 'D0'} ({stage_label}) ===")
    log(f"Catalog: {len(catalog)} depts known · Target: {len(targets)}")

    # Pass 1: Poll target depts (Playwright — real Chrome ผ่าน Cloudflare)
    all_items: list[dict] = []
    poll_started = time.time()
    poll_errors = 0

    pw_results = fetch_all_playwright(targets, anounce_type)
    for dept_id, (status, items) in pw_results.items():
        if status != 200:
            poll_errors += 1
            continue
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

    poll_elapsed = time.time() - poll_started
    log(f"Polled {len(targets)} depts in {poll_elapsed:.1f}s · {len(all_items)} items · {poll_errors} errors")

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
        "--probe-w0-full", action="store_true",
        help="Probe ทุก dept ID 0001-9999 ด้วย W0 → บันทึก egp_w0_catalog.json "
             "(ทุก dept ที่มี items, ไม่กรอง keyword) เพื่อ post-process "
             "→ map deptSubName → จังหวัด ทีหลัง. "
             "รัน workflow_dispatch จาก GHA หรือ manual เท่านั้น",
    )
    args = parser.parse_args()
    _init_log_file()

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
