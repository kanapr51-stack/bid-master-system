# Runbook — CGD Winner Refresh (residential node)

> เติม winner ย้อนหลังจาก CGD Open Data เข้า `data/winner_history.db` แบบ incremental
> auto-ingest ปีงบใหม่ (FY2569…) ทันทีที่ DGA publish. **ต้องรันบน residential IP** — CGD/data.go.th ส่ง **403 จาก VPS** (datacenter block).

## โครงสร้าง CGD จริง (probe 2026-06-06)
- 1 package ต่อปีงบ: `egp-contact-{ปีพ.ศ.}` (เช่น `egp-contact-2568`) — ปีที่ยังไม่ publish → HTTP 404
- แต่ละ package มี ~10 resources: `{year}-egp-contract-1..10`
- วันที่จริง = field `วันที่เกิดรายการ` (`'9 ก.ค. 68'` เว้นวรรค); `วันที่ประกาศ` ส่วนใหญ่ `'-'`
- **lag ปกติ ~8-9 เดือน** (publish ทีละปีงบที่จบแล้ว — ไม่ real-time). CGD = ผู้ชนะ**ย้อนหลัง** ไม่ใช่ winner สด

## องค์ประกอบ
| ไฟล์ | หน้าที่ |
|---|---|
| `scripts/cgd_resource_catalog.py` | `resource_ids_for_year(year)` → list rids (404→[], 403/quota→raise) |
| `scripts/cgd_winner_refresh.py` | `refresh_year(db, year, rids, provinces)` + `main()` — incremental INSERT OR IGNORE |
| `scripts/cgd_freshness.py` | `report(year=)` วัด lag + `parse_thai_date` |
| `scripts/_run_cgd_winner_refresh.ps1` | wrapper (log → `logs/cgd/`, rotate 7, ไม่ push git) |

token: `.env` → `OPEND_USER_TOKEN`. quota CGD ~1000 calls/วัน (แชร์กับ cgd_discovery + winner_sweep); refresh 2 จว.×10 res ≈ 20-40 calls

## Schedule (เครื่องบ้าน — Windows Task Scheduler)
- **Task:** `BidMaster_CGD_Winner_Refresh` — daily **21:30** (กัน quota/เวลากับ `BidMaster_CGD_Discovery` 05:00)
- รันมือ: `Start-ScheduledTask -TaskName BidMaster_CGD_Winner_Refresh`
- ดู log: `logs/cgd/winner_refresh_*.log` · ผลล่าสุด: `(Get-ScheduledTaskInfo -TaskName BidMaster_CGD_Winner_Refresh).LastTaskResult` (0=OK)
- register ใหม่ (ถ้าหาย): ดู `New-ScheduledTaskAction/Trigger` pattern เดียวกับ task อื่น, action = `powershell.exe -File _run_cgd_winner_refresh.ps1`

## ย้ายลง mini PC x86 (อนาคต — core เป็น Python ล้วน OS-agnostic)
- copy repo + `.env` (OPEND_USER_TOKEN) ลงเครื่อง residential ใหม่
- Linux/cron: `30 21 * * * cd /path/bms && python3 scripts/cgd_winner_refresh.py >> logs/cgd/refresh.log 2>&1`
- ไม่ต้องแก้ logic — เปลี่ยนแค่ scheduler (Task Scheduler ↔ cron). ห้ามย้ายลง VPS (403)

## ปรับจังหวัด/ปี
แก้ default ใน `cgd_winner_refresh.main(years=, provinces=)` หรือเรียก `main(years=["2569"], provinces=["นครพนม","บึงกาฬ","..."])`

## Rollback (Phase 1)
หยุด: `Disable-ScheduledTask -TaskName BidMaster_CGD_Winner_Refresh`. ข้อมูลเป็น additive (INSERT OR IGNORE, PK project_id) — ไม่แก้/ลบ row เดิม

---

# Phase 2 — sync subset → VPS (`cgd_winners`)

ป้อน competitive intel ใน LINE: ผู้ชนะพื้นที่เป้าหมาย (นครพนม+บึงกาฬ) จาก `winner_history.db` → VPS `bms_customers.db` table `cgd_winners`.

> หมายเหตุ: `winner_history.db` ปัจจุบันมี**เฉพาะ นครพนม+บึงกาฬ** (build จาก target provinces) → subset = ทั้ง DB (~617K, 2558-2568).

## องค์ประกอบ
| ที่ | หน้าที่ |
|---|---|
| `Sebastian_Customer_DB._migrate_v119` | สร้าง `cgd_winners` (12 col) บน VPS |
| `cgd_sync_to_vps.py` | `extract_subset` (residential) · `merge_winners`/`get_cgd_winners` (VPS) · main `--push`/`--merge-from` |

## รัน sync (เครื่องบ้าน → VPS)
```
python scripts/cgd_sync_to_vps.py --push
```
flow: `extract_subset(winner_history.db)` → เขียน `data/cgd_subset.jsonl.gz` → scp → ssh ให้ VPS `--merge-from` (stream + executemany batch 5000, INSERT OR REPLACE idempotent)

env override: `VPS_HOST` (root@45.76.156.166), `VPS_KEY` (~/.ssh/bms_vps), `BMS_REMOTE_DATA` (/opt/bms/data), `BMS_REMOTE_PY` (/opt/bms/venv/bin/python), `BMS_REMOTE_APP` (/opt/bms/app)

## deploy code ใหม่ขึ้น VPS
`git push origin main` → VPS: `cd /opt/bms/app && git pull --ff-only` → migrate: `sudo -u bms BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "import sys;sys.path.insert(0,'/opt/bms/app/scripts');import Sebastian_Customer_DB as db;db.init_schema()"`

## verify บน VPS
```
sudo -u bms BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "import sys;sys.path.insert(0,'/opt/bms/app/scripts');import cgd_sync_to_vps as s;print(len(s.get_cgd_winners('นครพนม')))"
```

## ⚠️ Followup (ยังไม่ทำ)
- **sync incremental** — ตอนนี้ `--push` extract ทั้ง 617K ทุกครั้ง (361MB→gzip). ยังไม่ schedule รายวัน. ถ้าจะ schedule ต้องทำ incremental (เฉพาะ project_id ใหม่/ปีล่าสุด) กัน re-push ก้อนใหญ่
- ป้อน feature competitive intel ใน line-sender (query `cgd_winners` by area + work-type)

## Rollback (Phase 2)
`DROP TABLE cgd_winners` บน VPS (additive, ไม่กระทบ Follow/Winner Poller — คนละตาราง). backup ก่อน migrate: `bms_customers_pre_v119_*.db`
