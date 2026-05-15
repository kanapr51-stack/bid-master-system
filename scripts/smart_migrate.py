"""
smart_migrate.py — Re-migrate raw_jobs.json → all_jobs โดย detect schema variant per-row

raw_jobs.json มี 3 variants ปนกัน:
  Variant A (737 rows): tor_url='new', status=mapped, project_status=raw 'province:X | flow'
  Variant B (7,353 rows): tor_url=URL, status='', project_status=mapped — ถูกอยู่แล้ว
  Variant C (601 rows): tor_url='skip'/'docs_failed', status=raw 'keyword:X | flow', project_status=ตัวเลข

Strategy:
  - Detect variant per-row จาก signature ของ tor_url + project_status
  - Extract flow_name + search_keyword จากที่ที่ถูกต้องของ variant นั้น
  - Map flow_name → project_status ผ่าน FLOW_STATUS_MAP

วิธีใช้:
    1. (Backup all_jobs ปัจจุบันลง JSON อัตโนมัติ)
    2. python scripts/smart_migrate.py
    3. Confirm prompt → clear all_jobs + rewrite
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from Sebastian_Scraper import FLOW_STATUS_MAP

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
RAW_JOBS_FILE  = Path("backups/sheets_2026-05-15_2046/raw_jobs.json")
BACKUP_DIR     = Path("backups/all_jobs_pre_smart_migrate")


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def extract_kw_and_flow(s: str) -> tuple[str, str]:
    """'province:X | flowName' หรือ 'keyword:X | flowName' → (X, flowName)"""
    if not s or "|" not in s:
        return "", ""
    left, right = s.split("|", 1)
    left = left.strip()
    flow = right.strip()
    keyword = ""
    for prefix in ("province:", "keyword:"):
        if left.startswith(prefix):
            keyword = left[len(prefix):].strip()
            break
    return keyword, flow


def normalize_row(r: list, idx: dict) -> dict:
    """
    ตรวจ schema variant ของ raw row → return dict ที่ field ถูกต้อง
    คืน None ถ้า row ไม่มี job_id
    """
    def g(key):
        i = idx.get(key, -1)
        return r[i] if 0 <= i < len(r) else ""

    jid = str(g("job_id")).strip()
    if not jid:
        return None

    tu = str(g("tor_url")).strip()
    ps_raw = str(g("project_status")).strip()
    status_raw = str(g("status")).strip()
    qn_raw = str(g("quantity_note")).strip()

    # ── Variant detection ──
    flow_name = ""
    search_keyword = ""
    tor_url = ""
    project_status = ""

    if tu == "new" and (ps_raw.startswith("province:") or ps_raw.startswith("keyword:")):
        # Variant A: ของจริงอยู่ใน status (already mapped) + project_status = raw_qn
        project_status = status_raw  # mapped value แล้ว เช่น "ประมูลแล้ว"
        search_keyword, flow_name = extract_kw_and_flow(ps_raw)
        tor_url = ""
        # ถ้า project_status ว่าง → fallback derive จาก flow_name
        if not project_status and flow_name:
            project_status = FLOW_STATUS_MAP.get(flow_name, flow_name)

    elif tu in ("skip", "docs_failed") and ps_raw.isdigit():
        # Variant C: ของจริงอยู่ใน status เป็น raw_qn → ต้อง map
        search_keyword, flow_name = extract_kw_and_flow(status_raw)
        project_status = FLOW_STATUS_MAP.get(flow_name, "")
        tor_url = ""  # 'skip'/'docs_failed' ไม่ใช่ URL จริง

    elif (status_raw.startswith("province:") or status_raw.startswith("keyword:")) and not ps_raw.startswith("province:"):
        # Variant C-ish: status เป็น raw_qn แต่ project_status อาจ mapped ถูกแล้ว
        search_keyword, flow_name = extract_kw_and_flow(status_raw)
        project_status = ps_raw if ps_raw and not ps_raw.isdigit() else FLOW_STATUS_MAP.get(flow_name, "")
        tor_url = "" if tu in ("new", "skip", "docs_failed") else tu

    else:
        # Variant B (default): schema สมบูรณ์
        project_status = ps_raw
        # quantity_note มี keyword, แต่ raw_jobs.json column 'quantity_note' บางทีว่าง
        # → ลอง extract จาก quantity_note ก่อน, ถ้าไม่ได้ → derive จาก flow ถ้า status มี
        if qn_raw:
            search_keyword, flow_name = extract_kw_and_flow(qn_raw)
        elif status_raw and ("|" in status_raw):
            search_keyword, flow_name = extract_kw_and_flow(status_raw)
        tor_url = "" if tu in ("new", "skip", "docs_failed") else tu

    # ── Build clean row ──
    return {
        "job_id":           jid,
        "title":            g("title"),
        "department":       g("department"),
        "province":         g("province"),
        "district":         g("district"),
        "subdistrict":      g("subdistrict"),
        "procurement_type": g("procurement_type"),
        "budget":           g("budget"),
        "publish_date":     g("publish_date"),
        "deadline":         g("deadline"),
        "project_status":   project_status,
        "search_keyword":   search_keyword,
        "tor_url":          tor_url,
    }


def main():
    log("=" * 60)
    log("Smart Re-Migration: raw_jobs.json → all_jobs")
    log("=" * 60)

    # ── Step 1: Backup current all_jobs ──
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_file = BACKUP_DIR / f"all_jobs_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    log(f"\n[1/4] Backup all_jobs ปัจจุบัน → {backup_file.name}")
    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    current = ws.get_all_values()
    backup_file.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"   backed up {len(current)} rows")

    # ── Step 2: Load raw + normalize per-row ──
    log(f"\n[2/4] อ่าน {RAW_JOBS_FILE}...")
    raw = json.loads(RAW_JOBS_FILE.read_text(encoding="utf-8"))
    raw_headers = raw[0]
    idx = {h: i for i, h in enumerate(raw_headers)}
    log(f"   raw rows: {len(raw) - 1}")
    log(f"   raw headers: {raw_headers}")

    log("\n[3/4] Normalize ทุก row + dedup by job_id (เก็บล่าสุด)...")
    seen = {}
    variant_counts = {"A_old": 0, "B_clean": 0, "C_skip": 0, "fallback": 0}
    unmapped_status = 0

    for r in raw[1:]:
        # Detect variant for stats
        tu = r[idx["tor_url"]] if idx["tor_url"] < len(r) else ""
        ps = r[idx["project_status"]] if idx["project_status"] < len(r) else ""
        if tu == "new" and (str(ps).startswith("province:") or str(ps).startswith("keyword:")):
            variant_counts["A_old"] += 1
        elif tu in ("skip", "docs_failed") and str(ps).isdigit():
            variant_counts["C_skip"] += 1
        elif ps in ("กำลังประมูล","ประมูลแล้ว","ยกเลิก","กำลังเตรียม","รายงานขอซื้อขอจ้าง",""):
            variant_counts["B_clean"] += 1
        else:
            variant_counts["fallback"] += 1

        norm = normalize_row(r, idx)
        if not norm:
            continue
        if not norm["project_status"]:
            unmapped_status += 1
        # Dedup: เก็บ row ล่าสุด (ตามลำดับใน raw — last write wins)
        seen[norm["job_id"]] = norm

    log(f"   variant breakdown:")
    for k, v in variant_counts.items():
        log(f"     {k}: {v}")
    log(f"   unique job_ids: {len(seen)}")
    log(f"   rows with unmapped project_status: {unmapped_status}")

    # ── Step 3: Build sheet rows ──
    new_headers = [
        "job_id", "title", "department", "province", "district", "subdistrict",
        "procurement_type", "budget", "publish_date", "deadline",
        "project_status", "search_keyword", "tor_url",
        "first_seen_at", "last_seen_at",
    ]
    now_iso = datetime.now().isoformat(timespec="seconds")
    new_rows = [
        [
            n["job_id"], n["title"], n["department"], n["province"], n["district"],
            n["subdistrict"], n["procurement_type"], n["budget"], n["publish_date"],
            n["deadline"], n["project_status"], n["search_keyword"], n["tor_url"],
            now_iso, now_iso,
        ]
        for n in seen.values()
    ]

    log(f"\n[4/4] เตรียม update sheet (clear + write {len(new_rows)} rows)")
    response = input("\nพิมพ์ 'YES' เพื่อ confirm: ").strip()
    if response != "YES":
        log("ยกเลิก — sheet ไม่ถูกแก้ไข")
        return

    log("Clearing all_jobs...")
    ws.clear()
    log("Writing headers + first 1000 rows...")
    ws.update([new_headers] + new_rows[:1000], "A1", value_input_option="USER_ENTERED")

    BATCH = 1000
    for i in range(1000, len(new_rows), BATCH):
        chunk = new_rows[i:i+BATCH]
        ws.append_rows(chunk, value_input_option="USER_ENTERED")
        log(f"  appended rows {i+1}-{i+len(chunk)}")

    log(f"\n✅ Smart migration complete: {len(new_rows)} rows → all_jobs")
    log(f"   Backup ที่: {backup_file}")
    log(f"\nรัน Classifier ใหม่: python scripts/Sebastian_Classifier.py")


if __name__ == "__main__":
    main()
