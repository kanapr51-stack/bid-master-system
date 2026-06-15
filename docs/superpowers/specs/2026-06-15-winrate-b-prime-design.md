# Win-Rate B′ — ขยาย coverage ด้วย machinery เดิม — Design

**วันที่:** 2026-06-15
**สถานะ:** design — APPROVED WITH MINOR REVISIONS (กัญจน์ 8.5/10 + ChatGPT consult converged 8/8)
→ revisions applied: MIN_N_AUCTIONS=3, assisted disclaimer เน้น, fail_reason log → next: writing-plans
**ต่อจาก:** B/B.1/#3 (LIVE, closed-loop validate งานจริง 69059374770 แม่น 0.04%). spec เดิม `2026-06-15-conditional-winrate-b-design.md`

---

## 1. Goal

ตาราง win% (B.1) ปัจจุบัน **ไม่ขึ้นเมื่อพื้นที่เป้าหมายข้อมูลบาง** (gate ต้อง ≥5 full-field auctions)
และเมื่อขึ้นก็ **center คอลัมน์ลึกเกินจริง** (province mean ~8 ขณะงานเล็กจริงมี 3-5 ราย) + **ไม่ถ่วงปี**
(งานเก่า 5 ปีนับเท่างานปีนี้). B′ แก้ 3 จุดนี้ **ด้วย machinery เดิม** ไม่เพิ่ม degree-of-freedom ใหม่.

## 2. หลักการแกน (กัญจน์ + ChatGPT ยืนยันร่วม)

1. **Price predictor = sacred.** สิ่งที่ผู้รับเหมาซื้อคือ "ควรยื่นเท่าไร". win-rate/n/F_bid ต้องยอม
   degrade ตัวเองเพื่อไม่ทำลายราคาหลัก. **ห้ามให้ตาราง assisted (อิงพื้นที่กว้าง) บังราคา local.**
2. **F_bid ก้อนเดียวต่อการ render.** ราคา (inverse-CDF) + win% (^k) มาจาก F เดียวกันเสมอ →
   คอลัมน์กลาง = เป้า 75/50/25 เป๊ะ (semantic consistency). **ไม่ใช้ 2 ก้อน** (price local + % broad
   → "ราคา 50% แต่คอลัมน์ 72%" = ผู้ใช้สับสน).
3. **ขยาย coverage ด้วย ladder เดิม ไม่เพิ่ม sophistication.** ในระบบข้อมูลบาง sophistication =
   variance เพิ่มเร็วกว่าความแม่น. B′ จบที่ **3 knobs** เท่านั้น.

## 3. Scope

- **In scope (3 knobs):** (1) scope ladder mirror ราคา · (2) recency-weighted CDF + ESS floor ผ่าน
  ladder · (3) local n centering · + confidence tag UI · + breadcrumb log (Δk/scope/ESS)
- **Out of scope (B″):** hierarchical shrinkage (`F* = wF_local + (1−w)F_broad`) · runtime KS shape-gate ·
  k-clamp (`|Δk|≤2`) · `discount' = discount − β(k−k̄)` · auto-tier ESS floor ตาม backfill %.
  B′ เก็บ **offline monitor data** (Δk, KS dataset, ESS distribution) ไว้ตัดสิน B″ เมื่อมีหลักฐาน drift.

## 4. กลไก (3 knobs)

### Knob 1 — Scope ladder (mirror ราคา)

F_bid เลือก scope แบบ mirror บล็อกราคา แล้วผ่อนต่อถ้า gate ไม่ผ่าน:

```
1. เริ่ม: used_rows project_ids   ← scope ที่บล็อกราคาเลือก (ตำบล/อำเภอ/จังหวัด + cf จัดเต็ม)
2. gate ผ่าน?  (auctions ≥ MIN_AUCTIONS(5)  AND  ESS ≥ ESS_FLOOR(6))
3. ไม่ผ่าน → ผ่อน 1 ขั้น: อำเภอ (cf) → จังหวัด (cf)  ผ่าน _fetch_scope → project_ids ใหม่
4. ใช้ scope แรกที่ผ่าน gate → F_bid ก้อนนี้ทำทั้งราคา+% (consistent)
5. สุด ladder (จังหวัด) ยังไม่ผ่าน → grid=None → ไม่โชว์ตาราง (graceful)
```

- **คง cf จัดเต็ม** (subtype/year/proc_type/work_kind/nature/market) ที่ทุกขั้น ผ่าน `_fetch_scope`
  → project_ids → `_field_auctions(project_ids=...)`. ไม่ใช่ raw scope query.
- เคสปกติ (local ผ่าน) = **ไม่ผ่อนเลย ราคา local ล้วน** ✓ หลักการ price sacred.

### Knob 2 — Recency-weighted CDF + ESS floor

- `_field_auctions` ดึง `cw.fiscal_year` เพิ่ม → คืน `[[(name, disc, is_winner, fiscal_year)]]`.
- ทุก bid มีน้ำหนัก `w = recency_weight(fiscal_year)` (half-life 1 ปี, reuse `cgd_intel.recency_weight`).
- **Weighted F_bid:** `F_bid(x) = (Σ w[bid≤x]) / (Σ w)` แทนนับหัว.
- **Weighted quantile** (`_weighted_quantile`): หา x ที่ cumulative-weight fraction = q (linear interp
  บน cumulative weight, แบบเดียวกับ `_quantile` แต่ถ่วงน้ำหนัก).
- **ESS gate** = `Σw` (recency-effective count: งานปีปัจจุบัน w=1.0, งานเก่าจางตาม half-life).
  เป็นส่วนหนึ่งของ gate Knob 1 (ข้อ 2). `ESS_FLOOR = 6`
  > ⚠️ แก้จาก implementation (N+138): เดิม spec เขียน Kish `(Σw)²/Σw²` ผิด — Kish=n เมื่อน้ำหนักเท่ากัน
  > → งานเก่าทั้งหมดผ่าน gate (ขัดเจตนา "งานเก่าจาง ESS ต่ำ"). `Σw` ตรง test+เจตนา (independent review ยืนยัน)
  (bootstrap: half-life 1ปี + 4+4 bids → ESS≈6-7; ต่ำกว่า 5 ไม่ไว้ใจ). **คงที่ใน B′** —
  comment ว่าขยับ 8 (backfill>60%) / 10 (>90%) ภายหลัง (auto-tier = B″).

### Knob 3 — Local n centering (decouple เดียวที่ปลอดภัย)

- แม้ F_bid ผ่อนไปจังหวัด → **center คอลัมน์ด้วย n ของ scope แคบสุดที่มี full-field ≥ `MIN_N_AUCTIONS(3)` auctions**
  (= สนามจริงพื้นที่เป้าหมาย). คำนวณ `n_mean/n_sd` จาก auctions ของ local scope นั้น.
  - **`MIN_N_AUCTIONS = 3`** (ไม่ใช่ 2 — review กัญจน์): 2 auctions → variance estimate แทบไม่มีความหมาย
    (เช่น 5+2 ราย → mean 3.5, sd 2.1 → คอลัมน์ 1/4/6 noise). ต้อง ≥3 ถึงไว้ใจ SD.
- `k_mid` (ใช้ทั้ง price inverse-CDF + % eval) = มาจาก local n → **center column = target เป๊ะ**
  (consistency รักษาไว้ แม้ F=จังหวัด, k=ตำบล: `price_t = budget(1−Wquantile(F_bids, target^(1/k_mid)))`,
  `win%_k = target^(k/k_mid)`).
- ถ้า local scope ไม่มี full-field ≥ MIN_N_AUCTIONS → ใช้ n ของ F-scope + tag "ประมาณจากระดับ[scope]".

## 5. Confidence tag (UI — รับจาก ChatGPT)

ป้ายระดับความเชื่อตาม scope ที่ F_bid ใช้เทียบ scope ที่ราคาใช้:

| scope F_bid | tag | ความหมาย |
|---|---|---|
| = scope ราคา (ไม่ผ่อน) | 🟢 local | ราคา+โอกาส อิงพื้นที่จริง |
| ผ่อน 1 ขั้น (อำเภอ) | 🟡 อิงอำเภอ | local บาง — เสริมด้วยอำเภอ |
| ผ่อนสุด (จังหวัด) | 🟠 อิงจังหวัด | local บางมาก — เสริมด้วยจังหวัด |

## 6. Integration กับ price block (price sacred)

- **🟢 local:** ตาราง win% **แทน** บล็อก a/b/c เดิม (เพราะ local ล้วน — consistent กับราคาหลัก).
- **🟡/🟠 assisted:** **คงบล็อกราคา local a/b/c ไว้** (`predict_lines` ปกติ) + ตาราง win% ต่อท้าย
  (label assisted) → ราคาหลักยัง local, ตารางเป็นข้อมูลเสริมโอกาสชนะ. **ไม่ให้ราคา assisted บัง local.**
  - **เน้น disclaimer ชัด (review กัญจน์):** ตาราง assisted **ต้องมีบรรทัดเตือนแยก** `⚠️ ราคาด้านบนยังอิง[local]
    — ตารางนี้บอกเฉพาะ "โอกาส%"` กันผู้ใช้อ่านเร็วแล้วเข้าใจว่าราคาในตาราง = ราคาแนะนำ.
- ถ้า grid=None → บล็อก a/b/c เดิม (เหมือนวันนี้).

## 7. Output (ตัวอย่าง 🟡 assisted, local n=5, F=อำเภอ)

```
💡 ราคาอ้างอิง (งานถนน ต.โพธิ์หมากแข้ง)        ← บล็อกราคา local คงไว้ (assisted mode)
   ... a/b/c เดิม ...

💵 โอกาสชนะตามจำนวนผู้ยื่น (งบ 2,000,000)
   ผู้ยื่น →     3ราย   5ราย   7ราย          ← center = n สนาม local (5) ไม่ใช่ province(8)
   1,138,622      85%    75%    66%
   1,171,015      62%    50%    40%           ← คอลัมน์กลาง = เป้า 50% เป๊ะ
   1,218,701      36%    25%    16%
   📊 สนามนี้เฉลี่ย 5 ผู้ยื่น (±2)
   📈 จาก 9 งานที่มีข้อมูลผู้ยื่นครบ · 41 ราย
   🟡 โอกาส% อิงระดับอำเภอ (พื้นที่นี้ข้อมูลบาง)
   ⚠️ ราคาด้านบนยังอิงตำบล — ตารางนี้บอกเฉพาะ "โอกาสชนะ%"
   * คอลัมน์ตรงค่าเฉลี่ย = เป้า 75/50/25 · ยิ่งผู้ยื่นเยอะ โอกาสยิ่งต่ำ
```

## 8. Architecture (เปลี่ยน `scripts/bid_field.py`)

```
_weighted_quantile(sorted_pairs, q) -> float
    # sorted_pairs = [(value, weight)] เรียงตาม value · หา value ที่ cum-weight fraction = q

_field_auctions(...)  # +SELECT cw.fiscal_year → tuple เพิ่ม fiscal_year (ตัวที่ 4)
    # ⚠️ consumer ที่ unpack 3-tuple (analyze_field/_winner_idx/field_lines 2B) ต้อง update
    #    รับ 4-tuple ด้วย (backward-compat: ใช้ a[i][:3] หรือ unpack 4 ตัว) — กัน 2B พัง

winrate_grid(auctions, budget, local_auctions=None, targets=(75,50,25)) -> dict | None
    # auctions      = F_bid scope (อาจผ่อนกว้าง) — ใช้ทำ weighted CDF + ราคา
    # local_auctions= scope แคบสุดมี full-field (≥ MIN_N_AUCTIONS=3) — ใช้ center n เท่านั้น (None → ใช้ auctions)
    # weighted CDF + ESS gate(≥6) + local-n centering
    # คืน {ns, rows, n_mean, n_sd, n_auctions, n_bids, ess, budget, k_mid} | None

winrate_lines(grid, conf_tag="", price_basis="") -> list[str]
    # render + confidence tag (🟢🟡🟠)

field_and_winrate(...)  # orchestrate ladder: ลอง scope → gate → ผ่อน → คืน (wl, fl, conf_tag, used_scope)
```

**ladder orchestration** อยู่ใน `field_and_winrate` (หรือ helper `_winrate_with_ladder`):
รับ price-scope project_ids + (province, tokens, tambon, amphoe, cf) → ลอง project_ids → ถ้า gate fail
ผ่อน `_fetch_scope(district=amphoe)` → `_fetch_scope()` (province) → คืน grid + conf_tag.

**Integration `cgd_intel.py` ~586-601:** เรียก ladder → ได้ (wl, fl, conf_tag). render ตาม §6
(🟢 แทน a/b/c · 🟡🟠 คง a/b/c + ตารางต่อท้าย).

## 9. Breadcrumb log (offline monitor — เตรียม B″)

`_log.info` ต่อ render: `winrate scope=%s conf=%s ess=%.1f k_local=%s k_fscope=%s delta_k=%s fail_reason=%s`
→ ภายหลัง analyze offline: KS(F_local,F_broad) distribution, Δk distribution → ตัดสิน B″ (clamp/shrinkage).

- **`fail_reason` (review กัญจน์)** = สาเหตุที่ scope หนึ่งไม่ผ่าน gate ก่อนผ่อน/หรือ None สุดท้าย:
  `AUCTIONS` (auctions<5) / `ESS` (ESS<6) / `BOTH` / `PRICE_COLLAPSE` (<2 แถว) / `OK`.
  → 6 เดือนข้างหน้าถาม "ทำไมตารางไม่ขึ้น" ตอบได้ทันทีจาก log โดยไม่ต้อง reproduce.

## 10. Gating (graceful)

| เงื่อนไข | ผล |
|---|---|
| local scope ผ่าน (auctions≥5 ∧ ESS≥6) | 🟢 ตารางแทน a/b/c |
| local ไม่ผ่าน, อำเภอ/จังหวัด ผ่าน | 🟡/🟠 คง a/b/c + ตาราง |
| สุด ladder ไม่ผ่าน | None → a/b/c เดิม (วันนี้) |
| ราคา <2 แถว distinct | None (สนามแคบ) |

## 11. Testing (TDD) — ขยาย `scripts/test_winrate_grid.py`

1. **Weighted quantile** — `_weighted_quantile` ถูกตาม synthetic ที่รู้ค่า (น้ำหนักเท่ากัน = `_quantile` เดิม).
2. **Recency** — งานปีเก่าถ่วงน้อยลง → CDF เลื่อนตามงานสด (synthetic 2 ปี ต่างชัด).
3. **ESS gate** — ESS<6 → ladder up / None ถูก (synthetic น้ำหนักเบ้).
4. **Local n centering** — F=province auctions (n~8) + local_auctions (n~4) → คอลัมน์ center=4 ไม่ใช่ 8.
   center column = target เป๊ะ แม้ F≠local. · local_auctions <MIN_N_AUCTIONS(3) → fallback ใช้ n ของ F-scope.
5. **Ladder** — mirror: local ผ่าน→ไม่ผ่อน(🟢) · local fail+อำเภอผ่าน→🟡 · สุด ladder fail→None.
6. **Consistency** — center column = target (75/50/25) ทุกกรณี (รวม assisted).
7. **Render+tag** — `winrate_lines` มี tag 🟢🟡🟠 + บรรทัด price-basis ถูก · grid=None → [].
8. **Assisted semantic** (review กัญจน์) — conf≠🟢 (price_basis=ตำบล, F=อำเภอ) → render **ต้องมี**
   บรรทัด `⚠️ ราคาด้านบนยังอิงตำบล`. กัน regression UX (ผู้ใช้เข้าใจราคาตาราง = ราคาแนะนำ).
9. **fail_reason** — gate fail แต่ละแบบ → grid/log มี fail_reason ถูก (AUCTIONS/ESS/BOTH/PRICE_COLLAPSE).
10. **Backward-compat** — `test_winrate.py`/`test_bid_field.py`/`test_cgd_intel.py` เดิมผ่าน (BMS_ENV=dev)
    + 4-tuple ไม่ทำ 2B (`analyze_field`) พัง.

## 12. Definition of Done (verifiable)

- `test_winrate_grid.py` ผ่านทุกเคสใหม่ + test เดิมทั้งหมดผ่าน (backward-compat).
- `py_compile` ผ่าน.
- smoke จริง: scope ข้อมูลบาง (อำเภอชนบท) → ตาราง 🟡/🟠 ขึ้น (เดิมไม่ขึ้น) + คงบล็อกราคา local ·
  scope local หนา → 🟢 ตารางแทน · center n สะท้อน local ไม่ใช่ province.
- `_field_auctions` ถูกอ่าน **รอบเดียวต่อ scope** (ไม่ query ซ้ำกับ 2B ในขั้นเดียวกัน;
  ladder อาจ query เพิ่มเมื่อผ่อน — ยอมรับได้ เกิดเฉพาะ local บาง).
- breadcrumb log ออกครบ (scope/conf/ess/Δk).
