"""
spy_detail_api.py — ดักจับ ALL API calls เมื่อคลิก announcement ใน search results
เพื่อหา endpoint ที่ใช้ดึง document/file list

วิธีใช้:
  1. เปิด Chrome: Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\\Temp\\ChromeDebug"
  2. python scripts/spy_detail_api.py
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "spy"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ใช้ keyword ที่รู้ว่ามีงานก่อสร้าง
SEARCH_KEYWORD = "บ้านแพง"

all_responses = []
all_requests  = []


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def on_request(req):
    url = req.url
    if any(x in url for x in [".js", ".css", ".png", ".ico", ".woff", ".svg", ".map"]):
        return
    if "gprocurement.go.th" in url:
        all_requests.append({
            "method": req.method,
            "url": url,
            "post_data": (req.post_data or "")[:300],
        })


def on_response(resp):
    url = resp.url
    if any(x in url for x in [".js", ".css", ".png", ".ico", ".woff", ".svg", ".map"]):
        return
    if "gprocurement.go.th" not in url:
        return
    try:
        body = resp.text()
        is_json = resp.headers.get("content-type", "").startswith("application/json")
        body_json = None
        if is_json and len(body) < 50000:
            try:
                body_json = json.loads(body)
            except Exception:
                pass
        all_responses.append({
            "status": resp.status,
            "url": url,
            "body_len": len(body),
            "body_json": body_json,
            "body_text": body[:300] if not body_json else None,
        })
        log(f"  → {resp.status} {url[:90]}")
    except Exception as e:
        all_responses.append({"status": resp.status, "url": url, "error": str(e)})


with sync_playwright() as p:
    log("เชื่อมต่อ Chrome CDP...")
    for attempt in range(15):
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            log("เชื่อมต่อสำเร็จ")
            break
        except Exception:
            log(f"  รอ Chrome... ({attempt+1}/15)")
            time.sleep(2)

    page = browser.contexts[0].new_page()
    page.on("request",  on_request)
    page.on("response", on_response)

    # ===== PHASE 1: ไป search page =====
    log(f"\n--- Phase 1: navigate to {SEARCH_URL}")
    page.goto(SEARCH_URL, wait_until="load", timeout=45000)
    time.sleep(5)
    page.screenshot(path=str(DEBUG_DIR / "01_search_page.png"))
    log(f"URL ปัจจุบัน: {page.url}")

    # ===== PHASE 2: รอ Turnstile bypass =====
    log("\n--- Phase 2: รอ Turnstile bypass token...")
    turnstile_done = False
    for wait_i in range(30):
        time.sleep(2)
        # ตรวจว่า search button enabled หรือยัง
        try:
            btn = page.query_selector("button[type='submit'], button:has-text('ค้นหา')")
            if btn:
                is_disabled = page.evaluate("(el) => el.disabled", btn)
                if not is_disabled:
                    log(f"  Search button enabled! (รอ {(wait_i+1)*2}s)")
                    turnstile_done = True
                    break
        except Exception:
            pass
        log(f"  รอ... ({(wait_i+1)*2}s)")
    page.screenshot(path=str(DEBUG_DIR / "02_after_turnstile.png"))

    # ===== PHASE 3: พิมพ์ keyword + ค้นหา =====
    log(f"\n--- Phase 3: ค้นหา '{SEARCH_KEYWORD}'")
    try:
        # หา input field สำหรับ keyword search
        inputs = page.query_selector_all("input[type='text'], input[type='search'], input:not([type])")
        log(f"  พบ input fields: {len(inputs)}")
        for inp in inputs:
            placeholder = inp.get_attribute("placeholder") or ""
            name = inp.get_attribute("name") or ""
            if any(x in (placeholder + name).lower() for x in ["ค้นหา", "keyword", "search", "ชื่อ"]):
                log(f"  คลิก input: placeholder='{placeholder}' name='{name}'")
                inp.click()
                time.sleep(0.5)
                # clear first
                inp.press("Control+a")
                inp.press("Delete")
                time.sleep(0.3)
                inp.type(SEARCH_KEYWORD, delay=80)
                time.sleep(0.5)
                break
        else:
            # fallback: use first visible text input
            if inputs:
                inputs[0].click()
                inputs[0].type(SEARCH_KEYWORD, delay=80)

        page.screenshot(path=str(DEBUG_DIR / "03_typed_keyword.png"))

        # กด search button
        btn = page.query_selector("button[type='submit']")
        if not btn:
            btn = page.query_selector("button:has-text('ค้นหา')")
        if btn:
            log("  กดปุ่มค้นหา")
            btn.click()
        else:
            log("  ไม่พบปุ่มค้นหา — กด Enter แทน")
            page.keyboard.press("Enter")

        time.sleep(5)
        page.screenshot(path=str(DEBUG_DIR / "04_search_results.png"))
        log(f"  URL หลัง search: {page.url}")

    except Exception as e:
        log(f"  ค้นหา error: {e}")
        page.screenshot(path=str(DEBUG_DIR / "04_search_error.png"))

    # ===== PHASE 4: คลิก result row แรก =====
    log("\n--- Phase 4: คลิก result row แรก")
    # บันทึก responses ก่อนคลิก
    before_click_count = len(all_responses)
    url_before_click = page.url

    try:
        # หา rows ใน table
        rows = page.query_selector_all("tr[class*='row'], tr[ng-click], tbody tr, mat-row, [role='row']")
        log(f"  พบ rows: {len(rows)}")

        if rows:
            # คลิก row แรกที่มี text
            for row in rows[:5]:
                text = (row.inner_text() or "").strip()
                if text and len(text) > 10:
                    log(f"  คลิก row: {text[:80]}")
                    row.click()
                    time.sleep(5)
                    break
        else:
            # ลองคลิก link ใน table
            links = page.query_selector_all("table a, .result-row, [class*='announcement'] a")
            log(f"  พบ links: {len(links)}")
            if links:
                log(f"  คลิก link: {links[0].inner_text()[:60]}")
                links[0].click()
                time.sleep(5)

        url_after_click = page.url
        log(f"  URL หลัง click: {url_after_click}")
        page.screenshot(path=str(DEBUG_DIR / "05_after_click.png"))

    except Exception as e:
        log(f"  click error: {e}")
        page.screenshot(path=str(DEBUG_DIR / "05_click_error.png"))

    # ===== PHASE 5: รอ API responses หลัง click =====
    log("\n--- Phase 5: รออีก 5s สำหรับ lazy API calls")
    time.sleep(5)
    page.screenshot(path=str(DEBUG_DIR / "06_final.png"))
    log(f"  URL สุดท้าย: {page.url}")

    # ===== บันทึก HTML ของหน้า =====
    try:
        html = page.content()
        (DEBUG_DIR / "page_html.html").write_text(html, encoding="utf-8")
        log(f"  บันทึก page HTML ({len(html):,} chars)")
    except Exception:
        pass

    # ===== ดู anchor tags ที่เกี่ยวกับ file =====
    try:
        anchors = page.query_selector_all("a[href]")
        file_links = []
        for a in anchors:
            href = a.get_attribute("href") or ""
            text = (a.inner_text() or "").strip()
            if any(x in href.lower() for x in [".pdf", ".xlsx", ".xls", "download", "file", "hashTag"]):
                file_links.append({"text": text, "href": href})
        log(f"  พบ file links: {len(file_links)}")
        for fl in file_links[:10]:
            log(f"    {fl['text'][:40]} → {fl['href'][:80]}")
    except Exception as e:
        log(f"  anchor scan error: {e}")

    page.close()

# ===== วิเคราะห์ผลลัพธ์ =====
log("\n" + "="*60)
log(f"รวม requests: {len(all_requests)}")
log(f"รวม responses: {len(all_responses)}")

# หา responses ที่เกิดขึ้นหลัง click
new_responses = all_responses[before_click_count:]
log(f"responses หลัง click: {len(new_responses)}")

print("\n=== ALL API CALLS (after click) ===")
for r in new_responses:
    print(f"  {r['status']} {r['url'][:100]}")
    if r.get("body_json"):
        keys = list(r["body_json"].keys()) if isinstance(r["body_json"], dict) else "list"
        print(f"       JSON keys: {keys}")

print("\n=== ค้นหา file/document endpoints ===")
for r in all_responses:
    url = r["url"]
    if any(x in url.lower() for x in ["file", "doc", "attach", "download", "upload", "adoc", "aobj"]):
        print(f"  {r['status']} {url}")
        if r.get("body_json"):
            d = r["body_json"]
            if isinstance(d, dict):
                print(f"       keys: {list(d.keys())}")
                data = d.get("data")
                if isinstance(data, list):
                    print(f"       data[]: {len(data)} items")
                    if data:
                        print(f"       data[0] keys: {list(data[0].keys()) if isinstance(data[0], dict) else data[0]}")

# บันทึกทุกอย่าง
output = {
    "timestamp": datetime.now().isoformat(),
    "url_before_click": url_before_click,
    "url_after_click": page.url if False else "see log",
    "all_requests": all_requests,
    "all_responses": all_responses,
    "new_responses_after_click": new_responses,
}
out_path = DEBUG_DIR / "spy_output.json"
out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"\nบันทึก: {out_path}")
log("ดูภาพ screenshots ใน: " + str(DEBUG_DIR))
