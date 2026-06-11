# Deprecate Sheet Pipeline — Decommission Plan

> **สถานะ:** DRAFT รอ กัญจน์ review (เขียนระหว่างกัญจน์นอน 2026-06-12 กลางคืน)
> **กฎ:** แผนนี้ยัง **ไม่ลงมือรื้ออะไร** — ทุก phase มี gate ให้ยืนยันก่อน. การตัด pipeline = reversible เท่านั้น (disable ก่อน, ลบทีหลัง)

**Goal:** เลิกพึ่ง Google Sheets pipeline (มรดกเดิม) โดย**ไม่กระทบ product จริง** (LINE/portal/pricing บน VPS SQLite)

---

## 1. สิ่งที่ค้นพบ (มีหลักฐาน) — ระบบเรามี 2 โลกแยกกัน

| | 🟢 โลก Product (ลูกค้าเห็น) | 🟡 โลก Sheet (มรดก) |
|---|---|---|
| Source of truth | SQLite `bms_customers.db` (VPS) | Google Sheet `all_jobs` |
| Ingestion | RSS/province → SQLite ตรง (`Enrichment_Worker`, `process5_http_client` = **0 sheet refs, db-only**) | GHA `pipeline_daily.yml` → scrape → `all_jobs` sheet |
| Process | `job_matcher` (0 sheet refs) → notification_queue | `Sebastian_Classifier` อ่าน all_jobs → เขียน 6 view sheets |
| Delivery | `Sebastian_LINE_Sender` + `bms_api` (portal) อ่าน sqlite | `dashboard_extractor` อ่าน 6 sheets → snapshot.json |
| Consumer | **ลูกค้าจริง** | **คนดูเอง (กัญจน์)** |

**ข้อสรุป:** customer-facing path เป็น SQLite ล้วน ฝั่ง matching/enrichment/delivery **ไม่มี sheet ref เลย** → โลก Sheet ตัดได้โดยไม่กระทบลูกค้า **ถ้า**ยืนยันว่าไม่มี job-flow ลอดจาก sheet เข้า product DB (ดู Gate 0)

---

## 2. ⚠️ จุดเสี่ยงที่ต้องเคลียร์ก่อน (Open Questions — กัญจน์ตอบ)

| # | คำถาม | ทำไมสำคัญ |
|---|---|---|
| Q1 | `etl_sheet_to_db.py` (Sheet→DB) **รันบน cron/timer ไหน หรือเป็น one-shot จริง?** | docstring บอก "one-shot Phase A" แต่ถ้ามันอยู่บน timer = product อาจกินข้อมูลจาก sheet → ตัดไม่ได้ |
| Q2 | กัญจน์ **ยังเปิดดู 6 view sheets** (active_bidding ฯลฯ) ด้วยตาเองไหม? | ถ้าดู = ต้องมี replacement (portal/dashboard) ก่อนตัด |
| Q3 | **Analytics sheets** (Work-Type, Market Size, Competitor Trend) — ยังใช้ทำ research/ตั้งราคาไหม? | พวกนี้เป็นเครื่องมือ research มีคุณค่า — อาจ **เก็บไว้** ไม่ตัด |
| Q4 | ยอมให้ portal dashboard ย้ายไปอ่าน SQLite แทน sheet (แทน `dashboard_extractor`) ไหม? | dashboard ปัจจุบันพึ่ง 6 sheets |

> **Order Sheet (BSC คำสั่งจอง, คนละ spreadsheet) = ไม่แตะเด็ดขาด** — แยกระบบ

---

## 3. การจัดกลุ่ม script ที่แตะ Sheet (จาก grep 51 จุด)

| กลุ่ม | scripts | ชะตากรรมที่เสนอ |
|---|---|---|
| **6-view writer** | `Sebastian_Classifier.py` (write 6 sheets + writeback all_jobs) | ปิด sheet-write (เก็บ logic classify ไว้ได้) |
| **all_jobs ingestion** | `cgd_discovery.py`, `migrate_to_all_jobs.py`, `patch_deadlines.py`, `fetch_bid_history.py` | หยุด GHA ที่เรียก (ดู Phase 1) |
| **analytics writers** | `_work_type_sheet`, `_market_size_sheet`, `_competitor_share_sheet`, `_trend_sheet`, `_my_company_sheet`, `_winner_history_summary` | **รอ Q3** — น่าจะเก็บ (research tool) |
| **one-shot backfill** | `backfill_*.py`, `create_calc_sheet`, `create_new_sheets` | dead อยู่แล้ว — ลบทีหลังได้ ไม่เร่ง |
| **readers (รวม Sophia tools)** | `dashboard_extractor`, `audit_all_sheets`, `coverage_audit`, `audit_pending` | repoint ไป SQLite (สอดคล้องกับ Sophia ที่เพิ่ง refocus) |
| **ETL bridge** | `etl_sheet_to_db.py` | **รอ Q1** ยืนยันก่อน |

---

## 4. แผนปฏิบัติ — Staged & Reversible

### Gate 0 — พิสูจน์ independence (บังคับก่อนเริ่ม)
- [ ] ตอบ Q1: เช็ค VPS crontab/systemd timers ว่าไม่มี `etl_sheet_to_db` / `Sebastian_Classifier` / `pipeline_daily`
- [ ] ยืนยัน job ที่เข้า notification_queue มาจาก RSS/province ingestion (SQLite) ไม่ใช่จาก all_jobs sheet
- [ ] **dispatch Sophia**: ตรวจว่า product DB (notification_queue) ป้อนตัวเองได้ ไม่พึ่ง sheet
- ✋ **ไม่ผ่าน Gate 0 = หยุด** ทั้งหมด รายงานกัญจน์

### Phase 1 — ปิดสวิตช์ (ไม่ลบโค้ด, reversible 100%)
- [ ] Disable GHA `pipeline_daily.yml` (sheet pipeline) — `git mv` เป็น `.yml.disabled` หรือ comment `on:` trigger
- [ ] เพิ่ม env flag `BMS_SHEET_WRITE=off` ใน `Sebastian_Classifier` → ถ้า off ข้าม `write_sheet()` ทั้ง 6
- [ ] commit + **สังเกต 3-7 วัน**: product (LINE/portal) ทำงานปกติไหม, มีใครบ่นว่า sheet ไม่อัปเดตไหม
- เกณฑ์ผ่าน: ลูกค้าได้งานครบ + กัญจน์ไม่ติดขัดจาก sheet หาย

### Phase 2 — ย้าย reader ที่ยังจำเป็น (ตาม Q2/Q4)
- [ ] ถ้ากัญจน์ยังต้องดูสถานะงาน → ทำ portal view อ่าน SQLite แทน (หรือยืนยันว่า portal ปัจจุบันพอแล้ว)
- [ ] repoint `dashboard_extractor` metrics จาก sheet → SQLite

### Phase 3 — ลบโค้ดจริง (หลัง observe ผ่าน + กัญจน์ approve)
- [ ] ลบ/archive 6-view writer + one-shot backfill scripts
- [ ] เก็บ analytics writers ตาม Q3
- [ ] อัปเดต CLAUDE.md (ตัด section Sheets ออกจาก Domain Rules) + Sophia (เอา sheet tool ออกถ้าไม่ใช้แล้ว)

---

## 5. สิ่งที่ **จะไม่ทำ** (กันพลาด)
- ❌ ไม่ลบโค้ดใน Phase 1 (แค่ disable) — กันกรณีต้อง rollback
- ❌ ไม่แตะ Order Sheet (BSC)
- ❌ ไม่ตัด analytics sheets จนกว่า Q3 ตอบ
- ❌ ไม่รัน `etl_sheet_to_db.py` หรือ classifier เต็มบน prod ระหว่างทดสอบ (เขียนทับ sheet/DB จริง)

---

## 6. ขั้นถัดไปเมื่อกัญจน์ตื่น
1. ตอบ Q1-Q4 (ส่วนใหญ่ผมหาคำตอบ Q1 ได้เองถ้าให้ ssh เช็ค VPS timers)
2. อนุมัติ Gate 0 → ผมเริ่ม Phase 1 (disable + observe)
3. ถ้าอยากให้ลงรายละเอียดเป็น task-by-task plan (TDD-style) ค่อยแปลงเป็น implementation plan เต็ม
