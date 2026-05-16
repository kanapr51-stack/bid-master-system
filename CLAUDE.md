# CLAUDE.md — Bid Master System Project Rules

ไฟล์นี้ Claude Code อ่านอัตโนมัติทุก session — กฎการทำงานที่ต้องปฏิบัติ

---

## 🔔 Discord Notification Protocol (สำคัญสูงสุด)

**ทุกครั้งที่มีการเปลี่ยนแปลง — ส่งแจ้งเตือนใน Discord ของคุณกัญจน์ทันที**

ใช้ `scripts/Sebastian_Discord_Notify.py` (token อยู่ใน .env)

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "ข้อความที่จะส่ง")
```

### Triggers (ต้องส่ง Discord เสมอ):

| Event | ตัวอย่างข้อความ |
|---|---|
| **เริ่ม phase ใหญ่** | "🚀 เริ่ม Phase X: [ชื่อ phase]" |
| **เสร็จ phase ใหญ่** | "✅ Phase X เสร็จ — [สรุปผล]" |
| **Commit code** | "📝 Commit: `[hash]` [ชื่อ commit]" |
| **เจอ bug ใหญ่** | "🐛 พบ bug: [คำอธิบาย root cause]" |
| **Long-running task เริ่ม** (background > 1 นาที) | "⏳ เริ่ม [งาน] background — ETA [เวลา]" |
| **Long-running task เสร็จ** | "✅ [งาน] เสร็จ — [สรุปผล]" |
| **Major decision** (รอ user confirm) | "❓ ต้องการ confirm: [ตัวเลือก A/B/C]" |
| **Sheet structure change** | "📊 Sheet [name] เปลี่ยน: [diff]" |
| **Schema migration** | "🔧 Schema all_jobs เพิ่ม column: [name]" |
| **Rate limit hit** | "⚠️ eGP rate limit — รอ [N] วินาที" |

### ไม่ต้องส่ง Discord:
- งานเล็กๆ ที่ทำไม่กี่วินาที (read file, simple grep)
- ทุก task ใน TaskCreate/TaskUpdate (verbose เกิน)
- ทุก bash command (verbose เกิน)

**Rule of thumb:** ส่งเมื่อมีผลกระทบกับ data/code ใน Sheet หรือ git, หรือคุณกัญจน์ควรรู้สถานะ

---

## 📋 Progress Logging Protocol (สำหรับ Rate Limit Recovery)

**บันทึก `progress_log.md` แบบ real-time** — ไม่รอจบ session

### กฎ:

1. **ทุก commit** → เพิ่ม entry ใน `progress_log.md` ทันที (ก่อน commit ก็ได้)
2. **ทุก phase ใหญ่ เริ่ม/เสร็จ** → ระบุ timestamp + สิ่งที่ทำ
3. **ทุก decision point** → บันทึกเหตุผลและทางเลือกที่ตัดสิน
4. **ก่อนรัน background task** → checkpoint state ปัจจุบันลง progress_log
5. **ทุก ~30 นาที** ของ work session → checkpoint state

### Format ของ progress_log entry:
```markdown
## งานที่ N+X: [ชื่องาน] ([วันที่])

### สถานะ: 🚧 กำลังทำ / ✅ เสร็จ / ⏸ pause

### Root cause / สิ่งที่ทำ
[คำอธิบาย]

### Fix / ผล
[ตัวเลข, จำนวน sheet rows, ฯลฯ]

### Followup
- [item ค้างไว้]
```

---

## 🔄 Resume Protocol (ถ้า Claude ใหม่เข้ามาทำต่อ)

**ถ้าคุณกัญจน์ส่งข้อความใดข้อความหนึ่งต่อไปนี้:**
- "เมื่อกี้ฉันโดน Rate Limit"
- "Claude ก่อนหน้าไม่ทันทำเสร็จ"
- "ฉันใช้ ID อื่นเข้ามา"
- "Resume ต่อ"
- "Continue"

**Claude ต้อง:**

1. อ่าน `progress_log.md` (section ล่าสุด — ดู timestamp ใหม่สุด)
2. ตรวจ `git log --oneline | head -10` ดู commits ล่าสุด
3. ตรวจ `git status` ดู uncommitted changes
4. ตรวจ TaskList — มี in_progress tasks ค้างไหม
5. ส่ง Discord notify ว่า "📍 Resume จาก [commit hash] — [งานที่กำลังทำ]"
6. **สรุปสถานะให้คุณกัญจน์** + **รอคำสั่ง** ไม่ลงมือทันที

---

## 🎯 Domain-Specific Rules

### Sheets (6 sheets after Phase A redesign)

ดู `docs/egp_stepid_catalog.md` สำหรับรายละเอียด stepId → sheet mapping

| Sheet | Logic | Semantic |
|---|---|---|
| pre_tor | stepId Q* | ขั้นวางแผน (early radar) |
| tor_review | stepId U* | รับฟังคำวิจารณ์ |
| active_bidding | stepId M03/S*/Z* + deadline ≥ today | ยื่นซองได้ตอนนี้ |
| pending_award | stepId active + deadline ผ่าน OR stepId W*/C*/I* ไม่มี winner | รอประกาศผู้ชนะ |
| awarded_jobs | มี winner cache | รู้ผู้ชนะแล้ว |
| cancelled_jobs | projectStatus=R OR announce ลงท้าย "1" OR stepId B* | ยกเลิก |

### Pipeline (8 steps, รัน 06:00 ทุกวัน)
```
scrape → classify → refresh → download → analyze → cost → rank → notify
```

### eGP API Endpoints (ที่ใช้)
- `getProjectDetail?projectId=X` → stepId, flowSeqno, projectStatus, announceType
- `getProcureResult?projectId=X` → bidders + winner (priceAgree != null)
- ใน `egp-atpj27-service/pb/a-egp-allt-project/announcement`

### Rate Limit
- eGP: ~100 req / 120s window
- ในสคริปต์ใช้: sleep 1.5s + cooldown 30s ทุก 50 jobs
- Detect: response มี flowSeqno=0 + stepId='' → retry 3s

---

## 🚦 Coding Guidelines

1. **ไม่สร้าง feature ก่อนต้องการจริงๆ** (YAGNI)
2. **เก็บง่ายๆ ก่อน** (KISS)
3. **Foundation first** — fix logic ก่อนเพิ่ม feature
4. **Verifiable in chunks** — commit เล็กๆ บ่อยๆ
5. **อย่า refactor ใหญ่ๆ ใน commit เดียว** — แยก
6. **Backup ก่อนเปลี่ยน schema** — `backups/[name]_[timestamp].json`
7. **ทุก research/probe → save raw data** ลง `data/` หรือ `docs/`

### File Layout
- `scripts/` — production scripts + helper/probe
- `docs/` — design docs, catalog, plans
- `data/` — runtime data (winner_cache, research output)
- `backups/` — sheet snapshots (ignored in git)
- `progress_log.md` — main work history (always update)
- `MEMORY.md` — Claude memory index (in `C:\Users\Ace\.claude\projects\...`)

---

## 📞 Communication Style

- **ภาษาไทยเป็นหลัก** (user เป็นคนไทย)
- **คำสั้น กระชับ** ใช้ markdown table/bullet
- **ไม่ over-explain** — บอกผลก่อน เหตุผลหลัง (ถ้าถาม)
- **ใช้ emoji แทนหัวข้อ** (🔵 active / 🟡 pending / ❌ cancelled)
- **ระบุไฟล์ด้วย format** `path:line`
- **ถ้าตัดสินใจไม่แน่ใจ — ถาม user** (อย่า assume)

---

## ⚠️ Don'ts (ที่ห้ามทำ)

- ❌ ห้าม commit `.env`, `credentials/`, `chrome_debug_profile/`
- ❌ ห้าม push to remote โดยไม่ confirm
- ❌ ห้าม force push, reset --hard, branch -D
- ❌ ห้าม skip pre-commit hooks (--no-verify)
- ❌ ห้าม run destructive operations โดยไม่ backup ก่อน
- ❌ ห้าม assume API response format โดยไม่ probe จริง
- ❌ ห้าม trust stepId อย่างเดียวสำหรับ active (ต้อง check deadline ด้วย — เรียนรู้จาก bug 2026-05-16)

---

## 📂 Quick Reference

- **Spreadsheet ID:** `1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps`
- **Chrome debug port:** `9222`
- **Pipeline 06:00 cron:** ยังต้องตั้ง (ดู `Sebastian_Pipeline.py --step all`)
- **LINE Notify token:** ใน `.env` → `LINE_CHANNEL_ACCESS_TOKEN`
- **Discord token:** ใน `.env` → `DISCORD_BOT_TOKEN`
- **Service account:** `credentials/service_account.json` (gitignored)

---

**Last updated:** 2026-05-16 (Phase A complete + Discord/Progress protocol added)
