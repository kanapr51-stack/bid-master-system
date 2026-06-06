"""test_job_matcher.py — proc-aware gate (ซื้อ+วัสดุ=lead BSC, ซื้อ+ไม่ใช่วัสดุ=cut, จ้าง=ก่อสร้าง) + regression.
รัน: python scripts/test_job_matcher.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from datetime import date  # noqa: E402
from job_matcher import match_job, is_procurement, tor_is_fresh  # noqa: E402

CFG = {
    "target_tambons": {"นครพนม": ["บ้านแพง"], "บึงกาฬ": ["บึงโขงหลง"]},
    "keywords": ["ถนน", "คอนกรีต", "ห้อง", "อาคาร"],
    "material_keywords": ["วัสดุก่อสร้าง", "คอนกรีตผสมเสร็จ", "คอนกรีต", "ท่อคอนกรีต", "ลูกรัง"],
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

# ── proc-aware gate: ซื้อ+วัสดุ = lead BSC (send), ซื้อ+ไม่ใช่วัสดุ = cut ──
d, info = match_job("ประกวดราคาซื้อคอนกรีตผสมเสร็จ ตำบลบ้านแพง", "นครพนม", cfg=CFG)
chk(d == "send" and info.get("reason") == "tambon_match",
    f"ซื้อคอนกรีตผสมเสร็จ+บ้านแพง = lead BSC ควร send, ได้ {d}/{info.get('reason')}")

d, info = match_job("จัดซื้อวัสดุก่อสร้าง ตำบลบ้านแพง โดยวิธีเฉพาะเจาะจง", "นครพนม", cfg=CFG)
chk(d == "send", f"ซื้อวัสดุก่อสร้าง+บ้านแพง = lead BSC ควร send, ได้ {d}/{info.get('reason')}")

# ซื้อ ที่ match คำก่อสร้าง (ห้อง) แต่ไม่ใช่ "วัสดุ" → ตัด (กันเครื่องแพทย์/รถ/คอม)
d, info = match_job("ประกวดราคาซื้อเครื่องรักษาโรคตา ห้องผ่าตัด ตำบลบ้านแพง", "นครพนม", cfg=CFG)
chk(d == "cut" and info.get("reason") == "no_material_keyword",
    f"ซื้อเครื่องแพทย์(match ห้อง ไม่ใช่วัสดุ) ควร cut/no_material, ได้ {d}/{info.get('reason')}")

# ซื้อวัสดุ จังหวัด target แต่ตำบลไม่ target → cut
d, info = match_job("ประกวดราคาซื้อคอนกรีตผสมเสร็จ ตำบลเรณู", "นครพนม", cfg=CFG)
chk(d == "cut" and info.get("reason") == "tambon_not_target",
    f"ซื้อวัสดุ ตำบลไม่ target ควร cut, ได้ {d}/{info.get('reason')}")

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

# ── tor_is_fresh: B0 freshness gate (กัน backlog blast + ตรงช่วงรับฟังคำวิจารณ์) ──
TODAY = date(2026, 6, 6)
chk(tor_is_fresh("2026-06-05", TODAY, days=14), "B0 เมื่อวาน ควร fresh=True")
chk(tor_is_fresh("2026-06-06", TODAY, days=14), "B0 วันนี้ ควร fresh=True")
chk(tor_is_fresh("2026-05-24", TODAY, days=14), "B0 13 วันก่อน ควร fresh=True (ขอบใน)")
chk(not tor_is_fresh("2026-05-20", TODAY, days=14), "B0 17 วันก่อน ควร fresh=False (เกิน)")
chk(not tor_is_fresh("2026-01-01", TODAY, days=14), "B0 เก่ามาก ควร fresh=False (backlog)")
chk(not tor_is_fresh("", TODAY, days=14), "announce_date ว่าง ควร fresh=False (conservative กัน blast)")
chk(not tor_is_fresh("ไม่ใช่วันที่", TODAY, days=14), "parse ไม่ได้ ควร fresh=False")

if fails:
    print(f"❌ FAIL {len(fails)} assertions:")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("✅ PASS proc-type gate (ตัดซื้อ/เก็บจ้างก่อสร้าง) + regression")
