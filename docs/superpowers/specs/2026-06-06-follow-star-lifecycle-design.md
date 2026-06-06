# ⭐ Follow/Star — Lifecycle Tracking + Winner & Competitive Intel — Design Spec

**วันที่:** 2026-06-06 · **สถานะ:** approved (กัญจน์) → เขียน plan ต่อ

## Goal (1 ประโยค)
แทนระบบ feedback 👍/🤔/👎 (พ่อแม่กดเล่น = noise) ด้วย **⭐ ติดดาว = ติดตามงานตลอดชีวิต** — แจ้งเมื่องานที่ติดตามเปิดประมูล (B0→D0) และเมื่อประกาศผู้ชนะ (→W0) พร้อมราคาคู่แข่งทุกราย + เก็บลง DB เป็น competitive intelligence

## Why
- feedback ปัจจุบัน (👍/🤔/👎) = พ่อแม่ "กดลองดู" → ไม่ใช่สัญญาณจริง (ดู [[project_matching_design]] INC-002 note)
- ⭐ = intent จริง ("ฉันสนใจงานนี้") → ได้ North-Star metric ที่เชื่อได้ + คุณค่าจริง (ติดตามผล + รู้ว่าใครชนะ/ราคาเท่าไร = competitive edge ที่เคยวิจัยไว้ [[project_classifier_research]] G-LEAD differentiator)
- lifecycle: projectId เดียวกันข้าม stage B0→D0→W0 (พิสูจน์แล้ว discovery probe 2026-06-06)

## Non-goals (YAGNI)
- ไม่แจ้ง transition อื่นนอกจาก เปิดประมูล + ผู้ชนะ (ไม่เอา deadline-reminder/cancelled ในเวอร์ชันนี้ — กัญจน์เลือก)
- ไม่ทำ web UI สำหรับ watchlist (LINE อย่างเดียว)
- ไม่ migrate feedback เก่า

---

## UX (LINE flex card)
ทุกการ์ดงานเปลี่ยน postback buttons เป็น **2 ปุ่ม**:
- **⭐ ติดตามงานนี้** → follow (intent จริง)
- **❌ ไม่เกี่ยว** → feedback(action=irrelevant) ปรับ matching (คงสัญญาณ negative ไว้)

(เอา 👍สนใจ / 🤔ไม่น่าสน / 👎ไม่เกี่ยว เดิมออก — `FB_ACTIONS` ใน Sebastian_LINE_Sender)

⭐ กดได้ทุกงานที่ส่ง (ทั้ง B0 รับฟังคำวิจารณ์ และ D0 ประมูล). ❌ กับ ⭐ เป็น action อิสระบนการ์ด.

---

## Data Model

### ตารางใหม่ 1: `followed_jobs` (watchlist)
```
customer_id        INTEGER   -- ใครติดตาม
project_id         TEXT      -- งานที่ติดตาม
starred_at         TEXT      -- เวลา ติดดาว
starred_stage      TEXT      -- stage ตอนติดดาว (B0/D0)
last_stage_notified TEXT     -- stage ล่าสุดที่แจ้งแล้ว (B0/D0/W0) — dedup กันแจ้งซ้ำ
status             TEXT      -- active | closed (ได้ผู้ชนะแล้ว/ยกเลิก/หมดเวลา)
UNIQUE(customer_id, project_id)
```

### ตารางใหม่ 2: `bid_results` (competitive intel — เก็บถาวร)
1 row = 1 bidder ต่องาน (จาก getProcureResult):
```
project_id, bidder_name, bidder_tin, price_proposal, price_agree,
is_winner (priceAgree != null), is_sme, result_flag, fetched_at
UNIQUE(project_id, bidder_tin)
```
> เก็บทุกงานที่ดึง result (ไม่เฉพาะติดดาว) → คลังวิเคราะห์งานหน้า. reuse logic จาก `fetch_bid_history.fetch_procure_result()` (แตก bidders ครบ + priceProposal ต่อราย — confirmed มีจริง)

### reuse: `feedback` table เดิม
❌ → `feedback(action='irrelevant', project_id, customer_id)` (ไม่เปลี่ยน schema)

---

## Flow (lifecycle 3 จุด)

### 1. ติดดาว (star)
postback `star:<project_id>` → upsert `followed_jobs(customer_id, project_id, starred_at, starred_stage=ann_type, last_stage_notified=ann_type, status='active')` → reply "⭐ ติดตามงานนี้แล้ว จะแจ้งเมื่อเปิดประมูล/ประกาศผู้ชนะ"

### 2. B0 → D0 (เปิดประมูล)
- discovery ingest D0 ของ projectId อยู่แล้ว (ทุกรอบ)
- เพิ่ม hook: หลัง ingest D0 → ถ้า project_id อยู่ใน `followed_jobs` (status=active, last_stage_notified='B0') → enqueue แจ้ง "⭐ งานที่ติดตาม **เปิดประมูลแล้ว**" + deadline (resolve ปกติ) → set last_stage_notified='D0'
- *(ถ้าติดดาวตอน D0 อยู่แล้ว = ข้ามจุดนี้ ไป W0)*

### 3. D0/B0 → W0 (ประกาศผู้ชนะ) ⭐ ส่วนหลัก
- **winner poller** (timer ใหม่, รอบห่างๆ เช่น ทุก 6 ชม.): หา followed_jobs status=active ที่ควรมีผลแล้ว (เลย deadline / announce นานพอ) → เรียก getProcureResult(project_id)
  - มีผล (มี bidders + winner) → (a) เก็บ `bid_results` ทุก bidder, (b) แจ้ง "⭐ **ประกาศผู้ชนะ**: [winner] ฿[price_agree] · คู่แข่ง: A ฿.., B ฿..", (c) set last_stage_notified='W0', status='closed'
  - ยังไม่มีผล → คงไว้ลองรอบหน้า
  - **stop condition**: ถ้า >60 วันหลัง starred_at ยังไม่มีผล (ประกาศผู้ชนะอาจช้าหลายสัปดาห์-เดือน หลังปิดยื่นซอง) หรือ งานยกเลิก → status='closed' (เลิก poll กัน loop). ค่าปรับได้ env `BMS_WINNER_POLL_MAX_DAYS`=60
- rate-limit: poll เฉพาะ followed jobs (set เล็ก) + รอบห่าง + cooldown (INC-001 discipline)

---

## Components (ไฟล์)
- `Sebastian_LINE_Sender.py` — เปลี่ยน buttons (⭐/❌), postback labels
- `bms_api.py` — postback handler: `star:` → followed_jobs · `irrelevant:` → feedback (มี handler เดิม ปรับ)
- `Sebastian_Customer_DB.py` — migrate: + `followed_jobs`, `bid_results` tables + helper (add_follow, get_active_follows, record_bid_results)
- `Sebastian_Province_Discovery.py` **หรือ** enrichment hook — detect B0→D0 transition ของ followed jobs → enqueue
- `Sebastian_Winner_Poller.py` (ใหม่) — poll getProcureResult สำหรับ followed jobs → notify + store. reuse `fetch_bid_history.fetch_procure_result`
- systemd: `bms-winner-poller.timer` (ทุก ~6 ชม.)

---

## ⚠️ Open verification (ทำใน plan ก่อนสร้าง Phase 2)
getProcureResult ตอนนี้เรียกผ่าน **Playwright browser** (`fetch_bid_history` page.evaluate). poller บน VPS ต้อง verify ว่าเรียกได้ด้วย **AES-token ตรง** (egp_token_investigation: AES key RDCrypto, getProcureResult ทำงานได้) — ถ้าได้ = poller เบา; ถ้าไม่ = ต้องใช้ browser path. **probe ก่อนสร้าง poller**

---

## Phasing
- **Phase 1** (เบา, ส่งคุณค่าเร็ว): ⭐/❌ buttons + `followed_jobs` + B0→D0 notify (reuse discovery) + reply. = watchlist + lifecycle ต้น ใช้ได้ทันที
- **Phase 2** (หนักกว่า): verify getProcureResult-via-token → `bid_results` table + Winner_Poller + winner notify (winner+คู่แข่ง+ราคา) = competitive intel

---

## Edge cases
- ติดดาวงานที่ W0 แล้ว (มีผลอยู่แล้ว) → poller รอบถัดไปเจอผล → แจ้งทันที (ไม่ต้อง special-case)
- งานติดดาวถูกยกเลิก (D1/status R) → poller เจอ → status='closed' ไม่แจ้งผู้ชนะ (อาจแจ้ง "ยกเลิก" = future)
- พ่อติดดาวงานเดียวกับที่ ❌ ก่อน → ⭐ ชนะ (intent ใหม่ทับ)
- dedup ส่ง: last_stage_notified กันแจ้งซ้ำ stage เดิม

## Testing (TDD)
- followed_jobs upsert + dedup (unit)
- B0→D0 transition detection (followed + last=B0 → trigger; ไม่ followed → ไม่ trigger)
- bid_results extraction (reuse fetch_bid_history — test กับ getProcureResult sample จริง)
- winner-poller stop condition (เลย N วัน → closed)
- format winner notification (pure)

## North-Star impact
⭐ count + "ติดดาวตอน B0 แล้วตามจนจบ" = สัญญาณ engagement จริง (แทน tap เล่น) → วัด North-Star ได้จริง
