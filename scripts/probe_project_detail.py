"""
probe_project_detail.py — Probe getProjectDetail response shape
หา field name ที่มี dept_name (ชื่อหน่วยงาน)
"""
import sys
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from Sebastian_Scraper import connect_browser

PROCESS5_BASE = "https://process5.gprocurement.go.th"

JS_FETCH = """async (url) => {
    try {
        const r = await fetch(url, {credentials: 'include'});
        return await r.json();
    } catch(e) { return {error: e.toString()}; }
}"""


def main():
    catalog = json.load(open(Path(__file__).parent.parent / "data" / "egp_deptid_catalog.json", encoding="utf-8"))
    # Find a sample projectId from an active dept
    sample_pid = None
    sample_dept = None
    for d, info in catalog.items():
        if info.get("projectIds"):
            sample_pid = info["projectIds"][0]
            sample_dept = d
            break
    if not sample_pid:
        print("❌ ไม่พบ projectId ใน catalog")
        return

    print(f"Probing dept={sample_dept} projectId={sample_pid}")

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto(f"{PROCESS5_BASE}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(3)

        url = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement/getProjectDetail?projectId={sample_pid}"
        body = page.evaluate(JS_FETCH, url)

        print("\n=== Full response ===")
        print(json.dumps(body, ensure_ascii=False, indent=2))

        if isinstance(body, dict) and "data" in body:
            data = body["data"]
            print("\n=== Field keys in 'data' ===")
            if isinstance(data, dict):
                for k, v in data.items():
                    v_str = str(v)[:100]
                    print(f"  {k}: {v_str}")

        # Save full response for analysis
        out = Path(__file__).parent.parent / "data" / "probe_project_detail_response.json"
        out.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ Saved full response → {out}")

        page.close()


if __name__ == "__main__":
    main()
