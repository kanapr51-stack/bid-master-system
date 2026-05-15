"""
click_and_spy.py — ดักจับ ALL API calls เมื่อคลิก result row
(ใช้สถานะปัจจุบันของ browser — ไม่ต้อง search ใหม่)

วิธีใช้: python scripts/click_and_spy.py
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
DEBUG_DIR = Path(__file__).parent.parent / "downloads" / "debug" / "click_spy"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

all_responses = []


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
        is_json = "application/json" in resp.headers.get("content-type", "")
        body_json = None
        if is_json:
            try:
                body_json = json.loads(body)
            except Exception:
                pass
        all_responses.append({
            "status": resp.status,
            "url": url,
            "body_len": len(body),
            "body_json": body_json,
        })
        log(f"  API: {resp.status} {url.replace(PROCESS5_BASE, '')[:90]}")
    except Exception:
        all_responses.append({"status": resp.status, "url": url})


with sync_playwright() as p:
    log("เชื่อมต่อ Chrome CDP...")
    for attempt in range(10):
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            log("เชื่อมต่อสำเร็จ")
            break
        except Exception:
            log(f"  รอ... ({attempt+1}/10)")
            time.sleep(2)

    # สร้าง page ใหม่เสมอ (หลีกเลี่ยง state ที่ค้างอยู่)
    page = browser.contexts[0].new_page()
    log("สร้าง page ใหม่")

    page.on("response", on_response)

    # ===== Navigate to search page =====
    log(f"Navigate ไป announcement page...")
    page.goto(f"{PROCESS5_BASE}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
    time.sleep(5)
    page.screenshot(path=str(DEBUG_DIR / "00_current_state.png"), timeout=10000)
    log(f"URL ปัจจุบัน: {page.url}")

    # ===== พยายามค้นหาและคลิก row =====
    log("\n--- ค้นหา clickable rows ใน table ---")

    # ตรวจ table body
    try:
        tbody = page.query_selector("tbody")
        if tbody:
            rows = page.query_selector_all("tbody tr")
            log(f"พบ {len(rows)} tr ใน tbody")
            for i, row in enumerate(rows[:5]):
                text = row.inner_text().strip()
                log(f"  row[{i}]: {text[:100]}")
        else:
            log("ไม่พบ tbody")
    except Exception as e:
        log(f"tbody error: {e}")

    # ===== ลองคลิก row แรกที่ไม่ใช่ error =====
    log("\n--- ลองคลิก row ---")
    clicked = False
    before_click_count = len(all_responses)
    url_before = page.url

    try:
        rows = page.query_selector_all("tbody tr")
        for i, row in enumerate(rows):
            text = row.inner_text().strip()
            # skip error rows
            if "E1530" in text or "ข้อความปฎิเสธ" in text or len(text) < 5:
                continue
            log(f"คลิก row[{i}]: {text[:80]}")
            row.click(timeout=5000)
            time.sleep(6)
            clicked = True
            break
    except Exception as e:
        log(f"row click error: {e}")

    if not clicked:
        log("ไม่พบ row ที่คลิกได้ — ลองค้นหาใหม่")
        # ===== ค้นหาใหม่ด้วย keyword ที่รู้ว่าได้ผล =====
        try:
            # ไปที่ search page ถ้ายังไม่ได้อยู่
            if "process5" not in page.url:
                page.goto(f"{PROCESS5_BASE}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
                time.sleep(5)

            # รอ search button enabled
            log("รอ search button...")
            for wait_i in range(30):
                time.sleep(2)
                btn = page.query_selector("button[type='submit']")
                if btn:
                    disabled = page.evaluate("(el) => el.disabled", btn)
                    if not disabled:
                        log(f"  enabled (รอ {(wait_i+1)*2}s)")
                        break

            page.screenshot(path=str(DEBUG_DIR / "01_ready_to_search.png"))

            # พิมพ์ keyword
            inputs = page.query_selector_all("input[name='keywordSearch']")
            if inputs:
                inp = inputs[0]
                inp.click()
                time.sleep(0.3)
                inp.press("Control+a")
                time.sleep(0.2)
                page.keyboard.type("ถนนคอนกรีต", delay=100)
                time.sleep(0.5)

            btn = page.query_selector("button[type='submit']")
            if btn:
                log("กดค้นหา...")
                btn.click()
                time.sleep(6)

            page.screenshot(path=str(DEBUG_DIR / "02_after_search.png"))
            log(f"URL หลัง search: {page.url}")

            # ลองคลิก row อีกครั้ง
            rows = page.query_selector_all("tbody tr")
            log(f"พบ {len(rows)} rows หลัง search")
            for i, row in enumerate(rows):
                text = row.inner_text().strip()
                if "E1530" in text or "ข้อความปฎิเสธ" in text or len(text) < 5:
                    continue
                log(f"คลิก row[{i}]: {text[:80]}")
                row.click(timeout=10000)
                time.sleep(6)
                clicked = True
                break

        except Exception as e:
            log(f"search/click error: {e}")

    # ===== Screenshot หลัง click =====
    page.screenshot(path=str(DEBUG_DIR / "03_after_click.png"))
    url_after = page.url
    log(f"\nURL หลัง click: {url_after}")

    # รออีก 3s สำหรับ lazy loads
    time.sleep(3)
    page.screenshot(path=str(DEBUG_DIR / "04_final.png"))

    # ===== บันทึก HTML =====
    try:
        html = page.content()
        (DEBUG_DIR / "page.html").write_text(html, encoding="utf-8")
    except Exception:
        pass

    page.remove_listener("response", on_response)

# ===== วิเคราะห์ผล =====
new_responses = all_responses[before_click_count:]
log(f"\n=== responses หลัง click: {len(new_responses)} ===")
for r in new_responses:
    log(f"  {r['status']} {r['url'].replace(PROCESS5_BASE, '')}")
    if r.get("body_json"):
        d = r["body_json"]
        if isinstance(d, dict):
            rc = d.get("response", {}).get("responseCode") if isinstance(d.get("response"), dict) else None
            data = d.get("data")
            if isinstance(data, list):
                log(f"       ★ data[{len(data)}] items")
                if data and isinstance(data[0], dict):
                    log(f"       ★ data[0] keys: {list(data[0].keys())[:10]}")
            elif isinstance(data, dict):
                log(f"       ★ data keys: {list(data.keys())[:10]}")

# บันทึกทั้งหมด
output = {
    "url_before": url_before,
    "url_after": url_after,
    "clicked": clicked,
    "all_responses": all_responses,
    "new_responses": new_responses,
}
out_path = DEBUG_DIR / "result.json"
out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"\nบันทึก: {out_path}")
log(f"Screenshots: {DEBUG_DIR}")
