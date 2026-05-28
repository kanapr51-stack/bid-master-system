"""
Probe: Download eGP JS bundle and search for X-Announcement-Token generation logic.
Target: main.04c281d2396cb9f9.js on process5.gprocurement.go.th
"""
import re
import sys
import json
import requests

BASE_URL = "https://process5.gprocurement.go.th/egp-agpc01-web/"
JS_FILES = [
    "main.04c281d2396cb9f9.js",
    "scripts.c8f2401c9e4496c4.js",
    "polyfills.a052d679de18cb00.js",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://process5.gprocurement.go.th/",
}

# Patterns to search for
SEARCH_PATTERNS = [
    # Token-related
    r"AnnouncementToken",
    r"announcement[_-]?token",
    r"X-Announcement",
    r"validateAnnouncement",
    # Crypto-related
    r"CryptoJS",
    r"AES\.encrypt",
    r"AES\.decrypt",
    r"HmacSHA",
    r"PBKDF2",
    r"enc\.Utf8",
    # Key/secret patterns (common hardcoded strings)
    r"['\"][A-Za-z0-9+/=]{32,}['\"]",   # base64-ish strings ≥32 chars
    r"secretKey",
    r"privateKey",
    r"tokenKey",
    r"hmac[Kk]ey",
    r"encryptKey",
    r"aesKey",
    # Token building
    r"generateToken",
    r"createToken",
    r"buildToken",
    r"tokenBuilder",
    r"Date\.now\(\)",         # timestamp component
    r"btoa\(",                # base64 encode
]

CONTEXT_CHARS = 200  # chars before/after match to show


def fetch_js(filename):
    url = BASE_URL + filename
    print(f"\n[fetch] {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"  status: {r.status_code}  size: {len(r.text):,} chars")
        if r.status_code == 200:
            return r.text
        else:
            print(f"  body: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def search_patterns(content, filename):
    findings = {}
    for pat in SEARCH_PATTERNS:
        matches = [(m.start(), m.end()) for m in re.finditer(pat, content, re.IGNORECASE)]
        if matches:
            snippets = []
            for start, end in matches[:5]:  # max 5 per pattern
                ctx_start = max(0, start - CONTEXT_CHARS)
                ctx_end = min(len(content), end + CONTEXT_CHARS)
                snippet = content[ctx_start:ctx_end]
                # Replace whitespace runs for readability
                snippet = re.sub(r'\s+', ' ', snippet)
                snippets.append({
                    "pos": start,
                    "context": snippet
                })
            findings[pat] = snippets
            print(f"  [HIT] {pat!r:40s} — {len(matches)} match(es)")
    return findings


def main():
    all_findings = {}
    for fname in JS_FILES:
        content = fetch_js(fname)
        if not content:
            continue
        print(f"\n[search] {fname}")
        findings = search_patterns(content, fname)
        if findings:
            all_findings[fname] = findings

    # Save full findings
    outfile = "data/egp_js_token_findings.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(all_findings, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {outfile}")

    # Print summary of most interesting hits
    print("\n" + "="*60)
    print("SUMMARY — High-value patterns:")
    high_value = [
        "AnnouncementToken", "announcement[_-]?token", "X-Announcement",
        "CryptoJS", "AES\\.encrypt", "HmacSHA", "secretKey", "tokenKey",
        "generateToken", "createToken", "buildToken"
    ]
    for fname, findings in all_findings.items():
        for pat, snippets in findings.items():
            if any(hv in pat for hv in high_value):
                print(f"\n--- {fname} | pattern: {pat} ---")
                for s in snippets[:2]:
                    print(f"  pos={s['pos']}")
                    print(f"  >>> {s['context'][:400]}")


if __name__ == "__main__":
    main()
