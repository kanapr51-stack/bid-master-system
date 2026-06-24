# Bid-Open Reminders — Design Spec (2026-06-24)

**Goal:** แจ้งลูกค้าว่ามีงาน "เปิดประมูล" (วันยื่นซอง = วันเป้าหมาย) ในพื้นที่ของเขา
- **เช้า 07:00 น.** — งานที่ยื่นซอง **วันนี้**
- **สรุปเย็น (ย้าย 20:00 → 23:00 น.)** — เพิ่ม section งานที่ยื่นซอง **พรุ่งนี้**

## นิยาม (ยืนยันกับกัญจน์ 2026-06-24)
- **"เปิดประมูล"** = `bid_submit_date` (วันยื่นซอง) == วันเป้าหมาย
- **scope** = งานในพื้นที่ที่ระบบเคย match ให้ลูกค้า = distinct `project_id` ใน `delivery_log` (customer_id, `is_test_data=0`)
- เวลาเช้า = 07:00 ไทย (00:00 UTC) · สรุปเย็น = 23:00 ไทย (16:00 UTC)
- build เลยแม้ LINE quota เต็ม → timer รัน live, ระหว่าง quota เต็มได้ 429 (log, ไม่พัง), ส่งจริงหลัง upgrade

## Components

### 1. `scripts/bid_open.py` (ใหม่, pure-ish, testable)
```
bid_open_for_customer(conn, customer_id: int, target_date: str) -> list[dict]
```
- `target_date` = "YYYY-MM-DD"
- query: distinct project ใน delivery_log (customer, non-test) JOIN projects_seen + project_locations + project_enrichments
- deadline = `COALESCE(project_locations.deadline, project_enrichments.bid_submit_date)`,
  time = `COALESCE(project_locations.deadline_time, project_enrichments.bid_submit_time)`
- กรอง `substr(deadline,1,10) == target_date`
- คืน `[{project_id, name, deadline, deadline_time}]` (เรียงตามชื่อ) — graceful: ตารางหาย/DBError → คืน `[]`

### 2. `scripts/Sebastian_BidOpen_Morning.py` (ใหม่)
- วน customers active → `bid_open_for_customer(today_th)`
- **ถ้า ≥1 งาน** → `send_line_push`: `🔔 วันนี้มีงานเปิดประมูล N งาน` + รายการ (ชื่อ / ⏰ เวลา / ลิงก์ /portal/job ผ่าน follow_token) + ลิงก์ board
- **0 งาน → ไม่ส่ง** (เลี่ยง spam เช้า + ประหยัด quota)
- `--dry-run` preview เฉยๆ · ใช้ `_load_line_token` + `send_line_push` (เหมือน Daily_User_Summary)

### 3. `scripts/Sebastian_Daily_User_Summary.py` (แก้)
- เพิ่ม section ต่อท้ายข้อความ: `bid_open_for_customer(tomorrow_th)` → ถ้ามี → "📅 พรุ่งนี้มีงานเปิดประมูล M งาน:" + รายการ
- คง heartbeat เดิม (นับ matched วันนี้จาก delivery_log) ไว้ครบ

### 4. systemd (VPS)
- เปลี่ยน `bms-daily-user-summary.timer`: `OnCalendar` 13:00 → **16:00 UTC**
- เพิ่ม `bms-bidopen-morning.timer` (00:00 UTC) + `.service` (รัน Sebastian_BidOpen_Morning.py)

## Testing (TDD)
- `test_bid_open.py`: มีงาน target / ไม่มี / ข้ามวัน (deadline คนละวัน) / non-test filter / table หายไม่พัง
- morning: ข้อความมีรายการ+ลิงก์ เมื่อมีงาน · 0 งาน → ส่งคืน 0 (ไม่ push)
- summary: มี section "พรุ่งนี้" เมื่อมีงาน · ไม่มี → ไม่โผล่ · heartbeat เดิมไม่พัง

## ไม่ทำ (YAGNI)
- ไม่ทำ province-wide (ใช้ delivery_log ตามที่ยืนยัน) · ไม่แตะ pipeline/queue · ไม่ทำ flex card (text ธรรมดาเหมือน summary เดิม)
