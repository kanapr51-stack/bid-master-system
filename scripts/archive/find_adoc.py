import sys, re, time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].new_page()
    js_bodies = {}
    def on_resp(resp):
        if "agpc01-web" in resp.url and ".js" in resp.url:
            try:
                body = resp.text()
                if len(body) > 5000:
                    js_bodies[resp.url] = body
            except:
                pass
    page.on("response", on_resp)
    page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
              wait_until="load", timeout=30000)
    time.sleep(3)
    page.close()

full_js = "\n".join(js_bodies.values())

# หา API calls ที่ใช้ projectId + seqNo ใกล้กับ service calls
print("=== projectId + seqNo in service calls ===")
hits = re.findall(r'.{0,80}(?:projectId|seqNo).{0,80}', full_js)
svc_hits = [h for h in hits if any(svc in h for svc in ["atpj27","ator13","adoc25","aobj19"])]
seen = set()
for h in svc_hits[:20]:
    h = h.strip()
    if h not in seen:
        seen.add(h)
        print(" ", h[:150])

# หา ator13 paths
print("\n=== ator13 paths ===")
hits2 = re.findall(r'ator13.{0,200}', full_js)
seen = set()
for h in hits2[:15]:
    if h not in seen and "/" in h:
        seen.add(h)
        print(" ", h[:150])

# หา apoj20 paths (project service)
print("\n=== apoj20 paths ===")
hits3 = re.findall(r'apoj20.{0,200}', full_js)
seen = set()
for h in hits3[:15]:
    if h not in seen:
        seen.add(h)
        print(" ", h[:150])

# หา function ที่ชื่อเกี่ยวกับ announcement + file/document
print("\n=== announcement file functions ===")
hits4 = re.findall(r'function\s+\w*(?:announce|Announce|announc)\w*\s*\([^)]*\)', full_js)
hits4 += re.findall(r'get\w*(?:File|Doc|Attach)\w*\s*\([^)]{0,100}\)', full_js)
seen = set()
for h in hits4[:15]:
    if h not in seen:
        seen.add(h)
        print(" ", h[:120])
