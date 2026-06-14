# Conditional Win-Rate (งาน B) — Self-Calibrate ตามจำนวนผู้ยื่น — Design

**วันที่:** 2026-06-15
**สถานะ:** design — approved (กัญจน์ 2026-06-15) → next: writing-plans
**Sub-project ของ:** เฟส 2 (all-bidders ใน predictor). 2A = backfill ✅ · 2B = เจ้าตลาด intel ✅ (LIVE) · **B = ตัวนี้**

---

## 1. Goal

แทนป้าย win% ตายตัว **75/50/25** บนการ์ด D0 ด้วย **win% ที่ self-calibrate จาก full-field (2A)** — โดยเงื่อนไข
**จำนวนผู้ยื่น** ของ scope. แสดงเป็น **ตาราง 3 ระดับ** (น้อย/เฉลี่ย/เยอะ ราย) ให้กัญจน์เห็นว่าโอกาสชนะของแต่ละราคา
แปรตามความหนาแน่นของสนามอย่างไร.

## 2. Motivation — ทำไม heuristic เดิมไม่พอ และทำไม "full-field unconditional" ไม่ช่วย

- heuristic ปัจจุบัน (cgd_intel.py:799-810): a/b/c = ราคาจาก p75/median/p25 ของ discount **ผู้ชนะ** → ติดป้าย win% = percentile rank เอง (75/50/25 ตายตัว).
- ในประมูลซองปิดราคาต่ำสุด: ชนะ ⇔ ลดดุกว่าผู้ชนะจริง (ผู้ชนะ = คนลดสุดในสนาม).
  ⇒ `P(บิด X ชนะ) = P(ผู้ชนะ < X) = winner-CDF` — **เท่ากับ percentile เดิมเป๊ะ**. ดังนั้น "full-field win-rate แบบ unconditional" = ของซ้ำ (ไม่คุ้ม).
- **full-field เพิ่มค่าเฉพาะตอนมีเงื่อนไข:** จำนวนผู้ยื่น `n` ดึงได้จาก full-field เท่านั้น (winner-only ดึงไม่ได้). สนามแน่น → ต้องลดลึกกว่าเพื่อ win% เท่าเดิม. นี่คือสิ่งที่ B เพิ่ม.

## 3. Scope

- **In scope:** ประเมิน F_bid + n stats จาก full-field · ตาราง win% 3 คอลัมน์ · gating graceful · เชื่อม predict() · TDD
- **Out of scope:** เปลี่ยน logic **ราคา** a/b/c (แถวยังเป็น winner p75/med/p25 เดิม) · closed-loop calibration จากผลจริง (option C, ภายหลัง) · recency-weight ของ F_bid (R2, v1 ไม่ทำ) · เปลี่ยนบล็อกเจ้าตลาด 2B

## 4. กลไก (algorithm)

ต่อ scope (ชุด auctions จาก `_field_auctions`):

1. **F_bid** = empirical CDF ของ discount **ผู้ยื่นรายเดียว** — รวมทุก bid ทุก auction ใน scope (ไม่ใช่แค่ผู้ชนะ).
   `F_bid(x) = (#bids ≤ x) / (#bids ทั้งหมด)`.
2. **n stats** = mean & sample-SD ของจำนวนผู้ยื่นต่อ auction (`len(auction)`).
3. **คอลัมน์** = `[round(mean−SD), round(mean), round(mean+SD)]` → clamp ขั้นต่ำ ≥ 2 · dedupe ถ้าเท่ากัน (SD เล็ก → เหลือ < 3 คอลัมน์, graceful).
4. **win% ของราคา P เมื่อคู่แข่ง k ราย** = `F_bid(disc_P) ^ k`
   - `disc_P = (budget − P)/budget × 100`
   - ความหมาย: ทุกคู่แข่ง k รายลดน้อยกว่าเรา (iid).
5. **แถว** = ราคา a/b/c เดิม (`area_price_lo/med/hi`).

**Property (sanity):** ที่ราคา = winner-median, คอลัมน์กลาง (k=mean) จะได้ ≈ 50% เสมอ —
เพราะ winner-median = median ของ max-of-mean draws ⇒ `F_bid(winner_median)^mean ≈ 0.5`. ⇒ B ไม่ขัดกับเลขเดิม
ที่ n เฉลี่ย แค่กาง ±SD ให้เห็นผลความหนาแน่น.

## 5. Data read — reuse `bid_field._field_auctions`

- ใช้ `_field_auctions(conn, province, tokens, subdistrict, district)` ที่มีอยู่ (2B) → คืน `[[(name, disc, is_winner)]]`
  พร้อมตัด outlier disc นอก `[0, DISC_MAX(60)]` แล้ว.
- **อ่านครั้งเดียว ป้อน 2 ผู้ใช้:** ใน predict() เรียก `_field_auctions` รอบเดียวต่อ scope → ส่งให้ทั้ง
  `analyze_field` (2B เจ้าตลาด) **และ** `winrate_grid` (B) → กัน query ซ้ำ (scope เดียวอ่าน 2 รอบ).

## 6. Architecture — เพิ่มใน `scripts/bid_field.py`

```
winrate_grid(auctions, prices, budget) -> dict | None
    # prices = [area_price_lo, area_price_med, area_price_hi] (None ตัดทิ้ง)
    # คืน {"ns": [k_lo, k_mid, k_hi], "rows": [(price, [w_lo, w_mid, w_hi])], "n_mean": float, "n_sd": float}
    # None ถ้า gate ไม่ผ่าน (auctions < MIN_AUCTIONS / SD คำนวณไม่ได้ / ไม่มี bid)

winrate_lines(grid, basis="") -> list[str]
    # render ตาราง (pure). [] ถ้า grid None.
```

**Integration (cgd_intel.py ~588-597):** อ่าน `_field_auctions` รอบเดียวสำหรับ scope ที่ resolve (ตำบล→อำเภอ
เหมือน 2B). สร้าง grid จาก `pred` prices → ถ้า grid ไม่ None: **แทน** บล็อก a/b/c เดิมด้วยตาราง · ถ้า None:
คงบล็อกเดิม (`predict_lines` ปกติ).

> ทางเลือก integration (เลือกตอน plan): (a) ให้ predict() ตัดสินใจ render — predict_lines คงเดิม, ต่อ winrate_lines
> แยก. (b) ส่ง grid เข้า predict_lines ให้มันเลือก render. **แนะนำ (a)** (surgical, ไม่แตะ predict_lines + test เดิมไม่ขยับ).

## 7. Output (mean=6, SD=2 → คอลัมน์ 4/6/8)

```
💵 แนะนำราคายื่น (งบ 2,000,000) — โอกาสชนะตามจำนวนผู้ยื่น
   ผู้ยื่น →     4ราย   6ราย   8ราย
   1,400,000     78%    68%    59%
   1,600,000     55%    42%    32%
   1,800,000     28%    18%    11%
   📊 สนามนี้เฉลี่ย 6 ผู้ยื่น (±2) · อิงอำเภอ
   * ยิ่งผู้ยื่นเยอะ โอกาสยิ่งต่ำ
```

- คอลัมน์ collapse ได้ (SD เล็ก) → เหลือ 1-2 คอลัมน์.
- ตาราง plain-text (LINE มือถือฟอนต์ไม่ fix → คอลัมน์อาจเยื้องนิด, กัญจน์รับได้แล้ว).

## 8. Gating (graceful — สำคัญเพราะ 2A เพิ่ง ~30%)

แสดงตารางเมื่อ: scope มี full-field auctions ≥ `MIN_AUCTIONS(5)` **และ** มี bid พอประเมิน F_bid **และ** คำนวณ SD ได้.
ไม่งั้น `winrate_grid` คืน None → **การ์ดเดิม 100%** (`predict_lines` ปกติ) → auto-activate เมื่อ trickle เติมพอ.
scope ที่ B โผล่ = scope ที่ backfill ครบ.

## 9. Testing (TDD) — `scripts/test_winrate_grid.py` (assert-style, BMS_ENV=dev)

1. `winrate_grid` ตัวเลขถูกตาม `F_bid(X)^k` — synthetic auctions ที่ F_bid รู้ค่า (เช่น disc uniform) → assert win% ตรงสูตร.
2. **Monotonic** — คู่แข่งเยอะขึ้น → win% ลด · ราคาต่ำลง → win% ขึ้น.
3. **คอลัมน์** = `[mean−SD, mean, mean+SD]` round + clamp(≥2) + dedupe ถูก.
4. **Consistency** — สนาม synthetic ที่รู้ winner-median → ราคานั้นคอลัมน์กลาง ≈ 50% (±tol).
5. **Gating** — auctions < MIN_AUCTIONS หรือ SD=0(จุดเดียว) → grid=None → การ์ด fallback เดิม.
6. **Render** — `winrate_lines` จัดตาราง + header + footer ถูก · grid=None → [].

## 10. Risks & open items

- **R1 (iid assumption):** `F_bid^k` สมมติผู้ยื่นอิสระ + กระจายเหมือนกัน. เป็น simplification ที่ **data-efficient**
  (pool ทุก bid แทน bucket ตาม n ซึ่ง sparse) เหมาะช่วง 2A ยังไม่ครบ. **Mitigation/validate:** เทียบ
  คอลัมน์กลาง vs winner-CDF จริงหลัง trickle ครบ (test #4 จับ regression เบื้องต้น).
- **R2 (recency):** v1 F_bid ไม่ถ่วงน้ำหนักความสด (ราคา rows ถ่วงอยู่แล้วผ่าน pipeline เดิม). KISS ก่อน — เติม
  recency_weight ทีหลังถ้าเห็นว่า drift.
- **R3 (ตาราง LINE):** ฟอนต์ไม่ fix → เยื้อง. รับได้ (กัญจน์ยืนยัน). ถ้าแย่ → ย้ายไป portal/LIFF render ทีหลัง.
- **R4 (n = total vs competitors):** ใช้ k = จำนวนผู้ยื่นในสนามประวัติ เป็น "จำนวนคู่แข่งที่เจอ" (เรา = รายเพิ่ม).
  conservative เล็กน้อย (นับ slot ตัวเองรวม) — ยอมรับได้ v1, label ชัดว่า "จำนวนผู้ยื่น".

## 11. Definition of Done (verifiable)

- `test_winrate_grid.py` ผ่านทุกเคส + `test_winrate.py`/`test_bid_field.py` เดิมยังผ่าน (backward-compat).
- `py_compile` ผ่าน.
- smoke จริง: เรียก predict() กับ scope ที่มี full-field ≥5 → เห็นตาราง 3 คอลัมน์ · scope บาง → เห็นการ์ดเดิม.
- `_field_auctions` ถูกอ่าน **รอบเดียว** ต่อ scope (ไม่ query ซ้ำกับ 2B).
