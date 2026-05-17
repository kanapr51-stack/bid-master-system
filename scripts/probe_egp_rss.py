"""
probe_egp_rss.py — POC ทดสอบ EGP RSS feeds (2026-05-17)

URL: https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml
ไม่ติด Cloudflare (subdomain แยกจาก process5)

Test cases:
1. ดึง RSS ทุก announceType (P0, B0, D0, D1, W0, W1)
2. ทดสอบ deptId filter
3. Decode TIS-620 → UTF-8
4. Extract projectId จาก description
5. Cross-match กับ CGD API (verify data consistency)
6. Follow link → ตรวจ PDF ดาวน์โหลดได้ไหม
"""
import sys
import os
import re
import json
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Discord_Notify import load_env

RSS_URL = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
OUT_DIR = Path(__file__).parent.parent / "data"
OUT_DIR.mkdir(exist_ok=True)

# Browser-like headers (จาก POC: ต้องมี User-Agent ไม่งั้น connection reset)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}

# announceType ที่จะทดสอบ (ตรงกับ stepId mapping ของระบบเรา)
ANNOUNCE_TYPES = {
    "P0": "แผนการจัดซื้อจัดจ้าง (pre_tor / Q-stepId)",
    "15": "ประกาศราคากลาง",
    "B0": "ร่างเอกสารประกวด (tor_review / U-stepId)",
    "D0": "ประกาศเชิญชวน (active_bidding / M-stepId)",
    "D1": "ยกเลิกประกาศเชิญชวน (cancelled)",
    "D2": "เปลี่ยนแปลงประกาศเชิญชวน",
    "W0": "ประกาศผู้ชนะ (awarded_jobs / W-stepId)",
    "W1": "ยกเลิกประกาศผู้ชนะ",
    "W2": "เปลี่ยนแปลงประกาศผู้ชนะ",
}

# deptId ตัวอย่าง (จาก POC: 0307 ได้ผลแล้ว = กรมการปกครอง?)
SAMPLE_DEPT_IDS = ["0307", "0708", "0205", "0506", "1209", "1407", "0703"]


def log(msg: str):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_rss(params: dict) -> tuple[int, str]:
    """ดึง RSS + decode encoding ที่ถูก"""
    try:
        r = requests.get(RSS_URL, params=params, headers=HEADERS, timeout=15)
        # Server บอก ISO-8859-1 แต่จริงคือ TIS-620/Windows-874 (ภาษาไทย)
        # ลอง decode TIS-620 ก่อน → fallback Windows-874 → UTF-8
        raw = r.content
        for enc in ["tis-620", "cp874", "windows-874", "utf-8"]:
            try:
                text = raw.decode(enc)
                # ตรวจว่า decode ได้ภาษาไทยจริงไหม (มี char ไทยอย่างน้อย 1 ตัว)
                if any('฀' <= c <= '๿' for c in text):
                    return r.status_code, text
            except UnicodeDecodeError:
                continue
        # Fallback: ใช้ raw
        return r.status_code, raw.decode("utf-8", errors="replace")
    except Exception as e:
        return -1, str(e)


def parse_rss_items(xml_text: str) -> list[dict]:
    """Parse RSS items ออกมาเป็น list of dicts"""
    items = []
    for item_xml in re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL):
        item = {}
        for tag in ['title', 'description', 'link', 'pubDate']:
            m = re.search(rf'<{tag}>(.*?)</{tag}>', item_xml, re.DOTALL)
            if m:
                item[tag] = m.group(1).strip()
        # extract projectId จาก description (numeric 11-12 digits ตัวแรก)
        if 'description' in item:
            pid_match = re.search(r'\b(\d{11,12})\b', item['description'])
            item['projectId'] = pid_match.group(1) if pid_match else None
        items.append(item)
    return items


def main():
    load_env()
    results = {}

    # ================================================================
    # Test 1: Baseline — ดึงไม่มี params
    # ================================================================
    log("=== Test 1: Baseline (no params) ===")
    status, text = fetch_rss({})
    items = parse_rss_items(text)
    log(f"  HTTP {status}, size {len(text)}, items: {len(items)}")
    results['baseline'] = {'status': status, 'item_count': len(items)}

    # ================================================================
    # Test 2-10: ทุก announceType
    # ================================================================
    log("\n=== Test 2: ทุก announceType ===")
    by_type = {}
    for code, desc in ANNOUNCE_TYPES.items():
        status, text = fetch_rss({"announceType": code})
        items = parse_rss_items(text)
        by_type[code] = {
            'desc': desc,
            'status': status,
            'item_count': len(items),
            'sample': items[0] if items else None,
        }
        log(f"  {code:3} {desc:55}: {len(items)} items")
        time.sleep(0.5)
    results['by_announce_type'] = by_type

    # ================================================================
    # Test 11-17: deptId variations
    # ================================================================
    log("\n=== Test 3: deptId variations ===")
    by_dept = {}
    for dept_id in SAMPLE_DEPT_IDS:
        status, text = fetch_rss({"deptId": dept_id})
        items = parse_rss_items(text)
        by_dept[dept_id] = {
            'status': status,
            'item_count': len(items),
            'titles': [i.get('title', '')[:60] for i in items[:3]],
        }
        log(f"  deptId={dept_id}: {len(items)} items")
        if items:
            log(f"    title: {items[0].get('title','')[:80]}")
        time.sleep(0.5)
    results['by_dept'] = by_dept

    # ================================================================
    # Test 18: Combination announceType + deptId
    # ================================================================
    log("\n=== Test 4: Combination ===")
    combo_tests = [
        {"announceType": "D0", "deptId": "0307"},
        {"announceType": "W0", "deptId": "0307"},
    ]
    combos = []
    for params in combo_tests:
        status, text = fetch_rss(params)
        items = parse_rss_items(text)
        combos.append({'params': params, 'status': status, 'item_count': len(items),
                       'first_item': items[0] if items else None})
        log(f"  {params}: {len(items)} items")
        time.sleep(0.5)
    results['combinations'] = combos

    # ================================================================
    # Test 19: Encoding verification — ดึง decode → ตรวจภาษาไทย
    # ================================================================
    log("\n=== Test 5: Encoding (ภาษาไทย) ===")
    status, text = fetch_rss({"deptId": "0307"})
    items = parse_rss_items(text)
    if items:
        first = items[0]
        thai_count = sum(1 for c in first.get('title', '') if '฀' <= c <= '๿')
        log(f"  Title: {first.get('title', '')}")
        log(f"  Thai chars: {thai_count} ({'✅ OK' if thai_count > 5 else '❌ Mojibake'})")
        log(f"  Description: {first.get('description', '')[:200]}")
        log(f"  projectId extracted: {first.get('projectId')}")
        log(f"  pubDate: {first.get('pubDate')}")
        log(f"  link: {first.get('link', '')[:120]}")
        results['encoding_check'] = {
            'thai_chars_in_title': thai_count,
            'projectId_extracted': first.get('projectId') is not None,
            'sample': first,
        }

    # ================================================================
    # Test 20: Cross-match กับ CGD API — verify data consistency
    # ================================================================
    log("\n=== Test 6: Cross-match กับ CGD API ===")
    token = os.environ.get('OPEND_USER_TOKEN', '').strip()
    if token and items:
        rss_pids = [i.get('projectId') for i in items if i.get('projectId')]
        log(f"  RSS projectIds: {rss_pids[:5]}")
        # ลอง lookup ใน CGD API
        matches = 0
        for pid in rss_pids[:3]:
            try:
                r = requests.get(
                    "https://opend.data.go.th/get-ckan/datastore_search",
                    params={
                        "resource_id": "e4eaa1b4-eb1a-4534-b227-988ee25b898d",
                        "filters": json.dumps({"รหัสโครงการ": int(pid)}),
                        "limit": 1,
                    },
                    headers={"api-key": token, "Accept": "application/json"},
                    timeout=15,
                )
                if r.status_code == 200:
                    body = r.json()
                    if body.get('success') and body['result'].get('records'):
                        rec = body['result']['records'][0]
                        log(f"    ✅ {pid}: matched in CGD — {str(rec.get('ชื่อโครงการ',''))[:60]}")
                        matches += 1
                    else:
                        log(f"    ⚠️ {pid}: ไม่พบใน CGD (อาจเป็นปี 2569)")
                else:
                    log(f"    ❌ {pid}: HTTP {r.status_code}")
            except Exception as e:
                log(f"    {pid}: {e}")
            time.sleep(0.3)
        results['cross_match'] = {'tested': len(rss_pids[:3]), 'matched': matches}

    # ================================================================
    # Test 21: Compare RSS items vs seen_ids (overlap analysis)
    # ================================================================
    log("\n=== Test 7: Compare RSS vs scraper seen_ids ===")
    seen_path = OUT_DIR / "seen_ids.json"
    if seen_path.exists():
        seen = set(json.loads(seen_path.read_text(encoding='utf-8')))
        rss_pids_all = set()
        # ดึง RSS ทุก announceType เพื่อ count overlap
        for code in ['D0', 'W0', 'B0']:
            _, text = fetch_rss({"announceType": code})
            items = parse_rss_items(text)
            for it in items:
                if it.get('projectId'):
                    rss_pids_all.add(it['projectId'])
            time.sleep(0.3)
        overlap = rss_pids_all & seen
        new = rss_pids_all - seen
        log(f"  Scraper seen_ids: {len(seen):,}")
        log(f"  RSS pids (3 types): {len(rss_pids_all)}")
        log(f"  Overlap: {len(overlap)}")
        log(f"  New (not in scraper): {len(new)}")
        if new:
            log(f"  Sample new: {list(new)[:5]}")
        results['scraper_overlap'] = {
            'seen_ids_count': len(seen),
            'rss_pids': len(rss_pids_all),
            'overlap': len(overlap),
            'new': len(new),
        }

    # ================================================================
    # บันทึก results
    # ================================================================
    out_file = OUT_DIR / "rss_probe_results.json"
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f"\n✅ POC เสร็จ — ดูผลใน {out_file}")


if __name__ == "__main__":
    main()
