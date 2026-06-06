"""cgd_resource_catalog.py — map ปีงบ → CKAN resource_id (แทน hardcode CGD_CONTRACT_RIDS).
ดึงรายการ resource จาก package เดียว (CGD เผยแพร่ resource ต่อปีใน package เดียว)."""
import os
import requests

CKAN_BASE = "https://opend.data.go.th/get-ckan"
# package id ของชุด "ข้อมูลจัดซื้อจัดจ้าง" CGD (ยืนยันใน Task 1.4 ด้วย package_search)
CGD_PACKAGE_ID = os.environ.get("CGD_PACKAGE_ID", "")


def _fetch_package(pkg_id: str) -> dict:
    tok = os.environ.get("OPEND_USER_TOKEN", "")
    r = requests.get(f"{CKAN_BASE}/package_show", params={"id": pkg_id},
                     headers={"api-key": tok, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def resource_id_for_year(year: str, pkg_id: str = None, fetch=None) -> str | None:
    """คืน resource_id ที่ชื่อมีปีงบ `year` (เช่น '2569'). fetch inject ได้สำหรับ test."""
    fetch = fetch or _fetch_package
    pkg_id = pkg_id or CGD_PACKAGE_ID
    data = fetch(pkg_id)
    for res in (data.get("result", {}) or {}).get("resources", []) or []:
        if year in (res.get("name") or ""):
            return res.get("id")
    return None
