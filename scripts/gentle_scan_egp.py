"""
gentle_scan_egp.py — Continuous gentle RSS scan to fill catalog

Strategy (2026-05-18 lesson learned):
  - 1 worker (sequential, NO concurrency — gentleness > speed)
  - 2 seconds between requests = 30 req/min (POC tested 50/min safe)
  - Adaptive: ถ้า timeout rate > 30% ในล่าสุด 100 calls → cooldown
  - Safe-stop: ถ้า timeout rate > 70% ใน 50 calls → หยุดทั้งหมด (กัน block)
  - Resume-aware: ข้าม deptId ที่อยู่ใน catalog แล้ว
  - Save catalog ทุก 50 entries (กัน crash เสียงาน)
  - Save empty entries ด้วย (กัน re-probe)
"""
import sys
import re
import json
import time
import random
from pathlib import Path
from datetime import datetime
from collections import deque

from curl_cffi import requests

sys.stdout.reconfigure(encoding="utf-8")

RSS_URL = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
DATA_DIR = Path(__file__).parent.parent / "data"
CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"
PROGRESS_FILE = DATA_DIR / "gentle_scan_progress.json"

IMPERSONATE = "chrome120"

SCAN_END = 9999
BASE_SLEEP = 2.0           # baseline between requests (sec)
JITTER = 0.5               # +/- random
SAVE_EVERY = 50
WINDOW_SIZE = 100          # rolling window for timeout rate
COOLDOWN_THRESHOLD = 0.30  # >30% timeout → cooldown
SAFE_STOP_THRESHOLD = 0.70 # >70% timeout → stop
COOLDOWN_DURATION = 120    # 2 min cooldown
HEALTH_CHECK_EVERY = 25    # log progress every N requests


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


def fetch_one(session: requests.Session, dept_id: str) -> tuple[str, list[dict] | None]:
    """Return (status, items): status='ok' | 'timeout' | 'error'"""
    try:
        r = session.get(RSS_URL, params={"deptId": dept_id}, timeout=12)
        if r.status_code != 200:
            return f"http_{r.status_code}", None
        text = decode_thai(r.content)
        return "ok", parse_items(text)
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg or "timed out" in msg:
            return "timeout", None
        if "connection" in msg:
            return "timeout", None
        return f"error_{type(e).__name__}", None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-minutes", type=int, default=0,
                        help="หยุดหลัง N นาที (0=ไม่จำกัด, GHA ใช้ 75)")
    args = parser.parse_args()
    max_seconds = args.max_minutes * 60 if args.max_minutes > 0 else None

    DATA_DIR.mkdir(exist_ok=True)

    # Load catalog
    catalog: dict = {}
    if CATALOG_FILE.exists():
        try:
            catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            log(f"Loaded catalog: {len(catalog)} entries")
        except json.JSONDecodeError:
            catalog = {}

    # known_ids = deptIds ที่ confirmed แล้ว (skip เฉพาะ probe สำเร็จ, ไม่ skip probe_429_still_limited)
    SKIP_NOTES = {"probe_429_still_limited", "probe_429_retry_err_-1"}
    known_ids = set()
    for k, v in catalog.items():
        if k.isdigit() and len(k) == 4:
            if isinstance(v, dict):
                note = v.get("note", v.get("source", ""))
                if note not in SKIP_NOTES:
                    known_ids.add(int(k))
            else:
                known_ids.add(int(k))
    pending = [n for n in range(1, SCAN_END + 1) if n not in known_ids]
    log(f"Pending: {len(pending)} deptIds to probe")

    if not pending:
        log("✅ Catalog already complete!")
        return

    # Shuffle to spread load (don't hammer sequential ranges)
    random.shuffle(pending)

    session = requests.Session(impersonate=IMPERSONATE)

    # Rolling stats
    recent_results: deque = deque(maxlen=WINDOW_SIZE)
    started = time.time()
    done = 0
    found_active = 0
    found_empty = 0

    for i, n in enumerate(pending, 1):
        dept_id = f"{n:04d}"
        status, items = fetch_one(session, dept_id)
        done += 1

        if status == "ok":
            recent_results.append("ok")
            if items:
                catalog[dept_id] = {
                    "item_count": len(items),
                    "projectIds": [it.get("projectId") for it in items if it.get("projectId")][:15],
                    "titles": [it.get("title", "")[:120] for it in items[:5]],
                    "pubDates": [it.get("pubDate", "") for it in items[:3]],
                    "scanned_at": datetime.now().isoformat(timespec="seconds"),
                    "source": "gentle_scan",
                }
                found_active += 1
                first_title = items[0].get("title", "")[:60]
                log(f"  ✅ {dept_id}: {len(items)} items · {first_title}")
            else:
                catalog[dept_id] = {
                    "item_count": 0,
                    "scanned_at": datetime.now().isoformat(timespec="seconds"),
                    "source": "gentle_scan",
                }
                found_empty += 1
        else:
            recent_results.append("timeout")

        # Periodic save
        if done % SAVE_EVERY == 0:
            CATALOG_FILE.write_text(
                json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            PROGRESS_FILE.write_text(
                json.dumps({
                    "scanned_total": done,
                    "found_active": found_active,
                    "found_empty": found_empty,
                    "catalog_size": len(catalog),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }), encoding="utf-8"
            )

        # Health check & adaptive control
        if done % HEALTH_CHECK_EVERY == 0:
            timeout_rate = recent_results.count("timeout") / max(1, len(recent_results))
            elapsed = time.time() - started
            rate_per_min = (done / elapsed) * 60 if elapsed else 0
            remaining = len(pending) - done
            eta_hr = (remaining / rate_per_min / 60) if rate_per_min else 0
            log(
                f"  [progress] {done}/{len(pending)} active={found_active} empty={found_empty} "
                f"timeout_rate={timeout_rate:.0%} rate={rate_per_min:.1f}/min eta={eta_hr:.1f}h"
            )

            if timeout_rate > SAFE_STOP_THRESHOLD:
                log(f"  🛑 SAFE-STOP — timeout rate {timeout_rate:.0%} > {SAFE_STOP_THRESHOLD:.0%} (กัน block หนักกว่าเดิม)")
                break

            if timeout_rate > COOLDOWN_THRESHOLD:
                log(f"  ⏸ Cooldown {COOLDOWN_DURATION}s (timeout {timeout_rate:.0%} > {COOLDOWN_THRESHOLD:.0%})")
                time.sleep(COOLDOWN_DURATION)

        # หยุดถ้าเกิน max_minutes (สำหรับ GHA timeout)
        if max_seconds and (time.time() - started) >= max_seconds:
            log(f"  ⏰ ครบ {args.max_minutes} นาที — หยุดเพื่อ commit (resume run ถัดไป)")
            break

        # Gentle sleep between requests
        sleep_sec = BASE_SLEEP + random.uniform(-JITTER, JITTER)
        time.sleep(max(0.5, sleep_sec))

    # Final save
    CATALOG_FILE.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    PROGRESS_FILE.write_text(
        json.dumps({
            "scanned_total": done,
            "found_active": found_active,
            "found_empty": found_empty,
            "catalog_size": len(catalog),
            "completed_at": datetime.now().isoformat(timespec="seconds"),
        }), encoding="utf-8"
    )
    elapsed = time.time() - started
    log("")
    log(f"✅ DONE — scanned {done} · {found_active} active · {found_empty} empty")
    log(f"   Catalog total: {len(catalog)}")
    log(f"   Time: {elapsed/60:.1f} min ({elapsed/3600:.1f} hours)")


if __name__ == "__main__":
    main()
