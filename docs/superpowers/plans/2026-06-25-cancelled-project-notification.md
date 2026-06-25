# Cancelled Project Notification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / subagent-driven-development. Steps use checkbox tracking.

**Goal:** ตรวจจับงานที่ติดตามแล้วโครงการถูกยกเลิก → แจ้งเตือน LINE + ย้ายออกจาก "สรุปราคาเบื้องต้น" บน Board ไปกลุ่ม "ยกเลิก"

**Architecture:** piggyback บน winner-poller (timer ~6 ชม.). เพิ่ม cancellation pass ก่อน prelim/formal pass → `get_project_detail` → `is_cancelled` (extract จาก classifier) → enqueue `followed_cancelled` + mark `CANCELLED` + close. Board เพิ่มกลุ่ม `cancelled` เช็ค `lsn=="CANCELLED"` ก่อน prelim. LINE card re-derive note ตอน render (เหมือน prelim re-fetch).

**Tech Stack:** Python, SQLite, plain-assert test scripts (รันตรง ไม่ใช่ pytest)

## Global Constraints
- mode gate: `BMS_PROVINCE_NOTIFY_MODE == "live"` เท่านั้นที่เขียน DB/enqueue; อื่น = shadow log
- dedup key: `(customer, project, source_stage)` — source_stage ใหม่ = `followed_cancelled`
- fail-safe: `get_project_detail` error/ว่าง → ข้าม (ห้าม false-cancel)
- ห้ามแก้พฤติกรรม `classify_by_stepid` (sheets) — extract เฉพาะ note generation
- spec: `docs/superpowers/specs/2026-06-25-cancelled-project-notification-design.md`

---

## Task 1: `is_cancelled` predicate (Classifier)

**Files:**
- Modify: `scripts/Sebastian_Classifier.py` (เพิ่ม `_cancel_note`, `is_cancelled`; refactor step-1 ของ `classify_by_stepid`)
- Test: `scripts/test_is_cancelled.py` (สร้างใหม่)

**Interfaces — Produces:**
- `is_cancelled(step_id: str, project_status_raw: str, announce_type: str) -> tuple[bool, str]`
- `_cancel_note(step: str) -> str`

**Predicate:** cancelled = `project_status_raw=="R"` OR `announce_type in ("D1","W1")` OR `step.upper().startswith("B")`.
note: ถ้า R/D1/W1 → `_cancel_note(step)`; ถ้า B-prefix อย่างเดียว → `""`.

- [ ] Test: R→(True, "ยกเลิกหลังประมูล (W01)"); D1→True; W1→True; B01 ล้วน→(True,""); S01 ปกติ→(False,""); ว่าง→(False,"")
- [ ] Run fail → implement → run pass
- [ ] Regression: `classify_by_stepid` เดิมยังคืนเท่าเดิม (B01+has_winner→awarded_jobs)
- [ ] Commit

---

## Task 2: Cancellation pass (Winner Poller)

**Files:**
- Modify: `scripts/Sebastian_Winner_Poller.py` (`poll_winners` เพิ่ม param `resolve_status=None` + pass ก่อน prelim/formal; `main()` wire `get_project_detail`)
- Test: `scripts/test_winner_poller_cancel.py` (สร้างใหม่)

**Interfaces — Consumes:** `is_cancelled` (Task 1); `store.get_active_follows/enqueue_for_customer/mark_stage_notified/close_follow`
**Produces:** `poll_winners(..., resolve_status=None)`; stats key `"cancelled"`

**Logic:** ถ้า `resolve_status` ไม่ None → group active follows ตาม pid → `resolve_status(pid)` → `is_cancelled` → ถ้าจริง (mode live): enqueue `followed_cancelled` + mark `CANCELLED` + close ทุก follow; เก็บ pid ใน `cancelled_pids`. formal/prelim pass exclude `cancelled_pids`. error → log+continue.

- [ ] Test: FakeStore 1 follow lsn=D0, `resolve_status`→cancelled → enqueue source_stage=followed_cancelled, mark CANCELLED, close, **ไม่เรียก** resolve_result(winner); stats["cancelled"]==1
- [ ] Test fail-safe: resolve_status raises → ไม่ cancel, follow ยังอยู่
- [ ] Test backward-compat: resolve_status=None → ไม่มี cancellation pass (test เดิมผ่าน)
- [ ] Run fail → implement → run pass → commit

---

## Task 3: LINE card `followed_cancelled` (LINE Sender)

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (เพิ่ม `format_cancelled_notification` + dispatch block หลัง followed_winner ~line 754)
- Test: `scripts/test_format_cancelled.py` (สร้างใหม่)

**Interfaces — Produces:** `format_cancelled_notification(project_name: str, province: str="", note: str="") -> str`

**Card:**
```
❌ โครงการถูกยกเลิก
[project_name]
📍 จ.[province]        (ถ้ามี)
[note]                 (ถ้ามี)
```
Dispatch block: source_stage-gated; re-derive note ผ่าน `get_project_detail`+`is_cancelled` (try/except → note=""); dry_run/send/mark_delivery_result/return เหมือน prelim block.

- [ ] Test: format มี "❌ โครงการถูกยกเลิก" + ชื่อ + จังหวัด + note; ไม่มี province → ไม่มีบรรทัด 📍
- [ ] Run fail → implement → run pass → commit

---

## Task 4: Board cancelled group (bms_api)

**Files:**
- Modify: `scripts/bms_api.py` (`_portal_jobs`: groups+["cancelled"], เช็ค `lsn=="CANCELLED"` ก่อน win; `_portal_page_html`: chip + `_card` branch + render loop)
- Test: `scripts/test_portal_cancelled.py` (สร้างใหม่)

**Logic:** หลังสร้าง job dict (≈line 450) — `if lsn=="CANCELLED": groups["cancelled"].append(job); continue`. chip `("cancelled","❌ ยกเลิก")`. `_card` branch `kind=="cancelled"` → badge "❌ ยกเลิกโครงการ" + "โครงการนี้ถูกยกเลิกแล้ว". render loop เพิ่ม `("cancelled","❌ ยกเลิกโครงการ")` ท้ายสุด.

- [ ] Test: follow lsn=CANCELLED → อยู่ `g["cancelled"]`, **ไม่อยู่** `g["prelim"]`; HTML มี "ยกเลิกโครงการ"
- [ ] Run fail → implement → run pass → commit

---

## Self-review note
ครอบคลุม spec ครบ 4 ส่วน (predicate/detection/notification/board) + backfill อัตโนมัติ (รอบ poll แรก). ไม่มี placeholder. ชื่อฟังก์ชัน/source_stage สอดคล้องทุก task.
