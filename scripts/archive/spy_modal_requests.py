"""
spy_modal_requests.py — ดักจับ request headers และ response ของ modal API calls

วิธีใช้: python scripts/spy_modal_requests.py
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "spy_modal"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ID = "69049267400"

all_reqs = []
all_resps = []


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def on_request(req):
    url = req.url
    if any(x in url for x in [".js", ".css", ".png", ".ico", ".woff", ".svg", ".map"]):
        return
    if "gprocurement.go.th" not in url:
        return
    all_reqs.append({
        "ts": datetime.now().isoformat(),
        "method": req.method,
        "url": url,
        "headers": dict(req.headers),
        "post_data": req.post_data,
    })
    log(f"  REQ: {req.method} {url.replace(PROCESS5_BASE,'')[:90]}")


def on_response(resp):
    url = resp.url
    if any(x in url for x in [".js", ".css", ".png", ".ico", ".woff", ".svg", ".map"]):
        return
    if "gprocurement.go.th" not in url:
        return
    try:
        body = resp.body()  # bytes
        body_json = None
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            try:
                body_json = json.loads(body.decode("utf-8"))
            except Exception:
                pass
        all_resps.append({
            "ts": datetime.now().isoformat(),
            "status": resp.status,
            "url": url,
            "content_type": ct,
            "body_json": body_json,
            "body_bytes_len": len(body),
            "body_text": body[:500].decode("utf-8", errors="replace") if not body_json else None,
        })
        log(f"  RESP: {resp.status} {url.replace(PROCESS5_BASE,'')[:90]} ({len(body)} bytes, {ct[:30]})")
    except Exception as e:
        log(f"  RESP error: {e}")


with sync_playwright() as p:
    log("เชื่อมต่อ Chrome...")
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    log("เชื่อมต่อสำเร็จ")

    page = browser.contexts[0].new_page()
    page.on("request", on_request)
    page.on("response", on_response)

    # Navigate to search page for cookies
    page.goto(SEARCH_URL, wait_until="load", timeout=45000)
    time.sleep(3)
    log("รอ search button...")
    deadline = time.time() + 40
    while time.time() < deadline:
        btn = page.query_selector("button:has-text('ค้นหา')")
        if btn and btn.is_enabled():
            log("  ✓ enabled")
            break
        time.sleep(0.8)

    # Search
    inp = page.query_selector("input[name='keywordSearch']")
    if inp:
        inp.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        time.sleep(0.3)
        page.keyboard.type("ก่อสร้างถนน", delay=80)
        time.sleep(0.5)

    try:
        with page.expect_response(
            lambda r: "egp-atpj27-service" in r.url and "announcement" in r.url
                      and "sumProject" not in r.url and "cfturnstile" not in r.url,
            timeout=35000
        ) as resp_info:
            page.locator("button:has-text('ค้นหา')").first.click(timeout=8000)
        body = resp_info.value.json()
        items = body.get("data", {}).get("data", [])
        log(f"  search: {len(items)} results")
    except Exception as e:
        log(f"  search error: {e}")

    time.sleep(2)

    # Click article link for project
    article_links = page.query_selector_all("a:has-text('article')")
    log(f"  article links: {len(article_links)}")
    if article_links:
        article_links[0].click(force=True, timeout=5000)
        time.sleep(6)
        log(f"  URL: {page.url.replace(PROCESS5_BASE,'')[:80]}")

    # Wait for page to fully load
    time.sleep(3)

    # ===== คลิกทุก modal button =====
    log(f"\n=== คลิก modal buttons ===")
    desc_btns = page.query_selector_all("a.btn-icon, a[data-toggle='modal']")
    log(f"  พบ {len(desc_btns)} modal buttons")

    before_all = len(all_resps)
    for i, btn in enumerate(desc_btns[:5]):
        try:
            parent_text = page.evaluate(
                "(el) => el.closest('tr') ? el.closest('tr').innerText.replace(/\\n/g,' ').substring(0,80) : 'no tr'",
                btn
            )
            log(f"\n  [button {i}] row: {parent_text}")
        except Exception:
            log(f"\n  [button {i}]")

        before_btn = len(all_resps)
        try:
            btn.click(force=True, timeout=5000)
        except Exception:
            try:
                page.evaluate("(el) => el.click()", btn)
            except Exception:
                continue

        time.sleep(4)
        new_resps = all_resps[before_btn:]
        log(f"    New responses: {len(new_resps)}")
        for r in new_resps:
            url_s = r["url"].replace(PROCESS5_BASE, "")
            log(f"      {r['status']} {url_s[:80]} ({r['body_bytes_len']} bytes)")
            if r.get("body_json"):
                log(f"        JSON: {json.dumps(r['body_json'], ensure_ascii=False)[:400]}")
            elif r.get("body_text"):
                log(f"        text: {r['body_text'][:200]}")

        # Close modal
        try:
            close = page.query_selector(".modal.show .close, .modal.show .btn-close, .modal.show [aria-label='Close']")
            if close:
                close.click(force=True)
            else:
                page.keyboard.press("Escape")
            time.sleep(1)
        except Exception:
            pass

    # ===== Log all requests headers for key endpoints =====
    log(f"\n=== Request headers for key endpoints ===")
    for req in all_reqs:
        url = req["url"]
        if any(x in url for x in ["listProjectPrice", "downloadFile", "egp-project-service", "egp-upload"]):
            log(f"  {req['method']} {url.replace(PROCESS5_BASE,'')[:80]}")
            log(f"    Headers: {json.dumps(dict(req['headers']), ensure_ascii=False)[:500]}")

    page.remove_listener("request", on_request)
    page.remove_listener("response", on_response)
    page.close()

# Save
result = {
    "all_reqs": all_reqs,
    "all_resps": [{k: v for k, v in r.items() if k != "body_text" or v} for r in all_resps],
}
out_path = DEBUG_DIR / "result.json"
out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
log(f"\nบันทึก: {out_path}")
