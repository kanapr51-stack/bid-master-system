"""
research_province_search.py — Test province-only search strategy

Hypothesis: 2 queries (นครพนม + บึงกาฬ) อาจดึงงานได้เทียบเท่า 28 ตำบล queries
→ 14x faster
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


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def fetch_with_retry(page, url, label, max_retries=2):
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            const text = await r.text();
            try { return {status: r.status, body: JSON.parse(text), text_len: text.length}; }
            catch { return {status: r.status, raw: text.slice(0, 300), text_len: text.length}; }
        } catch(e) { return {error: e.toString()}; }
    }"""
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = 60 if "Rate" in str(prev) else 30
            log(f"  retry {attempt}/{max_retries} after {wait}s...")
            time.sleep(wait)
        prev = page.evaluate(js, url)
        if "body" in prev:
            return prev
        if isinstance(prev, dict) and "raw" in prev and "Rate" not in str(prev.get("raw", "")):
            return prev
    return prev


def main():
    log("=" * 60)
    log("Province-only search test")
    log("=" * 60)

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto(f"{PROCESS5}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(8)

        results = {}
        for province in ["นครพนม", "บึงกาฬ"]:
            log(f"\n=== Search: {province} (methodId=16 e-bidding only) ===")
            # First page to get totalRecords
            url = f"{BASE}?keyword={province}&methodId=16&page=1"
            r = fetch_with_retry(page, url, f"page 1 of {province}")
            if "body" not in r:
                log(f"  ❌ failed: {r}")
                continue

            d = r["body"].get("data", {})
            items = d.get("data", [])
            total = d.get("totalRecords") or d.get("totalCount") or d.get("total")
            text_len = r.get("text_len", 0)
            log(f"  page 1: {len(items)} items, total={total}, text_len={text_len}")
            log(f"  data keys: {list(d.keys())[:10]}")

            results[province] = {
                "page1_items": len(items),
                "total": total,
                "text_len_per_page": text_len,
                "sample_first_jid": items[0].get("projectId") if items else None,
                "sample_first_title": items[0].get("projectName", "")[:60] if items else None,
            }

            time.sleep(5)

            # Try page 2
            url2 = f"{BASE}?keyword={province}&methodId=16&page=2"
            r2 = fetch_with_retry(page, url2, f"page 2 of {province}")
            if "body" in r2:
                items2 = r2["body"].get("data", {}).get("data", [])
                log(f"  page 2: {len(items2)} items")
                results[province]["page2_items"] = len(items2)

            time.sleep(10)

        page.close()

    # Analysis
    log("\n========== ANALYSIS ==========")
    total_all = 0
    for prov, info in results.items():
        if "total" in info and info["total"]:
            log(f"  {prov}: total={info['total']} e-bidding jobs")
            total_all += info["total"]
    log(f"\n  Combined total: {total_all} e-bidding jobs in target provinces")

    if total_all > 0:
        pages_needed = (total_all + 9) // 10  # 10 per page
        log(f"  Pages needed (size=10): {pages_needed}")
        log(f"  Time estimate (parallel batch 20, cooldown 90s/80pages):")
        groups = (pages_needed + 79) // 80
        time_est = groups * 95  # 5s for batch + 90s cooldown
        log(f"    ~{time_est}s = {time_est/60:.1f} min")
        log(f"\n  COMPARED TO current (28 keywords × ~3 min = ~85 min):")
        log(f"  Speedup: {85*60/time_est:.1f}x")

    # Save
    OUT = Path("data/province_search_test.json")
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nSaved → {OUT}")


if __name__ == "__main__":
    main()
