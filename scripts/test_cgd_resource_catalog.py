"""test_cgd_resource_catalog.py — list resource_ids ต่อปี จาก package egp-contact-{year}."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import requests
import cgd_resource_catalog as cat

# โครงสร้างจริง: 1 package/ปี (egp-contact-2569) มีหลาย resource (10 ไฟล์)
FAKE_PKG = {"result": {"resources": [
    {"id": "r1", "name": "2569-egp-contract-1"},
    {"id": "r2", "name": "2569-egp-contract-2"},
]}}

def fetch_ok(pkg):
    assert pkg == "egp-contact-2569", pkg
    return FAKE_PKG

ids = cat.resource_ids_for_year("2569", fetch=fetch_ok)
assert ids == ["r1", "r2"], ids

# ปีที่ยังไม่ publish → package 404 → คืน [] (ไม่ throw)
def fetch_404(pkg):
    resp = requests.Response(); resp.status_code = 404
    raise requests.HTTPError("404 Not Found", response=resp)

assert cat.resource_ids_for_year("2570", fetch=fetch_404) == []

# error อื่น (เช่น 403 token ว่าง / quota) ต้อง re-raise — ห้ามกลืนเป็น "ไม่ publish"
def fetch_403(pkg):
    resp = requests.Response(); resp.status_code = 403
    raise requests.HTTPError("403 Forbidden", response=resp)

try:
    cat.resource_ids_for_year("2568", fetch=fetch_403)
    assert False, "403 ต้อง raise ไม่ใช่คืน []"
except requests.HTTPError:
    pass
print("✅ PASS cgd_resource_catalog")
