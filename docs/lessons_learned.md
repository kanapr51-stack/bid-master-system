# BMS — Lessons Learned & Architecture Decisions

เอกสารความรู้ระดับโปรเจกต์ (project knowledge) — ไม่ใช่ preference ส่วนบุคคล
แยกเป็น 2 ส่วน: **Lessons** (บทเรียนเชิงหลักการ) + **ADR** (architecture decision records)

---

## Lessons Learned

### L-001 — Telemetry พิสูจน์พฤติกรรมระบบ ไม่ได้พิสูจน์สภาพโลกภายนอก (2026-06-03)

**Context:** RSS investigation — `rss_queue.json` หยุด append. telemetry poll_log แสดง `HTTP 200 + items=0` ต่อเนื่อง 8 ชม กลางคืน. Claude สรุปครั้งแรกว่า "feed ว่างจริง = ไม่มีประกาศ"

**บทเรียน:** `HTTP 200 + empty payload` **≠** proof ว่าไม่มี event เกิดขึ้นจริง
- สิ่งที่หลักฐานพิสูจน์: **source returned nothing** (ระบบตอบ 0)
- สิ่งที่หลักฐาน **ไม่** พิสูจน์: **nothing existed** (ไม่มีงานจริงในโลก)
- hypothesis ที่ยังไม่ถูกตัดออก: feed truncation · feed generation issue · partial outage

**Wording ที่ถูกต้อง:** "ไม่พบหลักฐาน bug ฝั่ง scraper ของเรา + feed คืน 0 items" — ไม่ใช่ "พิสูจน์แล้วว่าไม่มีงาน"

**ใช้ได้กับ (generalization):** RSS feed · WAF characterization · Discovery completeness · การพิสูจน์ใดๆ ตอน scale 77 จังหวัด — ทุกครั้งที่ telemetry "ดูเหมือนพิสูจน์อะไรบางอย่าง" ให้ถามว่ามันพิสูจน์ *พฤติกรรมระบบ* หรือ *สภาพภายนอก*

**How to apply:** เวลารายงาน root cause — แยก "observed (ระบบทำอะไร)" ออกจาก "inferred (โลกเป็นอย่างไร)" และระบุ hypothesis ที่ยังไม่ตัดออกเสมอ

---

## Architecture Decision Records (ADR)

### ADR-001 — Evidence-based gate ก่อน flip RSS Shadow Mode (2026-06-03)

**Status:** Approved (Co-Architect 2026-06-03)

**Context:** RSS Shadow Mode จะ flip `BMS_RSS_NOTIFY=off` เพื่อให้ Discovery เป็น primary. แผนเดิม = "รอ 1-2 วันแล้ว flip" (time-based)

**Decision:**
1. **flip เมื่อหลักฐานสนับสนุน ไม่ใช่เมื่อครบเวลา** — 48h dry-run (gate ยัง on) วัด **confirmed rate** ก่อน:
   - ≥ ~99% + ไม่มี backlog >24ชม → flip ได้
   - ต่ำ (~80%) หรือมี >24ชม ค้าง → ห้าม flip ต้องสืบ gap ก่อน
2. **เพิ่ม leading indicators** (เดิมมีแต่ lagging audit >24ชม ซึ่งรู้ช้าถ้า Discovery regression):
   - shadow backlog size (confirmed=0, age<24ชม)
   - age distribution (0-6/6-12/12-24/>24ชม)
   - confirmed rate

**Rationale:** lagging audit (24ชม) ช้าเกินถ้า Discovery พัง (token/rate-limit/incremental bug) — leading metric เห็นก่อน. flip แบบ time-based = เดา; flip แบบ confirmed-rate = มีหลักฐาน. สอดคล้องหลัก "observe before optimize"

**Consequences:** rollout ช้าลง (เพิ่ม 48h dry-run) แต่ลดความเสี่ยง flip ทั้งที่ Discovery ยังจับไม่ครบ (= งานหาย)

**Ref:** spec `docs/superpowers/specs/2026-06-02-rss-shadow-mode-design.md` §5.4, §8
