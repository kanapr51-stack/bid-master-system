"""test_star_buttons.py — LINE postback ⭐ติดตาม / ❌ไม่เกี่ยว (แทน 👍🤔👎)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_LINE_Sender import build_postback_data, build_job_flex  # noqa: E402

# postback data format
assert build_postback_data("star", "P9") == "star:P9", build_postback_data("star", "P9")
assert build_postback_data("irrelevant", "P9") == "fb:irrelevant:P9", build_postback_data("irrelevant", "P9")

# การ์ดมี 2 ปุ่ม: ⭐ ติดตาม + ❌ ไม่เกี่ยว (เอา 🤔 ออก)
flex = build_job_flex("P9", "งานถนน คสล.", "รายละเอียด", with_feedback=True)
labels = [b["action"]["label"] for b in flex["footer"]["contents"]]
assert any("ติดตาม" in l for l in labels), labels
assert any("ไม่เกี่ยว" in l for l in labels), labels
assert not any("น่าสน" in l for l in labels), "ต้องเอา 🤔 ออกแล้ว: " + str(labels)
# ⭐ ใช้ postback data star:
star_btn = [b for b in flex["footer"]["contents"] if "ติดตาม" in b["action"]["label"]][0]
assert star_btn["action"]["data"] == "star:P9", star_btn["action"]["data"]

print("✅ PASS star/irrelevant buttons")
