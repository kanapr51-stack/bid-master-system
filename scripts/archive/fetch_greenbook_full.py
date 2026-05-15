"""
fetch_greenbook_full.py — ดู full greenBook response และ listProjectPriceBuildZip

วิธีใช้: python scripts/fetch_greenbook_full.py
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "greenbook_full"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

APIKEY = "Liaqv30xLpFGOlJPW1N0hPKJkbO7vWUS"

# Test with projects from our target areas
JOBS = [
    {"projectId": "69049122041", "methodId": "19", "label": "บ้านแพง construction (was IM now W0)"},
    {"projectId": "69049267400", "methodId": "19", "label": "ด่านช้าง construction W0"},
    {"projectId": "69039557554", "methodId": "19", "label": "นาเชือก construction W0"},
]


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

    def fetch_api(url, headers=None):
        h = {"Accept": "application/json, text/plain, */*"}
        if headers:
            h.update(headers)
        js = f"""async () => {{
            try {{
                const r = await fetch({json.dumps(url)}, {{
                    credentials: 'include',
                    headers: {json.dumps(h)}
                }});
                const t = await r.text();
                return {{status: r.status, body: t}};
            }} catch(e) {{ return {{error: e.toString()}}; }}
        }}"""
        return page.evaluate(js)

    for job in JOBS:
        pid = job["projectId"]
        mid = job["methodId"]
        log(f"\n{'='*60}")
        log(f"Job: {pid} — {job['label']}")

        # 1. greenBook W0 — full response
        gb_url = f"{API_BASE}/announcement/greenBook?mode=LINK&methodId={mid}&tempProjectId={pid}&pageAnnounceType=W0"
        res = fetch_api(gb_url)
        body = res.get("body", "")
        (DEBUG_DIR / f"greenbook_W0_{pid}.json").write_text(body, encoding="utf-8")
        try:
            d = json.loads(body)
            link_dto = d.get("data", {}).get("greenBookAnnouncementTypeLinkDto", [])
            log(f"  greenBook W0 linkDto: {len(link_dto)} items")
            for item in link_dto:
                log(f"  {json.dumps(item, ensure_ascii=False)}")
        except Exception as e:
            log(f"  parse error: {e}")
            log(f"  body: {body[:200]}")

        time.sleep(0.5)

        # 2. listProjectPriceBuildZipByProjectId with apikey
        boq_url = f"{PROCESS5_BASE}/egp-project-service/listProjectPriceBuildZipByProjectId?projectId={pid}"
        res2 = fetch_api(boq_url, headers={"apikey": APIKEY})
        body2 = res2.get("body", "")
        (DEBUG_DIR / f"boq_list_{pid}.json").write_text(body2, encoding="utf-8")
        log(f"\n  listProjectPriceBuildZipByProjectId: status={res2.get('status')}")
        try:
            d2 = json.loads(body2)
            log(f"  response: {json.dumps(d2, ensure_ascii=False)}")
        except Exception:
            log(f"  body: {body2[:300]}")

        time.sleep(0.5)

        # 3. If zipFileId found, try to download
        try:
            items = d2.get("data", [])
            if items:
                file_id = items[0].get("zipFileId")
                log(f"\n  zipFileId: {file_id}")
                if file_id:
                    dl_url = f"{PROCESS5_BASE}/egp-upload-service/v1/downloadFileTest?fileId={file_id}"
                    res3 = fetch_api(dl_url)
                    status3 = res3.get("status")
                    body3 = res3.get("body", "")
                    log(f"  downloadFileTest: status={status3}, body_len={len(body3)}")
                    if body3 and not body3.startswith("{"):
                        log(f"  ★ Binary content detected (first 20 bytes): {body3[:20]!r}")
        except Exception as e:
            log(f"  error: {e}")

        # 4. Also try IM greenBook
        gb_im_url = f"{API_BASE}/announcement/greenBook?mode=LINK&methodId={mid}&tempProjectId={pid}&pageAnnounceType=IM"
        res_im = fetch_api(gb_im_url)
        body_im = res_im.get("body", "")
        try:
            d_im = json.loads(body_im)
            link_im = d_im.get("data", {}).get("greenBookAnnouncementTypeLinkDto", [])
            log(f"\n  greenBook IM linkDto: {len(link_im) if link_im else 0} items")
            for item in link_im or []:
                log(f"  {json.dumps(item, ensure_ascii=False)}")
        except Exception:
            pass

    # Also try with our target area jobs (บ้านแพง)
    log(f"\n{'='*60}")
    log("ลอง บ้านแพง jobs จาก database...")
    target_jobs = [
        {"projectId": "69049122041", "methodId": "19"},
        {"projectId": "69049177433", "methodId": "19"},
        {"projectId": "68119553711", "methodId": "19"},
    ]
    for tj in target_jobs:
        pid = tj["projectId"]
        boq_url = f"{PROCESS5_BASE}/egp-project-service/listProjectPriceBuildZipByProjectId?projectId={pid}"
        res = fetch_api(boq_url, headers={"apikey": APIKEY})
        body = res.get("body", "")
        log(f"  {pid}: status={res.get('status')}, body={body[:200]}")
        time.sleep(0.3)

    page.close()

log(f"\nดู responses ใน: {DEBUG_DIR}")
