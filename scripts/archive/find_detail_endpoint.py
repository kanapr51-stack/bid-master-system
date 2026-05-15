"""
find_detail_endpoint.py — ค้นหา endpoint ที่ใช้ดึง file list สำหรับ announcement
ใช้ mechanism เดียวกับ scraper (proven to work)

วิธีใช้:
  1. Chrome เปิด + --remote-debugging-port=9222
  2. python scripts/find_detail_endpoint.py
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROCESS5_BASE = "https://process5.gprocurement.go.th"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "find_endpoint"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

all_api_responses = []    # ALL responses after detail navigation
detail_started_at = 0     # index in all_api_responses when detail click happened


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def on_response(resp):
    url = resp.url
    if any(x in url for x in [".js", ".css", ".png", ".ico", ".woff", ".svg", ".map", "fonts"]):
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
            "ts": datetime.now().isoformat(),
            "status": resp.status,
            "url": url,
            "body_len": len(body),
            "body_json": body_json,
            "body_text": body[:500] if not body_json else None,
        })
    except Exception:
        all_api_responses.append({"status": resp.status, "url": url})


with sync_playwright() as p:
    log("เชื่อมต่อ Chrome...")
    for attempt in range(15):
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            log("เชื่อมต่อสำเร็จ")
            break
        except Exception:
            log(f"  รอ... ({attempt+1}/15)")
            time.sleep(2)

    page = browser.contexts[0].new_page()
    page.on("response", on_response)

    # ===== STEP 1: navigate + รอ Turnstile =====
    log(f"\n--- Step 1: Navigate + รอ Turnstile ---")
    page.goto(SEARCH_URL, wait_until="load", timeout=45000)
    time.sleep(3)

    log("  รอ search button enabled...")
    deadline = time.time() + 40
    btn_ready = False
    while time.time() < deadline:
        try:
            btn = page.query_selector("button:has-text('ค้นหา')")
            if btn and btn.is_enabled():
                btn_ready = True
                log(f"  ✓ button enabled!")
                break
        except Exception:
            pass
        time.sleep(0.8)

    if not btn_ready:
        log("  ⚠ button ยัง disabled — ดำเนินการต่อ")

    page.screenshot(path=str(DEBUG_DIR / "01_ready.png"), timeout=10000)

    # ===== STEP 2: Search using keyboard (same as scraper) =====
    log(f"\n--- Step 2: Search 'ถนนคอนกรีต' ---")

    inp = page.query_selector("input[name='keywordSearch']")
    if inp:
        inp.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        time.sleep(0.3)
        page.keyboard.type("ถนนคอนกรีต", delay=80)
        time.sleep(0.5)
        log("  พิมพ์ keyword แล้ว")

    search_url_captured = []
    search_items = []

    def capture_request(req):
        url = req.url
        if ("egp-atpj27-service" in url and "announcement" in url
                and "sumProject" not in url and "cfturnstile" not in url):
            search_url_captured.append(url)

    page.on("request", capture_request)

    try:
        with page.expect_response(
            lambda r: (
                "egp-atpj27-service" in r.url and
                "announcement" in r.url and
                "sumProject" not in r.url and
                "cfturnstile" not in r.url
            ),
            timeout=35000
        ) as resp_info:
            try:
                page.locator("button:has-text('ค้นหา')").first.click(timeout=8000)
            except Exception:
                log("  click failed — ลอง Enter")
                if inp:
                    inp.press("Enter")

        search_resp = resp_info.value
        body = search_resp.json()
        rc = body.get("response", {}).get("responseCode")
        log(f"  Search response code: {rc}")

        if rc == "0":
            items = body.get("data", {}).get("data", [])
            search_items = items
            log(f"  ✓ พบ {len(items)} results")
            if items:
                log(f"    First: {items[0].get('projectName', '')[:60]}")

    except PWTimeout:
        log("  ✗ timeout รอ search response")
    except Exception as e:
        log(f"  ✗ search error: {e}")

    page.remove_listener("request", capture_request)
    page.screenshot(path=str(DEBUG_DIR / "02_search_results.png"), timeout=10000)

    # ===== STEP 3: คลิก result row =====
    log(f"\n--- Step 3: คลิก result row ---")
    time.sleep(2)  # รอ render

    detail_started_at = len(all_api_responses)
    url_before_click = page.url
    url_after_click = page.url

    rows = page.query_selector_all("tbody tr")
    log(f"  พบ {len(rows)} rows")

    clicked = False
    for i, row in enumerate(rows[:10]):
        text = (row.inner_text() or "").strip()
        log(f"  row[{i}]: {text[:80]}")
        if "E1530" in text or "ข้อความปฎิเสธ" in text or len(text) < 10:
            continue
        # คลิก
        try:
            row.click(force=True, timeout=5000)
            time.sleep(5)
            url_after_click = page.url
            log(f"  ✓ คลิกแล้ว — URL: {url_after_click.replace(PROCESS5_BASE,'')}")
            clicked = True
            break
        except Exception as e:
            log(f"  row click error: {e}")
            # ลองคลิก cell แทน row
            cells = row.query_selector_all("td")
            for cell in cells[:3]:
                try:
                    cell.click(force=True, timeout=3000)
                    time.sleep(5)
                    url_after_click = page.url
                    clicked = True
                    break
                except Exception:
                    pass
            if clicked:
                break

    if not clicked:
        log("  ⚠ ไม่ได้คลิก row — ลอง JavaScript click")
        try:
            result = page.evaluate("""
            () => {
                const rows = document.querySelectorAll('tbody tr');
                for (const row of rows) {
                    const text = row.innerText.trim();
                    if (text.length > 10 && !text.includes('E1530') && !text.includes('ปฎิเสธ')) {
                        row.click();
                        return {clicked: true, text: text.substring(0, 80)};
                    }
                }
                return {clicked: false, rows: rows.length};
            }
            """)
            log(f"  JS click result: {result}")
            time.sleep(5)
            url_after_click = page.url
        except Exception as e:
            log(f"  JS click error: {e}")

    # รออีก 5s สำหรับ lazy loads
    time.sleep(5)
    page.screenshot(path=str(DEBUG_DIR / "03_after_click.png"), timeout=10000)
    log(f"  URL สุดท้าย: {page.url.replace(PROCESS5_BASE, '')}")

    # ===== STEP 4: บันทึก HTML =====
    try:
        html = page.content()
        (DEBUG_DIR / "page_after_click.html").write_text(html, encoding="utf-8")
        log(f"  บันทึก HTML ({len(html):,} chars)")
    except Exception:
        pass

    page.remove_listener("response", on_response)
    page.close()

# ===== วิเคราะห์ผล =====
new_responses = all_api_responses[detail_started_at:]
log(f"\n{'='*60}")
log(f"responses ก่อน click: {detail_started_at}")
log(f"responses หลัง click: {len(new_responses)}")

log("\n=== ALL responses หลัง click ===")
for r in new_responses:
    url_short = r["url"].replace(PROCESS5_BASE, "")
    log(f"  {r['status']} {url_short[:90]}")
    if r.get("body_json"):
        d = r["body_json"]
        if isinstance(d, dict):
            rc = d.get("response", {}).get("responseCode") if isinstance(d.get("response"), dict) else None
            data = d.get("data")
            if isinstance(data, list) and data:
                log(f"       ★★★ data[{len(data)}] items — keys: {list(data[0].keys()) if isinstance(data[0], dict) else '?'}")
            elif isinstance(data, dict):
                log(f"       data keys: {list(data.keys())}")
            elif isinstance(data, str):
                log(f"       data: {data[:60]}")
            if rc:
                log(f"       responseCode: {rc}")

log("\n=== ค้นหา file/document endpoints ===")
for r in all_api_responses:
    url = r["url"]
    if any(x in url.lower() for x in ["file", "doc", "attach", "download", "upload", "aobj", "adoc"]):
        log(f"  {r['status']} {url.replace(PROCESS5_BASE,'')}")

# บันทึกผล
output = {
    "timestamp": datetime.now().isoformat(),
    "search_count": len(search_items),
    "url_before_click": url_before_click,
    "url_after_click": url_after_click,
    "all_api_count": len(all_api_responses),
    "new_responses": new_responses,
    "all_responses": all_api_responses,
}
out_path = DEBUG_DIR / "result.json"
out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"\nบันทึก: {out_path}")
