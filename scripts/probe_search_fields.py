"""
probe_search_fields.py — ทำ search จริงๆ แล้ว dump ALL fields จาก API response
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

DEBUG_PORT    = 9222
PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement"
OUTPUT_DIR    = Path(__file__).parent.parent / "data" / "probe"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_js(page, url):
    js = f"""async () => {{
        try {{
            const r = await fetch({json.dumps(url)}, {{credentials:'include'}});
            const t = await r.text();
            try {{ return {{status:r.status, body:JSON.parse(t)}}; }}
            catch(e) {{ return {{status:r.status, text:t.slice(0,200)}}; }}
        }} catch(e) {{ return {{error:e.toString()}}; }}
    }}"""
    return page.evaluate(js)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}", timeout=5000)
        context = browser.contexts[0]
        page = context.new_page()

        log("โหลด search page...")
        page.goto(SEARCH_URL, wait_until="load", timeout=45000)
        time.sleep(6)

        # รอ input
        try:
            page.wait_for_selector("input[name*='keyword']", timeout=20000)
            log("input พบแล้ว")
        except Exception:
            log("ไม่พบ input[name*='keyword'] — ลอง selector อื่น")

        # รอปุ่ม enabled
        t_end = time.time() + 30
        while time.time() < t_end:
            try:
                btn = page.query_selector("button:has-text('ค้นหา')")
                if btn and btn.is_enabled():
                    log("ปุ่มพร้อม")
                    break
            except Exception:
                pass
            time.sleep(0.8)
        time.sleep(1)

        # ดักจับ URL + response
        captured_url = []
        raw_items = []

        def on_req(req):
            url = req.url
            if "egp-atpj27-service" in url and "announcement" in url and "sumProject" not in url:
                captured_url.append(url)

        page.on("request", on_req)

        # Search
        search_input = None
        for sel in ["input[name*='keyword']", "input[placeholder*='ค้นหา']", "input[type='search']", "input"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    search_input = el
                    log(f"ใช้ selector: {sel}")
                    break
            except Exception:
                pass

        if search_input:
            search_input.click()
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.keyboard.type("นครพนม", delay=60)
            time.sleep(0.8)

            try:
                with page.expect_response(
                    lambda r: "egp-atpj27-service" in r.url and "announcement" in r.url and "sumProject" not in r.url,
                    timeout=20000
                ) as resp_info:
                    page.locator("button:has-text('ค้นหา')").first.click()
                body = resp_info.value.json()
                items = (body.get("data") or {}).get("data", [])
                log(f"ได้ {len(items)} items จาก search")
                if items:
                    log("\n=== ALL FIELDS ของ item[0] ===")
                    for k, v in items[0].items():
                        log(f"  {k!r:45} = {str(v)[:100]}")
                    results["all_search_fields_item0"] = {k: str(v) for k, v in items[0].items()}
                    results["search_items_sample"] = [{k: str(v) for k,v in it.items()} for it in items[:3]]
                    raw_items = items[:3]
            except Exception as e:
                log(f"search error: {e}")
        else:
            log("ไม่พบ search input เลย")

        page.remove_listener("request", on_req)
        log(f"\nCapture URL: {captured_url[0][:120] if captured_url else 'none'}")

        # ลองดึง list API โดยตรง จาก URL ที่ดักได้
        if captured_url:
            base_url = captured_url[0]
            log(f"\n--- fetch URL ตรงๆ ---")
            res = fetch_js(page, base_url)
            body = res.get("body", {})
            items = (body.get("data") or {}).get("data", []) if isinstance(body, dict) else []
            if items:
                log("ALL FIELDS ของ item[0] (จาก direct fetch):")
                for k, v in items[0].items():
                    log(f"  {k!r:45} = {str(v)[:100]}")
                results["direct_fetch_item0"] = {k: str(v) for k, v in items[0].items()}

        # ลอง getAnnouncementDetail ของ item แรก
        if raw_items:
            pid = raw_items[0].get("projectId","")
            mid = raw_items[0].get("methodId","16")
            log(f"\n--- getAnnouncementDetail สำหรับ {pid} ---")
            for ep in [
                f"/getAnnouncementDetail?projectId={pid}&methodId={mid}",
                f"/getAnnouncementDetail?tempProjectId={pid}&methodId={mid}",
                f"/getInviteDetail?projectId={pid}&methodId={mid}",
                f"/getDetail?projectId={pid}&methodId={mid}",
                f"/getProjectDetail?projectId={pid}&methodId={mid}",
                f"/getProcureProjectDetail?projectId={pid}&methodId={mid}",
                f"/getProjectInfo?projectId={pid}&methodId={mid}",
                f"/getInfo?projectId={pid}&methodId={mid}",
            ]:
                url = f"{API_BASE}{ep}"
                res = fetch_js(page, url)
                st = res.get("status","?")
                body = res.get("body", {})
                if isinstance(body, dict) and body.get("data"):
                    rc = (body.get("response") or {}).get("responseCode","?")
                    data = body["data"]
                    log(f"  ✅ {ep[:60]}: rc={rc}")
                    if isinstance(data, dict):
                        for k, v in list(data.items())[:20]:
                            log(f"     {k!r:45} = {str(v)[:100]}")
                    results[ep] = data
                elif st == 200:
                    log(f"  200 nodata: {ep[:60]}")

        page.close()

    out_path = OUTPUT_DIR / f"search_fields_{datetime.now().strftime('%H%M%S')}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"\nบันทึก: {out_path}")
    log(f"found: {list(results.keys())}")


if __name__ == "__main__":
    main()
