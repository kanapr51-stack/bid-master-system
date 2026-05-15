"""
intercept_spy.py — ดักจับ announcementToken จาก Turnstile validate call
แล้วใช้ search API โดยตรง + คลิก result ผ่าน Angular router

วิธีใช้: python scripts/intercept_spy.py
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
API_BASE = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
DEBUG_DIR = Path(__file__).parent.parent / "downloads" / "debug" / "intercept_spy"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

all_responses = []
announcement_token = None
validate_token = None  # the CF validate token


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def on_response(resp):
    global announcement_token, validate_token
    url = resp.url
    if any(x in url for x in [".js", ".css", ".png", ".ico", ".woff", ".svg", ".map", "fonts"]):
        return
    if "gprocurement.go.th" not in url:
        return
    try:
        body = resp.text()
        body_json = None
        if "application/json" in resp.headers.get("content-type", ""):
            try:
                body_json = json.loads(body)
            except Exception:
                pass

        # ดักจับ announcementToken จาก validate response
        if "cfturnstile/validate" in url and body_json:
            data = body_json.get("data", {})
            if isinstance(data, dict):
                tok = data.get("announcementToken") or data.get("token")
                if tok:
                    announcement_token = tok
                    log(f"  ★ announcementToken: {tok[:50]}...")
                # บางที response มีแค่ token โดยตรง
            elif isinstance(data, str) and len(data) > 20:
                announcement_token = data
                log(f"  ★ announcementToken (str): {data[:50]}...")
            # Try top-level token
            if not announcement_token:
                tok = body_json.get("announcementToken") or body_json.get("token")
                if tok:
                    announcement_token = tok
            log(f"  validate response keys: {list(body_json.keys()) if isinstance(body_json, dict) else type(body_json)}")
            log(f"  validate body: {body[:300]}")

        all_responses.append({
            "status": resp.status,
            "url": url,
            "body_len": len(body),
            "body_json": body_json,
        })
        log(f"  API: {resp.status} {url.replace(PROCESS5_BASE, '')[:90]}")
    except Exception as e:
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

    page = browser.contexts[0].new_page()
    page.on("response", on_response)

    # Navigate to announcement page
    log(f"Navigate...")
    page.goto(f"{PROCESS5_BASE}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
    time.sleep(8)  # รอ Turnstile + validate call

    log(f"announcementToken ได้: {announcement_token is not None}")
    if announcement_token:
        log(f"  token: {announcement_token[:80]}")
    else:
        log("  token ยังไม่ได้ — รออีก 10s")
        time.sleep(10)
        log(f"  token หลังรอ: {announcement_token is not None}")

    # ===== ใช้ token search โดยตรง =====
    log("\n--- search โดยตรงด้วย fetch() ---")
    before_search = len(all_responses)

    search_results = []
    for keyword in ["ถนนคอนกรีต", "บ้านแพง", "ก่อสร้าง"]:
        if search_results:
            break

        # Build URL (same as scraper)
        if announcement_token:
            search_url = (
                f"{API_BASE}/announcement?"
                f"budgetYear=2569"
                f"&announcementTodayFlag=false"
                f"&keywordSearch={keyword}"
                f"&page=1"
                f"&announcementToken={announcement_token}"
            )
        else:
            # ไม่มี token — ลองแบบไม่มี token
            search_url = (
                f"{API_BASE}/announcement?"
                f"budgetYear=2569"
                f"&announcementTodayFlag=false"
                f"&keywordSearch={keyword}"
                f"&page=1"
            )

        js = f"""
        async () => {{
            try {{
                const r = await fetch({json.dumps(search_url)}, {{
                    credentials: 'include',
                    headers: {{'Accept': 'application/json'}}
                }});
                const text = await r.text();
                return {{status: r.status, body: text.substring(0, 2000)}};
            }} catch(e) {{
                return {{error: e.toString()}};
            }}
        }}
        """
        try:
            result = page.evaluate(js)
            log(f"search '{keyword}': status={result.get('status')}")
            body_text = result.get("body", "")
            log(f"  body: {body_text[:300]}")
            try:
                body_json = json.loads(body_text)
                data = body_json.get("data", {})
                if isinstance(data, dict):
                    items = data.get("data", [])
                    log(f"  ★ items: {len(items)}")
                    search_results = items
                    if items:
                        log(f"  ★ first item: {json.dumps(items[0], ensure_ascii=False)[:200]}")
            except Exception:
                pass
        except Exception as e:
            log(f"  fetch error: {e}")

    # ===== ถ้ามี results — ลอง navigate Angular router =====
    if search_results:
        first = search_results[0]
        project_id = first.get("projectId", "")
        seq_no = first.get("seqNo", "")
        log(f"\n--- navigate ไป detail: projectId={project_id} seqNo={seq_no} ---")

        before_detail = len(all_responses)

        # ลอง Angular router navigate
        try:
            js_nav = f"""
            async () => {{
                // Try Angular router injection
                try {{
                    const el = document.querySelector('egp-all-announcement-list') ||
                               document.querySelector('app-root') ||
                               document.querySelector('[ng-version]');
                    if (el) {{
                        const ngEl = window.ng && window.ng.getContext ? window.ng.getContext(el) : null;
                        return {{method: 'ng_context', el_tag: el.tagName, has_ng: ngEl !== null}};
                    }}
                }} catch(e) {{}}
                return {{method: 'no_ng', msg: 'Angular context not found'}};
            }}
            """
            nav_result = page.evaluate(js_nav)
            log(f"  Angular context: {nav_result}")
        except Exception as e:
            log(f"  nav error: {e}")

        # ลองรูปแบบ URL ต่างๆ ผ่าน page.goto
        candidate_urls = [
            f"{PROCESS5_BASE}/egp-agpc01-web/announcement?projectId={project_id}&seqNo={seq_no}&mode=detail",
            f"{PROCESS5_BASE}/egp-agpc01-web/announcement/view/{project_id}/{seq_no}",
            f"{PROCESS5_BASE}/egp-agpc01-web/announcement/detail/{project_id}/{seq_no}",
            f"{PROCESS5_BASE}/egp-agpc01-web/announcement/{project_id}/{seq_no}",
        ]

        for url in candidate_urls:
            log(f"\n  ลอง navigate: {url.replace(PROCESS5_BASE, '')}")
            before = len(all_responses)
            try:
                page.goto(url, wait_until="load", timeout=20000)
                time.sleep(4)
                url_now = page.url
                new_resps = all_responses[before:]
                log(f"    URL now: {url_now.replace(PROCESS5_BASE, '')}")
                log(f"    New responses: {len(new_resps)}")
                for r in new_resps:
                    log(f"      {r['status']} {r['url'].replace(PROCESS5_BASE,'')[:80]}")
                    if r.get("body_json"):
                        d = r["body_json"]
                        if isinstance(d, dict) and d.get("data"):
                            data = d.get("data")
                            if isinstance(data, list) and data:
                                log(f"      ★★★ data[{len(data)}] - keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'non-dict'}")
            except Exception as e:
                log(f"    error: {e}")

    else:
        log("ไม่มี search results — ข้าม detail navigation")

    # ===== Look at the announcement search response to find if there's a URL field =====
    log("\n--- ตรวจสอบ responses ---")
    for r in all_responses[before_search:]:
        if r.get("body_json"):
            d = r["body_json"]
            if isinstance(d, dict) and d.get("response", {}).get("responseCode") == "0":
                data = d.get("data")
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                    if isinstance(items, list) and items:
                        log(f"  search results: {len(items)} items")
                        log(f"  first item keys: {list(items[0].keys())}")
                        log(f"  first item: {json.dumps(items[0], ensure_ascii=False)[:300]}")

    page.close()

# บันทึกผล
output = {
    "announcement_token": announcement_token,
    "search_results_count": len(search_results),
    "all_responses": all_responses,
}
out_path = DEBUG_DIR / "result.json"
out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"\nบันทึก: {out_path}")
