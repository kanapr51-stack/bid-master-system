"""cgd_resource_catalog.py — map ปีงบ → CKAN resource_ids (แทน hardcode CGD_CONTRACT_RIDS).

โครงสร้างจริง CGD (probe 2026-06-06): 1 package ต่อปีงบ ชื่อ `egp-contact-{ปีพ.ศ.}`
แต่ละ package มี ~10 resources (`{year}-egp-contract-1..10`). ปีที่ยังไม่ publish → 404.
"""
import os
import requests

CKAN_BASE = "https://opend.data.go.th/get-ckan"
PACKAGE_TMPL = os.environ.get("CGD_PACKAGE_TMPL", "egp-contact-{year}")


def _fetch_package(pkg: str) -> dict:
    tok = os.environ.get("OPEND_USER_TOKEN", "")
    r = requests.get(f"{CKAN_BASE}/package_show", params={"id": pkg},
                     headers={"api-key": tok, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def resource_ids_for_year(year: str, fetch=None) -> list[str]:
    """คืน list resource_id ทั้งหมดของ package egp-contact-{year}.
    ปีที่ยังไม่ publish (package 404) → คืน [] (ไม่ throw). fetch inject ได้สำหรับ test."""
    fetch = fetch or _fetch_package
    pkg = PACKAGE_TMPL.format(year=year)
    try:
        data = fetch(pkg)
    except requests.HTTPError as e:
        resp = getattr(e, "response", None)
        if resp is not None and resp.status_code == 404:
            return []          # ปียังไม่ publish จริง
        raise                  # 401/403/429/5xx → อย่ากลืน (มักคือ token ว่าง/quota)
    return [r.get("id") for r in (data.get("result", {}) or {}).get("resources", []) or []
            if r.get("id")]
