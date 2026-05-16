# New Classifier Logic — Implementation Plan

**Status:** 📋 PLANNED (ยังไม่ implement — รอ user confirm)
**Based on:** `docs/egp_stepid_catalog.md` (research 2026-05-16, 277 samples)
**Will fix:** Bug 1 (cancelled-in-active), Bug 2A (deadline-passed-in-active), Bug Q7-9 (M03 misclassified as tor)

---

## 🎯 Decision Logic (stepId-driven)

```python
def classify(detail: dict, winner_in_cache: bool) -> str | None:
    """
    detail = response จาก getProjectDetail (มี stepId, flowSeqno, projectStatus, announceType)
    winner_in_cache = bool — มี winner ใน winner_cache_bootstrap.json ไหม

    Returns: sheet name หรือ None (skip — ไม่ขึ้นที่ไหน)
    """
    step     = (detail.get("stepId") or "").upper()
    status   = detail.get("projectStatus", "")
    announce = detail.get("announceType", "")

    # 1) Cancelled — Skip
    if status == "R" or announce in ("D1", "W1"):
        return None
    # 2) Has winner — Awarded
    if winner_in_cache:
        return "awarded_jobs"
    if not step:
        return "pending_award"  # ไม่มี stepId → safe fallback

    # 3) Letter-prefix-driven (with specific override for M03)
    prefix = step[0]
    if prefix == "U":   return "tor_review"        # U03, U06 = consulting
    if prefix == "M":   return "active_bidding"    # M03 = TOR-final → ⭐ Q7-9 fix
    if prefix in "SZ":  return "active_bidding"    # S01, Z01, Z03 = bidding
    if prefix in "WCIE X":  # หมายเหตุ: WCIEX no space
        return "pending_award"                     # W01/W03/C01/C03/I03/E03/X01/X03
    if prefix == "Q":   return None                # Q01/Q03 = early prep
    if prefix == "B":   return None                # B01/B03 = cancelled block

    # 4) Unknown stepId — log + safe fallback
    log_warning(f"Unknown stepId: {step}")
    return "pending_award"
```

⚠️ **หมายเหตุ:** บรรทัด `if prefix in "WCIEX"` ในจริงต้องเขียน `if prefix in ("W","C","I","E","X")` ที่ปลอดภัย

---

## 📋 Implementation Steps

### Step 1: เพิ่ม stepId/projectStatus/announceType ลง all_jobs schema
**File:** `scripts/Sebastian_Classifier.py`, `Sebastian_Scraper.py`, `refresh_active_jobs.py`

ปัจจุบัน all_jobs มี 15 columns — ยังไม่มี stepId เลย เพราะเดิมใช้ project_status text เป็นหลัก

**ทางเลือก A:** เพิ่ม 3 columns ใหม่ลง all_jobs:
- `step_id` (M03, U03, S01, ฯลฯ)
- `project_status_raw` (A/R)
- `announce_type` (D0/W0/D1/W1/BOQ ฯลฯ)

ต้อง:
- เพิ่มใน ALL_JOBS_HEADERS
- Scraper เก็บ field พวกนี้ตอน scrape
- Refresh เก็บ field พวกนี้ตอน refresh
- Classifier อ่าน fields นี้แทน text status

**ทางเลือก B:** ดึง 3 fields นี้ on-demand ใน refresh + เก็บใน winner_cache pattern (ไฟล์แยก)

→ **แนะนำ A** (clean schema, queryable, future-proof)

### Step 2: แก้ Scraper เก็บ 3 fields ใหม่
**File:** `scripts/Sebastian_Scraper.py`

eGP search API ส่ง flowSeqno + flowName มา ไม่ส่ง stepId/projectStatus/announceType
→ ต้องเรียก getProjectDetail ต่อใน Scraper สำหรับงานใหม่ทุกอัน

**Trade-off:** ช้าขึ้น (1 extra request per new job) แต่ได้ data ครบ
**Alternative:** Scraper ทิ้ง fields นี้ว่าง → refresh จะเติมในรอบถัดไป

→ **แนะนำ Alternative** (ไม่ช้า scrape; refresh handle ในรอบถัดมา)

### Step 3: แก้ Refresh เก็บ + ตรวจ cancellation
**File:** `scripts/refresh_active_jobs.py`

- เก็บ stepId, projectStatus, announceType ลง all_jobs (เพิ่ม 3 columns)
- เพิ่ม cancellation check: `projectStatus="R"` OR `announceType in ("D1","W1")` → set project_status="ยกเลิก"
- Mark cancelled jobs → SKIP ใน Classifier

### Step 4: เขียน Classifier ใหม่ (stepId-driven)
**File:** `scripts/Sebastian_Classifier.py`

แทน `_normalize_project_status()` ด้วย `classify_by_stepid()`:
- ใช้ logic ด้านบน
- คง compat: ถ้า stepId ว่าง (rows เก่าที่ยังไม่ refresh) → fallback to project_status text mapping เดิม

### Step 5: Migration — refresh ทุก row ใน all_jobs
ครั้งเดียว — รัน refresh บนทุก row ที่ไม่มี stepId
- 8,690 rows × 1.5s = 3.6 ชั่วโมง ... 😬 เยอะไป
- **Alternative:** refresh เฉพาะ active + tor + pending = ~30-50 jobs (5 นาที)
- งานเก่าๆ ปล่อยไว้ rebuild ตามรอบ (ทุกครั้งที่ user ดูสนใจ scrape ใหม่)

→ **แนะนำ:** refresh แค่ active + tor + pending (~50 jobs) — ปลอดภัย + เร็ว

### Step 6: Tests + Verify
- 5 Q7-9 jobs: 69049365887, 69049011449, 69049235336 → ต้องไป active_bidding
- 69059074818, 69059075123 → คงอยู่ tor_review
- 4 active jobs: 69049234631, 69049094319, 69049219653, 69049223058 → คงอยู่ active (พวก deadline ผ่านอาจย้ายไป pending ถ้า refresh มา stepId=W01/W03)
- Cancelled jobs: ตรวจไม่มี projectStatus="R" หลุดเข้า active

### Step 7: re-scrape ทุก row (Bug 2A — tor_url empty)
**File:** `scripts/Sebastian_Scraper.py`

ปัญหา: active jobs deadline ว่างเพราะ tor_url ว่าง (มาจาก migration)
**Fix:** รัน Scraper ใหม่ทั้งหมด → ทุก row จะได้ tor_url + Scraper จะ upsert (overwrite tor_url ที่ว่าง)
- ใช้เวลา 30-60 นาที
- patch_deadlines ครั้งเดียวเสร็จ → deadline ครบ

หรือ Skip Step 7 ตอนนี้ — รอ scrape รอบ next cron 06:00

### Step 8: Commit + Document
- Commit: "Redesign Classifier: stepId-driven 4-sheet lifecycle"
- Update progress_log.md

---

## 🔄 Migration Order (recommended)

```
1. [code] Add 3 columns to all_jobs (step_id, project_status_raw, announce_type)
2. [code] Update refresh_active_jobs.py — เก็บ + check cancellation
3. [code] Rewrite Classifier — stepId-driven
4. [run]  Refresh active + tor + pending (~50 jobs) — เติม fields ใหม่
5. [run]  Run Classifier — verify ผล
6. [run]  ตรวจ 5 Q7-9 + 4 active + sample cancelled
7. [run]  (Optional) Re-scrape ทุก row → patch_deadlines
8. [git]  Commit
```

---

## ❓ Open Questions (ต้องการ user confirm)

### Q1: Sheet structure ตอนนี้ดีไหม?
- ปัจจุบัน 4 sheets: tor_review / active_bidding / pending_award / awarded_jobs
- **คงเดิม** หรือ split เพิ่ม? (เช่น แยก "งานเก่า > 6 เดือนไม่ขยับ" ออก)

### Q2: Q01/Q03 (early prep) แสดงไหม?
- ตอนนี้ proposed = SKIP (ไม่ขึ้นที่ไหน)
- **ทางเลือก:** เพิ่ม sheet "pre_tor" สำหรับ Q stage (= early warning ก่อน TOR review)
- หรือ ใส่ tor_review ก็ได้ (เริ่มสนใจตั้งแต่เนิ่นๆ)

### Q3: Cancelled jobs แสดงไหม?
- ตอนนี้ proposed = SKIP (อยู่ใน all_jobs เฉยๆ)
- **ทางเลือก:** เพิ่ม sheet "cancelled" — ดูประวัติ + เห็นว่าหน่วยงานไหนยกเลิกบ่อย

### Q4: Refresh frequency?
- Pipeline 06:00 → refresh ทุก active_bidding (ปัจจุบัน 4-9 jobs)
- **ทางเลือก:** เพิ่ม refresh ทุก tor_review + pending_award ด้วย (rare แต่ catch winners)

### Q5: Re-scrape ทุก row หรือไม่ (Step 7)?
- ทำ → tor_url + deadline ครบใน 1 ครั้ง
- ข้าม → รอรอบ next cron (อาจค่อยๆ ดี)

---

## 🚨 Rollback Plan

ถ้าผิดพลาด:
1. **Revert code** — `git revert <commit-sha>` ของ commit ใหม่
2. **Restore all_jobs** — มี backup ใน `backups/all_jobs_pre_smart_migrate/` (ของ migration ก่อนหน้า) + อาจสร้าง backup ใหม่ก่อน step 4
3. **Restore winner cache** — backup `data/winner_cache_bootstrap.json` ก่อน

→ ก่อน implement ควร **backup all_jobs + winner_cache** ลง JSON ใหม่ก่อน

---

## 📈 Expected Outcome (after full implementation)

| Sheet | Now | After New Logic | Δ Reason |
|---|---:|---:|---|
| 🟢 tor_review | 8 | **5-8** | คงเดิม (M03 ที่ผิดอยู่ tor → ย้ายไป active) |
| 🔵 active_bidding | 4 | **~10-15** | +M03 jobs (Q7-9 + อื่นๆ ที่ปิดรับฟังแล้ว) |
| 🟡 pending_award | 25-30 | **~15-25** | ลดลง (cancelled ออก + บางตัวไป awarded หลัง refresh) |
| ⚪ awarded_jobs | 295 | **~295+** | ค่อยๆ เพิ่มตาม refresh winners |
| SKIP (cancelled) | (เห็นใน all_jobs) | (ชัดเจน) | จัดการชัดด้วย projectStatus=R |

---

## 🎓 Lessons จาก Research

1. **stepId คือ signal ที่ละเอียดที่สุด** — ดีกว่า flowSeqno เพราะแยก sub-state ได้ (M03 vs U03)
2. **projectStatus="R"** = gold standard สำหรับ cancellation
3. **announceType "1" suffix** = secondary cancellation signal (90% accuracy)
4. **flowId** = stage family — useful for grouping แต่ไม่จำเป็นใน classifier
5. **ไม่มี document endpoint แยก** — tor_url ที่ Scraper เก็บอยู่แล้ว = sufficient
6. **Letter-prefix fallback** = ทำให้ระบบ resilient ต่อ stepId ใหม่

---

# 🚀 Phase B — bid_history Feature (Future Roadmap)

**Status:** 📋 PLANNED — ทำหลัง Phase A (classifier) verified แล้ว
**Estimated:** ~55 นาที
**Decision date:** 2026-05-16

## Why หลัง Phase A?

1. **Foundation first** — bid_history ดึงข้อมูลให้ jobs ที่ classifier จัดเรียบร้อยแล้ว
2. **Risk isolation** — แก้แยก commit → rollback ง่าย
3. **Refresh complexity** — Phase A เพิ่ม 1 API call/job, Phase B เพิ่มอีก 1 → ทำที่หลังกัน controllable
4. **Verifiable** — user ดู Phase A ก่อนว่าใช้ได้ไหม ก่อนต่อ Phase B
5. **Value sequence** — Phase A แก้ bug urgent, Phase B เพิ่ม feature important-not-urgent

## Schema ใหม่ — `bid_history` sheet

```
1 row = 1 bidder ต่อ 1 job (1 awarded job มี 2-10 rows)
```

| column | source field | meaning |
|---|---|---|
| `job_id` | projectId | FK to awarded_jobs |
| `bidder_name` | receiveNameTh | ชื่อบริษัท |
| `bidder_tin` | receiveTin | เลขผู้เสียภาษี (unique ID) |
| `price_proposal` | priceProposal | ราคาเสนอ |
| `price_agree` | priceAgree | ราคาตกลง (มีเฉพาะผู้ชนะ) |
| `result_flag` | resultFlag | P/N/W |
| `is_winner` | (priceAgree != null) | derived |
| `is_sme` | (scoreTypeId == "SME") | derived |
| `is_joint_venture` | (jointVentureAndConsortiumsResponseList) | derived |
| `consider_desc` | considerDesc | คำอธิบายงาน |

## เพิ่มใน awarded_jobs (1 row = 1 job):

- `announce_date` — วันประกาศผู้ชนะ
- `report_date` — วันรายงานผล
- `deliver_day` — จำนวนวันส่งมอบ
- `project_cost_type` — C=เกณฑ์ราคา / Q=คุณภาพ
- `min_quality_score` — คะแนนคุณภาพขั้นต่ำ
- `num_bidders` — จำนวนผู้เสนอราคา

## 6 Use Cases — Competitive Intelligence

1. **Competitor Profile** — บริษัทไหนชนะบ่อย, อะไรถนัด, win rate
2. **Pricing Intelligence** — ราคาตลาด, % discount เฉลี่ย, ช่วงราคา
3. **Win Probability** — จำนวนคู่แข่งเฉลี่ย → predict win prob
4. **Market Share & Trends** — top winners, ใหม่/หาย, market dynamics
5. **Joint Venture Network** — ใครเป็น partner ใคร
6. **SME Advantage** — งานที่มี SME bonus → strategy ต่าง

## Implementation Effort

| งาน | เวลา |
|---|---|
| สร้าง bid_history sheet | 5 นาที |
| เพิ่ม 6 fields ใน awarded_jobs | 10 นาที |
| Update refresh — parse procureResult ครบ | 20 นาที |
| Migration — refresh 295 awarded → ดึง bid history | 10 นาที |
| Verify + tests | 10 นาที |
| **รวม** | **~55 นาที** |

## SaaS Vision Tie-in

นี่เป็น **premium feature** ที่ลูกค้าจะอยากจ่าย:
- ตอนนี้: SaaS = LINE notify รายวัน (basic)
- + bid_history: **Competitive Intelligence Dashboard** (premium)
- = strong moat — competitors ขายแค่ "list งาน" ของเรามี "ข่าวกรองตลาด"
