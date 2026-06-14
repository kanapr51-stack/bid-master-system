# Dominant-Detection Predictor (2B) — Design

**วันที่:** 2026-06-14
**สถานะ:** design (รอ implement — รอ 2A trickle สะสมข้อมูลครบก่อน validate threshold)
**Sub-project ของ:** เฟส 2 (all-bidders ใน predictor). 2A = evidence layer (backfill) ✅ · **2B = ตัวนี้**

---

## 1. Goal

ตรวจจับ "เจ้าใหญ่ชนะขาดลอย" ในแต่ละ scope จาก full-field bids (2A) แล้วเสนอ **2 ฉากทัศน์** ในการ์ด D0:
ถ้าเจ้าใหญ่มาลง → ต้องลดลึกแค่ไหนถึงชนะ (กำไรบาง) · ถ้าเจ้าใหญ่ไม่มา → กลุ่มที่เหลืออยู่ระดับไหน (ลดตื้น กำไรงาม)

## 2. Motivation / Evidence (จาก backfill จริง 224 auctions)

| สิ่งที่วัด | ค่า | ผลต่อ design |
|---|---|---|
| ผู้ยื่น/งาน | เฉลี่ย 5.9 | สนามแข่งจริง |
| gap ผู้ชนะ-ที่2 | median 4.1% · p90 16% | **ส่วนใหญ่สูสี** |
| ขาดลอย gap>10% | **24%** (54/224) | feature มีค่าใน ~1/4 ของงาน |
| ขาดลอย gap>20% | 8% (18/224) | landslide ชัด |
| กลุ่มเกาะกัน CV% | **3.9%** | "ราคากลุ่ม" แม่น → ฉากทัศน์ "เจ้าใหญ่ไม่มา" เชื่อถือได้ |

ข้อสรุป: pattern มีจริงแต่เป็น minority (24%) → 2B ต้อง **graceful: แสดงเฉพาะ scope ที่มีโครงสร้างขาดลอย** ไม่ใช่ทุกงาน (76% สูสี ใช้ a/b/c เดิมดีอยู่แล้ว)

## 3. Scope

- **Detection scope = จังหวัด + หมวดงาน (tokens)** — ตรงกับ scope ที่ predictor resolve อยู่. refine เป็น อำเภอ/ตำบล เมื่อ scope ย่อยมี auctions ≥ `MIN_AUCTIONS` (degrade เหมือน `cgd_intel._fetch`)
- **In scope:** named-dominant (Tier 1) · structural-landslide (Tier 2) · 2-scenario baht output · gating
- **Out of scope (§11):** เปลี่ยน headline a/b/c เดิม · self-calibrate win-rate (งาน B) · backfill (2A)

## 4. Architecture — โมดูลใหม่ `scripts/bid_field.py`

แยกความรับผิดชอบ: รับ full-field auctions ของ scope → คืน struct สรุปโครงสร้างสนาม. predictor เรียกตอนสร้างการ์ด. ไม่ยัดใน `competitor_trend.py` (โฟกัส recency) หรือ `cgd_intel.py` (ใหญ่อยู่แล้ว).

```
bid_results + cgd_winners(budget)
   │  _field_auctions(conn, scope): คืน [auction] โดย auction = [(bidder, disc_pct, is_winner)]
   ▼
analyze_field(auctions) → FieldResult{
     tier: 0|1|2,
     dominant: {name, show_rate, win_disc_med} | None,   # Tier 1
     landslide_gap_med,                                   # Tier 2
     pack_disc_med,                                       # ระดับกลุ่ม (ตัดผู้ชนะ)
     n_auctions }
   ▼
field_lines(field_result, budget_now) → list[str]   # บรรทัดการ์ด (หรือ [] ถ้า Tier 0/ข้อมูลน้อย)
```

## 5. Data read — `_field_auctions(conn, province, tokens, ...)`

- ดึง bid_results ของ scope (province + proc_type∈COMPETITIVE_SET + project_name LIKE tokens — เลียน `competitor_trend._area_where`), JOIN `cgd_winners` เอา **budget** (resolve ข้อ 2A defer ไว้)
- ต่อ bid: `disc_pct = (budget - bid)/budget*100` โดย `bid = price_proposal or price_agree` (sealed bid)
- **ตัด outlier:** เก็บเฉพาะ `0 ≤ disc_pct ≤ 60` (กัน unit-price เพี้ยน เช่น เคส gap 88% ที่ชนะ 121K vs กลุ่ม 1M)
- group เป็น auction ต่อ project_id; winner = is_winner=1 (fallback = disc สูงสุด)
- คืน `[[(bidder_name, disc_pct, is_winner)]]`

## 6. Algorithm — `analyze_field(auctions)` (tiered)

**Gate ข้อมูล:** ถ้า `len(auctions) < MIN_AUCTIONS` → Tier 0 (return เปล่า)

**Tier 1 — named dominant:** หาบริษัท X ที่:
- ปรากฏ ≥ `MIN_APPEAR` auctions ใน scope, **และ**
- ชนะ ≥ `WIN_FRACTION` ของ auctions ที่ X ลง, **และ**
- median winning-gap ของ X (= disc ผู้ชนะ − disc ที่2 ในงานที่ X ชนะ) > `LANDSLIDE_GAP`

ถ้าเจอ → `dominant = {name: X, show_rate: #ลง/#ทั้งscope, win_disc_med: median disc ที่ X ชนะ}`

**Tier 2 — structural** (ไม่มี X ผ่านเกณฑ์ แต่ landslide rate ของ scope สูง): ถ้า สัดส่วน auctions ที่ gap>`LANDSLIDE_GAP` ≥ `LANDSLIDE_RATE` → Tier 2 (`landslide_gap_med` = median gap ของ landslide auctions)

**Tier 0** — นอกนั้น (สนามสูสี) → ไม่แสดง

**pack_disc_med** (ทุก tier ที่ไม่ใช่ 0): median ของ disc_pct ของผู้ยื่นที่ **ไม่ใช่ผู้ชนะ** ทั่ว scope (กลุ่มเกาะแน่น CV 4% → robust)

ใช้ **median ทุกตัว** (ทน outlier).

**Thresholds (const ใน bid_field.py, ปรับได้):**
```
MIN_AUCTIONS = 5      # scope ต้องมี ≥ นี้ ถึงวิเคราะห์
MIN_APPEAR   = 3      # X ปรากฏ ≥ นี้ ถึง "ระบุชื่อ"
WIN_FRACTION = 0.5    # X ชนะ ≥ ครึ่งที่ลง
LANDSLIDE_GAP  = 10.0 # percentage points (จาก evidence: p75 gap ~10%)
LANDSLIDE_RATE = 0.30 # Tier 2: ≥30% ของ auctions เป็น landslide
```
(ค่าเริ่มจาก evidence 224 auctions — ปรับหลัง trickle ครบ)

## 7. Output — `field_lines(field_result, budget_now)` (baht ตาม budget งานปัจจุบัน)

แปลง disc% → baht: `price = budget_now * (1 - disc/100)`

**Tier 1:**
```
🏆 สนามนี้มีเจ้าใหญ่: หจก.X (ลง ~80% ของงาน · ชนะขาดลอยเฉลี่ย 22%)
   • ถ้า X มา → ต้องยื่นต่ำกว่า ~1,660,000 (ระดับ X) ถึงแซง (กำไรบาง)
   • ถ้า X ไม่มา → กลุ่มที่เหลืออยู่ ~2,500,000 → ยื่นต่ำกว่ากลุ่มนิดเดียวก็ชนะ (กำไรงาม)
   ⚠️ X มาบ่อย — ยื่นตื้นมีความเสี่ยง
```
**Tier 2:**
```
🏆 สนามนี้ผู้ชนะมักขาดลอย ~18% (ไม่มีเจ้าเด่นชัด)
   • กลุ่มหลักอยู่ ~2,500,000 → ถ้าคู่แข่งดุไม่มา ลดแค่พอแซงกลุ่มก็ชนะ
```
**Tier 0 / ข้อมูลน้อย:** คืน `[]` (การ์ดไม่เปลี่ยน)

## 8. Integration

- เพิ่มการเรียก `field_lines(...)` ตอนสร้างการ์ด D0 (จุดที่ปัจจุบันต่อ `predict_lines`) — append บล็อกเจ้าใหญ่ **ต่อจาก** a/b/c headline
- ไม่แก้ `predict_lines` เดิม (headline a/b/c คงเดิม)

## 9. Gating (graceful)

แสดงบล็อกเจ้าใหญ่เมื่อ: scope มี full-field ≥ `MIN_AUCTIONS` **และ** analyze_field คืน Tier 1/2. ไม่งั้น = พฤติกรรมเดิม 100% → auto-activate เมื่อ 2A สะสมข้อมูลพอ

## 10. Testing (TDD)

`scripts/test_bid_field.py` (assert-style, BMS_ENV=dev):
1. `analyze_field` Tier 1 — สนาม synthetic ที่ X ลง 4/5 ชนะขาดลอย → dominant=X, show_rate=0.8
2. Tier 2 — landslide เยอะแต่ไม่มี X เด่น → tier=2, landslide_gap_med ถูก
3. Tier 0 — สนามสูสี (gap เล็ก) → tier=0, field_lines=[]
4. gate ข้อมูลน้อย (<MIN_AUCTIONS) → Tier 0
5. outlier filter — bid disc 88% ถูกตัด ไม่เพี้ยน pack/winner
6. `field_lines` baht — แปลง disc%→baht ตาม budget_now ถูก
7. `_field_auctions` — JOIN budget จาก cgd_winners + group ต่อ project ถูก (mini DB)

## 11. Out of scope (→ ภายหลัง)

- เปลี่ยน/calibrate headline a/b/c (งาน B: self-calibrate win-rate)
- ใช้ show-rate คำนวณ expected-value ราคาเดียว (2B แค่เสนอ 2 ฉากทัศน์ ให้กัญจน์ตัดสิน)
- predict ว่าเจ้าใหญ่จะมางานนี้ไหม (ยื่นซองปิด — ทำไม่ได้ ใช้ show-rate ประวัติแทน)

## 12. Risks & open items

- **R1: ข้อมูล named-dominant อาจบาง** (224 auctions กระจายหลายหมวด/พื้นที่ → recurrence ต่อ scope อาจน้อย). Mitigation: tiered (fallback Tier 2 structural) + gate MIN_AUCTIONS. **validate หลัง trickle ครบ** ก่อน implement (รัน `_analyze_bidfield`-style ต่อ scope ดู recurrence)
- **R2: budget จาก cgd_winners อาจ NULL บางงาน** → bid นั้นคำนวณ disc ไม่ได้ → ข้าม (graceful) ; ถ้าเยอะกระทบ → fallback gap-based (ไม่ใช้ %)
- **R3: bidder_name มี TIN-fallback `name:%`** (จาก 1b/2A) — bid_field อ่าน bidder_name (ไม่ใช่ tin) อยู่แล้ว → ไม่กระทบ; แต่บริษัทเดียวกันคนละสะกดอาจนับแยก → ใช้ exact name ก่อน (ปรับ fuzzy ทีหลังถ้าจำเป็น)
- **R4: threshold ตั้งจาก 224 auctions** — ปรับหลัง trickle ครบ ~3046
