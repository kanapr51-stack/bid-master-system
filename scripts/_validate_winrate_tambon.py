"""_validate_winrate_tambon.py — closed-loop validate B′ ladder/conf สำหรับงานพื้นที่เป้าหมาย.
รันบน VPS (BMS_DATA_DIR=/opt/bms/data — ที่มี cgd_winners + bid_results backfilled).

  BMS_DATA_DIR=/opt/bms/data python3 scripts/_validate_winrate_tambon.py

ใช้ตรวจผล RECENT_FY += 2569 (2026-06-16): ต.บึงโขงหลง ยังติด 🟠 จังหวัด หรือเลื่อนเป็น 🟡 อำเภอ/🟢 local.
อ่านบรรทัด log:  INFO winrate basis=... conf=<local|อำเภอ|จังหวัด> ess=.. k_local=.. fail_reason=..
นั่นคือ conf tier จริง (จาก bid_field.field_and_winrate) — ไม่ใช่เดาจาก emoji ในการ์ด.
"""
import sys, logging
sys.path.insert(0, "scripts")
import cgd_intel as ci

# เปิดเฉพาะ log ของ bid_field (เห็นบรรทัด "winrate basis=.. conf=.." ที่บอก tier จริง)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("bid_field").setLevel(logging.INFO)

# งานทดสอบ — ถนนคอนกรีต งบเทียบ N+139/N+140
CASES = [
    ("บึงกาฬ",
     "ก่อสร้างถนนคอนกรีตเสริมเหล็ก ตำบลบึงโขงหลง อำเภอบึงโขงหลง จังหวัดบึงกาฬ",
     "องค์การบริหารส่วนตำบลบึงโขงหลง", 1_500_000),
    ("นครพนม",
     "ก่อสร้างถนนคอนกรีตเสริมเหล็ก ตำบลนาทม อำเภอนาทม จังหวัดนครพนม",
     "องค์การบริหารส่วนตำบลนาทม", 2_000_000),
]

print(f"RECENT_FY = {ci.RECENT_FY}\n")
for prov, name, dept, budget in CASES:
    print("=" * 70)
    print(f"📍 {name}  (งบ {budget:,})")
    print("  [ดู log 'winrate ... conf=' ด้านล่างนี้ = tier จริง]")
    ctx = ci.intel_context(prov, name, dept, project_id="", budget=budget)
    if not ctx:
        print("  ❌ intel_context = None (ไม่มี work-type/คู่แข่ง)")
        continue
    print("  --- การ์ด ---")
    for l in ctx["lines"]:
        print("   ", l)
    print()
