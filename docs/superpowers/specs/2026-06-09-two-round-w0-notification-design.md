# Two-Round W0 Notification + Detailed Analysis — Design (Sub-project 1)

**วันที่:** 2026-06-09
**สถานะ:** approved design (รอ user review spec → writing-plans)

## Problem

งานที่ลูกค้าติดตาม เมื่อประมูลจบ — ระบบเดิมตรวจผู้ชนะจาก `getProcureResult` (ผลทางการ, priceAgree) **อย่างเดียว** ซึ่ง lag ตามหลัง "สรุปข้อมูลการเสนอราคาเบื้องต้น" (ราคาต่ำสุดที่เสนอ, เปิดเผย ~เที่ยงวันเดียวกัน) เป็นวันๆ → ลูกค้าที่ติดตามไม่ได้รู้ผลทันเวลา (เคสจริง 69059075454: เห็นราคาต่ำสุด 740,000 เปิดเผย 12:02 แต่ระบบไม่แจ้ง).

**Root cause (debug 2026-06-09):** ไม่ใช่ bug — follow/poller/mode ถูกหมด, แค่ไม่มีแหล่งข้อมูลเร็ว. RE สำเร็จ: ดึงสรุปราคาเบื้องต้น pure-API ได้ (ดู `docs/research/2026-06-09-prelim-bid-summary-api.md`).

## Goal

แจ้งงานที่ติดตาม **2 รอบ** (กัญจน์เลือก Option C):
- **Round 1 (เบื้องต้น):** ทันทีที่สรุปราคาเปิดเผย — ราคาต่ำสุด + closed-loop เทียบ prediction (provisional)
- **Round 2 (เต็ม):** เมื่อผู้ชนะทางการออก — การ์ดผู้ชนะ + วิเคราะห์ละเอียด (breakdown ต่อราย + closed-loop authoritative)

ทั้งสองรอบ **เทียบ prediction เทียบจาก "กรอบบนของราคา" เสมอ**.

## Out of scope (Sub-project 2 / later)
- **Competitor Trend Learning Loop** (เก็บผล observe → เทรนด์ส่วนลดต่อบริษัท → feed กลับ prediction). Sub-1 อ่านประวัติจาก `cgd_winners` ที่มีอยู่ (read-only) ไม่สร้าง learning store.
- **ขยายการเตือนคู่แข่งใน D0 เกิน top-3** — คง `SHOW_N=3` ใน D0 (กัญจน์ยืนยัน). Sub-1 แค่โชว์ gap ใน Round 2.

---

## Architecture

ขยาย `Sebastian_Winner_Poller` เดิม (ไม่สร้าง poller ใหม่) — reuse stage-machine + closed-loop + delivery queue + LINE sender ที่มีอยู่.

```
followed_jobs (active)
   │  last_stage_notified: D0 ─► PRELIM ─► W0
   ▼
Winner_Poller (timer ทุก 2 ชม.)
   ├─ follow @ D0      → fetch_prelim_summary(pid)  ─มี─► Round 1 enqueue + mark PRELIM
   └─ follow @ D0|PRELIM → get_procure_result(pid)  ─มีผู้ชนะ─► Round 2 enqueue + mark W0 + close
   ▼
notification_queue (source_stage = followed_prelim | followed_winner)
   ▼
Sebastian_LINE_Sender → format Round 1 / Round 2 → ส่ง LINE
```

---

## Components

### 1. `scripts/prelim_summary.py` (ใหม่)
ดึง + parse "สรุปข้อมูลการเสนอราคาเบื้องต้น" (API chain พิสูจน์แล้ว, ดู research doc).

```
fetch_prelim_summary(pid) -> dict
  { "has_summary": bool,       # มี announceType 'price' ใน greenBook ไหม (เปิดเผยแล้ว)
    "has_price": bool,         # หลักเกณฑ์ราคา (แสดงราคา) vs 2-ซอง (ไม่แสดง)
    "lowest_price": float|None,
    "num_bidders": int|None,
    "revealed_at": str|None }  # 'DD/MM/YYYY HH:MM'
```
- chain: `_get_token` → `encryptApiKey`×2 → `genReportPrice` (egp-merchant-ebidding) → `viewPdf` → pdfplumber
- gate: ตรวจ `greenBook(mode=LINK).greenBookAnnouncementTypeLinkDto` มี `announceType='price'` ก่อน gen (เลี่ยงเรียกฟรี)
- parse: Thai digits ๐-๙→0-9, regex: `จำนวนผู้เสนอราคา`, `ราคาต่ำสุดที่เสนอ`, `เปิดเผย ณ วันที่...เวลา`
- **graceful**: error/ไม่มี → `{"has_summary": False}` (ห้ามทำ poller ล่ม)
- รับ constants PASSKEY/APIKEY_UUID จาก research doc

### 2. `Sebastian_Winner_Poller.py` — stage machine
เปลี่ยน `poll_winners`:
- เดิม poll เฉพาะ `last_stage_notified == "D0"` → **ขยาย**:
  - **Prelim pass:** follows `last == "D0"` → `fetch_prelim_summary` → ถ้า `has_summary`:
    - mode live: `enqueue_for_customer(cid, {..., source_stage:"followed_prelim"})` + `mark_stage_notified(cid,pid,"PRELIM")`
    - closed-loop provisional: ถ้า `has_price` → `compare_prediction_display(pid, lowest_price)` (โชว์เท่านั้น **ไม่ commit สถิติสะสม**)
  - **Formal pass:** follows `last in ("D0","PRELIM")` → `get_procure_result` → ถ้ามีผู้ชนะ (เดิม):
    - `record_bid_results` + `verify_hook` (commit สถิติ) + `enqueue followed_winner` + `mark W0` + `close_follow`
- **invariant:** Round 2 ยิงได้แม้ข้าม Round 1 (follow @ PRELIM ยังถูก formal pass หยิบ) — กันงานที่ prelim หลุด/พัง
- `resolve_prelim` inject ได้ (เหมือน `resolve_result`) เพื่อ test

### 3. Round 1 message — `format_prelim_notification` (LINE_Sender)
source_stage `followed_prelim`:
```
🔔 ผลเสนอราคาเบื้องต้น (ยังไม่ทางการ)
🏗 {ชื่องาน}
📍 {ต./อ./จ.}   💰 ราคากลาง {budget}
📊 ราคาต่ำสุดที่เสนอ: {lowest} · ผู้เสนอ {n} ราย
🎯 เทียบกรอบบนที่เราคาด {hi}: จริง {lowest} → {สูง/ต่ำ}กว่า {x}%
   (ส่วนลดจริง {d}% · เราคาด {p25}–{p75}%)
⏳ รอประกาศผู้ชนะทางการ — จะแจ้งรายชื่อ + คู่แข่งอีกครั้ง
🔑 {pid}
```
- **2-ซอง (`has_price=False`):** "📊 มีผู้เสนอ {n} ราย · ราคายังไม่เปิดเผย (เกณฑ์ 2 ซอง) · รอผลทางการ" (ข้าม closed-loop)
- ไม่มี prediction เก็บไว้ → ข้ามบรรทัด 🎯

### 4. Round 2 message — detailed (LINE_Sender, source_stage `followed_winner`)
ขยายการ์ดผู้ชนะเดิม → breakdown ต่อราย:
```
🏆 ผู้ชนะ: {winner} · {price} (ลด {d}%)
🎯 ความแม่น (เทียบกรอบบน {hi}): จริง {price} → {สูง/ต่ำ}กว่า {x}% · สะสมอยู่ในกรอบ {a}/{b}
📊 ผู้ยื่น {n} ราย (เรียงราคา · เทียบประวัติพื้นที่):
 1)🏆 {ชื่อ} {price} ลด{d}% · {ตำบลนี้/นอกตำบล}เคย~{h}%({k}ครั้ง) {↑↓→} · {ป้าย}
 2)   {ชื่อ} ...
📉 ผู้ชนะลด {d}% vs ตลาดตำบล {m}% ({มากกว่า/น้อยกว่า/พอๆกัน})
🔑 {pid}
```
**ป้ายต่อราย:**
- `✅เราเตือน` = อยู่ใน top-3 intel ที่ส่งตอน D0
- `🔸เจ้าประจำที่หลุด top3` = มีประวัติในพื้นที่ (cgd_winners) แต่ไม่ได้เตือน
- `⬜หน้าใหม่` = ไม่มีประวัติในพื้นที่
- `🏆` = ผู้ชนะ
**ประวัติต่อบริษัท** (จาก cgd_winners, competitive-set): median ส่วนลด + จำนวนครั้ง, แยก "ตำบลนี้" ก่อน ไม่มี→"นอกตำบล", เทรนด์ ↑/↓/→ = เทียบ median ประวัติ vs ครั้งนี้

### 5. Closed-loop — เทียบกรอบบน + upsert
- `cgd_intel.compare_prediction`: เปลี่ยน reference เป็น `area_price_hi` (กรอบบน):
  - `error_pct = (actual - hi) / hi * 100` (มีเครื่องหมาย: + = จริงสูงกว่ากรอบบน)
  - `held = actual <= hi` (อยู่ในกรอบ = winner ลดอย่างน้อยเท่าที่เราคาดขั้นต่ำ)
  - สถิติสะสม = % held ของ verified
- **`save_prediction` เปลี่ยน INSERT OR IGNORE → upsert** (ทับด้วยค่าล่าสุดที่ส่งจริง) — กันค่า prediction ที่เก็บเป็นค่าเก่า (เคสนี้ pooled 704–779 แทนที่จะเป็น concrete 679–730 ที่โชว์)
- Round 1 = `compare` แบบ display-only (ไม่เขียน DB/สถิติ). Round 2 = `compare` + commit (เดิม)

### 6. Poll cadence
`bms-winner-poller.timer`: 6 ชม. → **2 ชม.** (ทันสรุปราคาวันเดียวกัน; poll เฉพาะ followed = น้อย, เคารพ INC-001)

---

## Data / Schema
- `notification_queue.source_stage`: เพิ่มค่า `followed_prelim` (ไม่ต้อง migrate — เป็น TEXT). dedup `(customer, project, source_stage)` → prelim กับ winner ไม่ชนกัน
- `followed_jobs.last_stage_notified`: เพิ่มค่า logical `PRELIM` (TEXT เดิม รองรับ)
- ไม่มี schema migration ใหม่

## Edge cases
| กรณี | จัดการ |
|---|---|
| prelim ยังไม่เปิดเผย | `has_summary=False` → ไม่ทำอะไร, รอรอบหน้า |
| 2-ซอง (ไม่แสดงราคา) | Round 1 = จำนวนผู้เสนอ, ข้าม closed-loop |
| formal ออกก่อน/พร้อม prelim | formal pass หยิบ follow @ D0 ได้เลย → ข้าม Round 1 (ไม่ค้าง) |
| prelim parse fail | graceful skip, log, รอรอบหน้า (ไม่ส่งข้อมูลมั่ว) |
| ไม่มี prediction เก็บ (งานเก่า) | ข้ามบรรทัด closed-loop ทั้ง 2 รอบ |
| บริษัทไม่มีประวัติพื้นที่ | ป้าย ⬜หน้าใหม่ |

## Testing (TDD)
- `prelim_summary`: parse จาก PDF fixture จริง (เก็บ base64 งาน 69059075454) → lowest=740000, n=3, has_price=True. + 2-ซอง fixture (has_price=False). + garbage→has_summary=False
- `poll_winners` stage machine: inject `resolve_prelim`/`resolve_result` → ยืนยัน D0→PRELIM (Round1), PRELIM→W0 (Round2), D0→W0 ข้าม prelim, no-op เมื่อว่าง. ไม่ส่งซ้ำ (dedup stage)
- `compare_prediction`: เทียบกรอบบน (held/error sign) + `save_prediction` upsert ทับจริง
- format Round 1 (มีราคา/2-ซอง) + Round 2 (ป้ายครบ, ranking, ประวัติ in/out tambon)
- regression: test_cgd_intel, test_price_prediction, test_winner_card เดิมต้องผ่าน

## Deploy
push → VPS pull → restart? (poller = timer-based หยิบโค้ดใหม่เอง) + แก้ timer 6h→2h (`systemctl edit` หรือ unit file) + reload. ⚠️ gate confirm push ก่อน.
