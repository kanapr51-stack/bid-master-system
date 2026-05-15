# Sheet Redesign Plan — 2026-05-15

> **Resumable blueprint.** ID Claude อื่นอ่านไฟล์นี้ได้เลย แล้วทำต่อจาก phase ที่ค้างใน `progress_log.md`

## ปัญหา

- Sheet 17 ตัว — มี duplicate (raw_jobs vs raw_jobs_all, cost_data vs cost_data_By_Dexter), legacy (ranked_jobs, job_specs), และ test (dashboard)
- Schema ไม่ consistent: `publish_date` (eng) vs `วันที่ประกาศ` (ไทย); `เหลือเวลา` vs `เกินกำหนด`
- Classifier ทำงานครึ่ง ๆ กลาง ๆ — งาน e-bidding ที่หมด deadline ค้างใน `active_bidding` (เห็น 7 งานหมดอายุ -1 ถึง -77 วัน)
- ไม่มี reset cycle — append + dedup ทำให้ data drift
- ความน่าเชื่อถือของ sheet ตกหนัก

## การตัดสินใจ (จาก user 2026-05-15)

| คำถาม | คำตอบ |
|---|---|
| Backup | ผ่าน Google Sheets (export) — แต่ SA ติด quota → ใช้ local JSON dump แทน + user copy ใน Drive UI ได้ |
| `tor_review` | **เก็บไว้** (รื้อต่อ Phase 2 SaaS) |
| Migration | **Big bang** — ล้างทั้งหมด + rebuild from scratch (มี .json backup จาก scraper เดิม + local dump) |
| Scraper write | Scraper เขียน `all_jobs` อย่างเดียว → Classifier rebuild ชีท derived |

## โครงสร้างใหม่ (จาก 17 → 6 ชีท + tor_review reserved)

```
AUTO-MANAGED (Pipeline rebuild ทุก run)
├── all_jobs           Source of Truth — Scraper upsert ที่นี่ที่เดียว
├── active_bidding     e-bidding + deadline >= today  ← ชีทหลัก LINE
├── pending_award      e-bidding + deadline < today + ยังไม่ประกาศผู้ชนะ
└── awarded_jobs       ประกาศผู้ชนะแล้ว + winner data

MANUAL (ของพ่อ — ห้ามแตะ)
├── calc_road          ชีทคำนวน W/L/T
└── cost_data_By_Dexter สูตรต้นทุน

RESERVED
└── tor_review         เก็บไว้สำหรับ Phase 2 SaaS

ลบทิ้ง (11 ชีท):
raw_jobs, raw_jobs_all, raw_jobs_bidding, raw_jobs_related,
raw_jobs_direct, raw_jobs_cancelled, raw_jobs_awarded,
job_specs, ranked_jobs, cost_data, dashboard
```

## Schema unified

### `all_jobs` (Source of Truth)

| col | name | type | note |
|---|---|---|---|
| A | job_id | string PK | จาก eGP projectId |
| B | title | string | |
| C | department | string | |
| D | province | string | |
| E | district | string | |
| F | subdistrict | string | |
| G | procurement_type | enum | e-bidding / เฉพาะเจาะจง / etc |
| H | budget | number | |
| I | publish_date | date | dd/mm/yyyy พ.ศ. |
| J | deadline | date | dd/mm/yyyy พ.ศ. — วันยื่นซอง (อาจว่าง ถ้ายังไม่มี D0) |
| K | project_status | string | raw จาก eGP flowName |
| L | search_keyword | string | คำที่ scrape เจอ |
| M | tor_url | string | ถ้ามี |
| N | first_seen_at | datetime ISO | scrape ครั้งแรกเมื่อไหร่ |
| O | last_seen_at | datetime ISO | scrape ล่าสุดเมื่อไหร่ |

### `active_bidding` (derived)
ทุก column ของ `all_jobs` + เพิ่ม:
| col | name | type |
|---|---|---|
| P | days_remaining | int | (deadline - today) คำนวณตอน rebuild |

### `pending_award` (derived)
ทุก column ของ `all_jobs` + เพิ่ม:
| col | name | type |
|---|---|---|
| P | overdue_days | int | (today - deadline) |

### `awarded_jobs` (derived)
ทุก column ของ `all_jobs` + เพิ่ม:
| col | name | type |
|---|---|---|
| P | winner_name | string | |
| Q | winner_price | number | |
| R | discount_pct | number | (budget - winner_price) / budget * 100 |
| S | award_date | date | dd/mm/yyyy พ.ศ. |

## Classifier State Machine

```python
def classify_all_jobs():
    today = today_th()  # พ.ศ.
    rows = read_all_jobs()
    active, pending, awarded = [], [], []

    for r in rows:
        if r.procurement_type != "e-bidding":
            continue  # อยู่ใน all_jobs อย่างเดียว
        if r.has_winner:
            awarded.append(r)
        elif r.deadline and r.deadline >= today:
            active.append(r)
        else:
            pending.append(r)  # หมด deadline แต่ยังไม่ประกาศ

    clear_and_write("active_bidding", active)
    clear_and_write("pending_award", pending)
    clear_and_write("awarded_jobs",  awarded)
```

## Phases (resumable)

| # | Phase | Files / Outcome | Resume |
|---|---|---|---|
| 1 | ✅ Backup | `backups/sheets_2026-05-15_2046/*.json` | ดู folder มี 17 ไฟล์หรือยัง |
| 2 | 🔄 Blueprint | `docs/sheet_redesign_plan.md` (ไฟล์นี้) + `progress_log.md` checkpoint | ดูไฟล์ + log entry |
| 3 | Sheet `all_jobs` | สร้าง sheet ใหม่ + headers row 1 | `gspread.worksheet("all_jobs")` ไม่ throw |
| 4 | Migrate data | merge backups → write all_jobs | row count > 0 |
| 5 | Scraper | rewrite `Sebastian_Scraper.py` write หลัก = all_jobs | grep "all_jobs" found |
| 6 | Classifier | rewrite `Sebastian_Classifier.py` state machine | function `classify_all_jobs()` exists |
| 7 | Patch consumers | LINE_Notify / Winner_Checker / patch_deadlines อ่าน schema ใหม่ | grep update |
| 8 | Delete legacy | ลบ 11 ชีทเก่า | `list_sheets()` length = 6 |
| 9 | Test E2E | run scraper + classifier + verify counts | 3 sheets ทำงานได้ |

## รายละเอียดเทคนิค

### Source-of-truth principle
- Scraper เขียน `all_jobs` ตัวเดียว — upsert by `job_id`
- ทุก `last_seen_at` = current scrape timestamp
- `first_seen_at` = ค่าเดิมถ้ามี / current ถ้าใหม่
- Classifier **อ่าน all_jobs → clear+write 3 derived sheets** (atomic ผ่าน `batch_clear` + `batch_update`)

### Date handling
- ในชีท: dd/mm/yyyy พ.ศ. (เช่น 18/05/2569)
- ในโค้ด: parse เป็น date object พ.ศ., เปรียบเทียบ today() ใน พ.ศ.
- helper: `parse_thai_date(s) -> date_th`, `today_th() -> date_th`

### Backup info
- Local: `C:\Bid-Master-System\backups\sheets_2026-05-15_2046\`
- Drive: user ทำเองได้ 1 คลิก — File → Make a copy

### Spreadsheet ID
- `1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps`
- Service account: `bid-master-sheets@bid-master-sheets.iam.gserviceaccount.com`
- Owner email: `kanapr51@gmail.com`

## Files ที่จะแก้

| File | เปลี่ยนอะไร |
|---|---|
| `scripts/Sebastian_Scraper.py` | ตัด `append_jobs_to_sheet` เป็น append หลายชีท → upsert `all_jobs` ตัวเดียว |
| `scripts/Sebastian_Classifier.py` | rewrite state machine ตามข้างบน |
| `scripts/Sebastian_LINE_Notify.py` | อ่าน `active_bidding` schema ใหม่ (ไม่เปลี่ยนมาก) |
| `scripts/Sebastian_Winner_Checker.py` | เขียน `awarded_jobs` schema ใหม่ — เพิ่ม discount_pct |
| `scripts/patch_deadlines.py` | อ่าน `all_jobs` แทน `active_bidding`/`raw_jobs` |
| `scripts/create_new_sheets.py` | obsolete — ลบหรือ rename |
| `run_pipeline.bat` | ไม่ต้องแก้ (เรียก scripts เดิม) |
