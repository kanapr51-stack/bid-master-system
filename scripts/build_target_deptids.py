"""
build_target_deptids.py — map egp_w0_catalog.json → target_deptids.json

ขั้นตอน:
  1. โหลด egp_w0_catalog.json (จาก --probe-w0-full GHA run)
  2. สำหรับแต่ละ deptId ที่มี items: เรียก getProjectDetail → deptSubName
  3. ถ้า deptSubName มี keyword จากจังหวัดเป้าหมาย → เพิ่มใน target list
  4. บันทึก data/target_deptids.json (list ของ deptIds)

Usage:
    python scripts/build_target_deptids.py [--dry-run] [--workers N]

ข้อกำหนด: egp_w0_catalog.json ต้องมีอยู่ใน data/
  (รัน GHA catalog_discovery.yml mode=w0_full ก่อน)
"""

import sys
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from process5_http_client import get_project_detail

DATA_DIR = Path(__file__).parent.parent / "data"
W0_CATALOG_FILE  = DATA_DIR / "egp_w0_catalog.json"
TARGET_FILE      = DATA_DIR / "target_deptids.json"
RESULT_MAP_FILE  = DATA_DIR / "deptid_subname_map.json"  # ผล mapping เต็ม

# คำค้นจังหวัด/อำเภอเป้าหมาย (ตรงกับ deptSubName)
TARGET_PROVINCE_KEYWORDS = [
    "นครพนม", "บึงกาฬ",
    "บ้านแพง", "บึงโขงหลง",
    "ศรีสงคราม", "นาแก", "ท่าอุเทน", "ธาตุพนม",
    "เรณูนคร", "โพนสวรรค์", "นาหว้า", "วังยาง", "นาทม",
    "ปากคาด", "เซกา", "โซ่พิสัย", "พรเจริญ", "บึงโขงหลง",
    "ศรีวิไล", "บุ่งคล้า",
]

DEFAULT_WORKERS = 10


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_dept_subname(dept_id: str, project_ids: list[str]) -> str | None:
    """เรียก getProjectDetail สำหรับ project แรกที่ใช้งานได้ → คืน deptSubName"""
    for pid in project_ids[:3]:  # ลอง 3 project สำรอง
        if not pid:
            continue
        try:
            detail = get_project_detail(pid.lstrip("P"))
            subname = detail.get("dept_sub_name", "").strip()
            if subname:
                return subname
        except Exception:
            pass
        time.sleep(0.3)
    return None


def main():
    parser = argparse.ArgumentParser(description="Map W0 catalog deptIds → target provinces")
    parser.add_argument("--dry-run", action="store_true", help="แสดงผล ไม่บันทึกไฟล์")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"จำนวน workers (default={DEFAULT_WORKERS})")
    args = parser.parse_args()

    if not W0_CATALOG_FILE.exists():
        log(f"❌ ไม่พบ {W0_CATALOG_FILE}")
        log("  → รัน GHA catalog_discovery.yml mode=w0_full ก่อน")
        sys.exit(1)

    w0_catalog: dict = load_json(W0_CATALOG_FILE, {})
    log(f"โหลด egp_w0_catalog.json: {len(w0_catalog)} depts")

    # โหลด existing map (resume กรณี interrupted)
    dept_subname_map: dict[str, str] = load_json(RESULT_MAP_FILE, {})
    already_done = set(dept_subname_map.keys())
    log(f"ข้าม {len(already_done)} depts ที่ map แล้ว")

    to_process = [(did, info) for did, info in w0_catalog.items()
                  if did not in already_done and info.get("projectIds")]
    log(f"เหลือ {len(to_process)} depts ต้อง getProjectDetail")

    if not to_process:
        log("ไม่มีงานเพิ่มเติม — ใช้ map ที่มีอยู่")
    else:
        def _do(item):
            dept_id, info = item
            subname = get_dept_subname(dept_id, info.get("projectIds", []))
            return dept_id, subname

        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(_do, item): item[0] for item in to_process}
            for fut in as_completed(futs):
                dept_id, subname = fut.result()
                done += 1
                dept_subname_map[dept_id] = subname or ""
                if subname:
                    is_target = any(kw in subname for kw in TARGET_PROVINCE_KEYWORDS)
                    if is_target:
                        log(f"  🎯 {dept_id}: {subname}")
                    # else: quiet

                if done % 50 == 0:
                    log(f"  ↳ {done}/{len(to_process)} done")
                    if not args.dry_run:
                        save_json(RESULT_MAP_FILE, dept_subname_map)

        if not args.dry_run:
            save_json(RESULT_MAP_FILE, dept_subname_map)
            log(f"💾 deptid_subname_map.json: {len(dept_subname_map)} entries")

    # Filter target depts
    target_depts = sorted(
        did for did, subname in dept_subname_map.items()
        if subname and any(kw in subname for kw in TARGET_PROVINCE_KEYWORDS)
    )
    log(f"\n🎯 Target-area depts found: {len(target_depts)}")
    for did in target_depts:
        log(f"  {did}: {dept_subname_map[did]}")

    if args.dry_run:
        log("\n[dry-run] ไม่บันทึก target_deptids.json")
        return

    # Merge กับ existing target_deptids.json
    existing: list[str] = load_json(TARGET_FILE, [])
    if not isinstance(existing, list):
        existing = []

    # โหลด D0 catalog active depts ด้วย (ต้องไม่หาย)
    d0_catalog_file = DATA_DIR / "egp_deptid_catalog.json"
    d0_active: list[str] = []
    if d0_catalog_file.exists():
        d0_cat = load_json(d0_catalog_file, {})
        d0_active = [did for did, v in d0_cat.items()
                     if isinstance(v, dict) and v.get("item_count", 0) > 0]

    merged = sorted(set(existing) | set(target_depts) | set(d0_active))
    save_json(TARGET_FILE, merged)
    log(f"\n✅ target_deptids.json: {len(merged)} depts")
    log(f"   = {len(target_depts)} new W0-mapped + {len(d0_active)} D0-active + {len(existing)} existing")


if __name__ == "__main__":
    main()
