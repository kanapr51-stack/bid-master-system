"""test_customer_keywords.py — parse personal keyword list + N+207 send-time gate decision."""
import json
import customer_keywords as ck

# union keywords + defaultKeywords, unique รักษาลำดับ
notes = json.dumps({"classes": [
    {"keywords": ["คอนกรีต", "ท่อ"], "defaultKeywords": ["ถนน"]},
    {"keywords": ["ท่อ", "ราง"]},
]})
assert ck.keywords_from_notes(notes) == ["คอนกรีต", "ท่อ", "ถนน", "ราง"]

# ว่าง / พังต้องไม่ระเบิด → []
assert ck.keywords_from_notes("") == []
assert ck.keywords_from_notes("not json") == []
assert ck.keywords_from_notes(json.dumps({"classes": []})) == []
assert ck.keywords_from_notes(json.dumps({})) == []

print("PASS test_customer_keywords")

# ── should_notify (N+207) ────────────────────────────────────────────────────
kw_notes = json.dumps({"classes": [{"keywords": ["ถนน"]}]})
empty_notes = json.dumps({"classes": []})

# followed_* (opt-in ติดตามเอง) → แจ้งเสมอ ไม่กรอง แม้ตั้ง keyword ไม่ตรง/ไม่ตั้งเลย
assert ck.should_notify("followed_winner", "ซื้อเวชภัณฑ์", kw_notes) is True
assert ck.should_notify("followed_prelim", "ซื้อเวชภัณฑ์", empty_notes) is True

# ไม่ตั้ง personal keyword → แจ้งทุกงาน (default)
assert ck.should_notify("province_qualified", "ซื้อเวชภัณฑ์", empty_notes) is True
assert ck.should_notify("province_qualified", "ก่อสร้างถนนคอนกรีต", "") is True

# ตั้ง keyword แล้ว → แจ้งเฉพาะที่ตรง
assert ck.should_notify("province_qualified", "ก่อสร้างถนนคอนกรีต", kw_notes) is True
assert ck.should_notify("province_qualified", "ซื้อเวชภัณฑ์", kw_notes) is False

# guard เดิม (ท่อ ไม่ชน ท่องเที่ยว) ต้องใช้ได้แม้เป็น personal keyword
guard_notes = json.dumps({"classes": [{"keywords": ["ท่อ"]}]})
assert ck.should_notify("province_qualified", "ส่งเสริมการท่องเที่ยว", guard_notes) is False
assert ck.should_notify("province_qualified", "วางท่อระบายน้ำ", guard_notes) is True

print("PASS test_customer_keywords should_notify")
