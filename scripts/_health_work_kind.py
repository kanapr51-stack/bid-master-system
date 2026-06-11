"""_health_work_kind.py — VPS health: ยืนยัน work_kind ทำงานบน prod (classifier + แยก new/reno จริง)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci
from Sebastian_Customer_DB import get_connection

print("=== work_kind classifier (โค้ดใหม่โหลดแล้ว?) ===")
for n in ["ปรับปรุงอาคารสำนักงาน", "ก่อสร้างอาคารสำนักงานใหม่", "ปรับปรุงถนนคอนกรีตเสริมเหล็ก",
          "ก่อสร้างถนนคอนกรีตเสริมเหล็ก", "ปรับปรุงไฟฟ้าส่องสว่าง", "ขุดลอกคลอง"]:
    sub = None if ci.is_building(n) else (ci.road_subtype(n) or ci.water_subtype(n))
    print(f"  {str(ci.work_kind(n, sub)):5s} (sub={sub}) | {n}")

print("\n=== intel_context จริง: อาคาร สร้างใหม่ vs ปรับปรุง (อ.บ้านแพง) ===")
conn = get_connection()
for name in ["ก่อสร้างอาคารสำนักงาน อบต. อำเภอบ้านแพง",
             "ปรับปรุงอาคารสำนักงาน อบต. อำเภอบ้านแพง"]:
    ctx = ci.intel_context("นครพนม", name, "องค์การบริหารส่วนตำบลบ้านแพง", "", 5000000, conn)
    p = ctx.get("prediction") if ctx else None
    if p and p.get("area_disc_med") is not None:
        print(f"  {name[:34]:34s} → ปกติ ลด {p['area_disc_med']:.0f}% (ชนะ {p.get('area_price_med'):,})")
    else:
        print(f"  {name[:34]:34s} → no prediction")
print("\n→ ถ้า ปรับปรุง ลด% ต่างจาก สร้างใหม่ = work_kind แยกจริงบน prod ✅")
