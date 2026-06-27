# Ongoing Bidder Capture — Design Spec

**วันที่:** 2026-06-27
**สถานะ:** approved (design), รอเขียน implementation plan
**Scope:** เก็บผู้ยื่นทุกราย ทุกงาน **หลังจากนี้** ในนครพนม + บึงกาฬ (ทุก proc_type รวมเฉพาะเจาะจง)

---

## 1. เป้าหมาย & ขอบเขต

สะสม `bid_results` (ผู้ยื่นทุกราย + ราคา ต่องาน) ของงานใน **นครพนม + บึงกาฬ** แบบ ongoing —
ไม่ใช่ backfill งานเก่าที่มีอยู่แล้ว แต่เก็บงานที่ "โผล่เข้ามาหลังวัน deploy" เป็นต้นไป

**ครอบคลุม:** ทุก proc_type (e-bidding / สอบราคา / คัดเลือก / **เฉพาะเจาะจง**)

**ไม่ทำ (out of scope):**
- ไม่ backfill 617K แถวเก่าใน cgd_winners
- ไม่ขยายนอก 2 จังหวัด (national = followup คนละงาน)
- ไม่แก้ `winner_poller` (followed + แจ้งเตือน — คนละหน้าที่)
- ไม่ retire `bms-backfill-bidders.timer` ในงานนี้ (drain history จนเสร็จค่อย disable แยก)

### Success criteria (verifiable)
1. หลัง deploy: `bid_results` ได้แถวใหม่จากงานที่ award **หลัง** epoch โดยไม่มีแถวจากงานเก่ากว่า epoch
2. `bid_results.source` แยกได้ชัด `'procure_api'` vs `'cgd_copy'`
3. งานเฉพาะเจาะจงใหม่ → ได้ 1 แถว (ผู้ชนะ = ผู้ยื่นรายเดียว) โดย**ไม่เรียก getProcureResult**
4. รันซ้ำ idempotent — ไม่มี duplicate (project_id, bidder_tin)
5. ไม่ทำ `winner_poller` / `backfill_bidders` พัง (bid_results ยังถูกต้อง, ไม่ double-write)

---

## 2. ที่มาของข้อมูล — ทำไมต้อง 2 pass

ความต้องการ 2 ข้อชนกัน: **"รวมเฉพาะเจาะจง"** + **"สด (หลังจากนี้)"**

| แหล่ง | เฉพาะเจาะจง? | ความสด | สถานะ |
|---|---|---|---|
| discovery → `projects_seen` | ❌ ไม่เห็น (เจาะจงไม่มีขั้นเชิญชวน) | ✅ near-real-time | มีอยู่แล้ว (province discovery 2×/วัน) |
| CGD → `cgd_winners` | ✅ ครบ | ❌ lag ~8-9 เดือน | sync จาก residential (ดู runbook cgd-refresh) |

→ ใช้ทั้งคู่: Pass 1 เก็บแข่งสด, Pass 2 เติมเฉพาะเจาะจง (+ แข่งที่ Pass 1 พลาด) ทีหลัง

> **หมายเหตุความซื่อสัตย์:** Pass 2 *กลไก*ไม่ใช่ backfill (ไม่ไล่ของเก่าที่มี) แต่ *เนื้อข้อมูล*เป็นของย้อนหลังเพราะ CGD lag — ยอมรับตามที่เคาะกับ user

---

## 3. สถาปัตยกรรม

โมดูลใหม่ `scripts/ongoing_bidder_capture.py` — รันบน VPS (projects_seen / cgd_winners / getProcureResult / bid_results อยู่ VPS หมด ไม่มี cross-node)

ใช้ helper ของ `backfill_bidders.py` ซ้ำ (loop, cooldown, seen-set, fail-open) — ไม่ก็อปลอจิก

### Pass 1 — LIVE (discovery-driven)
```
projects_seen (province IN [นครพนม,บึงกาฬ], first_seen_at ≥ epoch, NOT IN bid_results)
  ฟิลเตอร์ "พร้อมมีผล" → getProcureResult → มี bidders → record_bid_results(source='procure_api')
  ไม่มีผล → ปล่อยรอบหน้า
```
- **ความพร้อม (readiness):** `projects_seen` **ไม่มี deadline/stepId** → ใช้ heuristic ช่วงอายุ `first_seen_at`:
  poll เฉพาะงานอายุ ≥ MIN_AGE_DAYS (ยังไม่ award ถ้าใหม่เกิน) และ ≤ MAX_AGE_DAYS (เลิก poll กัน loop)
  ค่าเริ่ม: MIN=7, MAX=90 (ปรับได้ตอน plan)
- rate discipline: sleep 1.5s + cooldown 130s/25 งาน (เหมือน backfill — INC-001)

### Pass 2 — CGD-FILL (completeness รวมเฉพาะเจาะจง)
```
cgd_winners (province IN [นครพนม,บึงกาฬ], NOT IN bid_results, epoch floor)
  proc_type = เฉพาะเจาะจง/ไม่แข่ง → คัดลอกผู้ชนะเป็น bidder เดียว (source='cgd_copy', ไม่เรียก API)
  proc_type ∈ COMPETITIVE_SET (Pass 1 พลาด) → getProcureResult (source='procure_api')
                                              → ถ้า API ล้ม fallback copy winner (source='cgd_copy')
```
- **คัดลอก (copy path):** สร้าง bidder dict สังเคราะห์จาก cgd_winners:
  `bidder_name=winner`, `price_proposal=price_agree=win_price`, `is_winner=1`,
  `bidder_tin` = winner_tin เพี้ยน ~99% (ดู memory winner_tin_corruption) → ใช้ **name-fallback key** (`record_bid_results` มีอยู่แล้ว line 1026)
- `proc_type` มีใน cgd_winners (ยืนยันจาก index `_migrate_v134`)

---

## 4. Schema change

`_migrate_v136`: เพิ่มคอลัมน์ `source TEXT` ใน `bid_results`
- ค่า: `'procure_api'` (จาก getProcureResult) | `'cgd_copy'` (คัดลอกจาก cgd_winners)
- backfill แถวเก่า: NULL (ไม่ต้องเดา; แถวเก่าทั้งหมดมาจาก getProcureResult อยู่แล้ว — ถ้าจะให้ครบ set NULL→'procure_api' แบบ resumable)
- แก้ `record_bid_results(..., source='procure_api')` รับ+เขียนคอลัมน์นี้ (INSERT OR REPLACE เขียนทั้งแถว → ต้องส่งทุกครั้ง กันค่าหาย เหมือนเคส normalized_name v135)

---

## 5. Idempotency, resumable, state

- **กันซ้ำ 2 ชั้น:** `NOT IN bid_results` (SQL ตัดงานที่เก็บแล้ว) + `INSERT OR REPLACE` PK (project_id, bidder_tin)
- **seen-set แยกต่อ pass:** `data/ongoing_capture_seen_live.json`, `..._cgd.json` (กัน re-poll งาน empty)
- **epoch:** persist `data/ongoing_capture_state.json` — ตั้งครั้งแรก = วัน deploy. เป็นเส้นแบ่ง "ไม่ backfill"
  - Pass 1 floor: `first_seen_at ≥ epoch_date` (first_seen_at เป็น ISO timestamp เทียบได้)
  - Pass 2 floor: `CAST(fiscal_year AS INTEGER) ≥ epoch_fy` (ปีงบไทย ณ deploy)
    - ⚠️ **ทำไมไม่ใช้ announce_date/synced_at:** `cgd_winners.announce_date` เป็น Thai date (`'9-เม.ย.-67'`) เทียบ ISO ไม่ได้; `synced_at` รีเซ็ตหมดทุก full re-push (617K — ดู runbook cgd-refresh followup). `fiscal_year` ทนต่อ full-re-push (key=project_id ไม่ใช่เวลา sync) + ตัดปีเก่าได้ตรง
    - state file: `{"epoch_date": "YYYY-MM-DD", "epoch_fy": <int>}` (epoch_fy = `backfill_bidders.current_fy()`)

---

## 6. Scheduling & ความสัมพันธ์กับของเดิม

- systemd timer ใหม่ `bms-ongoing-bidder-capture` — รายวัน **03:00** (หลัง backfill 02:00, หลัง discovery)
- coexist กับของเดิมผ่าน `NOT IN bid_results` (idempotent ร่วมกัน):
  - `winner_poller` (00,06,12,18:15) — followed + แจ้งเตือน → ไม่แตะ
  - `bms-backfill-bidders` (02:00) — competitive history drain → ไม่แตะ; งานที่มันเก็บแล้วถูกตัดด้วย NOT IN
- Discord: จบรอบส่งสรุป `stored / copied / empty / error` ต่อ pass

---

## 7. Followup (นอก scope งานนี้)

- VPS `cgd_winners` sync ให้ **incremental + schedule รายวัน** (ตอนนี้ manual full re-push) → ทำให้ `synced_at` ใช้เป็น floor ได้ + เฉพาะเจาะจงเข้าเร็วขึ้น
- ขยาย national (77 จว.) — รอ scale decision

---

## 8. Test plan (TDD)

- `test_ongoing_capture.py`:
  - Pass 1: mock get_procure_result → งานในจังหวัด+อายุในช่วง → stored(source=procure_api); งานเก่ากว่า epoch → ข้าม; งานนอกจังหวัด → ข้าม; ไม่มี bidders → empty (mark seen)
  - Pass 2: เฉพาะเจาะจง → copied(source=cgd_copy, ไม่เรียก API); competitive ที่ยังไม่มีใน bid_results → API; API ล้ม → fallback copy
  - idempotent: รัน 2 รอบ → row count เท่าเดิม, ไม่มี duplicate
  - epoch floor: งาน announce_date < epoch / first_seen_at < epoch → ไม่ถูกแตะ
- `record_bid_results` source column: เขียน/อ่านค่าถูก, INSERT OR REPLACE ไม่ทำ source หาย
