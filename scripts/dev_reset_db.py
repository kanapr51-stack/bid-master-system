"""
dev_reset_db.py — DEV ONLY: wipe and re-seed BMS database with test data.

NOT for production use.
Refuses to run if BMS_DATA_DIR points to /opt/bms/data (production path).
"""
import os
import sys
from pathlib import Path

# Production guard
data_dir = os.environ.get("BMS_DATA_DIR", "")
if "/opt/bms/data" in data_dir:
    print("ERROR: BMS_DATA_DIR points to production path. Refusing to reset.")
    print(f"  BMS_DATA_DIR={data_dir}")
    print("  Unset BMS_DATA_DIR or point to a dev path before running.")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import DB_PATH, init_schema, SubscriptionStore

print(f"[dev_reset_db] target DB: {DB_PATH}")

if DB_PATH.exists():
    DB_PATH.unlink()
    print(f"Removed: {DB_PATH}")

init_schema()
store = SubscriptionStore()

cid = store.add_customer("Uxxxxxxxxx_TEST", display_name="ทดสอบ บริษัทก่อสร้าง", tier="trial")
store.add_subscription(cid, provinces=["นครพนม", "บึงกาฬ"], min_budget=500_000)
print(f"Seeded: customer id={cid} (ทดสอบ บริษัทก่อสร้าง)")
print("Done — dev DB ready.")
