"""
research_doc_endpoints.py — Phase 5: หา API endpoint สำหรับเอกสารใน eGP

Strategy:
1. ลอง 30+ endpoint patterns ใน egp-atpj27-service (ที่เรารู้)
2. ลอง services อื่นที่เป็น standard eGP: egp-amaq01, egp-amfb01, egp-asf01, egp-ada01
3. Navigate to project detail page → spy DOM/network for file download URLs

Sample jobs (each different stage):
- S01 (active bidding)
- W03 (winner announced)
- C01 (contract)
- U03 (consultation)
- M03 (post-consultation pre-bidding)
"""
import sys, json, time
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

PROCESS5 = "https://process5.gprocurement.go.th"
OUT = Path(__file__).parent.parent / "data" / "doc_endpoint_research.json"


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


# Endpoint patterns to try
ENDPOINT_PATTERNS = [
    # egp-atpj27 (current known service)
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/getProjectFiles",
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/getAttachments",
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/listAttachment",
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/getAnnounceFiles",
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/listAnnouncement",
    "/egp-atpj27-service/pb/a-egp-allt-project/file/getProjectFile",
    "/egp-atpj27-service/pb/a-egp-allt-project/file/list",
    "/egp-atpj27-service/pb/a-egp-allt-project/document/list",
    "/egp-atpj27-service/pb/a-egp-allt-project/file/getProject",
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/getDocumentByProjectId",
    # Other eGP services
    "/egp-amaq01-service/pb/announcement/getFiles",
    "/egp-amaq01-service/pb/announcement/getProjectDocuments",
    "/egp-amfb01-service/pb/announcement/getFiles",
    "/egp-asf01-service/pb/announcement/getFiles",
    "/egp-ada01-service/pb/announcement/getFiles",
    "/egp-atpj27-service/pb/project/getFile",
    "/egp-atpj27-service/pb/project/getDocument",
    "/egp-atpj27-service/pb/project/getAnnouncement",
    "/egp-atpj27-service/pb/project/files",
    # patterns with project param in path
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/PROJECT_ID/files",
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/PROJECT_ID/documents",
    # TOR-related
    "/egp-atpj27-service/pb/a-egp-allt-project/tor/getList",
    "/egp-atpj27-service/pb/a-egp-allt-project/tor/getFile",
    # BOQ-related
    "/egp-atpj27-service/pb/a-egp-allt-project/boq/getFile",
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement/getBoq",
]

# Sample jobs from different stages
SAMPLES = {
    "69049094319": "S01 - active bidding",
    "69039325763": "W03 - winner announced",
    "68109395450": "C01 - contract",
    "69059074818": "U03 - consultation",
    "69049365887": "M03 - post-consultation",
}


def probe_endpoints(page, jid: str) -> dict:
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            const text = await r.text();
            try { return {status: r.status, body: JSON.parse(text)}; }
            catch { return {status: r.status, preview: text.slice(0, 300)}; }
        } catch(e) { return {error: e.toString()}; }
    }"""
    results = {}
    for pattern in ENDPOINT_PATTERNS:
        url = PROCESS5 + pattern
        if "PROJECT_ID" in url:
            url = url.replace("PROJECT_ID", jid)
        else:
            url += f"?projectId={jid}"
        res = page.evaluate(js, url)
        # Save key info only
        results[pattern] = {
            "status": res.get("status"),
            "has_body": "body" in res,
            "preview": (res.get("preview", "") or str(res.get("body", ""))[:200])[:200],
        }
        time.sleep(0.5)
    return results


def spy_detail_page(page, jid: str) -> dict:
    """Navigate to project detail page → capture all network requests"""
    log(f"  Navigate to detail page for {jid}...")

    requests = []
    def on_req(req):
        if "egp" in req.url.lower() or ".pdf" in req.url.lower() or "file" in req.url.lower():
            requests.append({
                "method": req.method,
                "url": req.url[:300],
                "resource_type": req.resource_type,
            })

    page.on("request", on_req)
    try:
        # Try common detail URL patterns
        detail_url = f"{PROCESS5}/egp-agpc01-web/announcement/detail/{jid}"
        page.goto(detail_url, wait_until="networkidle", timeout=20000)
        time.sleep(3)
    except Exception as e:
        log(f"  Detail page error: {e}")

    page.remove_listener("request", on_req)

    # Look for download links in DOM
    download_links = []
    try:
        links = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('a').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (href.includes('file') || href.includes('download') || href.endsWith('.pdf') || href.endsWith('.zip')) {
                    out.push({href: href.slice(0, 200), text: (a.textContent || '').trim().slice(0, 80)});
                }
            });
            return out;
        }""")
        download_links = links or []
    except Exception:
        pass

    return {
        "captured_requests": requests[:50],  # cap
        "download_links": download_links[:30],
    }


def main():
    log("=" * 60)
    log("Phase 5: Deep document endpoint probe")
    log("=" * 60)

    results = {}
    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto(f"{PROCESS5}/egp-agpc01-web/announcement",
                  wait_until="load", timeout=45000)
        time.sleep(5)

        for jid, label in SAMPLES.items():
            log(f"\n{jid} ({label})")
            ep_results = probe_endpoints(page, jid)
            valid = {k: v for k, v in ep_results.items() if v.get("status") not in (None, 404, 405)}
            log(f"  endpoint results: {len(valid)} non-404 / {len(ep_results)} tried")
            for ep, r in valid.items():
                log(f"    ✓ {ep}: status={r['status']}")
                log(f"      preview: {r['preview'][:120]}")

            spy = spy_detail_page(page, jid)
            log(f"  spy: {len(spy['captured_requests'])} requests, {len(spy['download_links'])} dom links")
            if spy['download_links']:
                for l in spy['download_links'][:5]:
                    log(f"    link: {l['text'][:40]} → {l['href'][:80]}")

            results[jid] = {
                "label": label,
                "endpoint_results": ep_results,
                "spy_results": spy,
            }
            time.sleep(2)

        page.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nSaved → {OUT}")


if __name__ == "__main__":
    main()
