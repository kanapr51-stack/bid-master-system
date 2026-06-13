# Recency Weighting Research — Half-Life (L3)

**วันที่:** 2026-06-13
**คำถาม:** ควรถ่วงน้ำหนัก precedent ตามอายุไหม + half-life เท่าไหร่ดีสุด
**วิธี:** backtest no-lookahead (ใช้ precedent ปี ≤ ปีงานเป้าหมาย) บนถนนแข่งขันจริง
**สคริปต์:** `scripts/_research_recency_halflife.py`

---

## 1. สูตรที่ได้

```
น้ำหนักความสด = 0.5 ^ (อายุงาน / half_life)        half_life = 1 ปี
อายุงาน = ปีปัจจุบัน − ปีงบของ precedent
```
ใช้ถ่วง percentile (p25/p75/median) ของ scope แทนการนับเท่ากันหมด

## 2. Backtest (RMSE)

| วิธี | อำเภอ (แข่งจริง) | ตำบล (แข่งจริง) |
|---|---|---|
| no-recency (เท่ากันหมด) | 8.94 | 8.71 |
| recent-3yr cutoff (เดิม) | 8.87 | 8.78 |
| **half-life 0.5 ปี** | **8.58** | 8.68 |
| **half-life 1 ปี** | 8.64 | **8.58** |
| half-life 1.5 ปี | 8.69 | 8.58 |
| half-life 3 ปี | 8.79 | 8.61 |

- **recency weighting ดีกว่าทั้ง no-recency และ recent-3yr cutoff** (ของเดิม)
- half-life สั้น: อำเภอ 0.5 · ตำบล 1-1.5 → **จุดสมดุล 2 scope = 1 ปี** (เกือบดีสุดทั้งคู่)

## 3. 🎯 ผลสำคัญ — ฆ่าข้อมูลเก่า (แก้ root cause หนองเดิ่น)

ที่ half-life=1: ข้อมูล **2562** ทำนายงาน **2569** (อายุ 7) → น้ำหนัก = 0.5⁷ ≈ **0.008**

→ มงคลธรรม 2562 (40%) ถูกถ่วงเหลือ ~0 → ไม่ลากราคาให้ดุ (ต่างจาก `include_old` เดิมที่ใช้น้ำหนักเต็ม)
→ **นี่คือตัวที่ L1 blend แก้ไม่ได้** (L1 ลด weight ไม่พอ Z=0.4 ยังเอา 40% มา 40%)

## 4. แทนที่ของเดิม
- `include_old` (ใช้ข้อมูลเก่าน้ำหนักเต็ม) → ข้อมูลเก่าจางตามอายุ
- `RECENT_FY` 3-ปี cutoff แข็ง → decay ลื่น (ยังดึงปีเก่ามาได้ถ้าพื้นที่ข้อมูลน้อย แต่น้ำหนักน้อย)

## 5. ข้อจำกัด
- improvement เฉลี่ยปานกลาง (8.94→8.64) — แต่ **critical กับเคส stale-fallback**
- backtest ใช้ amphoe/tambon level, contested road — ภูมิภาคนครพนม+บึงกาฬ
- half-life อาจต่างตามหมวดงาน (ถนนเปลี่ยนเร็ว?) — เริ่ม 1 ปี global, จูนทีหลังได้

## Sources (recency/time-decay = standard สำหรับ non-stationary series)
- EWMA / exponential time decay — time-series forecasting standard practice
- เกี่ยว: docs/research/2026-06-13-z-formula-credibility.md (L1)
