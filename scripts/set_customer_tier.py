"""set_customer_tier.py — แอดมินตั้งแพ็กเกจ + วันหมดอายุให้ลูกค้า (dry-run default).

บอร์ด /portal/world อ่าน tier จาก customers.tier (source of truth) และ
วันหมดอายุจาก customers.expires_at (ไม่ตั้ง → fallback created_at+30 วัน).
ไม่มีระบบจ่ายเงิน — ลูกค้ากดสนใจอัปเกรด → Discord → แอดมินปิดการขายแล้วรันตัวนี้.

ใช้:
  python set_customer_tier.py --list
  python set_customer_tier.py --user U1234abcd --tier standard --expires 2026-08-04
  python set_customer_tier.py --user U1234abcd --tier standard --expires 2026-08-04 --apply
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db

# mirror TIERS ids ใน dashboard/web/src/lib/portal-data.ts
VALID_TIERS = ("trial", "starter", "standard", "premium", "ultra")


def list_customers():
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT line_user_id, display_name, tier, expires_at, active, created_at "
            "FROM customers ORDER BY created_at").fetchall()
    if not rows:
        print("(ไม่มีลูกค้า)")
        return
    for r in rows:
        act = "✅" if r["active"] else "⛔"
        exp = r["expires_at"] or f"(auto: created+30 = {r['created_at'][:10] if r['created_at'] else '?'}+30)"
        print(f"{act} {r['line_user_id']}  {r['display_name'] or '(ไม่มีชื่อ)'}  "
              f"tier={r['tier'] or 'trial'}  expires={exp}")


def set_tier(user: str, tier: str, expires: str, apply: bool):
    if tier not in VALID_TIERS:
        sys.exit(f"tier ต้องเป็นหนึ่งใน {VALID_TIERS} (ได้ '{tier}')")
    if expires:
        try:
            datetime.strptime(expires, "%Y-%m-%d")
        except ValueError:
            sys.exit(f"expires ต้องเป็น YYYY-MM-DD (ได้ '{expires}')")
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id, display_name, tier, expires_at FROM customers WHERE line_user_id=?",
            (user,)).fetchone()
        if not row:
            sys.exit(f"ไม่พบลูกค้า line_user_id='{user}' (ดูรายชื่อด้วย --list)")
        print(f"ลูกค้า: {row['display_name'] or '(ไม่มีชื่อ)'} ({user})")
        print(f"  tier:    {row['tier'] or 'trial'} → {tier}")
        print(f"  expires: {row['expires_at'] or '(auto)'} → {expires or '(auto)'}")
        if not apply:
            print("DRY-RUN — ยังไม่เขียน (เติม --apply เพื่อบันทึกจริง)")
            return
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE customers SET tier=?, expires_at=?, updated_at=? WHERE id=?",
            (tier, expires or None, now, row["id"]))
    print("✅ บันทึกแล้ว")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="แสดงลูกค้าทั้งหมด + tier/expiry ปัจจุบัน")
    ap.add_argument("--user", help="line_user_id ของลูกค้า")
    ap.add_argument("--tier", help=f"หนึ่งใน {VALID_TIERS}")
    ap.add_argument("--expires", default="", help="วันหมดอายุ YYYY-MM-DD (เว้น = fallback created+30)")
    ap.add_argument("--apply", action="store_true", help="เขียนจริง (default dry-run)")
    args = ap.parse_args()
    db.init_schema()
    if args.list:
        list_customers()
        return
    if not args.user or not args.tier:
        ap.error("ต้องมี --user + --tier (หรือใช้ --list)")
    set_tier(args.user, args.tier, args.expires, args.apply)


if __name__ == "__main__":
    main()
