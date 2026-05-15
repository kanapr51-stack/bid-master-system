"""
เข้าผ่าน search page → คลิกผลลัพธ์ → ดักจับ API calls ทั้งหมด
เพื่อหา endpoint สำหรับ TOR / เอกสารแนบ
"""
import sys, time, json
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
PROJECT_ID    = "69049122041"
BOQ_APIKEY    = "Liaqv30xLpFGOlJPW1N0hPKJkbO7vWUS"

interesting = []

def on_response(resp):
    url = resp.url
    if "process5" not in url:
        return
    if any(s in url for s in [".js", ".css", ".ico", "font", "chunk", ".woff", ".jpg", ".png"]):
        return
    try:
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            body = resp.json()
            body_str = json.dumps(body, ensure_ascii=False)
            interesting.append({"url": url, "body_str": body_str})
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].new_page()
    page.on("response", on_response)

    print("navigate ไป search page...")
    page.goto(SEARCH_URL, wait_until="load", timeout=45000)
    time.sleep(5)

    # กรอก project ID ในช่องค้นหา
    print("ค้นหา project ID...")
    try:
        search_input = page.locator("input").first
        search_input.click()
        time.sleep(0.5)
        page.keyboard.type(PROJECT_ID, delay=50)
        time.sleep(1)

        # กด search
        btn = page.locator("button").filter(has_text="ค้นหา").first
        btn.click()
        time.sleep(3)
    except Exception as e:
        print(f"  ค้นหาไม่ได้: {e}")

    # ลองคลิกผลลัพธ์แรก
    print("คลิกผลลัพธ์...")
    try:
        # หา row หรือ link ที่มี project ID
        row = page.locator(f"text={PROJECT_ID}").first
        row.click()
        time.sleep(4)
        print(f"  URL หลังคลิก: {page.url}")
    except Exception as e:
        print(f"  คลิกไม่ได้: {e}")

    time.sleep(3)

    print(f"\n=== ดักได้ {len(interesting)} JSON responses ===")
    for item in interesting:
        url = item["url"]
        body = item["body_str"]
        endpoint = url.split("/")[-1].split("?")[0]
        has_file = any(k in body.lower() for k in ["fileid", "attachid", "document", "attach", "tor", "download"])
        marker = "★" if has_file else " "
        print(f"{marker} [{endpoint}]")
        if has_file:
            print(f"    URL: {url}")
            print(f"    body: {body[:400]}")
        print()

    page.close()
