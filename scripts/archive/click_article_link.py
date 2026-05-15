"""
click_article_link.py — คลิก "article" link ใน search result row
เพื่อดักจับ API calls สำหรับ announcement detail

วิธีใช้: python scripts/click_article_link.py
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "article_click"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

all_responses = []


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
        all_responses.append({
            "ts": datetime.now().isoformat(),
            "status": resp.status,
            "url": url,
            "body_json": body_json,
            "body_text": body[:500] if not body_json else None,
        })
        log(f"  → {resp.status} {url.replace(PROCESS5_BASE,'')[:90]}")
    except Exception:
        pass


with sync_playwright() as p:
    log("เชื่อมต่อ...")
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
            log(f"  ✓ enabled")
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

    # Search
    search_items = []
    def capture_req(req):
        url = req.url
        if "egp-atpj27-service" in url and "announcement" in url and "sumProject" not in url and "cfturnstile" not in url:
            pass

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
            search_items = body.get("data", {}).get("data", [])
            log(f"✓ {len(search_items)} results")
    except Exception as e:
        log(f"search error: {e}")

    time.sleep(2)
    page.screenshot(path=str(DEBUG_DIR / "01_search.png"), timeout=10000)

    # ===== หา "article" links =====
    log("\n--- หา 'article' links ใน search results ---")
    article_links = page.query_selector_all("a:has-text('article')")
    log(f"  พบ {len(article_links)} article links")

    if not article_links:
        # ลอง mat-icon
        article_links = page.query_selector_all("mat-icon:has-text('article')")
        log(f"  พบ mat-icon: {len(article_links)}")
        # ถ้าเป็น mat-icon ให้คลิก parent <a>
        if article_links:
            parents = [page.evaluate("(el) => el.closest('a, button, [role=\"button\"]', el) || el", a) for a in article_links]

    before_click = len(all_responses)
    url_before = page.url

    if article_links:
        target = article_links[0]
        # Get the row text context
        try:
            row_el = page.evaluate("(el) => el.closest('tr') ? el.closest('tr').innerText.substring(0, 80) : 'no tr'", target)
            log(f"  คลิก link ใน row: {row_el}")
        except Exception:
            pass

        log(f"  คลิก article link[0]...")
        try:
            target.click(force=True, timeout=5000)
            log(f"  ✓ คลิกแล้ว")
        except Exception as e:
            log(f"  click error: {e}")
            # Try JS click
            try:
                page.evaluate("(el) => el.click()", target)
                log(f"  ✓ JS click")
            except Exception as e2:
                log(f"  JS click error: {e2}")

        # รอ API calls
        time.sleep(0.5)
        url_after_500ms = page.url
        log(f"  URL after 500ms: {url_after_500ms.replace(PROCESS5_BASE,'')}")

        time.sleep(3)
        url_after_3s = page.url
        log(f"  URL after 3.5s: {url_after_3s.replace(PROCESS5_BASE,'')}")

        page.screenshot(path=str(DEBUG_DIR / "02_after_click_3s.png"), timeout=10000)

        time.sleep(5)
        log(f"  URL after 8.5s: {page.url.replace(PROCESS5_BASE,'')}")
        page.screenshot(path=str(DEBUG_DIR / "03_after_click_8s.png"), timeout=10000)

        # บันทึก HTML หลัง click
        try:
            html_after = page.content()
            (DEBUG_DIR / "after_click.html").write_text(html_after, encoding="utf-8")
        except Exception:
            pass

    else:
        log("ไม่พบ article links")

    # ===== วิเคราะห์ =====
    new_resps = all_responses[before_click:]
    log(f"\n=== API calls หลัง click: {len(new_resps)} ===")
    for r in new_resps:
        url_s = r["url"].replace(PROCESS5_BASE, "")
        log(f"  {r['status']} {url_s[:90]}")
        if r.get("body_json"):
            d = r["body_json"]
            if isinstance(d, dict):
                rc = d.get("response", {}).get("responseCode") if isinstance(d.get("response"), dict) else None
                data = d.get("data")
                if isinstance(data, list) and data:
                    log(f"    ★★★ data[{len(data)}] — keys: {list(data[0].keys()) if isinstance(data[0], dict) else '?'}")
                    for it in data[:3]:
                        if isinstance(it, dict):
                            log(f"      item: {json.dumps(it, ensure_ascii=False)[:200]}")
                elif isinstance(data, dict):
                    log(f"    data keys: {list(data.keys())}")
                elif isinstance(data, str):
                    log(f"    data: {data[:60]}")

    page.remove_listener("response", on_response)
    page.close()

# บันทึก
output = {
    "all_responses": all_responses,
    "new_responses": new_resps if article_links else [],
}
out_path = DEBUG_DIR / "result.json"
out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"\nบันทึก: {out_path}")
