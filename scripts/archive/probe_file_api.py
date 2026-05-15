"""
probe_file_api.py — ลอง API endpoints ต่างๆ โดยตรงจาก browser context
(ใช้ cookies + XSRF token ที่มีอยู่ใน browser)

วิธีใช้:
  1. Chrome ต้องเปิด process5.gprocurement.go.th ไว้
  2. python scripts/probe_file_api.py
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PROCESS5_BASE = "https://process5.gprocurement.go.th"
SEARCH_URL    = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"

# test with known construction jobs
TEST_JOBS = [
    # projectId, seqNo, title
    ("69049122041", "7", "ก่อสร้างถนนคอนกรีตเสริมเหล็ก"),
    ("69049177433", "7", "ก่อสร้างรางระบายน้ำคอนกรีต"),
    ("68119553711", "8", "ก่อสร้างรั้วคอนกรีต บ้านแพง"),
    ("68119515201", "8", "ก่อสร้างลานคอนกรีต บ้านแพง"),
]

# Candidate endpoints (will be tested with browser's cookies)
def build_candidates(project_id, seq_no):
    base = PROCESS5_BASE
    atpj = f"{base}/egp-atpj27-service/pb/a-egp-allt-project"
    adoc = f"{base}/egp-adoc25-service/pb"
    aobj = f"{base}/egp-aobj19-service/pb"
    ator = f"{base}/egp-ator13-service/pb"
    return [
        # atpj27 variants
        f"{atpj}/announcement/{project_id}/{seq_no}/file",
        f"{atpj}/announcement/{project_id}/{seq_no}/files",
        f"{atpj}/announcement/{project_id}/{seq_no}/document",
        f"{atpj}/announcement/{project_id}/{seq_no}/attachment",
        f"{atpj}/announcement/file?projectId={project_id}&seqNo={seq_no}",
        f"{atpj}/file?projectId={project_id}&seqNo={seq_no}",
        f"{atpj}/announcement/{project_id}/{seq_no}",
        # adoc25 variants
        f"{adoc}/a-doc/announcement/{project_id}/{seq_no}/file",
        f"{adoc}/a-doc/file?projectId={project_id}&seqNo={seq_no}",
        f"{adoc}/announcement/{project_id}/{seq_no}/file",
        f"{adoc}/file?projectId={project_id}&seqNo={seq_no}",
        # aobj19 variants
        f"{aobj}/a-file/list?projectId={project_id}&seqNo={seq_no}",
        f"{aobj}/a-file/files?projectId={project_id}&seqNo={seq_no}",
        f"{aobj}/a-object/list?projectId={project_id}&seqNo={seq_no}",
        # ator13 variants
        f"{ator}/a-tor/file?projectId={project_id}&seqNo={seq_no}",
        f"{ator}/a-tor/announcement/{project_id}/{seq_no}",
    ]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


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

    # ไป process5 เพื่อให้มี cookies
    if "process5.gprocurement.go.th" not in page.url:
        log(f"navigate ไป {SEARCH_URL}")
        page.goto(SEARCH_URL, wait_until="load", timeout=45000)
        time.sleep(5)
    else:
        log(f"อยู่บน process5 แล้ว: {page.url}")

    # Test each job
    results = {}
    for project_id, seq_no, title in TEST_JOBS:
        log(f"\n{'='*60}")
        log(f"ทดสอบ job: {project_id} (seq={seq_no})")
        log(f"ชื่อ: {title}")
        candidates = build_candidates(project_id, seq_no)
        job_results = []

        for url in candidates:
            js = f"""
            async () => {{
                try {{
                    const r = await fetch({json.dumps(url)}, {{
                        credentials: 'include',
                        headers: {{
                            'Accept': 'application/json, text/plain, */*',
                        }}
                    }});
                    const text = await r.text();
                    let parsed = null;
                    try {{ parsed = JSON.parse(text); }} catch(e) {{}}
                    return {{
                        status: r.status,
                        ok: r.ok,
                        body: text.substring(0, 500),
                        parsed: parsed,
                        content_type: r.headers.get('content-type')
                    }};
                }} catch(e) {{
                    return {{status: 0, error: e.toString()}};
                }}
            }}
            """
            try:
                result = page.evaluate(js)
                status = result.get("status", 0)
                is_json = result.get("parsed") is not None

                # ตัวย่อ URL สำหรับ log
                url_short = url.replace(PROCESS5_BASE, "").replace(
                    "/egp-atpj27-service/pb/a-egp-allt-project", "[atpj27]"
                ).replace("/egp-adoc25-service/pb", "[adoc25]"
                ).replace("/egp-aobj19-service/pb", "[aobj19]"
                ).replace("/egp-ator13-service/pb", "[ator13]")

                if status == 200:
                    parsed = result.get("parsed") or {}
                    resp_code = None
                    data_len = 0
                    if isinstance(parsed, dict):
                        resp_code = parsed.get("response", {}).get("responseCode") if isinstance(parsed.get("response"), dict) else None
                        data = parsed.get("data")
                        if isinstance(data, list):
                            data_len = len(data)
                        elif isinstance(data, dict):
                            data_len = 1
                    log(f"  ✓ {status} {url_short}")
                    log(f"      responseCode={resp_code}, data_len={data_len}")
                    if data_len > 0:
                        log(f"      *** พบข้อมูล! data keys: {list(data[0].keys()) if isinstance(data, list) and data else data}")
                    job_results.append({
                        "url": url,
                        "status": status,
                        "response_code": resp_code,
                        "data_len": data_len,
                        "body": result.get("body", "")[:300],
                        "parsed": parsed,
                    })
                elif status == 404:
                    log(f"  ✗ 404 {url_short}")
                    job_results.append({"url": url, "status": 404})
                elif status == 401 or status == 403:
                    log(f"  ✗ {status} (auth) {url_short}")
                    job_results.append({"url": url, "status": status})
                else:
                    log(f"  ? {status} {url_short} — {result.get('body','')[:80]}")
                    job_results.append({"url": url, "status": status, "body": result.get("body","")[:100]})

            except Exception as e:
                log(f"  ERROR {url_short}: {e}")
                job_results.append({"url": url, "error": str(e)})

            time.sleep(0.3)

        results[project_id] = job_results

    page.close()

# บันทึกผล
out_dir = Path(__file__).parent.parent / "downloads" / "debug" / "api_probe"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"probe_{datetime.now().strftime('%H%M%S')}.json"
out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

log(f"\n{'='*60}")
log("สรุป endpoints ที่ตอบ 200:")
for proj, job_res in results.items():
    ok = [r for r in job_res if r.get("status") == 200]
    log(f"  {proj}: {len(ok)}/{len(job_res)} returned 200")
    for r in ok:
        log(f"    {r['url'].replace(PROCESS5_BASE,'')}")
        if r.get("data_len", 0) > 0:
            log(f"    ★★★ data_len={r['data_len']} ← นี่คือ endpoint ที่เราต้องการ!")

log(f"\nบันทึก: {out_path}")
