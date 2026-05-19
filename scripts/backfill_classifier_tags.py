"""
backfill_classifier_tags.py — เติม 8 columns ใหม่ (S:Z) ใน all_jobs ทุก row

ใช้ครั้งเดียวหลัง schema migration ของ Phase 1
รันซ้ำได้ — ถ้า column มีค่าอยู่แล้วจะ overwrite ด้วยค่าใหม่จาก rule

Usage:
  python scripts/backfill_classifier_tags.py [--dry-run] [--limit N]
"""

import sys
import argparse
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from classifier_tags import classify_all, TAG_COLUMNS

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SOURCE_SHEET = "all_jobs"
BATCH_SIZE = 1000  # rows per API call


def log(msg: str):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="คำนวณแต่ไม่เขียน Sheet")
    ap.add_argument("--limit", type=int, default=0, help="จำกัด N rows (0 = ทั้งหมด)")
    args = ap.parse_args()

    log("=" * 60)
    log(f"Backfill classifier tags → {SOURCE_SHEET}")
    log(f"  dry-run: {args.dry_run}")
    log(f"  limit:   {args.limit or 'all'}")
    log("=" * 60)

    ws = open_sheet(SPREADSHEET_ID, SOURCE_SHEET)
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        log("❌ sheet ว่าง — abort")
        return

    headers = all_values[0]
    h_idx = {h: i for i, h in enumerate(headers)}
    log(f"  headers: {len(headers)} cols, data rows: {len(all_values) - 1}")

    # Find column indices for tag columns
    tag_col_indices = {}
    for tag in TAG_COLUMNS:
        if tag not in h_idx:
            log(f"❌ missing column '{tag}' in sheet — run header migration first")
            return
        tag_col_indices[tag] = h_idx[tag]

    # First tag column letter
    first_tag_col_idx = min(tag_col_indices.values())
    last_tag_col_idx = max(tag_col_indices.values())
    first_letter = chr(ord("A") + first_tag_col_idx)
    last_letter = chr(ord("A") + last_tag_col_idx)
    log(f"  tag range: {first_letter}:{last_letter} (cols {first_tag_col_idx}-{last_tag_col_idx})")

    today = date.today()
    rows_to_update = all_values[1:]
    if args.limit > 0:
        rows_to_update = rows_to_update[: args.limit]

    log(f"\nClassifying {len(rows_to_update)} rows...")
    t0 = time.time()

    # Build new tag values for each row, ordered by sheet column index
    new_values = []
    skipped = 0
    for r in rows_to_update:
        # Build row dict
        row_dict = {}
        for col_name, idx in h_idx.items():
            row_dict[col_name] = r[idx] if 0 <= idx < len(r) else ""

        jid = row_dict.get("job_id", "")
        if not jid:
            new_values.append([""] * len(TAG_COLUMNS))
            skipped += 1
            continue

        tags = classify_all(row_dict, today)
        # Order tags by their sheet column index so they map S→Z correctly
        ordered = sorted(tag_col_indices.items(), key=lambda kv: kv[1])
        new_values.append([tags[name] for name, _ in ordered])

    log(f"  classified {len(new_values)} rows (skipped {skipped}) in {time.time()-t0:.1f}s")

    if args.dry_run:
        log("\n[dry-run] — skipping sheet write")
        from collections import Counter
        for col_pos, name in enumerate([n for n, _ in sorted(tag_col_indices.items(), key=lambda kv: kv[1])]):
            counter = Counter(row[col_pos] for row in new_values)
            log(f"\n  {name}:")
            for val, cnt in counter.most_common(8):
                log(f"    {val or '(empty)':20s}: {cnt} ({cnt*100/len(new_values):.1f}%)")
        return

    # Write to sheet — batched
    log(f"\nWriting to sheet (batch size {BATCH_SIZE})...")
    sheet_total = len(rows_to_update)
    written = 0
    for start in range(0, sheet_total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, sheet_total)
        chunk = new_values[start:end]
        # Sheet rows: header at row 1, so data row r corresponds to sheet row r+2
        # (0-indexed in chunk → sheet row = start + i + 2)
        start_row = start + 2
        end_row = end + 1  # inclusive
        rng = f"{SOURCE_SHEET}!{first_letter}{start_row}:{last_letter}{end_row}"
        ws.spreadsheet.values_update(
            rng,
            params={"valueInputOption": "USER_ENTERED"},
            body={"values": chunk},
        )
        written += len(chunk)
        log(f"  rows {start_row}-{end_row}: wrote {len(chunk)} (total {written}/{sheet_total})")

    log(f"\n✅ Done — wrote {written} rows in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
