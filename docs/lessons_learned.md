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

---

### ADR-002 — Residential Resolve Node (incident response, 2026-06-03)

**Status:** Approved (กัญจน์ + ChatGPT converged 2026-06-03, ระหว่าง INC-001)

**Context:** WAF block `generateToken` + `getProcurementDetail` จาก VPS datacenter IP → resolve พัง (ดู INC-001). ต้องเลือกทางฟื้น: A (token-mint proxy) / B (residential resolve node) / C (proxy/VPN)

**Decision:** เลือก **B — Residential Resolve Node** (A ตกไปเพราะ getProcurementDetail VPS ก็ block, ไม่ใช่แค่ generateToken)
- resolve (generateToken + getProcurementDetail + doczip) ทำบน Windows residential → push ผล (moiName + deadline) ให้ VPS → VPS แค่ match+enqueue+ส่ง
- **bounded change:** แตะเฉพาะ Enrichment Plane ไม่แตะ Discovery/Delivery
- **P0.0 (restore เร็วสุด) แยกจาก P0.1 (build worker):** manual resolve บน Windows ฟื้น service วันนี้ ก่อน build automation — KPI = time-to-recovery ไม่ใช่ elegance

**Rationale:** B = proven path (matrix พิสูจน์ residential ผ่านทุก endpoint วันนี้). C = unproven + เพิ่ม dependency (proxy/VPN/billing/latency). incident → restore ด้วย proven path ก่อน

**Explicitly deferred (ยังไม่มี evidence ว่าจำเป็น):** proxy/VPN · ย้าย Discovery ไป residential (announcement search VPS ยังผ่าน — ตั้ง tripwire แทน) · 77-province redesign

---

## Lessons Learned (เพิ่มจาก INC-001)

### L-002 — Discovery health ≠ Business health (2026-06-03)
**Context:** INC-001 — Discovery scan ปกติ (full sweep 738/347) แต่ notifications = 0 พร้อมกันได้
**บทเรียน:** plane หนึ่ง healthy ไม่ได้แปลว่าธุรกิจ healthy — Discovery=healthy + Enrichment=dead → user ไม่ได้งาน. **ห้ามอ่าน Discovery health เป็น proxy ของ business health**
**How to apply:** health dashboard ต้องวัด business outcome (notifications sent) ไม่ใช่แค่ upstream (scan count)

### L-003 — ทุก plane ต้องมี health signal ของตัวเอง (2026-06-03)
**Context:** dead-man switch มีแค่ token harvest (Discovery) — ไม่มีของ qualification/delivery → INC-001 พังเงียบ 1.5 วัน
**บทเรียน:** Discovery Plane · Enrichment Plane · Delivery Plane — แต่ละ plane ต้องมี health signal แยก **ห้ามใช้ plane หนึ่งเป็น proxy ของอีก plane**
**How to apply:** เพิ่ม resolve-success-rate + qualification-throughput alerts (P1)

### L-004 — Canary ต้องวัด business-critical path ไม่ใช่แค่ upstream availability (2026-06-03)
**Context:** announcement search (upstream) ผ่าน → ดูเหมือน healthy แต่ resolve (business-critical) พัง
**บทเรียน:** "announcement search canary" ไม่พอ — ต้องมี **qualification canary** (AES canary: generateToken + getProcurementDetail กับ test project ทุก 1-2 ชม) ที่วัด path ที่ธุรกิจพึ่งจริง
**How to apply:** AES canary (P1) — พิสูจน์ resolve path healthy ไม่ใช่แค่ scan path

---

## Incident Log

### INC-001 — Control Plane Assumption Failure (2026-06-03)

**Severity:** High · **Customer impact:** Notifications stopped ~1.5 วัน (delivery ล่าสุด 06-02 00:09) · เจอโดยบังเอิญระหว่าง debug "ประทับ 8" (ไม่มี alert)

**Plane status:** Discovery = Healthy · Enrichment = **Failed** · Delivery = Healthy but starved

**Facts (evidence matrix, test จริง 2026-06-03):**
| Endpoint | residential (Windows) | VPS (datacenter) |
|---|---|---|
| generateToken (POST) | ✅ | ❌ WAF "Request Rejected" |
| getProcurementDetail (GET) | ✅ (moiName ได้) | ❌ WAF "Request Rejected" |
| announcement search (GET) | ✅ | ✅ **ผ่าน** |

WAF signature: HTTP 200 + HTML "The requested URL was rejected. Your support ID is: <…>" (BIG-IP ASM / Imperva style)

**Interpretation:** Discovery endpoint และ Resolve endpoint อยู่ใต้ WAF behavior คนละแบบ → ไม่ได้อยู่ใน trust zone เดียวกัน

**Root Cause:** **Control Plane Assumption Failure** — BMS assumed `discovery reachable ⇒ resolve reachable` ซึ่ง**เป็นเท็จ**. ไม่ใช่ bug แต่เป็น finding เชิง architecture

**สิ่งที่ incident พิสูจน์เพิ่ม:** observability > cleverness — dead-man switch/telemetry (ที่เคยเป็น hypothesis) พิสูจน์คุณค่าจริง: ถ้าไม่มี telemetry เราจะยังเชื่อว่า "ตลาดเงียบ" ทั้งที่ qualification plane dead

**Recovery Plan:** P0.0 manual residential resolve (restore) → P0.1 Residential Resolve Worker (B) → P1 AES canary + qualification throughput alert + resolve success-rate alert → P2 measure residential dependency + Windows uptime → P3 Raspberry Pi decision

**Explicitly deferred:** proxy · VPN · ย้าย Discovery ไป residential · 77-province redesign (ยังไม่มี evidence ว่าจำเป็น)
