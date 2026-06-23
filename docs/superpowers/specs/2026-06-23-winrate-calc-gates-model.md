# Custom Win% Calculator — Gates Model Rebuild — Design Spec

**Date:** 2026-06-23
**Requested by:** คุณกัญจน์
**Status:** Approved (brainstorming complete), ready for implementation plan
**Supersedes computation model of:** `2026-06-22-custom-winrate-calculator-design.md` (§4 computation + §6 components). UI/form (§3) และ data flow ภาพรวมยังคงเดิม — เปลี่ยนเฉพาะ "เครื่องยนต์คำนวณ"

## 1. Problem / Bug ที่จุดประกาย

งาน `69059453079` (อบต.หนองซน อ.นาทม จ.นครพนม, งบ 1,647,000) ผู้ชนะจริงยื่น **1,145,000 (ลด 30.5%) ซึ่งเป็นราคาต่ำสุดในสนาม 12 ราย**. พอผู้ใช้กรอกราคาเดียวกันนี้ลง Custom Win% Calculator → ระบบขึ้น **"โอกาสชนะ 0%"** ซึ่งขัดความจริงชัดเจน (ราคาที่ชนะจริงไม่ควรได้ 0%).

### Root cause (พิสูจน์ด้วยข้อมูล prod แล้ว) — สองสาเหตุประกอบกัน

1. **ฐานข้อมูลคู่แข่งแย่ (สาเหตุหลัก).** `calc_custom_winrate` เดิมใช้ `scope_rows` = **เฉพาะผู้ชนะ** ของงานในตำบล/อำเภอเดียวกัน ซึ่งงานนี้มีแค่ **5 auction** → คู่แข่งที่เลือกเกือบทั้งหมด `has_history=False` → ตก fallback ไปใช้ median ของ "ผู้ชนะ 5 งาน" ซึ่งเบ้ลึก = 40.3% → ราคาเรา (ลด 30.5%) เลยดู "ตื้นกว่าค่ากลาง" → `win_pct_against=95%` (เพดาน clamp) ทุกราย.
2. **สูตรรวมแบบ Friedman (คูณ) ระเบิดเป็นศูนย์.** เดิมรวมหลายคู่แข่งด้วยการคูณ `∏ CDF` (`cgd_intel.py:943`). พอแต่ละราย ≈ 0.05 และมี 11 ราย → `0.05¹¹ ≈ 0` → round เป็น 0%.

> **สำคัญ:** แม้แก้สาเหตุ #1 ให้ฐานข้อมูลดีแล้ว สาเหตุ #2 ก็ **ยังพังอยู่** — ดู §3 (Friedman ให้ 0.1% แม้ใช้ข้อมูลดี). ต้องแก้ทั้งคู่.

## 2. งานวิจัยที่อ้างอิง — Friedman vs Gates

ปัญหานี้คือข้อถกเถียงคลาสสิกใน **competitive bidding theory**:

| สำนัก | สูตรรวมหลายคู่แข่ง | สมมติฐาน | ผล |
|---|---|---|---|
| **Friedman (1956)** | `P_win = ∏ Pᵢ` | คู่แข่งยื่นอิสระต่อกัน | คนเยอะ → ดิ่งศูนย์เร็ว (= bug ของเรา) |
| **Gates (1967)** | `P_win = 1 / (1 + Σ (1−Pᵢ)/Pᵢ)` | bids สัมพันธ์กัน (proportional hazards) | คนเยอะ → ลดลงแต่ไม่ดิ่งศูนย์ |

โดย `Pᵢ` = ความน่าจะเป็นที่ "เรา" ชนะคู่แข่ง i รายเดียว.

- งานยุคหลัง (Skitmore, Pettitt & McVinish 2007, *J. Constr. Eng. Manage.* 133(11)) พิสูจน์ว่า Gates มีรากฐานคณิตศาสตร์รองรับ (valid iff bids อยู่ในตระกูล proportional-hazards / Weibull) และ **ทำนายแม่นกว่า Friedman ในงานจริง** เพราะ bids ก่อสร้างมีความสัมพันธ์กัน (ต้นทุนวัสดุ/สภาพตลาดร่วมกัน) ไม่อิสระจริงอย่างที่ Friedman สมมติ.
- คุณสมบัติสำคัญของ Gates: ถ้าทุก `Pᵢ = 0.5` (เราเป็นค่าเฉลี่ยของสนาม) → `P_win = 1/(N+1)` พอดี = "ส่วนแบ่งยุติธรรม" ในสนาม N+1 ราย. และ Gates **ทนทานต่อข้อมูลคู่แข่งรายเดียวที่เพี้ยน** (หนึ่งพจน์เพี้ยนไม่ทำผลรวมเป็น 0 เหมือนการคูณ) — สำคัญมากเพราะข้อมูลเรามีจุดบกพร่อง (เจอ `is_winner=0` ผิด, งานไม่มีแถวใน `cgd_winners`).

**แหล่งอ้างอิง:**
- [Comparison of Friedman and Gates Competitive Bidding Models — ASCE](https://cedb.asce.org/CEDBsearch/record.jsp?dockey=0008620)
- [Friedman and Gates—Another Look, *JCEM* 126(4), 2000](https://ascelibrary.org/doi/10.1061/%28ASCE%290733-9364%282000%29126%3A4%28306%29)
- [Gates' Bidding Model, *JCEM* 133(11), 2007](https://ascelibrary.org/doi/10.1061/(ASCE)0733-9364(2007)133:11(855))
- [Gates' bidding model — QUT ePrints](https://eprints.qut.edu.au/13406/)

## 3. Validation — ทดสอบบนข้อมูล prod จริง (งาน 69059453079, ลด 30.5%, คู่แข่งจริง 11 ราย)

งานนี้ = **ถนนคอนกรีต (`subtype=concrete`) ของ อบต. (`market=local`)**. ใช้ดีไซน์ใหม่ (per-company all-bids + กรอง subtype+agency เป็นชั้น + recency-weight) คำนวณ `Pᵢ` ราย:

| คู่แข่ง | P(เราชนะ) | ฐานข้อมูลที่ใช้ (ชั้นที่ผ่าน) |
|---|---|---|
| ภูริพัฒน์ กรุ๊ป | 0.82 | concrete+local 134 |
| ตรีมูรติการโยธา | 0.70 | concrete+local 91 |
| **นุ่มนวลก่อสร้าง** | **0.23** | concrete 16 (concrete+local=1 บาง → ตกชั้น) — ลดลึก = คู่แข่งตัวจริง |
| ดวงจินดา 999 | 0.36 | concrete+local 33 |
| พาหุงรุ่งเรือง | 0.38 | concrete+local 32 |
| **นครหลวงท่าอุเทน** | **0.25** | concrete+local 23 (ลดลึก) |
| ยศประทานฯ | 0.46 | concrete+local 18 |
| พันศิริ / วาทิพ / โพธิ์ชัย / เอส.พี. | 0.83 | pooled (ประวัติบาง) |

| สูตรรวม | ผล |
|---|---|
| **Friedman (คูณ)** | **0.1%** ← ยังดิ่งศูนย์แม้ข้อมูลดี |
| **Gates** | **7.5%** ← สมเหตุสมผล |
| ตาราง win% production เดิม (`winrate_grid`, k=12) | 12.7% (เทียบเป็น sanity ภาพรวม) |

**บทพิสูจน์ 2 ชั้น:**
1. **Gates จำเป็นจริง:** Friedman พังเพราะคูณเลข <1 จำนวน 11 ตัว (มีคู่แข่งตัวจริง 0.23/0.25 ปน) → 0.1%. Gates รวมแบบบวก → 7.5% สมเหตุสมผล.
2. **กรอง subtype+agency ทำให้แม่นขึ้น:** เทียบกับเวอร์ชันไม่กรอง (ใช้ประวัติทุกประเภทงาน) คู่แข่งหลายราย `Pᵢ` **ลดลง** (ตรีมูรติ 0.80→0.70, พาหุง 0.56→0.38, นครหลวง 0.36→0.25) เพราะพวกเขา**ลดลึกกว่าค่าเฉลี่ยตัวเองเมื่อทำงานถนนคอนกรีตของ อบต.** = สะท้อนว่าตลาดท้องถิ่นแข่งดุจริง ([[project_market_regime_pricing]], [[project_price_by_road_type]]). Gates ตามไปที่ 7.5% (สมจริงกว่า 9.8% ของเวอร์ชันไม่กรอง).

Coverage (พิสูจน์แล้ว): `bid_results` **157,946 แถว / 10,022 บริษัท** ทุกแถวมี `normalized_name`. **หน่วยงานอนุมานจาก `project_name` ได้ 100%** (482/482 — ชื่องานก่อสร้างฝัง "องค์การบริหารส่วนตำบล/เทศบาล/กรม" เสมอ) เพราะ `cgd_winners` ไม่มีคอลัมน์ `dept_name`. Sample ต่อบริษัทหลังกรอง subtype+agency ยังพอ (18–134) ยกเว้นบางรายที่ fallback ลงชั้น — กลไกชั้นจึงจำเป็น.

## 4. Computation Model (เครื่องยนต์ใหม่)

### 4.1 แปลงราคาผู้ใช้ → %ส่วนลด (คงเดิม)
```
my_discount_pct = max(0, (budget − my_price) / budget × 100)
```
`my_price ≤ 0` หรือ parse ไม่ได้ หรือ `budget ≤ 0` → return `None` (แสดงข้อความให้กรอกใหม่).

### 4.2 distribution ต่อคู่แข่ง 1 ราย (กรอง subtype+agency เป็นชั้น)

**signature ของงานปัจจุบัน** — คำนวณครั้งเดียวจากงานที่กำลังดู:
- `this_subtype` = `road_subtype(project_name)` หรือ `water_subtype(project_name)` → `concrete`/`asphalt`/`water_excav`/`water_struct`/`None`
- `this_market` = `agency_market(dept_name)` (มีจาก `projects_seen`) — `local`/`provincial`/`central`/`None`

สำหรับคู่แข่งชื่อ `name` (normalize ด้วย `portal_views._norm_name`) ดึง **all-bids history** จาก `bid_results JOIN cgd_winners`:
```sql
SELECT b.price_proposal, cw.budget, cw.project_name, cw.fiscal_year
FROM bid_results b JOIN cgd_winners cw ON cw.project_id = b.project_id
WHERE b.normalized_name = ?
  AND cw.proc_type IN (COMPETITIVE_SET)      -- เฉพาะงานแข่งจริง กันงานเฉพาะเจาะจง disc≈0 เจือจาง
  AND cw.budget > 0 AND CAST(b.price_proposal AS REAL) > 0
```
แต่ละแถว: คิด `discount = (budget − price_proposal)/budget × 100` (ตัด outlier นอก `[0, DISC_MAX=60]`), แท็ก `subtype = road/water_subtype(project_name)` และ `market = agency_market(project_name)` **(อนุมานหน่วยงานจาก `project_name` เพราะ `cgd_winners` ไม่มี `dept_name` — พิสูจน์แล้วได้ 100%)**, ถ่วงน้ำหนัก `recency_weight(fiscal_year)`.

**เลือก distribution แบบ "ชั้นที่เจาะจงสุดที่ยังหนาพอ"** — ใช้ชั้นแรกที่มี **จำนวนแถวดิบ ≥ `MIN_OWN_BIDS`(=5)**:

| ชั้น | เงื่อนไขกรอง | เหตุผล |
|---|---|---|
| 1 | `subtype == this_subtype` **และ** `market == this_market` | ตรงประเภทงาน+ระบอบหน่วยงานที่สุด |
| 2 | `subtype == this_subtype` | ผ่อน agency (เช่นนุ่มนวล concrete+local=1 → ตกมา concrete=16) |
| 3 | ทุกแถว (all work types) | กันบริษัทที่ประวัติประเภทนี้บาง |
| 4 (pooled) | — ไม่ใช่ประวัติบริษัท → ใช้ §4.3 | บริษัทไม่มีประวัติใช้ได้เลย |

ถ้า `this_subtype is None` (เช่นงานอาคาร) → ข้ามชั้นที่อิง subtype, เริ่มที่ market-only แล้ว all. `this_market is None` → ข้ามเงื่อนไข market.

> **🔑 Design decision (กัญจน์ 2026-06-23) — gate ด้วย "จำนวนดิบ" ไม่ใช่ effective sample.** recency weight (`half_life=1` ปี: ปีนี้=1.0, 2568=0.5, 2567=0.25...) ใช้ **ภายในการคิด `Pᵢ` เท่านั้น** (§4.4 — bid ใหม่ถ่วงหนักกว่าเก่า) **ไม่ใช้เป็นเกณฑ์ตกชั้น**. เหตุผล: นิสัยการลดราคาเป็น **structural trait** ของบริษัท (คนลดลึกก็ลดลึกต่ออีกหลายปี) — ถ้า gate ด้วย effective sample (เช่น ESS≥6) บริษัทที่มีประวัติลดลึกแต่ข้อมูลเก่าจะถูกทิ้งไปใช้ค่าเฉลี่ยตลาด ทำให้ผลมองโลกดีเกินจริง (พิสูจน์: ESS-gate ทำนุ่มนวล P 0.23→0.83, Gates 7.5%→10%). **ห้ามเปลี่ยน gate ไปใช้ effective sample โดยไม่มี evidence ใหม่** — จะทำผลเปลี่ยนเงียบๆ และทิ้งสัญญาณคู่แข่งตัวจริง.

### 4.3 pooled fallback distribution (สนามทั่วไป)
คู่แข่งที่ประวัติบาง → ใช้ distribution ของสนาม (อำเภอ) = all-bids ทุกบริษัทใน scope เดียวกับที่ `bid_field._field_auctions` ดึงให้ `winrate_grid` (ถ่วงน้ำหนักปีเหมือนกัน). เป็นตัวเดียวกันทั้งหมดสำหรับทุกคู่แข่ง "ไม่รู้จัก" — แต่ **ไม่เกิดปัญหาคูณซ้ำ** เพราะ Gates รวมแบบบวก (ดู §4.5).

### 4.4 Pᵢ = โอกาสที่เราชนะคู่แข่ง i
```
Pᵢ = (Σ weight ของ bids ที่ discount < my_discount_pct) / (Σ weight ทั้งหมด)
   clamp [0.05, 0.95]
```
ตีความ: คู่แข่งยื่น "ตื้นกว่าเรา" = ราคาเขาสูงกว่า = **เราชนะ**. clamp กันมั่นใจเกินจริงจาก sample เล็ก. `win_pct_against = round((1 − Pᵢ) × 100)` สำหรับแสดงราย (โอกาสคู่แข่งรายนี้ชนะเรา).

### 4.5 รวมหลายคู่แข่ง — Gates
```
P_win = 1 / (1 + Σᵢ (1 − Pᵢ)/Pᵢ)
overall_win_pct = round(P_win × 100)
```
- คู่แข่ง "ไม่รู้จัก" M ราย ที่ใช้ pooled `P` เท่ากัน → บวก `M × (1−P)/P` เข้าไปตรงๆ (ไม่ต้อง hack "รวมเป็น 1 ก้อน" แบบ spec เดิม — การบวกไม่ระเบิด).
- ไม่มีคู่แข่งเลย (หลัง dedupe) → return `None` + ข้อความ "เลือกคู่แข่งอย่างน้อย 1 บริษัท".

### 4.6 ทำไมไม่ใช้ `winrate_grid` ที่มีอยู่แล้วเลย
`winrate_grid` ตอบ "สนาม N คน (ไม่รู้ว่าใคร)". Calculator นี้ value-add คือ **เจาะจงบริษัท A/B** — ใช้ประวัติยื่นจริงรายบริษัท. สอง feature คนละคำถาม อยู่คู่กันในหน้าเดียว.

## 5. Data Flow / Components

| Component | File | หน้าที่ |
|---|---|---|
| `_company_bid_dist(conn, name, this_subtype, this_market)` | `bid_field.py` (ใหม่) | ดึง all-bids + แท็ก subtype/market + เลือก distribution เป็นชั้น (§4.2) · คืน `([(disc,weight)], layer_label)` · `(None, 'pooled')` ถ้าทุกชั้นบาง |
| `_pooled_dist(conn, province, tokens, district)` | `bid_field.py` (ใหม่/refactor จาก `_field_auctions`) | pooled `[(discount, weight)]` ของสนาม (§4.3) |
| `p_beat(dist, my_discount)` | `bid_field.py` (ใหม่) | `Pᵢ` clamp [0.05,0.95] (§4.4) · `None` ถ้า dist ว่าง |
| `gates_winrate(probs)` | `bid_field.py` (ใหม่) | Gates combine (§4.5) · pure |
| `calc_custom_winrate(...)` | `cgd_intel.py` (rewrite) | derive `this_subtype`/`this_market` → per-name `_company_bid_dist` → p_beat → gates · คืน `{overall_win_pct, my_discount_pct, breakdown:[{name, win_pct_against, p_beat, source, n_games}]}` |
| `_render_custom_calc_form(...)` | `portal_views.py` (ปรับ output) | ฟอร์มเดิม + ผลใหม่ (P ต่อราย + ป้าย layer ที่ใช้ เช่น "ถนนคอนกรีต อบต. 91 ครั้ง" / "สนามทั่วไป" + disclaimer) |

**reuse ของเดิม (ไม่เขียนใหม่):** `road_subtype`, `water_subtype`, `agency_market`, `recency_weight`, `COMPETITIVE_SET` ใน `cgd_intel.py`.

**signature เปลี่ยน:** `calc_custom_winrate` เดิมรับ `(rows, fallback_stats, ...)` → ใหม่รับ `(conn, province, tokens, project_name, dept_name, district, my_price, budget, selected_names, extra_names)` (ต้องเข้าถึง DB + ชื่องาน/หน่วยงานเพื่อ derive subtype/market). `job_detail()` ใน `portal_views.py:93-99` ปรับ call site — `dept_name` มีอยู่แล้วในฟังก์ชัน (`portal_views.py:72-79`).

ไม่แก้ schema/DB — ใช้ `bid_results` + `cgd_winners` ที่มีอยู่.

## 6. Edge Cases

| กรณี | พฤติกรรม |
|---|---|
| ไม่เลือก/พิมพ์คู่แข่งเลย | ข้อความเตือน ไม่คำนวณ |
| `my_price` ว่าง/parse ไม่ได้/≤0/≥budget×(1+) | ≥budget → discount=0 คำนวณต่อได้; ≤0/parse ไม่ได้ → เตือนกรอกใหม่ |
| คู่แข่งประวัติ <5 ครั้ง หรือ 0 | fallback pooled + ป้าย "สนามทั่วไป (ไม่มีประวัติเฉพาะบริษัท)" |
| pooled เองก็ว่าง (scope ไม่มีข้อมูลเลย) | `Pᵢ = None` → ข้ามรายนั้น; ถ้าทุกรายว่าง → คำนวณไม่ได้ แสดงข้อความ |
| คู่แข่งซ้ำ (ติ๊ก+พิมพ์ชื่อเดียวกัน) | dedupe ด้วย `_norm_name` ก่อนคำนวณ |
| `Pᵢ` หลัง clamp ติดเพดาน 0.95/พื้น 0.05 | ใช้ได้ปกติใน Gates (ไม่หาร 0) |
| error ใดๆ | graceful — wrap try/except ไม่ทำหน้า `/portal/job` พัง (เหมือน intel เดิม) |

## 7. ข้อจำกัดที่บอกผู้ใช้ตรงๆ (แสดงในผลลัพธ์)

- `Pᵢ` อิงพฤติกรรมการยื่นในอดีตของบริษัทนั้น **กรองตามประเภทงาน (ผิวถนน/งานน้ำ) + ระบอบหน่วยงาน (อบต./อบจ./กรม) ทั่วประเทศ** — เป็น proxy ที่ดีของ "นิสัยการลดราคาในงานแบบนี้" แต่ไม่ใช่ความแม่น 100%. ไม่กรองตามพื้นที่ (จังหวัด/อำเภอ) เพราะ sample จะบางเกิน (อ.นาทม มี ~2 ครั้ง/บริษัท) — การ scope ตามพื้นที่ = future work (§9).
- หน่วยงานอนุมานจาก `project_name` (cgd_winners ไม่มี dept_name) — ส่วนใหญ่แม่น แต่งานที่ชื่อไม่ระบุหน่วยงานจะนับเป็น market=None (ตกไปชั้นที่ผ่อน agency).
- Gates สมมติ bids สัมพันธ์กัน (เหมาะกับ sealed-bid ก่อสร้าง) — model ที่งานวิจัยรับรองว่าแม่นกว่าการคูณ แต่ยังเป็นการประมาณ.
- disclaimer สั้นในหน้าผล: *"โอกาส% ประเมินจากนิสัยการยื่นราคาของคู่แข่งในงานประเภท+หน่วยงานแบบเดียวกัน ด้วยโมเดล Gates — เป็นการประมาณ ไม่ใช่การรับประกัน"*

## 8. Testing Plan

- `test_bid_field.py`:
  - `gates_winrate([0.5,0.5,0.5])` → 1/4 = 0.25 (คุณสมบัติ 1/(N+1))
  - `gates_winrate([0.9])` → 0.9 (รายเดียว = P เอง)
  - `gates_winrate` ไม่ดิ่งศูนย์เร็วเท่า `∏` (เทียบ 11 ราย @0.5: Gates=1/12≈8.3% vs Friedman=0.05%)
  - `p_beat`: clamp [0.05,0.95], dist ว่าง→None, weight ทำงาน (ปีล่าสุดถ่วงหนัก)
  - `_company_bid_dist`: เลือกชั้นถูก — concrete+local หนาพอ→ชั้น1 (label มี subtype+agency); concrete+local บาง→ตกชั้น concrete; ทุกชั้นบาง→`(None,'pooled')`; subtype/market=None→ข้ามเงื่อนไขที่เกี่ยว; proc_type filter ตัดงานเฉพาะเจาะจง
  - **gate = จำนวนดิบ (lock design decision §4.2):** บริษัทมี 5 bid เก่า (ปี 2564, effective weight รวม <1) → **ยังผ่าน gate ใช้ distribution ตัวเอง** ไม่ตกไป pooled (ยืนยันว่า recency ไม่ถูกใช้เป็นเกณฑ์ตกชั้น)
- `test_cgd_intel.py`:
  - `calc_custom_winrate`: เคสมีประวัติ/ไม่มี(pooled)/ผสม, dedupe ชื่อซ้ำ, ไม่มีคู่แข่ง→None, price invalid→None
  - **regression เคสจริง**: งาน 69059453079 ราคา 1,145,000 + 11 คู่แข่ง → overall ∈ [3,15]% (ไม่ใช่ 0%) — assert ป้องกัน bug เดิมกลับมา
- `test_portal_views.py`: render ผล — P ต่อราย, ป้าย source, disclaimer ครบ
- Manual smoke: POST `/portal/job/calc` บน prod เทียบเลขกับ unit (ผ่าน Sophia sanity)

## 9. Out of Scope (เลื่อนไว้)

- per-company distribution scope ตาม**พื้นที่** (จังหวัด/อำเภอ) — ตอนนี้กรองแค่ subtype+agency ทั่วประเทศ เพราะ scope พื้นที่ทำ sample บางเกิน (อ.นาทม ~2 ครั้ง/บริษัท). future work เมื่อ backfill หนาพอ
- correlated/joint competitor modeling ที่ละเอียดกว่า Gates — Gates เพียงพอสำหรับ MVP
- แก้ data-quality root causes ที่เจอระหว่างทาง (`is_winner=0` ผิดในงาน 69059453079, งานไม่มีแถวใน `cgd_winners`) — แยกเป็น issue ต่างหาก ไม่ปนกับ feature นี้
- JS autocomplete — ระบบไม่มี JS คงไว้
