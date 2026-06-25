# Design: แจ้งเตือน + แสดงงานยกเลิกโครงการ (Cancelled Project Notification)

**วันที่:** 2026-06-25
**สถานะ:** approved (design) → รอ implementation plan

---

## ที่มา (Problem)

พ่อของคุณกัญจน์เห็นงานที่ **ถูกยกเลิกโครงการแล้ว** ค้างอยู่ในกลุ่ม **"สรุปราคาเบื้องต้น"** บน Web Board และอยากให้ระบบ **แจ้งเตือนเมื่อมีงานถูกยกเลิก**

### Root cause
Lifecycle ฝั่ง Product DB / Board คือ `B0 → D0 → PRELIM → W0` — **ไม่มี stage "ยกเลิก"** Board (`scripts/bms_api.py:406-481`) จัดกลุ่มงานที่ติดตามตาม `last_stage_notified`:

| กลุ่มบน Board | เงื่อนไข |
|---|---|
| 🟢 ประกาศผู้ชนะ | มี winner / stage W0 |
| 📊 สรุปราคาเบื้องต้น | `last_stage_notified == "PRELIM"` |
| 🔵 ประกาศวันยื่นซอง | `announce == "D0"` |
| (เตรียม) | อื่นๆ |

ผลคือ:
1. ไม่มีใครตรวจสถานะยกเลิกของงานที่ติดตามอยู่
2. งานที่เคยขึ้น PRELIM แล้วโครงการถูกยกเลิกทีหลัง **ค้างในกลุ่มสรุปราคาเบื้องต้นตลอดไป**
3. ระบบ notification event-centric ไม่มี stage แจ้งยกเลิก

> หมายเหตุ: legacy Sheets (`Sebastian_Classifier.py`) ตรวจยกเลิกได้อยู่แล้ว แต่ logic นั้น **ไม่ถูกพอร์ตมาฝั่ง DB / Board / notification**

---

## ขอบเขต (Scope — ยืนยันกับ user)

- **ทำทั้งคู่:** แจ้งเตือนยกเลิก **+** แก้ Board ให้งานยกเลิกออกจาก "สรุปราคาเบื้องต้น"
- **ตรวจทุก stage:** B0 / D0 / PRELIM (ทุก active follow ไม่ใช่แค่ D0+PRELIM)

---

## สถาปัตยกรรม

เพิ่ม stage `CANCELLED` เข้า lifecycle โดย **piggyback บน winner-poller** (timer ~6 ชม. ที่มีอยู่) — ไม่สร้าง pipeline / cron ใหม่

### 1. Predicate ยกเลิก (shared — กัน logic แตก)

Extract ออกจาก `Sebastian_Classifier.py` (logic ที่ `classify_by_stepid` บรรทัด 153-168 + LETTER_TO_SHEET "B" บรรทัด 139) เป็นฟังก์ชันใหม่:

```python
def is_cancelled(step_id: str, project_status_raw: str, announce_type: str) -> tuple[bool, str]:
    """คืน (cancelled, note). 3 สัญญาณ:
       - projectStatus == "R"            (gold)
       - announce_type in ("D1", "W1")   (secondary — ลงท้าย "1")
       - step_id ขึ้นต้น "B"             (Block stage)
       note = จุดที่ยกเลิก (เช่น "ยกเลิกระหว่างยื่นซอง (S01)")
    """
```

`classify_by_stepid` เรียกใช้ `is_cancelled` แทน inline logic เดิม (พฤติกรรมเดิมต้องไม่เปลี่ยน — มี test ยืนยัน)

### 2. Detection — cancellation pass ใหม่ใน `Sebastian_Winner_Poller.py`

- เพิ่ม pass **ก่อน** prelim/formal pass — วน **ทุก** active follow (B0/D0/PRELIM)
- เรียก `get_project_detail(pid)` (มีอยู่แล้ว `process5_http_client.py:221`) ครั้งเดียวต่อ pid → `step_id`, `project_status_raw`, `announce_type`
- ตัดสินด้วย `is_cancelled(...)`
- ถ้ายกเลิก → ต่อแต่ละ follow บน pid นั้น:
  - `enqueue_for_customer(cid, {..., "source_stage": "followed_cancelled", "cancel_note": note})` (mode == "live")
  - `mark_stage_notified(cid, pid, "CANCELLED")`
  - `close_follow(pid, cid)` — หยุด poll
- dedup key `(customer, project, "followed_cancelled")` กันแจ้งซ้ำ ([[project_event_centric_queue]])
- pid ที่ยกเลิกแล้ว → **ลบออกจาก** by_pid / prelim_by_pid ก่อนรัน pass ถัดไป (ประหยัด API + ไม่แจ้งซ้อน)
- mode != "live" → shadow log เท่านั้น (เหมือน prelim/winner pass)
- ใช้ `POLL_SLEEP_SEC` cooldown ต่อ pid (INC-001 discipline)

### 3. Notification — การ์ด LINE

`Sebastian_LINE_Sender.py` render source_stage `followed_cancelled`:

```
❌ โครงการถูกยกเลิก
[ชื่องาน]
📍 จ.[province]
[cancel_note]
```

วิ่งผ่าน queue → delivery_log → **digest เดิม** (`Sebastian_Backlog_Digest.py`) → ช่วง LINE quota เต็มถูกรวมส่งใน digest 1 ก.ค. อัตโนมัติ (idempotent — ไม่ต้องแก้อะไรเพิ่ม)

### 4. Board — กลุ่ม "ยกเลิก" ใน `bms_api.py`

- เพิ่ม `groups["cancelled"]`
- ใน grouping loop (รอบ ~451) **เช็ค `lsn == "CANCELLED"` เป็นอันดับแรกสุด** (ก่อน won/prelim/bidding) → เข้า `cancelled`, ไม่หล่นไปกลุ่มอื่น
- เพิ่ม render section `❌ ยกเลิกโครงการ` + badge ที่ **ล่างสุด** ของ board (won → prelim → bidding → pre → cancelled)

### 5. Backfill งานที่ค้างปัจจุบัน

**ไม่ต้องเขียน backfill แยก** — งานที่ยกเลิกแล้วค้างใน PRELIM/D0 จะถูก cancellation pass จับใน **รอบ poll แรกหลัง deploy** เอง (pass วนทุก active follow)

---

## Data flow

```
winner-poller (timer ~6h)
  └─ cancellation pass (ทุก active follow B0/D0/PRELIM)
       └─ get_project_detail(pid) → is_cancelled?
            ├─ yes → enqueue followed_cancelled + mark CANCELLED + close_follow
            │         └─ LINE_Sender การ์ด ❌ → queue → delivery_log → digest
            │         └─ Board: lsn=CANCELLED → กลุ่ม "ยกเลิกโครงการ"
            └─ no  → คงอยู่ → prelim/formal pass ตามเดิม
```

---

## Error handling

- `get_project_detail` ล้มเหลว/ว่าง → log + ข้าม pid นั้น (ไม่ถือว่ายกเลิก — fail-safe ไม่ false-cancel)
- enqueue ซ้ำ → dedup key กันเอง
- mode != "live" → shadow log, ไม่เขียน DB

---

## Tests (TDD)

| Test | ตรวจ |
|---|---|
| `is_cancelled` | 3 สัญญาณ (R / D1,W1 / B*) + negative (ปกติ → False) + note ถูกต้องตาม stage |
| `classify_by_stepid` regression | พฤติกรรมเดิมไม่เปลี่ยนหลัง extract |
| poller cancellation pass | mock detail=cancelled → enqueue followed_cancelled + mark CANCELLED + close + **skip** winner/prelim poll ของ pid นั้น |
| poller fail-safe | get_project_detail error → ไม่ false-cancel |
| board grouping | lsn=CANCELLED → อยู่ cancelled group, **ไม่อยู่** prelim |

### Success criteria (verifiable)
- `is_cancelled` ผ่านทุก case (R/D1/W1/B* = True, ปกติ = False)
- mock cancelled pid → queue มี row `source_stage=followed_cancelled`, follow ปิด, ไม่มี getProcureResult call
- board: job lsn=CANCELLED ไม่ปรากฏใน `groups["prelim"]`, ปรากฏใน `groups["cancelled"]`

---

## ตัดออก (YAGNI)

- ❌ ไม่สร้าง cron/timer ใหม่ — ใช้ winner-poller เดิม
- ❌ ไม่สร้างตารางเก็บ cancel reason — note inline ใน enqueue payload (เหมือน prelim)
- ❌ ไม่แตะ legacy Sheets classifier behavior (พอร์ตเฉพาะ predicate ออกมา reuse)
- ❌ ไม่ทำ auto-hide งานยกเลิกบน board (แสดงค้างไว้ให้เห็น — ตัดสินภายหลังถ้าจำเป็น)

---

## ไฟล์ที่กระทบ

| ไฟล์ | การเปลี่ยนแปลง |
|---|---|
| `scripts/Sebastian_Classifier.py` | extract `is_cancelled()`, ให้ `classify_by_stepid` เรียกใช้ |
| `scripts/Sebastian_Winner_Poller.py` | cancellation pass ใหม่ ก่อน prelim/formal |
| `scripts/Sebastian_LINE_Sender.py` | render การ์ด `followed_cancelled` |
| `scripts/bms_api.py` | กลุ่ม `cancelled` + render section บน board |
| `scripts/test_*.py` | tests ตามตารางด้านบน |
