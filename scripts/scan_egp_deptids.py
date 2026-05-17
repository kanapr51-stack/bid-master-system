"""
scan_egp_deptids.py — Brute-force scan deptId 0001-9999 บน EGP RSS feed
เก็บ dept ที่มี items + sample projectIds + titles

Two-pass design:
  Pass 1: Fast concurrent scan (workers=12, no retry) — discover most depts quickly
          Track errors separately
  Pass 2: Retry pass on errored deptIds with backoff (workers=4)

Output: data/egp_deptid_catalog.json
Errors: data/egp_deptid_scan_errors.json (debug)
Runtime: 5-10 minutes total
"""
import sys
import re
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

RSS_URL = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
OUT_DIR = Path(__file__).parent.parent / "data"
OUT_FILE = OUT_DIR / "egp_deptid_catalog.json"
ERR_FILE = OUT_DIR / "egp_deptid_scan_errors.json"
PROGRESS_FILE = OUT_DIR / "egp_deptid_scan_progress.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}

SCAN_END = 9999
# 2026-05-18 revision: SLOW + SAFE — workers=2, sleep=1s = ~2 req/s
# (POC: ~50 req/min ปลอดภัย → 120 req/min ก็ยังไหว)
# Time: 9999 ÷ 2 workers ÷ ~1.5 req/s effective = ~55 นาที (รวม retries)
PASS1_WORKERS = 2
PASS2_WORKERS = 1
PASS2_MAX_RETRIES = 3
INTER_REQUEST_SLEEP = 0.5  # delay between completed requests per worker


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
        for tag in ["title", "description", "pubDate"]:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", item_xml, re.DOTALL)
            if m:
                item[tag] = m.group(1).strip()
        if "description" in item:
            pid_match = re.search(r"\b(\d{11,12})\b", item["description"])
            item["projectId"] = pid_match.group(1) if pid_match else None
        items.append(item)
    return items


_local = threading.local()


def session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        _local.s = s
    return s


def fetch_one(n: int, timeout: int = 12) -> tuple[str, str, list[dict]]:
    """Return (dept_id, status, items)
    status: 'ok' | 'http_NNN' | 'error_<exception>'
    """
    dept_id = f"{n:04d}"
    try:
        r = session().get(RSS_URL, params={"deptId": dept_id}, timeout=timeout)
        if r.status_code != 200:
            return dept_id, f"http_{r.status_code}", []
        text = decode_thai(r.content)
        items = parse_items(text)
        return dept_id, "ok", items
    except Exception as e:
        return dept_id, f"err_{type(e).__name__}", []


def add_to_catalog(catalog: dict, dept_id: str, items: list[dict]):
    """บันทึก dept entry — รวม empty results เพื่อป้องกันการ re-probe โดย RSS scraper"""
    catalog[dept_id] = {
        "item_count": len(items),
        "projectIds": [it.get("projectId") for it in items if it.get("projectId")][:15],
        "titles": [it.get("title", "")[:120] for it in items[:5]],
        "pubDates": [it.get("pubDate", "") for it in items[:3]],
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "source": "batch_scan",
    }


def save(catalog: dict, errors: list, last_n: int):
    OUT_FILE.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    ERR_FILE.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    PROGRESS_FILE.write_text(
        json.dumps({"last_scanned": last_n, "found": len(catalog), "errors": len(errors)}),
        encoding="utf-8",
    )


def run_pass(name: str, numbers: list[int], workers: int, timeout: int,
             catalog: dict, errors_out: list, save_lock: threading.Lock) -> list[int]:
    """Run a scan pass — return list of N that errored"""
    log(f"=== {name}: {len(numbers)} deptIds, workers={workers}, timeout={timeout}s ===")
    started = time.time()
    done = 0
    errored: list[int] = []
    highest = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_one, n, timeout): n for n in numbers}
        for fut in as_completed(futures):
            n = futures[fut]
            done += 1
            try:
                dept_id, status, items = fut.result()
            except Exception as e:
                errored.append(n)
                continue

            if status == "ok":
                with save_lock:
                    add_to_catalog(catalog, dept_id, items)
                if items:
                    first_title = items[0].get("title", "")[:60]
                    log(f"  ✅ {dept_id}: {len(items)} items · {first_title}")
                # ถ้า empty (0 items) ก็บันทึกไว้ — กัน RSS scraper มา re-probe
            else:
                errored.append(n)
                with save_lock:
                    errors_out.append({"deptId": dept_id, "status": status, "pass": name})
            time.sleep(INTER_REQUEST_SLEEP)

            if n > highest:
                highest = n
            if done % 250 == 0:
                with save_lock:
                    save(catalog, errors_out, highest)
                elapsed = time.time() - started
                rate = done / elapsed if elapsed else 0
                eta = (len(numbers) - done) / rate / 60 if rate else 0
                log(f"  [progress] {done}/{len(numbers)} found={len(catalog)} err={len(errored)} rate={rate:.1f}/s eta={eta:.1f}m")

    elapsed = time.time() - started
    log(f"   {name} done in {elapsed/60:.1f}m · {len(errored)} errors → next pass")
    return errored


def main():
    OUT_DIR.mkdir(exist_ok=True)
    catalog: dict = {}
    errors_log: list = []
    save_lock = threading.Lock()

    # Load existing catalog — skip deptIds already known
    if OUT_FILE.exists():
        try:
            catalog = json.loads(OUT_FILE.read_text(encoding="utf-8"))
            log(f"Loaded existing catalog: {len(catalog)} entries (จะข้ามตอน scan)")
        except json.JSONDecodeError:
            catalog = {}

    known_ids = {int(k) for k in catalog.keys() if k.isdigit()}

    # Pass 1: Slow scan — skip already-known
    nums = [n for n in range(1, SCAN_END + 1) if n not in known_ids]
    log(f"Will scan {len(nums)} unknown deptIds (skip {len(known_ids)} known)")
    errored = run_pass("Pass 1 (slow)", nums, PASS1_WORKERS, timeout=15,
                       catalog=catalog, errors_out=errors_log, save_lock=save_lock)
    save(catalog, errors_log, SCAN_END)

    # Pass 2-N: Retry passes
    for attempt in range(1, PASS2_MAX_RETRIES + 1):
        if not errored:
            break
        # Reset errors_log for this pass
        errors_log = [e for e in errors_log if e.get("pass") != f"Pass{attempt + 1}"]
        time.sleep(3)
        errored = run_pass(
            f"Pass {attempt + 1} (retry, {len(errored)} items)",
            errored,
            PASS2_WORKERS,
            timeout=20,
            catalog=catalog,
            errors_out=errors_log,
            save_lock=save_lock,
        )
        save(catalog, errors_log, SCAN_END)

    log(f"\n✅ ALL DONE — {len(catalog)} active depts · {len(errored)} unresolved errors")
    log(f"   Output: {OUT_FILE}")
    log(f"   Errors: {ERR_FILE}")


if __name__ == "__main__":
    main()
