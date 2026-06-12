# Z Formula Research — Credibility Blend (ตำบล↔อำเภอ)

**วันที่:** 2026-06-13
**คำถาม:** เวลาคาดราคา ควรให้น้ำหนักข้อมูล "ตำบล" vs "อำเภอ" เท่าไหร่ — สูตรไหนดีสุด
**วิธี:** ทฤษฎี (Bühlmann credibility / Fay-Herriot small-area) + backtest จากข้อมูลจริง 2,994 งาน
**สคริปต์:** `scripts/_research_z_formula.py` (reproducible)

---

## 1. สูตรที่ได้ (final)

```
Z = n / (n + 3)
เรตสนาม = Z · median(ตำบล) + (1 − Z) · median(อำเภอ)
```
- **n** = จำนวนงาน precedent ในตำบล (นับดิบ)
- **k = 3** — จุดสมดุล (n=3 → เชื่อตำบลครึ่งหนึ่ง)

## 2. ทฤษฎี — k ไม่ใช่ค่าเดา

Bühlmann credibility: `Z = n/(n+k)` โดย **k = EPV/VHM**
- EPV = expected process variance = ความแปรปรวน *ภายใน* ตำบล
- VHM = variance of hypothetical means = ความแปรปรวน *ระหว่าง* ตำบล
- ตีความ: ตำบลต่างกันมาก (VHM สูง) → k ต่ำ → เชื่อ local ไว · ตำบลเหมือนกันหมด (VHM ต่ำ) → k สูง → ใช้ค่ารวม

ประมาณจากข้อมูลจริง:
| dataset | EPV | VHM | **K** |
|---|---|---|---|
| ถนนแข่งขัน (disc 0–60%) | 230.7 | 71.3 | **3.2** |
| ถนนแข่งจริง (disc 15–60%) | 73.0 | 22.0 | **3.3** |

## 3. Backtest (leave-one-out, 2,961 งาน) — ยืนยัน k

ทำนายแต่ละงานด้วย Z-blend(ตำบล,อำเภอ) แล้ววัด error เทียบจริง:

| วิธี | RMSE (0–60%) | RMSE (15–60%) |
|---|---|---|
| pure ตำบล (Z=1) | 15.56 | 8.92 |
| **Z-blend k=3** | **15.49 ★** | 8.75 |
| Z-blend k=5 | 15.50 | **8.74 ★** |
| pure อำเภอ (Z=0) | 19.03 ❌ | 10.38 ❌ |

- **k empirical ดีสุด = 3–5 · K ทฤษฎี = 3.2 → ตรงกัน** (ทฤษฎี+ข้อมูล converge)
- blend ชนะทั้ง 2 ขั้ว — โดยเฉพาะชนะ pure-อำเภอขาด → **ตำบลมีค่า ห้ามทิ้ง** แต่ก็ห้ามเชื่อ 100%
- curve แบนช่วง k=2–4 → robust (ค่าไหนก็ได้ในช่วงนี้)

## 4. ค้นพบสำคัญ: ใช้ n ดิบ ไม่ใช่ effective-companies

ทดสอบสูตรที่เอา "ความผูกขาด" มาลด Z (eff = inverse-Simpson ของบริษัท):

| | RMSE ดีสุด |
|---|---|
| Z = n/(n+k) (นับดิบ) | 15.49 |
| Z = eff/(eff+k) (ปรับผูกขาด) | 15.49 (เท่ากัน) แต่ k เลื่อนไป 1.5–2 |

→ **eff ไม่ช่วยให้แม่นขึ้น** ⇒ ใช้ n ดิบ (ง่ายกว่า)

**นัยเชิงดีไซน์:** การผูกขาด **ไม่ควรอยู่ใน Z** — ข้อมูลพิสูจน์ว่าลด Z เพราะผูกขาด = ไม่ช่วยทำนาย
→ ความผูกขาดต้องไปอยู่ที่ตัวแปร **C** (เจ้าใหญ่จะมายื่นไหม) แทน *(ตรงกับที่กัญจน์ argue ไว้)*

## 5. ข้อจำกัด (ต้องซื่อสัตย์)
1. backtest ใช้ **mean** (ตามทฤษฎี squared-error) — production ใช้ median อาจขยับ k เล็กน้อย
2. **subdistrict จาก geocode มี noise** (~85% เพี้ยน per `reference_cgd_winners_location_columns`) — backtest จับตำบลจาก column ไม่ใช่ชื่องาน → faithful น้อยกว่า predictor จริง (ซึ่ง match ด้วยชื่อ)
3. ยังไม่รวม **recency (L3)** + **แยกเจ้าใหญ่ (C)** — เป็นเลเยอร์แยก (วิจัยต่อ)
4. winner_history = นครพนม+บึงกาฬ เท่านั้น → k=3 calibrate กับภูมิภาคนี้ (ภาคอื่นอาจต่าง)

## Sources
- [Credibility theory — Wikipedia](https://en.wikipedia.org/wiki/Credibility_theory)
- [Experience Rating Using Credibility Theory — Loss Data Analytics](https://openacttexts.github.io/Loss-Data-Analytics/ChapCredibility.html)
- [Small Area Shrinkage Estimation (Fay-Herriot) — Project Euclid](https://projecteuclid.org/journals/statistical-science/volume-27/issue-1/Small-Area-Shrinkage-Estimation/10.1214/11-STS374.pdf)
