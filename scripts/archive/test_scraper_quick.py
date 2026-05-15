"""
Quick Test - Sebastian Scraper v2
ดักจับ network requests เพื่อหา API endpoint ของ gprocurement.go.th
"""

import sys
import time
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

sys.stdout.reconfigure(encoding="utf-8")

DEBUG_PORT   = 9222
TEST_KEYWORD = "ถนนคอนกรีต"
OUT_DIR      = Path(__file__).parent.parent / "data" / "test_run"
OUT_DIR.mkdir(parents=True, exist_ok=True)

captured_requests = []
captured_responses = []

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def snapshot(page, name: str):
    page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=True)
    (OUT_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
    log(f"   snapshot saved: {name}")


def main():
    log("=" * 60)
    log(f"Sebastian Quick Test v2 - keyword: '{TEST_KEYWORD}'")
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

        # ดักจับ network requests ทั้งหมด
        api_calls = []

        def on_request(req):
            url = req.url
            # เก็บเฉพาะ XHR/Fetch และ URL ที่เกี่ยวกับ procurement/search
            if req.resource_type in ("xhr", "fetch") or any(
                k in url for k in ["search", "query", "keyword", "procure", "egp", "json", "api"]
            ):
                api_calls.append({
                    "type": req.resource_type,
                    "method": req.method,
                    "url": url[:200],
                    "post_data": (req.post_data or "")[:300],
                })

        def on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if "json" in ct and any(k in url for k in ["search", "procure", "query"]):
                try:
                    body = resp.json()
                    log(f"   [JSON response] {url[:80]}")
                    log(f"   keys: {list(body.keys()) if isinstance(body, dict) else type(body).__name__}")
                    (OUT_DIR / f"api_response_{len(api_calls)}.json").write_text(
                        json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        # ---- Step 1: เปิดหน้าค้นหา ----
        log("Step 1: เปิดหน้าค้นหา gprocurement.go.th")
        page.goto(
            "https://www.gprocurement.go.th/wps/portal/egp/area/procurement",
            wait_until="load",
            timeout=45000,
        )
        time.sleep(4)
        snapshot(page, "01_landing")

        # ---- Step 2: หา search input ----
        log("Step 2: หา search input")
        selectors_to_try = [
            "input[placeholder*='ค้นหา']",
            "input[type='search']",
            "input[name='keyword']",
            "#searchText",
            "input[type='text']",
        ]
        search_input = None
        for sel in selectors_to_try:
            try:
                el = page.wait_for_selector(sel, timeout=5000)
                if el and el.is_visible():
                    search_input = el
                    log(f"   Found input: {sel}")
                    break
            except Exception:
                pass

        if not search_input:
            log("   No search input found. Checking all inputs:")
            inputs = page.query_selector_all("input")
            for inp in inputs[:10]:
                try:
                    log(f"   input: type={inp.get_attribute('type')} name={inp.get_attribute('name')} placeholder={inp.get_attribute('placeholder')} visible={inp.is_visible()}")
                except Exception:
                    pass
            snapshot(page, "02_no_input")
        else:
            # ---- Step 3: ค้นหา ----
            log(f"Step 3: พิมพ์ '{TEST_KEYWORD}' และค้นหา")
            search_input.click()
            search_input.fill(TEST_KEYWORD)
            time.sleep(1)

            # ลองหา search button ก่อน
            btn = page.query_selector(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('ค้นหา'), button:has-text('Search'), "
                ".searchBtn, #searchBtn"
            )
            if btn:
                log("   Found search button, clicking...")
                btn.click()
            else:
                log("   No button found, pressing Enter")
                page.keyboard.press("Enter")

            # รอผล
            log("   Waiting for results (load)...")
            try:
                page.wait_for_load_state("load", timeout=15000)
            except Exception:
                pass
            time.sleep(5)
            snapshot(page, "03_after_search")

            # ---- Step 4: วิเคราะห์ผล ----
            log("Step 4: วิเคราะห์ผล")
            title = page.title()
            url   = page.url
            log(f"   Title: {title[:80]}")
            log(f"   URL: {url[:100]}")

            # นับ elements
            tables  = len(page.query_selector_all("table"))
            divs    = len(page.query_selector_all("div"))
            links   = len(page.query_selector_all("a"))
            log(f"   tables={tables}, divs={divs}, links={links}")

            # หา elements ที่อาจเป็น result items
            candidates = [
                ("table tr td", "table rows"),
                (".procurement-item", "procurement-item class"),
                (".result-item", "result-item class"),
                ("[class*='row']", "row-like class"),
                ("[class*='item']", "item-like class"),
                ("[class*='list']", "list-like class"),
                ("[class*='card']", "card-like class"),
                ("[class*='result']", "result-like class"),
                ("li", "list items"),
            ]
            log("   Looking for result containers:")
            for sel, name in candidates:
                els = page.query_selector_all(sel)
                if els:
                    log(f"   {name}: {len(els)} elements")
                    # แสดง text ของ 3 รายการแรก
                    for el in els[:3]:
                        try:
                            text = el.inner_text().strip()[:80].replace("\n", " ")
                            if text: log(f"      -> {text}")
                        except Exception:
                            pass

            # ดู innerText ของหน้าทั้งหมด (plain text)
            page_text = page.evaluate("document.body.innerText")
            # หาคำที่เกี่ยวกับผลการค้นหา
            lines = [l.strip() for l in page_text.split("\n") if l.strip()]
            relevant = [l for l in lines if any(
                k in l for k in ["ถนน","ก่อสร้าง","ปรับปรุง","ซ่อม","คอนกรีต","วงเงิน","บาท","อบต","เทศบาล"]
            )]
            if relevant:
                log(f"   Relevant text found ({len(relevant)} lines):")
                for line in relevant[:10]:
                    log(f"      {line[:100]}")
            else:
                log("   No relevant Thai procurement text found in page")

            # บันทึก plain text
            (OUT_DIR / "03_page_text.txt").write_text(
                "\n".join(lines[:200]), encoding="utf-8"
            )

        # ---- Step 5: สรุป API calls ----
        log("\nStep 5: API calls ที่ถูก intercept")
        log(f"   รวม {len(api_calls)} calls")
        for call in api_calls[:20]:
            log(f"   [{call['type']}] {call['method']} {call['url']}")
            if call['post_data']:
                log(f"      body: {call['post_data'][:100]}")

        # บันทึก
        (OUT_DIR / "api_calls.json").write_text(
            json.dumps(api_calls, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        log(f"\nOutput saved to: {OUT_DIR}")
        log("=" * 60)
        input("\nกด Enter เพื่อปิด")
        browser.close()


if __name__ == "__main__":
    main()
