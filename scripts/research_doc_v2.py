"""Phase 5b: ลอง navigate ผ่าน SPA route หลายแบบ + spy network"""
import sys, json, time
from pathlib import Path
from collections import Counter
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

PROCESS5 = "https://process5.gprocurement.go.th"
OUT = Path("data/doc_endpoint_research_v2.json")


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def spy_load(page, url, label, wait=10):
    log(f"\n  Trying {label}: {url[:80]}")
    reqs = []

    def on_req(req):
        u = req.url
        if "egp" in u.lower() and any(k in u.lower() for k in ["service", "api", "file", "atpj", "amaq", "agpc"]):
            reqs.append({"method": req.method, "url": u[:300]})

    page.on("request", on_req)
    try:
        page.goto(url, wait_until="networkidle", timeout=15000)
        time.sleep(wait)
    except Exception as e:
        log(f"    error: {str(e)[:100]}")
    page.remove_listener("request", on_req)
    return reqs


def main():
    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()

        # 1. Start at search to bootstrap session
        log("Bootstrapping session...")
        page.goto(f"{PROCESS5}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(5)

        jid = "69049094319"
        results = {}

        # Try several SPA URL patterns
        patterns = [
            f"{PROCESS5}/egp-agpc01-web/announcement;projectId={jid}",
            f"{PROCESS5}/egp-agpc01-web/detail/{jid}",
            f"{PROCESS5}/egp-agpc01-web/announcement/{jid}",
            f"{PROCESS5}/egp-agpc01-web/project/{jid}",
            f"{PROCESS5}/egp-agpc01-web/announcement/view?projectId={jid}",
            f"{PROCESS5}/egp-agpc01-web/announcement/detail?projectId={jid}",
            f"{PROCESS5}/egp-agpc01-web/#/announcement/detail/{jid}",
            f"{PROCESS5}/egp-agpc01-web/#/detail/{jid}",
        ]
        for url in patterns:
            reqs = spy_load(page, url, f"pattern{patterns.index(url)+1}", wait=5)
            unique_paths = set()
            for r in reqs:
                path = r["url"].split("?")[0]
                if "egp-agpc01-web" not in path and "egp-atpj27" not in path.split("?")[0]:
                    unique_paths.add(path)
                elif "egp-atpj27" in path and "announcement" not in path:
                    unique_paths.add(path)
            log(f"    captured {len(reqs)} req, {len(unique_paths)} unique non-trivial paths")
            for p_ in list(unique_paths)[:10]:
                log(f"      {p_[:120]}")
            results[url] = {"requests": reqs, "unique_paths": list(unique_paths)}

        # 2. Try clicking a result on search page
        log("\n=== Click-through from search ===")
        page.goto(f"{PROCESS5}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(5)

        # Type keyword
        search_input = None
        for sel in ["input[name*='keyword']", "input[placeholder*='ค้นหา']", "input[type='search']"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    search_input = el
                    break
            except Exception:
                pass

        if search_input:
            search_input.click()
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.keyboard.type(jid, delay=60)
            time.sleep(1)

            # Click search button
            try:
                page.locator("button:has-text('ค้นหา')").first.click(timeout=8000)
                time.sleep(5)
            except Exception as e:
                log(f"  search click failed: {e}")

            # Try clicking the result
            click_reqs = []
            def on_req2(req):
                u = req.url
                if "egp" in u.lower():
                    click_reqs.append(u[:200])
            page.on("request", on_req2)

            try:
                # Try various clickables
                for sel in [
                    "a:has-text('รายละเอียด')",
                    "a:has-text('ดูรายละเอียด')",
                    "button:has-text('รายละเอียด')",
                    "tr:has-text('69049094319') a",
                    "td a",
                    f"a[href*='{jid}']",
                ]:
                    try:
                        el = page.query_selector(sel)
                        if el:
                            log(f"  Found clickable: {sel}")
                            el.click()
                            time.sleep(5)
                            break
                    except Exception:
                        pass
            except Exception as e:
                log(f"  click error: {e}")

            page.remove_listener("request", on_req2)
            log(f"  after-click captured {len(click_reqs)} requests")
            click_paths = set(r.split("?")[0] for r in click_reqs)
            for p_ in click_paths:
                log(f"    {p_[:150]}")
            results["__click_through__"] = {"requests": click_reqs, "paths": list(click_paths)}

        page.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nSaved → {OUT}")


if __name__ == "__main__":
    main()
