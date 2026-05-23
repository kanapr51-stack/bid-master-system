"""
enrich_dept_names.py — Enrich egp_deptid_catalog.json with dept_name
จาก process5 getProjectDetail (field: deptSubName) — HTTP-only version

Strategy:
  สำหรับแต่ละ dept ที่ยังไม่มี dept_name:
    - call getProjectDetail(projectIds[0]) ผ่าน process5_http_client
    - extract deptSubName → save เข้า catalog[deptId].dept_name

ใช้งาน:
    python scripts/enrich_dept_names.py            # enrich ทั้งหมดที่ยังไม่มี
    python scripts/enrich_dept_names.py --limit 20 # enrich แค่ 20 ตัวแรก
    python scripts/enrich_dept_names.py --redo     # ทำใหม่ทุกตัว (overwrite)
"""
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from process5_http_client import get_project_detail

DATA_DIR     = Path(__file__).parent.parent / "data"
CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="limit จำนวน depts ที่ enrich (0=ไม่จำกัด)")
    ap.add_argument("--redo", action="store_true",
                    help="ทำใหม่ทุกตัว (overwrite existing dept_name)")
    args = ap.parse_args()

    if not CATALOG_FILE.exists():
        log(f"❌ ไม่พบ {CATALOG_FILE}")
        return

    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    log(f"Catalog: {len(catalog)} entries")

    to_enrich = []
    for dept_id, info in catalog.items():
        if not info.get("projectIds"):
            continue
        if info.get("dept_name") and not args.redo:
            continue
        to_enrich.append((dept_id, info["projectIds"][0]))

    if args.limit > 0:
        to_enrich = to_enrich[: args.limit]

    log(f"จะ enrich {len(to_enrich)} depts")
    if not to_enrich:
        log("ไม่มี dept ที่ต้อง enrich — เสร็จ")
        return

    success = 0
    fail    = 0
    started = time.time()

    for i, (dept_id, pid) in enumerate(to_enrich, 1):
        detail = get_project_detail(pid)
        dept_name = detail.get("dept_sub_name", "")
        if detail.get("valid") and dept_name:
            catalog[dept_id]["dept_name"]    = dept_name.strip()
            catalog[dept_id]["enriched_at"]  = datetime.now().isoformat(timespec="seconds")
            success += 1
            log(f"  [{i}/{len(to_enrich)}] {dept_id} → {dept_name[:60]}")
        else:
            fail += 1
            log(f"  [{i}/{len(to_enrich)}] {dept_id}: ❌ ไม่ได้ชื่อ")

        if i % 10 == 0:
            CATALOG_FILE.write_text(
                json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log(f"  💾 checkpoint ({success} success, {fail} fail)")

        time.sleep(1.0)

    CATALOG_FILE.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    elapsed = time.time() - started
    log(f"\n✅ DONE — enriched {success} (fail {fail}) ใน {elapsed/60:.1f} นาที")


if __name__ == "__main__":
    main()
