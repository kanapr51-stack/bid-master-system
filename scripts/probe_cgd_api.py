"""
probe_cgd_api.py — ทดสอบ data.go.th CKAN Data API

Discovered 2026-05-17 (จาก DATAGOTH3 user manual หน้า 36-37):
    URL:    https://opend.data.go.th/get-ckan/datastore_search
    Header: api-key: <user_token>
    Method: GET
    Params: resource_id=<UUID> + q=<keyword> + limit=N + offset=N

Datasets ที่ใช้:
    - egp-contact-2568  (10 resources, ~5M records, จัดซื้อจัดจ้างปี 2568)
    - egpwinner         (5 resources, ~2.5M records, รายชื่อผู้ชนะ)
    - thai-government-procurement (1 API resource, POST endpoint แยก)

วิธีใช้:
    python scripts/probe_cgd_api.py
"""
import sys
import os
import json
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Discord_Notify import load_env

CKAN_BASE = "https://opend.data.go.th/get-ckan"
OUT_DIR = Path(__file__).parent.parent / "data"
OUT_DIR.mkdir(exist_ok=True)

# Resource IDs ที่ confirmed ใช้งานได้ (ค้นจาก package_show 2026-05-17)
EGP_CONTRACT_2568_RIDS = [
    "e4eaa1b4-eb1a-4534-b227-988ee25b898d",  # contract-1
    "9ae119c4-73b9-4bb6-9b71-7b355269bc00",  # contract-2
    "1c1a90af-2d47-4bfb-ae87-e479b2582257",  # contract-3
    "c2385bd6-7e2a-40c2-94d8-6a65824c9415",  # contract-4
    "bb538ac1-3455-446d-b975-d709d6439e72",  # contract-5
    "5b98d6ba-0f66-4bb1-b8db-9b9aae928171",  # contract-6
    "037adcca-b349-44f6-9686-9fd1e9182227",  # contract-7
    "26316135-a95f-40e3-b2e8-1c912046c0ed",  # contract-8
    "882332c4-1f60-4db7-9962-9062eb08f6c4",  # contract-9
    "35961821-d945-4fc0-8ce1-a96b4cd46bd6",  # contract-10
]
EGPWINNER_RIDS = [
    "bf6017ec-b731-43e1-b5b8-abc2e91d1f95",  # winner-1
    "07654f45-d1cc-4470-84b4-f421fc737990",  # winner-2
    "9c8c4c1f-4365-4ebc-9ddc-2a02e05f95a2",  # winner-3
    "2eba095b-f6f2-4807-8c45-e60b360a9f23",  # winner-4
    "08eb695c-5d5a-420e-b088-6db1b26653da",  # winner-5
]


def log(msg: str):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def call_ckan(endpoint: str, params: dict, token: str) -> tuple[int, dict | str]:
    """เรียก CKAN API ด้วย api-key header (มี dash)"""
    url = f"{CKAN_BASE}/{endpoint}"
    headers = {"api-key": token, "Accept": "application/json"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text[:500]
    except Exception as e:
        return -1, str(e)


def datastore_search(resource_id: str, token: str, q: str | None = None,
                     limit: int = 10, offset: int = 0,
                     filters: dict | None = None) -> dict | None:
    """Search records ใน resource — return dict result หรือ None ถ้า fail"""
    params = {"resource_id": resource_id, "limit": limit, "offset": offset}
    if q:
        params["q"] = q
    if filters:
        params["filters"] = json.dumps(filters, ensure_ascii=False)
    status, body = call_ckan("datastore_search", params, token)
    if status == 200 and isinstance(body, dict) and body.get("success"):
        return body["result"]
    return None


def main():
    load_env()
    token = os.environ.get("OPEND_USER_TOKEN", "").strip()
    if not token:
        log("❌ ไม่พบ OPEND_USER_TOKEN ใน .env")
        return

    log(f"User Token: {token[:8]}...{token[-4:]} (len={len(token)})")

    # ====================================
    # Step 1: ทดสอบ basic API call
    # ====================================
    log("\n=== Step 1: Basic API call (egp-contract-2568-1, limit=2) ===")
    rid = EGP_CONTRACT_2568_RIDS[0]
    res = datastore_search(rid, token, limit=2)
    if res is None:
        log("❌ Basic call ล้มเหลว — token ถูกต้องไหม?")
        return
    log(f"  ✅ Total records: {res.get('total'):,}")
    log(f"  ✅ Fields ({len(res.get('fields', []))}):")
    for f in res.get('fields', [])[:10]:
        log(f"     - {f.get('id')}: {f.get('type')}")
    (OUT_DIR / "cgd_step1_basic.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    # ====================================
    # Step 2: ทดสอบ keyword search ทุก resource ใน egp-contract-2568
    # ====================================
    log("\n=== Step 2: Search 'นครพนม' ใน egp-contract-2568 ทุก file ===")
    total_nkp = 0
    for i, rid in enumerate(EGP_CONTRACT_2568_RIDS, 1):
        res = datastore_search(rid, token, q="นครพนม", limit=1)
        n = res.get('total', 0) if res else 0
        total_nkp += n
        log(f"  file-{i}: {n:,} records matching 'นครพนม'")
        time.sleep(0.3)
    log(f"  📊 รวม 'นครพนม' ปี 2568 ทั่วประเทศ: {total_nkp:,} งาน")

    # ====================================
    # Step 3: ทดสอบ filter province (exact match)
    # ====================================
    log("\n=== Step 3: Filter จังหวัด='นครพนม' (exact) ===")
    rid = EGP_CONTRACT_2568_RIDS[0]
    res = datastore_search(rid, token, filters={"จังหวัด": "นครพนม"}, limit=3)
    if res:
        log(f"  ✅ จังหวัด=นครพนม ใน file-1: {res.get('total'):,} records")
        if res.get('records'):
            first = res['records'][0]
            log(f"  Sample: {first.get('ชื่อโครงการ','?')[:80]}")
            log(f"          งบ: {first.get('งบประมาณ(บาท)')} | จว: {first.get('จังหวัด')}")

    # ====================================
    # Step 4: ทดสอบ egpwinner (รายชื่อผู้ชนะ)
    # ====================================
    log("\n=== Step 4: ทดสอบ egpwinner schema ===")
    rid = EGPWINNER_RIDS[0]
    res = datastore_search(rid, token, limit=2)
    if res:
        log(f"  Total winners (file-1): {res.get('total'):,}")
        log(f"  Fields:")
        for f in res.get('fields', []):
            log(f"     - {f.get('id')}: {f.get('type')}")

    # ค้นหา TIN ของบริษัทคุณกัญจน์: หจก.ยศประทานรุ่งเรืองทรัพย์
    log("\n  Search 'ยศประทาน' ใน egpwinner file-1:")
    res = datastore_search(rid, token, q="ยศประทาน", limit=3)
    if res and res.get('records'):
        log(f"  Found: {res.get('total'):,} matches")
        for r in res['records']:
            log(f"     - TIN={r.get('เลขประจำตัวนิติบุคคล')} | {r.get('ผู้ชนะการเสนอราคา','?')[:60]}")

    # ====================================
    # Step 5: ทดสอบ pagination (limit สูง)
    # ====================================
    log("\n=== Step 5: ทดสอบ pagination limit สูง ===")
    rid = EGP_CONTRACT_2568_RIDS[0]
    for limit in [100, 500, 1000]:
        res = datastore_search(rid, token, filters={"จังหวัด": "นครพนม"}, limit=limit)
        n_records = len(res.get('records', [])) if res else 0
        log(f"  limit={limit}: got {n_records} records")
        time.sleep(0.5)

    log("\n✅ Probe เสร็จ — ดูผลใน data/cgd_step*.json")


if __name__ == "__main__":
    main()
