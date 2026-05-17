"""
Sebastian Scraper — ดึงข้อมูลงานประมูลภาครัฐจาก gprocurement.go.th
เป้าหมาย: งานก่อสร้าง/คอนกรีต → raw_jobs (archive) + e-bidding → raw_jobs_bidding

วิธีใช้:
    1. เปิด Chrome ด้วย:
       Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\\Temp\\ChromeDebug"
    2. python Sebastian_Scraper.py

API ที่ใช้จริง (2026-04):
    https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement
"""

import sys
import time
import re
import json
import hashlib
import base64
import io
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode, quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

sys.stdout.reconfigure(encoding="utf-8")

# ---- CONFIG ----
DEBUG_PORT      = 9222
SPREADSHEET_ID  = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
DOWNLOAD_DIR    = Path(__file__).parent.parent / "downloads"
SEEN_IDS_FILE   = Path(__file__).parent.parent / "data" / "seen_ids.json"
SCRAPER_STATE_FILE = Path(__file__).parent.parent / "data" / "scraper_state.json"

RATE_LIMIT_COOLDOWN = 60   # วินาทีที่รอหลังโดน rate limit ก่อน retry

# Incremental scraping — เปิด/ปิดได้ผ่าน --no-incremental flag
INCREMENTAL_DEFAULT = True

# Process5 — Angular SPA (new UI)
SEARCH_URL_PROCESS5 = "https://process5.gprocurement.go.th/egp-agpc01-web/announcement"
API_BASE            = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project"
BUDGET_YEAR         = "2569"   # พ.ศ. ปัจจุบัน

# ---- Filter keywords (กรอง title — ใช้กับทุก search term เหมือนกันหมด) ----
FILTER_KEYWORDS = [
    # ถนน
    "ถนนคอนกรีต", "ก่อสร้างถนน", "ซ่อมแซมถนน", "ปรับปรุงถนน",
    "ปรับปรุงถนนลูกรัง", "ถนนลาดยาง", "เสริมผิว", "ผิวจราจร", "ไหล่ทาง",
    # คอนกรีต
    "คอนกรีตเสริมเหล็ก", "คอนกรีตผสมเสร็จ", "ปูคอนกรีต",
    "ลานคอนกรีต", "ทางเดินคอนกรีต",
    # สะพาน / อาคาร / โยธา
    "ก่อสร้างสะพาน", "ซ่อมแซมสะพาน", "ก่อสร้างอาคาร", "งานโยธา",
    "ก่อสร้างรั้ว", "กำแพง",
    # ท่อ / ฝาย / น้ำ
    "ท่อระบายน้ำ", "รางระบายน้ำ", "ก่อสร้างท่อ", "วางท่อ", "ขุดลอก",
    "ฝายคอนกรีต", "ฝาย", "คสล.",
    # วัสดุก่อสร้าง
    "Dowel", "Wire Mesh", "ถมดิน", "ปรับพื้นที่",
]

# ---- Department search terms → expected province (ชื่อซ้ำข้ามจังหวัด ต้องระบุจังหวัดที่คาดไว้) ----
# Key = search term, Value = จังหวัดที่ถูกต้อง
# ถ้า province ที่ extract ได้ไม่ตรงและไม่ว่าง → ถือว่าผิดจังหวัด → ข้าม
DEPT_PROVINCE_MAP: dict[str, str] = {
    "ตำบลบ้านแพง":                           "นครพนม",
    "ตำบลไผ่ล้อม":                           "นครพนม",
    "ตำบลโพนทอง":                            "นครพนม",
    "ตำบลนาเข":                              "นครพนม",
    "ตำบลหนองแวง":                           "นครพนม",
    "ตำบลนาหว้า":                            "นครพนม",
    "ตำบลสามผง":                             "นครพนม",
    "ตำบลหาดแพง":                            "นครพนม",
    "ตำบลศรีสงคราม":                         "นครพนม",
    "ตำบลหนองซน":                            "นครพนม",
    "ตำบลดอนเตย":                            "นครพนม",
    "ตำบลนาทม":                              "นครพนม",
    "ตำบลดงบัง":                             "นครพนม",
    "ตำบลบุ่งคล้า":                          "บึงกาฬ",
    "ตำบลโคกกว้าง":                          "บึงกาฬ",
    "ตำบลหนองเดิ่น":                         "บึงกาฬ",
    "ตำบลท่าดอกคำ":                          "บึงกาฬ",
    "ตำบลโพธิ์หมากแข้ง":                     "บึงกาฬ",
    "ตำบลบึงงาม":                            "บึงกาฬ",
    "ตำบลบึงโขงหลง":                         "บึงกาฬ",
    "โยธาธิการและผังเมืองจังหวัดนครพนม":      "นครพนม",
    "ชลประทานนครพนม":                        "นครพนม",
    "แขวงทางหลวงชนบทนครพนม":                "นครพนม",
    "องค์การบริหารส่วนจังหวัดนครพนม":        "นครพนม",
    "โยธาธิการและผังเมืองจังหวัดบึงกาฬ":     "บึงกาฬ",
    "ชลประทานบึงกาฬ":                        "บึงกาฬ",
    "แขวงทางหลวงชนบทบึงกาฬ":               "บึงกาฬ",
    "องค์การบริหารส่วนจังหวัดบึงกาฬ":       "บึงกาฬ",
}

def is_relevant_job(title: str) -> bool:
    return any(k in title for k in FILTER_KEYWORDS)

# Method ID → description
METHOD_MAP = {
    "15": "e-market",
    "16": "e-bidding",
    "19": "เฉพาะเจาะจง",
    "18": "คัดเลือก",
    "03": "ประกวดราคา",
}


# ================================================================
# UTILITIES
# ================================================================

def ensure_dirs():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)


FLOW_STATUS_MAP = {
    "หนังสือเชิญชวน/ประกาศเชิญชวน":                        "กำลังประมูล",
    "จัดทำสัญญา/บริหารสัญญา":                              "ประมูลแล้ว",
    "อนุมัติสั่งซื้อสั่งจ้างและประกาศผู้ชนะการเสนอราคา":   "ประมูลแล้ว",
    "ยกเลิกโครงการ":                                        "ยกเลิก",
    "จัดทำ TOR":                                             "กำลังเตรียม",
}


def load_seen_ids() -> set:
    if SEEN_IDS_FILE.exists():
        return set(json.loads(SEEN_IDS_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen_ids(seen: set):
    SEEN_IDS_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ── Scraper state for incremental scraping ─────────────────────
# Strategy: cache top job_id per keyword. Next run → fetch page 1 first,
# if first item.jid == cached → no new jobs → skip pagination → 95% speedup
def load_scraper_state() -> dict:
    if SCRAPER_STATE_FILE.exists():
        try:
            return json.loads(SCRAPER_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_scraper_state(state: dict):
    SCRAPER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCRAPER_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update_keyword_state(state: dict, keyword: str, first_item: dict, page1_hash: str = ""):
    """Update state for keyword with top item + page 1 content hash"""
    state.setdefault("keyword_states", {})[keyword] = {
        "last_scraped_at": datetime.now().isoformat(timespec="seconds"),
        "latest_jid":      first_item.get("projectId", ""),
        "latest_publish":  first_item.get("announceDate", ""),
        "page1_hash":      page1_hash,
    }


def compute_page_hash(items: list) -> str:
    """SHA1 hash of (jid + publish_date) tuples — sensitive to actual data change"""
    sig = "|".join(
        f"{(it.get('projectId') or '')}~{(it.get('announceDate') or '')}"
        for it in items[:10]
    )
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]


def exponential_backoff(attempt: int, base: int = 30, max_wait: int = 600, jitter: int = 30) -> float:
    """attempt 0 → ~30s, 1 → ~60s, 2 → ~120s, 3 → ~240s, capped at 600s"""
    import random
    wait = min(base * (2 ** attempt), max_wait)
    return wait + random.uniform(0, jitter)


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ================================================================
# SHEETS CLIENT
# ================================================================

def _get_ws(sheet_name: str):
    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet
    return open_sheet(SPREADSHEET_ID, sheet_name)


def _extract_search_keyword(quantity_note: str) -> str:
    """quantity_note: 'keyword:X | step' หรือ 'province:X | step' → คืน X"""
    if not quantity_note:
        return ""
    first = str(quantity_note).split("|", 1)[0].strip()
    for prefix in ("keyword:", "province:"):
        if first.startswith(prefix):
            return first[len(prefix):].strip()
    return ""


def _build_all_jobs_row(j: dict, first_seen: str, last_seen: str) -> list:
    """all_jobs schema (18 cols) — Source of Truth
    3 fields ท้าย (step_id, project_status_raw, announce_type) เว้นว่าง —
    refresh_active_jobs.py จะเติมจาก getProjectDetail
    """
    note = j.get("quantity_note", "")
    return [
        j.get("job_id", ""),
        j.get("title", ""),
        j.get("department", ""),
        j.get("province", ""),
        j.get("district", ""),
        j.get("subdistrict", ""),
        j.get("procurement_type", ""),
        j.get("budget", ""),
        j.get("publish_date", ""),
        j.get("deadline", ""),
        j.get("project_status", ""),
        _extract_search_keyword(note),
        j.get("tor_url", ""),
        first_seen,
        last_seen,
        j.get("step_id", ""),
        j.get("project_status_raw", ""),
        j.get("announce_type", ""),
    ]


def append_jobs_to_sheet(jobs: list[dict]):
    """
    Upsert jobs to all_jobs (single source of truth).
    - งานใหม่: append + first_seen_at = last_seen_at = now
    - งานเดิม: update ทั้งแถว แต่คง first_seen_at เดิม + last_seen_at = now

    Classifier เป็นคนแยกชีท derived (active_bidding/pending_award/awarded_jobs) ตอนรันถัดไป
    """
    if not jobs:
        return

    now = datetime.now().isoformat(timespec="seconds")
    ws = _get_ws("all_jobs")
    all_values = ws.get_all_values()

    if not all_values:
        log("❌ all_jobs ว่างเปล่า (ยังไม่ได้สร้าง headers?) — abort")
        return

    headers = all_values[0]
    h_idx = {h: i for i, h in enumerate(headers)}
    fs_col = h_idx.get("first_seen_at", -1)

    existing = {}  # job_id -> (row_num, first_seen_at)
    for row_num, row in enumerate(all_values[1:], start=2):
        jid = row[0] if row else ""
        if jid:
            fs = row[fs_col] if 0 <= fs_col < len(row) else now
            existing[jid] = (row_num, fs or now)

    new_rows = []
    update_data = []  # batch update payload
    for j in jobs:
        jid = j.get("job_id", "")
        if not jid:
            continue
        if jid in existing:
            row_num, first_seen = existing[jid]
            row = _build_all_jobs_row(j, first_seen, now)
            update_data.append({
                "range": f"all_jobs!A{row_num}:R{row_num}",
                "values": [row],
            })
        else:
            new_rows.append(_build_all_jobs_row(j, now, now))

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        log(f"เพิ่ม {len(new_rows)} งานใหม่ลง all_jobs")

    if update_data:
        BATCH = 200
        for i in range(0, len(update_data), BATCH):
            chunk = update_data[i:i+BATCH]
            ws.spreadsheet.values_batch_update(
                {"valueInputOption": "USER_ENTERED", "data": chunk}
            )
        log(f"อัปเดต {len(update_data)} งานเดิม (last_seen_at + status) ใน all_jobs")

    if not new_rows and not update_data:
        log("ไม่มีงานที่จะ upsert")


# ================================================================
# BROWSER CONNECTION
# ================================================================

def connect_browser(p):
    # Fail-fast: timeout 5s ต่อ attempt × 3 ครั้ง = ~15 วินาที (เดิม 45 นาที)
    for attempt in range(3):
        try:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUG_PORT}",
                timeout=5000,
            )
            log("เชื่อมต่อ Chrome สำเร็จ")
            return browser
        except Exception as e:
            log(f"  รอ Chrome... ({attempt+1}/3): {type(e).__name__}")
            time.sleep(2)
    raise RuntimeError("เชื่อมต่อ Chrome ไม่ได้ — เปิด Chrome ด้วย --remote-debugging-port=9222")


def new_stealth_page(browser):
    context = browser.contexts[0]
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        delete navigator.__proto__.webdriver;
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
    """)
    return context.new_page()


# ================================================================
# PROCESS5 SCRAPER — API-based (2026)
# ================================================================

def detect_cloudflare_block(page) -> bool:
    """ตรวจ Cloudflare modal บล็อกหน้า — เจอแล้วต้อง long cooldown"""
    try:
        modal = page.query_selector("modal-container.show .modal-body")
        if modal:
            txt = (modal.inner_text() or "")
            if "Cloudflare" in txt and "ไม่ผ่าน" in txt:
                return True
    except Exception:
        pass
    return False


def init_process5_page(page, cloudflare_retries: int = 2) -> bool:
    """
    โหลดหน้า process5 และรอ Cloudflare Turnstile ให้เสร็จ
    ถ้าเจอ Cloudflare modal block → long cooldown 5 นาที + retry
    """
    for attempt in range(cloudflare_retries + 1):
        log("กำลังโหลด process5.gprocurement.go.th ...")
        try:
            page.goto(SEARCH_URL_PROCESS5, wait_until="load", timeout=45000)
        except Exception as e:
            log(f"  goto error: {e}")
            return False

        time.sleep(5)

        # ตรวจ Cloudflare modal บล็อกหรือยัง (2026-05-17)
        if detect_cloudflare_block(page):
            if attempt < cloudflare_retries:
                cooldown = 300  # 5 นาที
                log(f"  🛑 Cloudflare บล็อก — long cooldown {cooldown}s แล้ว retry ({attempt+1}/{cloudflare_retries})")
                time.sleep(cooldown)
                continue
            else:
                log(f"  🛑 Cloudflare บล็อกต่อเนื่อง — ยอมแพ้")
                return False

        try:
            page.wait_for_selector("input[name*='keyword']", timeout=20000)
        except Exception:
            log("  ไม่พบ search input")
            return False

        # รอปุ่ม ค้นหา ให้ enabled (Cloudflare Turnstile ต้องเสร็จก่อน)
        log("  รอปุ่มค้นหา enabled (Cloudflare Turnstile)...")
        deadline = time.time() + 35
        btn_ready = False
        while time.time() < deadline:
            try:
                btn = page.query_selector("button:has-text('ค้นหา')")
                if btn and btn.is_enabled():
                    btn_ready = True
                    break
            except Exception:
                pass
            time.sleep(0.8)
        if btn_ready:
            log("  ปุ่มค้นหา enabled แล้ว")
        else:
            log("  ปุ่มยัง disabled หลัง 35s — ดำเนินการต่อ")

        log("  หน้า process5 พร้อมแล้ว")
        return True

    return False


def search_keyword_process5(page, keyword: str, max_pages: int = 30, scraper_state: dict = None) -> list[dict]:
    """
    ค้นหา keyword บน process5 แล้วดึงทุกหน้าผ่าน API
    คืนค่า list ของ job dicts

    Incremental mode (เมื่อ scraper_state ส่งมา):
    - Cache top jid per keyword ใน scraper_state["keyword_states"][keyword]
    - หลัง page 1: ถ้า first item.jid == cached → no new jobs → return ทันที (skip pagination)
    - ระหว่าง pagination: ถ้าเจอ cached jid → break (no need to fetch further)
    """
    log(f"ค้นหา: '{keyword}'")
    jobs = []
    cached_jid = ""
    cached_hash = ""
    if scraper_state:
        kw_state = scraper_state.get("keyword_states", {}).get(keyword, {})
        cached_jid = kw_state.get("latest_jid", "")
        cached_hash = kw_state.get("page1_hash", "")

    # หา search input
    search_input = None
    for sel in ["input[name*='keyword']", "input[placeholder*='ค้นหา']", "input[type='search']"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                search_input = el
                break
        except Exception:
            pass

    if not search_input:
        log("  ไม่พบ search input")
        return jobs, False

    # Clear และ type keyword ด้วย keyboard simulation (สำหรับ Angular)
    search_input.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    time.sleep(0.2)
    page.keyboard.type(keyword, delay=60)
    time.sleep(0.8)

    # คลิกปุ่มค้นหาและดักรับ response + URL
    captured_search_url = []
    first_page_items = []

    def on_request_capture(req):
        url = req.url
        if ("egp-atpj27-service" in url and
                "announcement" in url and
                "sumProject" not in url and
                "cfturnstile" not in url):
            captured_search_url.append(url)

    page.on("request", on_request_capture)

    try:
        with page.expect_response(
            lambda r: (
                "egp-atpj27-service" in r.url and
                "announcement" in r.url and
                "sumProject" not in r.url and
                "cfturnstile" not in r.url
            ),
            timeout=30000
        ) as resp_info:
            try:
                page.locator("button:has-text('ค้นหา')").first.click(timeout=8000)
            except Exception:
                search_input.press("Enter")

        first_resp = resp_info.value
        first_body = first_resp.json()

        if first_body.get("response", {}).get("responseCode") == "0":
            items = first_body.get("data", {}).get("data", [])
            first_page_items = items
            for item in items:
                job = parse_api_item(item, keyword)
                if job:
                    jobs.append(job)
            log(f"  หน้า 1: {len(items)} รายการ")
        else:
            log(f"  API error: {first_body.get('response', {})}")

    except Exception as e:
        err_str = str(e)
        page.remove_listener("request", on_request_capture)
        if "Timeout" in err_str or "timeout" in err_str:
            log(f"  Search timeout — reinit session แล้ว retry ทันที")
            return jobs, "timeout"
        log(f"  Search failed: {e}")
        return jobs, False

    page.remove_listener("request", on_request_capture)

    if not captured_search_url or not first_page_items:
        return jobs, False  # 0 results or no URL captured

    # ── INCREMENTAL: dual check (content hash + top jid) ──
    page1_hash = compute_page_hash(first_page_items)
    if cached_hash and page1_hash == cached_hash:
        log(f"  ⚡ incremental: page 1 hash ตรงกับ cache ({cached_hash}) → ไม่มีงานใหม่ (skip)")
        return jobs, "no_new"
    if cached_jid and first_page_items[0].get("projectId") == cached_jid:
        log(f"  ⚡ incremental: top jid={cached_jid} ตรง cache → ไม่มีงานใหม่ (skip)")
        return jobs, "no_new"

    # Parallel pagination — eGP rate limit ทดสอบแล้ว: threshold ~100 reqs / 120s window (IP-based)
    # ส่งเร็วก็โดนเท่ากับส่งช้า → กลยุทธ์: burst สูงสุด (80 reqs ใน 5s) แล้วรอเต็ม window ให้ aged out
    base_url = captured_search_url[0]
    BATCH_SIZE      = 20      # parallel requests ต่อ batch (test ผ่าน 20 parallel ฉิวๆ)
    BATCHES_PER_GROUP = 4     # 4 × 20 = 80 reqs/group (ปลอดภัย ใต้ threshold 100)
    GROUP_COOLDOWN  = 90      # รอเต็ม window ให้ requests aged out
    RATE_LIMIT_RECOVERY = 90  # ถ้าโดน rate limit รอ 90s แล้ว retry
    MAX_RL_RETRIES  = 2

    def _build_page_url(p_num: int) -> str:
        u = re.sub(r"([?&]page=)\d+", rf"\g<1>{p_num}", base_url)
        if u == base_url:
            sep = "&" if "?" in base_url else "?"
            u = base_url + f"{sep}page={p_num}"
        return u

    def _fetch_batch(page_nums: list) -> list:
        """ส่ง parallel batch — คืน list ของ {page, items, rate_limited, error}"""
        urls = [_build_page_url(p) for p in page_nums]
        js = f"""async () => {{
            const urls = {json.dumps(urls)};
            const pages = {json.dumps(page_nums)};
            const results = await Promise.all(urls.map((u, i) =>
                fetch(u, {{credentials: 'include'}})
                    .then(async r => {{
                        const text = await r.text();
                        if (text.startsWith('Rate limit') || text.includes('rate limit')) {{
                            return {{page: pages[i], rate_limited: true}};
                        }}
                        try {{
                            const body = JSON.parse(text);
                            const items = body && body.data && body.data.data ? body.data.data : [];
                            return {{page: pages[i], items: items, code: body && body.response ? body.response.responseCode : null}};
                        }} catch(e) {{
                            return {{page: pages[i], error: e.toString().slice(0,80)}};
                        }}
                    }})
                    .catch(e => ({{page: pages[i], error: e.toString().slice(0,80)}}))
            ));
            return results;
        }}"""
        return page.evaluate(js)

    page_num = 2
    consecutive_empty = 0  # ถ้าได้ empty หลายหน้าติด → จบ (results หมด)

    while page_num <= max_pages:
        # สร้าง group ของ pages
        group_end = min(page_num + BATCH_SIZE * BATCHES_PER_GROUP, max_pages + 1)
        group_pages = list(range(page_num, group_end))
        if not group_pages:
            break

        # ส่งทีละ batch ภายใน group
        all_results = []
        for batch_start in range(0, len(group_pages), BATCH_SIZE):
            batch_pages = group_pages[batch_start:batch_start + BATCH_SIZE]
            try:
                results = _fetch_batch(batch_pages)
            except Exception as e:
                log(f"  Batch {batch_pages[0]}-{batch_pages[-1]} exception: {e}")
                return jobs, False
            all_results.extend(results)

            # ถ้าเจอ rate limit ใน batch นี้ → retry batch นั้นอีกครั้ง
            rl_pages = [r['page'] for r in results if r.get('rate_limited')]
            for retry_n in range(MAX_RL_RETRIES):
                if not rl_pages:
                    break
                log(f"  หน้า {rl_pages[0]}-{rl_pages[-1]} rate limit ({len(rl_pages)} หน้า) — รอ {RATE_LIMIT_RECOVERY}s แล้ว retry ({retry_n+1}/{MAX_RL_RETRIES})")
                time.sleep(RATE_LIMIT_RECOVERY)
                try:
                    retry_results = _fetch_batch(rl_pages)
                except Exception as e:
                    log(f"  retry exception: {e}")
                    break
                # อัปเดต all_results — แทนที่ rate_limited ด้วยผลใหม่
                retry_map = {r['page']: r for r in retry_results}
                for i, r in enumerate(all_results):
                    if r['page'] in retry_map:
                        all_results[i] = retry_map[r['page']]
                rl_pages = [r['page'] for r in retry_results if r.get('rate_limited')]

            if rl_pages:
                log(f"  หน้า {rl_pages} ยังโดน rate limit หลัง retry — ข้าม")

        # เรียง results ตาม page number
        all_results.sort(key=lambda r: r['page'])

        # ประมวลผล
        group_jobs_added = 0
        hit_cached = False
        for r in all_results:
            if r.get('error') or r.get('rate_limited'):
                continue
            items = r.get('items', [])
            if not items:
                consecutive_empty += 1
                continue
            consecutive_empty = 0
            for item in items:
                # INCREMENTAL: stop ถ้าเจอ cached jid → ทุกอันถัดไปเก่ากว่า
                if cached_jid and item.get("projectId") == cached_jid:
                    log(f"  ⚡ incremental: เจอ cached jid {cached_jid} หน้า {r['page']} → หยุด pagination")
                    hit_cached = True
                    break
                job = parse_api_item(item, keyword)
                if job:
                    jobs.append(job)
                    group_jobs_added += 1
            if hit_cached:
                break

        log(f"  Group หน้า {group_pages[0]}-{group_pages[-1]} ({len(group_pages)} หน้า): +{group_jobs_added} งาน, รวม {len(jobs)}")

        if hit_cached:
            break

        # ถ้าเจอ empty 5 หน้าติด → จบ (results หมดจริง)
        if consecutive_empty >= 5:
            log(f"  ผลลัพธ์หมด — หยุด pagination")
            break

        page_num += BATCH_SIZE * BATCHES_PER_GROUP

        # cooldown ระหว่าง group
        if page_num <= max_pages:
            time.sleep(GROUP_COOLDOWN)

    return jobs, False


def parse_api_item(item: dict, keyword: str) -> dict | None:
    """แปลง API item เป็น job dict"""
    project_id = item.get("projectId", "")
    title = item.get("projectName", "").strip()
    department = item.get("deptSubName", item.get("announceSubDesc", "")).strip()

    if not title or not project_id:
        return None

    # Format budget
    budget_raw = item.get("projectMoney", 0)
    try:
        budget = f"{float(budget_raw):,.2f}"
    except Exception:
        budget = str(budget_raw)

    # Format date (ISO → dd/mm/yyyy)
    announce_date = item.get("announceDate", "")
    publish_date = ""
    if announce_date:
        try:
            dt = datetime.fromisoformat(announce_date.replace("Z", "+00:00"))
            publish_date = dt.strftime("%d/%m/%Y")
        except Exception:
            publish_date = announce_date[:10]

    # Procurement type
    method_id = item.get("methodId", "")
    procurement_type = METHOD_MAP.get(method_id, f"method_{method_id}")

    # Extract location from title + department
    combined = title + " " + department
    province    = _extract_province(combined)
    district    = _extract_district(combined)
    subdistrict = _extract_subdistrict(combined, department)

    # Project status from flowName
    flow_name = item.get("flowName", "")
    project_status = FLOW_STATUS_MAP.get(flow_name, flow_name or "ไม่ทราบ")

    return {
        "job_id": project_id,
        "title": title[:300],
        "department": department[:150],
        "province": province,
        "district": district,
        "subdistrict": subdistrict,
        "procurement_type": procurement_type,
        "budget": budget,
        "publish_date": publish_date,
        "deadline": "",
        "tor_deadline": "",
        "tor_url": "",
        "project_status": project_status,
        "quantity_note": f"province:{keyword} | {flow_name}",
    }


_ZW = str.maketrans("", "", "​‌‍﻿­")


def _clean(text: str) -> str:
    return text.translate(_ZW)


# ================================================================
# DEADLINE FETCHING — PDF-based (วันยื่นซอง จาก ประกาศเชิญชวน PDF)
# ================================================================

_DEADLINE_KEYWORDS = [
    "ยื่นข้อเสนอ", "กำหนดยื่น", "เสนอราคา", "ยื่นซอง",
    "ปิดรับ", "สิ้นสุดรับ", "กำหนดส่ง",
]

_THAI_MONTH = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}
_THAI_DATE_RE = re.compile(
    r'(\d{1,2})\s+(' + '|'.join(_THAI_MONTH.keys()) + r')\s+(\d{4})'
)
_NUMERIC_DATE_RE = re.compile(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b')
_THAI_DIGITS_TABLE = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')

_PDF_BLOB_JS = """
async () => {
    const r = await fetch(document.URL);
    const blob = await r.blob();
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject("FileReader error");
        reader.readAsDataURL(blob);
    });
}
"""


def _dept_keyword(dept: str) -> str:
    for prefix in ["องค์การบริหารส่วนตำบล", "เทศบาลตำบล", "เทศบาลเมือง", "เทศบาลนคร"]:
        if dept.startswith(prefix):
            return dept[len(prefix):]
    words = dept.split()
    return words[-1] if words else dept


def _parse_deadline_from_pdf(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for pg in pdf.pages:
                text = (pg.extract_text() or "").translate(_THAI_DIGITS_TABLE)
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if any(kw in line for kw in _DEADLINE_KEYWORDS):
                        block = '\n'.join(lines[i:i+4])
                        m = _NUMERIC_DATE_RE.search(block)
                        if m:
                            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
                            return f"{d:02d}/{mo:02d}/{y}"
                        m2 = _THAI_DATE_RE.search(block)
                        if m2:
                            d = int(m2.group(1))
                            mo = _THAI_MONTH[m2.group(2)]
                            y = m2.group(3)
                            return f"{d:02d}/{mo:02d}/{y}"
    except Exception as e:
        log(f"    PDF parse: {e}")
    return ""


def fetch_deadline_via_pdf(page, pid: str, search_keyword: str) -> str:
    """
    ดึง deadline จาก PDF ประกาศเชิญชวน:
    1. ค้น search_keyword → หา row index ของ pid จาก API response
    2. คลิก btn-icon → detail page (Angular router)
    3. TABLE4: คลิก description icon ของ ประกาศเชิญชวน → TABLE1 โหลด
    4. TABLE1: คลิก file_download → blob page (new tab)
    5. อ่าน blob → pdfplumber → คืน deadline string
    """
    ctx = page.context
    captured_items = []

    def _on_resp(resp):
        if ("egp-atpj27-service" in resp.url and
                "announcement" in resp.url and
                "sumProject" not in resp.url):
            try:
                body = resp.json()
                items = body.get("data", {}).get("data", [])
                if items:
                    captured_items.extend(items)
            except Exception:
                pass

    page.on("response", _on_resp)

    search_input = None
    for sel in ["input[name*='keyword']", "input[placeholder*='ค้น']", "input[type='search']"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                search_input = el
                break
        except Exception:
            pass

    if not search_input:
        page.remove_listener("response", _on_resp)
        log("    ไม่พบ search input")
        return ""

    search_input.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.type(search_keyword, delay=50)
    time.sleep(0.5)

    try:
        with page.expect_response(
            lambda r: ("egp-atpj27-service" in r.url and
                       "announcement" in r.url and
                       "sumProject" not in r.url),
            timeout=20000
        ) as _ri:
            page.locator("button:has-text('ค้นหา')").first.click()
        _ri.value
    except Exception as e:
        log(f"    search error: {e}")
        page.remove_listener("response", _on_resp)
        return ""

    time.sleep(2)
    page.remove_listener("response", _on_resp)

    row_idx = next(
        (i for i, item in enumerate(captured_items)
         if str(item.get("tempProjectId") or item.get("projectId") or "") == pid),
        -1
    )
    if row_idx < 0:
        log(f"    pid {pid} ไม่อยู่ใน '{search_keyword}'")
        return ""

    log(f"    พบที่ row {row_idx}")

    try:
        btns = page.locator("table tbody tr a.btn-icon").all()
        if not btns:
            btns = page.locator("table tbody tr td:last-child a").all()
        if row_idx >= len(btns):
            log(f"    row_idx={row_idx} เกิน len(btns)={len(btns)}")
            return ""
        btns[row_idx].click()
    except Exception as e:
        log(f"    row click error: {e}")
        return ""

    time.sleep(8)

    clicked_t4 = False
    doc_used = ""
    try:
        rows_list = page.locator("table tr").all()
        for target in ["ประกาศเชิญชวน", "ร่างเอกสารประกวดราคา"]:
            for row in rows_list:
                try:
                    rt = row.inner_text(timeout=2000)
                except Exception:
                    continue
                if target in rt:
                    links = row.locator("a").all()
                    if links:
                        links[0].click()
                        clicked_t4 = True
                        doc_used = target
                        break
            if clicked_t4:
                break
    except Exception as e:
        log(f"    TABLE4 error: {e}")

    if not clicked_t4:
        log("    ไม่พบ ประกาศเชิญชวน หรือ ร่างเอกสารประกวดราคา — ข้าม")
        try:
            page.go_back(wait_until="load", timeout=15000)
            time.sleep(2)
        except Exception:
            pass
        return ""
    if doc_used != "ประกาศเชิญชวน":
        log(f"    fallback: ใช้ {doc_used}")

    time.sleep(6)

    deadline = ""
    if doc_used == "ร่างเอกสารประกวดราคา":
        # อ่านวันสิ้นสุดรับฟังคำวิจารณ์จาก inline table
        try:
            full_text = page.inner_text("body").translate(_THAI_DIGITS_TABLE)
            idx = full_text.find("วันที่สิ้นสุดรับฟังคำวิจารณ์")
            if idx >= 0:
                snippet = full_text[idx:idx+300]
                m = _NUMERIC_DATE_RE.search(snippet)
                if m:
                    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
                    deadline = f"{d:02d}/{mo:02d}/{y}"
                else:
                    m2 = _THAI_DATE_RE.search(snippet)
                    if m2:
                        d = int(m2.group(1))
                        mo = _THAI_MONTH[m2.group(2)]
                        y = m2.group(3)
                        deadline = f"{d:02d}/{mo:02d}/{y}"
            if not deadline:
                log("    ไม่พบวันที่สิ้นสุดรับฟังคำวิจารณ์ในตาราง")
        except Exception as e:
            log(f"    inline table read error: {e}")
    else:
        try:
            with ctx.expect_page(timeout=8000) as _npi:
                page.locator("a:has-text('file_download')").first.click()
            pdf_page = _npi.value
            pdf_page.wait_for_load_state("load", timeout=15000)
            time.sleep(2)

            log(f"    PDF URL: {pdf_page.url[:60]}")
            pdf_b64 = pdf_page.evaluate(_PDF_BLOB_JS)
            if pdf_b64:
                pdf_bytes = base64.b64decode(pdf_b64)
                log(f"    PDF {len(pdf_bytes)} bytes")
                deadline = _parse_deadline_from_pdf(pdf_bytes)

            try:
                pdf_page.close()
            except Exception:
                pass

        except Exception as e:
            log(f"    PDF page error: {e}")

    try:
        page.go_back(wait_until="load", timeout=15000)
        time.sleep(2)
    except Exception:
        try:
            page.goto(SEARCH_URL_PROCESS5, wait_until="load", timeout=30000)
            time.sleep(3)
        except Exception:
            pass

    return deadline, doc_used


def fetch_deadlines_for_active_jobs(page, jobs: list) -> None:
    """ดึง deadline/tor_deadline สำหรับ e-bidding กำลังประมูล — อัปเดต in-place"""
    active = [
        j for j in jobs
        if j.get("procurement_type") == "e-bidding"
        and j.get("project_status") == "กำลังประมูล"
    ]
    if not active:
        log("ไม่มีงาน e-bidding กำลังประมูล — ข้ามการดึง deadline")
        return

    log(f"\nดึง deadline สำหรับ {len(active)} งาน e-bidding กำลังประมูล...")

    for i, job in enumerate(active):
        pid = job["job_id"]
        log(f"  [{i+1}/{len(active)}] {pid} — {job['title'][:40]}...")
        try:
            dl, doc_type = fetch_deadline_via_pdf(page, pid, pid)
            if dl:
                if doc_type == "ร่างเอกสารประกวดราคา":
                    job["tor_deadline"] = dl
                    log(f"    ✅ สิ้นสุดรับฟังคำวิจารณ์: {dl}")
                else:
                    job["deadline"] = dl
                    log(f"    ✅ วันยื่นซอง: {dl}")
            else:
                log(f"    ❌ ไม่พบวันที่")
        except Exception as e:
            log(f"    error: {e}")
        if i < len(active) - 1:
            time.sleep(5)

    log("คืนหน้า search page...")
    try:
        page.goto(SEARCH_URL_PROCESS5, wait_until="load", timeout=30000)
        time.sleep(3)
    except Exception:
        pass


def _extract_district(text: str) -> str:
    text = _clean(text)
    m = re.search(r'อำเภอ\s*(\S+)', text)
    if m:
        return m.group(1).rstrip('.,)')
    m = re.search(r'\bอ\.\s*(\S+)', text)
    if m:
        return m.group(1).rstrip('.,)')
    return ""


def _extract_subdistrict(text: str, department: str = "") -> str:
    # ค้นหาจาก department ก่อน (ชื่อตั้งต้นด้วย อบต./เทศบาลตำบล/องค์การบริหารส่วนตำบล)
    for src in ([department, text] if department else [text]):
        src = _clean(src)
        for pat in [r'อบต\.\s*(\S+)', r'เทศบาลตำบล\s*(\S+)', r'ตำบล\s*(\S+)', r'\bต\.\s*(\S+)']:
            m = re.search(pat, src)
            if m:
                val = m.group(1).rstrip('.,)')
                if len(val) >= 2:
                    return val
    return ""


def _extract_province(text: str) -> str:
    provinces = [
        "กรุงเทพ", "เชียงใหม่", "เชียงราย", "ลำปาง", "ลำพูน", "แม่ฮ่องสอน",
        "พะเยา", "แพร่", "น่าน", "อุตรดิตถ์", "ตาก", "สุโขทัย", "กำแพงเพชร",
        "พิษณุโลก", "เพชรบูรณ์", "พิจิตร", "นครสวรรค์", "อุทัยธานี",
        "ชัยนาท", "สิงห์บุรี", "อ่างทอง", "พระนครศรีอยุธยา", "สระบุรี",
        "ลพบุรี", "นครนายก", "ปทุมธานี", "นนทบุรี", "สมุทรปราการ",
        "สมุทรสาคร", "สมุทรสงคราม", "นครปฐม", "ราชบุรี", "กาญจนบุรี",
        "สุพรรณบุรี", "เพชรบุรี", "ประจวบคีรีขันธ์", "ชลบุรี", "ระยอง",
        "จันทบุรี", "ตราด", "ฉะเชิงเทรา", "ปราจีนบุรี", "สระแก้ว",
        "นครราชสีมา", "บุรีรัมย์", "สุรินทร์", "ศรีสะเกษ", "อุบลราชธานี",
        "ยโสธร", "อำนาจเจริญ", "มุกดาหาร", "ร้อยเอ็ด", "กาฬสินธุ์",
        "สกลนคร", "นครพนม", "ขอนแก่น", "มหาสารคาม", "อุดรธานี",
        "หนองบัวลำภู", "หนองคาย", "บึงกาฬ", "เลย", "ชัยภูมิ",
        "สุราษฎร์ธานี", "นครศรีธรรมราช", "กระบี่", "พังงา", "ภูเก็ต",
        "ตรัง", "สตูล", "สงขลา", "พัทลุง", "ยะลา", "ปัตตานี", "นราธิวาส",
        "ระนอง", "ชุมพร",
    ]
    for p in provinces:
        if p in text:
            return p
    return ""


# ================================================================
# MAIN
# ================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-incremental", action="store_true",
                        help="Disable incremental scraping (always full scrape)")
    args = parser.parse_args()

    ensure_dirs()
    seen_ids = load_seen_ids()
    use_incremental = INCREMENTAL_DEFAULT and not args.no_incremental
    scraper_state = load_scraper_state() if use_incremental else None

    # Structured metrics + Discord anomaly alerts
    try:
        from scraper_metrics import ScraperMetrics
        metrics = ScraperMetrics()
    except Exception:
        metrics = None

    log("=" * 60)
    log("Sebastian Scraper — เริ่มต้น (process5 API)")
    log(f"Search terms: 2 จังหวัด + {len(DEPT_PROVINCE_MAP)} หน่วยงาน/ตำบล = {2 + len(DEPT_PROVINCE_MAP)} ตัวรวม")
    log(f"Filter keywords: {len(FILTER_KEYWORDS)} รายการ (ใช้กับทุก search term)")
    if use_incremental:
        cached_count = len(scraper_state.get("keyword_states", {})) if scraper_state else 0
        log(f"Incremental: ON ({cached_count} keywords cached) — 95% speedup on typical days")
    else:
        log("Incremental: OFF (full scrape)")
    log("=" * 60)

    all_new_jobs = []

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = new_stealth_page(browser)

        # โหลด process5 และรอ Turnstile ครั้งเดียว
        if not init_process5_page(page):
            log("ไม่สามารถโหลด process5 ได้ — หยุด")
            return

        # ---- Search loop: เฉพาะหน่วยงาน/ตำบลเท่านั้น ----
        # ตัด "นครพนม"/"บึงกาฬ" ออก (2026-05-17): ดึง 14,810 รายการแต่ใหม่ 0 + กิน Cloudflare quota
        # → scrape ระดับตำบล/หน่วยงานครอบคลุมพอแล้ว
        ALL_TERMS = [
            {"keyword": t, "expected_province": p} for t, p in DEPT_PROVINCE_MAP.items()
        ]

        consecutive_timeouts = 0
        for i, term_info in enumerate(ALL_TERMS):
            keyword        = term_info["keyword"]
            expected_prov  = term_info["expected_province"]
            is_dept        = expected_prov is not None

            # cooldown ก่อนค้น — เพิ่มจาก 5s → 15s ระหว่าง dept terms (2026-05-17 กัน Cloudflare)
            if i > 0:
                log(f"  รอ 15s ก่อนค้น '{keyword}' ...")
                time.sleep(15)

            # ถ้า timeout ติดกัน 2 ครั้ง → long cooldown + reinit + ตรวจ Cloudflare (2026-05-17)
            if consecutive_timeouts >= 2:
                log(f"  ⚠️ timeout ติดกัน {consecutive_timeouts} ครั้ง — long cooldown 300s + reinit")
                time.sleep(300)
                if not init_process5_page(page):
                    log("  ❌ reinit ไม่สำเร็จ (Cloudflare?) — หยุด scrape")
                    break
                consecutive_timeouts = 0

            kw_start = time.time()
            try:
                jobs, needs_reinit = search_keyword_process5(page, keyword, max_pages=9999, scraper_state=scraper_state)

                if needs_reinit and needs_reinit != "no_new":
                    if needs_reinit == "timeout":
                        consecutive_timeouts += 1
                        log(f"  Timeout — reinit แล้ว retry '{keyword}' ทันที (streak={consecutive_timeouts})")
                    else:
                        consecutive_timeouts = 0
                        log(f"  Rate limit — รอ 90s แล้ว retry '{keyword}'...")
                        time.sleep(90)
                    if init_process5_page(page):
                        try:
                            page.wait_for_selector("span.loading", state="hidden", timeout=15000)
                        except Exception:
                            pass
                        time.sleep(1)
                        jobs, _ = search_keyword_process5(page, keyword, max_pages=9999, scraper_state=scraper_state)
                    else:
                        log("  Reinit ไม่สำเร็จ — ข้าม")
                        jobs = []

                # ── Update incremental state with top item + content hash ──
                if scraper_state is not None and jobs:
                    raw_items = [
                        {"projectId": j.get("job_id", ""), "announceDate": j.get("publish_date", "")}
                        for j in jobs[:10]
                    ]
                    update_keyword_state(scraper_state, keyword, raw_items[0],
                                         page1_hash=compute_page_hash(raw_items))

                # กรอง FILTER_KEYWORDS ทุก term เหมือนกัน
                filtered = [j for j in jobs if is_relevant_job(j["title"])]

                # กรองจังหวัดเฉพาะ dept terms (จังหวัดไม่ต้องกรอง — ค้นชื่อจังหวัดตรงๆ อยู่แล้ว)
                province_skip = 0
                if is_dept:
                    province_ok = []
                    for j in filtered:
                        ext = j.get("province", "")
                        if ext == "" or ext == expected_prov:
                            if ext == "":
                                j["province"] = expected_prov
                            province_ok.append(j)
                        else:
                            province_skip += 1
                    filtered = province_ok

                new_jobs = [j for j in filtered if j["job_id"] not in seen_ids]
                seen_ids.update(j["job_id"] for j in new_jobs)
                all_new_jobs.extend(new_jobs)

                # search สำเร็จ (มีรายการ) → reset streak (2026-05-17)
                if jobs:
                    consecutive_timeouts = 0

                skip_str = f", ข้ามผิดจังหวัด {province_skip}" if province_skip else ""
                log(f"  '{keyword}': {len(jobs)} รายการ → กรองแล้ว {len(filtered)}{skip_str}, ใหม่ {len(new_jobs)}")

                if metrics:
                    metrics.record_keyword(
                        keyword,
                        duration_ms=int((time.time() - kw_start) * 1000),
                        items=len(jobs),
                        new_items=len(new_jobs),
                        pages_fetched=max(1, len(jobs) // 10),
                        incremental_skip=(needs_reinit == "no_new"),
                        status="success",
                    )

            except Exception as e:
                log(f"  '{keyword}' ERROR: {e} — ข้ามไปตัวถัดไป")
                try:
                    page.goto(SEARCH_URL_PROCESS5, wait_until="load", timeout=30000)
                    time.sleep(3)
                except Exception:
                    pass
            time.sleep(1)

        log(f"\nรวมงานใหม่ทั้งหมด: {len(all_new_jobs)} รายการ")

        # บันทึก seen IDs + incremental state
        save_seen_ids(seen_ids)
        if scraper_state is not None:
            save_scraper_state(scraper_state)
            log(f"  saved scraper_state ({len(scraper_state.get('keyword_states', {}))} keywords cached)")

        # Finalize metrics + Discord anomaly alert
        if metrics:
            summary, anomalies = metrics.finalize(send_discord=True)
            log(f"\nMetrics: {summary['total_duration_min']:.1f}min | {summary['total_items']} items | skipped {summary['incremental_skipped']}")
            if anomalies:
                log(f"⚠️ Anomalies: {anomalies}")

        # ดึง deadline สำหรับ e-bidding กำลังประมูล
        if all_new_jobs:
            fetch_deadlines_for_active_jobs(page, all_new_jobs)

        # บันทึก local JSON backup
        if all_new_jobs:
            backup_path = Path(__file__).parent.parent / "data" / f"jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            backup_path.write_text(
                json.dumps(all_new_jobs, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            log(f"Backup: {backup_path}")

            # บันทึกลง Google Sheets
            log("กำลังบันทึกลง Google Sheets...")
            try:
                append_jobs_to_sheet(all_new_jobs)
            except Exception as e:
                log(f"Sheets error: {e} — ข้อมูลอยู่ใน backup JSON")

        log("เสร็จสิ้น")
        page.close()


if __name__ == "__main__":
    main()
