"""
enrich_dept_names.py — Enrich egp_deptid_catalog.json with dept_name
จาก process5 getProjectDetail (field: deptSubName)

Strategy:
  สำหรับแต่ละ active dept (มี projectIds):
    - ถ้ายังไม่มี dept_name → call getProjectDetail(projectIds[0])
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
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from Sebastian_Scraper import connect_browser

DATA_DIR = Path(__file__).parent.parent / "data"
CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"
PROCESS5_BASE = "https://process5.gprocurement.go.th"

JS_FETCH = """async (url) => {
    try {
        const r = await fetch(url, {credentials: 'include'});
        return await r.json();
    } catch(e) { return {error: e.toString()}; }
}"""


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_dept_name(page, project_id: str) -> tuple[str, str] | None:
    """Return (deptSubName, projectName) or None if fail"""
    url = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement/getProjectDetail?projectId={project_id}"
    try:
        body = page.evaluate(JS_FETCH, url)
        if not isinstance(body, dict):
            return None
        data = body.get("data") or {}
        if not isinstance(data, dict):
            return None
        dept_name = data.get("deptSubName") or ""
        proj_name = data.get("projectName") or ""
        if not dept_name:
            return None
        return dept_name.strip(), proj_name.strip()
    except Exception as e:
        log(f"  ⚠️ fetch error: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="limit จำนวน depts ที่ enrich (0=ไม่จำกัด)")
    ap.add_argument("--redo", action="store_true", help="ทำใหม่ทุกตัว (overwrite existing dept_name)")
    args = ap.parse_args()

    if not CATALOG_FILE.exists():
        log(f"❌ ไม่พบ {CATALOG_FILE}")
        return

    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    log(f"Catalog: {len(catalog)} entries")

    # หา depts ที่ต้อง enrich
    to_enrich = []
    for d, info in catalog.items():
        if not info.get("projectIds"):
            continue
        if info.get("dept_name") and not args.redo:
            continue
        to_enrich.append((d, info["projectIds"][0]))

    if args.limit > 0:
        to_enrich = to_enrich[: args.limit]

    log(f"จะ enrich {len(to_enrich)} depts")
    if not to_enrich:
        log("ไม่มี dept ที่ต้อง enrich — เสร็จ")
        return

    success = 0
    fail = 0
    started = time.time()

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto(f"{PROCESS5_BASE}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(3)

        for i, (dept_id, pid) in enumerate(to_enrich, 1):
            result = fetch_dept_name(page, pid)
            if result:
                dept_name, proj_name = result
                catalog[dept_id]["dept_name"] = dept_name
                catalog[dept_id]["enriched_at"] = datetime.now().isoformat(timespec="seconds")
                success += 1
                log(f"  [{i}/{len(to_enrich)}] {dept_id} → {dept_name[:60]}")
            else:
                fail += 1
                log(f"  [{i}/{len(to_enrich)}] {dept_id}: ❌ ไม่ได้ชื่อ")
            # save ทุก 10 ตัว (กัน crash เสียงาน)
            if i % 10 == 0:
                CATALOG_FILE.write_text(
                    json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                log(f"  💾 saved checkpoint ({success} success, {fail} fail)")
            time.sleep(1.0)  # rate limit guard

        page.close()

    # Final save
    CATALOG_FILE.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    elapsed = time.time() - started
    log(f"\n✅ DONE — enriched {success} (fail {fail}) ใน {elapsed/60:.1f} นาที")
    log(f"   Output: {CATALOG_FILE}")


if __name__ == "__main__":
    main()
