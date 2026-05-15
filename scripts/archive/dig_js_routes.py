"""
dig_js_routes.py — ดึง JS bundle มาค้นหา:
1. Route definitions (path: '...')
2. API calls ใน detail component
3. File service calls

วิธีใช้: python scripts/dig_js_routes.py
"""
import sys, re, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

SEARCH_URL = "https://process5.gprocurement.go.th/egp-agpc01-web/announcement"
OUT_DIR = Path(__file__).parent.parent / "downloads" / "debug" / "js_dig"
OUT_DIR.mkdir(parents=True, exist_ok=True)

js_bodies = {}

with sync_playwright() as p:
    print("เชื่อมต่อ Chrome...", flush=True)
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].new_page()

    def on_resp(resp):
        url = resp.url
        if "agpc01-web" in url and ".js" in url and "map" not in url:
            try:
                body = resp.text()
                if len(body) > 3000:
                    js_bodies[url] = body
                    print(f"  JS: {url.split('/')[-1]} ({len(body):,} chars)", flush=True)
            except Exception:
                pass

    page.on("response", on_resp)
    page.goto(SEARCH_URL, wait_until="load", timeout=45000)
    time.sleep(5)
    page.close()

full_js = "\n".join(js_bodies.values())
print(f"\nTotal JS: {len(full_js):,} chars from {len(js_bodies)} files\n")

# ===== 1. Angular route paths =====
print("="*60)
print("=== ANGULAR ROUTE PATHS (path:) ===")
route_hits = re.findall(r'path\s*:\s*["\']([^"\']{1,80})["\']', full_js)
seen = set()
for h in route_hits:
    if h not in seen and any(x in h.lower() for x in
            ["detail", "announce", "file", "doc", "tor", "view", "info", "down"]):
        seen.add(h)
        print(f"  path: '{h}'")

# ===== 2. All route paths =====
print("\n=== ALL ROUTE PATHS ===")
seen2 = set()
for h in route_hits:
    if h not in seen2 and len(h) > 1 and not h.startswith("http"):
        seen2.add(h)
        print(f"  '{h}'")

# ===== 3. HTTP calls in detail context =====
print("\n=== HTTP GET/POST calls near 'projectId' ===")
# Find code blocks containing projectId and http calls
contexts = re.findall(r'.{0,200}projectId.{0,200}', full_js)
http_contexts = [c for c in contexts if any(x in c for x in
    ["this.http", "HttpClient", ".get(", ".post(", "fetch(", "subscribe"])]
seen3 = set()
for c in http_contexts[:20]:
    c = c.strip()
    if c not in seen3:
        seen3.add(c)
        print(f"  {c[:200]}")
        print()

# ===== 4. service URL variables near 'file' =====
print("=== SERVICE URL near 'file'/'doc'/'attach' ===")
service_hits = re.findall(r'.{0,100}(?:file|doc|attach|upload|download).{0,100}', full_js, re.IGNORECASE)
url_hits = [h for h in service_hits if any(x in h for x in ["/egp-", "service_url", "environment"])]
seen4 = set()
for h in url_hits[:30]:
    h = h.strip()
    if h not in seen4 and len(h) > 20:
        seen4.add(h)
        print(f"  {h[:180]}")

# ===== 5. `atpj27` paths — full list =====
print("\n=== atpj27 PATHS (all unique) ===")
atpj_hits = re.findall(r'["\`]/(?:egp-atpj27-service/pb/[^"\`\s]{3,80})["\`]', full_js)
seen5 = set()
for h in sorted(set(atpj_hits)):
    print(f"  {h}")

# ===== 6. `aobj19` paths — all =====
print("\n=== aobj19 PATHS (all unique) ===")
aobj_hits = re.findall(r'["\`]/(?:egp-aobj19-service/pb/[^"\`\s]{3,80})["\`]', full_js)
for h in sorted(set(aobj_hits)):
    print(f"  {h}")

# ===== 7. adoc25 paths =====
print("\n=== adoc25 PATHS ===")
adoc_hits = re.findall(r'["\`]/(?:egp-adoc25-service/pb/[^"\`\s]{3,80})["\`]', full_js)
for h in sorted(set(adoc_hits)):
    print(f"  {h}")

# ===== 8. All service paths combined =====
print("\n=== ALL SERVICE PATHS (/egp-...) ===")
all_svc = re.findall(r'["\`](/egp-[a-z0-9]+-service/pb/[^"\`\s]{5,100})["\`]', full_js)
seen6 = set()
for h in sorted(set(all_svc)):
    seen6.add(h)
    print(f"  {h}")

# ===== 9. Template literals with service calls =====
print("\n=== TEMPLATE LITERAL SERVICE CALLS ===")
template_hits = re.findall(r'`\$\{[^}]+\}([^`\$]{3,80})`', full_js)
svc_templates = [t for t in template_hits if any(x in t for x in
    ["/pb/", "/file", "/doc", "/attach", "/download", "announce"])]
seen7 = set()
for h in svc_templates[:30]:
    if h not in seen7:
        seen7.add(h)
        print(f"  `...{h}`")

# ===== 10. Save full JS for manual inspection =====
# (too large to save all, save just interesting files)
for url, body in js_bodies.items():
    fname = url.split("/")[-1].split("?")[0]
    if len(body) > 50000:  # save large files
        out_path = OUT_DIR / fname
        out_path.write_text(body, encoding="utf-8", errors="replace")
        print(f"\nบันทึก JS: {fname} ({len(body):,} chars)")
