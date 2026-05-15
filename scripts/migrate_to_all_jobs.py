"""
migrate_to_all_jobs.py — Migration ครั้งเดียว (2026-05-15)

อ่าน raw_jobs.json จาก backup → map schema เก่า → schema ใหม่ของ all_jobs
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
BACKUP_DIR     = Path("backups/sheets_2026-05-15_2046")
NOW_ISO        = datetime.now().isoformat(timespec="seconds")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def extract_search_keyword(quantity_note: str) -> str:
    """quantity_note format: 'keyword:X | step' หรือ 'province:X | step' หรืออื่น ๆ"""
    if not quantity_note:
        return ""
    first = str(quantity_note).split("|", 1)[0].strip()
    for prefix in ("keyword:", "province:"):
        if first.startswith(prefix):
            return first[len(prefix):].strip()
    return ""


def main():
    log("=" * 60)
    log("Migrate raw_jobs.json → all_jobs")
    log("=" * 60)

    raw_path = BACKUP_DIR / "raw_jobs.json"
    if not raw_path.exists():
        log(f"❌ ไม่พบ {raw_path}")
        return

    raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
    log(f"  raw_jobs.json: {len(raw_rows)} rows")

    headers = raw_rows[0]
    log(f"  raw headers: {headers}")
    idx = {h: i for i, h in enumerate(headers)}

    def g(row, key, default=""):
        i = idx.get(key, -1)
        return row[i] if 0 <= i < len(row) else default

    # New schema (15 cols):
    # job_id title department province district subdistrict
    # procurement_type budget publish_date deadline
    # project_status search_keyword tor_url first_seen_at last_seen_at
    new_rows = []
    seen = set()
    for r in raw_rows[1:]:
        jid = str(g(r, "job_id", "")).strip()
        if not jid or jid in seen:
            continue
        seen.add(jid)
        new_rows.append([
            jid,
            g(r, "title"),
            g(r, "department"),
            g(r, "province"),
            g(r, "district"),
            g(r, "subdistrict"),
            g(r, "procurement_type"),
            g(r, "budget"),
            g(r, "publish_date"),
            g(r, "deadline"),
            g(r, "project_status"),
            extract_search_keyword(g(r, "quantity_note")),
            g(r, "tor_url"),
            NOW_ISO,
            NOW_ISO,
        ])

    log(f"  unique jobs after dedup: {len(new_rows)}")
    log(f"  duplicates removed: {len(raw_rows) - 1 - len(new_rows)}")

    log("\nWriting to all_jobs...")
    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    if new_rows:
        # gspread append_rows ส่งครั้งเดียว — handle large batch
        BATCH = 1000
        for i in range(0, len(new_rows), BATCH):
            chunk = new_rows[i:i+BATCH]
            ws.append_rows(chunk, value_input_option="USER_ENTERED")
            log(f"  appended {i + len(chunk)}/{len(new_rows)}")

    log(f"\n✅ Migration complete: {len(new_rows)} rows → all_jobs")


if __name__ == "__main__":
    main()
