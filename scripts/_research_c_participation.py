"""_research_c_participation.py — วิจัยตัวแปร C (เจ้าใหญ่จะกลับมาแข่งไหม)
ข้อจำกัด: winner_history มีแค่ "ผู้ชนะ" → วัดได้แค่ "ความถี่/recency การชนะ" (proxy ของ participation)
คำถาม: ถ้าบริษัทชนะในอำเภอปีหนึ่ง โอกาสกลับมาชนะอีกภายใน g ปี = เท่าไหร่ (recency decay ของ C)
"""
import sqlite3
from collections import defaultdict

c = sqlite3.connect('data/winner_history.db'); c.row_factory = sqlite3.Row
rows = c.execute("""SELECT winner, province, district, fiscal_year FROM winner_history
    WHERE work_type='ถนน' AND method_group='แข่งขันราคา' AND price_valid=1
    AND winner IS NOT NULL AND winner!='' AND fiscal_year GLOB '25[0-9][0-9]'""").fetchall()

# (บริษัท, อำเภอ) -> เซ็ตปีที่ชนะ
wins = defaultdict(set)
for r in rows:
    wins[(r['winner'], r['province'], r['district'])].add(int(r['fiscal_year']))

# recurrence: ถ้าชนะปี Y, ภายใน g ปี (Y+1..Y+g) ชนะอีกไหม — เฉพาะคู่ที่มี window ครบ (Y+g <= ปีสุดท้ายของ data)
MAXYR = max(int(r['fiscal_year']) for r in rows)
print(f"ข้อมูลถึงปีงบ {MAXYR} · {len(rows)} win · {len(wins)} คู่(บริษัท,อำเภอ)")
print("\nP(กลับมาชนะในอำเภอเดิม ภายใน g ปี | ชนะปีนี้):")
for g in (1, 2, 3, 4, 5):
    num = den = 0
    for yset in wins.values():
        for Y in yset:
            if Y + g > MAXYR:    # window ไม่ครบ ตัดออก (กัน censoring bias)
                continue
            den += 1
            if any((Y + d) in yset for d in range(1, g + 1)):
                num += 1
    if den:
        print(f"  ภายใน {g} ปี: {num/den*100:.0f}%  (n={den})")

# frequency effect: เจ้าที่ชนะบ่อย (≥4 ปีในอำเภอ) vs นานๆ ครั้ง
print("\nผลของความถี่ (เจ้าประจำ vs ขาจร) — P(recur ภายใน 2 ปี):")
for label, lo, hi in [("ขาจร (1-2 ปีที่เคยชนะ)", 1, 2), ("ประจำ (3-4)", 3, 4), ("เจ้าถิ่น (≥5)", 5, 99)]:
    num = den = 0
    for yset in wins.values():
        if not (lo <= len(yset) <= hi):
            continue
        for Y in yset:
            if Y + 2 > MAXYR: continue
            den += 1
            if any((Y + d) in yset for d in (1, 2)): num += 1
    if den:
        print(f"  {label}: {num/den*100:.0f}%  (n={den})")

# เคสมงคลธรรม: หนองเดิ่น(ตำบล) vs บุ่งคล้า(อำเภอ) ปีที่ชนะ
print("\nเคสจริง — ปีที่มงคลธรรมชนะถนน:")
for scope, dist in [("อำเภอบุ่งคล้า", "บุ่งคล้า")]:
    ys = sorted(wins.get(('ห้างหุ้นส่วนจำกัด มงคลธรรม', 'บึงกาฬ', dist), set()))
    print(f"  {scope}: {ys}  (ล่าสุด {max(ys) if ys else '-'}, ห่างปัจจุบัน {MAXYR-max(ys) if ys else '-'} ปี)")
