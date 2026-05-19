# Classifier Deep Research (2026-05-18)

วิจัยเชิงลึกเรื่อง Classifier — เปรียบเทียบ Bid Master ปัจจุบัน vs G-LEAD vs eGP advanced + UNSPSC + แนวทาง upgrade

---

## 1. Current Classifier (Bid Master)

**มิติเดียว:** Lifecycle stage (6 buckets จาก stepId + status)

| Bucket | Logic |
|---|---|
| `pre_tor` | stepId Q* (แผนการจัดซื้อ) |
| `tor_review` | stepId U* (รับฟังคำวิจารณ์) |
| `active_bidding` | stepId M03/S*/Z* + deadline ≥ today |
| `pending_award` | active + deadline ผ่าน OR W*/C*/I* ไม่มี winner |
| `awarded_jobs` | มี winner cache |
| `cancelled_jobs` | projectStatus=R OR announce ลงท้าย "1" OR stepId B* |

**Filter pipeline:** Province + District whitelist (อ.บ้านแพง / อ.บึงโขงหลง) + keyword include/exclude

### ข้อจำกัด:
1. ❌ ไม่มี **project type** taxonomy (ถนน vs สะพาน vs อาคาร vs วัสดุ)
2. ❌ ไม่มี **budget tier** (งานเล็ก vs ใหญ่)
3. ❌ ไม่มี **urgency** (deadline ใกล้/ไกล)
4. ❌ ไม่มี **SME suitability flag**
5. ❌ ไม่มี **win probability** ต่อ customer
6. ❌ ไม่ parse TOR/BOQ content เลย (เห็นแค่ metadata)

---

## 2. G-LEAD Classification (จาก lightworkai.com)

### Filter dimensions:
- **Project Search** (keyword include)
- **Data Filter** (multi-criteria)
- **Project Status** (lifecycle stage)
- **Government Agencies** + **Location**
- **Budget Ranges** (min-max)
- **Midpoint Pricing**
- **Bidding Dates / Deadlines**
- **Procurement Method** (e-bidding / เฉพาะเจาะจง / คัดเลือก)
- **Categorization** (criteria types + methods)
- **Keywords / Exclusion Terms**

### Killer features:
- 🤖 **AI Deep Search** บน TOR + BOQ PDF
- 📊 **Competitor data aggregation** (bid count, wins, prices, midpoint vs winning bid)
- 📅 **1-year history** (vs eGP's 90 days)

---

## 3. Thai eGP Official Taxonomy

### UNSPSC (United Nations SPSC)
- 4-level hierarchy: **Segment / Family / Class / Commodity**
- 8-digit code
- ตัวอย่าง: `72121403` = บริการก่อสร้างโรงพยาบาล
- ใช้สำหรับสินค้า/บริการ

### 5 Code Groups ใน eGP
| Code | Group | ใช้กับ |
|---|---|---|
| **CGD** | สินค้าที่กรมบัญชีกลางกำหนด | สินค้าทั่วไป |
| **Innovation** | สินค้านวัตกรรมไทย | สินค้าวิจัย/นวัตกรรม |
| **TMT** | รหัสบัญชียา | ยาและเวชภัณฑ์ |
| **CMC** ⭐ | **รหัสวัสดุก่อสร้าง** | **เกี่ยวข้องกับเราโดยตรง** |
| **e-Market** | รหัสสินค้า e-Market | สินค้าใน e-market |

### methodId codes
- `15` = e-market
- `16` = e-bidding
- `19` = เฉพาะเจาะจง
- `18` = คัดเลือก
- `03` = ประกวดราคา

### Procurement Method × Project Type combination
typeId (เช่น construction/goods/service) × methodId (วิธีการ) = ระบุ "ทำงานประเภทไหนด้วยวิธีไหน"

---

## 4. Proposed Multi-Dimensional Classifier

### Architecture: **single row → multiple tags**

```
all_jobs row
  ├── lifecycle_stage (existing)        # pre_tor / tor_review / active / pending / awarded / cancelled
  ├── project_type                      # NEW: ก่อสร้าง / วัสดุ / บริการ / อุปกรณ์ / IT
  ├── construction_subtype              # NEW: ถนน / อาคาร / สะพาน / ระบบน้ำ / ปรับปรุง
  ├── budget_tier                       # NEW: micro(<500K) / small(<5M) / medium(<20M) / large(20M+)
  ├── urgency_tier                      # NEW: critical(<3d) / soon(<7d) / normal(<30d) / planning(>30d)
  ├── method_id                         # NEW: e-bidding / เฉพาะเจาะจง / etc.
  ├── sme_suitable                      # NEW: bool (จาก criteria + budget)
  ├── geographic_precision              # NEW: precise(district) / province / region / national
  ├── unspsc_family                     # NEW: 4-digit UNSPSC family code
  ├── document_complexity               # NEW: simple / standard / complex (จาก attached docs count)
  └── win_probability_per_customer      # NEW: derived per request
```

### Per-customer ranking score:
```
score = w1 * keyword_match
      + w2 * area_match (district > province)
      + w3 * budget_fit (within customer's range)
      + w4 * type_match (ก่อสร้างถนน?)
      + w5 * urgency_bonus
      + w6 * historical_win_rate_similar_jobs
      + w7 * sme_advantage
```

---

## 5. Implementation Phases

### Phase 1: Add classification columns (~1-2 ชม.)
- เพิ่ม column ใน all_jobs: `project_type`, `construction_subtype`, `budget_tier`, `urgency_tier`, `method_id`, `sme_suitable`
- Backfill จาก existing data (PDF + getProjectDetail)
- Postgres schema migration

### Phase 2: Rule-based classifier (~2-3 ชม.)
- **Construction sub-type** keyword classifier
  - ถนน: keyword "ถนน", "คอนกรีตเสริมเหล็ก", "ลาดยาง", "ก่อสร้างทาง"
  - อาคาร: "อาคาร", "ปรับปรุงอาคาร", "สำนักงาน"
  - สะพาน: "สะพาน", "ทางเชื่อม"
  - ระบบน้ำ: "ประปา", "ระบบส่งน้ำ", "บ่อบาดาล", "เขื่อน"
  - ปรับปรุง: "ปรับปรุง", "ซ่อมแซม"
- **Budget tier**: parse จาก PDF (₫ราคากลาง)
- **Urgency**: คำนวณจาก deadline - today
- **method_id**: จาก getProjectDetail
- **SME flag**: จาก criteria (มี "เฉพาะ SME" หรือไม่)

### Phase 3: AI Deep Search (Claude API) (~3-4 ชม.) ⭐
**G-LEAD's killer feature — เราทำได้แล้ว เพราะเรามี PDF**
- Download TOR + BOQ PDF
- Send to Claude API with structured prompt:
  ```
  จากเอกสาร TOR/BOQ:
  - ประเภทงาน?
  - วัสดุหลัก?
  - คุณสมบัติผู้เสนอราคา?
  - ค่าผ่านเกณฑ์ (qualifications)?
  - ความซับซ้อน 1-5?
  - SME suitable?
  ```
- เก็บผลใน `ai_classified` column (JSON)

### Phase 4: UNSPSC mapping (~2-3 ชม.)
- Build lookup table CMC → UNSPSC สำหรับวัสดุก่อสร้าง
- Match จาก keyword ใน project title → UNSPSC family
- Future: cross-reference กับ CGD list

### Phase 5: Per-customer ranking (~2-3 ชม.)
- เพิ่ม `customer_preferences` table:
  - budget_min, budget_max
  - project_types (multi-select)
  - construction_subtypes (multi-select)
  - urgency_preference (ชอบงานเร่งด่วน?)
  - sme_only (bool)
- Compute score per (customer, job) pair
- ส่ง LINE notify เรียง score สูงสุดก่อน

---

## 6. Quick Win: ลำดับความสำคัญ

| Phase | Effort | Impact | ทำเมื่อ |
|---|---|---|---|
| 1. Add columns | 1-2 ชม. | Foundation | **NEXT** |
| 2. Rule-based | 2-3 ชม. | High (ใช้ได้ทันที) | **NEXT** |
| 3. AI Deep Search | 3-4 ชม. | Killer ⭐ | หลัง HTTP-only migration |
| 4. UNSPSC mapping | 2-3 ชม. | Nice-to-have | Phase 3 SaaS |
| 5. Per-customer | 2-3 ชม. | Stickiness ↑ | หลังมีลูกค้า > 5 ราย |

**Total: ~10-15 ชม.** กระจาย 3-4 session

---

## 7. Strategic Differentiator vs G-LEAD

| มิติ | G-LEAD | Bid Master (proposed) |
|---|---|---|
| Lifecycle | ✅ | ✅ ครบเหมือนกัน |
| Multi-filter (budget/area/type) | ✅ | ✅ (Phase 1-2) |
| AI Deep Search on TOR/BOQ | ✅ | ✅ (Phase 3 — Claude API) |
| Competitor data | ✅ | ✅ (getProcureResult — เหนือกว่า) |
| Per-customer ranking | ❌ | ✅ (Phase 5 — เด่นกว่า) |
| Construction sub-typing | ⚠️ ทั่วๆ ไป | ✅ ละเอียดกว่า (ถนน/อาคาร/...) |
| UNSPSC mapping | ⚠️ ไม่แน่ใจ | ✅ planned |
| Push notification by score | ❌ | ✅ LINE notify ที่ filter ละเอียด |

→ **เหนือกว่าด้วย: per-customer ranking + construction sub-type + LINE-first delivery**

---

## 8. Caveats / Risk

1. **AI Deep Search cost** — Claude API ~$0.003 per page × ~3-5 pages = $0.01-0.02/job × 10K jobs/day = $100-200/day ❗ — ต้องเลือก analyze เฉพาะ job ที่ตรงกับ customer
2. **UNSPSC mapping** — รัฐบาลไม่มี public API → ต้องสร้าง table เอง
3. **Schema migration** — เพิ่ม column 8-10 อัน → backfill 8,796 rows ใช้เวลานาน (parallel processing)
4. **Customer preferences UI** — ต้องสร้างหน้า `/customer/[id]/preferences` (form ซับซ้อนขึ้น)

## 9. References

- [G-LEAD Filtering](https://lightworkai.com/glead-egp-difference/)
- [G-LEAD AI Deep Search](https://lightworkai.com/ai-deep-search-gprocurement/)
- [Thai eGP UNSPSC Portal](https://www.gprocurement.go.th/wps/portal/egp/UNSPSC)
- [UNSPSC Official](https://www.unspsc.org/)
- existing: `docs/rss_full_replacement_research.md` (HTTP-only เปิดทางให้ AI Deep Search ทำได้)
