# Sophia Sanity-Auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** สร้าง Sophia — Claude Code read-only sub-agent ที่รัน sanity check แทน main thread เพื่อลด context/rate-limit

**Architecture:** Agent definition (`.claude/agents/sophia.md`) = frontmatter (tools จำกัด read-only) + system prompt ที่ encode Sanity Check Protocol. Persona doc (`docs/agents/Sophia.md`) ตาม convention Dexter/Joyce. Scratch dir gitignored สำหรับ throwaway probe. ไม่มีโค้ด runtime — เป็น markdown config ล้วน

**Tech Stack:** Claude Code Agent (markdown + YAML frontmatter), reuse Python health scripts เดิม

---

### Task 1: Scratch dir + gitignore

**Files:**
- Modify: `.gitignore`
- Create: `scripts/_scratch/.gitkeep`

- [ ] **Step 1: เพิ่ม scratch ใน .gitignore** (ต่อท้าย section data ignores ราวบรรทัด 62)

```
# Sophia sanity-auditor throwaway probes (ไม่ commit)
scripts/_scratch/
!scripts/_scratch/.gitkeep
```

- [ ] **Step 2: สร้าง .gitkeep กัน dir หาย**

เนื้อหาไฟล์ `scripts/_scratch/.gitkeep`:
```
# Sophia เขียน throwaway probe ที่นี่ — gitignored ยกเว้นไฟล์นี้
```

- [ ] **Step 3: verify gitignore ทำงาน**

Run: `touch scripts/_scratch/x.py && git status --short scripts/_scratch/`
Expected: เห็นแค่ `.gitkeep` (ถ้า track อยู่) — ไม่เห็น `x.py`. แล้วลบ: `rm scripts/_scratch/x.py`

- [ ] **Step 4: Commit**

```bash
git add .gitignore scripts/_scratch/.gitkeep
git commit -m "chore(sophia): scratch dir for throwaway sanity probes"
```

---

### Task 2: Persona doc (docs/agents/Sophia.md)

**Files:**
- Create: `docs/agents/Sophia.md`

- [ ] **Step 1: เขียน persona doc ตาม convention Joyce** (frontmatter + ตัวตน + System Prompt block)

เนื้อหา (frontmatter):
```
---
name: Sophia
role: Sub Agent ด้านตรวจสอบความถูกต้องข้อมูล (Sanity Auditor)
status: ใช้งานอยู่
expertise: sanity check หลังแก้ pipeline/script — row count, dup IDs, winner extraction, price sanity, silent error
---
```
ตัวตน: ละเอียด ระแวงข้อมูล ไม่เชื่อจนกว่าจะเห็นตัวเลข, read-only, รายงานต่อ Sebastian
ใส่ System Prompt block ที่ชี้ไป `.claude/agents/sophia.md` เป็น source of truth

- [ ] **Step 2: verify frontmatter ตรง convention**

Run: `head -6 docs/agents/Sophia.md`
Expected: เห็น `name: Sophia` + 4 field ตรงแบบ Joyce

---

### Task 3: Agent definition (.claude/agents/sophia.md) — หัวใจ

**Files:**
- Create: `.claude/agents/sophia.md`

- [ ] **Step 1: เขียน frontmatter — tools จำกัด read-only (กำแพงจริง)**

```
---
name: sophia
description: Read-only BMS sanity auditor. Dispatch หลังแก้ pipeline/script ก่อน commit เพื่อตรวจ row count, duplicate IDs, winner extraction, price sanity, silent errors. คืน verdict SAFE/STOP. ห้ามใช้เขียน/แก้ข้อมูล.
tools: Read, Grep, Glob, Bash, mcp__google-sheets__get_sheet_data
model: sonnet
---
```
หมายเหตุ: **ไม่ใส่** Write, Edit, update_cells, batch_update = hard guarantee read-only ฝั่ง tool

- [ ] **Step 2: เขียน system prompt body** — encode 6 ส่วน:
  1. ตัวตน: read-only auditor, ห้ามรันคำสั่ง mutate/git/deploy ใน Bash เด็ดขาด
  2. Context-aware: รับ "แก้อะไร" → เลือกชุดเช็คตาม catalog (ดู spec section 3)
  3. Hybrid: เรียก script เดิมก่อน (`audit_all_sheets.py`, `queue_health.py`, `sebastian_health_check.py`, `Sebastian_Shadow_Audit.py`, `coverage_audit.py`), probe เฉพาะกิจเขียนลง `scripts/_scratch/` เท่านั้น
  4. แหล่งข้อมูล: local `data/` + sqlite + Google Sheets get_sheet_data — **ห้ามแตะ VPS**
  5. Output contract: verdict table + บรรทัดสุดท้าย `VERDICT: SAFE TO PROCEED` / `VERDICT: STOP — [เหตุผล]`
  6. ไม่ทำ: แก้ข้อมูล/commit/deploy/Discord/progress_log

- [ ] **Step 3: verify tools list ไม่มี write (acceptance critical)**

Run: `grep -E "^tools:" .claude/agents/sophia.md`
Expected: บรรทัด tools มีแค่ Read, Grep, Glob, Bash, mcp__google-sheets__get_sheet_data — **ไม่มี** Write/Edit/update/batch

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/sophia.md docs/agents/Sophia.md
git commit -m "feat(sophia): read-only BMS sanity-auditor sub-agent"
```

---

### Task 4: End-to-end smoke test

**Files:** (ไม่สร้างไฟล์ — แค่ทดสอบ)

- [ ] **Step 1: dispatch Sophia จริงผ่าน Agent tool** ด้วย prompt ทดสอบ เช่น
  "เพิ่งแก้ pricing logic ใน competitor_trend.py — ตรวจ price sanity sample + ไม่มี NaN/ติดลบ"

- [ ] **Step 2: verify output มี verdict**

Expected: Sophia คืน table + บรรทัด `VERDICT: ...` และไม่พยายามเขียน/แก้ไฟล์ใดๆ (ถ้าพยายาม Write จะ error เพราะไม่มี tool = ยืนยันกำแพง)

- [ ] **Step 3: ถ้า output ตรง contract → เสร็จ.** ถ้าเพี้ยน → กลับไปแก้ system prompt Task 3 Step 2

---

## Self-Review Notes
- Spec coverage: Task1=scratch(spec§4), Task2=persona(spec§2), Task3=agent core(spec§2,3,4,5,6), Task4=acceptance(spec§7) ✅
- Read-only hard guarantee = ไม่ให้ write tool (Task3 Step1) + by-instruction สำหรับ Bash (Task3 Step2.1) ตรง spec§2
- ไม่มี placeholder — เนื้อหา system prompt ชี้ไป spec sections ที่มีรายละเอียดครบแล้ว
