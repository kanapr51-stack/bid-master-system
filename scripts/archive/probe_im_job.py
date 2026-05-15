"""
probe_im_job.py — ทดสอบ API สำหรับ IM-type jobs (open bid)
เพื่อหา document/file endpoint

วิธีใช้: python scripts/probe_im_job.py
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project"
DEBUG_DIR     = Path(__file__).parent.parent / "downloads" / "debug" / "probe_im"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# Known IM jobs from our data
IM_JOBS = [
    # From jobs_20260430_0335.json — construction IM type
    {"projectId": "69049122041", "seqNo": "7", "title": "ก่อสร้างถนนคอนกรีตเสริมเหล็ก นพ.ถ 1-0076 บ้านแพง"},
    {"projectId": "69049177433", "seqNo": "7", "title": "ก่อสร้างรางระบายน้ำคอนกรีตเสริมเหล็ก บ้านแพง"},
    {"projectId": "68119553711", "seqNo": "8", "title": "ก่อสร้างรั้วคอนกรีต บ้านแพง"},
    {"projectId": "68119515201", "seqNo": "8", "title": "ก่อสร้างลานคอนกรีต บ้านแพง"},
    {"projectId": "69019077732", "seqNo": "8", "title": "เสริมผิวแอสฟัลท์คอนกรีต"},
    {"projectId": "68129570964", "seqNo": "8", "title": "บำรุงถนนสาย นพ.3023"},
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


all_responses = []


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
        all_responses.append({"url": url, "status": resp.status, "body_json": body_json})
    except Exception:
        pass


with sync_playwright() as p:
    log("เชื่อมต่อ Chrome...")
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    log("เชื่อมต่อสำเร็จ")

    page = browser.contexts[0].new_page()
    page.on("response", on_response)

    # Navigate to ensure cookies
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

    # ===== ทดสอบ API endpoints สำหรับแต่ละ IM job =====
    for job in IM_JOBS:
        project_id = job["projectId"]
        seq_no     = job["seqNo"]
        log(f"\n{'='*50}")
        log(f"Job: {project_id} (seqNo={seq_no})")
        log(f"Title: {job['title'][:60]}")

        results = {}

        # 1. getProjectDetail
        url = f"{API_BASE}/announcement/getProjectDetail?projectId={project_id}"
        js = f"""async () => {{
            try {{
                const r = await fetch({json.dumps(url)}, {{credentials: 'include', headers: {{'Accept': 'application/json'}}}});
                const t = await r.text();
                return {{status: r.status, body: t.substring(0, 1000)}};
            }} catch(e) {{ return {{error: e.toString()}}; }}
        }}"""
        try:
            res = page.evaluate(js)
            log(f"  getProjectDetail: status={res.get('status')}")
            if res.get("body"):
                try:
                    d = json.loads(res["body"])
                    data = d.get("data", {})
                    method_id = data.get("methodId")
                    announce_type = data.get("announceType")
                    step_id = data.get("stepId")
                    log(f"    methodId={method_id}, announceType={announce_type}, stepId={step_id}")
                    results["method_id"] = method_id
                    results["announce_type"] = announce_type
                except Exception:
                    log(f"    body: {res['body'][:200]}")
        except Exception as e:
            log(f"  getProjectDetail error: {e}")

        time.sleep(0.5)

        # 2. greenBook with IM type
        method_id = results.get("method_id", "19")
        announce_type = results.get("announce_type", "IM")

        for page_type in ["IM", announce_type, "D0", ""]:
            if not page_type:
                continue
            gb_url = f"{API_BASE}/announcement/greenBook?mode=LINK&methodId={method_id}&tempProjectId={project_id}&pageAnnounceType={page_type}"
            js2 = f"""async () => {{
                try {{
                    const r = await fetch({json.dumps(gb_url)}, {{credentials: 'include', headers: {{'Accept': 'application/json'}}}});
                    const t = await r.text();
                    return {{status: r.status, body: t.substring(0, 3000)}};
                }} catch(e) {{ return {{error: e.toString()}}; }}
            }}"""
            try:
                res2 = page.evaluate(js2)
                log(f"  greenBook(pageAnnounceType={page_type}): status={res2.get('status')}")
                if res2.get("body"):
                    try:
                        d2 = json.loads(res2["body"])
                        if d2.get("response", {}).get("responseCode") == "0":
                            gb_data = d2.get("data", {})
                            links = gb_data.get("greenBookAnnouncementTypeLinkDto", [])
                            log(f"    ★ greenBookAnnouncementTypeLinkDto: {len(links)} items")
                            for item in links[:5]:
                                file_path = item.get("filePath")
                                token = item.get("token")
                                att = item.get("attachSumulate")
                                part = item.get("partFile")
                                at_type = item.get("announceType")
                                at_name = item.get("announceTypeDesc")
                                log(f"      type={at_type} ({at_name}) filePath={file_path} token={token} attach={att} part={part}")
                        else:
                            log(f"    responseCode: {d2.get('response', {}).get('responseCode')}")
                    except Exception:
                        log(f"    body: {res2['body'][:200]}")
            except Exception as e:
                log(f"  greenBook error: {e}")
            time.sleep(0.3)

        # 3. Try getDocumentList / getAttachment type endpoints
        log(f"  --- ลอง document endpoints ---")
        doc_endpoints = [
            f"{API_BASE}/announcement/getDocList?projectId={project_id}&seqNo={seq_no}",
            f"{API_BASE}/announcement/getAttachment?projectId={project_id}&seqNo={seq_no}",
            f"{API_BASE}/announcement/document?projectId={project_id}&seqNo={seq_no}",
            f"{API_BASE}/announcement/getFile?projectId={project_id}&seqNo={seq_no}",
            f"{API_BASE}/announcement/getFileAttachment?projectId={project_id}&seqNo={seq_no}",
            f"{API_BASE}/announcement/{project_id}/{seq_no}/getFile",
            # aobj19 endpoints
            f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-object/list?projectId={project_id}&seqNo={seq_no}",
            f"{PROCESS5_BASE}/egp-aobj19-service/pb/a-object/getList?projectId={project_id}&seqNo={seq_no}",
        ]
        for ep in doc_endpoints:
            js3 = f"""async () => {{
                try {{
                    const r = await fetch({json.dumps(ep)}, {{credentials: 'include', headers: {{'Accept': 'application/json'}}}});
                    const t = await r.text();
                    return {{status: r.status, body: t.substring(0, 500)}};
                }} catch(e) {{ return {{error: e.toString()}}; }}
            }}"""
            try:
                res3 = page.evaluate(js3)
                status = res3.get("status", 0)
                if status != 404:
                    body = res3.get("body", "")
                    ep_short = ep.replace(PROCESS5_BASE, "")
                    log(f"    {status} {ep_short[:80]}: {body[:100]}")
            except Exception:
                pass
            time.sleep(0.2)

        # Break after first successful job
        if results.get("method_id"):
            log(f"\n  ★ สรุป job {project_id}: methodId={results.get('method_id')}, announceType={results.get('announce_type')}")

    page.remove_listener("response", on_response)
    page.close()

log("\nเสร็จสิ้น")
