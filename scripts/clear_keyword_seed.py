"""clear_keyword_seed.py — ลบ 89-keyword seed (N+181) ออกจาก customers.notes.
"ไม่มี keyword = เห็น/ส่งทั้งจังหวัด". idempotent. รัน one-off บน prod แบบ:
    BMS_DATA_DIR=/opt/bms/data python scripts/clear_keyword_seed.py --apply
(default = dry-run; --apply เท่านั้นถึงเขียน). backup DB ก่อนเสมอ (ดู Rollout)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import get_connection


def clear_keyword_seed(conn) -> int:
    """ลบ key 'classes' ออกจาก notes JSON ของทุก customer ที่มี. คืนจำนวนแถวที่แก้."""
    rows = conn.execute("SELECT id, notes FROM customers WHERE notes IS NOT NULL AND notes!=''").fetchall()
    changed = 0
    for r in rows:
        try:
            parsed = json.loads(r["notes"])
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("classes"):
            parsed["classes"] = []
            conn.execute("UPDATE customers SET notes=? WHERE id=?",
                         (json.dumps(parsed, ensure_ascii=False), r["id"]))
            changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="เขียนจริง (default = dry-run)")
    args = ap.parse_args()
    with get_connection() as conn:
        if not args.apply:
            rows = conn.execute("SELECT id, notes FROM customers WHERE notes LIKE '%\"classes\"%'").fetchall()
            print(f"[dry-run] จะเคลียร์ classes ของ {len(rows)} customer (ใส่ --apply เพื่อเขียนจริง)", flush=True)
            return
        n = clear_keyword_seed(conn)
    print(f"✅ เคลียร์ keyword seed แล้ว {n} customer", flush=True)


if __name__ == "__main__":
    main()
