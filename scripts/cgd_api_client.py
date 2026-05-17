"""
cgd_api_client.py — Client สำหรับ CGD CKAN Data API (opend.data.go.th)

ใช้เพื่อ enrich ข้อมูลโครงการจาก projectId → ทุก field ที่ all_jobs ต้องการ:
  ชื่อโครงการ, ชื่อหน่วยงาน, จังหวัด/อำเภอ/ตำบล, งบประมาณ, สถานะ, ผู้ชนะ, ฯลฯ

Datasets:
  egp-contact-2568 (10 files × ~500K records) — โครงการจัดซื้อจัดจ้างปี 2568
  egpwinner        (5 files × 500K records)   — รายชื่อผู้ชนะการเสนอราคา

Auth: api-key header (OPEND_USER_TOKEN ใน .env)
Quota: 1000 calls / วัน / user

Functions:
  lookup_project(project_id) → dict | None
  lookup_winner_by_tin(tin)  → dict | None
  normalize_to_all_jobs(rec, **overrides) → dict (เข้ากับ schema all_jobs)
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

CKAN_BASE = "https://opend.data.go.th/get-ckan"
DATA_DIR = Path(__file__).parent.parent / "data"

EGP_CONTRACT_2568_RIDS = [
    "e4eaa1b4-eb1a-4534-b227-988ee25b898d",
    "9ae119c4-73b9-4bb6-9b71-7b355269bc00",
    "1c1a90af-2d47-4bfb-ae87-e479b2582257",
    "c2385bd6-7e2a-40c2-94d8-6a65824c9415",
    "bb538ac1-3455-446d-b975-d709d6439e72",
    "5b98d6ba-0f66-4bb1-b8db-9b9aae928171",
    "037adcca-b349-44f6-9686-9fd1e9182227",
    "26316135-a95f-40e3-b2e8-1c912046c0ed",
    "882332c4-1f60-4db7-9962-9062eb08f6c4",
    "35961821-d945-4fc0-8ce1-a96b4cd46bd6",
]
EGPWINNER_RIDS = [
    "bf6017ec-b731-43e1-b5b8-abc2e91d1f95",
    "07654f45-d1cc-4470-84b4-f421fc737990",
    "9c8c4c1f-4365-4ebc-9ddc-2a02e05f95a2",
    "2eba095b-f6f2-4807-8c45-e60b360a9f23",
    "08eb695c-5d5a-420e-b088-6db1b26653da",
]

CACHE_FILE = DATA_DIR / "cgd_projectid_cache.json"

_cache: dict[str, dict | None] | None = None
_token: str | None = None


# ================================================================
# Auth + cache
# ================================================================

def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_token() -> str:
    global _token
    if _token is None:
        _load_env()
        _token = os.environ.get("OPEND_USER_TOKEN", "").strip()
        if not _token:
            raise RuntimeError("ไม่พบ OPEND_USER_TOKEN ใน .env")
    return _token


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        if CACHE_FILE.exists():
            try:
                _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                _cache = {}
        else:
            _cache = {}
    return _cache


def _save_cache():
    global _cache
    if _cache is None:
        return
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ================================================================
# Raw CKAN calls
# ================================================================

def _datastore_search(
    resource_id: str,
    *,
    q: str | None = None,
    limit: int = 10,
    offset: int = 0,
    filters: dict | None = None,
    timeout: int = 20,
) -> dict | None:
    params: dict[str, Any] = {"resource_id": resource_id, "limit": limit, "offset": offset}
    if q:
        params["q"] = q
    if filters:
        params["filters"] = json.dumps(filters, ensure_ascii=False)
    headers = {"api-key": get_token(), "Accept": "application/json"}
    try:
        r = requests.get(
            f"{CKAN_BASE}/datastore_search",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        body = r.json()
        if body.get("success"):
            return body["result"]
    except Exception:
        return None
    return None


# ================================================================
# Public lookups
# ================================================================

def lookup_project(project_id: str | int, use_cache: bool = True) -> dict | None:
    """ค้นหา project ตาม รหัสโครงการ ใน 10 resource files (concurrent)
    Returns: dict record หรือ None
    """
    pid_str = str(project_id).strip()
    if not pid_str:
        return None

    cache = _load_cache()
    if use_cache and pid_str in cache:
        return cache[pid_str]

    try:
        pid_int = int(pid_str)
    except ValueError:
        return None

    found: dict | None = None
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [
            ex.submit(
                _datastore_search,
                rid,
                filters={"รหัสโครงการ": pid_int},
                limit=1,
            )
            for rid in EGP_CONTRACT_2568_RIDS
        ]
        for fut in futures:
            res = fut.result()
            if res and res.get("records"):
                found = res["records"][0]
                break

    cache[pid_str] = found
    if found is not None:
        _save_cache()
    return found


def lookup_winner_by_tin(tin: str) -> list[dict]:
    """ค้นหา winner ตามเลขนิติบุคคล → คืนรายการ contracts ทั้งหมดของ TIN นั้น"""
    tin_str = str(tin).strip()
    if not tin_str:
        return []

    records: list[dict] = []
    for rid in EGPWINNER_RIDS:
        res = _datastore_search(
            rid,
            filters={"เลขประจำตัวนิติบุคคล": tin_str},
            limit=1000,
        )
        if res and res.get("records"):
            records.extend(res["records"])
        time.sleep(0.2)
    return records


# ================================================================
# Schema mapping → all_jobs row
# ================================================================

def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _safe_num(v: Any) -> str:
    """งบประมาณ อาจเป็น number หรือ string มี comma — คืน plain digit string"""
    if v is None:
        return ""
    s = str(v).strip().replace(",", "")
    return s if s else ""


def normalize_to_all_jobs(
    record: dict,
    *,
    publish_date: str = "",
    deadline: str = "",
    procurement_type: str = "",
    project_status: str = "",
    step_id: str = "",
    project_status_raw: str = "",
    announce_type: str = "",
    tor_url: str = "",
    search_keyword: str = "rss_cgd",
) -> dict:
    """แปลง CGD record → dict ที่เข้ากับ _build_all_jobs_row ของ Sebastian_Scraper
    (จาก all_jobs 18 columns)
    """
    return {
        "job_id": _safe_str(record.get("รหัสโครงการ")),
        "title": _safe_str(record.get("ชื่อโครงการ")),
        "department": _safe_str(record.get("ชื่อหน่วยงาน")),
        "province": _safe_str(record.get("จังหวัด")),
        "district": _safe_str(record.get("เขต/อำเภอ")),
        "subdistrict": _safe_str(record.get("แขวง/ตำบล")),
        "procurement_type": procurement_type or _safe_str(record.get("วิธีจัดซื้อฯ")),
        "budget": _safe_num(record.get("งบประมาณ(บาท)")),
        "publish_date": publish_date or _safe_str(record.get("วันที่ประกาศ")),
        "deadline": deadline,
        "project_status": project_status or _safe_str(record.get("สถานะโครงการ")),
        "quantity_note": f"keyword:{search_keyword} | cgd",
        "tor_url": tor_url,
        "step_id": step_id,
        "project_status_raw": project_status_raw,
        "announce_type": announce_type,
    }


# ================================================================
# CLI for debugging
# ================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CGD CKAN Client")
    parser.add_argument("--project-id", help="lookup project by รหัสโครงการ")
    parser.add_argument("--tin", help="lookup winner by เลขนิติบุคคล")
    args = parser.parse_args()

    if args.project_id:
        rec = lookup_project(args.project_id)
        if rec:
            print(json.dumps(rec, ensure_ascii=False, indent=2))
            print("\n--- normalized ---")
            print(json.dumps(normalize_to_all_jobs(rec), ensure_ascii=False, indent=2))
        else:
            print(f"❌ ไม่พบ projectId {args.project_id}")
    elif args.tin:
        recs = lookup_winner_by_tin(args.tin)
        print(f"พบ {len(recs)} contracts สำหรับ TIN {args.tin}")
        for r in recs[:5]:
            print(f"  - {r.get('ผู้ชนะการเสนอราคา', '?')}")
    else:
        parser.print_help()
