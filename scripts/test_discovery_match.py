"""test_discovery_match.py — pure per-user matching for board discovery."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discovery_match as dm


def t(name, prov, budget, provs, kws, bmin=0, bmax=0, neg=None):
    return dm.match(name, prov, budget, provs, kws, bmin, bmax, neg if neg is not None else [])


# keyword OR + province AND → match + คืนคำที่โดน
ok, hits = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 1000000, ["นครพนม"], ["คอนกรีต", "ท่อ"])
assert ok and hits == ["คอนกรีต"], (ok, hits)

# province ไม่อยู่ใน subscribe → ตัด
ok, _ = t("ก่อสร้างถนนคอนกรีต", "ชลบุรี", 1000000, ["นครพนม"], ["คอนกรีต"])
assert not ok, "province ไม่ตรงต้องตัด"

# ไม่มี keyword โดน → ตัด
ok, _ = t("ซื้อเวชภัณฑ์", "นครพนม", 1000000, ["นครพนม"], ["คอนกรีต"])
assert not ok, "ไม่มี keyword ต้องตัด"

# guard: "ท่อ" ห้ามชน "ท่องเที่ยว"
ok, _ = t("ส่งเสริมการท่องเที่ยว", "นครพนม", 1000000, ["นครพนม"], ["ท่อ"])
assert not ok, "ท่อ ต้องไม่ชน ท่องเที่ยว"
# แต่ "ท่อระบายน้ำ" ต้องโดน
ok, hits = t("วางท่อระบายน้ำ", "นครพนม", 1000000, ["นครพนม"], ["ท่อ"])
assert ok and hits == ["ท่อ"], (ok, hits)

# budget range: ต่ำกว่า min → ตัด, สูงกว่า max → ตัด
ok, _ = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 500000, ["นครพนม"], ["คอนกรีต"], 1000000, 0)
assert not ok, "ต่ำกว่า budget_min ต้องตัด"
ok, _ = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 99000000, ["นครพนม"], ["คอนกรีต"], 0, 20000000)
assert not ok, "สูงกว่า budget_max ต้องตัด"

# budget=0 (ไม่รู้ราคากลาง) → ไม่ตัด แม้ตั้งช่วงงบ
ok, _ = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 0, ["นครพนม"], ["คอนกรีต"], 1000000, 20000000)
assert ok, "budget=0 ต้องผ่าน"

# negative safety net → ตัด
ok, _ = t("ก่อสร้างถนนคอนกรีต ครุภัณฑ์", "นครพนม", 1000000, ["นครพนม"], ["คอนกรีต"], neg=["ครุภัณฑ์"])
assert not ok, "negative ต้องตัด"

# N+206 (พลิกกลับ N+198): ไม่มี keyword เลย = ไม่มีงานแมตช์เลย แม้จังหวัด/งบตรงก็ตาม
ok, hits = t("ซื้อเวชภัณฑ์", "นครพนม", 1000000, ["นครพนม"], [])
assert not ok and hits == [], (ok, hits)
ok, _ = t("ก่อสร้างถนนคอนกรีต", "นครพนม", 1000000, ["นครพนม"], [])
assert not ok, "ไม่ตั้ง keyword ต้องไม่แมตช์แม้ชื่องานจะมีคำก่อสร้างจริงก็ตาม"

print("PASS test_discovery_match")
