"""Probe หา API endpoint สำหรับ project detail จาก projectId"""
import sys, json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

JID = "69039325763"  # จะลองหา winner data
PROCESS5 = "https://process5.gprocurement.go.th"
SEARCH_URL = f"{PROCESS5}/egp-agpc01-web/announcement"

with sync_playwright() as p:
    browser = connect_browser(p)
    page = browser.contexts[0].new_page()
    page.goto(SEARCH_URL, wait_until="load", timeout=45000)
    import time; time.sleep(5)

    # ลองหลาย endpoint pattern
    base = f"{PROCESS5}/egp-atpj27-service/pb/a-egp-allt-project/announcement"
    endpoints = [
        f"{base}/sumProject?projectId={JID}",
        f"{base}/getContractAvailable?projectId={JID}",
        f"{base}/getProcureResult?projectId={JID}",
        f"{base}/getProjectDetail?projectId={JID}",
        f"{base}/getProject?projectId={JID}",
        f"{base}?keyword={JID}&page=1",  # search by jid as keyword
    ]

    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            const text = await r.text();
            if (text.length > 5000) return {status: r.status, len: text.length, preview: text.slice(0, 1500)};
            try {
                return {status: r.status, body: JSON.parse(text)};
            } catch(e) {
                return {status: r.status, text: text.slice(0, 500)};
            }
        } catch(e) { return {error: e.toString()}; }
    }"""

    for url in endpoints:
        print(f"\n=== {url.split('/')[-1][:60]} ===")
        res = page.evaluate(js, url)
        print(json.dumps(res, ensure_ascii=False, indent=2)[:2000])

    page.close()
