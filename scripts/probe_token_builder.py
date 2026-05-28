"""
Search for X-Announcement-Token builder logic in chunk 744 (1.1MB main chunk).
Focus: how the 3-part token (AES_part : timestamp : HMAC) is constructed.
"""
import re, json, requests

BASE_URL = "https://process5.gprocurement.go.th/egp-agpc01-web/"
HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/124.0", "Referer": "https://process5.gprocurement.go.th/"}

CHUNK = ("744", "7d7ff6ece738a49c")

PATTERNS = [
    # Direct token references
    r"[Aa]nnouncementToken",
    r"announcement[_\-]?[Tt]oken",
    r"validateAnnouncement",
    r"X-Announcement",
    # Token header setting
    r"['\"]x-announcement",
    r"headers.*[Tt]oken",
    r"[Tt]oken.*headers",
    # Timestamp + join patterns (token = A:B:C)
    r"Date\.now\(\)\.toString",
    r"\.join\(['\"]:\s*['\"]",       # .join(":")
    r"['\"][^'\"]*:[^'\"]*:[^'\"]*['\"]",  # literal "A:B:C"
    # HMAC in token context
    r"HmacSHA.*?Date\.now|Date\.now.*?HmacSHA",
    r"HmacSHA.*?toString.*?btoa|btoa.*?HmacSHA",
    # encryptData used for token
    r"encryptData.*?token|token.*?encryptData",
    r"encryptData\(",
    # Parts of token construction
    r"btoa\(encodeURIComponent",
    r"encodeURIComponent.*?btoa",
    # projectId encryption
    r"projectId.*?encrypt|encrypt.*?projectId",
    r"encryptedProjectId|encryptProject",
]

CONTEXT = 400


def fetch(cid, chash):
    fname = f"{cid}.{chash}.js"
    print(f"Fetching {fname}...")
    r = requests.get(BASE_URL + fname, headers=HEADERS, timeout=60)
    print(f"  {r.status_code}  {len(r.text):,} chars")
    return r.text if r.status_code == 200 else None


def search(content):
    hits = {}
    for pat in PATTERNS:
        ms = list(re.finditer(pat, content, re.IGNORECASE | re.DOTALL))
        if ms:
            snippets = []
            for m in ms[:5]:
                s = max(0, m.start() - CONTEXT)
                e = min(len(content), m.end() + CONTEXT)
                ctx = re.sub(r'\s+', ' ', content[s:e])
                snippets.append({"pos": m.start(), "match": m.group()[:80], "ctx": ctx})
            hits[pat] = snippets
            print(f"  [HIT] {pat!r:55s} {len(ms)}x")
    return hits


def main():
    cid, chash = CHUNK
    content = fetch(cid, chash)
    if not content:
        return

    print(f"\nSearching {cid}.{chash}.js...")
    hits = search(content)

    out = "data/egp_token_builder_findings.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(hits, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {out}")

    # Print all hits with full context
    print("\n" + "="*70)
    for pat, snippets in hits.items():
        print(f"\n--- Pattern: {pat} ---")
        for s in snippets[:3]:
            print(f"  pos={s['pos']}  match={s['match']!r}")
            print(f"  >>> {s['ctx'][:700]}")
            print()


if __name__ == "__main__":
    main()
