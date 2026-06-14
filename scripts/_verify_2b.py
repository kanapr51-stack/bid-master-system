"""_verify_2b.py — smoke/tuning: เจ้าตลาด intel ต่อ scope จริง (v2 market-leader). debug ชั่วคราว.
รัน: BMS_DATA_DIR=/opt/bms/data python scripts/_verify_2b.py"""
import os, sys
os.environ.setdefault("BMS_DATA_DIR", "/opt/bms/data")
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf
from Sebastian_Customer_DB import get_connection

SCOPES = [("นครพนม", ["ถนน"]), ("นครพนม", ["อาคาร"]), ("นครพนม", ["ก่อสร้าง"]),
          ("บึงกาฬ", ["ถนน"]), ("บึงกาฬ", ["ก่อสร้าง"])]

with get_connection() as conn:
    for prov, tok in SCOPES:
        fr = bf.analyze_field(bf._field_auctions(conn, prov, tok))
        print(f"=== {prov} {tok} === n={fr['n_auctions']} tier={fr['tier']}")
        block = bf.field_lines(fr, 2_000_000)   # budget ตัวอย่าง 2M
        for ln in block:
            print(ln)
        if not block:
            print("  (ไม่โชว์ — tier0/ไม่มีเจ้าตลาด)")
        print()
