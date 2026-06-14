"""_show_card.py — render การ์ด D0 เต็มใบของงานตัวอย่าง (ดู intel + เจ้าตลาด จริง). debug ชั่วคราว.
project_id="" → ไม่เขียน save_prediction (กัน prod เปื้อน). รัน: BMS_DATA_DIR=/opt/bms/data python scripts/_show_card.py"""
import os, sys
os.environ.setdefault("BMS_DATA_DIR", "/opt/bms/data")
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls

SAMPLES = [
    dict(province="นครพนม", budget=2000000, deliver_day=120,
         project_name="ประกวดราคาจ้างก่อสร้างถนนคอนกรีตเสริมเหล็ก สายบ้านนาทม อำเภอนาทม จังหวัดนครพนม",
         dept_name="องค์การบริหารส่วนตำบลนาทม", bid_submit_date="2026-06-25", bid_submit_time="16:30"),
    dict(province="บึงกาฬ", budget=1500000, deliver_day=90,
         project_name="ประกวดราคาจ้างก่อสร้างถนนคอนกรีตเสริมเหล็ก อำเภอบึงโขงหลง จังหวัดบึงกาฬ",
         dept_name="องค์การบริหารส่วนตำบลบึงโขงหลง", bid_submit_date="2026-06-28", bid_submit_time="16:30"),
]

for s in SAMPLES:
    print("=" * 50)
    card = ls.format_notification(project_id="", announce_type="D0", **s)
    print(card)
    print()
