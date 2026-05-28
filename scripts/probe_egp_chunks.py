"""
Download key Angular chunks from eGP process5 and search for X-Announcement-Token generation logic.
"""
import re, json, requests, sys

BASE_URL = "https://process5.gprocurement.go.th/egp-agpc01-web/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0",
    "Referer": "https://process5.gprocurement.go.th/",
}

# From main.js chunk hash map — most likely to contain token logic
CHUNKS = {
    "744": "7d7ff6ece738a49c",   # main entry, loads all libs
    "453": "843493ff0b45477e",   # business-lib
    "506": "b345190b83005837",   # shared-lib
    "546": "0ba850a324a9899f",   # shared-lib v2
    "171": "d567b51356205218",   # model-lib
    "411": "ef931e8fec707c87",   # model-lib entry
}

# High-value patterns (ordered by importance)
PATTERNS = [
    r"AnnouncementToken",
    r"announcement[_\-]?token",
    r"validateAnnouncement",
    r"X-Announcement",
    r"generateToken|createToken|buildToken|makeToken",
    r"CryptoJS",
    r"AES\.encrypt|AES\.decrypt",
    r"HmacSHA(?:256|512)",
    r"PBKDF2",
    r"secretKey|tokenKey|encryptKey|hmacKey",
    r"['\"][A-Za-z0-9+/=]{40,}['\"]",  # long base64 strings
    r"window\.__TOKEN|window\.token",
]

CONTEXT = 300


def fetch_chunk(cid, chash):
    fname = f"{cid}.{chash}.js"
    url = BASE_URL + fname
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"  [{r.status_code}] {fname}  ({len(r.text):,} chars)")
        return r.text if r.status_code == 200 else None
    except Exception as e:
        print(f"  [ERR] {fname}: {e}")
        return None


def search(content, cid):
    hits = {}
    for pat in PATTERNS:
        ms = list(re.finditer(pat, content, re.IGNORECASE))
        if ms:
            snippets = []
            for m in ms[:8]:
                s = max(0, m.start() - CONTEXT)
                e = min(len(content), m.end() + CONTEXT)
                ctx = re.sub(r'\s+', ' ', content[s:e])
                snippets.append({"pos": m.start(), "match": m.group(), "ctx": ctx})
            hits[pat] = snippets
            star = " ***" if any(x in pat for x in ["Announcement","Crypto","AES","Hmac","secretKey","tokenKey","Token"]) else ""
            print(f"    [HIT{star}] {pat!r:50s} {len(ms)}x")
    return hits


def main():
    all_findings = {}
    print("=== Fetching chunks ===")
    for cid, chash in CHUNKS.items():
        print(f"\nChunk {cid}:")
        content = fetch_chunk(cid, chash)
        if not content:
            continue
        hits = search(content, cid)
        if hits:
            all_findings[f"{cid}.{chash}"] = hits

    out = "data/egp_chunk_token_findings.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_findings, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {out}")

    # Print starred hits
    print("\n" + "="*70)
    print("STARRED HITS (AnnouncementToken / Crypto / AES / Hmac / Key):")
    star_pats = ["Announcement","Crypto","AES","Hmac","secretKey","tokenKey","encryptKey","hmacKey","Token"]
    found_any = False
    for chunk, findings in all_findings.items():
        for pat, snippets in findings.items():
            if any(x.lower() in pat.lower() for x in star_pats):
                found_any = True
                print(f"\n{'='*60}")
                print(f"Chunk: {chunk}  Pattern: {pat}")
                for s in snippets[:3]:
                    print(f"  pos={s['pos']}  match={s['match']!r}")
                    print(f"  >>> {s['ctx'][:600]}")
    if not found_any:
        print("  (none)")
        print("\nAll hits:")
        for chunk, findings in all_findings.items():
            for pat, snippets in findings.items():
                print(f"\n  {chunk} | {pat}: {len(snippets)} match(es)")
                for s in snippets[:1]:
                    print(f"    >>> {s['ctx'][:300]}")


if __name__ == "__main__":
    main()
