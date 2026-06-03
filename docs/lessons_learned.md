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

### L-006 — external dataset: field LABEL ≠ field CONTENT (verify ค่าจริง ไม่ใช่แค่ชื่อ field) (2026-06-04)

**Context:** ดึง winner ย้อนหลังจาก CGD `egp-contract-2568` (data.go.th). field ชื่อ `"ชื่อผู้ชนะ"` → map ตรงตามชื่อ. sanity check พบ **100% ของค่าใน field นั้นเป็นวันที่** (ไม่ใช่ชื่อบริษัท). winner จริงอยู่ field `'ละติจูดโครงการ'` — dataset มี **column shift** (เลื่อนจาก block พิกัด/coordinate ที่มี variable-length)

**บทเรียน:** external dataset (CKAN/open data/CSV) — **ชื่อ column ไม่การันตีว่าเนื้อหาตรง**. ต้อง verify ค่าจริงของ sample (ไม่ใช่แค่ดู field names ว่ามี field ที่ต้องการ). การ map by field-name ตรงๆ = เสี่ยง garbage เงียบ

**วิธีแก้ (adaptive extraction):** หาค่าจาก **pattern ของเนื้อหา** ไม่ใช่ตำแหน่ง/ชื่อ field — winner = field แรกที่ค่ามี company marker (บริษัท/ห้าง/หจก/กิจการร่วมค้า) ยกเว้น field ชื่องาน/หน่วยงาน. + validate (price: ตกลง≤กลาง×1.5). กู้ได้ 86% ถูก 100%

**How to apply:** ก่อน map external dataset → print sample values ของทุก field เทียบ label. ถ้า shift → extract by content-pattern (adaptive) + validate. อย่า trust field name. (= ญาติของ "ห้าม assume API response format โดยไม่ probe จริง" ใน CLAUDE.md)

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

**Status:** ⬇️ **Superseded by ADR-003** (2026-06-03 Rev 3) — downgrade Primary → **Contingency/Fallback**. residential validated จริง (ไม่ผิด) แต่ model ที่สร้าง ADR-002 **ยังไม่ครบ** (สมมติ VPS = permanent block). Rev 3 พบ VPS = burst-limit ฟื้นหลัง cooldown → residential ไม่ใช่ทางหลัก เป็น fallback

**Context:** WAF block `generateToken` + `getProcurementDetail` จาก VPS datacenter IP → resolve พัง (ดู INC-001). ต้องเลือกทางฟื้น: A (token-mint proxy) / B (residential resolve node) / C (proxy/VPN)

**Decision:** เลือก **B — Residential Resolve Node** (A ตกไปเพราะ getProcurementDetail VPS ก็ block, ไม่ใช่แค่ generateToken)
- resolve (generateToken + getProcurementDetail + doczip) ทำบน Windows residential → push ผล (moiName + deadline) ให้ VPS → VPS แค่ match+enqueue+ส่ง
- **bounded change:** แตะเฉพาะ Enrichment Plane ไม่แตะ Discovery/Delivery
- **P0.0 (restore เร็วสุด) แยกจาก P0.1 (build worker):** manual resolve บน Windows ฟื้น service วันนี้ ก่อน build automation — KPI = time-to-recovery ไม่ใช่ elegance

**Rationale:** B = proven path (matrix พิสูจน์ residential ผ่านทุก endpoint วันนี้). C = unproven + เพิ่ม dependency (proxy/VPN/billing/latency). incident → restore ด้วย proven path ก่อน

**Explicitly deferred (ยังไม่มี evidence ว่าจำเป็น):** proxy/VPN · ย้าย Discovery ไป residential (announcement search VPS ยังผ่าน — ตั้ง tripwire แทน) · 77-province redesign

---

### ADR-003 — Rate-Limited Resolve Architecture (INC-001 Rev 3, 2026-06-03)

**Status:** Approved (กัญจน์ + ChatGPT converged 2026-06-03, Rev 3 — supersedes ADR-002)

**Context:** หลัง pause VPS enrichment worker → WAF block หาย → test ยืนยัน VPS resolve กลับมา (generateToken OK + getProcurementDetail 200 moiName=นางัว, blocked=False). พิสูจน์ว่า WAF = **rate/behavior-based ไม่ใช่ permanent IP blacklist**. VPS ถูก block ตลอด 1.5 วันเพราะ worker ยิง resolve ทุก 2 นาทีต่อเนื่อง → burst saturated ไม่หยุด → block ถูก**ต่ออายุเอง**

**Decision:** เปลี่ยนกรอบจาก "External Dependency Failure" (ต้องย้าย node) เป็น **"Rate-Control Failure"** (ต้องคุมจังหวะยิง)
- **Primary: VPS throttled** — 24/7, single deploy, ไม่ต้อง Windows uptime/harvest sync/Pi. ปัญหาเปลี่ยนจาก *reachability* → *throughput control*
- **Fallback: Residential** (ADR-002 path) — เก็บไว้เป็น contingency ถ้า VPS throttle ไม่พอ
- **lock = "Need adaptive rate control"** ไม่ lock ตัวเลข (batch=5/cooldown=30m ยังเป็น observation ไม่ใช่ characterization)

**Rationale:** ปัญหาจริงคือ throughput envelope ไม่ใช่ node location. VPS ง่ายกว่ามาก (ไม่มี dependency เพิ่ม). RPi **defer หนักกว่าเดิม** (เหตุผลเดิม = VPS ใช้ไม่ได้ ตอนนี้ VPS อาจใช้ได้ → ซื้อ Pi ยิ่ง YAGNI)

**Phase A (recovery):** re-enable worker **ultra-conservative + cooldown awareness** (ไม่ใช่แค่ batch เล็ก — ต้อง backoff เมื่อเจอ WAF, interval ยาว, ไม่ retry ทันที). **Success ≠ worker start ได้** แต่ = **worker survives without re-entering block loop**

**Production Restored declared เมื่อ:** new candidate → resolve success → qualification success → no WAF block → worker remains healthy — อย่างน้อย 1 cycle จริง (ไม่ใช่ generateToken ผ่าน 1 ครั้ง)

**Caveat (L-001):** test ผ่าน 1 ครั้ง = observation ไม่ใช่ characterization. ยังไม่รู้ VPS safe sustained throughput → characterize ทีหลัง (Phase A 24h = production characterization)

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
**บทเรียน:** "announcement search canary" ไม่พอ — ต้องมี **qualification canary** ที่วัด path ที่ธุรกิจพึ่งจริง
**How to apply:** ✅ **DEPLOYED 2026-06-03 (P1)** — เลือก **resolve heartbeat** (worker เขียน `resolve_heartbeat.json`: last_resolve_success_at = business outcome จริง) **แทน active AES canary** เพราะ canary จะยิง generateToken เพิ่ม = เสี่ยง burst + ขัด cooldown (บทเรียน INC-001 Rev3). deadman ตรวจ heartbeat ทุก 15 นาที → RESOLVE_DEAD (>75m+pending+ไม่cooldown) / WORKER_STALE (>12m) / RESOLVE_STUCK (cooldown ค้าง>2h) → Discord. INC-001 จะถูกจับใน ≤75 นาที (เทียบ 1.5 วัน)

### L-005 — External service กับ unknown limit ต้องมี rate-control envelope ก่อนถือว่า production-ready (2026-06-03, INC-001 Rev 3)
**Context:** INC-001 Rev 3 — worker ยิง resolve ทุก 2 นาที (timer) << WAF cooldown 30-40 นาที → worker **เติม traffic ก่อน cooldown ครบทุกครั้ง** → block ถูกต่ออายุเอง 1.5 วัน. 1.5-day outage **ไม่ใช่ "WAF ลงโทษ 1.5 วัน" แต่ "worker รักษา block state เองตลอด 1.5 วัน"** (positive feedback loop: burst → block → retry → ยิงซ้ำ → block นานขึ้น)
**บทเรียน:** external service ใดที่ limit ไม่รู้แน่ (RSS · Province API · Resolve API ล้วนเป็น external) **ต้องมี 3 อย่างก่อนถือว่า production-ready:**
1. **throughput envelope** — รู้/คุมว่ายิงได้กี่ call ต่อ window (ไม่ยิงไม่จำกัด)
2. **cooldown state** — รับรู้เมื่อโดน throttle แล้ว**หยุด** (ไม่ retry ทันที)
3. **recovery state** — กลับมายิงแบบ ramp ไม่ใช่ full-rate ทันที
**ไม่มี 3 อย่างนี้ = ระบบเป็นคนสร้าง outage เอง** (self-inflicted). Layer นี้คือสิ่งที่ยืด incident จาก *นาที* → *วันครึ่ง*
**How to apply:** ก่อน deploy worker ที่เรียก external API บน loop — ต้องมี backoff + cooldown awareness + ramp-up ไม่ใช่แค่ fixed-interval timer. ใช้ตอน scale 77 จังหวัด (volume สูง = ชน limit คลาสนี้ซ้ำแน่)

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

**Root Cause (Rev 3 — 2 layers):**
- **Layer 1 — Incorrect assumption:** `discovery reachable ⇒ resolve reachable` = **เท็จ** (Control Plane Assumption Failure). อธิบายว่า*ทำไม resolve ถึงพัง* แต่ไม่อธิบายว่า*ทำไมพังนาน 1.5 วัน*
- **Layer 2 — Missing rate-limit adaptation:** worker ไม่มี cooldown awareness / adaptive throttling / sustained throughput envelope → ยิง resolve ทุก 2 นาที << WAF cooldown 30-40 นาที → **block ถูกต่ออายุเอง** (self-sustained). **Layer 2 คือสิ่งที่ทำให้ incident ยืดจากนาที → วันครึ่ง** (ดู L-005)
- ⚠️ Rev 1-2 เข้าใจว่า "VPS โดน block ถาวร (datacenter IP)". Rev 3 (evidence: VPS ฟื้นหลัง pause) แก้เป็น **rate-control failure** — incident class เปลี่ยนจาก External Dependency Failure → Rate-Control Failure

**สิ่งที่ incident พิสูจน์เพิ่ม:** observability > cleverness — dead-man switch/telemetry (ที่เคยเป็น hypothesis) พิสูจน์คุณค่าจริง: ถ้าไม่มี telemetry เราจะยังเชื่อว่า "ตลาดเงียบ" ทั้งที่ qualification plane dead

**Recovery Plan:** P0.0 manual residential resolve (restore) → P0.1 Residential Resolve Worker (B) → P1 AES canary + qualification throughput alert + resolve success-rate alert → P2 measure residential dependency + Windows uptime → P3 Raspberry Pi decision

**Explicitly deferred:** proxy · VPN · ย้าย Discovery ไป residential · 77-province redesign (ยังไม่มี evidence ว่าจำเป็น)

---

### INC-001 Update — P0.0 finding: residential burst-limit (2026-06-03)

**🧠 Mental model change (รอบ 2):** Residential = **finite execution resource** (ไม่ใช่ "trusted unlimited zone")
- evidence: residential ผ่าน ~30 generateToken/burst → WAF block → cooldown >2 นาที → ผ่านอีก (VPS = permanent block, 0 burst)
- batch test: oldest 20 → resolved 14 (ทั้งหมด **expired**) · newest 20 → block ทั้งหมด (no AES token, หลัง burst ~40 calls)
- **architecture consequence:** Worker → **Queue + Capacity Management** (bottleneck = throughput ไม่ใช่ reachability)

**Severity wording (refined):**
- **Customer Impact = Unknown-to-Low** — open jobs ที่พลาดจริงกี่งาน ยังพิสูจน์ไม่ได้ (backlog ส่วนใหญ่ expired)
- **Systemic Risk = High** — Enrichment dead 1.5 วัน no alert = พิสูจน์แล้ว ("luck ≠ health": 0 งานใหม่ = incident ช่วง low-volume ไม่ใช่ system healthy)

**ADR-002 refinement:** Residential Resolve **Worker** → **Queue** (state machine: PENDING → READY → COOLDOWN → RETRY → DONE). Explicit assumptions: residential execution available · **rate-limited** · throughput managed by queue · **no assumption of unlimited capacity**

**Objective lock (เปลี่ยนรอบ 3):** Recover backlog → Restore notifications → **Validate forward-processing** (KPI = **path viability** ไม่ใช่ notification count). Step 1 สำเร็จเมื่อ: new candidate → resolve → qualify → enqueue **ทำงานได้** (ไม่จำเป็นต้องมี notification จริง ถ้า evidence บอกไม่มี open job)

**Recovery first · Characterization second** — อย่า probe burst regime ระหว่าง recovery (probe = consume scarce residential resource)
