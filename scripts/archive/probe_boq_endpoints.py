"""
probe_boq_endpoints.py — probe เฉพาะ BOQ/file endpoints ที่เพิ่งค้นพบ

วิธีใช้: python scripts/probe_boq_endpoints.py
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "boq_probe"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# Known endpoints from modal click discovery
PROJECT_ID = "69049267400"
FILE_ID_W0 = "25ad05370d3e41bd8fd92b2aa6c2c7fe"  # from W0 announcement modal

# More IM jobs to test
IM_JOBS = [
    {"projectId": "69049267400", "seqNo": "7", "deptSubId": "1509906972"},
    {"projectId": "69049177433", "seqNo": "7", "deptSubId": None},
    {"projectId": "68119553711", "seqNo": "8", "deptSubId": None},
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

    def fetch_api(url, save_name=None):
        js = f"""async () => {{
            try {{
                const r = await fetch({json.dumps(url)}, {{
                    credentials: 'include',
                    headers: {{'Accept': 'application/json, */*'}}
                }});
                const t = await r.text();
                return {{status: r.status, body: t, content_type: r.headers.get('content-type') || ''}};
            }} catch(e) {{ return {{error: e.toString()}}; }}
        }}"""
        res = page.evaluate(js)
        if save_name and res.get("body"):
            (DEBUG_DIR / save_name).write_text(res["body"], encoding="utf-8")
        return res

    # ===== 1. BOQ zip list endpoint =====
    log(f"\n=== 1. listProjectPriceBuildZipByProjectId ===")
    boq_url = f"{PROCESS5_BASE}/egp-project-service/listProjectPriceBuildZipByProjectId?projectId={PROJECT_ID}"
    res = fetch_api(boq_url, "boq_zip_list.json")
    log(f"  status: {res.get('status')}")
    body = res.get("body", "")
    log(f"  content-type: {res.get('content_type')}")
    log(f"  body: {body[:500]}")

    # ===== 2. Upload service downloadFileTest =====
    log(f"\n=== 2. downloadFileTest (W0 file) ===")
    dl_url = f"{PROCESS5_BASE}/egp-upload-service/v1/downloadFileTest?fileId={FILE_ID_W0}"
    res2 = fetch_api(dl_url, "download_test.json")
    log(f"  status: {res2.get('status')}")
    body2 = res2.get("body", "")
    log(f"  content-type: {res2.get('content_type')}")
    log(f"  body: {body2[:500]}")

    # ===== 3. ลอง egp-project-service endpoints อื่นๆ =====
    log(f"\n=== 3. ลอง egp-project-service endpoints ===")
    proj_eps = [
        f"{PROCESS5_BASE}/egp-project-service/getProjectDetail?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/listProjectFile?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/getFile?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/getProjectFileList?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/listProjectPriceBuild?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/listPriceBuild?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/listProjectPriceBuildFile?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/downloadPriceBuild?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-project-service/getPriceBuildFile?projectId={PROJECT_ID}",
    ]
    for ep in proj_eps:
        res_ep = fetch_api(ep)
        status = res_ep.get("status", 0)
        body_ep = res_ep.get("body", "")
        ep_s = ep.replace(PROCESS5_BASE, "")
        if status not in (404, 0):
            log(f"  {status} {ep_s[:70]}: {body_ep[:200]}")
        time.sleep(0.2)

    # ===== 4. egp-upload-service endpoints =====
    log(f"\n=== 4. egp-upload-service endpoints ===")
    upload_eps = [
        f"{PROCESS5_BASE}/egp-upload-service/v1/getFileInfo?fileId={FILE_ID_W0}",
        f"{PROCESS5_BASE}/egp-upload-service/v1/downloadFile?fileId={FILE_ID_W0}",
        f"{PROCESS5_BASE}/egp-upload-service/v1/listFileByProjectId?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-upload-service/v1/getFile?projectId={PROJECT_ID}",
        f"{PROCESS5_BASE}/egp-upload-service/v1/listFile?projectId={PROJECT_ID}",
    ]
    for ep in upload_eps:
        res_ep = fetch_api(ep)
        status = res_ep.get("status", 0)
        body_ep = res_ep.get("body", "")
        ep_s = ep.replace(PROCESS5_BASE, "")
        log(f"  {status} {ep_s[:70]}: {body_ep[:200]}")
        time.sleep(0.2)

    # ===== 5. ตรวจสอบ IM jobs อื่นๆ ด้วย BOQ endpoint =====
    log(f"\n=== 5. ทดสอบ BOQ endpoint กับ IM jobs อื่น ===")
    for job in IM_JOBS:
        pid = job["projectId"]
        boq_url2 = f"{PROCESS5_BASE}/egp-project-service/listProjectPriceBuildZipByProjectId?projectId={pid}"
        res_j = fetch_api(boq_url2)
        status_j = res_j.get("status", 0)
        body_j = res_j.get("body", "")
        log(f"  {pid}: status={status_j}, body={body_j[:200]}")
        time.sleep(0.3)

    page.close()

log(f"\nดู responses ใน: {DEBUG_DIR}")
log("เสร็จสิ้น")
