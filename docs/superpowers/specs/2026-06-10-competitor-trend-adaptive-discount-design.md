# Competitor Trend — Recency-Weighted Adaptive Discount (Sub-2a) — Design

**วันที่:** 2026-06-10
**สถานะ:** approved design (รอ user review spec → writing-plans)

## Problem / Goal

คาดราคาปัจจุบัน (`cgd_intel.predict_winning_price`) ใช้ percentile ของส่วนลดจาก `cgd_winners` แบบ **flat** (ทุกงานน้ำหนักเท่ากัน, ไม่สนวันที่) → ไม่ปรับตามผลล่าสุด. กัญจน์อยากให้ระบบ **เรียนรู้จากผลจริง** — ถ้างานล่าสุดในพื้นที่ลงราคาต่างจากที่คาด คาดครั้งหน้าควรขยับตาม **แต่แบบนุ่มนวล** (recency-weighted, ไม่ไล่ตาม noise) + วิเคราะห์ **เทรนด์ส่วนลดแยกต่อบริษัท**.

**Decision (กัญจน์):** learning rule = ให้น้ำหนักงานล่าสุดมากสุด แต่ไม่ปรับเร็วเกิน + แยกเทรนด์ต่อบริษัท → **EWMA (α≈0.3) + damping**.

**ตอบโจทย์ "คาด 70 จริง 80":** ขยับ 70→73 หลังครั้งแรก (นิดเดียว) → ลู่เข้า ~80 เมื่อ 5-7 งานยืนยัน (ไม่ overfit ฟลุ๊คครั้งเดียว).

## Scope / Out of scope
- ✅ **Sub-2a (นี้):** foundation (รวม cgd_winners + bid_results เป็น series ตามเวลา + EWMA) + **prediction ปรับตัว recency-weighted (area-level)** + **เทรนด์ต่อบริษัทใน Round 2**.
- ⏳ **Sub-2b (defer):** ถ่วงน้ำหนัก "ผู้น่าจะยื่น" ใน prediction (speculative — ไม่รู้ใครจะยื่นตอน D0).
- ⏳ **Sub-2c (defer):** รายงานเทรนด์ตลาดรวม (ภาพรวม).
- ❌ ไม่ทำ materialized trend table — คำนวณ on-the-fly จาก cgd_winners + bid_results (เร็วพอ, YAGNI). ข้อมูล observe เก็บใน `bid_results` อยู่แล้ว (Winner_Poller).

## Architecture

`competitor_trend.py` (ใหม่) = layer คำนวณ series + EWMA. consumer 2 ตัว: `predict_winning_price` (area) + `analyze_bidders` (บริษัท).

```
cgd_winners (winner+discount+announce_date)  ─┐
                                              ├─► series ตามเวลา ─► EWMA(α) + trend
bid_results (bidder+price+fetched_at) +budget ─┘         │
                                                          ├─► area: recency-shift percentile → predict_winning_price
                                                          └─► company: ewma_trend → analyze_bidders (Round 2)
```

## Components

### 1. `scripts/competitor_trend.py` (ใหม่)

**series builders** (คืน list[{date, discount_pct, source}] เรียง **เก่า→ใหม่**):
- `area_win_series(conn, province, tokens, subdistrict, district, subtype=None)` — ส่วนลด**ผู้ชนะ** (= ที่ใช้คาดราคา):
  - cgd_winners: `discount_pct` + `announce_date` (competitive-set + FY + subtype filter เดิม จาก `cgd_intel._fetch`)
  - bid_results: rows `is_winner=1` → discount = `(budget - price_agree)/budget*100` (budget จาก projects_seen) + `fetched_at`
- `company_series(conn, province, tokens, company, subdistrict, district)` — ส่วนลด**ของบริษัทนั้น** (พฤติกรรมการลด):
  - cgd_winners: rows `winner=company` (= งานที่บริษัทนี้ชนะ) + discount + date
  - bid_results: rows `bidder_name=company` → discount จาก `price_proposal` (ราคาที่เขาเสนอ) + budget + fetched_at
  - scope: ตำบลก่อน (subdistrict+district) → ไม่มี→จังหวัด (เหมือน Sub-1 `company_area_history`)

**EWMA core:**
- `ewma(series, alpha=0.3)` — recency-weighted (เก่า→ใหม่, ตัวท้ายน้ำหนักมากสุด). `None` ถ้า series ว่าง.
- `ewma_trend(series, alpha=0.3, min_n=3)` → `{ewma, median, n, trend}`:
  - `trend` ∈ {↑, ↓, →, None}: เทียบ ewma vs median — `ewma > median+TREND_EPS` → ↑ (ล่าสุดลดแรงกว่าค่ากลางในอดีต), `ewma < median-TREND_EPS` → ↓, ระหว่างนั้น → →. `None` ถ้า n<min_n.
  - n<min_n → คืน median เป็น ewma + trend=None (ไม่โชว์เทรนด์ — กัน data น้อยให้สัญญาณมั่ว)

**recency-adjusted percentiles (สำหรับ prediction):**
- `recency_adjusted_pct(series, p25, p75, alpha=0.3, min_n=3, cap=CAP)` → `(p25', p75')`:
  - delta = `clamp(ewma - median, -cap, +cap)` (damping: เลื่อนได้ไม่เกิน cap จุด/รอบ กันสุดโต่ง)
  - `p25' = p25 + delta`, `p75' = p75 + delta` (เลื่อนทั้ง range คงความกว้าง = ความไม่แน่นอนเดิม)
  - n<min_n → คืน (p25, p75) เดิม (ไม่ปรับ)
- **เหตุผล:** percentile ให้ "ความกว้าง" (uncertainty), EWMA ให้ "center ที่ปรับตามล่าสุด". เลื่อน range ด้วย delta = ปรับ center โดยไม่ทิ้ง spread.

**Constants:** `ALPHA=0.3`, `MIN_N=3`, `CAP=8` (เลื่อน percentile ได้ ≤8 จุด/การคำนวณ — กัน 1 ฟลุ๊คดันแรง), `TREND_EPS=2` (เกณฑ์ ↑/↓).

### 2. Integrate — `cgd_intel` prediction (area-level adaptive)
- `_build_intel` / `_scope_block`: หลังได้ `p25, p75` จาก `_pct` → เรียก `recency_adjusted_pct(area_win_series(...), p25, p75)` → ใช้ p25'/p75' ใน `predict_winning_price`.
- closed-loop (Sub-1) ไม่เปลี่ยน — ยังเทียบกรอบบน `area_price_hi` (ตอนนี้ recency-adjusted แล้ว).

### 3. Integrate — Round 2 per-company trend
- `analyze_bidders` (Sub-1): เปลี่ยน `company_area_history` (median เดิม) → ใช้ `ewma_trend(company_series(...))` → โชว์ `{ewma, trend ↑↓→, n}` แทน median เดิม. format Round 2 เดิมรองรับ (มี field hist+trend อยู่แล้ว — ปรับ source).

## Data semantics (สำคัญ)
- **area_win_series** = ส่วนลด**ผู้ชนะ** (cgd_winners ทั้งหมด = winner เท่านั้น) + bid_results winner → "ต้องลดเท่าไรถึงชนะ" (= ที่ predict ใช้)
- **company_series** = win-discount (cgd_winners) + bid-discount (bid_results price_proposal) ของบริษัทนั้น → "บริษัทนี้ลดระดับไหน เทรนด์ยังไง". cgd_winners มีเฉพาะที่เขา**ชนะ**, bid_results เพิ่มงานที่เขา**ยื่น(แพ้)** → ครบขึ้น
- bid_results ตอนนี้ sparse (W0 เพิ่งทำ) → series ส่วนใหญ่มาจาก cgd_winners. recency-weight ยังทำงาน (cgd_winners มี announce_date). bid_results จะค่อยเพิ่มน้ำหนักล่าสุดเมื่อสะสม

## Edge cases
| กรณี | จัดการ |
|---|---|
| series ว่าง / n<MIN_N | ใช้ median/percentile เดิม ไม่ปรับ (ไม่มีเทรนด์) |
| budget=0/None ใน bid_results | ข้าม point นั้น (คำนวณ discount ไม่ได้) |
| ewma สุดโต่ง (1 ฟลุ๊ค) | CAP จำกัด delta ≤8 จุด + blend median |
| announce_date/fetched_at หาย | จัดเป็นเก่าสุด (น้ำหนักน้อย) หรือข้าม — เลือกข้าม (ordering ต้องเชื่อถือได้) |
| subtype (concrete/asphalt) | area_win_series ส่ง subtype ต่อ `_fetch` (สอดคล้อง N+111) |

## Testing (TDD)
- `ewma`: worked example — series [30,30,30,20] α=0.3 → ~27 (ไม่ใช่ 20). [30]×5+[20] → ลู่เข้า. ว่าง→None
- `ewma_trend`: n<3→trend None; recent สูงกว่า→↑; เท่า→→
- `recency_adjusted_pct`: delta clamp ที่ CAP; n<MIN_N→ไม่ปรับ; เลื่อน range คงความกว้าง
- `area_win_series`/`company_series`: รวม cgd_winners+bid_results, เรียงเวลาถูก, discount จาก budget ถูก, scope ตำบล→จังหวัด (seed in-memory ทั้ง 2 ตาราง)
- integrate: predict ใช้ค่า recency-adjusted (เทียบ flat); analyze_bidders โชว์ ewma trend
- regression: test_cgd_intel, test_price_prediction, test_round2_analysis, test_compare_upper_bound เดิมผ่าน

## Deploy
push → VPS pull (timer-based หยิบเอง, ไม่ต้อง restart). ⚠️ gate confirm push. **ระวัง:** เปลี่ยน prediction LIVE → sanity เทียบ predict flat vs adaptive บนงานจริงก่อน + ดูว่า bid_results sparse ทำให้เหมือนเดิมเกือบหมด (ปลอดภัย).
