"""
Sebastian Scraper v3 - Direct process5 search
ไปที่ process5.gprocurement.go.th โดยตรง แล้วค้นหา + ดัก API call
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

DEBUG_PORT   = 9222
TEST_KEYWORD = "ถนนคอนกรีต"
BASE_URL     = "https://process5.gprocurement.go.th/egp-agpc01-web/announcement"
OUT_DIR      = Path(__file__).parent.parent / "data" / "test_run_v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def snapshot(page, name: str):
    page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=True)
    (OUT_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
    log(f"   snapshot: {name}")


def main():
    log("=" * 60)
    log(f"Sebastian v3 - direct process5 search: '{TEST_KEYWORD}'")
    log("=" * 60)

    with sync_playwright() as p:
        browser = None
        for i in range(10):
            try:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
                log("Connected to Chrome")
                break
            except Exception:
                log(f"  waiting for Chrome... ({i+1}/10)")
                time.sleep(2)

        if not browser:
            log("Cannot connect to Chrome")
            return

        ctx = browser.contexts[0]
        page = ctx.new_page()

        api_calls = []
        search_responses = []

        def on_request(req):
            url = req.url
            if "process5.gprocurement" in url and req.resource_type in ("xhr", "fetch"):
                entry = {
                    "type": req.resource_type,
                    "method": req.method,
                    "url": url,
                    "post_data": (req.post_data or "")[:500],
                }
                api_calls.append(entry)
                log(f"   [API] {req.method} {url[:100]}")
                if req.post_data:
                    log(f"         body: {req.post_data[:150]}")

        def on_response(resp):
            url = resp.url
            if "process5.gprocurement" not in url:
                return
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return
            try:
                body = resp.json()
                fname = f"resp_{len(search_responses):03d}_{url.split('/')[-1][:40]}.json"
                (OUT_DIR / fname).write_text(
                    json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                log(f"   [JSON] {url.split('?')[0][-60:]}")
                search_responses.append({"url": url, "file": fname, "keys": list(body.keys()) if isinstance(body, dict) else type(body).__name__})
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        # Step 1: ไปที่ process5 โดยตรง
        log(f"Step 1: ไปที่ {BASE_URL}")
        try:
            page.goto(BASE_URL, wait_until="load", timeout=45000)
        except Exception as e:
            log(f"   goto error: {e}")
        time.sleep(5)
        snapshot(page, "01_process5_landing")
        log(f"   Title: {page.title()}")
        log(f"   URL: {page.url}")

        # Step 2: หา input ค้นหา
        log("Step 2: หา search input บน process5")
        selectors = [
            "input[placeholder*='ค้นหา']",
            "input[placeholder*='keyword']",
            "input[placeholder*='search']",
            "input[type='search']",
            "input[name*='keyword']",
            "input[name*='search']",
            "input[formcontrolname*='keyword']",
            "input[formcontrolname*='search']",
            "mat-form-field input",
            "input[type='text']",
        ]
        search_input = None
        for sel in selectors:
            try:
                el = page.wait_for_selector(sel, timeout=3000)
                if el and el.is_visible():
                    search_input = el
                    log(f"   Found: {sel}")
                    break
            except Exception:
                pass

        if not search_input:
            log("   No search input found. All inputs:")
            for inp in page.query_selector_all("input")[:15]:
                try:
                    log(f"   - type={inp.get_attribute('type')} name={inp.get_attribute('name')} placeholder={inp.get_attribute('placeholder')} formcontrolname={inp.get_attribute('formcontrolname')} visible={inp.is_visible()}")
                except Exception:
                    pass
            snapshot(page, "02_no_input")
        else:
            # Step 3: พิมพ์และค้นหา
            log(f"Step 3: ค้นหา '{TEST_KEYWORD}'")
            # รอ Cloudflare Turnstile ให้เสร็จก่อน แล้วค่อย type
            log("   Waiting for Cloudflare Turnstile to complete (~12s)...")
            time.sleep(12)

            # ใช้ keyboard.type เพื่อ trigger Angular input event
            search_input.click()
            # clear existing text first
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            time.sleep(0.3)
            page.keyboard.type(TEST_KEYWORD, delay=80)
            time.sleep(1)
            log(f"   Input value: {search_input.input_value()}")

            # คลิกปุ่มค้นหา และดัก announcement response โดยตรง
            log("   Clicking search button + waiting for announcement response...")
            announcement_body = None
            with page.expect_response(
                lambda r: "egp-atpj27-service" in r.url and "announcement" in r.url and "sumProject" not in r.url,
                timeout=30000
            ) as resp_info:
                try:
                    loc = page.locator("button:has-text('ค้นหา')").first
                    loc.click(timeout=10000)
                    log("   Button clicked via locator")
                except Exception as e:
                    log(f"   Button click failed ({e}), trying Enter")
                    search_input.press("Enter")

            try:
                resp = resp_info.value
                log(f"   Announcement response: {resp.status} {resp.url[:80]}")
                announcement_body = resp.json()
                (OUT_DIR / "announcement_result.json").write_text(
                    json.dumps(announcement_body, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                log(f"   Saved announcement_result.json")
            except Exception as e:
                log(f"   Failed to read announcement response: {e}")

            time.sleep(3)
            snapshot(page, "03_after_search")
            log(f"   URL after search: {page.url}")

            # Step 4: วิเคราะห์ผล
            log("Step 4: ผลการค้นหา")
            page_text = page.evaluate("document.body.innerText")
            lines = [l.strip() for l in page_text.split("\n") if l.strip()]
            log(f"   Total text lines: {len(lines)}")

            relevant = [l for l in lines if any(k in l for k in [
                "ถนน","ก่อสร้าง","ปรับปรุง","คอนกรีต","วงเงิน","บาท","อบต","เทศบาล",
                "โครงการ","จัดซื้อ","ประมูล","ประกวด"
            ])]
            if relevant:
                log(f"   Relevant lines ({len(relevant)}):")
                for l in relevant[:15]:
                    log(f"      {l[:120]}")
            else:
                log("   No relevant procurement lines found")
                log("   First 20 lines:")
                for l in lines[:20]:
                    log(f"      {l[:120]}")

            (OUT_DIR / "03_page_text.txt").write_text("\n".join(lines[:300]), encoding="utf-8")

        # Step 5: สรุป
        log(f"\nStep 5: สรุป API calls ({len(api_calls)} calls)")
        for c in api_calls:
            log(f"   [{c['method']}] {c['url'][:120]}")

        (OUT_DIR / "api_calls.json").write_text(
            json.dumps(api_calls, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUT_DIR / "api_responses_index.json").write_text(
            json.dumps(search_responses, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        log(f"\nOutput: {OUT_DIR}")
        log("=" * 60)
        page.close()


if __name__ == "__main__":
    main()
