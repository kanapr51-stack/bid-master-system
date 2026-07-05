"""
backup_db.py — Daily SQLite backup for BMS production database

Copies bms_customers.db → /opt/bms/backups/bms_YYYYMMDD.db
Retains last 5 days, prunes older backups.
(เดิม 14 วัน — DB โต 439MB→1.9GB หลัง backfill สกลนคร ทำให้ 14 วัน ≈ 27GB
ดิสก์ VPS 52GB เต็ม 100% เมื่อ 2026-07-05 — ดู progress_log N+186)
Run daily at 03:00 via bms-backup.timer
"""
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TH          = timezone(timedelta(hours=7))
NOW         = datetime.now(TH)
DATA_DIR    = Path(os.environ.get("BMS_DATA_DIR") or "/opt/bms/data")
BACKUP_DIR  = Path(os.environ.get("BMS_BACKUP_DIR") or "/opt/bms/backups")
RETAIN_DAYS = 5


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    src = DATA_DIR / "bms_customers.db"
    if not src.exists():
        print(f"ERROR: source DB not found: {src}", file=sys.stderr)
        sys.exit(1)

    dst      = BACKUP_DIR / f"bms_{NOW.strftime('%Y%m%d')}.db"
    shutil.copy2(src, dst)
    # ดิสก์เต็มระหว่างก็อป → ได้ไฟล์ขาดเงียบๆ (เจอจริง 2026-07-05: 361MB/829MB จาก 1.9GB)
    # — ตรวจขนาดเทียบต้นฉบับ ถ้าไม่ครบให้ลบทิ้งแล้ว fail ดังๆ
    if dst.stat().st_size != src.stat().st_size:
        got, want = dst.stat().st_size, src.stat().st_size
        dst.unlink()
        print(f"ERROR: backup truncated ({got} != {want} bytes) — deleted, check disk space",
              file=sys.stderr)
        sys.exit(1)
    size_kb  = dst.stat().st_size // 1024
    print(f"Backup: {dst.name} ({size_kb} KB)")

    # Prune backups older than RETAIN_DAYS
    cutoff = NOW - timedelta(days=RETAIN_DAYS)
    for f in sorted(BACKUP_DIR.glob("bms_????????.db")):
        try:
            date_str  = f.stem.split("_")[1]
            file_date = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=TH)
            if file_date < cutoff:
                f.unlink()
                print(f"Pruned: {f.name}")
        except (ValueError, IndexError):
            pass

    print(f"Done — {len(list(BACKUP_DIR.glob('bms_*.db')))} backup(s) retained")


if __name__ == "__main__":
    main()
