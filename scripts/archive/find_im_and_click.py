"""
find_im_and_click.py — ค้นหา announcement ที่ยังอยู่ใน IM phase
แล้วคลิกเพื่อดู document endpoints

วิธีใช้: python scripts/find_im_and_click.py
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "find_im"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

all_responses = []
detail_start_idx = 0


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
    log("เชื่อมต่อ Chrome...")
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    log("เชื่อมต่อสำเร็จ")

    page = browser.contexts[0].new_page()
    page.on("response", on_response)

    # Navigate
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

    # ===== ค้นหา IM-type announcements =====
    # Search with keyword that's likely to return IM (active) results
    KEYWORDS = ["ก่อสร้างถนน", "ประกวดราคา", "ก่อสร้าง"]
    search_items_all = []

    for keyword in KEYWORDS:
        if search_items_all:
            break

        inp = page.query_selector("input[name='keywordSearch']")
        if inp:
            inp.click()
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            time.sleep(0.3)
            page.keyboard.type(keyword, delay=80)
            time.sleep(0.5)

        log(f"Search '{keyword}'...")
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

            body_json = resp_info.value.json()
            if body_json.get("response", {}).get("responseCode") == "0":
                items = body_json.get("data", {}).get("data", [])
                # Filter for IM-type (M steps = active bidding)
                im_items = [it for it in items if it.get("announceType") in ("IM",) or
                            str(it.get("stepId", "")).startswith("M")]
                log(f"  total={len(items)}, IM/M-step={len(im_items)}")
                if im_items:
                    search_items_all = im_items
                    log(f"  ★ พบ IM items! ใช้ '{keyword}'")
                else:
                    search_items_all = items[:5]  # fallback
        except Exception as e:
            log(f"  search error: {e}")

        time.sleep(2)

    if not search_items_all:
        log("ไม่พบ items — ลอง search แบบ Today announcements")
        # Try "ดูประกาศวันนี้" button
        try:
            today_btn = page.locator("button:has-text('ดูประกาศวันนี้')").first
            today_btn.click(timeout=5000)
            time.sleep(3)
            # Try to get results
        except Exception:
            pass

    log(f"\nพบ search items: {len(search_items_all)}")
    for it in search_items_all[:5]:
        log(f"  {it.get('projectId')} seqNo={it.get('seqNo')} type={it.get('announceType')} step={it.get('stepId')} - {it.get('projectName','')[:50]}")

    # ===== คลิก article link ของ IM item =====
    page.screenshot(path=str(DEBUG_DIR / "01_search_results.png"), timeout=10000)

    article_links = page.query_selector_all("a:has-text('article')")
    log(f"\nพบ article links: {len(article_links)}")

    # ลองคลิกทุก article link จนกว่าจะพบ IM type
    detail_start_idx = len(all_responses)
    clicked_item = None
    url_after_click = page.url

    for idx, link in enumerate(article_links[:10]):
        try:
            row_text = page.evaluate("(el) => el.closest('tr') ? el.closest('tr').innerText.substring(0, 60) : 'no tr'", link)
            log(f"\n  คลิก link[{idx}]: {row_text}")
        except Exception:
            pass

        before = len(all_responses)
        url_before = page.url

        try:
            link.click(force=True, timeout=5000)
        except Exception as e:
            log(f"  click error: {e}")
            try:
                page.evaluate("(el) => el.click()", link)
            except Exception:
                continue

        time.sleep(1)
        url_now = page.url
        log(f"  URL: {url_now.replace(PROCESS5_BASE,'')[:80]}")

        if url_now != url_before:
            # Navigation happened!
            url_after_click = url_now
            clicked_item = search_items_all[idx] if idx < len(search_items_all) else None
            log(f"  ★ navigation สำเร็จ!")
            break

        # Check if any IM-specific API calls happened
        new_resps = all_responses[before:]
        for r in new_resps:
            if "getProjectDetail" in r["url"]:
                # Check what type this project is
                if r.get("body_json"):
                    ann_type = r["body_json"].get("data", {}).get("announceType")
                    log(f"  project announceType={ann_type}")
                    if ann_type in ("IM", "D0"):
                        url_after_click = url_now
                        detail_start_idx = before
                        log(f"  ★ IM/D0 project พบ!")
                        break

    # รอ API calls โหลดครบ
    time.sleep(8)
    url_final = page.url
    log(f"\nURL สุดท้าย: {url_final.replace(PROCESS5_BASE,'')}")

    page.screenshot(path=str(DEBUG_DIR / "02_detail_page.png"), timeout=10000)

    # ===== Scroll down เพื่อโหลด lazy content =====
    log("\n--- Scroll down ---")
    for scroll_n in range(5):
        page.evaluate(f"window.scrollBy(0, 600)")
        time.sleep(1.5)

    time.sleep(3)
    page.screenshot(path=str(DEBUG_DIR / "03_scrolled.png"), timeout=10000)

    # บันทึก HTML
    try:
        html = page.content()
        (DEBUG_DIR / "detail.html").write_text(html, encoding="utf-8")
        log(f"บันทึก HTML ({len(html):,} chars)")
    except Exception:
        pass

    page.remove_listener("response", on_response)
    page.close()

# ===== วิเคราะห์ =====
new_resps = all_responses[detail_start_idx:]
log(f"\n{'='*60}")
log(f"API calls หลัง click: {len(new_resps)}")
for r in new_resps:
    url_s = r["url"].replace(PROCESS5_BASE, "")
    log(f"  {r['status']} {url_s[:90]}")
    if r.get("body_json"):
        d = r["body_json"]
        if isinstance(d, dict):
            data = d.get("data")
            if isinstance(data, list) and data:
                log(f"    ★ data[{len(data)}] — keys: {list(data[0].keys()) if isinstance(data[0], dict) else '?'}")
                for it in data[:2]:
                    if isinstance(it, dict):
                        log(f"      {json.dumps(it, ensure_ascii=False)[:200]}")
            elif isinstance(data, dict):
                log(f"    data keys: {list(data.keys())}")
                # Look for file/doc related keys
                for k, v in data.items():
                    if v and any(x in str(k).lower() for x in ["file", "doc", "attach", "path", "url", "link"]):
                        log(f"      {k}: {str(v)[:100]}")
            elif isinstance(data, str) and len(data) > 10:
                log(f"    data: {data[:100]}")

log("\nดู screenshots ใน: " + str(DEBUG_DIR))

# บันทึกผล
output = {
    "url_after_click": url_after_click,
    "new_responses": new_resps,
    "all_responses": all_responses,
}
out_path = DEBUG_DIR / "result.json"
out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
