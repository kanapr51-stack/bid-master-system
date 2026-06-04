"""กู้ proc_type shift (61.5K) + เพิ่ม method_group ใน winner_history.db (2026-06-04).

Root cause: CGD column swap — header string 'วิธีการจัดหา ประกาศเชิญชวนทั่วไป คัดเลือก เฉพาะเจาะจง'
โผล่สลับระหว่าง field 'วิธีจัดซื้อฯ' กับ 'กลุ่มวิธีจัดซื้อฯ' → ค่าจริง = อันที่ไม่ใช่ header.
recompute proc_type จาก raw_json (source of truth, ไม่แตะ) ทั้งชุด → idempotent + reversible.
+ method_group = bucket วิธีจัดซื้อ (เฉพาะเจาะจง/แข่งขันราคา/คัดเลือก/อื่นๆ).
"""
import sqlite3, json, gzip, sys, time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
DB = "data/winner_history.db"
BACKUP_DIR = Path("backups"); BACKUP_DIR.mkdir(exist_ok=True)
HEADER = "วิธีการจัดหา ประกาศเชิญชวนทั่วไป คัดเลือก เฉพาะเจาะจง"


def real_method(d: dict) -> str:
    v = (d.get("วิธีจัดซื้อฯ") or "").strip()
    g = (d.get("กลุ่มวิธีจัดซื้อฯ") or "").strip()
    return v if v and v != HEADER else g


def method_group(m: str) -> str:
    if any(k in m for k in ["ประกวดราคา", "สอบราคา", "e-bidding", "อิเล็กทรอนิกส์", "เชิญชวน", "e-market"]):
        return "แข่งขันราคา"
    if "คัดเลือก" in m:
        return "คัดเลือก"
    if any(k in m for k in ["เฉพาะเจาะจง", "ตกลง", "พิเศษ"]):
        return "เฉพาะเจาะจง"
    return "อื่นๆ"


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 1) snapshot (rowid, proc_type) เดิม — rollback ได้ (เบา, ไม่ copy 2.6GB)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = BACKUP_DIR / f"proctype_snapshot_{ts}.json.gz"
    old = cur.execute("SELECT rowid, proc_type FROM winner_history").fetchall()
    with gzip.open(snap, "wt", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False)
    print(f"📦 snapshot {len(old):,} rows → {snap}")

    # 2) ADD COLUMN method_group (idempotent)
    cols = [r[1] for r in cur.execute("PRAGMA table_info(winner_history)")]
    if "method_group" not in cols:
        cur.execute("ALTER TABLE winner_history ADD COLUMN method_group TEXT")
        print("➕ ADD COLUMN method_group")
    else:
        print("• method_group มีอยู่แล้ว — overwrite")

    # 3) recompute proc_type + method_group จาก raw_json ทั้งชุด
    t0 = time.time()
    updates = []
    n = 0
    for rowid, rj in cur.execute("SELECT rowid, raw_json FROM winner_history"):
        try:
            d = json.loads(rj)
        except Exception:
            continue
        m = real_method(d) or "(ว่าง)"
        updates.append((m, method_group(m), rowid))
        n += 1
    cur.executemany("UPDATE winner_history SET proc_type=?, method_group=? WHERE rowid=?", updates)
    con.commit()
    print(f"✅ recompute {n:,} rows ({time.time()-t0:.0f}s)")

    # 4) sanity
    print("\n=== SANITY ===")
    left = cur.execute("SELECT COUNT(*) FROM winner_history WHERE proc_type=?", (HEADER,)).fetchone()[0]
    print(f"proc_type ยังเป็น header (ต้อง=0): {left}")
    print("method_group dist:")
    for v, c in cur.execute("SELECT method_group, COUNT(*) FROM winner_history GROUP BY method_group ORDER BY 2 DESC"):
        print(f"  {c:>7,}  {v}")
    print("proc_type top 6:")
    for v, c in cur.execute("SELECT proc_type, COUNT(*) FROM winner_history GROUP BY proc_type ORDER BY 2 DESC LIMIT 6"):
        print(f"  {c:>7,}  {v[:45]}")
    con.close()


if __name__ == "__main__":
    main()
