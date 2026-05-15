"""
click_modal_button.py — คลิก modal button บน detail page ของ IM job
เพื่อดักจับ API calls สำหรับ file list

วิธีใช้: python scripts/click_modal_button.py
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "modal_click"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ID = "69049267400"  # W0 job - has ประกาศราคากลาง modal

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
            "body_text": body[:1000] if not body_json else None,
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

    # Navigate to search page first (to get cookies/token)
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

    # ===== เปิด detail page โดยตรง via JS fetch =====
    # First, use the fetch API to get the greenBook with IM pageAnnounceType
    log(f"\n=== Test greenBook for projectId={PROJECT_ID} with pageAnnounceType=IM ===")
    for announce_type in ["IM", "BOQ", "D0", "W0"]:
        gb_url = f"{API_BASE}/announcement/greenBook?mode=LINK&methodId=19&tempProjectId={PROJECT_ID}&pageAnnounceType={announce_type}"
        js = f"""async () => {{
            try {{
                const r = await fetch({json.dumps(gb_url)}, {{
                    credentials: 'include',
                    headers: {{'Accept': 'application/json'}}
                }});
                const t = await r.text();
                return {{status: r.status, body: t}};
            }} catch(e) {{ return {{error: e.toString()}}; }}
        }}"""
        res = page.evaluate(js)
        status = res.get("status")
        body_text = res.get("body", "")
        try:
            d = json.loads(body_text)
            gb_data = d.get("data", {})
            link_dto = gb_data.get("greenBookAnnouncementTypeLinkDto", [])
            log(f"  pageAnnounceType={announce_type}: status={status}, linkDto={len(link_dto) if link_dto else 0} items")
            if link_dto:
                for item in link_dto[:3]:
                    log(f"    type={item.get('announceType')} seqNo={item.get('seqNo')} "
                        f"filePath={item.get('filePath')} token={item.get('token')} "
                        f"priceBuildName={item.get('priceBuildName')}")
        except Exception as e:
            log(f"  pageAnnounceType={announce_type}: status={status}, parse error: {e}")
        time.sleep(0.3)

    # ===== ลอง getAnnouncementFile / getfile / download endpoints =====
    log(f"\n=== ลอง more file endpoints ===")
    file_eps = [
        f"{API_BASE}/announcement/getAnnouncement?projectId={PROJECT_ID}&announceType=BOQ",
        f"{API_BASE}/announcement/getAnnouncement?projectId={PROJECT_ID}&announceType=IM",
        f"{API_BASE}/announcement/getAnnouncementFile?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/getAnnouncementFile?projectId={PROJECT_ID}&seqNo=7",
        f"{API_BASE}/announcement/getAnnouncementFile?projectId={PROJECT_ID}&announceType=BOQ",
        f"{API_BASE}/announcement/getAnnouncementInfo?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/getAnnouncementInfo?projectId={PROJECT_ID}&announceType=IM",
        f"{API_BASE}/announcement/getFileInfo?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/fileList?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/file?projectId={PROJECT_ID}",
        # aobj19 with pricebuild
        f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-object/download?fileName=pricebuild_1509906972_{PROJECT_ID}.zip",
        f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-file/download?fileName=pricebuild_1509906972_{PROJECT_ID}.zip",
        f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-file/pricebuild?projectId={PROJECT_ID}",
        # Try getAnnouncements (plural)
        f"{API_BASE}/announcement/getAnnouncements?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/getProjectAnnouncement?projectId={PROJECT_ID}",
        # greenBook with seqNo
        f"{API_BASE}/announcement/greenBook?mode=LINK&methodId=19&tempProjectId={PROJECT_ID}&pageAnnounceType=BOQ&seqNo=7",
    ]
    for ep in file_eps:
        js = f"""async () => {{
            try {{
                const r = await fetch({json.dumps(ep)}, {{
                    credentials: 'include',
                    headers: {{'Accept': 'application/json'}}
                }});
                const t = await r.text();
                return {{status: r.status, body: t.substring(0, 500)}};
            }} catch(e) {{ return {{error: e.toString()}}; }}
        }}"""
        res = page.evaluate(js)
        status = res.get("status", 0)
        if status not in (404, 0, 500):
            body_t = res.get("body", "")
            ep_s = ep.replace(PROCESS5_BASE, "")
            log(f"  {status} {ep_s[:80]}: {body_t[:150]}")
        time.sleep(0.2)

    # ===== นำทางไปที่ detail page แล้วคลิก modal button =====
    log(f"\n=== นำทางไปที่ detail page ===")

    # Search to get the encrypted URL for this project
    inp = page.query_selector("input[name='keywordSearch']")
    if inp:
        inp.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        time.sleep(0.3)
        page.keyboard.type("ก่อสร้างถนน", delay=80)
        time.sleep(0.5)

    before_search = len(all_responses)
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

    # คลิก article link ของ projectId=69049267400
    before_click = len(all_responses)
    article_links = page.query_selector_all("a:has-text('article')")
    log(f"  article links: {len(article_links)}")

    target_link = None
    for link in article_links:
        try:
            row = page.evaluate("(el) => el.closest('tr') ? el.closest('tr').innerText : ''", link)
            if PROJECT_ID[:6] in row or "ก่อสร้างถนน" in row:
                target_link = link
                log(f"  เป้าหมาย: {row[:80]}")
                break
        except Exception:
            pass

    if not target_link and article_links:
        target_link = article_links[0]

    if target_link:
        url_before = page.url
        target_link.click(force=True, timeout=5000)
        time.sleep(6)
        url_now = page.url
        log(f"  URL: {url_now.replace(PROCESS5_BASE,'')[:80]}")

        page.screenshot(path=str(DEBUG_DIR / "01_detail.png"), timeout=10000)

        # ===== คลิก modal buttons (description icons) =====
        log(f"\n=== คลิก modal buttons ===")
        time.sleep(2)

        desc_btns = page.query_selector_all("a.btn-icon, a[data-toggle='modal']")
        log(f"  พบ modal buttons: {len(desc_btns)}")

        for i, btn in enumerate(desc_btns[:5]):
            before_modal = len(all_responses)
            try:
                text = btn.inner_text().strip()
                parent_text = page.evaluate(
                    "(el) => el.closest('tr') ? el.closest('tr').innerText.substring(0, 80) : ''", btn
                )
                log(f"\n  คลิก button[{i}]: '{text}' in row: {parent_text[:60]}")
            except Exception:
                log(f"\n  คลิก button[{i}]")

            try:
                btn.click(force=True, timeout=5000)
            except Exception as e:
                log(f"    click error: {e}")
                try:
                    page.evaluate("(el) => el.click()", btn)
                except Exception:
                    continue

            time.sleep(3)
            new_resps = all_responses[before_modal:]
            log(f"    API calls: {len(new_resps)}")
            for r in new_resps:
                url_s = r["url"].replace(PROCESS5_BASE, "")
                log(f"      {r['status']} {url_s[:80]}")
                if r.get("body_json"):
                    d = r["body_json"]
                    if isinstance(d, dict):
                        data = d.get("data")
                        if isinstance(data, list) and data:
                            log(f"        ★ data[{len(data)}] — keys: {list(data[0].keys()) if isinstance(data[0], dict) else '?'}")
                            for it in data[:2]:
                                if isinstance(it, dict):
                                    log(f"          {json.dumps(it, ensure_ascii=False)[:250]}")
                        elif isinstance(data, dict):
                            log(f"        data keys: {list(data.keys())}")
                            for k, v in data.items():
                                if v and any(x in str(k).lower() for x in ["file", "path", "token", "url", "doc", "hash"]):
                                    log(f"          {k}: {str(v)[:100]}")
                elif r.get("body_text"):
                    log(f"      text: {r['body_text'][:100]}")

            page.screenshot(path=str(DEBUG_DIR / f"0{i+2}_modal_{i}.png"), timeout=10000)

            # ปิด modal ถ้ามี
            try:
                close_btn = page.query_selector(".modal.show .btn-close, .modal.show [aria-label='Close'], .modal.show .close")
                if close_btn:
                    close_btn.click(force=True)
                    time.sleep(1)
                else:
                    page.keyboard.press("Escape")
                    time.sleep(1)
            except Exception:
                pass

    page.remove_listener("response", on_response)
    page.close()

# บันทึก
out_path = DEBUG_DIR / "result.json"
out_path.write_text(json.dumps({"all_responses": all_responses}, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"\nบันทึก: {out_path}")
log("เสร็จสิ้น")
