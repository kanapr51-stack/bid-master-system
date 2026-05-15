"""ค้นหา service URLs และ file list endpoints"""
import sys, re, time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].new_page()
    js_bodies = {}

    def on_resp(resp):
        url = resp.url
        if "agpc01-web" in url and ".js" in url and "map" not in url:
            try:
                body = resp.text()
                if len(body) > 5000:
                    js_bodies[url] = body
            except Exception:
                pass

    page.on("response", on_resp)
    page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
              wait_until="load", timeout=45000)
    time.sleep(5)
    page.close()

full_js = "\n".join(js_bodies.values())
print(f"Captured {len(js_bodies)} files, {len(full_js):,} chars")

# 1. หา service URLs (merchant, upload etc)
print("\n=== SERVICE URL PATTERNS ===")
svc_hits = re.findall(r'egp_all_\w+_url["\s]*[:=]["\s]*\w+\+["\s]*"([^"]{5,50})"', full_js)
for h in sorted(set(svc_hits)):
    print(" ", h)

# 2. หา environment.link.*
print("\n=== ENVIRONMENT LINKS ===")
env_hits = re.findall(r'environment\.(?:link\.)?\w+\s*\+\s*`([^`]{5,80})`', full_js)
for h in sorted(set(env_hits))[:30]:
    print(" ", h)

# 3. ค้นหา "merchant" context
print("\n=== MERCHANT SERVICE CONTEXT ===")
merchant_hits = re.findall(r'.{0,80}merchant.{0,80}', full_js, re.IGNORECASE)
seen = set()
for h in merchant_hits[:30]:
    h = h.strip()
    if h not in seen and "/" in h:
        seen.add(h)
        print(" ", h[:120])

# 4. ค้นหา file list / get files endpoints
print("\n=== FILE LIST ENDPOINTS ===")
fl_hits = re.findall(r'.{0,40}(?:getFile|fileList|listFile|getDoc|docList|file-info|file-list|files\b).{0,80}', full_js, re.IGNORECASE)
seen = set()
for h in fl_hits[:20]:
    h = h.strip()
    if h not in seen:
        seen.add(h)
        print(" ", h[:120])

# 5. ค้นหา docId / hashTag / hashId usage near announcement
print("\n=== DOC ID / HASH PATTERNS ===")
doc_hits = re.findall(r'.{0,60}(?:docId|hashTag|hashId|fileId).{0,60}', full_js, re.IGNORECASE)
seen = set()
for h in doc_hits[:20]:
    h = h.strip()
    if h not in seen and len(h) > 20:
        seen.add(h)
        print(" ", h[:120])
