"""
research_scraper_optimization.py — Deep research for fastest eGP scraping

Phases:
  R1: Probe hidden/bulk endpoints (sumProject, exportData, allProjects, etc.)
  R2: Test pagination size + filters (page size up to 1000?)
  R3: Network analysis (check what other paths exist)
  R4: Look at sitemap/robots.txt
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

PROCESS5 = "https://process5.gprocurement.go.th"
BASE     = f"{PROCESS5}/egp-atpj27-service/pb/a-egp-allt-project/announcement"
OUT      = Path("data/scraper_research.json")


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def probe(page, url, label):
    """Probe URL → return {status, body_preview, json_keys, error}"""
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            const text = await r.text();
            const ct = r.headers.get('content-type') || '';
            try {
                const body = JSON.parse(text);
                return {status: r.status, ct: ct, body: body, text_len: text.length};
            } catch {
                return {status: r.status, ct: ct, preview: text.slice(0, 500), text_len: text.length};
            }
        } catch(e) { return {error: e.toString()}; }
    }"""
    log(f"  → {label}")
    res = page.evaluate(js, url)
    return res


def phase_r1_hidden_endpoints(page):
    """ลอง endpoint patterns ที่อาจเป็น bulk/export"""
    log("\n========== R1: Hidden bulk endpoints ==========")
    candidates = [
        # Bulk / export patterns
        f"{BASE}/getAllProjects",
        f"{BASE}/exportData",
        f"{BASE}/exportProjects",
        f"{BASE}/bulkSearch",
        f"{BASE}/sumProject",  # known to exist (filtered out in Scraper)
        f"{BASE}/sumProject?methodId=16",
        f"{BASE}/listProject",
        f"{BASE}/getProjects",
        f"{BASE}/searchProjects",
        # Different services
        f"{PROCESS5}/egp-atpj27-service/pb/a-egp-allt-project/api/all",
        f"{PROCESS5}/egp-atpj27-service/pb/a-egp-allt-project/api/list",
        # OpenAPI / Swagger discovery
        f"{PROCESS5}/egp-atpj27-service/v3/api-docs",
        f"{PROCESS5}/egp-atpj27-service/swagger-ui.html",
        f"{PROCESS5}/egp-atpj27-service/api-docs",
        # Try root paths
        f"{PROCESS5}/egp-atpj27-service/actuator",
        f"{PROCESS5}/egp-atpj27-service/health",
        # Sitemap / robots
        f"{PROCESS5}/robots.txt",
        f"{PROCESS5}/sitemap.xml",
        f"{PROCESS5}/egp-agpc01-web/sitemap.xml",
    ]
    results = {}
    for url in candidates:
        label = url.replace(PROCESS5, "")[:60]
        r = probe(page, url, label)
        status = r.get("status", "ERR")
        text_len = r.get("text_len", 0)
        has_body = "body" in r
        results[url] = {"status": status, "json": has_body, "len": text_len}
        if status not in (404, 405, None) and status != "ERR":
            log(f"    ✅ status={status} json={has_body} len={text_len}")
            if has_body and isinstance(r["body"], dict):
                keys = list(r["body"].keys())[:10]
                log(f"       keys: {keys}")
            elif "preview" in r:
                log(f"       preview: {r['preview'][:150]}")
        time.sleep(0.8)
    return results


def phase_r2_pagination(page):
    """ลอง page size ใหญ่ๆ — default 10, ลอง 50, 100, 500, 1000"""
    log("\n========== R2: Pagination size limits ==========")
    # ใช้ keyword ที่รู้ว่าเจอเยอะ เช่น "นครพนม"
    base_url = f"{BASE}?keyword=นครพนม&methodId=16&page=1"
    results = {}
    for size in [10, 20, 50, 100, 200, 500, 1000]:
        url = f"{base_url}&size={size}"
        r = probe(page, url, f"size={size}")
        if "body" in r:
            d = r["body"].get("data", {})
            items = d.get("data", [])
            total = d.get("totalRecords") or d.get("totalCount") or d.get("total")
            results[size] = {
                "items_returned": len(items),
                "total_records": total,
                "text_len": r.get("text_len"),
            }
            log(f"    size={size}: returned {len(items)}, total={total}, text_len={r.get('text_len')}")
        else:
            results[size] = {"error": r.get("error") or r.get("status")}
            log(f"    size={size}: error")
        time.sleep(1.5)
    return results


def phase_r3_param_discovery(page):
    """ลอง parameters อื่น: dateFrom, dateTo, lastUpdate, since"""
    log("\n========== R3: Parameter discovery ==========")
    test_params = [
        f"{BASE}?keyword=นครพนม&methodId=16&dateFrom=2026-05-01",
        f"{BASE}?keyword=นครพนม&methodId=16&since=2026-05-15",
        f"{BASE}?keyword=นครพนม&methodId=16&lastDays=7",
        f"{BASE}?keyword=นครพนม&methodId=16&modifiedAfter=2026-05-15",
        f"{BASE}?methodId=16&page=1&size=100",  # no keyword
        f"{BASE}?methodId=16&province=NAKHON_PHANOM",
        f"{BASE}?methodId=16&provinceId=48",  # นครพนม
    ]
    results = {}
    for url in test_params:
        label = url.split("?")[1][:80]
        r = probe(page, url, label)
        if "body" in r:
            d = r["body"].get("data", {})
            total = d.get("totalRecords") or d.get("totalCount")
            items = d.get("data", [])
            results[url] = {"total": total, "items": len(items)}
            log(f"    total={total}, items={len(items)}")
        else:
            results[url] = {"error": r.get("status")}
        time.sleep(1.5)
    return results


def phase_r4_check_other_services(page):
    """ลองบริการอื่นที่อาจเป็น bulk source"""
    log("\n========== R4: Other eGP services ==========")
    candidates = [
        "https://www.gprocurement.go.th",
        "https://www.gprocurement.go.th/sitemap.xml",
        "https://www.gprocurement.go.th/robots.txt",
        # Old EGP system
        "https://process3.gprocurement.go.th",
        # Open data
        "https://data.go.th/dataset/gprocurement",
        # Common government bulk patterns
        f"{PROCESS5}/egp-atpj27-service/pb/a-egp-allt-project/announcement/getRecentlyUpdated",
        f"{PROCESS5}/egp-atpj27-service/pb/a-egp-allt-project/announcement/getNewToday",
    ]
    results = {}
    for url in candidates:
        label = url.replace("https://", "")[:80]
        r = probe(page, url, label)
        results[url] = {"status": r.get("status"), "json": "body" in r, "len": r.get("text_len")}
        if r.get("status") and r["status"] not in (404, 405):
            log(f"    ✅ {label}: status={r.get('status')}")
        time.sleep(1.5)
    return results


def main():
    log("=" * 60)
    log("Scraper Optimization Research")
    log("=" * 60)

    all_results = {}
    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        log("Loading process5...")
        page.goto(f"{PROCESS5}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(8)

        all_results["r1_hidden_endpoints"] = phase_r1_hidden_endpoints(page)
        time.sleep(5)

        all_results["r2_pagination"] = phase_r2_pagination(page)
        time.sleep(5)

        all_results["r3_params"] = phase_r3_param_discovery(page)
        time.sleep(5)

        all_results["r4_other_services"] = phase_r4_check_other_services(page)

        page.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nSaved → {OUT}")

    # Analyze + highlight wins
    log("\n========== ANALYSIS ==========")

    # R1: any non-404 endpoint
    r1 = all_results["r1_hidden_endpoints"]
    wins_r1 = [(u, info) for u, info in r1.items() if info.get("status") not in (404, 405, None) and info.get("status") != "ERR"]
    log(f"\nR1 — Working endpoints: {len(wins_r1)}")
    for u, info in wins_r1:
        log(f"  {u.replace(PROCESS5, '')[:80]}: status={info['status']} len={info['len']}")

    # R2: max items per page
    r2 = all_results["r2_pagination"]
    log(f"\nR2 — Pagination test:")
    max_size = 10
    for size, info in r2.items():
        if isinstance(info, dict) and info.get("items_returned", 0) > 10:
            max_size = max(max_size, info["items_returned"])
            log(f"  ✅ size={size}: got {info['items_returned']} items!")
    log(f"  → Effective max page size: {max_size}")
    if max_size > 10:
        log(f"  💡 SPEEDUP: current Scraper uses size=10, could use {max_size} → {max_size/10:.0f}x faster!")


if __name__ == "__main__":
    main()
