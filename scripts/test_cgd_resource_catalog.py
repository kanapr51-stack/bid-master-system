"""test_cgd_resource_catalog.py — map ปี→resource_id จาก CKAN package."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_resource_catalog as cat

# fake CKAN package_show payload: 1 package มีหลาย resource (ต่อปี)
FAKE_PKG = {"result": {"resources": [
    {"id": "rid-2568", "name": "ข้อมูลจัดซื้อจัดจ้าง ปีงบประมาณ 2568"},
    {"id": "rid-2569", "name": "ข้อมูลจัดซื้อจัดจ้าง ปีงบประมาณ 2569"},
]}}
rid = cat.resource_id_for_year("2569", fetch=lambda pkg_id: FAKE_PKG)
assert rid == "rid-2569", rid
rid68 = cat.resource_id_for_year("2568", fetch=lambda pkg_id: FAKE_PKG)
assert rid68 == "rid-2568", rid68
# ไม่เจอปี → None
assert cat.resource_id_for_year("2570", fetch=lambda pkg_id: FAKE_PKG) is None
print("✅ PASS cgd_resource_catalog")
