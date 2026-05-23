"""
backfill_province.py — เติม province ให้ all_jobs ด้วย province_extractor

DEFAULT = dry-run (อ่านอย่างเดียว ไม่เขียน Sheet) → รายงานสถิติ
--write       เขียนจริง (เติมเฉพาะ row ที่ province ว่าง)
--overwrite   เขียนทับ province เดิมที่ extractor คิดว่าต่าง (ใช้ระวัง)

อ่าน header แบบ dynamic — หา column title/department/province เอง
"""
import sys
import time
import argparse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet                # noqa: E402
from province_extractor import extract_province      # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"

TITLE_KEYS = ["title", "ชื่อโครงการ", "project_name"]
DEPT_KEYS = ["department", "dept_sub_name", "dept_name", "หน่วยงาน", "ชื่อหน่วยงานย่อย"]
PROV_KEYS = ["province", "จังหวัด"]


def find_col(h_idx: dict, keys: list) -> int:
    for k in keys:
        if k in h_idx:
            return h_idx[k]
    return -1


def col_letter(idx: int) -> str:
    """0-based index → A1 column letter (รองรับ >26 คอลัมน์)"""
    s = ""
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(ord("A") + rem) + s
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="เขียนจริง (เติมที่ว่าง)")
    ap.add_argument("--overwrite", action="store_true",
                    help="เขียนทับ province เดิมที่ต่างด้วย (ระวัง)")
    args = ap.parse_args()

    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    rows = ws.get_all_values()
    hdrs = rows[0]
    h_idx = {h: i for i, h in enumerate(hdrs)}

    ci_title = find_col(h_idx, TITLE_KEYS)
    ci_dept = find_col(h_idx, DEPT_KEYS)
    ci_prov = find_col(h_idx, PROV_KEYS)
    print(f"header: title=col{ci_title} dept=col{ci_dept} province=col{ci_prov}({col_letter(ci_prov)})")
    if min(ci_title, ci_dept, ci_prov) < 0:
        raise SystemExit(f"หา column ไม่ครบ! headers={hdrs}")

    total = len(rows) - 1
    empty = filled = changed = same = 0
    fill_dist = Counter()
    change_samples = []
    updates = []  # (row_num, new_prov)

    def cell(r, i):
        return r[i].strip() if i < len(r) else ""

    for row_num, r in enumerate(rows[1:], start=2):
        title = cell(r, ci_title)
        dept = cell(r, ci_dept)
        cur = cell(r, ci_prov)
        pred = extract_province(dept, title)

        if not cur:
            empty += 1
            if pred:
                filled += 1
                fill_dist[pred] += 1
                updates.append((row_num, pred))
        else:
            if pred and pred != cur:
                changed += 1
                if len(change_samples) < 15:
                    change_samples.append((cur, pred, dept[:30], title[:35]))
                if args.overwrite:
                    updates.append((row_num, pred))
            else:
                same += 1

    # ── รายงาน ──
    print(f"\n=== all_jobs: {total} rows ===")
    print(f"  province ว่าง         : {empty}")
    print(f"    → extractor เติมได้ : {filled}  ({filled/empty:.1%} ของที่ว่าง)" if empty else "")
    print(f"  มี province อยู่แล้ว   : {total - empty}")
    print(f"    → ตรงกับ extractor  : {same}")
    print(f"    → extractor คิดต่าง : {changed}")
    print(f"\n  การกระจายของที่เติมใหม่ (top 12):")
    for p, n in fill_dist.most_common(12):
        print(f"    {p}: {n}")
    if change_samples:
        print(f"\n  ตัวอย่าง province เดิม vs extractor (อาจเป็น bug เก่า):")
        for cur, pred, dept, title in change_samples:
            print(f"    เดิม={cur} → ใหม่={pred} | {dept} | {title}")

    if not (args.write or args.overwrite):
        print(f"\n[DRY-RUN] ไม่เขียน Sheet — รัน --write เพื่อเติมที่ว่าง ({filled} rows)")
        return

    # ── เขียนจริง ──
    if not updates:
        print("\nไม่มีอะไรต้องเขียน")
        return

    # backup province column เดิมก่อนเขียน (กู้คืนได้)
    import json
    from datetime import datetime
    bdir = Path(__file__).parent.parent / "backups"
    bdir.mkdir(exist_ok=True)
    bfile = bdir / f"all_jobs_province_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup = {str(rn): cell(r, ci_prov) for rn, r in enumerate(rows[1:], start=2)}
    bfile.write_text(json.dumps(backup, ensure_ascii=False), encoding="utf-8")
    print(f"\n💾 backup province column → {bfile.name} ({len(backup)} rows)")

    print(f"✍️  เขียน {len(updates)} cells → all_jobs column {col_letter(ci_prov)} ...")
    # gspread ws.batch_update เติมชื่อ worksheet ให้เอง → ใช้แค่ A1 ของ cell
    batch = [{"range": f"{col_letter(ci_prov)}{rn}", "values": [[p]]}
             for rn, p in updates]
    CHUNK = 500
    for i in range(0, len(batch), CHUNK):
        ws.batch_update(batch[i:i + CHUNK], value_input_option="RAW")
        print(f"  เขียนแล้ว {min(i + CHUNK, len(batch))}/{len(batch)}")
        time.sleep(1)
    print("✅ เสร็จ")


if __name__ == "__main__":
    main()
