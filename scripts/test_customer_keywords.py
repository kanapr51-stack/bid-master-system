"""test_customer_keywords.py — parse personal keyword list จาก customers.notes.classes[]."""
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
