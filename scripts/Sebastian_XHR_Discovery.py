"""
Sebastian_XHR_Discovery.py — eGP endpoint discovery via Playwright

Visits key eGP pages, intercepts ALL network requests (XHR, Fetch, Doc, Other),
captures JSON/XML responses, and saves structured report for analysis.

ChatGPT tip: Thai gov legacy systems hide endpoints in form POST / servlet /
iframe loads — don't filter XHR/Fetch only, capture everything with a body.

Output: data/xhr_discovery_TIMESTAMP.json
Usage:
  python scripts/Sebastian_XHR_Discovery.py
  python scripts/Sebastian_XHR_Discovery.py --headless   # for GHA
"""
import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlencode

DATA_DIR   = Path(__file__).parent.parent / "data"
REPORT_DIR = Path(__file__).parent.parent / "data"

# Pages to visit and actions to perform on each
DISCOVERY_PLAN = [
    {
        "label":  "process_portal_root",
        "url":    "https://process.gprocurement.go.th/",
        "actions": [],
        "reason": "Parent of RSS feed — may have listing pages",
    },
    {
        "label":  "rss_feed_parent",
        "url":    "https://process.gprocurement.go.th/EPROCRssFeedWeb/",
        "actions": [],
        "reason": "RSS webapp root — other servlets may live here",
    },
    {
        "label":  "egp_main_portal",
        "url":    "https://www.gprocurement.go.th/wps/portal/egp/",
        "actions": [],
        "reason": "Main eGP portal — announcement listing expected",
    },
    {
        "label":  "egp_announce_list",
        "url":    "https://www.gprocurement.go.th/wps/portal/egp/announce",
        "actions": [],
        "reason": "Direct guess at announcement listing route",
    },
    {
        "label":  "process_announce_search",
        "url":    "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml",
        "actions": [],
        "reason": "Known RSS endpoint — verify what other requests it triggers",
    },
]

# ── Filters ──────────────────────────────────────────────────────────────────

# MIME types worth capturing response body for
CAPTURE_MIME = {
    "application/json", "text/json",
    "application/xml", "text/xml", "application/rss+xml",
    "text/html",           # forms + iframes load HTML with data
    "application/x-www-form-urlencoded",
}

# URL patterns that are always noise
SKIP_URL_PATTERNS = [
    r"\.(png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|css|map)(\?|$)",
    r"google-analytics", r"googletagmanager", r"doubleclick",
    r"facebook\.com", r"twitter\.com",
]
_skip_re = re.compile("|".join(SKIP_URL_PATTERNS), re.I)

# Keywords that strongly suggest interesting endpoints
INTERESTING_KEYWORDS = [
    "project", "announce", "procure", "bid", "tender",
    "search", "list", "result", "award", "winner",
    "egp", "dept", "org", "feed", "rss", "api", "json",
    "page", "offset", "limit", "filter", "query",
]


def _score_url(url: str) -> int:
    """Heuristic score: higher = more interesting endpoint."""
    score = 0
    url_lower = url.lower()
    for kw in INTERESTING_KEYWORDS:
        if kw in url_lower:
            score += 1
    if any(x in url_lower for x in ["json", "xml", "api", "feed"]):
        score += 3
    if any(x in url_lower for x in ["page=", "offset=", "limit=", "from=", "since="]):
        score += 2   # pagination indicators
    return score


def _truncate(text: str, n: int = 800) -> str:
    return text[:n] + "…" if len(text) > n else text


# ── Playwright session ────────────────────────────────────────────────────────

async def discover_page(page, entry: dict) -> list[dict]:
    """Navigate to URL, perform actions, return list of captured request records."""
    captured: list[dict] = []

    async def on_response(response):
        url = response.url
        if _skip_re.search(url):
            return
        try:
            status       = response.status
            content_type = response.headers.get("content-type", "")
            method       = response.request.method
            req_type     = response.request.resource_type   # xhr, fetch, document, other …

            body_text = ""
            for mime in CAPTURE_MIME:
                if mime in content_type.lower():
                    try:
                        body_text = await response.text()
                    except Exception:
                        pass
                    break

            record = {
                "url":          url,
                "method":       method,
                "type":         req_type,
                "status":       status,
                "content_type": content_type,
                "body_preview": _truncate(body_text, 600) if body_text else "",
                "score":        _score_url(url),
            }
            captured.append(record)
        except Exception:
            pass

    page.on("response", on_response)

    print(f"\n[discover] -> {entry['label']}: {entry['url']}")
    try:
        await page.goto(entry["url"], wait_until="networkidle", timeout=20_000)
    except Exception as e:
        print(f"  ⚠ goto failed: {e}")

    # Extra wait for lazy-loaded XHR
    await asyncio.sleep(2)

    # Perform any scripted actions (scroll, click search, etc.)
    for action in entry.get("actions", []):
        try:
            if action["type"] == "scroll":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
            elif action["type"] == "click":
                await page.click(action["selector"], timeout=5000)
                await asyncio.sleep(2)
            elif action["type"] == "fill_and_submit":
                await page.fill(action["selector"], action["value"])
                await page.keyboard.press("Enter")
                await asyncio.sleep(3)
        except Exception as e:
            print(f"  ⚠ action failed ({action}): {e}")

    page.remove_listener("response", on_response)
    print(f"  captured {len(captured)} requests")
    return captured


async def run_discovery(headless: bool = True) -> Path:
    from playwright.async_api import async_playwright

    all_records: list[dict] = []
    errors: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
            },
        )
        page = await context.new_page()

        for entry in DISCOVERY_PLAN:
            try:
                records = await discover_page(page, entry)
                for r in records:
                    r["page_label"] = entry["label"]
                    r["page_reason"] = entry["reason"]
                all_records.extend(records)
            except Exception as e:
                msg = f"{entry['label']}: {e}"
                errors.append(msg)
                print(f"  [ERR] {msg}")

        await browser.close()

    # ── Deduplicate + rank ────────────────────────────────────────────────────
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for r in all_records:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            deduped.append(r)

    deduped.sort(key=lambda r: -r["score"])

    # ── Split findings ────────────────────────────────────────────────────────
    high_value   = [r for r in deduped if r["score"] >= 3]
    medium_value = [r for r in deduped if 1 <= r["score"] < 3]
    low_value    = [r for r in deduped if r["score"] == 0]

    # ── JSON report ──────────────────────────────────────────────────────────
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    out     = DATA_DIR / f"xhr_discovery_{ts}.json"
    report  = {
        "discovered_at": datetime.now().isoformat(timespec="seconds"),
        "pages_visited": len(DISCOVERY_PLAN),
        "total_requests": len(all_records),
        "unique_urls": len(deduped),
        "errors": errors,
        "high_value_endpoints": high_value,
        "medium_value_endpoints": medium_value,
        "low_value_endpoints": low_value,
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Console summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Discovery complete: {len(deduped)} unique URLs")
    print(f"  High-value  (score≥3): {len(high_value)}")
    print(f"  Medium      (score 1-2): {len(medium_value)}")
    print(f"  Low/noise   (score 0): {len(low_value)}")
    print(f"  Errors: {len(errors)}")
    print(f"\nReport: {out}")

    if high_value:
        print("\n=== HIGH VALUE ENDPOINTS ===")
        for r in high_value[:20]:
            print(f"  [{r['type']:8s}] {r['status']}  score={r['score']}  {r['url'][:100]}")
            if r["body_preview"]:
                print(f"            {r['body_preview'][:120]}")

    return out


def main():
    parser = argparse.ArgumentParser(description="eGP XHR endpoint discovery")
    parser.add_argument("--headless", action="store_true", default=False,
                        help="Run browser headless (default: visible for debugging)")
    args = parser.parse_args()

    out = asyncio.run(run_discovery(headless=args.headless))
    print(f"\nDone → {out}")


if __name__ == "__main__":
    main()
