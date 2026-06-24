"""test_portal_page.py — _portal_page_html render 4 กลุ่ม + winner + prelim + countdown + empty + escape."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_DB_PATH"] = str(Path(os.environ["BMS_DATA_DIR"]) / "x.db")
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import bms_api as api


def _job(**kw):
    base = {"project_id": "P", "name": "งาน", "location": "จ.บึงกาฬ", "deadline": "", "deadline_time": "",
            "pred_lo": None, "pred_hi": None, "winner": None, "winner_price": None,
            "winner_disc": None, "competitors": [], "bidders": [], "prelim_low": None, "prelim_n": 0}
    base.update(kw)
    return base


groups = {
    "bidding": [_job(project_id="PD", name="ถนน คสล. บ้านนาสาร", location="ต.โพธิ์หมากแข้ง จ.บึงกาฬ",
                     deadline="2026-12-31", deadline_time="09.00-16.00 น.", pred_lo=679000, pred_hi=730000)],
    "prelim": [_job(project_id="PP", name="งานสรุปราคา", prelim_low=738000.0, prelim_n=3)],
    "won": [_job(project_id="PW", name="ถนน W", winner="หจก.X", winner_price=738000.0,
                 winner_disc=26.2, competitors=[{"name": "หจก.Y", "price": 752000.0}],
                 bidders=[{"name": "หจก.X", "price": 738000.0, "is_winner": True, "is_sme": False},
                          {"name": "หจก.Y", "price": 752000.0, "is_winner": False, "is_sme": True}])],
    "pre": [_job(project_id="PB", name="<script>x</script>")],
}
h = api._portal_page_html(groups, 2000000000, "TOK")
assert "งานที่คุณติดตาม (4)" in h, h
# req3 + req4: bidding label เปลี่ยน + วันที่ไทย + countdown
assert "ประกาศวันยื่นซอง" in h and "กำลังประมูล" not in h, h
assert "ยื่นซอง 31 ธ.ค. 2569 09.00-16.00 น." in h and "เหลืออีก" in h, h
assert "679,000" in h, h
# req2: prelim แยกจาก won ทางการ
assert "สรุปราคาเบื้องต้น" in h and "ราคาต่ำสุดที่เสนอ 738,000 บาท (3 ราย)" in h, h
assert "ประกาศผู้ชนะทางการ" in h and "ประกาศผล</span>" not in h, h
assert "หจก.X" in h and "738,000" in h and "ลด 26%" in h, h
# ทุกกลุ่มเป็นลิงก์ไปหน้า detail (won + bidding + prelim + pre)
assert "/portal/job?t=TOK&pid=PW" in h, "การ์ด won ต้องลิงก์ไป detail"
assert "/portal/job?t=TOK&pid=PD" in h, "การ์ด bidding ต้องลิงก์ไป detail"
assert "/portal/job?t=TOK&pid=PP" in h, "การ์ด prelim ต้องลิงก์ไป detail"
assert "/portal/job?t=TOK&pid=PB" in h, "การ์ด pre ต้องลิงก์ไป detail"
assert "ดูผู้ยื่นทั้งหมด" in h and "ดูรายละเอียด" in h, h
assert "querySelectorAll('.clickable')" not in h and "class=\"detail\"" not in h, h
# req5: pre label เปลี่ยน
assert "รับฟังคำประชาวิจารณ์" in h and "รับฟังความเห็น" not in h, h
# escape ยังทำงาน (ชื่องาน escape — script injection ในชื่อต้องไม่หลุด)
assert "&lt;script&gt;x&lt;/script&gt;" in h, "escape ชื่อผิด"
# แถบค้นหา + ID ใต้ชื่อ
assert "class=\"search\"" in h and "ค้นหางาน" in h, "ไม่มีแถบค้นหา"
assert "🆔 PD" in h and "🆔 PW" in h, "ไม่มี ID ใต้ชื่อ"
assert "querySelectorAll('.gw')" in h, "ไม่มี JS filter"
# หน้าว่าง: ไม่มีแถบค้นหา
h0 = api._portal_page_html({"won": [], "bidding": [], "pre": []}, 0, "TOK")
assert "ยังไม่มีงานที่ติดตาม" in h0 and "class=\"search\"" not in h0, h0
print("OK test_portal_page")

# --- ⭐ ที่สนใจ: ปุ่มดาวบนการ์ด + ชิป filter อิสระ ---
groups2 = dict(groups)
groups2["bidding"] = [dict(groups["bidding"][0], starred=True)]
groups2["pre"] = [dict(groups["pre"][0], starred=False)]
h2 = api._portal_page_html(groups2, 2000000000, "TOK")
assert "id=\"starchip\"" in h2 and "⭐ ที่สนใจ" in h2, "ต้องมีชิป filter ดาว"
assert "data-starred=\"1\"" in h2 and "data-starred=\"0\"" in h2, h2
assert "/portal/star_toggle?t=TOK&pid=PD&back=board" in h2, "ต้องมีลิงก์ toggle จากการ์ด"
assert "class=\"stagechip\"" in h2, "ชิป stage เดิมต้องมี class แยกจากดาว"
print("OK test_portal_page_star")
