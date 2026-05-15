import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

js = Path('downloads/debug/js_dig/744.7d7ff6ece738a49c.js').read_text(encoding='utf-8', errors='replace')
print(f'744.js: {len(js):,} chars')

print('\n=== announcement context with service calls ===')
hits = re.findall(r'.{0,100}announcement.{0,200}', js)
svc_hits = [h for h in hits if 'service_url' in h or '.get(' in h or '.post(' in h]
seen = set()
for h in svc_hits[:20]:
    h = h.strip()
    if h not in seen:
        seen.add(h)
        print(f'  {h[:280]}')

print('\n=== ALL service_url usages ===')
all_svc = re.findall(r'environment\.[a-z_]+service_url[^;]{5,120}', js)
seen = set()
for s in sorted(set(all_svc)):
    if s not in seen:
        seen.add(s)
        print(f'  {s[:200]}')

print('\n=== Template literal paths ===')
tpaths = re.findall(r'[+`]["/][a-z][a-z_/\-?=&]{5,80}[`"\' ]', js)
seen = set()
for t in sorted(set(tpaths)):
    if t not in seen:
        seen.add(t)
        if any(x in t for x in ['/pb/', '/api/', 'announcement', 'file', 'doc']):
            print(f'  {t[:120]}')
