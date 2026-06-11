# Sophia — BMS Sanity-Auditor (Dev Sub-Agent) — Design Spec

**วันที่:** 2026-06-12
**สถานะ:** approved design → pending implementation
**ประเภท:** Dev sub-agent (Claude Code Agent tool) — ไม่ใช่ runtime/product agent

---

## 1. ปัญหาที่แก้

โค้ดเบส BMS โต ~231 ไฟล์ / ~45K บรรทัด ทุกครั้งที่แก้ pipeline/script ต้องรัน sanity check
ด้วยมือ (ตาม Sanity Check Protocol ใน CLAUDE.md) ปัจจุบันทำโดย:

- เขียน throwaway probe ใหม่ทุกครั้ง (`_audit_*.py`, `verify_math.py`) รันทีเดียวแล้วทิ้ง → repo รก
- งานเขียน/รัน probe เกิดใน main session → เผา context ของ main thread → เร่ง rate limit

**เป้าหมาย:** ย้ายงาน sanity check ไปอยู่ใน sub-agent (Sophia) ที่ทำงานแยก context แล้วส่งกลับ
แค่ verdict → main thread เบาลง + ลดการสะสม throwaway script

**Non-goal:** ไม่ใช่ runtime agent, ไม่แทน pipeline deterministic, ไม่เกี่ยวกับ Sebastian multi-agent vision

---

## 2. นิยาม & ขอบเขต

- **รูปแบบ:** Claude Code subagent definition ที่ `.claude/agents/sophia.md` + persona doc `docs/agents/Sophia.md` (ตาม convention Dexter/Joyce)
- **Trigger:** on-demand — main thread (Sebastian/Claude) dispatch หลังแก้โค้ดเสร็จ ก่อน commit/ขั้นถัดไป
- **Read-only:** tools = Read, Grep, Glob, Bash + google-sheets `get_sheet_data`
  - **ห้ามมี (hard guarantee ผ่านการไม่ให้ tool):** Write, Edit, update_cells, batch_update, create_sheet
  - **ข้อจำกัดที่ต้องรู้:** Bash จำเป็นต้องมี (รัน python probe) แต่ Bash รันอะไรก็ได้ → read-only ของฝั่ง Bash
    เป็น **by-instruction ไม่ใช่ hard-enforced**. ป้องกันด้วย: (1) system prompt สั่งห้ามรันคำสั่ง mutate/git/deploy เด็ดขาด
    (2) ไม่มี Edit/Write/MCP-write tool เป็นกำแพงจริง (3) ตรวจ tools frontmatter ใน acceptance test
- **แหล่งข้อมูล:** `data/` local + sqlite local + Google Sheets (service account). **ไม่แตะ VPS** (เลี่ยง WAF/ssh)
- **ผลลัพธ์:** คืน verdict report กลับ main thread เท่านั้น — ไม่แตะ git/progress_log/Discord เอง (main thread ตัดสินใจ log)

---

## 3. Context-aware Check Catalog

main thread ส่ง prompt บอก "แก้อะไร" → Sophia เลือกชุดเช็คที่เกี่ยว (ไม่รันทุกอย่างทุกครั้ง):

| ขอบเขตที่แก้ | เช็คที่รัน |
|---|---|
| data ingestion | row count, duplicate IDs, province filter, empty fields |
| winner extraction | sample winners ตรง company pattern, ไม่มี garbage |
| classifier / state machine | job count ต่อ sheet, ไม่มี job หาย/ซ้ำ |
| pricing logic | re-predict sample, ช่วงราคาสมเหตุผล, ไม่มี NaN/ติดลบ |
| pipeline script | exit code, silent error (`\|\| true`, swallowed exception) |
| CGD discovery | winner count, seen set size, duplicate check |

อ้างอิงนิยามเช็คจาก `CLAUDE.md` → section "Sanity Check Protocol"

---

## 4. Hybrid Execution — ใช้ของเดิมก่อน เขียน probe เมื่อจำเป็น

**ลำดับความพยายาม:**
1. เรียก health script ที่มีอยู่ก่อนเสมอ:
   `audit_all_sheets.py`, `queue_health.py`, `sebastian_health_check.py`,
   `Sebastian_Shadow_Audit.py`, `coverage_audit.py`, `audit_pending.py`
2. ถ้าต้อง probe เฉพาะกิจ → เขียนลง `scripts/_scratch/` (gitignored) **ไม่ commit**
3. ตีความ output → สรุปเป็น verdict

`scripts/_scratch/` เป็น directory ใหม่ (เพิ่มใน .gitignore) แทนการโปรย `_audit_*.py` ทั่ว repo

---

## 5. Output Contract

Sophia คืน report รูปแบบคงที่:

```
## Sophia Sanity Report — [ขอบเขตที่ตรวจ]

| สถานะ | check | เจอ | คาด | หมายเหตุ |
|---|---|---|---|---|
| ✅ | row count active_bidding | 312 | ~310 | ok |
| ❌ | duplicate project_id | 4 ซ้ำ | 0 | DUP: 681..., 682... |

VERDICT: STOP — เจอ duplicate 4 รายการ ต้องหาสาเหตุก่อน commit
```

- บรรทัดสุดท้ายต้องเป็น `VERDICT: SAFE TO PROCEED` หรือ `VERDICT: STOP — [เหตุผล]`
- main thread เห็น `STOP` → ไม่ commit, แก้ก่อน (ตรงกฎ CLAUDE.md)

---

## 6. สิ่งที่ Sophia ไม่ทำ (YAGNI)

❌ แก้ข้อมูล ❌ commit ❌ deploy ❌ แตะ VPS ❌ ส่ง Discord เอง ❌ เขียน progress_log เอง
❌ ตัดสินใจ design/refactor — แค่ "ตรวจแล้วรายงาน"

---

## 7. Acceptance Criteria

- [ ] `.claude/agents/sophia.md` ทำงานได้ — dispatch แล้วรันเช็คตาม context ที่ส่งไป
- [ ] persona doc `docs/agents/Sophia.md` ตาม convention Dexter/Joyce
- [ ] `scripts/_scratch/` ถูก gitignore
- [ ] ทดสอบจริง: dispatch Sophia หลังแก้ pricing 1 ครั้ง → ได้ verdict table + บรรทัด VERDICT
- [ ] ยืนยัน Sophia ไม่มี write tool (ตรวจ tools list ใน agent frontmatter)
