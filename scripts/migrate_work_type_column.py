"""migrate_work_type_column.py — Phase 1: เพิ่ม work_type + work_type_version ใน winner_history.db.
แบบเดียวกับ _winner_history_proctype_fix.py: snapshot → idempotent ADD COLUMN → recompute → sanity.
recompute เฉพาะงานจ้างก่อสร้าง (ชื่อประเภทโครงการ=จ้างก่อสร้าง) — งานซื้อ/เช่า เก็บ NULL.
เก็บ work_type = primary (เดี่ยว). secondary/all คำนวณ runtime ตอนทำ analytics (Task 6).
รัน: python scripts/migrate_work_type_column.py
"""
import gzip
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from work_type_classifier import classify_work_type, WORK_TYPE_VERSION  # noqa: E402

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "winner_history.db"
BACKUP_DIR = ROOT / "backups"
BACKUP_DIR.mkdir(exist_ok=True)


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 1) snapshot (rowid, work_type เดิมถ้ามี) — เบา, rollback ได้
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cols = [r[1] for r in cur.execute("PRAGMA table_info(winner_history)")]
    if "work_type" in cols:
        snap = BACKUP_DIR / f"work_type_snapshot_{ts}.json.gz"
        old = cur.execute("SELECT rowid, work_type, work_type_version FROM winner_history").fetchall()
        with gzip.open(snap, "wt", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False)
        print(f"📦 snapshot {len(old):,} rows → {snap.name}")

    # 2) ADD COLUMN (idempotent)
    if "work_type" not in cols:
        cur.execute("ALTER TABLE winner_history ADD COLUMN work_type TEXT")
        print("➕ ADD COLUMN work_type")
    if "work_type_version" not in cols:
        cur.execute("ALTER TABLE winner_history ADD COLUMN work_type_version TEXT")
        print("➕ ADD COLUMN work_type_version")

    # 3) recompute เฉพาะงานจ้างก่อสร้าง
    t0 = time.time()
    updates = []
    n = 0
    for rowid, rj in cur.execute("SELECT rowid, raw_json FROM winner_history"):
        try:
            d = json.loads(rj)
        except Exception:
            continue
        if d.get("ชื่อประเภทโครงการ") != "จ้างก่อสร้าง":
            continue
        name = d.get("ชื่อโครงการ") or ""
        primary = classify_work_type(name)["primary"]
        updates.append((primary, WORK_TYPE_VERSION, rowid))
        n += 1
    cur.executemany(
        "UPDATE winner_history SET work_type=?, work_type_version=? WHERE rowid=?", updates
    )
    con.commit()
    print(f"✅ recompute {n:,} construction rows ({time.time()-t0:.0f}s)")

    # 4) sanity
    print("\n=== SANITY ===")
    total = cur.execute("SELECT COUNT(*) FROM winner_history").fetchone()[0]
    tagged = cur.execute("SELECT COUNT(*) FROM winner_history WHERE work_type IS NOT NULL").fetchone()[0]
    print(f"total (ต้อง=617,357): {total:,}")
    print(f"tagged (ต้อง ~52,525): {tagged:,}")
    print("work_type distribution:")
    for v, c in cur.execute(
        "SELECT work_type, COUNT(*) FROM winner_history WHERE work_type IS NOT NULL "
        "GROUP BY work_type ORDER BY 2 DESC"
    ):
        print(f"  {c:>7,}  {v}")
    con.close()


if __name__ == "__main__":
    main()
