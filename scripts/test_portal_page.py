"""test_portal_page.py — _portal_page_html render 3 กลุ่ม + winner + empty + escape."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_DB_PATH"] = str(Path(os.environ["BMS_DATA_DIR"]) / "x.db")
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import bms_api as api

groups = {
    "bidding": [{"project_id": "PD", "name": "ถนน คสล. บ้านนาสาร", "location": "ต.โพธิ์หมากแข้ง จ.บึงกาฬ",
                 "deadline": "15 มิ.ย. 2569", "pred_lo": 679000, "pred_hi": 730000,
                 "winner": None, "winner_price": None, "winner_disc": None, "competitors": []}],
    "won": [{"project_id": "PW", "name": "ถนน W", "location": "จ.บึงกาฬ", "deadline": "",
             "pred_lo": None, "pred_hi": None, "winner": "หจก.X", "winner_price": 738000.0,
             "winner_disc": 26.2, "competitors": [{"name": "หจก.Y", "price": 752000.0}]}],
    "pre": [{"project_id": "PB", "name": "<script>x</script>", "location": "จ.บึงกาฬ", "deadline": "",
             "pred_lo": None, "pred_hi": None, "winner": None, "winner_price": None,
             "winner_disc": None, "competitors": []}],
}
h = api._portal_page_html(groups, 2000000000)
assert "งานที่คุณติดตาม (3)" in h, h
assert "กำลังประมูล" in h and "ยื่นซอง 15 มิ.ย." in h and "679,000" in h, h
assert "ประกาศผล" in h and "หจก.X" in h and "738,000" in h and "ลด 26%" in h, h
assert "หจก.Y" in h, h
assert "&lt;script&gt;" in h and "<script>x" not in h, "escape ผิด"
h0 = api._portal_page_html({"won": [], "bidding": [], "pre": []}, 0)
assert "ยังไม่มีงานที่ติดตาม" in h0, h0
print("OK test_portal_page")
