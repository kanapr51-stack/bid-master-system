"""
probe_greenbook_im.py — ดู full response ของ greenBook สำหรับ IM type
และค้นหา processDataAnnouncementTypeResponceList

วิธีใช้: python scripts/probe_greenbook_im.py
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "greenbook_im"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# Test job: 69049122041 (was IM, now W0)
PROJECT_ID = "69049122041"
METHOD_ID  = "19"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


with sync_playwright() as p:
    log("เชื่อมต่อ Chrome...")
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    log("เชื่อมต่อสำเร็จ")

    page = browser.contexts[0].new_page()
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

    def fetch_api(url):
        js = f"""async () => {{
            try {{
                const r = await fetch({json.dumps(url)}, {{
                    credentials: 'include',
                    headers: {{'Accept': 'application/json'}}
                }});
                const t = await r.text();
                return {{status: r.status, body: t}};
            }} catch(e) {{ return {{error: e.toString()}}; }}
        }}"""
        return page.evaluate(js)

    log(f"\n=== greenBook with pageAnnounceType=IM ===")
    gb_url_im = f"{API_BASE}/announcement/greenBook?mode=LINK&methodId={METHOD_ID}&tempProjectId={PROJECT_ID}&pageAnnounceType=IM"
    res = fetch_api(gb_url_im)
    log(f"status: {res.get('status')}")
    body = res.get("body", "")
    log(f"body length: {len(body)}")
    try:
        d = json.loads(body)
        gb_data = d.get("data", {})

        # Show processDataAnnouncementTypeResponceList
        proc_list = gb_data.get("processDataAnnouncementTypeResponceList", [])
        log(f"\nprocessDataAnnouncementTypeResponceList: {len(proc_list) if proc_list else 'None/empty'}")
        if proc_list:
            for item in proc_list[:10]:
                log(f"  {json.dumps(item, ensure_ascii=False)[:200]}")

        # Show alProcurePriceAndReceiveResponce
        price_resp = gb_data.get("alProcurePriceAndReceiveResponce")
        log(f"\nalProcurePriceAndReceiveResponce: {type(price_resp).__name__}")
        if price_resp:
            log(f"  {json.dumps(price_resp, ensure_ascii=False)[:500]}")

        # Show greenBookAnnouncementTypeLinkDto
        link_dto = gb_data.get("greenBookAnnouncementTypeLinkDto", [])
        log(f"\ngreenBookAnnouncementTypeLinkDto: {len(link_dto) if link_dto else 'None/empty'}")
        if link_dto:
            for item in link_dto[:10]:
                log(f"  {json.dumps(item, ensure_ascii=False)[:250]}")

    except Exception as e:
        log(f"parse error: {e}")
        log(f"raw body: {body[:1000]}")

    # Save full response
    (DEBUG_DIR / "greenbook_im.json").write_text(body, encoding="utf-8")

    # ===== ทดสอบ getProcurementDetail (full) =====
    log(f"\n=== getProcurementDetail ===")
    pd_url = f"{API_BASE}/announcement/getProcurementDetail?projectId={PROJECT_ID}"
    res2 = fetch_api(pd_url)
    pd_body = res2.get("body", "")
    (DEBUG_DIR / "procurement_detail.json").write_text(pd_body, encoding="utf-8")
    try:
        d2 = json.loads(pd_body)
        data2 = d2.get("data", {})
        log(f"data keys: {list(data2.keys()) if isinstance(data2, dict) else type(data2)}")
        # Look for any file/document related fields
        if isinstance(data2, dict):
            for k, v in data2.items():
                if v and any(x in str(v).lower() for x in ["file", "path", "doc", "attach", "hash", "url"]):
                    log(f"  {k}: {str(v)[:100]}")
    except Exception as e:
        log(f"parse error: {e}")

    # ===== ทดสอบ validateProcureProjectStep =====
    log(f"\n=== validateProcureProjectStep ===")
    vp_url = f"{API_BASE}/announcement/validateProcureProjectStep?projectId={PROJECT_ID}"
    res3 = fetch_api(vp_url)
    vp_body = res3.get("body", "")
    (DEBUG_DIR / "validate_step.json").write_text(vp_body, encoding="utf-8")
    try:
        d3 = json.loads(vp_body)
        log(f"response: {json.dumps(d3, ensure_ascii=False)[:500]}")
    except Exception:
        log(f"body: {vp_body[:200]}")

    # ===== ลอง getDocumentList / getFileList / getAnnounceFile =====
    log(f"\n=== ลอง document endpoints ===")
    doc_eps = [
        f"{API_BASE}/announcement/getDocumentList?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/getFileList?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/getAnnounceFile?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/getAnnounceDoc?projectId={PROJECT_ID}",
        f"{API_BASE}/file/list?projectId={PROJECT_ID}",
        f"{API_BASE}/announcement/file-info?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-object/list?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-file/file-info?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-file/list?projectId={PROJECT_ID}",
    ]
    for ep in doc_eps:
        res_ep = fetch_api(ep)
        status = res_ep.get("status", 0)
        body_ep = res_ep.get("body", "")
        ep_short = ep.replace(PROCESS5_BASE, "")
        if status != 404 and status != 0:
            log(f"  {status} {ep_short[:70]}: {body_ep[:200]}")
        time.sleep(0.2)

    page.close()

log("\nดู full responses ใน: " + str(DEBUG_DIR))
