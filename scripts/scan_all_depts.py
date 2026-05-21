"""
scan_all_depts.py — Full dept scan: deptId 0001-2603 via RSS (no Cloudflare)

เป้าหมาย: ดึงงาน D0 ทุก dept ที่มีงานอยู่ตอนนี้ → queue → refresh → sheets
รัน: python scripts/scan_all_depts.py
     python scripts/scan_all_depts.py --resume   (ต่อจากที่หยุดไว้)
     python scripts/scan_all_depts.py --max-id 500  (scan ถึง deptId 500)
"""

import sys
import json
import re
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    import requests as cffi_requests
    _use_cffi = False

RSS_URL = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}
IMPERSONATE = "chrome120" if _use_cffi else None

DATA_DIR    = Path(__file__).parent.parent / "data"
QUEUE_FILE  = DATA_DIR / "rss_queue.json"
SEEN_FILE   = DATA_DIR / "rss_seen_ids.json"
PROGRESS    = DATA_DIR / "scan_all_depts_progress.json"

SLEEP_SEC   = 1.5
COOLDOWN_N  = 50    # cooldown ทุก N depts
COOLDOWN_S  = 30    # วินาที


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_rss(dept_id: str, anounce_type: str = "D0", timeout: int = 10):
    params = {"deptId": dept_id, "anounceType": anounce_type}
    try:
        if _use_cffi:
            r = cffi_requests.get(RSS_URL, params=params, headers=HEADERS,
                                   timeout=timeout, impersonate=IMPERSONATE)
        else:
            r = cffi_requests.get(RSS_URL, params=params, headers=HEADERS, timeout=timeout)
        return r.status_code, r.content.decode("tis-620", errors="replace")
    except Exception as e:
        return -1, str(e)


def parse_items(xml_text: str) -> list[dict]:
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL):
        def tag(t):
            m = re.search(rf"<{t}[^>]*>(.*?)</{t}>", block, re.DOTALL)
            return m.group(1).strip() if m else ""

        title = tag("title")
        link  = tag("link")
        pub   = tag("pubDate")

        # extract projectId จาก link
        pid_m = re.search(r"projectId=([A-Z]?\d+)", link)
        if not pid_m:
            continue
        raw_pid = pid_m.group(1)
        norm_pid = raw_pid.lstrip("P")

        dept_m = re.search(r"deptId=(\d+)", link)
        dept_id = dept_m.group(1) if dept_m else ""

        items.append({
            "projectId": norm_pid,
            "title": title[:120],
            "deptId": dept_id,
            "pubDate": pub[:10],
            "link": link,
            "queued_at": datetime.utcnow().isoformat(),
            "source": "scan_all_depts",
        })
    return items


def load_known_ids() -> set[str]:
    known: set[str] = set()
    seen = _load_json(SEEN_FILE, [])
    if isinstance(seen, list):
        known.update(str(x) for x in seen)
    queue = _load_json(QUEUE_FILE, [])
    if isinstance(queue, list):
        for item in queue:
            if isinstance(item, dict) and item.get("projectId"):
                known.add(str(item["projectId"]).lstrip("P"))
    return known


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume",       action="store_true", help="ต่อจากที่หยุดไว้")
    parser.add_argument("--max-id",       type=int, default=2603, help="scan ถึง deptId นี้")
    parser.add_argument("--min-id",       type=int, default=1,    help="เริ่มจาก deptId นี้")
    parser.add_argument("--anounce-type", type=str, default="D0", help="RSS anounceType: D0/B0/W0/P0")
    args = parser.parse_args()

    atype = args.anounce_type.upper()
    # progress file แยกตาม anounceType
    progress_file = DATA_DIR / f"scan_all_depts_{atype}_progress.json"

    log("=" * 60)
    log(f"Scan All Depts [{atype}] — deptId {args.min_id:04d} → {args.max_id:04d}")
    log("=" * 60)

    # โหลด progress ถ้า resume
    start_id = args.min_id
    if args.resume:
        prog = _load_json(progress_file, {})
        start_id = prog.get("last_id", args.min_id) + 1
        log(f"Resume จาก deptId {start_id:04d}")

    known_ids = load_known_ids()
    log(f"Known IDs: {len(known_ids)}")

    queue = _load_json(QUEUE_FILE, [])
    if not isinstance(queue, list):
        queue = []

    total_new   = 0
    total_depts = 0
    active_depts = []

    for n in range(start_id, args.max_id + 1):
        dept_id = f"{n:04d}"

        status, xml = fetch_rss(dept_id, atype)

        if status == -1:
            log(f"  ⚠️  deptId={dept_id}: network error — skip")
            time.sleep(SLEEP_SEC)
            continue

        items = parse_items(xml)
        new_items = [i for i in items if i["projectId"] not in known_ids]

        if new_items:
            active_depts.append(dept_id)
            for item in new_items:
                item["anounce_type"] = atype
                known_ids.add(item["projectId"])
                queue.append(item)
            total_new += len(new_items)
            log(f"  ✅ deptId={dept_id}: {len(items)} items, {len(new_items)} new (รวม {total_new})")

        total_depts += 1

        # บันทึก progress + queue ทุก 50 depts
        if total_depts % COOLDOWN_N == 0:
            _save_json(QUEUE_FILE, queue)
            _save_json(progress_file, {
                "anounce_type": atype,
                "last_id": n,
                "total_new": total_new,
                "active_depts": len(active_depts),
                "updated_at": datetime.now().isoformat(),
            })
            pct = (n - args.min_id + 1) / (args.max_id - args.min_id + 1) * 100
            log(f"  📍 checkpoint deptId={dept_id} ({pct:.0f}%) — {total_new} new, {len(active_depts)} active depts — cooldown {COOLDOWN_S}s")
            time.sleep(COOLDOWN_S)
        else:
            time.sleep(SLEEP_SEC)

    # บันทึกสุดท้าย
    _save_json(QUEUE_FILE, queue)
    _save_json(progress_file, {
        "anounce_type": atype,
        "last_id": args.max_id,
        "total_new": total_new,
        "active_depts": len(active_depts),
        "completed": True,
        "updated_at": datetime.now().isoformat(),
    })

    log(f"\n{'='*60}")
    log(f"สรุป:")
    log(f"  scanned: {total_depts} depts")
    log(f"  active:  {len(active_depts)} depts (มีงาน D0)")
    log(f"  new jobs queued: {total_new}")
    log(f"  active deptIds: {active_depts[:20]}{'...' if len(active_depts)>20 else ''}")
    log(f"\nขั้นต่อไป: python scripts/refresh_active_jobs.py")


if __name__ == "__main__":
    main()
