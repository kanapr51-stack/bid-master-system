"""
read_table_html.py — ดูโครงสร้าง HTML ของ search results table
เพื่อหา link/button สำหรับ document download

วิธีใช้: python scripts/read_table_html.py
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROCESS5_BASE = "https://process5.gprocurement.go.th"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "read_table"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

all_api_responses = []


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def on_response(resp):
    url = resp.url
    if any(x in url for x in [".js", ".css", ".png", ".ico", ".woff", ".svg", ".map"]):
        return
    if "gprocurement.go.th" not in url:
        return
    try:
        body = resp.text()
        body_json = None
        if "json" in resp.headers.get("content-type", ""):
            try:
                body_json = json.loads(body)
            except Exception:
                pass
        all_api_responses.append({
            "url": url,
            "status": resp.status,
            "body_json": body_json,
        })
        log(f"  API: {resp.status} {url.replace(PROCESS5_BASE,'')[:90]}")
    except Exception:
        pass


with sync_playwright() as p:
    log("เชื่อมต่อ Chrome...")
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    log("เชื่อมต่อสำเร็จ")

    page = browser.contexts[0].new_page()
    page.on("response", on_response)

    # Navigate
    page.goto(SEARCH_URL, wait_until="load", timeout=45000)
    time.sleep(3)

    # รอ button
    log("รอ search button...")
    deadline = time.time() + 40
    while time.time() < deadline:
        btn = page.query_selector("button:has-text('ค้นหา')")
        if btn and btn.is_enabled():
            log("  ✓ enabled")
            break
        time.sleep(0.8)

    # Type keyword
    inp = page.query_selector("input[name='keywordSearch']")
    if inp:
        inp.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        time.sleep(0.3)
        page.keyboard.type("ถนนคอนกรีต", delay=80)
        time.sleep(0.5)

    search_items = []
    search_url_used = []

    def capture_req(req):
        url = req.url
        if ("egp-atpj27-service" in url and "announcement" in url
                and "sumProject" not in url and "cfturnstile" not in url):
            search_url_used.append(url)

    page.on("request", capture_req)

    try:
        with page.expect_response(
            lambda r: "egp-atpj27-service" in r.url and "announcement" in r.url
                      and "sumProject" not in r.url and "cfturnstile" not in r.url,
            timeout=35000
        ) as resp_info:
            try:
                page.locator("button:has-text('ค้นหา')").first.click(timeout=8000)
            except Exception:
                if inp:
                    inp.press("Enter")

        body = resp_info.value.json()
        if body.get("response", {}).get("responseCode") == "0":
            items = body.get("data", {}).get("data", [])
            search_items = items
            log(f"✓ search: {len(items)} results")
    except Exception as e:
        log(f"search error: {e}")

    page.remove_listener("request", capture_req)
    time.sleep(3)  # รอ render

    # ===== บันทึก HTML ทันทีหลัง search =====
    page.screenshot(path=str(DEBUG_DIR / "01_search_results.png"), timeout=10000)
    html = page.content()
    (DEBUG_DIR / "after_search.html").write_text(html, encoding="utf-8")
    log(f"บันทึก HTML หลัง search: {len(html):,} chars")

    # ===== ดู HTML ของ tbody ทั้งหมด =====
    tbodies = re.findall(r'<tbody[^>]*>.*?</tbody>', html, re.DOTALL)
    log(f"พบ {len(tbodies)} tbody")
    for i, tbody in enumerate(tbodies):
        rows = re.findall(r'<tr[^>]*>.*?</tr>', tbody, re.DOTALL)
        log(f"\n--- tbody[{i}]: {len(rows)} rows ---")
        for j, row in enumerate(rows[:3]):
            text = re.sub(r'<[^>]+>', ' ', row).strip()
            text = re.sub(r'\s+', ' ', text)
            # Find links
            links = re.findall(r'href=["\']([^"\']+)["\']', row)
            log(f"  row[{j}]: {text[:120]}")
            if links:
                log(f"    links: {links[:5]}")

    # ===== ดู Angular components ที่มี click handlers =====
    log("\n--- Elements with click handlers ---")
    clickables = page.query_selector_all("[click], [ng-click], [data-action]")
    log(f"  ng-click elements: {len(clickables)}")

    # ===== ดูว่า row มี button หรือ link ข้างใน =====
    log("\n--- ตรวจสอบ rows สำหรับ buttons/links ---")
    all_rows = page.query_selector_all("tbody tr")
    log(f"  ทั้งหมด: {len(all_rows)} rows")
    for i, row in enumerate(all_rows):
        # หา buttons ใน row
        btns = row.query_selector_all("button, a")
        if btns:
            for b in btns:
                text = (b.inner_text() or "").strip()
                href = b.get_attribute("href") or ""
                tag = b.evaluate("el => el.tagName")
                log(f"  row[{i}] has {tag}: text='{text[:40]}' href='{href[:60]}'")

    # ===== ลองคลิก row ที่ถูกต้อง และ capture HTML ทันที =====
    if search_items:
        log("\n--- ลองคลิก row และ capture API calls ทันที ---")
        before_click = len(all_api_responses)

        # หา row ที่มีข้อมูลจริง (ไม่ใช่ error)
        actual_rows = page.query_selector_all("tbody tr")
        target_row = None
        for row in actual_rows:
            text = (row.inner_text() or "").strip()
            if len(text) > 20 and "E1530" not in text and "ปฎิเสธ" not in text and "ไม่มีเอกสาร" not in text:
                target_row = row
                log(f"  เป้าหมาย: {text[:80]}")
                break

        if target_row:
            # เพิ่ม event listener ก่อน click
            js_intercept = """
            window._clickEvents = [];
            window._origFetch = window.fetch;
            window.fetch = function(url, opts) {
                window._clickEvents.push({type: 'fetch', url: typeof url === 'string' ? url : url.url, method: (opts && opts.method) || 'GET'});
                return window._origFetch.apply(this, arguments);
            };
            """
            page.evaluate(js_intercept)

            target_row.click(force=True, timeout=5000)
            time.sleep(0.3)  # รอแค่ 300ms แล้วเก็บข้อมูล

            # เก็บ URL ของ Angular router
            url_now = page.url
            log(f"  URL หลัง click: {url_now.replace(PROCESS5_BASE,'')}")

            # เก็บ captured fetch calls
            time.sleep(2)
            click_events = page.evaluate("window._clickEvents || []")
            log(f"  Fetch calls หลัง click: {len(click_events)}")
            for ev in click_events[:10]:
                log(f"    {ev['method']} {ev['url'][:100]}")

            # Screenshot ทันที
            page.screenshot(path=str(DEBUG_DIR / "02_immediately_after_click.png"), timeout=5000)
            html_after = page.content()
            (DEBUG_DIR / "immediately_after_click.html").write_text(html_after, encoding="utf-8")

            # รออีก 3s
            time.sleep(3)
            page.screenshot(path=str(DEBUG_DIR / "03_3s_after_click.png"), timeout=5000)

            new_resps = all_api_responses[before_click:]
            log(f"  API calls หลัง click: {len(new_resps)}")
            for r in new_resps:
                log(f"    {r['status']} {r['url'].replace(PROCESS5_BASE,'')[:80]}")
                if r.get("body_json"):
                    d = r["body_json"]
                    if isinstance(d, dict) and isinstance(d.get("data"), list):
                        log(f"      ★ data[{len(d['data'])}] items")

    page.remove_listener("response", on_response)
    page.close()

log("\nเสร็จสิ้น")
