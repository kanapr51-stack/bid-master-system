"""
discover_jobs_playwright.py — HTTP-only job discovery using Playwright

ปัญหา (2026-05-20): หลัง retire Sebastian_Scraper.py ไม่มี discovery step
  RSS ที่มีอยู่ poll แค่ราชการส่วนกลาง ไม่ครอบคลุมนครพนม/บึงกาฬ

วิธีแก้: ใช้ Playwright (headless) เพื่อ search eGP ด้วย province keyword
  → queue new projectIds → refresh_active_jobs.py --from-queue รับช่วงต่อ

Usage:
    python discover_jobs_playwright.py                  # discovery + queue
    python discover_jobs_playwright.py --dry-run        # แสดงผล ไม่ queue

GHA: รันใน rss_scraper.yml (Playwright ติดตั้งอยู่แล้ว)
"""

import asyncio
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent.parent / "data"
RSS_QUEUE_FILE  = DATA_DIR / "rss_queue.json"
RSS_SEEN_FILE   = DATA_DIR / "rss_seen_ids.json"
ALL_JOBS_CACHE  = DATA_DIR / "_discover_alljobs_cache.json"  # local cache เพื่อเลี่ยงเรียก Sheets API ซ้ำ

EGP_SEARCH_PAGE = "https://process5.gprocurement.go.th/egp-agpc01-web/announcement"
SEARCH_API      = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"

# ทั้ง 77 จังหวัด — ingest-once + filter-per-tenant
ALL_77_PROVINCES = [
    "กระบี่", "กรุงเทพมหานคร", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร",
    "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท",
    "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง",
    "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม",
    "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส",
    "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์",
    "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา", "พะเยา", "พังงา",
    "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์",
    "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน",
    "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง",
    "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน", "เลย",
    "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ",
    "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี",
    "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย",
    "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์",
    "อุทัยธานี", "อุบลราชธานี",
]

TARGET_KEYWORDS = ALL_77_PROVINCES
PAGE_SIZE       = 100   # items per API call
MAX_PAGES       = 15    # cap per keyword — 15×100=1500 งาน/จังหวัด (ลด timeout risk)

PW_TIMEOUT      = 45_000  # ms — รอ page load + Cloudflare challenge
PAGE_INIT_WAIT  = 5       # sec — รอ React app init หลัง navigation


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_existing_ids() -> set[str]:
    """โหลด projectIds ที่รู้จักแล้ว (all_jobs + rss_queue + rss_seen)"""
    known: set[str] = set()

    # 1. rss_seen_ids
    seen_data = _load_json(RSS_SEEN_FILE, [])
    if isinstance(seen_data, list):
        known.update(str(x) for x in seen_data)

    # 2. rss_queue (pending)
    queue_data = _load_json(RSS_QUEUE_FILE, [])
    if isinstance(queue_data, list):
        for item in queue_data:
            if isinstance(item, dict) and item.get("projectId"):
                known.add(str(item["projectId"]).lstrip("P"))

    # 3. all_jobs sheet — ใช้ sheets API (ช้า แต่ครบ)
    # ใช้ cache ถ้ามีอยู่ (อายุ < 2 ชั่วโมง)
    if ALL_JOBS_CACHE.exists():
        age_sec = (datetime.now().timestamp() - ALL_JOBS_CACHE.stat().st_mtime)
        if age_sec < 7200:  # 2 hours
            cache = _load_json(ALL_JOBS_CACHE, [])
            known.update(str(x) for x in cache)
            log(f"all_jobs cache: {len(cache)} IDs (age {age_sec/60:.0f} min)")
            return known

    log("โหลด all_jobs จาก Google Sheets...")
    try:
        import dotenv
        dotenv.load_dotenv(str(Path(__file__).parent.parent / ".env"))
        sys.path.insert(0, str(Path(__file__).parent))
        from sheets_client import open_sheet
        ws = open_sheet("1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps", "all_jobs")
        rows = ws.get_all_records()
        ids = [str(r["job_id"]) for r in rows if r.get("job_id")]
        _save_json(ALL_JOBS_CACHE, ids)
        known.update(ids)
        log(f"all_jobs: {len(ids)} IDs cached")
    except Exception as e:
        log(f"[WARN] โหลด all_jobs ไม่ได้: {e} — ใช้แค่ seen_ids")

    return known


async def _discover_keyword(page, keyword: str, known_ids: set[str], max_pages: int = MAX_PAGES) -> list[dict]:
    """Search eGP for active e-bidding jobs, return list of new items"""
    new_items = []
    page_num = 1
    total_found = 0

    while page_num <= max_pages:
        url = f"{SEARCH_API}?keyword={keyword}&methodId=16&page={page_num}&pageSize={PAGE_SIZE}"
        js = f"""async () => {{
            try {{
                const r = await fetch({json.dumps(url)}, {{credentials: 'include'}});
                const t = await r.text();
                try {{ return {{status: r.status, body: JSON.parse(t)}}; }}
                catch {{ return {{status: r.status, text: t.slice(0, 500)}}; }}
            }} catch(e) {{ return {{error: e.toString()}}; }}
        }}"""

        result = await page.evaluate(js)

        if "error" in result:
            log(f"  ⚠️ {keyword} page {page_num}: {result['error']}")
            break

        if result.get("status") != 200:
            log(f"  ⚠️ {keyword} page {page_num}: HTTP {result.get('status')}")
            break

        body = result.get("body", {})
        if isinstance(body, dict) and "validateCfTurnTile" in body:
            log(f"  ⚠️ {keyword}: ต้องการ session — navigate ล้มเหลว")
            break

        data_wrapper = body.get("data", {}) or {}
        items = data_wrapper.get("data", []) or []
        total = (data_wrapper.get("totalRecords")
                 or data_wrapper.get("totalCount")
                 or data_wrapper.get("total", 0))

        if page_num == 1:
            log(f"  keyword='{keyword}': total={total} items")
            total_found = total or 0

        if not items:
            break

        for item in items:
            raw_id = str(item.get("projectId", "")).strip()
            norm_id = raw_id.lstrip("P")  # strip P prefix (pre-TOR type)
            if not norm_id or norm_id in known_ids:
                continue
            new_items.append({
                "projectId": norm_id,
                "title": item.get("projectName", "")[:120],
                "deptId": item.get("deptId", ""),
                "pubDate": str(item.get("publishDate") or item.get("pubDate") or "")[:10],
                "link": "",
                "queued_at": datetime.utcnow().isoformat(),
                "source": "discover_playwright",
                "keyword": keyword,
            })
            known_ids.add(norm_id)  # ป้องกัน duplicate ระหว่าง keywords

        if len(items) < PAGE_SIZE or (total_found and page_num * PAGE_SIZE >= total_found):
            break
        page_num += 1
        await asyncio.sleep(0.3)  # gentle pacing

    return new_items


async def discover_async(dry_run: bool = False, max_pages: int = MAX_PAGES) -> list[dict]:
    from playwright.async_api import async_playwright

    known_ids = _load_existing_ids()
    log(f"Known IDs: {len(known_ids)} total")

    all_new: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        log(f"นำทางไป eGP search page...")
        try:
            await page.goto(EGP_SEARCH_PAGE, timeout=PW_TIMEOUT, wait_until="networkidle")
        except Exception as e:
            log(f"[WARN] networkidle timeout: {e} — รอต่อ")
        await asyncio.sleep(PAGE_INIT_WAIT)
        log(f"Page loaded — cookies set")

        for kw in TARGET_KEYWORDS:
            log(f"\nSearching: '{kw}'...")
            try:
                new = await _discover_keyword(page, kw, known_ids, max_pages=max_pages)
                log(f"  → {len(new)} new jobs")
                all_new.extend(new)
            except Exception as e:
                log(f"  ❌ Error: {e}")

        await browser.close()

    log(f"\nรวม new jobs: {len(all_new)}")

    if not dry_run and all_new:
        # append to rss_queue.json
        queue = _load_json(RSS_QUEUE_FILE, [])
        if not isinstance(queue, list):
            queue = []
        queue.extend(all_new)
        _save_json(RSS_QUEUE_FILE, queue)
        log(f"✅ เพิ่ม {len(all_new)} jobs → rss_queue.json (total queue: {len(queue)})")
    elif dry_run:
        log("[dry-run] ไม่ได้บันทึก")
        for item in all_new[:10]:
            log(f"  {item['projectId']}: {item['title'][:60]}")

    return all_new


def main():
    parser = argparse.ArgumentParser(
        description="eGP keyword discovery ทั้งประเทศ (ผ่าน Playwright bypass CF)")
    parser.add_argument("--dry-run", action="store_true", help="แสดงผล ไม่บันทึก")
    parser.add_argument("--provinces", default="all",
                        help="'all' = 77 จังหวัด หรือ comma-separated (default: all)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES,
                        help=f"max pages per keyword (default {MAX_PAGES})")
    args = parser.parse_args()

    if args.provinces.strip().lower() != "all":
        global TARGET_KEYWORDS
        TARGET_KEYWORDS = [p.strip() for p in args.provinces.split(",") if p.strip()]

    asyncio.run(discover_async(dry_run=args.dry_run, max_pages=args.max_pages))


if __name__ == "__main__":
    main()
