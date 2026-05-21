"""
probe_deptid_coverage.py — ค้นหา deptId จริงของ 8,500 หน่วยงานไทย

Hypotheses:
  H1: RSS ไม่มี deptId → คืน global announcements
  H2: deptId > 9999 (5+ หลัก) มีงาน
  H3: scan P0/B0/W0 นอกจาก D0 → เจอ dept เพิ่ม
  H4: EGP มี dept-list API แยก

วิธีรัน:
    python scripts/probe_deptid_coverage.py
"""
import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    import requests as cffi_requests
    _use_cffi = False

RSS_URL = "https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}

DATA_DIR = Path(__file__).parent.parent / "data"
CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"

IMPERSONATE = "chrome120" if _use_cffi else None


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_rss(params: dict, timeout: int = 10) -> tuple[int, str]:
    try:
        if _use_cffi:
            r = cffi_requests.get(RSS_URL, params=params, headers=HEADERS,
                                   timeout=timeout, impersonate=IMPERSONATE)
        else:
            r = cffi_requests.get(RSS_URL, params=params, headers=HEADERS, timeout=timeout)
        return r.status_code, r.content.decode("tis-620", errors="replace")
    except Exception as e:
        return -1, str(e)


def count_items(xml_text: str) -> int:
    return len(re.findall(r"<item>", xml_text))


def extract_depts_from_xml(xml_text: str) -> list[str]:
    """ดึง deptId จาก link tags ถ้ามี"""
    return re.findall(r"deptId=(\d+)", xml_text)


def main():
    # โหลด catalog เพื่อรู้ active deptIds
    catalog = {}
    if CATALOG_FILE.exists():
        try:
            catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    active_depts = sorted(
        k for k, v in catalog.items()
        if isinstance(v, dict) and v.get("item_count", 0) > 0
    )
    log(f"Known active D0 depts: {len(active_depts)}")

    results = {}

    # =========================================================
    # H1: RSS โดยไม่มี deptId เลย
    # =========================================================
    log("\n=== H1: RSS ไม่มี deptId ===")
    status, text = fetch_rss({})
    n = count_items(text)
    log(f"  status={status}, items={n}, body_len={len(text)}")
    if n > 0:
        log(f"  ✅ WORKS! Global RSS feed มีงาน — sample:\n{text[:500]}")
    else:
        log(f"  ❌ ว่างเปล่า (body snippet): {text[:200]}")
    results["h1_no_deptid"] = {"status": status, "items": n}
    time.sleep(1)

    # =========================================================
    # H1b: RSS ไม่ระบุ deptId แต่ระบุ anounceType=D0
    # =========================================================
    log("\n=== H1b: RSS anounceType=D0 ไม่มี deptId ===")
    status, text = fetch_rss({"anounceType": "D0"})
    n = count_items(text)
    log(f"  status={status}, items={n}")
    results["h1b_no_deptid_d0"] = {"status": status, "items": n}
    time.sleep(1)

    # =========================================================
    # H2: deptId 5 หลัก (10000-10050)
    # =========================================================
    log("\n=== H2: probe deptId 5 หลัก (10000-10030) ===")
    five_digit_active = []
    for n in [10000, 10001, 10002, 10003, 10004, 10005,
              10010, 10020, 10030, 10050, 10100,
              11000, 12000, 20000, 50000]:
        did = str(n)
        status, text = fetch_rss({"deptId": did, "anounceType": "D0"})
        items = count_items(text)
        if items > 0:
            log(f"  ✅ deptId={did}: {items} items!")
            five_digit_active.append(did)
        else:
            log(f"  - deptId={did}: {items} items (empty)")
        time.sleep(0.5)
    results["h2_five_digit"] = {"tested": 15, "active": five_digit_active}

    # =========================================================
    # H3a: scan W0 สำหรับ known active depts → เจอ dept ใหม่ไหม?
    # =========================================================
    log("\n=== H3: Multi-anounceType scan สำหรับ range 0001-0200 ===")
    announce_types = ["P0", "B0", "D0", "W0", "D1"]
    type_new_depts: dict[str, list[str]] = {t: [] for t in announce_types}

    # probe เฉพาะ 0001-0300 (ไม่ scan ทั้งหมด — แค่ PoC)
    for n in range(1, 301):
        did = f"{n:04d}"
        if did in active_depts:
            continue  # รู้จักแล้วจาก D0
        for atype in announce_types:
            if atype == "D0":
                continue  # scan แล้ว
            status, text = fetch_rss({"deptId": did, "anounceType": atype})
            items = count_items(text)
            if items > 0:
                type_new_depts[atype].append(did)
                log(f"  ✅ deptId={did} atype={atype}: {items} items!")
                break
        time.sleep(0.3)

    log(f"\n  New depts found per type (range 0001-0300):")
    for atype, depts in type_new_depts.items():
        log(f"    {atype}: {len(depts)} new depts {depts[:5]}")
    results["h3_multitype"] = type_new_depts

    # =========================================================
    # H4: EGP dept-list API
    # =========================================================
    log("\n=== H4: EGP dept directory API probe ===")
    # ลอง endpoint ต่างๆ ที่น่าจะมี dept list
    import requests as req_lib
    process5_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://process5.gprocurement.go.th/",
        "Accept": "application/json, text/plain, */*",
    }
    test_endpoints = [
        ("https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement/getDeptList", {}),
        ("https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement/getOrganizationList", {}),
        ("https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml", {"deptId": ""}),
    ]
    for url, params in test_endpoints:
        try:
            r = req_lib.get(url, params=params, headers=process5_headers, timeout=10)
            log(f"  {url[-60:]}: status={r.status_code}, len={len(r.text)}, sample={r.text[:100]}")
        except Exception as e:
            log(f"  {url[-60:]}: ERROR {e}")
        time.sleep(0.5)

    # =========================================================
    # สรุป
    # =========================================================
    log("\n=== SUMMARY ===")
    log(f"Known active D0 depts: {len(active_depts)}")
    log(f"H1 (no deptId): {results['h1_no_deptid']['items']} items")
    log(f"H2 (5-digit): {len(results['h2_five_digit']['active'])} active out of 15 tested")
    log(f"H3 new depts from non-D0: {sum(len(v) for v in results['h3_multitype'].values())}")

    out = DATA_DIR / "probe_deptid_coverage.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n💾 บันทึกผลที่ {out}")


if __name__ == "__main__":
    main()
