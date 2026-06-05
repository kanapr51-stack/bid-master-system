"""test_job_matcher.py — proc-type gate (ตัดงาน 'ซื้อ', เก็บ 'จ้างก่อสร้าง') + regression.
รัน: python scripts/test_job_matcher.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from job_matcher import match_job, is_procurement  # noqa: E402

CFG = {
    "target_tambons": {"นครพนม": ["บ้านแพง"], "บึงกาฬ": ["บึงโขงหลง"]},
    "keywords": ["ถนน", "คอนกรีต", "ห้อง", "อาคาร"],
    "negative_keywords": [],
    "soft_include": {"enabled": True, "label_default": "⚠️ พื้นที่ไม่ชัด"},
}

fails = []


def chk(cond, msg):
    if not cond:
        fails.append(msg)


# ── is_procurement (หน่วยย่อย) ──
chk(is_procurement("ประกวดราคาซื้อเครื่องรักษาโรคตาด้วยแสงเลเซอร์"), "ปกวด.ซื้อ ควร=True")
chk(is_procurement("ประกวดราคาซื้อคอนกรีตผสมเสร็จ"), "ซื้อคอนกรีต ควร=True")
chk(is_procurement("จัดซื้อวัสดุก่อสร้าง"), "จัดซื้อ ควร=True")
chk(is_procurement("สอบราคาซื้อครุภัณฑ์"), "สอบราคาซื้อ ควร=True")
chk(is_procurement("ซื้อรถบรรทุกขยะ"), "ซื้อ(เปล่า) ควร=True")
chk(not is_procurement("ประกวดราคาจ้างก่อสร้างถนนคอนกรีต"), "ปกวด.จ้างก่อสร้าง ควร=False")
chk(not is_procurement("จ้างเหมาปรับปรุงอาคาร"), "จ้างเหมา ควร=False")
chk(not is_procurement("สอบราคาจ้างก่อสร้างห้องน้ำ"), "สอบราคาจ้าง ควร=False")
# งานจ้างก่อสร้างที่บังเอิญมีคำ 'ซื้อ' กลางชื่อ ต้องไม่โดนตัด (leading-token)
chk(not is_procurement("ประกวดราคาจ้างก่อสร้างถนนพร้อมจัดซื้อวัสดุ"),
    "จ้างก่อสร้าง+จัดซื้อกลางชื่อ ควร=False")

# ── match_job: proc gate ตัดงานซื้อ แม้ keyword+tambon ครบ ──
d, info = match_job("ประกวดราคาซื้อคอนกรีตผสมเสร็จ ตำบลบ้านแพง", "นครพนม", cfg=CFG)
chk(d == "cut" and info.get("reason") == "procurement_not_construction",
    f"ซื้อคอนกรีต+บ้านแพง ควร cut/procurement, ได้ {d}/{info.get('reason')}")

d, info = match_job("ประกวดราคาซื้อเครื่องรักษาโรคตา ห้องผ่าตัด ตำบลบ้านแพง", "นครพนม", cfg=CFG)
chk(d == "cut" and info.get("reason") == "procurement_not_construction",
    f"ซื้อเครื่องแพทย์(false-pos เดิม) ควร cut, ได้ {d}/{info.get('reason')}")

# ── match_job: งานจ้างก่อสร้าง ยังผ่านปกติ (regression) ──
d, info = match_job("ประกวดราคาจ้างก่อสร้างถนนคอนกรีต ตำบลบ้านแพง", "นครพนม", cfg=CFG)
chk(d == "send" and info.get("reason") == "tambon_match",
    f"จ้างก่อสร้างถนน+บ้านแพง ควร send, ได้ {d}/{info.get('reason')}")

d, info = match_job("จ้างก่อสร้างถนน ต.บ้านแพง", "นครพนม", cfg=CFG)
chk(d == "send", f"จ้างก่อสร้างถนน(เปล่า) ควร send, ได้ {d}")

# จ้างก่อสร้าง location ไม่ชัด → soft_include ยังทำงาน
d, info = match_job("ประกวดราคาจ้างก่อสร้างถนนลาดยางสายหลัก", "นครพนม", cfg=CFG)
chk(d == "soft_include", f"จ้างก่อสร้าง ไม่ระบุตำบล ควร soft_include, ได้ {d}")

# ซื้อ ในจังหวัดไม่ target → cut (province ก่อน หรือ proc ก็ได้ ขอแค่ cut)
d, info = match_job("ประกวดราคาซื้อครุภัณฑ์", "ขอนแก่น", cfg=CFG)
chk(d == "cut", f"ซื้อ จังหวัดไม่ target ควร cut, ได้ {d}")

if fails:
    print(f"❌ FAIL {len(fails)} assertions:")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("✅ PASS proc-type gate (ตัดซื้อ/เก็บจ้างก่อสร้าง) + regression")
