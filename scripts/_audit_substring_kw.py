"""_audit_substring_kw.py — หา substring false-match ของ keyword สั้นกับชื่องานจริง 617K
ผลลัพธ์: keyword ตัวไหน match แต่จริงๆ เป็นส่วนของคำอื่น (เช่น ราง⊂รางวัล, ท่อ⊂ท่อง)
เขียนผลลง data/_audit_substring_kw.txt (utf-8)
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
cfg = json.loads((ROOT / "config" / "matching_preferences.json").read_text(encoding="utf-8"))
keywords = cfg["keywords"]

con = sqlite3.connect(ROOT / "data" / "winner_history.db")
names = [r[0] for r in con.execute("SELECT project_name FROM winner_history") if r[0]]

THAI = "ก-๙"
out = []
out.append(f"ชื่องานทั้งหมด: {len(names):,}\n")

# สำหรับแต่ละ keyword: จับ keyword + อักษรไทยที่ตามมา (ดูคำเต็มที่ keyword ไปโผล่)
for k in keywords:
    if not re.search(f"[{THAI}]", k):  # ข้าม Dowel/Wire Mesh (อังกฤษ)
        continue
    # หา "คำเต็ม" = ขอบซ้าย(อักษรไทยก่อนหน้า)..keyword..ขอบขวา(อักษรไทยตามหลัง)
    pat = re.compile(f"[{THAI}]*{re.escape(k)}[{THAI}]*")
    words = Counter()
    n_hit = 0
    for name in names:
        found = pat.findall(name)
        if found:
            n_hit += 1
            for w in found:
                words[w] += 1
    # คำเต็มที่ != keyword (= อาจเป็นคำชน) เรียงตามความถี่
    collisions = [(w, c) for w, c in words.most_common() if w != k]
    out.append(f"\n{'='*60}\nKEYWORD: {k!r}  (match {n_hit:,} งาน)")
    # โชว์ top 15 คำเต็มที่ keyword ไปฝังอยู่
    for w, c in words.most_common(15):
        flag = "  <-- ตรงตัว" if w == k else ""
        out.append(f"   {c:>7,}  {w}{flag}")

(ROOT / "data" / "_audit_substring_kw.txt").write_text("\n".join(out), encoding="utf-8")
print("written data/_audit_substring_kw.txt")
