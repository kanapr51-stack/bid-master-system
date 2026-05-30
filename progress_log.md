# Bid Master System — Progress Log

---

## งานที่ N+41: P1 — Dead-Man Switch (Protect Live System) (2026-05-31 ~00:10)

### สถานะ: ✅ เสร็จ

### Root cause / สิ่งที่ทำ
ระบบ live แล้ว → failure mode อันตรายสุด = **silent failure** (เจอจริง: harvest report success แต่ VPS token stale). ChatGPT+Claude converged: dead-man switch (P1) ก่อน root cause (P3) — เปลี่ยน silent→observable ก่อน

### Implementation
- `scripts/Sebastian_Province_Discovery.py`: เพิ่ม `_write_heartbeat()` — เขียน `last_discovery_run.json` ทุกรอบ (status=ok/no_data + counts)
- `scripts/health_deadman.py`: ตรวจทุก 15 นาที (VPS timer `bms-deadman`)
  - TOKEN_EXPIRED / HARVEST_STALE (>40 นาที ไม่ refresh) = CRITICAL [fast, ~35 นาที detect]
  - DISCOVERY_STALE (>14 ชม. เผื่อ overnight gap 12 ชม.) / DISCOVERY_NODATA = WARN
  - cooldown 60 นาที/issue กัน spam, **exit 0 เสมอ** (ไม่ทำให้ systemd fail)
- `deploy/systemd/bms-deadman.{service,timer}` + README — version-controlled (units อื่นยังอยู่บน VPS เท่านั้น)

### ทดสอบ (verified)
- detection logic ครบ 4 เคส (fixture stale token) ✅
- Discord alert ยิงจริง + cooldown กัน spam ✅
- healthy path: "✅ dead-man: healthy" exit 0 ✅
- heartbeat code: seed สำเร็จ `{status:ok, total:420}` ✅

### 🔴 Finding ใหม่ระหว่างทำ: discovery service timeout
- `bms-province-discovery.service` รัน **ทั้ง 2 จังหวัด timeout ที่ 15 นาที** (Result=timeout, killed) → heartbeat ไม่ถูกเขียน
- น่าจะ throttle-induced (ยิง API หนักทั้ง session: harvest/re-resolve/reclassify หลายรอบ) → empty-page retry 30s ballooning
- **สมมติฐาน: อาจเป็นสาเหตุบึงกาฬเคย=0** (รอบ schedule ทำนครพนมก่อน → timeout ก่อนถึงบึงกาฬ)
- **ยังไม่แก้ config** (ไม่แน่ใจว่า standing problem หรือ transient) → followup: monitor รอบ schedule 00:00 UTC; ถ้า recur → bump TimeoutStartSec + แก้ page-retry ballooning
- dead-man จับ timeout ได้ทางอ้อม (discovery_stale 14h) แต่ช้า — ควรพิจารณา check systemd Result โดยตรงภายหลัง

### Followup (priority หลัง P1 — ChatGPT converged)
- P2: feedback loop (👍/👎/ใหม่/โทรแล้ว) — fresh signal window จาก 16 ข้อความ
- P3: token harvest root cause (success-but-stale) + discovery timeout
- P4: เพิ่มอำเภอ+ตำบล (getProcurementDetail moiName+districtMoiId)
- P5: retire RSS (disable scheduler+alert, เก็บ code)

---

## งานที่ N+40: 🎉 P0 GO-LIVE — Notification จริงครั้งแรกถึงครอบครัว (2026-05-30 ~23:05)

### สถานะ: ✅ เสร็จ — MILESTONE

### Root cause / สิ่งที่ทำ
หลัง P2 + Q1 เสร็จ → report ChatGPT → converged Q2 (P0 ก่อน P1 ทันที, "analysis paralysis = ความเสี่ยงใหญ่กว่า feedback missing สำหรับ 5 family users"). คุณกัญจน์อนุมัติ ส่ง province-wide พร้อมเงื่อนไข "Controlled ≠ Blind → ผ่าน checklist ก่อน"

### Checklist 5/5 ผ่าน (4 งานบึงกาฬเปิดจริง)
① จังหวัด ✓ (hard/moiId=380000) · ② location ✓ (แขวงทางหลวง/รพ.บึงกาฬ/พาณิชย์จังหวัด/อบต.นากั้ง) · ③ deadline>now ✓ (4-10 มิ.ย.) · ④ link/PDF ✓ (templateId resolve) · ⑤ format ✓ (mobile-first)

### กลไก + ผล
1. backup `.env` → flip `BMS_PROVINCE_NOTIFY_MODE=preview→live`
2. reset 4 preview_held → pending → worker (mode=live) → **enqueue 4** (× 5 subs = 20)
3. LINE sender (BATCH_SIZE=1, drive ทีละตัว) → **delivered 16/16 ถึง 4 user จริง** (กัญจน์/Hong/ณฐมน/Mr.suvit คนละ 4 งาน), 4 fail = test account (fake LINE ID ตามคาด)
- subscription = province-level นครพนม+บึงกาฬ ทั้ง 5 คน (ตรง Q3)

### 🎯 North-Star prerequisite
"Has a real user received a real notification yet?" → **YES (ครั้งแรกของ BMS)**

### Followup / สถานะใหม่
- **mode=live (preview gate ปิด) = automation เต็ม** — งานใหม่ที่ qualify (นครพนม+บึงกาฬ) จะส่ง LINE อัตโนมัติ ไม่ผ่าน preview แล้ว (ตาม procedure "ผ่าน 3 งาน → เอา gate ออก")
- **P1 feedback loop** = priority ถัดไป (👍/👎/ใหม่/โทรแล้ว) — วัด value (Useful Rate / Discovery / Action)
- เฝ้าดู reaction ครอบครัว 30 วัน → North-Star "ไม่เคยเห็น + นำไปทำต่อ"
- ถ้าต้องการกลับ preview: flip env กลับ + restore `.env.bak.*`

---

## งานที่ N+39: P2 — บึงกาฬ Full Ingest + Recency-Gated Qualification (2026-05-30 ~21:45)

### สถานะ: ✅ เสร็จ

### Root cause / สิ่งที่ทำ
ก่อนหน้า: projects_seen มีแต่ นครพนม (730 province_api) — **บึงกาฬ = 0 rows** ทั้งที่อยู่ใน PROVINCE_MOI (380000) แล้ว → coverage gap จังหวัดที่ 2 ของ family beta (อ.บึงโขงหลง)

flow: harvest token สด (Chrome9222, 1798s) → push VPS → dry-run นับ → ingest → recency-gated qualification

### Decision: เปลี่ยนจาก "epoch suppress ทั้งหมด" → "recency-gated" (evidence-based)
- นครพนม 730 ถูก suppress เพราะ ingest **ก่อน** epoch (first_seen 06:46Z < epoch 10:34Z) — wholesale
- บึงกาฬ 347 ingest **หลัง** epoch → ถ้าปล่อย worker จะ qualify ทั้ง 347 (resolve PDF 347 ครั้ง = เปลือง + WAF risk)
- **evidence:** projectId prefix (BE YYMM) distribution → แค่ ~25 ตัว (≥6904) อาจยังเปิด, 322 ตัว (≤6903) เกือบแน่ปิดแล้ว
- **วิธี:** pre-insert project_locations เอง — recent(≥6904)→`pending`, เก่า→`suppressed_backlog` (terminal). seed query skip ทั้งหมด (NOT IN) → งานใหม่อนาคต qualify ปกติ **ไม่แตะ epoch** (นครพนม ไม่กระทบ)

### Fix / ผล
- ingest: **+347 บึงกาฬ** (420 total − 73 ยกเลิก), 0 dup
- qualification: 322 suppressed_backlog + 12 suppressed_expired + 4 **preview_held** + 9 pending (drain ต่อ)
- **resolver ทำงานบนบึงกาฬด้วย (2nd province validated): failed=0** บน 16 ตัวที่ resolve
- **4 งานบึงกาฬเปิดจริง** surface เข้า Discord preview (mode=preview, **ไม่มี LINE หาครอบครัว**):
  - 69049214773 แขวงทางหลวงชนบทบึงกาฬ ฿12M (สะพาน+ถนน) deadline 2026-06-10
  - 69059480101 รพ.บึงกาฬ ฿1.3M (เลเซอร์รักษาตา) deadline 2026-06-08
  - 69059447656 พาณิชย์จังหวัดบึงกาฬ ฿1.87M (จัดงานแสดงสินค้า) deadline 2026-06-05
  - 69059255961 อบต.นาก... ฿1.32M (ถนน คสล.) deadline 2026-06-04
- sanity: projects_seen 1,077 total, dup=0, notification_queue ไม่เปลี่ยน (7, pending 0, province_qualified 0) ✓

### Q1 Refinement: announceDate reclassification (ChatGPT+Claude converged รอบ 2)
หลัง report ChatGPT 2 รอบ — ตกลง: projectId-prefix = *creation signal* ไม่แม่น, ใช้ **announceDate** (*opportunity signal*) re-classify backlog **ครั้งเดียว → terminal** (ไม่ใช่ non-terminal loop — base rate backlog = almost all expired → false-suppress risk < re-eval cost)
- `scripts/reclassify_backlog_by_announcedate.py` (reusable, --window-days 45): re-fetch list → announceDate (ISO CE) → suppressed_backlog ที่ announce ≥ cutoff + failed_provider_error → pending
- **เจอจริง 3 งาน prefix เก่าแต่ announce ล่าสุด** (ที่ prefix-gate จะทิ้งถาวร): `68119177741` prefix 6811→announce 2026-05-11 (ห่าง 6 ด.!), `69029066538`, `69039425551` → ยืนยัน announceDate ถูก ไม่ใช่ทฤษฎี
- resolve 7 ตัว (3 backlog + 4 provider_error) → **expired ทั้งหมด, failed=0** → resolver=authoritative gate ทำงาน, terminal ปลอดภัย
- final บึงกาฬ: suppressed_backlog 319 + suppressed_expired 24 + preview_held 4 = 347

### Followup
- **announce_date column** (long-term): ChatGPT+Claude ตกลงว่า announceDate = first-class domain field (ใช้ backlog/heuristic/analytics/drift) → ควรเพิ่ม column ใน projects_seen เมื่อ consumer ถัดไป (P4 drift) มาถึง — ตอนนี้ re-fetch ครั้งเดียวพอ (YAGNI)
- **go-live config note:** preview เป็น จ.บึงกาฬทั้งจังหวัด ไม่ใช่เฉพาะ อ.บึงโขงหลง — ChatGPT แนะ beta=ระดับจังหวัด + instrument อำเภอ/ระยะทาง + เก็บ 👍/👎 30 วัน → ค่อย tighten (= P1 feedback loop)
- 4 preview_held = candidate จริงสำหรับ P0 go-live 5-item checklist

---

## งานที่ N+38: Post-Incident Hardening — Daily Backup + Test Harness Separation (2026-05-29 ~23:00)

### สถานะ: ✅ เสร็จ

### Root cause / สิ่งที่ทำ
Incident: Claude รัน `python Sebastian_Customer_DB.py` ตรงๆ บน VPS → `__main__` block มี `os.remove(db)` → ลบ production DB → customers 5 → 1
Recovery: grep LINE IDs จาก sender logs → re-seed 4 customers ภายใน 5 นาที
**delivery_log history: accept data loss** (3 วัน, 2-3 users, ไม่คุ้มกับ reconstruct)

### Fix / ผล
- `scripts/backup_db.py` — daily backup 03:00, 14-day retention, `/opt/bms/backups/`
- `scripts/dev_reset_db.py` — destructive reset แยกออกจาก production module, production guard
- `Sebastian_Customer_DB.py __main__` — smoke test only, ไม่มี DB wipe
- `bms-backup.timer` active บน VPS, ทดสอบ manual: `bms_20260529.db` (108 KB) ✅
- Commits: `935f226` (--reset guard), `71109d5` (backup + separation)

### Followup
- schema_version tracking → defer (ยังไม่จำเป็นสำหรับ family beta)
- project_locations จะ repopulate อัตโนมัติจาก RSS Notifier ครั้งถัดไป

---

## งานที่ N+37: Real User Onboarding — ณฐมน ธงยศ + Mr.suvit (2026-05-29 ~22:00)

### สถานะ: ✅ เสร็จ

### Root cause / สิ่งที่ทำ
- ณฐมน ธงยศ: self-onboard ผ่าน LINE OA → follow → ตั้งค่า → นครพนม+บึงกาฬ ✅
- Mr.suvit: follow แต่ไม่พิมพ์ตั้งค่า → Claude insert provinces ใน DB + ส่ง proactive onboarding message
- Test notification inject → delivered 4/5 (1 ล้มเหลวเพราะ fake LINE ID ของ test account)

### Fix / ผล
- 2 real users active ใน production system
- Mr.suvit ได้รับ welcome message พร้อมคำสั่งทั้งหมด

---

## งานที่ N+36: Enrichment Worker fixes + Daily Digest enrichment section (2026-05-29 ~17:45)

### สถานะ: ✅ เสร็จ — deployed บน VPS

### Root cause / สิ่งที่ทำ
- `_save_retry` เพิ่ม MAX_ATTEMPTS=5 → ถ้า attempts >= 5 mark `enrichment_status='failed'` แทน retry ไปเรื่อยๆ
- Pass 2 repair: หลัง batch loop ทุกรอบ — SELECT success+target+not-in-queue → re-enqueue (prevent success-but-never-notified)
- Daily Digest เพิ่ม `enrichment_section()`: total/success/pending/failed + oldest_pending_age + failed threshold warning
- tasks_section เพิ่ม Enrich_Worker log check

### Fix / ผล
- Commit `170be62` pushed + deployed บน VPS
- VPS git pulled สำเร็จ (reset untracked Sebastian_Enrichment_Worker.py ก่อน)
- 232 pending items มี next_retry_at=17:53-17:55 → timer จะ drain อัตโนมัติ

### Followup
- Monitor enrichment drain: คาดว่า 232 → 0 ภายใน 2026-05-29 ~19:30 (ขึ้นอยู่กับ WAF uptime)
- ถ้า target province hit → จะมี LINE notification จริงๆ
- Day 5-7: verify 5 readiness criteria ก่อน onboard พ่อ-แม่

---

## งานที่ N+35: Discovery/Enrichment Plane Separation + eGP Location Enrichment (2026-05-29 ~17:30)

### สถานะ: ✅ เสร็จ

### Root cause / สิ่งที่ทำ
- เดิม Notifier v2 ทำทั้ง discovery + enrichment → rate limit ทำให้ 232/260 fail
- แยก Notifier v3 (discovery only, ไม่ call API) + Enrichment Worker (batch 20, sleep 1.5s)
- eGP `getProcurementDetail` return `provinceMoiId` → MOI_PROVINCE_MAP prefix 2 digits → province_name
- `project_locations` table: hard/unknown confidence, pending/success/failed status

### Fix / ผล
- Commits: `e2d020c` (plane separation) + `385038e` (location enrichment)
- 7 timers active บน VPS รวม bms-enrichment-worker (every 2 min)
- 28 projects enriched สำเร็จ (ยังไม่ใช่ target province)

---

## งานที่ N+34: X-Announcement-Token Reverse Engineering สำเร็จ (2026-05-28 ~21:00)

### สถานะ: ✅ เสร็จ — พร้อม integrate

### Root cause / Discovery
eGP process5 เพิ่ม `X-Announcement-Token` requirement ซึ่งทำให้ API เดิมได้ `{"validateAnnouncementToken": false}`

### Reverse Engineering ผล

**AES Key**: `"RDCrypto"` (CryptoJS passphrase, EVP_BytesToKey MD5)

**Token Generation Flow (ไม่ต้อง Auth!):**
```
1. key = encryptData(encryptData({projectId}))
   encryptData(obj) = URL_encode(AES_CBC_encrypt(JSON.stringify(obj), "RDCrypto"))
2. POST /egp-atpj27-service/pb/a-egp-allt-project/announcement/generateToken
   Body: {"key": key}
   Headers: noToken:noToken, noDataProfile:noDataProfile
3. Response: {"data": "<token>"} → token valid 30 minutes
```

**Endpoints ที่ทำงานได้ (ใช้ X-Announcement-Token header):**
- `GET /egp-atpj27-service/pb/a-egp-allt-project/announcement/getProjectDetail?projectId=X`
  → stepId, flowSeqno, announceType, projectStatus
- `GET /egp-atpj27-service/pb/a-egp-allt-project/announcement/getProcurementDetail?projectId=X`
  → priceAgree, reportDate, announceDate
- `GET /egp-atpj27-service/pb/a-egp-allt-project/announcement/getProcureResult?projectId=X`
  → procureResultList → winner (receiveNameTh, receiveTin, priceAgree, resultFlag)

**Note:** Cloudflare Turnstile ต้องการเฉพาะ Search list endpoint ไม่ใช่ project-detail endpoints

### Implementation
- `scripts/probe_generate_token.py` — proof of concept สำเร็จ
- ต้อง integrate เข้า `scripts/process5_http_client.py`

### Followup
- Integrate token generation เข้า process5_http_client.py
- Test กับ project IDs ใน target provinces (อ.บ้านแพง, อ.บึงโขงหลง)
- Token expiry 30 min → cache token per projectId (หรือ share token 1 อัน/รอบ)

---

## งานที่ N+33: 10-Day Family Beta Sprint Plan (2026-05-28 17:00)

### สถานะ: 📋 แผน — รอ execute

### Goal
ให้พ่อและแม่ของคุณกัญจน์ใช้ BMS ได้จริงภายใน 10 วัน (deadline ~2026-06-07)

Requirements:
1. VPS — รัน workers เสถียร 24/7
2. Customer portal — ตั้งค่าจังหวัดผ่านเว็บได้เอง
3. LINE personal — แจ้งเตือนไปยัง LINE ส่วนตัวแต่ละคนแยกกัน

### Architecture ที่ตัดสินใจ (ChatGPT confirmed ✅)

```
Portal UI        → Vercel (คงเดิม)
Webhook API      → Vercel (คงเดิม)
    ↓ POST to VPS
FastAPI service  → VPS (ใหม่)
    ↓
SQLite DB        → VPS (ย้ายจาก local)
RSS Notifier     → VPS (ย้ายจาก local)
LINE Sender      → VPS (ย้ายจาก local)
Queue Processor  → VPS (WAF bypass ด้วย IP ใหม่)
Discord Digest   → VPS (centralized observability)
```

Key decisions:
- SQLite ต่อไป (ไม่ migrate Postgres) — single writer, WAL, low QPS
- Paid VPS (ไม่ใช่ Oracle Free) — reliability > cost ในช่วง deadline
- Spec: Ubuntu 22.04, 2 vCPU, 2-4 GB RAM (Vultr/DigitalOcean ~$12-18/เดือน)

### Sprint Plan

| Day | งาน |
|---|---|
| 1-2 | ซื้อ VPS + install Python/git + ย้าย DB + workers + ทดสอบ WAF bypass |
| 3-4 | FastAPI webhook service + portal wiring → bms_customers.db |
| 5-6 | LINE follow → auto-create customer + auto-reply portal link |
| 7-8 | ทดสอบ end-to-end กับพ่อ-แม่จริง |
| 9-10 | Fix bugs + confirm digest + monitoring |

### Defer (ไม่ทำใน 10 วัน)
- WAF perfect recovery (RSS provisional พอแล้วสำหรับ beta)
- Postgres migration
- Multi-tier billing
- 77-province extraction ครบ
- Advanced analytics

### Followup
- RSS semantic experiment: probe ทุก 30 นาที จนกว่าจะ UP — บันทึก pubDate distribution
- WAF test จาก VPS IP ทันทีหลัง setup

## งานที่ N+32: RSS-First Pilot + Schema v1.5 source_stage (2026-05-28 11:30)

### สถานะ: ✅ เสร็จ

### สิ่งที่ทำ

**Schema v1.5 — source_stage (latent metadata)**
- เพิ่ม `source_stage TEXT` ใน notification_queue
- values: `rss_provisional` | `api_enriched`
- ยัง NOT active ใน delivery logic — เก็บไว้เป็น upgrade path สำหรับอนาคต

**Pilot Semantics Decision (intentionally deferred):**
```
Current pilot semantics:
  - One notification per project_id (UNIQUE constraint preserved)
  - RSS-first notifications are terminal notifications during pilot phase
  - Enriched re-notification intentionally deferred — not oversight, scoped decision
```
เหตุผล: enriched re-notification มี complexity สูง (supersession, "spam vs refinement",
snapshot invalidation, versioned payloads, customer preference) — พิสูจน์ใน Phase 2+

**RSS Notifier** — pass `source_stage="rss_provisional"` ทุก item ที่ enqueue

**LINE Sender format_notification()** — เพิ่ม provenance footer:
```
📡 ข้อมูลเบื้องต้นจาก RSS
```
เมื่อ `source_stage == "rss_provisional"` เท่านั้น

**WAF probe result (10:26):** Scenario C — canary INVALID (3863ms), silence ต่อ

**Working hypothesis (H2-style):**
Multi-day persistent interaction-history-sensitive regime explains observations better than
short-horizon decay (H1). VALID→INVALID during 21h silence weakens H1 assumption
"inactivity moves toward healthier regime". Key signal: stable 3800ms latency plateau
across 9+ runs (mechanistically robust), not VALID→INVALID (could be classifier drift).

**Probe trigger framework (declared):**
- Class 1: Identity/interaction conditions changed
- Class 2: Upstream regime evidence changed
- Class 3: Crossed hypothesized upstream persistence boundary (must declare H first)
- Class 4: Operational necessity (label as such)
Time-based Class 3 requires declared hypothesis — not numerology.

### Followup
- รอ LINE user ID จากคุณกัญจน์ → `python scripts/seed_self_notify.py --line-id U...`
- RSS-first pilot: `python scripts/Sebastian_RSS_Notifier.py` → `python scripts/Sebastian_LINE_Sender.py --dry-run` → live send
- R2 probe: เมื่อมี Class 1/2/3(H-declared) trigger เท่านั้น

## งานที่ N+31: WAF Morning Probe — Decision Framework (2026-05-28 03:30)

### สถานะ: ⏳ รอ probe 06:00

### Silence experiment state
- Queue Processor OFF ตั้งแต่ 2026-05-27T13:20 (~14h ณ เวลาเขียน)
- eGP API: UNKNOWN (needs_revalidation)
- Last canary success: 2026-05-27T13:06 → early_stop avg 3,865ms

### Probe plan 06:00
```
1. canary probe อย่างเดียวก่อน — ดู latency
2. ถ้าผ่าน → run 1 unseen D0 ID เท่านั้น → STOP ทันที
3. ห้าม resume scheduler แม้ healthy
4. ห้าม run เพิ่มแม้ผลดี
```

### Decision tree (จาก ChatGPT review — ✅ ทั้งหมด)

**Scenario A: canary pass + 1 ID < 600ms**
- Interpret: "consistent with inactivity-linked recovery" (ไม่ใช่ "recovery proven")
- Action: บันทึก latency + geometry + time-of-day → STOP
- Next: รอ +6h หรือ next morning pulse ก่อน Phase R2
- ห้าม: run เพิ่ม, resume scheduler, conclude stable

**Scenario B: canary pass + 1 ID ≥ 3,000ms**
- Interpret: "14h silence insufficient under current identity"
- Action: extend silence, reduce probing frequency massively
- Next experiment: longer silence (ยังไม่เปลี่ยน identity variables)
- ห้าม: accept degraded, adaptive retry hammering, continuous probing

**Scenario C: canary fail**
- Interpret: "probe lane itself degraded" — ไม่ใช่ "fully banned"
- Action: หยุด probe ทั้งหมด 24-48h minimum
- ห้าม: test more (measurement itself = aggressive behavior ตอนนี้)

### Re-engagement phases (เฉพาะหลัง Scenario A)
```
R1: 06:00 — 1 ID → STOP                        ← วันนี้
R2: +6h later — 3 IDs spaced → observe geometry
R3: +1 day — 5 IDs
    → 10 IDs → 15 IDs → enable scheduler
```
**Core question: "what accumulates distrust?"** ไม่ใช่ "can we get 1 successful response?"

### Key insight
"recovery probe itself changes future interaction-history"
→ ดังนั้น STOP after 1 ID เสมอในรอบนี้

### Script
`scripts/run_morning_probe.ps1` — พร้อมไว้รัน 06:00

---

## งานที่ N+30: Notification Delivery Pipeline — Phase 2 Complete (2026-05-28)

### สถานะ: ✅ เสร็จ — รอ LINE user ID ก่อน first live send

### สิ่งที่สร้าง

**3-plane notification architecture:**

| Plane | Script | Role |
|---|---|---|
| Discovery | Sebastian_RSS_Scraper.py | RSS → rss_queue.json (append-only log) |
| Classify+Enqueue | Sebastian_RSS_Notifier.py ← **NEW** | province extract → confidence gate → notification_queue |
| Deliver | Sebastian_LINE_Sender.py ← **NEW** | LINE push API, state machine, retry |

**Schema ที่เพิ่ม (v1.1 → v1.4):**
- `projects_seen`: + project_name, dept_id, dept_name, extraction_confidence, source
- `notification_queue`: + retry_count, sending_at, worker_id, snapshot fields, is_backfill
- `delivery_log`: append-only audit log (replaces sent_notifications)

**Architecture decisions (confirmed ทุกจุดกับ ChatGPT):**
- Option C hybrid: RSS = provisional signal, API enrich = async
- Confidence gate: `extract_province(title) ∈ TARGET_PROVINCES` → "high" (wrapper heuristic)
- Snapshot semantics: province/project_name/dept_name copy ลง notification_queue ตอน enqueue
- rss_queue = immutable discovery log (ไม่เพิ่ม processed flag — projects_seen คือ dedup)
- is_backfill: items ก่อน notifier epoch → 📦 label (ไม่ใช่ 🔔)
- BATCH_SIZE=1 จนกว่า trust semantics validated

### Dry-run results
```
rss_queue: 1,273 total → 260 eligible D0
Province extracted (target): 3/260 = 1.2% → นครพนม
All 3 = BACKFILL (queued 2026-05-26, ก่อน notifier epoch)
```

### Pilot launch sequence (confirmed โดยคุณกัญจน์)
```
Phase 0: seed customer (ต้องการ LINE user ID จาก LINE Developers Console)
Phase 1:
  1. seed_self_notify.py --line-id U... --provinces นครพนม บึงกาฬ
  2. Sebastian_RSS_Notifier.py --dry-run   → verify classification
  3. Sebastian_LINE_Sender.py --dry-run    → verify formatting
  4. Sebastian_LINE_Sender.py              → manual live send (1 item)
  5. inspect LINE message + delivery_log + queue state + dedup
  6. rerun sender → verify no duplicate
  7. เปิด Task Scheduler BidMaster_RSS_Notifier + BidMaster_LINE_Sender (LAST STEP)
```

### Pilot success metrics (4 layers)
- Transport: LINE API success, queue transitions ถูก, no stuck, retry works, no duplicate
- Semantic: province ถูก, title ไม่ misleading, backfill label ถูก
- Usability: readable ใน <3 sec scan
- Operational: scheduler rerun safe, restart safe, replay safe, DB consistent
- Observation window: 3-5 วัน ก่อนเพิ่ม customer จริง

### Blocking
- LINE user ID: ดูจาก LINE Developers Console → Basic Settings → "Your user ID"

### Followup
- เปิด Task Scheduler หลัง first live send validate แล้วเท่านั้น
- WAF morning probe (~06:00) ยังค้าง — Queue Processor ยัง OFF

---

## งานที่ N+29: Behavioral Characterization — WAF Trust Envelope Day 1 (2026-05-26 → 27)

### สถานะ: ⏳ กำลังเก็บข้อมูล — รอ 06:00 pipeline เช้านี้

### สรุปสถานะ ณ 00:45 น.

**Queue Processor runs วันนี้:**
| Run | เวลา | Result | avg_ms | p95_ms | gap_min |
|-----|------|--------|--------|--------|---------|
| #1 | 18:21 | clean_pass 15/15 | N/A | N/A | — |
| #2 | 18:35 | clean_pass 15/15 | 657 | 3,429 | 14.6 |
| #3 | 19:05 | clean_pass 15/15 | 450 | 519 | 30.0 |
| #4 | 19:36 | **early_stop 0/15** | 3,875 | 3,937 | 30.1 |
| #5 | 22:06 | **early_stop 0/15** | 3,878 | 3,905 | 150 |
| #6 | 00:36 | **early_stop 0/15** | 3,908 | 3,913 | 150 |

**API state ตอนนี้:** BLOCKED until 02:36 น.
**RSS:** ยังไม่กลับ — last item queued_at = 2026-05-26T06:54:00
**Queue depth:** ~167 items (D0:148, B0:43, W0:21 ตอนเริ่ม)

### สิ่งที่รู้แล้วจากการ characterize
- WAF มี memory — behavior ไม่ stateless
- Pattern: 3 clean_pass → degraded regime เริ่มทันที
- Degradation = distribution-wide (avg≈p95 ทั้ง 3 degraded runs) ไม่ใช่ spike เดี่ยว
- 2.5h inactivity ไม่ช่วย recovery เลย (Run #5, #6 ยัง 3,900ms)
- Canary pass ≠ batch safe (canary = "not fully banned" เท่านั้น)
- Control plane ทำงานถูกต้อง (blocked_until, scheduler, telemetry ครบ)

### สิ่งที่ยังไม่รู้
- Variable อะไรที่ trigger recovery จริง (time-of-day? cumulative volume? IP reputation?)
- Memory half-life ของ WAF
- 2h cooldown อาจไม่ใช่ค่าที่ถูก — ตั้งขึ้นมาโดยไม่มี evidence

### Next high-value datapoint
**06:00 pipeline พรุ่งนี้** — ถ้า clean_pass → consistent with time-of-day-linked recovery
ถ้า early_stop อีก → governing variable ไม่ใช่ time-of-day

### Silence Experiment (เริ่ม 2026-05-27T13:20)
- BidMaster_Queue_Processor: **DISABLED** ตอน 13:20 น.
- Frame: "silence experiment" ไม่ใช่ "cooldown" — ยังไม่รู้ว่า upstream มี notion ของ recovery window จริงไหม
- Upstream จะเห็น "absence" ครั้งแรก — สำคัญถ้า scoring เป็น rolling interaction-based

**Morning probe plan (~06:00–08:00 พรุ่งนี้):**
1. canary probe อย่างเดียวก่อน — ดู latency
2. ถ้าผ่าน → run **1 ID เดียวเท่านั้น** โดยเลือกแบบ deterministic:
   "first unseen D0 after RSS recovery timestamp" (ไม่เลือกด้วย intuition)
3. Observe latency geometry → **STOP ทันที**
4. ห้าม resume scheduler แม้ healthy
5. ถ้า healthy → ยังไม่แปลว่า "silence fixed it" — อาจเป็น low-volume allowance หรือ probe tolerance
   next question ยังคือ: "does sustained interaction re-trigger degradation?"

**Interpretation rules:**
- ถ้า healthy → "consistent with inactivity-linked recovery under current identity"  (ไม่ใช่ "24h reset proven")
- ถ้ายัง degraded → "24h inactivity alone insufficient under persistent identity" (ตัด time-only hypothesis)

### Engineering backlog (รอ characterization เสร็จก่อน)
- P0: Fix GH Runner (GHA `shell: pwsh`) — ง่าย, 30 นาที
- P1: Winner sweep script แยกสำหรับ W0 — ปานกลาง
- P2: CGD integration — ปานกลาง-ยาก
- P3: Scale 77 จังหวัด — ยากที่สุด

### Params ที่ freeze อยู่ (ห้ามเปลี่ยนจนกว่า characterization จบ)
- limit=15, jitter=4-9s, workers=3, cooldown=2h (early_stop), cooldown=30min (canary_fail)

---

## งานที่ N+28: Adaptive Ingestion Control Loop — Universe B Day 1 (2026-05-26)

### สถานะ: ✅ เสร็จ (commits af0e915→3be472c) / ⏳ characterization phase คืนนี้

### สิ่งที่ทำ
- Universe B เกิด 12:43 น. — 3 rows แรก (discovered_at + enrichment_version=v2_process5)
- --from-queue ย้ายออกจาก GHA ไป local Task Scheduler (eGP behavioral block ต่อ datacenter IP)
- Local machine = ingestion authority, GHA = maintenance layer
- BidMaster_Queue_Processor: canary probe + early_stop + blocked_until + jitter 4-9s
- Queue Health Snapshot: depth, oldest_age, drain_eta_hours, drain_eta_confidence
- failure_mode taxonomy: canary_fail | early_stop | partial | zero_processed | clean_pass
- Envelope history rolling last 5 (EWMA-lite, non-stationary env)

### Commits
- af0e915: Queue Processor + limit 15 + jitter
- 680ba17: Canary probe + early_stop (3 consecutive invalid)
- b16810a: blocked_until persistence (circuit breaker)
- 123e2cb: time-to-block envelope logging
- 3058e9c: queue_health.py + weighted D0>B0>W0 sort + drain_eta
- 42e7b0c: envelope history rolling-5 + drain_eta_confidence
- 3be472c: failure_mode classification ทุก code path

### สถานะ 18:00 Playbook
1. Manual trigger: `.\scripts\run_queue_processor.ps1`
2. Watch canary → ถ้า HEALTHY + 3+ IDs valid → Enable-ScheduledTask BidMaster_Queue_Processor
3. เก็บ failure_mode จากรอบแรก — Scenario B (partial/early_stop) คือ valuable signal

### TODO พรุ่งนี้ (หลังมีข้อมูลคืนนี้)
- [ ] Add `first_invalid_after_n_requests` (≈ processed_before_stop + 1) ใน envelope — raw data มีแล้ว
- [ ] Add `time_to_first_invalid_seconds` (run_started_at → first_invalid_at) — raw data มีแล้ว
- [ ] เปลี่ยน drain_eta_hours ให้ใช้ actual rolling throughput แทน bootstrap 80%
- [ ] Review tonight's failure_mode pattern → diurnal trust curve เริ่มเห็น?
- [ ] Add `rss_avg_response_ms` + `rss_latency_p95` ใน RSS workflow log — latency inflation อาจเป็น early warning ก่อน canary fail
- [ ] Cross-correlate: ถ้า RSS latency สูงขึ้น + API partial degradation พร้อมกัน → strengthen shared reputation hypothesis

### Insight สำคัญที่บันทึกไว้
- zero_processed ≠ canary_fail: probe path trusted แต่ sustained fetch ถูก downgrade คนละ phenomenon
- partial + early_stop = signature ของ upstream WAF mood ณ เวลานั้น
- multi-run stability > single-run clean_pass ก่อน scale ใดๆ
- goal คืนนี้: observe shape of degradation ไม่ใช่ drain queue

---

## งานที่ N+23: Dept ID Coverage Research + Global RSS Mode (2026-05-21)

### สถานะ: ✅ เสร็จ (commit ec190bf)

### สิ่งที่ค้นพบ
1. เราสแกน deptId 0001-9999 ครบแล้ว → พบ 57 active D0 (max ID=2603)
2. ไทยมี 8,500+ หน่วยงาน แต่ส่วนใหญ่ไม่มี D0 ตอนนั้น (เป็น W0/P0 หรือไม่มีโครงการ)
3. **Breakthrough: Global RSS (ไม่ระบุ deptId) → คืน 20 items จากทุก dept ทั่วประเทศ!**
4. 5-digit deptId (10000+) ไม่มีงาน → confirmed 4-digit only
5. P0/B0/W0 ใน range 0001-0300 ไม่ได้ depts เพิ่ม

### Fix ที่ทำ
- เพิ่ม `--global` mode ใน Sebastian_RSS_Scraper.py
  - poll D0+P0+W0 โดยไม่ระบุ deptId → ครอบคลุม อบต./เทศบาล/รัฐวิสาหกิจทุกแห่ง
  - ทดสอบ: 60 items, 59 new queued ในครั้งแรก ✅
- อัปเดต GHA workflow: global step (2 min) + per-dept full-poll (8 min) ทุกชั่วโมง

### Followup
- กลับมาทำ Portal ข้อ 2-10

---

## งานที่ N+22: Portal Redesign v3 — ทำใหม่ตาม brief จริง (2026-05-21)

### สถานะ: 🚧 กำลังทำ — ⏸ pause (ไปทำ RSS ก่อน)

### ความคืบหน้า
- ✅ ข้อ 1: discount ทุก bidder จาก price_proposal, per-job %, reliability score, ไม่จำกัดจำนวน (commit 96fec3e, deployed)
- 🔲 ข้อ 2: History 2 tab (ค้นหาคู่แข่ง / บริษัทฉัน), layout column ไม่ใช่การ์ด
- 🔲 ข้อ 3: Classes → บริษัท, เพิ่มบริษัท, ประเภทธุรกิจ checkbox
- 🔲 ข้อ 4: พื้นที่ครอบคลุม — slider ตรง, Haversine แม่น, Leaflet map จริง
- 🔲 ข้อ 5: Keywords defaults จาก deep research + fix ปุ่มบันทึก
- 🔲 ข้อ 6: Budget (บาท) + SME/MIT/เวลาแจ้งเตือน per company หลัง keyword
- 🔲 ข้อ 7: Profile — ข้อมูลคน (ชื่อ/gmail/โทร/LINE) + บริษัทแต่ละการ์ด
- 🔲 ข้อ 8: Star per company (popup ถามบริษัท) + งานที่สนใจแยกบริษัท
- 🔲 ข้อ 9: ประวัติประมูลตัวเองแยกรายบริษัท
- 🔲 ข้อ 10: Upload ไฟล์แยกรายบริษัท

### Followup
- กลับมาทำ Portal ข้อ 2-10 หลังจัดการ RSS เสร็จ

---

## งานที่ N+21: Portal Redesign v2 — 10 items (2026-05-21)

### สถานะ: ⚠️ ไม่ตรง brief — ทำใหม่ใน N+22 (commit 047f010)

### สิ่งที่ทำ
ทำ Portal Redesign ครบ 10 ข้อในรอบเดียว:

1. **DB**: `competitor_profiles` materialized view เพิ่ม `avg_discount_from_budget_pct` + `stddev_discount_pct` — budget column มี comma จึงต้องใช้ `REPLACE(budget, ',', '')` ก่อน cast
2. **History**: discount% per bidder จาก budget, 3-tab layout (งาน/บริษัท/บริษัทฉัน), `ProfileView` stats 6 ช่อง, own-company bid history tab
3. **Nav**: เพิ่ม "ประวัติ" tab ใน bottom nav → 5 items, font-size 9px
4. **Classes**: rename "Business Class" → "บริษัท", keywords เป็น checkboxes per type (12 ประเภท), Leaflet+OSM map preview, per-company filter tab (budget/SME/MIT/notifyTime), file upload tab
5. **Profile**: เพิ่ม LINE USER ID, account status grid, expiry + days left (แดงถ้า ≤7 วัน)
6. **World**: star/favorite system, "งานที่สนใจ" section ด้านบน, toggle persist ลง DB
7. **APIs**: `/api/portal/history/mine` (own bids by company name) + `/api/portal/upload` (Vercel Blob + graceful fallback)
8. **Deps**: leaflet, @types/leaflet, @vercel/blob

### Fixes ระหว่างทาง
- Budget มี comma format `'24,600,000.00'` → REPLACE before NUMERIC cast
- Python Windows CP1252 UnicodeEncodeError → ลบ emoji จาก print statements
- Leaflet SSR error → `dynamic(() => import(...), { ssr: false })`
- KeywordEditor `onSave` → `onClose` (กด บันทึก แล้วไม่ย้อน)

### Followup
- Push to Vercel (ต้อง confirm)
- ตั้ง `BLOB_READ_WRITE_TOKEN` ใน Vercel env vars สำหรับ file upload

---

## งานที่ N+20: ซ่อม RSS Catalog — กู้ 475→2111 + harden workflow (2026-05-20 13:30)

### สถานะ: ✅ เสร็จแล้ว (commit b7e6044)

### Root Causes ที่เจอ (4 อย่างซ้อนกัน)
1. **catalog หาย**: `gentle_scan_egp.py` สร้าง 2091 entries (May 18 22:00) แต่ไม่ commit → ทุกครั้งที่ dashboard_extractor ทำ `git pull` (commit e714fdf) → reset เป็น 475 entries
2. **dashboard โกหก**: `rss_catalog_stats()` ใช้ `max(catalog_file, last_run.catalog_size)` → แสดง 2111 ทั้งที่ไฟล์จริง 475
3. **GHA timeout**: POLL_WORKERS=4 × 15s timeout × 2111 depts → 10 นาที (success case), 25+ นาที (server ช้า) → cancelled
4. **Commit late**: catalog commit step อยู่หลัง queue refresh → cancelled = catalog หาย (ไม่ถูก commit)

### Fixes
- ✅ กู้ catalog 475 → 2111 จาก `git stash` (มี diff +8775 lines เก็บไว้)
- ✅ `dashboard_extractor.py`: ใช้ catalog file เป็นความจริง ลบ max() fallback
- ✅ `Sebastian_RSS_Scraper.py`: POLL_WORKERS 4 → 8, timeout 15s → 10s (fail-fast)
- ✅ `.github/workflows/rss_scraper.yml`:
  - job timeout 25 → 35 นาที
  - step-level timeout 15 นาที (แต่ละ step)
  - **early catalog commit** ก่อน queue refresh + `if: always()`

### ผลลัพธ์
- catalog file: 2111 entries (41 active, 2070 empty, 21.11% coverage)
- dashboard แสดงเลขจริง: 2111
- GHA run ต่อไป จะใช้ code ใหม่ — มี slack timeout มากขึ้น + commit ก่อน

### Followup
- monitor GHA run ใหม่ (26145215108) ว่า poll เร็วขึ้นจาก 10 → ~5-6 นาที (8 workers) ไหม
- ถ้า server ยังบล็อก local IP อยู่ → ต้องพึ่ง GHA อย่างเดียว

---


## งานที่ 1: แก้ Sheet cost_data_By_Dexter

### สถานะ: ✅ เสร็จแล้ว (2026-04-29)

**สิ่งที่ทำ:**
- ~~Shift rows 48-113 (เก่า) → rows 37-102 (ใหม่) ลบช่องว่าง 11 แถว~~
- ~~แก้ bug G column ใน DB/RB rows: เพิ่ม $ lock + B column condition~~
- ~~เพิ่ม Section 6 (งาน Joint) คืน: Metal Cap, Joint Filler, Sealer EJ/CJ (rows 50-54)~~
- ~~เพิ่ม Section 7 header "ท่อระบาย" + Shift ท่อระบาย→rows 56-58~~
- ~~อัปเดต SUM: I65=SUM(I22:I63), I75=SUM(I69:I74), I86=SUM(I79:I85)~~
- ~~อัปเดต summary refs: G91=I65, G92=I75, G93=I86, G94=G91+G92+G93~~
- ~~G101=G94*B100 (ราคาประมูล Factor F), G103=% กำไร~~
- ~~แก้ #ERROR! row (====formula) → blank~~
- ~~แก้ typo "ท่อระบย" → "ท่อระบาย"~~
- ~~ล้าง rows 103-120~~

**โครงสร้างปัจจุบัน:**
| Row | Content |
|-----|---------|
| 1-21 | ข้อมูลโครงการ (W, L, T, St, Sh, CJ, EJ, Factor F) |
| 22-36 | Section 1-4: ดิน, ทราย, คอนกรีต, Wire Mesh |
| 37-49 | Section 5: Dowel Bar / Tie Bar (DB10-RB25) |
| 50-54 | Section 6: งาน Joint (Metal Cap, Filler, Sealer EJ/CJ) |
| 55 | header Section 7: ท่อระบาย |
| 56-63 | Section 7-8: ท่อระบาย + อื่นๆ |
| 65 | ■ รวมต้นทุนวัตถุดิบ =SUM(I22:I63) |
| 69-74 | ค่าแรงงาน |
| 75 | ■ รวมค่าแรง =SUM(I69:I74) |
| 79-85 | ค่าเครื่องจักร |
| 86 | ■ รวมเครื่องจักร =SUM(I79:I85) |
| 91-103 | สรุปต้นทุน, Factor F, ราคาประมูล, % กำไร |

---

## งานที่ 2: Python Scraper — gprocurement.go.th

### สถานะ: ✅ ทำงานได้จริง (2026-04-29)

**ไฟล์:** `scripts/Sebastian_Scraper.py`

**สิ่งที่ค้นพบและทำสำเร็จ:**
- ~~ค้นพบว่า process3 (เก่า) ถูกปิด → เว็บย้ายมา process5 (Angular SPA)~~
- ~~ค้นพบ API จริง: `process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement`~~
- ~~แก้ปัญหา Cloudflare Turnstile — รอปุ่มค้นหา enabled ก่อน search~~
- ~~แก้ปัญหา Angular form binding — ใช้ `keyboard.type()` แทน `fill()`~~
- ~~Pagination ผ่าน `page.evaluate(fetch(url))` ในบริบท browser~~
- ~~Multi-keyword search 21 keywords บน session เดียว ไม่ต้อง reload~~
- ~~Filter เฉพาะพื้นที่: อ.บ้านแพง นครพนม + อ.บึงโขงหลง บึงกาฬ~~
- ~~Deduplication ด้วย projectId (จาก API โดยตรง)~~
- ~~บันทึก seen_ids.json + local JSON backup~~

**Keywords (21 รายการ):**
- Tier 1: ถนนคอนกรีต, ก่อสร้างถนนคอนกรีต, ปูคอนกรีต, คอนกรีตเสริมเหล็ก
- Tier 2: ก่อสร้างถนน, ซ่อมแซมถนน, ปรับปรุงถนน, งานโยธา, ท่อระบายน้ำ คสล., Dowel Bar, คอนกรีตผสมเสร็จ, ฝายคอนกรีต, ลานคอนกรีต ฯลฯ

**วิธีรัน:**
```
1. Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\Temp\ChromeDebug"
2. python scripts/Sebastian_Scraper.py
```

**ยังขาด:**
- [ ] ทดสอบ `append_jobs_to_sheet` full run จริงกับ Sheets
- [ ] TOR URL — process5 API ไม่ return ลิงก์ PDF (ต้องเปิดหน้ารายละเอียด projectId แยก)

---

## งานที่ 3: Document Downloader

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_Doc_Downloader.py`

- อ่านงาน status='new' + D0/M-step จาก Sheet 1
- ลอง API endpoint 3 รูปแบบสำหรับ file list
- Fallback: navigate ไป detail page → capture API + HTML links
- จำแนก pr4, pr5, tor จากชื่อไฟล์
- Download ไปยัง `downloads/<job_id>/`
- อัปเดต status: docs_downloaded / docs_failed

---

## งานที่ 4: ปร.4/5 Parser

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_PR45_Parser.py`

- รองรับ PDF (pymupdf) และ Excel (openpyxl)
- Auto-detect ปร.4 vs ปร.5 จากชื่อไฟล์และเนื้อหา
- ปร.4: แยก line items → {description, quantity, unit, unit_price, total}
- ปร.5: ดึง direct_cost, overhead_pct, profit_pct, total_price

---

## งานที่ 5: TOR AI Analyzer

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_TOR_Analyzer.py`

- อ่าน TOR PDF → clean + prioritize relevant sections
- เรียก Claude API (claude-sonnet-4-6) ครั้งเดียวต่องาน
- Output: W, L, T, St, grade, dowel_bar, tie_bar, wire_mesh, CJ, EJ, confidence

---

## งานที่ 6: JSON Merger + Sheet 2 Writer

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_JSON_Merger.py` + `scripts/Sebastian_Sheet2_Writer.py`

- Merger: ผนวก JSON (ปร.4/5) + JSON (TOR) + raw_job → Combined JSON
- Writer: Combined JSON → Sheet 2 (job_specs)
- Sheet 2 columns: job_id, title, W, L, T, St, grade, dowel, wire_mesh, CJ, EJ, budget, scores

---

## งานที่ 7: Cost Filler

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_Cost_Filler.py`

- อ่าน Sheet 2 status='analyzed'
- เติม C11=W, C12=L, C13=T, C14=St, C16=CJ, C17=EJ ใน cost_data_By_Dexter
- รอ 3 วินาทีให้ Sheets recalculate
- อ่าน output: I65, I75, I86, G94, G101, G103
- บันทึก cost_results JSON สำหรับ Ranker

---

## งานที่ 8: Ranker

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_Ranker.py`

- โหลด cost_results JSON
- Score: margin(40%) + budget(30%) + confidence(20%) + completeness(10%)
- บันทึกลง Sheet 4 (ranked_jobs) เรียงอันดับสูง → ต่ำ

---

## Master Pipeline

**ไฟล์:** `scripts/Sebastian_Pipeline.py`

```
python Sebastian_Pipeline.py                    # รันทั้ง 5 steps
python Sebastian_Pipeline.py --step scrape
python Sebastian_Pipeline.py --step download
python Sebastian_Pipeline.py --step analyze
python Sebastian_Pipeline.py --step cost
python Sebastian_Pipeline.py --step rank
```

---

## แผนงานถัดไป (เรียงตามลำดับ)

1. ~~**Full Run Test (Scraper)** — เปิด Chrome → รัน Scraper จริง → ตรวจ Sheet 1~~ ✅ 601 งาน
2. ~~**Full Run Test (Doc Download)** — รัน Doc Downloader → ยืนยัน API endpoint~~ ✅
3. ~~**Test ปร.4/5 Parser** — Claude Vision อ่าน PDF สแกนได้~~ ✅
4. ~~**Test TOR Analyzer** — Vision อ่าน pB2 ได้ W/L/T~~ ✅
5. ~~**End-to-end Test** — รัน full pipeline 1 งานสำเร็จ~~ ✅ job 69049122041
6. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน cost step ใหม่
7. **Task Scheduler** — ตั้ง Windows Task Scheduler รันอัตโนมัติ

---

## Checkpoint — 2026-04-29 22:47

### สถานะล่าสุด
Pipeline redesign เสร็จสมบูรณ์ (4-Sheet design)

### สิ่งที่เพิ่งทำ
- อัปเดต `work_overview.md` + `future_development.md` เป็น 4-Sheet design ใหม่
- เพิ่ม `seq_no`, `announce_type`, `step_id` ลง job dict ใน `Sebastian_Scraper.py`
- เขียน script ใหม่ครบ 6 ไฟล์:
  - `Sebastian_Doc_Downloader.py` — Chrome CDP download ปร.4/5/TOR
  - `Sebastian_PR45_Parser.py` — อ่าน ปร.4 (BOQ) + ปร.5 (price summary)
  - `Sebastian_TOR_Analyzer.py` — Claude API วิเคราะห์ TOR → JSON
  - `Sebastian_JSON_Merger.py` — ผนวก JSON สองอัน → combined
  - `Sebastian_Sheet2_Writer.py` — combined JSON → Sheet 2 (job_specs)
  - `Sebastian_Cost_Filler.py` — Sheet 2 → เติม C11-C17 → อ่าน output Sheet 3
  - `Sebastian_Ranker.py` — cost results → score → Sheet 4
- อัปเดต `Sebastian_Pipeline.py` ให้ครอบคลุม 5 steps ใหม่

### สิ่งที่ยังไม่ได้ทำ
- ยังไม่ได้รัน Full Run Test (ต้องการ Chrome port 9222)
- ยังไม่ทราบ exact API endpoint สำหรับ document download (Doc Downloader มี fallback + debug capture)
- ยังไม่ได้ตั้ง Task Scheduler

### ต้องทำต่อ
1. เปิด Chrome: `Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\Temp\ChromeDebug"`
2. รัน `python scripts/Sebastian_Scraper.py` → ตรวจ Sheet 1
3. รัน `python scripts/Sebastian_Doc_Downloader.py` → ดู `downloads/debug/` → หา API endpoint
4. ต่อ pipeline ตามผลที่ได้

---

## Checkpoint — 2026-05-07

### สถานะล่าสุด
Scraper routing fix + data integrity fixes เสร็จสมบูรณ์

### สิ่งที่เพิ่งทำ
- ~~แก้ `Sebastian_Scraper.py`: e-bidding jobs → raw_jobs_bidding ด้วย (เดิมเขียนแค่ raw_jobs)~~
- ~~คัดลอก 2 งาน e-bidding ที่ตกค้างจาก raw_jobs → raw_jobs_bidding: 69019024418, 69039054231~~
- ~~แก้ job_specs: ชื่อ column ไทยครบ 40 คอลัมน์, มี/ไม่มี แทน Y/N, สูง/กลาง/ต่ำ แทน high/medium/low~~
- ~~แก้ Scraper filter: กรองเฉพาะงานก่อสร้าง (CONSTRUCTION_KEYWORDS) ไม่ผ่านแค่พื้นที่~~
- ~~เพิ่ม Tier system: Tier 1 (ถนนคอนกรีต) = คำนวนเต็ม, Tier 2 = ยังไม่ได้คำนวน~~
- ~~เพิ่ม tor_result.json cache ใน TOR Analyzer~~
- ~~เพิ่มฟิลด์ใหม่ใน TOR: warranty_period_days, required_tests, required_delivery_documents, special_conditions~~
- ~~แก้ Doc Downloader: ตรวจ renamed folder ก่อนสร้างใหม่~~

### raw_jobs_bidding ปัจจุบัน (6 งาน)
| job_id | ชื่องาน (สั้น) | status |
|--------|----------------|--------|
| 68129570964 | บำรุงถนน นพ.3023 | no_boq |
| 69019077732 | เสริมผิวแอสฟัลท์ | docs_downloaded |
| 69049020320 | เพิ่มค่าสัมประสิทธิ์ผิวทาง | no_boq |
| 68119260653 | ปรับปรุงถนนแอสฟัลต์ติก | docs_downloaded |
| 69019024418 | เสริมผิวจราจรด้วยแอสฟัลท์คอนกรีต | **new** |
| 69039054231 | ปรับปรุงถนนคอนกรีตเสริมเหล็ก | **new** |

### ต้องทำต่อ
1. รัน Doc Downloader สำหรับ 2 งาน status='new' (ต้องการ Chrome port 9222)
2. รัน pipeline: analyze → merge → sheet2_writer สำหรับงานใหม่
3. กรอกราคา/หน่วย ใน cost_data_By_Dexter column H (รอ Phase 0)

---

## Checkpoint — 2026-04-30 03:35

### สถานะล่าสุด
Scraper Full Run Test สำเร็จสมบูรณ์

### สิ่งที่เพิ่งทำ
- รัน `Sebastian_Scraper.py` พร้อม Tier 0 keywords (บ้านแพง, บึงโขงหลง)
- ได้งานใหม่ **601 รายการ** บันทึกลง Sheet 1 (raw_jobs) + `data/jobs_20260430_0335.json`
  - บ้านแพง: 300/300 ✅
  - บึงโขงหลง: 299/300 (1 ซ้ำ) ✅
  - ลานคอนกรีต: 2 bonus
- Tier 1/2 keywords โดนrate limit หลัง Tier 0 แต่ได้ 0 พื้นที่อยู่แล้ว — ไม่กระทบ
- Session reinit ทำงานถูกต้อง (20s cooldown + Cloudflare Turnstile ผ่าน)

### สิ่งที่ยังไม่ได้ทำ
- ยังไม่ได้รัน Doc Downloader
- ยังไม่ทราบ exact API endpoint สำหรับ document download
- ยังไม่ได้ตั้ง Task Scheduler

### ต้องทำต่อ
1. รัน `python scripts/Sebastian_Doc_Downloader.py` → ดู `downloads/debug/` → หา API endpoint
2. ต่อ pipeline ตามผลที่ได้

---

## Checkpoint — 2026-05-01 14:25

### สถานะล่าสุด
**End-to-End Pipeline ผ่านครั้งแรก** ✅

### API Endpoints ที่ค้นพบ (สำคัญมาก)
| Endpoint | Method | Header | หมายเหตุ |
|----------|--------|--------|----------|
| `/egp-project-service/listProjectPriceBuildZipByProjectId?projectId={pid}` | GET | `apikey: Liaqv30xLpFGOlJPW1N0hPKJkbO7vWUS` | ดึง zipFileId |
| `/egp-upload-service/v1/downloadFileTest?fileId={zipFileId}` | GET | ไม่ต้องการ | ดาวน์โหลด zip จริง |

### โครงสร้าง BOQ Zip
```
pB0.pdf — ประกาศราคากลาง
pB1.pdf — รายการตรวจสอบประมาณการ (มี T, St)
pB2.pdf — แบบมาตรฐานงานถนน (มี W, L, T, CJ)
pB3.pdf — แบบสรุปราคากลาง (ปร.5) ← อ่านด้วย Claude Vision → budget_price
pB4.pdf — แผนที่โครงการ
```

### Script ที่แก้ไขวันนี้
- `Sebastian_Doc_Downloader.py` — เขียนใหม่ทั้งหมด ใช้ 2-step API flow
- `Sebastian_PR45_Parser.py` — เพิ่ม Claude Vision fallback สำหรับ PDF สแกน
- `Sebastian_TOR_Analyzer.py` — เพิ่ม `analyze_job_tor_vision()` อ่าน pB1/pB2/pB3
- `Sebastian_Sheet2_Writer.py` — เพิ่ม upsert (อัปเดตแถวที่มี W/L ใหม่)
- `Sebastian_Cost_Filler.py` — แก้ OUTPUT_CELLS (I77, I84, G91, G98, G100) + default CJ=10, EJ=100 (มาตรฐานถนน คสล. ไทย)

### ผลทดสอบ job 69049122041 (บ้านแพง ถนน คสล.)
- budget จาก Sheet 1: 497,000 บาท
- budget จาก ปร.5 (Vision): 491,741.89 บาท ✅
- W=5.0, L=145.0, T=0.15 (Vision จาก pB2) ✅
- Pipeline: download → analyze → cost → rank ผ่านครบ ✅
- ต้นทุน = 2,030 บาท (ผิด) เพราะ **ยังไม่ได้กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H

### Sheet ที่สร้างใหม่
- `job_specs` (Sheet 2) — สร้างวันนี้ มี 5 งาน

### ต้องทำต่อ
1. **คุณกัญจน์กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H
2. รัน `python scripts/Sebastian_Pipeline.py --step cost` ใหม่
3. ตั้ง Windows Task Scheduler

---

## Checkpoint — 2026-05-01 (session 2)

### สถานะล่าสุด
Task Scheduler พร้อมใช้งาน — pipeline รันอัตโนมัติทุกเช้า 06:00 น.

### สิ่งที่ทำสำเร็จ
- ~~**Windows Task Scheduler** — ลงทะเบียน `BidMaster-DailyPipeline` รันทุก 06:00 น.~~ ✅
- ~~**ปิด Sleep อัตโนมัติ** — AC Power Sleep เดิม 45 นาที → ตั้งเป็น Never~~ ✅
- ~~**แก้ CJ/EJ defaults** — CJ=10m, EJ=100m (มาตรฐานถนน คสล. ไทย)~~ ✅

### Pipeline ที่รันได้จริงตอนนี้ (06:00 น. ทุกวัน)
```
scrape → download → analyze → rank
```

### สิ่งที่ยังค้างอยู่ (ยังไม่รวมใน pipeline อัตโนมัติ)
| งาน | สาเหตุ | ต้องทำ |
|-----|--------|--------|
| Cost step | ราคา/หน่วย ใน cost_data_By_Dexter column H ยังว่าง | คุณกัญจน์กรอกราคา → รัน cost step ใหม่ |
| Classifier (6 Sheets) | `Sebastian_Classifier.py` ยังไม่ได้เขียน | เขียน script + สร้าง 3 sheet ที่เหลือ |

### 6-Sheet System — สถานะ
| Sheet | สถานะ |
|-------|-------|
| `raw_jobs_all` | ✅ สร้างแล้ว (ยังว่าง — รอ Classifier) |
| `raw_jobs_related` | ✅ สร้างแล้ว (ยังว่าง — รอ Classifier) |
| `raw_jobs_bidding` | ✅ สร้างแล้ว (ยังว่าง — รอ Classifier) |
| `raw_jobs_awarded` | ❌ ยังไม่สร้าง |
| `raw_jobs_direct` | ❌ ยังไม่สร้าง |
| `raw_jobs_cancelled` | ❌ ยังไม่สร้าง |

### ต้องทำต่อ
1. **คุณกัญจน์กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost` ใหม่
2. ~~เขียน `Sebastian_Classifier.py` + สร้าง 3 sheet ที่เหลือ~~ ✅
3. เพิ่ม cost step เข้า `run_pipeline.bat` (เมื่อ step 1 เสร็จ)

---

## Checkpoint — 2026-05-01 (session 3)

### สถานะล่าสุด
6-Sheet Classification system เสร็จสมบูรณ์

### สิ่งที่ทำสำเร็จ
- ~~**Sebastian_Classifier.py** — เขียนเสร็จ + รันสำเร็จ~~ ✅
- ~~**สร้าง 3 sheet ที่เหลือ** — raw_jobs_awarded, raw_jobs_direct, raw_jobs_cancelled~~ ✅
- ~~**เพิ่ม classify step** ใน Sebastian_Pipeline.py และ run_pipeline.bat~~ ✅
- ~~**แก้ province filter** — เช็ค keyword + province ตรงกัน (ไม่ใช่แค่ keyword ใน text)~~ ✅
  - ก่อน: กรองแค่ "บ้านแพง" ใน title → งานจากจังหวัดอื่นหลุดเข้ามา
  - หลัง: ต้องมี "บ้านแพง" ใน text AND province = "นครพนม" ถึงจะผ่าน
  - แก้ทั้ง `Sebastian_Scraper.py` และ `Sebastian_Classifier.py`

### 6-Sheet System — สถานะปัจจุบัน ✅ ครบทั้ง 6 ชีท
| Sheet | งาน | ความหมาย |
|-------|-----|----------|
| `raw_jobs_all` | 593 | ทุกงานในพื้นที่ (บ้านแพง นครพนม + บึงโขงหลง บึงกาฬ) |
| `raw_jobs_related` | 35 | งานก่อสร้างที่เกี่ยวกับบริษัท |
| `raw_jobs_bidding` | 4 | e-bidding + กำลังประมูล ← ชีทหลักสำหรับคำนวณ |
| `raw_jobs_awarded` | 0 | ประกาศผู้ชนะ (ยังไม่มีในรอบนี้) |
| `raw_jobs_direct` | 28 | วิธีเฉพาะเจาะจง |
| `raw_jobs_cancelled` | 0 | ยกเลิก (ยังไม่มีในรอบนี้) |

### Pipeline อัตโนมัติ 06:00 น. (ครบแล้ว ยกเว้น cost)
```
scrape → download → classify → analyze → rank
```

### ยังค้าง (เรียงตามลำดับความสำคัญ)
1. **LINE Notify** — ส่งสรุป ranked_jobs ไป LINE หลัง pipeline รัน (รอ token จากคุณกัญจน์)
2. **เพิ่ม Keywords** — คุณกัญจน์จะเพิ่ม keyword ใน Scraper + Classifier ให้ละเอียดขึ้น
3. **Cost step** — รอคุณกัญจน์กรอกราคา/หน่วยใน cost_data_By_Dexter column H

---

## Checkpoint — 2026-05-06

### สิ่งที่ทำสำเร็จ
- ~~**Service Account auth**~~ — แก้ `sheets_client.py` เปลี่ยนจาก ADC (หมดอายุ) → Service Account ✅
- ~~**Share Sheets กับ SA**~~ — Bid Master + BSC Orders share กับ `bid-master-sheets@bid-master-sheets.iam.gserviceaccount.com` ✅
- ~~**Full pipeline run**~~ — Step 1-4, 6 ผ่าน / Step 5 มี bug ✅
- ~~**Rate limit fix**~~ — Pagination detect → sleep 60s → retry / Search timeout → reinit + sleep 120s → retry / Loading spinner wait ✅
- ~~**Bug Step 5 Cost**~~ — แก้ `get_all_records(expected_headers=...)` ✅
- ~~**Doc Downloader เปลี่ยน source sheet**~~ — อ่านจาก `raw_jobs_bidding` แทน `raw_jobs` (download เฉพาะ 4 งาน e-bidding) ✅

### Pipeline ปัจจุบัน
```
scrape → classify → download PDF (raw_jobs_bidding เท่านั้น) → analyze → cost → rank
```

### ต้องทำต่อ
1. คุณกัญจน์กรอกราคา/หน่วยใน cost_data_By_Dexter column H → รัน `--step cost` ใหม่
2. LINE Notify token

---

## Checkpoint — 2026-05-06 (BSC Website session)

### สิ่งที่ทำสำเร็จ — BSC Website (bsc-website-wine.vercel.app)

**Booking System:**
- ~~**OrderModal disclaimer**~~ — เพิ่มกล่อง ✓ 3 ข้อ (ไม่มีมัดจำ, ยกเลิกได้, ทีมโทรกลับ) ✅
- ~~**BookingHighlight popup**~~ — floating card มุมล่างขวา โผล่หลัง scroll 400px มี X ปิดได้ ✅
- ~~**Booking cards หน้า /products**~~ — 3 การ์ดระหว่าง header กับสินค้า 01 ✅
- ~~**แยก lean กับ 240/2**~~ — แยกเป็น 2 options ใน OrderModal.tsx ✅

**SEO:**
- ~~**Google index แล้ว**~~ — ยืนยันผ่าน Search Console (site: query ขึ้นผล) ✅
- ~~**Sitemap.xml**~~ — `app/sitemap.ts` ✅
- ~~**robots.txt**~~ — `app/robots.ts` ✅
- ~~**Metadata แต่ละหน้า**~~ — layout.tsx สำหรับ /products, /about, /contact ✅

**Portfolio:**
- ~~**หน้า /portfolio**~~ — 40 รูป, filter 5 หมวด, lightbox คลิกดูเต็มจอ ✅
- ~~**caption มืออาชีพ**~~ — เปลี่ยนชื่อรูปทุกใบให้เป็นทางการ ✅
- ~~**Photo Marquee หน้าแรก**~~ — 2 แถวไหลสวนทาง infinite scroll ✅
- ~~**ลิงก์ผลงานใน Navbar**~~ — เพิ่ม "ผลงาน" ระหว่างสินค้า-เกี่ยวกับเรา ✅

### ยังค้าง
1. **คุณกัญจน์กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **LINE Notify token** → implement notification
3. **Domain** — ซื้อ `bscconcrete.co.th` หรือ `bscconcrete.com` แล้วผูก Vercel
4. **Open Graph image** — รูป preview ตอนแชร์ใน LINE/Facebook

---

## Checkpoint — 2026-05-08

### สิ่งที่ทำสำเร็จวันนี้

- ~~**แก้ Scraper keywords**~~ — เปลี่ยนจาก 21 keywords → ค้นหาด้วยจังหวัด `นครพนม` + `บึงกาฬ` แล้วใช้ 17 keywords เป็น filter ✅
- ~~**ลบ district filter**~~ — ไม่จำกัดแค่ บ้านแพง/บึงโขงหลง แล้ว ได้งานทั้ง 2 จังหวัด ✅
- ~~**แก้ rate limit retry**~~ — เปลี่ยนจาก 300s → 120s ตรงๆ (จาก pattern จริง: 60s ไม่พอ, 120s พอเสมอ) ✅
- ~~**รัน Scraper สำเร็จ**~~ — นครพนม 2,980 / บึงกาฬ 3,790 = 6,770 รายการ, ใหม่ 142 งาน ✅
- ~~**เพิ่ม project_status column**~~ — ดึงจาก flowName ใน API (กำลังประมูล / ประมูลแล้ว / ยกเลิก / กำลังเตรียม) ✅
- ~~**สร้าง sheet active_bidding**~~ — e-bidding กำลังประมูล → ชีทหลักคำนวณ ✅
- ~~**สร้าง sheet awarded_jobs**~~ — e-bidding ที่ประมูลแล้ว ✅
- ~~**แก้ Doc Downloader**~~ — อ่านจาก `active_bidding` แทน `raw_jobs_bidding` ✅
- ~~**สร้าง Sebastian_Winner_Checker.py**~~ — ดึงชื่อบริษัทผู้ชนะจาก greenBook API W0 ✅

### ต้องทำต่อ (เรียงลำดับ)
1. **รัน Scraper อีกครั้ง** — เพื่อให้ข้อมูลไหลเข้า `active_bidding` และ `awarded_jobs` (2 sheets ยังว่างอยู่)
2. **รัน Winner Checker** (ต้องการ Chrome port 9222) — ดึงชื่อบริษัทผู้ชนะใน `awarded_jobs`
3. **กรอกราคา/หน่วย** ใน `cost_data_By_Dexter` column H → รัน cost step

---

## Checkpoint — 2026-05-10

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Sebastian_LINE_Notify.py**~~ — เขียนเสร็จ (แต่ต้องแก้ใหม่ — ดูด้านล่าง) ⚠️
- ~~**Sebastian_Pipeline.py**~~ — เพิ่ม step notify (step 7/7) ✅
- ~~**work_overview.md**~~ — อัปเดตให้ตรงกับ pipeline จริงปัจจุบัน ✅

### ⚠️ LINE Notify ปิดให้บริการแล้ว (31 มี.ค. 2568)
`Sebastian_LINE_Notify.py` ที่เขียนไว้ใช้ LINE Notify API ซึ่งปิดตัวแล้ว — ต้องเปลี่ยนไปใช้ทางเลือกอื่น

ทางเลือกที่กำลังพิจารณา:
- **LINE Messaging API** — ต้องสร้าง LINE Official Account + รู้ User ID ตัวเอง
- **Telegram Bot** — ง่ายที่สุด ฟรีไม่จำกัด รอการตัดสินใจจากคุณกัญจน์

### ต้องทำต่อ (เรียงลำดับ)
1. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **เลือกระบบ Notify** — LINE Messaging API หรือ Telegram → แก้ `Sebastian_LINE_Notify.py`
3. ~~**รัน Scraper ใหม่** → ให้ active_bidding + awarded_jobs มีข้อมูล~~ ✅

---

## Checkpoint — 2026-05-10 (session 2)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Scraper: เพิ่ม district/subdistrict extraction**~~ — regex ดึง อำเภอ/ตำบล จาก title+department ✅
- ~~**awarded_jobs: เพิ่ม 3 column ผู้ชนะ**~~ — ผู้ชนะประมูล, ราคาที่ชนะ (บาท), วันประกาศผู้ชนะ ✅
- ~~**รัน Scraper**~~ — นครพนม 5,990 / บึงกาฬ 4,510 = 10,500 รายการ, ใหม่ 130 งาน ✅

### ผล Sheets หลังรัน
| Sheet | ผล |
|-------|-----|
| `raw_jobs` | +130 งานใหม่ |
| `awarded_jobs` | +38 งาน (e-bidding ประมูลแล้ว) ← พร้อมรัน Winner Checker |
| `active_bidding` | ยังว่าง — ไม่มี e-bidding กำลังประมูลใหม่ในพื้นที่ตอนนี้ |

### ต้องทำต่อ (เรียงลำดับ)
1. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **รัน Winner Checker** → ดึงชื่อผู้ชนะสำหรับ 38 งานใน awarded_jobs (ต้องการ Chrome port 9222)
3. **เลือกระบบ Notify** — LINE Messaging API หรือ Telegram

---

## Checkpoint — 2026-05-10 (session 3)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**แก้ Classifier ทั้งหมด**~~ — เปลี่ยน filter บ้านแพง/บึงโขงหลง → ทั้งจังหวัด นครพนม+บึงกาฬ ✅
- ~~**เพิ่ม active_bidding + awarded_jobs**~~ ใน Classifier output (clear+rewrite พร้อม preserve winner data) ✅
- ~~**ลบ raw_jobs_all**~~ ออกจาก Classifier (ไม่จำเป็น) ✅
- ~~**แก้ raw_jobs header**~~ — col13: quantity_note→project_status, col14: seq_no→quantity_note ✅
- ~~**แก้ regex district/subdistrict**~~ — เปลี่ยนจาก `[^\s,จ]`/`[^\s,อ]` → `\S+` (ไม่หยุดกลางคำ) ✅
- ~~**รัน Classifier**~~ — ผลครบทุกชีท ✅

### ผล Sheets หลัง Classifier รัน
| ชีท | งาน | หมายเหตุ |
|-----|-----|---------|
| `raw_jobs_related` | 419 | ครอบทั้งจังหวัด (จากเดิม 36) |
| `raw_jobs_bidding` | 15 | e-bidding กำลังประมูล |
| `active_bidding` | 15 | พร้อม Doc Downloader อ่าน |
| `raw_jobs_awarded` | 98 | e-bidding ประมูลแล้ว |
| `awarded_jobs` | 98 | พร้อม Winner Checker อ่าน |
| `raw_jobs_direct` | 292 | เฉพาะเจาะจง |
| `raw_jobs_cancelled` | 12 | ยกเลิก |

### ต้องทำต่อ (เรียงลำดับ)
1. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **รัน Winner Checker** → ดึงชื่อผู้ชนะ 98 งานใน awarded_jobs (ต้องการ Chrome port 9222)
3. **เลือกระบบ Notify** — LINE Messaging API หรือ Telegram

---

## Checkpoint — 2026-05-11

### เปลี่ยนแผน: ตัด Cost/Rank อัตโนมัติออก

**เหตุผล:** ตัวแปรเยอะเกินไป, cost_data column H ค้างมาตั้งแต่ 1 พ.ค. ไม่ได้กรอก
**แผนใหม่:** pipeline อัตโนมัติหา+แจ้งงาน, พ่อคำนวนเองผ่านชีทที่สร้างขึ้นใหม่

### สิ่งที่ทำสำเร็จวันนี้

- ~~**เปลี่ยน Sebastian_LINE_Notify.py**~~ — จาก LINE Notify API (ปิดแล้ว) → LINE Messaging API ✅
- ~~**ทดสอบ LINE Notify**~~ — ส่ง 15 งานเข้า LINE Group สำเร็จ ✅
- ~~**ยืนยัน Vercel env vars**~~ — LINE_CHANNEL_ACCESS_TOKEN + LINE_GROUP_ID มีอยู่ใน production แล้ว ✅
- ~~**BSC website order notify**~~ — โค้ดมีอยู่แล้วใน send-order/route.ts พร้อมใช้งาน ✅

### Pipeline ปัจจุบัน (แผนใหม่)

```
ส่วนอัตโนมัติ (06:00 น.):
scrape → classify → [Winner Checker แยก] → LINE notify

ส่วน manual (พ่อทำเอง):
รับ LINE → ค้น ID ใน eGP → กรอก W/L/T ในชีทคำนวน → ได้ปริมาณวัสดุ
```

### สถานะ Sheets

| Sheet | งาน | สถานะ |
|-------|-----|-------|
| `active_bidding` | 15 | ✅ พร้อมใช้ |
| `awarded_jobs` | 98 | ✅ รอ Winner Checker |
| `raw_jobs_related` | 419 | ✅ |
| `raw_jobs_direct` | 292 | ✅ |

### ต้องทำต่อ

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ (งานถัดไป)
2. **รัน Winner Checker** — ดึงชื่อผู้ชนะ 98 งาน (ต้องการ Chrome port 9222)

---

## Checkpoint — 2026-05-11 (session 2)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**เปลี่ยนแผน**~~ — ตัด Analyze, Rank, Download ออกจาก pipeline ✅
- ~~**แก้ run_pipeline.bat**~~ — ลำดับถูกต้อง + ตัด step ที่ไม่ใช้ + เพิ่ม LINE Notify ✅
- ~~**ยืนยัน Task Scheduler**~~ — BidMaster-DailyPipeline สถานะ Ready ✅
- ~~**Chrome เปิดอัตโนมัติ**~~ — run_pipeline.bat จัดการเองทุกวัน ไม่ต้องทำเอง ✅

### Pipeline ปัจจุบัน (แผนใหม่ สมบูรณ์)

```
06:00 น. ทุกวัน (Task Scheduler)
  → เปิด Chrome Debug อัตโนมัติ
  → Step 1: Scrape (ใช้ Chrome)
  → Step 2: Classify (ไม่ใช้ Chrome)
  → ปิด Chrome
  → Step 3: LINE Notify → ส่งรายการ active_bidding เข้า LINE Group
```

### พับเอาไว้ก่อน (ยังไม่ทำ)
- Download step — โหลด PDF (รอแผนในอนาคต)
- Analyze step — TOR Analyzer (รอแผนในอนาคต)
- Rank step — จัดอันดับ (รอแผนในอนาคต)

### ต้องทำต่อ
1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ
2. **รัน Winner Checker** — ดึงชื่อผู้ชนะ 98 งานใน awarded_jobs (ต้องการ Chrome port 9222)

---

## Checkpoint — 2026-05-11 (session 3 — ก่อนนอน)

### สถานะระบบ ✅ พร้อมรันตี 6

- เครื่องเปิดอยู่ + เสียบปลั๊ก
- Task Scheduler: Ready — NextRun 11/05/2026 06:00 น.

### Pipeline ที่จะรันตี 6

```
เปิด Chrome อัตโนมัติ
  → Step 1: Scrape
  → Step 2: Classify
  → Step 3: Winner Checker (ดึงชื่อผู้ชนะ awarded_jobs)
  → ปิด Chrome
  → Step 4: LINE Notify → ส่งเข้า LINE Group
```

### ต้องทำต่อ (รอเช้า)
1. เช็ค LINE ว่า Sebastian ส่งผลมาไหม
2. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ

---

## Checkpoint — 2026-05-12

### สถานะระบบ

- Pipeline ตี 6 รันสำเร็จ ✅ (Sebastian แจ้งใน Discord 06:00–06:36 น.)
- LINE Notify ไม่ส่ง ⚠️ — สาเหตุ: ข้อความเกิน 5,000 ตัว (LINE API limit) เพราะ TOP_N=50

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Discord Bot ทำงานได้**~~ — Sebastian_Discord_Bot.py online ✅
- ~~**ask_discord.py two-way test**~~ — GSD ส่งคำถาม → คุณกัญจน์ตอบใน Discord → รับคำตอบได้ ✅
- ~~**แก้ LINE ข้อความยาวเกิน**~~ — ลด TOP_N จาก 50 → 15 + เพิ่ม auto-split (>4,900 ตัว) ✅
- ~~**ทดสอบ LINE ส่งสำเร็จ**~~ — ส่ง 15 งานเข้า LINE Group ✅

### Discord Bot files
| ไฟล์ | หน้าที่ |
|------|---------|
| `Sebastian_Discord_Bot.py` | Bot หลัก — listen ตลอด |
| `ask_discord.py` | GSD ถาม → รอคำตอบจาก Discord |
| `start_sebastian_bot.bat` | รัน Bot + auto-restart |

### ต้องทำต่อ (ก่อน session ถัดไป)

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ
2. ~~**รัน Winner Checker** — ดึงชื่อผู้ชนะ awarded_jobs~~ ✅ (ดูด้านล่าง)
3. **ตั้ง Discord Bot startup** — รัน start_sebastian_bot.bat อัตโนมัติเมื่อเปิดเครื่อง

---

## Checkpoint — 2026-05-12 (session 2 — Winner Checker fix)

### Root Cause: Winner Checker ไม่ได้ชื่อผู้ชนะ

`Sebastian_Winner_Checker.py` เดิมใช้ `greenBook` API (`pageAnnounceType=W0`) → ลองอ่านฟิลด์ `winnerName`, `vendorName`, `companyName`, `announceSubDesc` — **ทุกฟิลด์ null** greenBook มีแค่ metadata ไฟล์ ไม่มีชื่อบริษัทเลย ผล "อัปเดต 82 งานสำเร็จ" ในเช้าวันก่อนคือการเขียน empty string ลง Sheet

### API ที่ถูกต้อง (ค้นพบจาก Angular bundle `egp-aann09-web/594.e5359f451f8e5894.js`)

| Endpoint | ฟิลด์ที่ใช้ | ใช้เมื่อ |
|----------|------------|---------|
| `getContractAvailable?projectId=` | `contractAvailableResponse[0].corporateName` + `contractPrice` + `contractDate` | เซ็นสัญญาแล้ว |
| `getProcureResult?projectId=` | `procureResultDataResponse[].receiveNameTh` (flag P/W/A) + `priceAgree`/`priceProposal` | ประกาศผู้ชนะแล้วแต่ยังไม่เซ็นสัญญา |

Base: `process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement`

### สิ่งที่ทำสำเร็จ

- ~~**เขียนใหม่ `fetch_winner_info()`**~~ — 2-tier: getContractAvailable → fallback getProcureResult ✅
- ~~**ทดสอบ debug_winner_test.py**~~ — 5 งานแรก ✅ ทุกงานได้ชื่อบริษัท ✅
- ~~**รัน Winner Checker เต็ม**~~ — awarded_jobs 79/115 อัปเดตสำเร็จ ✅
- ~~**ลบ debug scripts ชั่วคราว**~~ — ล้าง scripts/ เรียบร้อย ✅

### ผล Winner Checker full run

| Sheet | ผล |
|-------|-----|
| `awarded_jobs` | **79/115 งานได้ชื่อผู้ชนะ** ✅ |
| `raw_jobs_direct` | 300 งานประมวลผล — ส่วนใหญ่ไม่มีข้อมูล (วิธีเฉพาะเจาะจงไม่ผ่าน contract API) |

36 งานที่เหลือใน awarded_jobs ไม่มีข้อมูล — เป็นงานใหม่มาก, ยกเลิก, หรือไม่ผ่านระบบสัญญาปกติ

### Pipeline ปัจจุบัน (สมบูรณ์)

```
06:00 น. ทุกวัน:
  → Step 1: Scrape
  → Step 2: Classify
  → Step 3: Winner Checker (getContractAvailable + getProcureResult)
  → ปิด Chrome
  → Step 4: LINE Notify (15 งาน, auto-split)
```

### ต้องทำต่อ

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ (**สำคัญที่สุด**)
2. **ตั้ง Discord Bot startup** — รัน start_sebastian_bot.bat อัตโนมัติเมื่อเปิดเครื่อง

---

## Checkpoint — 2026-05-13 (session 2)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Discord Bot startup อัตโนมัติ**~~ — เพิ่ม Windows Registry Run key `HKCU\...\Run\SebastianDiscordBot` → รัน `start_sebastian_bot.bat` ทุกครั้งที่ login (ไม่ต้องการ admin rights) ✅
- ~~**ชีทคำนวนถนน คสล.**~~ — สร้าง sheet `calc_road` ใน Bid Master Spreadsheet ✅
  - กรอกแค่ L (ความยาว) ที่ C5 → เห็นปริมาณวัสดุทันที
  - ตัวแปร: W, L, T, St, Sh, CJ, EJ (มีค่า default แล้ว)
  - ผลลัพธ์: คอนกรีต, ทรายรองพื้น, Wire Mesh, Dowel Bar, Metal Cap, Joint Filler/Sealer, ไหล่ทาง
  - script: `scripts/create_calc_sheet.py`

### Phase 0 — เสร็จสมบูรณ์ ✅

| งาน | สถานะ |
|-----|-------|
| ชีทคำนวน W/L/T → ปริมาณวัสดุ | ✅ `calc_road` sheet พร้อมใช้ |
| Discord Bot startup อัตโนมัติ | ✅ Registry Run key ตั้งแล้ว |

### ต้องทำต่อ (Phase 1)

1. **คุณกัญจน์สร้าง LINE Official Account** (ฟรี ที่ developers.line.biz) → ส่ง Channel Access Token + Channel Secret
2. Sebastian สร้าง Webhook Server (Next.js บน Vercel) รับข้อความจาก LINE + เชื่อม Claude API

---

## Checkpoint — 2026-05-13 (รอบบ่าย — fix pipeline)

### Pipeline 06:00 fail: Chrome ไม่ผูก port 9222 → เสียเวลา 90 นาที

**Root cause:**
- `wmic.exe` ถูกลบใน Windows 11 25H2 (build 26200) → คำสั่ง kill Chrome เก่าใน `run_pipeline.bat` ทำงานไม่ได้แบบเงียบๆ
- `run_pipeline.bat` ลบเฉพาะ `lockfile` แต่ Chrome ใช้ `SingletonLock`/`SingletonCookie`/`SingletonSocket` เป็น lock จริง
- ไม่มี health-check หลัง start Chrome → playwright รอ 3 นาที × 15 รอบ = 45 นาทีต่อ step (Scraper + Winner Checker = 90 นาที)

**สิ่งที่แก้ใน `run_pipeline.bat`:**
- ~~แทน `wmic process delete` (2 จุด) ด้วย PowerShell `Get-CimInstance Win32_Process | Stop-Process`~~ ✅
- ~~เพิ่มลบ `SingletonLock` / `SingletonCookie` / `SingletonSocket` (Chrome lock จริง)~~ ✅
- ~~เพิ่ม health-check `http://127.0.0.1:9222/json/version` (รอสูงสุด 60s, fail fast)~~ ✅
- ~~ใช้ `SET CHROME_OK=1` gate Step 1 (Scraper) และ Step 3 (Winner Checker) — ถ้า Chrome ไม่ขึ้น ข้ามไป Step 2 + Step 4 ยังรันได้ตามปกติ~~ ✅
- ~~แก้ nested `%ERRORLEVEL%` → `if errorlevel 1` (batch parse-time gotcha)~~ ✅

**ผลคาด:** Pipeline พรุ่งนี้ 06:00 ถ้า Chrome ขึ้นไม่ได้ จะ fail fast ใน 60s แทน 90 นาที และยังได้ Step 2 (Classify) + Step 4 (LINE Notify) จากข้อมูลเดิมในชีท

---

## Checkpoint — 2026-05-13

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Complete DEPT_SEARCH_TERMS integration**~~ — เพิ่ม 28 หน่วยงานเข้า main() loop หลัง province loop ✅
  - รอ 60s cooldown ก่อนเริ่ม dept loop
  - wait 15s ระหว่าง dept แต่ละชื่อ (เดิมออกแบบ 30s แต่ลดลง)
  - ไม่กรอง FILTER_KEYWORDS — รับทุกงานจากหน่วยงานเหล่านั้น
  - ยังคง dedup กับ seen_ids

- ~~**Discord step notifications ใน run_pipeline.bat**~~ ✅
  - ส่ง 🚀 เมื่อ pipeline เริ่ม
  - ส่ง ✅/❌ หลังแต่ละ step พร้อมชื่อ log file เมื่อ error
  - เพิ่ม `--notify` flag ให้ `ask_discord.py` CLI

- ~~**Claude Code Stop hook**~~ — เพิ่มใน `~/.claude/settings.json` ✅
  - ping Discord ทุกครั้งที่ Claude ตอบเสร็จ: "✅ Sebastian เสร็จแล้ว — กลับมาดูผลได้เลยครับ"
  - 0 token cost (pure Discord API call)

### เวลารัน pipeline โดยประมาณ
| ส่วน | เวลา |
|------|------|
| Province search (นครพนม + 180s + บึงกาฬ) | ~12–15 นาที |
| Dept search (60s cooldown + 28 หน่วยงาน × 15s) | ~11–13 นาที |
| Classifier + Winner Checker + LINE Notify | ~5 นาที |
| **รวม** | **~28–35 นาที** |

### ต้องทำต่อ

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ (**สำคัญที่สุด**)
2. **ตั้ง Discord Bot startup** — รัน start_sebastian_bot.bat อัตโนมัติเมื่อเปิดเครื่อง

---

---

## Pipeline Chrome Connect — Fail-fast (2026-05-13)

### สถานะ: ✅ แก้แล้ว

**ปัญหา:** Pipeline วันที่ 13 พ.ค. เสียเวลา **90 นาที** ไปกับการรอ Chrome
- Step 1 (Scraper) fail หลัง 45 นาที — `RuntimeError: เชื่อมต่อ Chrome ไม่ได้`
- Step 3 (Winner Checker) fail หลัง 45 นาที — error เดียวกัน

**Root cause hypothesis:**
- `run_pipeline.bat` health-check `/json/version` **ผ่าน** (Chrome HTTP ตอบ)
- แต่ playwright `connect_over_cdp()` (CDP WebSocket) **fail** — Chrome ค้าง/zombie
- `connect_browser()` ใช้ playwright default timeout 180s × 15 retries = 45 นาที

**สิ่งที่แก้:**
- ~~`Sebastian_Scraper.py:218-228` connect_browser(): retry 15→3, timeout=5000ms, log exception type~~
- ~~`Sebastian_Winner_Checker.py:121-130` connect_browser(): pattern เดียวกัน~~

**ผลที่คาดหวัง:** ถ้า Chrome connect fail อีก จะ fail ภายใน **~30 วินาที** (เดิม 45 นาที) — ทั้ง pipeline ประหยัด 89 นาทีต่อรอบที่ Chrome พัง

**ยังไม่ได้แก้ (รอสังเกตว่ายังเกิดอีกไหม):**
- [ ] เพิ่ม CDP WebSocket health-check ใน `run_pipeline.bat` (เดิมเช็คแค่ HTTP `/json/version`)
- [ ] เพิ่ม Chrome restart logic เมื่อ connect fail ครั้งแรก

---

## Checkpoint — 2026-05-13 (session — วันยื่นซอง fix)

### สถานะ: ✅ เสร็จสมบูรณ์

**ปัญหา:** `active_bidding` ทั้ง 17 งาน มี `deadline = ""` เพราะ eGP search API ไม่ return วันยื่นซอง

**Root cause ที่ค้นพบ:**
- Search API คืนแค่ metadata, ไม่มี deadline field
- ลอง 20+ API endpoints — ทั้งหมด 404 หรือ no data
- วันยื่นซองอยู่ใน **ไฟล์ PDF ประกาศเชิญชวน** (blob URL) เท่านั้น

**วิธีแก้ที่ทำงานได้จริง (PDF approach):**
1. ค้นหาด้วยชื่อหน่วยงาน (เช่น "สามผง") → interceptAPI response → หา row index ของ pid
2. Click `a.btn-icon` ใน row นั้น → Angular router ไปหน้า detail `/procurement/{encrypted_token}`
3. Click description icon ใน TABLE4 (ประกาศเชิญชวน D0) → TABLE1 โหลด
4. Click `file_download` icon ใน TABLE1 → new page เปิด blob URL
5. `FileReader.readAsDataURL(blob)` → base64 → `pdfplumber.open(BytesIO(...))` → extract text
6. Thai numeral conversion (`๐-๙` → `0-9`) + regex หาวันที่

**ผลการรัน patch_deadlines.py:**
| job_id | วันยื่นซอง | เหลือ |
|--------|-----------|-------|
| 69049366395 | 12/05/2569 | -1 วัน (หมดแล้ว) |
| 69049365887 | 18/05/2569 | +5 วัน ✅ |
| 68119422244 | 28/04/2569 | -15 วัน (หมดแล้ว) |

**วิเคราะห์ 14 งานที่ไม่มี deadline:**

| สาเหตุ | จำนวน | แก้ได้? |
|--------|-------|---------|
| keyword กว้างเกิน (นครพนม/บึงกาฬ/กรุงเทพฯ) → pid อยู่ page 2+ | 5 งาน | ✅ เพิ่ม pagination |
| งานประมูลแล้ว (W0) — ไม่แสดงใน active search | 1 งาน | ❌ deadline ไม่มีความหมายแล้ว |
| ไม่มี D0 ยัง (ยังร่างอยู่/รอประกาศ) | 3 งาน | ❌ ตอนนี้ — pipeline รัน scraper ทุกวันจะจับได้เอง |
| หน่วยงานนอกพื้นที่ (มุกดาหาร) | 2 งาน | ❌ ไม่จำเป็นต้องแก้ |
| keyword ค้นไม่เจอ (งานหมดอายุ/department ไม่ตรง) | 3 งาน | ⚠️ ลอง paginate ก่อน |

**ไฟล์ที่แก้ไข:**
- `scripts/Sebastian_Scraper.py` — rewrite `fetch_deadline_via_pdf()` แทน direct URL approach เดิม
- `scripts/patch_deadlines.py` — rewrite ทั้งหมดด้วย PDF approach + Thai numeral handling

**Pipeline ที่รันวันนี้:**
```
patch_deadlines.py → Classifier → LINE Notify (ส่งสำเร็จ 2 part)
```

LINE แสดง "📆 ยื่นซอง: 18/05/2569  ⏳ เหลือ 5 วัน" สำหรับงาน 69049365887 ✅

**ต้องทำต่อ (ถ้าต้องการ deadline ครบ):**
- [ ] เพิ่ม pagination ใน `fetch_deadline_via_pdf()` — ค้นหาทุก page จนกว่าจะเจอ pid (แก้กรณี keyword กว้างเกิน)

---

## Rate Limit Research & Parallel Batching (2026-05-15)

### สถานะ: ✅ เสร็จแล้ว — Pipeline runtime 2hr → ~45-60 min

### ปัญหาเดิม
Pipeline ใช้เวลา 2 ชั่วโมง (06:00-08:00) ส่วนใหญ่เสียให้ rate limit:
- ~20 hits × 120s = ~40 นาที นอนรอเฉยๆ
- Sequential pagination 1.5s/หน้า × ~600 หน้า/จังหวัด

### วิธีทดสอบ
สร้าง 4 test scripts (ลบทิ้งแล้ว) ทดสอบจริงกับ eGP API:
1. `explore_egp_api.py` — จับ URL pattern + capture announcementToken
2. `test_egp_pagesize.py` — ทดสอบ pageSize parameters ทุกชื่อ
3. `test_egp_burst.py` — หา parallel burst threshold
4. `test_multi_context.py` — ทดสอบว่า rate limit ผูกกับ token หรือ IP
5. `test_rate_threshold.py` — หา sustained rate ที่ปลอดภัย

### สิ่งที่ค้นพบ

**1. PageSize ตายตัว = 10 รายการ/หน้า**
- ทดสอบทุก parameter (pageSize, size, limit, perPage, rows, recordsPerPage, max, count, take, ฯลฯ) → server ignore ทั้งหมด
- ความหมาย: นครพนม 5990 รายการ = 599 หน้า (ไม่ใช่ 300 หน้าที่ 20/หน้า)

**2. Rate limit ผูกกับ IP ไม่ใช่ session token**
- ทดสอบ: สร้าง 2 browser contexts (cookies/tokens แยก)
- หลอม context A ด้วย burst → context B ทดสอบทันที
- ผล: context B โดน rate limit เลย 20/20 → ผูกกับ IP
- ความหมาย: เปิดหลาย contexts ไม่ช่วย ต้องใช้ proxy เท่านั้น

**3. Rate limit threshold: ~100 reqs / 120s window**
- 1 req/s sustained → hit ที่ req 110 (~106s)
- 1.5 req/s sustained → hit ที่ req 100 (~66s)
- 3 req/s sustained → hit ที่ req 80-100 (~28s)
- ความหมาย: ส่งเร็วก็โดนเท่ากับส่งช้า

**4. Parallel burst เร็วมาก (ภายใน threshold)**
- 20 parallel requests พร้อมกัน → 50ms each
- 80 parallel (4 batches) → ผ่านสบาย
- 100+ → เริ่มโดน

### กลยุทธ์ที่ใช้: Burst-then-Wait

แทน sequential 1.5s/หน้า → **burst 80 reqs ใน 5s แล้วรอ 90s** (ให้ requests aged out จาก rate limit window)

```python
BATCH_SIZE      = 20      # 20 parallel/batch
BATCHES_PER_GROUP = 4     # 4 × 20 = 80 reqs/group
GROUP_COOLDOWN  = 90      # รอเต็ม window
RATE_LIMIT_RECOVERY = 90  # ถ้าโดนก็รอ 90s
```

**Effective rate: ~0.84 req/s** (vs 0.5-0.65 req/s ของ sequential + rate limit hits เดิม)

### ผลลัพธ์
- Province 600 หน้า: ~12 นาที (เดิม ~30 นาที)
- Total pipeline: ~45-60 นาที (เดิม 2 ชั่วโมง) = **2-2.5x faster**
- ปริมาณงานเท่าเดิม (ไม่ตัด max_pages ไม่มี early-exit) — ปลอดภัย 100%

### ไฟล์ที่แก้
- `scripts/Sebastian_Scraper.py` — `search_keyword_process5()` rewrite ใช้ parallel batching + ใส่ try/except dept loop
- `scripts/Sebastian_Classifier.py` — เพิ่ม pending_award + tor_review classification
- `scripts/Sebastian_LINE_Notify.py` — ส่ง 2 ส่วน (active + tor_review)
- `scripts/Sebastian_Winner_Checker.py` — เพิ่ม column "% ลดจากราคากลาง"
- `scripts/create_new_sheets.py` — สร้าง pending_award + tor_review sheets (รันแล้ว)
- `run_pipeline.bat` — เพิ่ม wait หลัง kill Chrome + หลัง health-check ผ่าน

---

## Checkpoint — 2026-05-15 (SaaS Roadmap Research Session)

### สิ่งที่ทำในวันนี้

**1. Proxy / Rate Limit Legal Analysis**
- สรุป: proxy bypass = gray area ตาม พ.ร.บ. คอมพิวเตอร์ มาตรา 7
- eGP ไม่มี ToS เป็นลายลักษณ์อักษร แต่ data.go.th มีแค่ static CSV ล้าหลัง 1.5 ปี
- สรุป: ไม่แนะนำ proxy, ไม่คุ้ม risk vs reward

**2. eGP API Sort Order — ทดสอบจริง**
- เขียน `test_sort_order.py` ยิง API กับ Chrome debug port ที่เปิดอยู่
- ผล: **API sort by `announceDate` DESC (ใหม่→เก่า) ยืนยัน 100%**
  - Page 1-5: ทั้งหมด 2026-05-15 (วันทดสอบ)
  - Page 10: 2026-05-14
  - Page 15: 2026-05-13
- พบ outlier: page 1 มี 1 งาน announceDate=2026-05-08 โผล่ขึ้นมา (re-announce)
- ความหมาย: early-exit แบบ date-based ใช้ได้ แต่ต้องมี buffer ≥2 วัน
- คุณกัญจน์ตัดสินใจ: **ไม่ทำ early-exit** (ความเสี่ยงพลาดงาน detection ยาก)
- ลบ test script ทิ้งแล้ว

**3. SaaS Vision & Roadmap 2**
- คุณกัญจน์เปิดเผย business vision: ปล่อยเช่าระบบให้ผู้รับเหมารายอื่น
  - 1,500 บาท/เดือน/จังหวัด/บริษัท
  - เป้า 90 บริษัท × 77 จังหวัด = **6,930 บริษัท** → Revenue ceiling ~10.4M/เดือน
- บันทึก Roadmap 2 เข้า memory (`project_saas_roadmap.md`):
  - **Phase 1 (ปัจจุบัน):** ใช้เอง 2 อำเภอ — stable ก่อน
  - **Phase 2 (Pilot):** 5-10 ลูกค้านครพนม 3-4 สัปดาห์ — 6 ขั้นตอน multi-tenant
  - **Phase 3 (Scale):** Cloud + PostgreSQL + 77 จังหวัด + บริษัท SaaS
- **คุณกัญจน์สั่ง: ยึด Roadmap นี้ ห้ามออกนอกเส้นทาง**
- เพิ่ม Mermaid Flowchart ขนาดกะทัดรัดเข้า roadmap.md

### ไฟล์ที่เปลี่ยน
- `C:\Users\Ace\.claude\projects\C--Bid-Master-System\memory\project_saas_vision.md` — สร้างใหม่
- `C:\Users\Ace\.claude\projects\C--Bid-Master-System\memory\project_saas_roadmap.md` — สร้างใหม่ (Roadmap 2)
- `MEMORY.md` — เพิ่ม 2 entries ใหม่

### สถานะ Pipeline ปัจจุบัน
- Pipeline ทำงาน: 45-60 นาที/รัน, รัน 06:00 น. ทุกวัน
- Phase 1 stable — ไม่มี optimization ค้างอยู่
- รอคุณกัญจน์ตัดสินใจเริ่ม Phase 2 เมื่อพร้อม

---

## Checkpoint — 2026-05-15 (Sheet Redesign — IN PROGRESS)

> **สำหรับ Claude ID ใหม่:** อ่าน `docs/sheet_redesign_plan.md` แล้วทำต่อจาก Phase ที่ค้าง

### เหตุผล
คุณกัญจน์รายงาน: "scrape ดูราบรื่น แต่ใส่ Google Sheet มั่วไปหมด งานหมดวันยื่นซองโผล่ใน active_bidding, ไม่มี reset, ความน่าเชื่อถือตกหนัก"

Inspect 17 sheets เจอ root causes:
- Sheet duplicate / legacy เยอะ (raw_jobs vs raw_jobs_all, ranked_jobs ตัด Ranker ไปแล้ว, dashboard test, ฯลฯ)
- Schema ไม่ consistent (publish_date eng vs วันที่ประกาศ ไทย)
- Classifier ไม่ filter deadline → 7 งาน e-bidding หมดอายุ -1 ถึง -77 วัน ค้างใน active_bidding
- Append-only ไม่มี reset cycle

### การตัดสินใจ (user)
| คำถาม | คำตอบ |
|---|---|
| Backup | local JSON dump (SA ไม่มี Drive quota) |
| tor_review | เก็บไว้ (Phase 2 SaaS) |
| Migration | Big bang — ล้าง+rebuild |
| Scraper | เขียน all_jobs ตัวเดียว → Classifier rebuild derived |

### Phases
| # | Phase | Status |
|---|---|---|
| 1 | Backup → `backups/sheets_2026-05-15_2046/` | ✅ 17 sheets, 11,294 rows |
| 2 | Blueprint → `docs/sheet_redesign_plan.md` | ✅ |
| 3 | สร้าง all_jobs schema (15 cols) | ✅ |
| 4 | Migrate raw_jobs.json → all_jobs | ✅ 8,690 unique rows |
| 5 | แก้ Sebastian_Scraper เขียน all_jobs (upsert) | ✅ |
| 6 | แก้ Sebastian_Classifier state machine | ✅ active=11 / pending=18 / awarded=132 |
| 7 | แก้ LINE_Notify (schema ใหม่), Winner_Checker (cache file), patch_deadlines (all_jobs) | ✅ |
| 8 | ลบชีทเก่า 11 ตัว | ✅ เหลือ 7 ชีท |
| 9 | Test E2E (Classifier + LINE_Notify dry-run) | ✅ |

### ผลลัพธ์สุดท้าย

**Sheet structure (17 → 7):**
- `all_jobs` 8,690 rows — Source of Truth
- `active_bidding` 7 งาน — งานก่อสร้างในพื้นที่ deadline ≥ วันนี้
- `pending_award` 17 งาน — deadline หมด ยังไม่ประกาศผู้ชนะ
- `awarded_jobs` 132 งาน — มี winner data
- `tor_review` reserved (Phase 2 SaaS)
- `calc_road` + `cost_data_By_Dexter` (manual ของพ่อ — ไม่แตะ)

**Scripts ที่แก้:**
| File | เปลี่ยน |
|---|---|
| `Sebastian_Scraper.py` | upsert all_jobs (1 sheet) แทน append 3 sheets |
| `Sebastian_Classifier.py` | rewrite — state machine + clear/rewrite + province + construction filters |
| `Sebastian_LINE_Notify.py` | อ่าน schema ใหม่ (publish_date / deadline / days_remaining) |
| `Sebastian_Winner_Checker.py` | rewrite — เขียน `data/winner_cache_bootstrap.json` แทน sheet ตรง ๆ |
| `patch_deadlines.py` | source = all_jobs, auto-trigger Classifier rebuild |
| `migrate_to_all_jobs.py` (ใหม่) | one-time migration script |
| `build_winner_cache.py` (ใหม่) | bootstrap winner cache จาก backup |

**Pipeline ใหม่:**
```
Scraper          → upsert all_jobs (1 sheet, single source of truth)
Patch deadlines  → fetch missing deadlines → update all_jobs → rebuild
Classifier       → clear+write 3 derived sheets (state machine)
Winner Checker   → update winner_cache.json → rebuild
LINE Notify      → อ่าน active_bidding (clean จาก Classifier)
```

**ปัญหาเดิม → แก้แล้ว:**
- ❌ งานหมดวันยื่นซองโผล่ใน active → ✅ Classifier filter ตาม deadline ทุกครั้ง
- ❌ ไม่มี reset → ✅ clear+rewrite ทุก pipeline run
- ❌ Schema ไม่ consistent → ✅ schema เดียว all_jobs + extra ใน derived
- ❌ ความน่าเชื่อถือตก → ✅ source of truth ตัวเดียว

### Backup
- Local JSON: `backups/sheets_2026-05-15_2046/` (17 sheets, 11,294 rows)
- Drive copy: ผู้ใช้ทำเอง 1 คลิก (File → Make a copy)

---

## Checkpoint — 2026-05-15 (Bug investigation: filter เข้มเกินไป)

> **สำหรับ ID ใหม่:** อ่าน `docs/sheet_redesign_plan.md` + entry นี้

### Bug ที่ user รายงาน
- active_bidding / pending_award มีแต่งานที่ keyword "นครพนม"
- งานที่ scrape ผ่าน dept_search_terms (เช่น "ตำบลโพนทอง", "เทศบาลตำบลศรีสงคราม") หายไป
- มีงานยื่นซองวันนี้ที่พ่อสนใจ — ไม่ขึ้น

### Root cause hypothesis
Classifier filter `is_in_target_province()` หา "นครพนม"/"บึงกาฬ" ใน province + fallback ใน search_keyword/title/department
- งานที่ scrape ด้วย dept_search → search_keyword = "ตำบลโพนทอง" (ไม่มีชื่อจังหวัด)
- province field อาจว่างหรือเป็นชื่อหน่วยงานต้นสังกัด
- ถ้า title + department ก็ไม่มี "นครพนม"/"บึงกาฬ" → ตก filter

### กำลังสืบ
- นับ province distribution ใน all_jobs (e-bidding + กำลังประมูล)
- หาตัวอย่างงานที่ skipped_off_province
- แก้ filter ให้ครอบคลุม dept-source jobs

### Diagnosis
29 e-bidding "กำลังประมูล" ใน all_jobs:
- 20 มี province="นครพนม"/"บึงกาฬ" (ผ่าน filter เก่า)
- 5 search_keyword จาก dept_search (เช่น "เทศบาลตำบลศรีสงคราม", "อบต.ดงบัง"):
  - 2 ตัวเป็น cross-province false match (อบต.ไผ่ล้อม จ.พิษณุโลก, อบต.หนองแวง จ.มหาสารคาม) — ถูกต้องที่ตัด
  - 3 ตัวเป็นงานในนครพนมจริง — ถูกตัดผิด ❌
- 4 อื่น ๆ (มุกดาหาร 3, กรุงเทพ HQ ทำงานในนครพนม 1)

### Root cause
1. `is_in_target_province` ดู province field + fallback "นครพนม"/"บึงกาฬ" string match
2. งาน dept_search มี search_keyword = "เทศบาลตำบลศรีสงคราม" (ชื่อเต็ม) — ไม่มี "นครพนม" → ตก filter
3. ไม่ได้ใช้ `DEPT_PROVINCE_MAP` ของ Scraper (28 entries) เป็น fallback

### Fix (2026-05-15 21:46)
แก้ `Sebastian_Classifier.is_in_target_province()`:
- Case A: `province` ตรงเป้า → True
- Case C: `province` มีค่าแต่ไม่ใช่เป้า → True ถ้า title มี "จ.นครพนม"/"จังหวัดนครพนม" (HQ ทำงานต่างจังหวัด); else False (ตัด cross-province false match)
- Case B: `province` ว่าง → fallback ดู title/dept + DEPT_PROVINCE_MAP key (substring match)

### ผลหลัง fix
| Sheet | ก่อน | หลัง |
|---|---|---|
| active_bidding | 7 | **8** (+1 อบต.ดงบัง) |
| pending_award | 17 | 17 |
| awarded_jobs | 132 | 132 |
| skipped off-province | 93 | 82 |

### หมายเหตุ
- jid=69049235336 (อบต.ดงบัง) — deadline ว่าง → patch_deadlines จะดึงให้รอบถัดไป
- งาน user สนใจที่หาย (อาจเป็น) jid=69049235336 → ตอนนี้อยู่ใน active แล้ว ✅

---

## งานที่ N+5: Schema Drift Healing — 1,300 misaligned rows (2026-05-15 → 2026-05-16)

### สถานะ: ✅ เสร็จแล้ว

### Bug ที่ user รายงาน
- พบงานใน all_jobs A1476 (jid=69059074818, ตำบลโพธิ์หมากแข้ง — งานก่อสร้างถนน คสล. ทางเข้าวัดถ้ำชัยมงคล)
- ตรงกับเกณฑ์บริษัทชัดเจน แต่ไม่ปรากฏใน active_bidding หรือ pending_award

### Diagnosis (debug_row_1476.py + count_misaligned.py)
Row 1476 มี:
- `project_status = 'province:องค์การบริหารส่วนตำบลโพธิ์หมากแข้ง | หนังสือเชิญชวน/ประกาศเชิญชวน'` ← raw quantity_note หลุดมา
- `search_keyword = ''` (ว่าง)
- `tor_url = 'new'` ← ผิด
- `province = ''`

นับ misaligned rows ใน all_jobs:
- 737 rows มี project_status เป็น `'province:...'` หรือ `'keyword:...'`
- 1,340 rows มี search_keyword ว่าง
- 772 rows มี tor_url='new'
- 601 rows มี project_status เป็นตัวเลข ('0','1','4','5','6','7','8')

### Root cause
`migrate_to_all_jobs.py` (Phase 4 ของ Sheet Redesign) ใช้ `headers` ของ raw_jobs.json[0] เป็น single index map สำหรับทุก row แต่ raw_jobs.json มี **3 schema variants** ปนกัน (เพราะ Scraper เคยเปลี่ยน schema หลายครั้ง):

| Variant | จำนวน | tor_url | status | project_status | quantity_note |
|---|---:|---|---|---|---|
| A (เก่า) | 737 | `'new'` | mapped value | raw `'province:X \| flow'` | ว่าง |
| B (clean) | 7,353 | URL หรือว่าง | ว่าง | mapped value | raw `'province:X \| flow'` |
| C (skip) | 601 | `'skip'`/`'docs_failed'` | raw `'keyword:X \| flow'` | stage code (1-8) | step code (IM/W0/W1) |

migrate_to_all_jobs.py ดึง `g(r, 'project_status')` ตรงๆ → Variant A/C ถูก map ผิดทั้งหมด

### Fix — 2 layers

**Layer 1: Healing data (`scripts/smart_migrate.py`)**
- ตรวจ schema variant per-row จาก signature ของ tor_url + project_status
- Variant A: ของจริง project_status อยู่ใน `status` field, search_keyword extract จาก raw_qn
- Variant B: schema สมบูรณ์ ใช้ตามปกติ
- Variant C: ของจริงอยู่ใน `status` (raw_qn) → split " | " + map flow_name → project_status
- Backup all_jobs ปัจจุบันลง `backups/all_jobs_pre_smart_migrate/` ก่อน clear+rewrite

**Layer 2: Resilient Classifier (`scripts/Sebastian_Classifier.py`)**
- `_normalize_project_status()`: รับ raw string → return mapped value
  - ถ้าเป็น `'กำลังประมูล'/'ประมูลแล้ว'/...` → return ตรงๆ
  - ถ้าเริ่มต้น `'province:'/'keyword:'` → split " | " + FLOW_STATUS_MAP lookup
  - ถ้าเป็นตัวเลข → return "" (ไม่มี info พอ map)
- `is_in_target_province()` Case D: ถ้า search_keyword ว่าง → fallback ตรวจ `department + subdistrict` กับ DEPT_PROVINCE_MAP
- Import `FLOW_STATUS_MAP` จาก `Sebastian_Scraper` เป็น single source of truth

### ผลหลัง fix
| Sheet | ก่อน | หลัง | Δ |
|---|---:|---:|---:|
| active_bidding | 8 | **13** | +5 |
| pending_award | 17 | **21** | +4 |
| awarded_jobs | 132 | 132 | 0 |
| **รวมงานกู้คืน** | | | **+9** |

Variant breakdown หลัง smart_migrate:
- A_old: 737 → mapped ถูกแล้ว
- B_clean: 7,353 → ใช้ตามปกติ
- C_skip: 563 → mapped ถูกแล้ว
- fallback: 38 → ยังต้อง investigate (น้อยมาก)

### Verify
jid=69059074818 (row 1476 ของ user) ตอนนี้อยู่ใน `active_bidding` row 7:
- project_status: `'กำลังประมูล'` ✓
- search_keyword: `'องค์การบริหารส่วนตำบลโพธิ์หมากแข้ง'` ✓
- tor_url: `''` ✓
- deadline ว่าง → รอ patch_deadlines ดึง PDF เติม

### ไฟล์ที่เพิ่ม/แก้
- `scripts/smart_migrate.py` (ใหม่) — per-row variant detection + heal
- `scripts/Sebastian_Classifier.py` (แก้) — `_normalize_project_status()` + Case D
- `scripts/coverage_audit.py` (ใหม่) — วัด pond size 3 ชั้น (API total / keyword gap / filter drop)
- `scripts/count_misaligned.py` (ใหม่) — debug helper
- `scripts/debug_row_1476.py` (ใหม่) — trace filter logic per row
- `backups/all_jobs_pre_smart_migrate/all_jobs_2026-05-15_2343.json` — pre-heal backup

### Followup
- รัน `patch_deadlines.py` (ต้อง Chrome) — เติม deadline ของงานใหม่ที่กู้คืนได้
- พิจารณา sampling audit (จาก idea ของ user): สุ่ม 100 จาก eGP → เทียบกับระบบเรา → คำนวณ recall % + classification accuracy %

---

## งานที่ N+6: Stale Data Refresh — query eGP API สดต่อ active job (2026-05-16)

### สถานะ: ✅ เสร็จแล้ว

### Bug ที่ user รายงาน
- jid=69039325763 อยู่ใน active_bidding แต่จริงๆ ประกาศผู้ชนะแล้ว
- jid=69059074818 อยู่ใน active_bidding แต่ "ยังรับฟังคำวิจารณ์อยู่" (ยังไม่เปิดให้ยื่นซองจริง)

### Root cause
1. **ข้อมูล all_jobs frozen** ตั้งแต่ migration (2026-05-15 23:43) → ไม่มี Scraper run ใหม่หลังจากนั้น
2. **Winner Checker เช็คเฉพาะ status='ประมูลแล้ว'** — ไม่ catch งานที่มีผู้ชนะแล้วแต่ status เรายังเป็น 'กำลังประมูล'
3. **flowName "หนังสือเชิญชวน/ประกาศเชิญชวน" → mapped เป็น "กำลังประมูล"** — แต่จริงๆ ระยะนี้ครอบคลุมทั้ง "รับฟังคำวิจารณ์" (ยังไม่เปิดยื่น) และ "เปิดยื่นซอง"

### eGP API ที่ค้นพบใหม่
- **`getProjectDetail?projectId=X`** → คืน `flowSeqno`, `stepId`, `flowId`, `announceType`
  - flowSeqno guide: 1-3=กำลังเตรียม, 4=กำลังประมูล, 5+=ประมูลแล้ว
  - stepId pattern: M03/U03=TOR draft, S01=Submission open, W03=Winner stage
- **`getProcureResult?projectId=X`** → คืน `procureResultList[].procureResultDataResponse[]`
  - **Winner = row ที่มี `priceAgree != null`** (ราคาตกลง)
  - `data.announceDate` = วันประกาศผู้ชนะ
  - resultFlag P/N = ผ่าน/ไม่ผ่าน, แต่ priceAgree เป็น signal ที่ชัดเจนกว่า

### Fix — `scripts/refresh_active_jobs.py` (ใหม่)
- Query 2 endpoints per active job:
  1. `getProcureResult` → ถ้ามี winner (priceAgree != null) → cache + status='ประมูลแล้ว'
  2. `getProjectDetail` → flowSeqno → derive project_status
- Update all_jobs (project_status, last_seen_at, deadline ถ้ามี)
- Trigger Classifier rebuild ภายในหลัง update

### Pipeline integration
เพิ่ม `refresh` เป็น step 4/8 ใน `Sebastian_Pipeline.py`:
```
scrape → classify → refresh → download → analyze → cost → rank → notify
```
- รัน 06:00 ทุกวันก่อน LINE notify → ข้อมูลใน LINE จะ fresh เสมอ
- ต้องการ Chrome (port 9222) — ถ้าไม่ได้เปิด refresh จะ fail แต่ Pipeline จะ continue

### ผล (Full refresh ทั้ง 9 active jobs)
| Sheet | ก่อน | หลัง | Δ |
|---|---:|---:|---:|
| active_bidding | 9 | **2** | -7 |
| pending_award | 23 | 23 | 0 |
| awarded_jobs | 132 | **133** | +1 |

**Insight: 7 จาก 9 active jobs จริงๆ ยังเป็น "กำลังเตรียม" (รับฟังคำวิจารณ์)** — ไม่ได้เปิดยื่นซองจริง
- 69039325763: refresh พบ winner = ห้างหุ้นส่วนจำกัด ลัทธนนต์คอนสตรัคชั่น @ 9,976,000 (-0.22%) → ย้าย awarded ✓
- 69059074818 + 6 อื่นๆ: flowSeqno=3 → "กำลังเตรียม" → ตัดออกจาก active ✓
- เหลือ 2 active จริง (jid=69049234631 + 69049094319, flowSeqno=4 stepId=S01)

### ไฟล์ที่เพิ่ม/แก้
- `scripts/refresh_active_jobs.py` (ใหม่) — refresh active jobs จาก eGP API
- `scripts/probe_project_api.py` (ใหม่) — probe eGP endpoints
- `scripts/debug_2_jobs.py` (ใหม่) — diagnostic helper
- `scripts/Sebastian_Pipeline.py` (แก้) — เพิ่ม refresh step 4/8

### Followup
- พิจารณาเพิ่ม `tor_review` sheet (Phase 2) สำหรับงาน flowSeqno=3 ที่กำลังรับฟังคำวิจารณ์ — เพื่อ pre-warning user ว่ามีงานกำลังจะเปิดยื่นซอง
- ตรวจสอบว่า `Winner_Checker` ยัง relevant ไหม หรือ replace ด้วย `refresh_active_jobs` ทั้งหมด

---

## งานที่ N+7: 4-Sheet Lifecycle Redesign (2026-05-16)

### สถานะ: ✅ เสร็จแล้ว

### Bug ที่ user รายงาน
- jid=69059074818 อยู่ใน active_bidding แต่จริงๆ "ยังรับฟังคำวิจารณ์อยู่"
- 167 jobs ที่ status='ประมูลแล้ว' ไม่มี winner ใน cache → หายไปไม่ขึ้นที่ไหน

### Root cause
3-sheet structure (active/pending/awarded) ไม่ครอบคลุม lifecycle จริงของ eGP:
- "รับฟังคำวิจารณ์" (flowSeqno=3) ไม่ใช่ทั้ง active หรือ pending
- "ประมูลแล้ว ไม่มี winner" ตกหล่นเพราะไม่ผ่าน status='กำลังประมูล' filter

### Fix — 4-Sheet Lifecycle (สอดคล้อง eGP flow)
```
TOR Draft → [รับฟังคำวิจารณ์] → [เปิดยื่นซอง] → [รอรู้ผู้ชนะ] → [ประกาศแล้ว]
              tor_review        active_bidding   pending_award    awarded_jobs
```

| Sheet | คือ | Logic | Action ของ user |
|---|---|---|---|
| 🟢 tor_review | รับฟังคำวิจารณ์ | flowSeqno≤3 (กำลังเตรียม) | เตรียมตัว, อ่าน TOR ล่วงหน้า |
| 🔵 active_bidding | ยื่นซองได้ตอนนี้ | กำลังประมูล + deadline≥today | **ตัดสินใจประมูลตอนนี้** |
| 🟡 pending_award | รอรู้ผู้ชนะ | deadline ผ่าน OR ประมูลแล้ว ไม่มี winner | รอ refresh / benchmark คู่แข่ง |
| ⚪ awarded_jobs | รู้ผู้ชนะแล้ว | มี winner cache | reference, discount %, คู่แข่ง |

### ไฟล์ที่เพิ่ม/แก้
- `scripts/Sebastian_Classifier.py` — เพิ่ม TOR_REVIEW_HEADERS, แยก stage_note vs wait_reason, write 4 sheets
- `scripts/Sebastian_LINE_Notify.py` — เปิด `get_tor_review_jobs()` (เดิม return []), แก้ `_build_tor_block()` ให้ใช้ schema ใหม่ (publish_date, stage_note)
- `scripts/refresh_active_jobs.py` — เพิ่ม retry + cooldown + valid-data check (ป้องกัน rate limit ทำ status ผิด)

### Insight ระหว่างทำ
**Rate limit ของ eGP API:** refresh 167 jobs ติดกัน (sleep 0.5s) → 68/167 = 41% ได้ empty data → ทำให้ status mapping ผิด (default เป็น "กำลังเตรียม")
- Fix: เพิ่ม `valid` flag ใน fetch_project_detail (ตรวจ flowSeqno>0 OR stepId), retry 1 ครั้ง delay 3s, ถ้ายัง empty → keep current status (ไม่ overwrite)
- Fix #2: sleep 1.5s ระหว่าง requests + cooldown 30s ทุก 50 jobs

### ผลรวม (after 2 รอบ refresh = 167 + 76 = 243 jobs)
| Sheet | ก่อน | หลัง |
|---|---:|---:|
| tor_review | (ไม่มี) | **8** |
| active_bidding | 2 | **5** |
| pending_award | 23 | **25** |
| awarded_jobs | 133 | **295** (+162 winners) |

**ตัวอย่าง winner ที่กู้คืน:**
- jid=68109450159: ห้างหุ้นส่วนจำกัด **ยศประทานรุ่งเรืองทรัพย์** @ 1,480,000 (-28.16%) ← บริษัทของ user!
- + 161 winner อื่นๆ ที่เคยอยู่ใน "ประมูลแล้ว ไม่มี cache"

### Followup
- รัน refresh เป็น cron 06:00 ผ่าน Sebastian_Pipeline.py step 4/8 — winner ใหม่จะ catch อัตโนมัติ
- พิจารณา Winner_Checker ตอนนี้ redundant กับ refresh_active_jobs

---

## งานที่ N+8: Pre-sleep cleanup (2026-05-16, 02:30) — A.1+A.2 fix, B research

### Task A.1: patch_deadlines สำหรับ active jobs ✅
- ดึง deadline ได้ 4 จาก ~9 candidates (jids: 69049276732, 69049216940, 69049200617, 68089313232)
- ทั้ง 4 deadline ผ่านไปนาน (เก่าสุด 20/03/2026 = 2 เดือนแล้ว) → ย้ายจาก active → pending
- เหลือ active 4 jobs ที่ deadline ยังว่าง (tor_url='' → patch ดึงไม่ได้ — ดู Task B)

### Task A.2: Heal winner_cache_bootstrap.json (50 bad winners) ✅
**Bug:** 50 จาก 295 entries ใน winner_cache_bootstrap.json มี winner_name='province:X | flow' (raw qn)
**สาเหตุ:** build_winner_cache.py สร้างจาก awarded_jobs.json backup ที่ schema เลื่อน (เหมือน bug schema drift แต่ครั้งนี้อยู่ใน cache file)

**Fix 2 ขั้น:**
1. `scripts/heal_winner_cache.py` (ใหม่) — ลบ 50 bad entries (backup ลง `data/winner_cache_pre_heal.json`)
2. รัน refresh บน 50 jids → ดึง winner จริงจาก eGP getProcureResult → cache มีข้อมูลถูก
3. แก้ `Classifier.load_winner_cache()` — skip bad winners ตอน load จาก awarded_jobs sheet (ป้องกัน sheet เก่า overwrite cache file ที่สะอาด)

**ผล:** awarded_jobs ตอนนี้ winner_name = 245 proper + 50 ถูก = 295 (0 bad)

### Task B: Investigation — งาน "ยกเลิก" หรือ "deadline ผ่าน" ใน active_bidding (research only, ไม่แก้)

#### B.1: ทำไม active มีงาน "ยกเลิก" (cancelled)?

**Root cause:** eGP API field `projectStatus` (ใน getProjectDetail response):
- `"A"` = Active (ปกติ)
- `"R"` = **Cancelled (ยกเลิก/Removed)**

**ตัวอย่างที่ probe ได้:**
| jid | flowSeqno | stepId | projectStatus | announceType | สถานะใน all_jobs |
|---|---:|---|---|---|---|
| 69049431523 | 0 | B03 | **R** | W1 | ยกเลิก |
| 69019024418 | **4** | S01 | **R** | D1 | ยกเลิก |
| 69049202990 | 0 | B03 | **R** | W1 | ยกเลิก |

**Bug ที่ refresh_active_jobs.py:** ใช้แค่ flowSeqno → `flowSeqno=4` → ใส่ "กำลังประมูล" → Classifier ใส่เข้า active. **ไม่ได้เช็ค projectStatus="R"**

**Pattern เพิ่มเติม:** `announceType` ที่มี suffix "1" (D1, W1) อาจเป็น cancelled version ของ stage นั้น (D0/W0 = Original, D1/W1 = Cancelled)

**Fix proposal (สำหรับเช้านี้):**
```python
# fetch_project_detail() — เพิ่ม check projectStatus ก่อน
if data.get("projectStatus") == "R":
    return {"project_status": "ยกเลิก", "valid": True, ...}
# else use flowSeqno mapping เดิม
```

#### B.2: ทำไม active มีงาน "deadline ผ่านแล้ว"?

**Root cause:** Classifier logic:
```python
dl = parse_thai_date(g(r, "deadline"))
if dl is None:
    # deadline ว่าง → active (pessimistic)
    active.append(base + [""])
```
- งานที่ deadline ว่างจริงๆ + project_status='กำลังประมูล' → ใส่ active เป็น default
- ทำให้ดูเหมือน "active" ทั้งที่ deadline จริงอาจผ่านไปแล้ว (เพราะ publish > 1 เดือน)

**ทำไม deadline ว่าง:**
1. Scraper API (eGP search) ไม่ส่ง deadline กลับมา — ต้อง parse จาก PDF "ประกาศเชิญชวน"
2. patch_deadlines.py ใช้ tor_url ใน all_jobs → fetch PDF → parse
3. **ถ้า tor_url='' → patch ดึงไม่ได้** (ตอนนี้ active 4 ตัวเป็นแบบนี้หมด)
4. tor_url ว่างเพราะ migration จาก raw_jobs.json ไม่มี field นี้

**Verify จาก getProjectDetail API:** field deadline **ไม่อยู่ใน response เลย** — confirm ว่าต้องใช้ PDF method

**Fix proposal (สำหรับเช้านี้, 2 ทางเลือก):**

**A) Re-scrape ทั้งหมด** เพื่อ refresh tor_url
- รัน Sebastian_Scraper.py → ทุก row จะได้ tor_url ใหม่
- จากนั้น patch_deadlines → ดึง deadline ครบ
- ใช้เวลา 30-60 นาที

**B) Heuristic fallback ใน Classifier**
- ถ้า publish_date > 30 วันมาแล้ว + deadline ว่าง → ย้ายไป pending (สมมติ deadline ผ่านแล้ว)
- ใช้เวลา 5 นาที, แต่อาจ false-positive

**แนะนำ:** A — ปลอดภัยกว่า + ได้ tor_url สำหรับทุก row

#### B.3: หลักฐานเชิงปริมาณ
- ตัวอย่าง projectStatus="R" + flowSeqno=4 = 1 ใน 3 cancelled samples → ~33% ของ cancelled มีโอกาสหลุดเข้า active ผ่าน refresh
- ใน all_jobs ทั้งหมดมี 'ยกเลิก' กี่งาน: ต้องนับ (ทำเช้า)

### ไฟล์ที่เพิ่ม/แก้ใน Task A
- `scripts/heal_winner_cache.py` (ใหม่)
- `scripts/Sebastian_Classifier.py` (แก้ load_winner_cache — skip bad)
- `data/winner_cache_bootstrap.json` (heal — 295 → 245 → 295 with fresh winners)
- `data/winner_cache_pre_heal.json` (backup)

### Action items สำหรับเช้านี้ (2026-05-16, ตื่น)
1. **สำคัญสูง — Fix B.1**: เพิ่ม `projectStatus="R"` check ใน refresh_active_jobs.py + Classifier ตัด "ยกเลิก" ออกจาก active (ปัจจุบัน "ยกเลิก" ตัดอยู่แล้ว)
2. **สำคัญกลาง — Fix B.2 ทาง A**: รัน Sebastian_Scraper.py → patch_deadlines → ดึง deadline ครบ
3. **ตรวจ active หลังแก้** ว่าทุก job มี deadline + projectStatus='A' จริงๆ
4. **ตั้ง cron 06:00** ถ้ายังไม่ได้ตั้ง

---

## งานที่ N+9: Phase A complete + audit + Phase B bid_history + cron (2026-05-16)

### Phase A (Classifier rewrite) ✅
- 6-sheet stepId-driven: pre_tor / tor_review / active_bidding / pending_award / awarded_jobs / cancelled_jobs
- Letter-prefix fallback (defensive for unknown stepIds)
- Added 3 columns to all_jobs: step_id, project_status_raw, announce_type
- Re-scrape + patch_deadlines + refresh
- Fixed bug: active_bidding ต้อง deadline ≥ today (ไม่งั้น stale M03/S01 ค้าง)
- Result: active 6 (M03 ทั้งหมด), tor 5, pending 18, awarded 303, cancelled 43

### Audit ชีตอื่น ✅ (35/35 pass)
- tor_review (5/5): stepId U* + projectStatus=A
- cancelled (10/10): projectStatus=R OR announce ends "1"
- awarded sample (20/20): มี winner หรือ stepId W*/C*/I*
- pre_tor (0): empty (ไม่มี Q stage ใน data ตอนนี้)

### Phase B: bid_history (Competitive Intelligence) ✅
- สร้าง `bid_history` sheet (12 cols): job_id, bidder_name, bidder_tin, price_proposal, price_agree, result_flag, is_winner, is_sme, is_joint_venture, jv_partners, consider_desc, fetched_at
- ขยาย `awarded_jobs` schema: +deliver_day, +num_bidders (รวม 24 cols)
- `scripts/fetch_bid_history.py` (ใหม่) — migration ดึง procureResult ทั้ง bidder list
- Migration 2 รอบ: 200/303 awarded → 1,545 bidders ใน bid_history
- 103 ยัง pending (rate limit Cloudflare) — รอ Pipeline 06:00 refresh ครอบคลุม

### Cron 06:00 + Chrome auto-launch ✅
- พบ Task Scheduler `BidMaster-DailyPipeline` ตั้งไว้แล้ว (NextRun 5/17 06:00)
- Update `run_pipeline.bat`:
  - Kill old Chrome Debug + clear lock files
  - Launch Chrome with --remote-debugging-port=9222
  - Wait for port 9222 ready (60s timeout)
  - Run `python Sebastian_Pipeline.py --step all` (8 steps with internal Discord notify)
  - Kill Chrome at end
  - Discord notify on success/failure
- ใช้ Pipeline.py orchestrator แทนเรียก step ทีละอัน

### ไฟล์ที่เพิ่ม/แก้
- `CLAUDE.md` (ใหม่) — Discord notify protocol + progress logging rules + resume protocol
- `scripts/audit_all_sheets.py` (ใหม่) — audit helper
- `scripts/fetch_bid_history.py` (ใหม่) — Phase B migration
- `scripts/Sebastian_Classifier.py` — เพิ่ม BID_HISTORY_HEADERS + extend AWARDED_JOBS_HEADERS + deadline guard
- `run_pipeline.bat` — เปลี่ยนเป็น Pipeline.py --step all

### Followup
- Retry bid_history เหลือ 103 jobs (background รันอยู่ + Pipeline 06:00 จะ catch ใน refresh)
- Phase C (future): Competitive intel dashboard — pivot tables + LINE summary "งานนี้คู่แข่งเฉลี่ย N ราย"

---

## งานที่ N+10: Pipeline 17/05 รีวิว + 4 fixes (2026-05-17, commit ca0474a)

### สถานะ: ✅ เสร็จ

### Root cause (จาก pipeline_collect_20260517.txt log)
1. **Cloudflare บล็อกครึ่งหลัง:** scrape ต่อเนื่อง 87 นาที → modal "ไม่ผ่านการตรวจสอบ" หลัง 50 นาที → 14 search terms สุดท้าย 0 รายการทุกตัว
2. **SCRAPE 87 นาที (ยาวเกิน):** `นครพนม` 10,000 + `บึงกาฬ` 4,810 = ใช้ 30 นาที, ใหม่ 0 (วันนั้น)
3. **PATCH_DEADLINES fail 3/3:** งาน id 68xxx (ปี 2568) ค้างใน all_jobs — stepId M*/S*/Z* + deadline ว่าง + หา PDF ประกาศไม่เจอ → patch fail ซ้ำๆ ทุกเช้า
4. **False alarm "Chrome ไม่ผูก port 9222":** ใน `run_pipeline_collect.bat` ใช้ `%ERRORLEVEL%` ภายในบล็อก if/else → ค่า expand ตอน parse ไม่ใช่ runtime → log ทั้ง "พร้อม" + "ERROR" พร้อมกัน

### Fix
1. **Scraper:** ตัด `["นครพนม", "บึงกาฬ"]` ออกจาก ALL_TERMS (revert ภายหลัง — ดู N+11)
2. **Scraper:** เพิ่ม `detect_cloudflare_block()` + `init_process5_page(cloudflare_retries=2)` → long cooldown 300s + reinit
3. **Scraper:** track `consecutive_timeouts` → ถ้าติด 2 ครั้ง → long cooldown 300s + reinit
4. **patch_deadlines.py:** เพิ่ม `STALE_YEAR_PREFIXES = ("67", "68")` → skip jid ปีก่อนหน้า (stop bleed งานเก่าค้าง)
5. **run_pipeline_collect.bat:** `setlocal enabledelayedexpansion` + `%ERRORLEVEL%` → `!ERRORLEVEL!`

### Followup
- รัน audit_pending.py ตอน Chrome เปิด → ตรวจ 18 pending_award + 3 งาน 68xxx ใน all_jobs
- ตรวจผล SCRAPE พรุ่งนี้

---

## งานที่ N+11: Cloudflare Stealth — Deep Research + Apply (2026-05-17, commit d77e159)

### สถานะ: ✅ เสร็จ (ลุ้นผลพรุ่งนี้)

### Trigger
คุณกัญจน์สงสัย: "ตัด keyword จังหวัดจะไม่เป็นอะไรใช่ไหม?" → เช็คแล้วพบ:
- 16/05 'บึงกาฬ' **ใหม่ 48 งาน** (งานหน่วยงานชาติ/ภาค — กรมทางหลวงชนบทกรุงเทพฯ, ประปาภูมิภาค ฯลฯ ที่ทำในจังหวัด)
- ถ้าตัด keyword จังหวัด → **พลาดงานหน่วยงานชาติทันที** เพราะ scrape ตำบล/หน่วยงานท้องถิ่นเจอไม่ได้

### Deep research findings (Top 5 Cloudflare bot signals 2025-2026)
1. **Runtime.enable / CDP isolation leak** ← แก้ด้วย JS ไม่ได้ (ต้อง Patchright)
2. **JA4 TLS fingerprint** ← เราใช้ Chrome จริง = OK
3. **navigator.webdriver + --enable-automation flag**
4. **Behavioral / bot score escalation** (session ยาว → คะแนนสะสม)
5. **window.chrome ไม่ครบ + WebGL/plugins mismatch**

### Fix (4 layers)
**Layer 1 — Stealth init script (`new_stealth_page()`):**
- navigator.webdriver = undefined + delete จาก prototype
- window.chrome ครบ (runtime/loadTimes/csi/app/webstore)
- permissions.query Notification fix
- plugins/languages `['th-TH','th','en-US','en']`
- WebGL vendor Intel Iris (Windows realistic)

**Layer 2 — Chrome launch flags (`run_pipeline*.bat`):**
- `--disable-blink-features=AutomationControlled`
- `--disable-features=...,AutomationControlled`
- window-size `800x600 → 1280x800` (bot-tell)

**Layer 3 — Pacing:**
- Fixed 5-15s → **random jitter 2.5-6.5s**
- Idle gap 45-90s ทุก 15 keywords (bot score sediment)
- Session warmup: mouse move + scroll หลัง init

**Layer 4 — Revert keyword cut + page limit:**
- คืน `"นครพนม"` + `"บึงกาฬ"` 
- max_pages **9999 → 20** สำหรับ keyword จังหวัด (200 รายการล่าสุด เพียงพอ เพราะใหม่สุด/วัน = 48)

### ผลคาด
- SCRAPE **87 → ~25 นาที**
- Cloudflare hits **81 → <20**
- ครอบคลุมเท่าเดิม (ไม่พลาดงานหน่วยงานชาติ)

### ที่ยังไม่ทำ (Phase ถัดไป — Option upgrade)
**Patchright** drop-in replacement ของ playwright — แก้ root cause `Runtime.enable` leak:
- `pip install patchright && patchright install chrome`
- เปลี่ยน import ใน 15+ scripts
- ความเสี่ยง: ต้อง smoke test ทุก script
- **เก็บไว้รอผลพรุ่งนี้ — ถ้า 4 layer ปัจจุบันยังไม่พอ ค่อยทำ**

### Followup
- ดูผล SCRAPE 18/05 06:00 — เทียบ time, Cloudflare hits, งานใหม่
- ถ้ายังติด → Patchright Phase ถัดไป

---

## งานที่ N+12: CGD Open Data API Discovery (2026-05-17)

### สถานะ: ✅ Discovery เสร็จ + probe ใช้งานได้ (commit pending)

### Trigger
1. รัน pipeline เทสต์ Cloudflare stealth (commit d77e159) ก่อน 02:00 ตามตาราง
2. ผล: 4 keywords แรก (นครพนม, บึงกาฬ, ตำบลบ้านแพง, ตำบลไผ่ล้อม) ติด timeout ทุกตัว → **stealth 4 layers ไม่พอ** (confirmed ต้อง Patchright หรือลดบทบาท scraper)
3. ลุยวิจัย G-LEAD: พบว่า **data.go.th มี Open API ฟรี** สำหรับข้อมูลจัดซื้อจัดจ้าง — G-LEAD ก็ใช้ source เดียวกัน

### Process
1. คุณกัญจน์ลงทะเบียนที่ https://opend.data.go.th/register_api/signup.php → ได้ User Token ทันที
2. Probe API หา auth pattern — ลอง parameter name หลายแบบ (query + header) → ทุกตัว 401 "No API key found"
3. คุณกัญจน์อัปโหลด user manual: `downloads/2025-07-08-051605.3384232025-03-07-DATAGOTH3USERMANUAL.pdf`
4. อ่าน manual หน้า 36-37 → พบ endpoint + auth pattern ที่ถูกต้อง

### API ที่ใช่ (จาก DATAGOTH3 manual หน้า 36-37)
```
URL:    https://opend.data.go.th/get-ckan/datastore_search
Header: api-key: <user_token>    # มี dash
Method: GET
Params: resource_id=<UUID> + q=<keyword> + limit=N + offset=N + filters=<JSON>
```

### Datasets ที่ใช้ได้ (datastore_active=True)
| Dataset | Files | Records/file | Last update | ใช้ |
|---|---|---|---|---|
| **egp-contact-2568** | 10 | ~500K | 2026-05-11 | awarded_jobs backfill + winner |
| **egpwinner** | 5 | 500K | 2026-05-05 | company lookup (TIN ↔ ชื่อ) |
| **thai-government-procurement** | 2 | (ZIP เก่า, API POST) | 2020 | skip |

### ผลทดสอบ
- ✅ filter `จังหวัด=นครพนม` exact: **5,757 records** ใน file-1 เพียงตัวเดียว
- ✅ keyword `q=นครพนม` ทุก file รวม: **37,936 งาน** (ปี 2568 ทั่วประเทศ)
- ✅ pagination `limit=1000` ทำงาน → **1 ล้าน records/วัน ได้** (quota = 1,000 calls/วัน)
- ⚠️ Schema มี **column drift** (CSV upload field order ไม่ตรง) — ต้อง map ใหม่ก่อนใช้:
  - `แขวง/ตำบล` มีค่า `POINT(lon lat)` (พิกัด)
  - `ละติจูดโครงการ` มีค่าชื่อบริษัท
  - ฯลฯ
- ⚠️ ค้น "ยศประทาน" ใน egpwinner file-1 ไม่เจอ — อาจอยู่ใน file 2-5 หรือ TIN ไม่ตรง search

### Schema (32 columns ของ egp-contact-2568)
ลำดับ, รหัสโครงการ, ชื่อโครงการ, ชื่อประเภทโครงการ, ชื่อหน่วยงาน, ชื่อหน่วยงานย่อย, วิธีจัดซื้อฯ, กลุ่มวิธีจัดซื้อฯ, วันที่ประกาศ, งบประมาณ(บาท), ราคากลาง(บาท), ราคาตกลงซื้อ/จ้าง, ปีงบประมาณ, วันที่เกิดรายการ, จังหวัด, จังหวัด(Eng), เขต/อำเภอ, เขต/อำเภอ(Eng), แขวง/ตำบล, แขวง/ตำบล(Eng), สถานะโครงการ, พิกัดของโครงการ, ละติจูดโครงการ, ลองจิจูดโครงการ, เลขนิติบุคคล, ชื่อผู้ชนะ, เลขที่สัญญา, วันที่ลงนามสัญญา, วันที่สิ้นสุดสัญญา, งบสัญญา(บาท), สถานะสัญญา

### ไฟล์ที่เพิ่ม
- `scripts/probe_cgd_api.py` — script ทดสอบ API (มี EGP_CONTRACT_2568_RIDS + EGPWINNER_RIDS hard-coded)
- `data/cgd_step1_basic.json` — sample 2 records
- `data/cgd_egp_contract_2568_sample.json` — search "นครพนม" sample
- `data/cgd_egpwinner_bf6017ec.json` — egpwinner sample

### Followup (Phase ถัดไป — Hybrid Integration)
- Map column names เก็บ schema ที่ถูก (CSV upload schema drift)
- เขียน `scripts/cgd_api_client.py` — fetch/normalize → Sheet awarded_jobs
- ออกแบบ pipeline ใหม่: API หลัก (awarded_jobs) + Scraper เสริม (pre_tor/tor/active เฉพาะที่ API ไม่มี)
- Audit หจก.ยศประทาน TIN — ค้นใน egpwinner file 2-5 หา record บริษัท

### Insight สำคัญ
- **G-LEAD ก็ใช้ API นี้** — ไม่มี data moat → เราแข่งบน real-time scraper + UX ได้
- **Real-time bidding ยังต้อง scrape** (API ครอบคลุมแค่ awarded contract)
- **Cloudflare stealth Phase 1 ไม่พอ** → ต้องลดบทบาท scraper (ผ่าน API hybrid) + Patchright Phase ต่อไปถ้ายังจำเป็น

---

## งานที่ N+13: Deep API Research + EGP RSS POC (2026-05-17)

### สถานะ: ✅ POC verified — Phase 1 ready

### Trigger
หลัง stealth 4 layers ไม่พอ → ค้นทางอื่น
1. คุณกัญจน์ขอวิจัย API ทุกแบบที่มีประโยชน์สำหรับ Bid Master
2. Spawn deep research agent → ค้น 15+ queries + WebFetch หลายแหล่ง

### Discovery (14 APIs ทั้งหมด — รายละเอียดใน [[project_api_roadmap]])

**Tier ⭐⭐⭐⭐⭐ (Phase 0-1):**
1. eGP Internal API (ใช้ปัจจุบัน — Cloudflare ติด)
2. **EGP RSS Feeds** ⭐ — process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml ไม่ติด Cloudflare!
3. CGD CKAN API (ใช้แล้ว N+12)

**Tier ⭐⭐⭐⭐ (Phase 2-3):**
4. DBD Juristic API (api.egov.go.th) — competitor profiling
5. TPSO CMI — ดัชนีราคาวัสดุก่อสร้าง
6. BOT API — ดอกเบี้ย/exchange rate

**Tier ⭐⭐⭐ (Phase 3+):**
7. Royal Gazette scraper (community fork) — predict future projects
8. MOT Roads, 9. PWA eProcurement, 10. NSO GPP, 11. SME-GP

### RSS POC Results (probe_egp_rss.py)
**✅ ที่ใช้งานได้:**
- HTTP 200 ทุก request — ไม่ติด Cloudflare
- TIS-620 encoding decode สำเร็จ (92 Thai chars)
- projectId extract: regex `\d{11,12}` ใช้งานได้
- deptId filter ทำงาน (0703=20, 0708=13 items)
- ต้องมี User-Agent header (ไม่งั้น ConnectionReset 10054)

**⚠️ Limitations:**
- RSS = **D0 (active_bidding) ONLY** — ไม่รวม pre_tor/tor/awarded/cancelled
- `annType`/`type`/`announceType` params server ignore — D0 only
- ลอง URL variations อื่น (egpplanrss, egpwinnerrss) → ทั้งหมด 404
- ~3-20 items per dept call
- DeptId catalog ยังไม่ครบสำหรับหน่วยงานเป้าหมาย (scan 700-799/1500-1599/4800-4899 ไม่เจอ match)

### Cross-match กับ CGD API
- RSS projectIds = 69xxx (ปี 2569)
- CGD dataset = ปี 2568 → ไม่ match (cross-source consistency ต้องรอ contract 2569 ขึ้น)
- เป็น expected behavior (RSS = real-time / pending, CGD = post-contract)

### ไฟล์ที่เพิ่ม
- `scripts/probe_egp_rss.py` — POC script (7 test cases)
- `data/rss_probe_results.json` — sample data
- `data/rss_poc_results.md` — full report
- `data/egp_deptid_scan.json` — initial scan (empty result)

### Memory ที่สร้าง/อัปเดต
- `reference_egp_rss.md` — RSS API quick reference
- `project_api_roadmap.md` — รวม catalog 14 API + adoption timeline 4 Phases
- `MEMORY.md` index updated

### Coverage Matrix หลัง Phase 1 implement
| Stage | Source |
|---|---|
| pre_tor / tor_review | process5 scrape (เหลือเท่าเดิม) |
| **active_bidding** | **RSS feeds** ⭐ (เปลี่ยนจาก scrape) |
| pending_award | classifier logic |
| **awarded_jobs** | **CGD API** ⭐ (Phase 0 → Phase 1) |
| cancelled_jobs | classifier logic |

### Implication
- **ลด process5 scraper traffic ~70%** (เหลือเฉพาะ pre_tor/tor)
- **Multi-tenant SaaS feasibility ขึ้น** — RSS+API ส่วนใหญ่ shared cost
- **G-LEAD ไม่มี data moat** — ใช้ source เดียวกัน

### Followup
- **Phase 1 implementation** (2-3 สัปดาห์): RSS-First Pipeline
  - หา deptId catalog ของหน่วยงานเป้าหมาย (broader scan หรือ reverse-lookup จาก all_jobs)
  - เขียน `Sebastian_RSS_Scraper.py` + `cgd_api_client.py`
  - ลดบทบาท process5 scraper
- **Dashboard (คุณกัญจน์ขอ)**: brainstorm spec ก่อน implement — track scrape/classify performance + history + inflection points

---

## Setup (ครั้งแรก)

```bash
pip install playwright pymupdf openpyxl anthropic gspread google-auth
playwright install chromium
```

สร้างไฟล์ `.env` ที่ root:
```
ANTHROPIC_API_KEY=sk-ant-...
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
OPEND_USER_TOKEN=...    # data.go.th User Token (CKAN Data API)
```

---

## งานที่ N+14: Dashboard Pages + Vercel Deploy (2026-05-17/18)

### สถานะ: ✅ เสร็จ

### สิ่งที่ทำ
1. **Fix duplicate React keys** ใน `PipelineDurationChart` — dedupe commits ตามวัน + label `+N` เมื่อมี multiple commits/วัน
2. **HeaderBar refactor** เป็น `"use client"` + `usePathname` → active state แท้จริง (ก่อนนี้ hardcoded)
3. **สร้าง 5 หน้า dashboard:**
   - `/scrape` — Cloudflare/timeout trend, keyword breakdown (`ScrapeMetricsChart` + `KeywordBreakdown`)
   - `/classifier` — Lifecycle stack + trend, sheet-vs-classifier diff (`ClassifierTrendChart`)
   - `/funnel` — Funnel diagram (Raw→Filtered→New→Classified→Actionable) (`FunnelDiagram`)
   - `/timeline` — Inflection list with before/after metrics (`InflectionList`)
   - `/history` — Pipeline run history grouped by day
4. **Vercel deploy production** — `https://bid-master-dashboard.vercel.app`
5. **`/api/revalidate`** — POST + secret header → ใช้ revalidatePath
6. **Helper scripts:**
   - `scripts/Sebastian_Revalidate_Dashboard.py` — เรียก revalidate API
   - `scripts/Sebastian_Deploy_Dashboard.py` — รัน `vercel deploy --prod`

### Real-time strategy (ปัจจุบัน)
Git ยังไม่มี remote → `vercel deploy` ผ่าน CLI เท่านั้น  
Flow ที่ใช้ได้จริง: pipeline → snapshot.json updated → `python scripts/Sebastian_Deploy_Dashboard.py` → deploy ~1 นาที

### Followup
- [ ] Option A: ย้าย snapshot ไป Vercel Blob → instant update (< 5s) ไม่ต้อง redeploy
- [ ] Option C: setup GitHub remote → auto-deploy บน push
- [ ] เพิ่มในเป็น step สุดท้ายของ `Sebastian_Pipeline.py` หลัง snapshot generate

### Update (2026-05-18)
- Pipeline integration: เพิ่ม step 9 (`snapshot`) + step 10 (`deploy`)
- `--no-deploy` flag สำหรับข้าม deploy ใน dev mode
- ทดสอบ `--step snapshot` ผ่าน (19s, snapshot.json regenerated)

### Update 2 (2026-05-18) — Option A: Vercel Blob
- สร้าง public Blob store `bid-master-snapshots` (auto-link กับ project ทั้ง 3 env)
- API route `/api/snapshot` (POST) — รับ JSON body, ลบ blob เก่า, put ใหม่, revalidate 6 pages
- `snapshot.ts` ตอนนี้ prefer Blob (ถ้ามี `BLOB_READ_WRITE_TOKEN`) — fallback ไป fs ใน dev
- `Sebastian_Upload_Snapshot.py` — POST snapshot ไป /api/snapshot endpoint
- Pipeline step 10 เปลี่ยนเป็น `publish` (upload) แทน full deploy → **2.3 วินาที** เทียบกับ deploy 60s
- มี fallback อัตโนมัติ: ถ้า upload fail จะลอง full deploy

### Real-time flow (ปัจจุบัน)
```
pipeline → snapshot.json updated → POST /api/snapshot → Blob (overwrite)
                                                          ↓
                                                  revalidatePath × 6 pages
                                                          ↓
                                                  dashboard อัปเดต < 5s
```

### Update 3 (2026-05-18) — HTTP Basic Auth
- เพิ่ม `dashboard/web/src/middleware.ts` — Basic Auth บนทุก route ยกเว้น `/api/snapshot`, `/api/revalidate`, static assets
- timingSafeEqual ป้องกัน timing attack
- ENV: `DASHBOARD_USER`, `DASHBOARD_PASS` (ตั้งใน Vercel + .env)
- ทดสอบครบ: no auth → 401, wrong → 401, correct → 200, /api/* → 200 (bypass)
- Python upload ยังทำงาน (ใช้ x-revalidate-secret แทน)

---

## งานที่ N+15: Phase 1 RSS-First Pipeline (2026-05-18)

### สถานะ: ✅ เสร็จ (MVP)

### สิ่งที่ทำ

**1. DeptId Discovery**
- `scripts/scan_egp_deptids.py` — batch scan 0001-9999 (2-pass: fast + retry)
- ติด HTTP 429 (rate limit) ระหว่าง scan รอบสอง → pivot ไป **incremental discovery**
- Seed catalog 15 depts (จาก scan รอบแรกที่สำเร็จ + POC verified)
- ภายหลังโตเป็น 75 depts ผ่าน probe ในการรัน RSS scraper 3 รอบ

**2. `scripts/cgd_api_client.py`**
- ห่อ CKAN `datastore_search` ใช้สำหรับ enrichment
- `lookup_project(project_id)` — concurrent search 10 contract files
- `lookup_winner_by_tin(tin)` — search egpwinner ทุก file
- `normalize_to_all_jobs(record)` — schema mapping (18 cols)
- Note: 2569 contract data ยังไม่อยู่ใน CGD → enrichment ทำได้เฉพาะ 2568 awarded

**3. `scripts/Sebastian_RSS_Scraper.py`**
- Discovery-mode: poll known active depts + probe N=20 random unknowns/run
- ทำงานเร็ว: 75 depts ใน 17s · concurrent threads workers=4
- ผลลัพธ์: data/rss_run_TIMESTAMP.json + อัปเดต catalog
- Mode `--queue` → เขียน new projectIds ลง rss_queue.json (สำหรับ refresh_active_jobs pickup)

**4. `scripts/filter_target_deptids.py`**
- 2 layers: keyword match (title) + reverse projectId lookup (all_jobs sheet)
- ปัจจุบัน 1 match (0137 — adjacent province สกลนคร) · 1713 target jobs ใน sheet แต่ 0 overlap (RSS = recent, sheet = historical)
- จะ effective มากขึ้นเมื่อ RSS รันต่อเนื่องหลายวัน

**5. Pipeline Integration**
- เพิ่ม step `rss` (1.5) ระหว่าง scrape → download
- ใช้: `python scripts/Sebastian_Pipeline.py --step rss`
- Discord notify เมื่อ step done
- Pipeline หลักรัน rss อัตโนมัติทุกรอบ (cron 06:00)

### ผลลัพธ์ทดสอบ
- 86 items (active D0) ดึงได้จาก 55 depts ใน 16.9 วินาที
- **86 items ทั้งหมด "missed by process5 scraper"** (อาจเป็นเพราะ seen_ids snapshot ที่เปรียบเทียบ — ตัวเลขนี้จะค่อยลดเมื่อทั้งสอง source align)
- Catalog เพิ่มจาก 15 → 75 depts ใน 3 รอบ test

### Followup (Phase 1.5+)
- [ ] Wire RSS queue → refresh_active_jobs.py เพื่อ fetch detail สำหรับ new projectIds
- [ ] ตั้ง cron แยกให้ RSS scraper รันทุก 30 นาที (ตามที่ roadmap บอก)
- [ ] เมื่อ catalog โต 200+ depts → re-run filter_target_deptids.py + curate target list
- [ ] Measure จริง: เทียบ traffic process5 ก่อน/หลัง RSS adoption → KPI 70
---

## งานที่ N+15: Phase 1 RSS-First Pipeline (2026-05-18)

### สถานะ: ✅ เสร็จ (MVP)

### สิ่งที่ทำ

**1. DeptId Discovery**
- `scripts/scan_egp_deptids.py` — batch scan 0001-9999 (2-pass: fast + retry)
- ติด HTTP 429 (rate limit) ระหว่าง scan รอบสอง → pivot ไป **incremental discovery**
- Seed catalog 15 depts (จาก scan รอบแรกที่สำเร็จ + POC verified)
- ภายหลังโตเป็น 75 depts ผ่าน probe ในการรัน RSS scraper 3 รอบ

**2. `scripts/cgd_api_client.py`**
- ห่อ CKAN `datastore_search` ใช้สำหรับ enrichment
- `lookup_project(project_id)` — concurrent search 10 contract files
- `lookup_winner_by_tin(tin)` — search egpwinner ทุก file
- `normalize_to_all_jobs(record)` — schema mapping (18 cols)
- Note: 2569 contract data ยังไม่อยู่ใน CGD → enrichment ทำได้เฉพาะ 2568 awarded

**3. `scripts/Sebastian_RSS_Scraper.py`**
- Discovery-mode: poll known active depts + probe N=20 random unknowns/run
- ทำงานเร็ว: 75 depts ใน 17s · concurrent threads workers=4
- ผลลัพธ์: `data/rss_run_TIMESTAMP.json` + อัปเดต catalog
- Mode `--queue` → เขียน new projectIds ลง rss_queue.json

**4. `scripts/filter_target_deptids.py`**
- 2 layers: keyword match (title) + reverse projectId lookup (all_jobs sheet)
- ปัจจุบัน 1 match (0137 — adjacent province สกลนคร)
- จะ effective มากขึ้นเมื่อ RSS รันต่อเนื่องหลายวัน

**5. Pipeline Integration**
- เพิ่ม step `rss` (1.5) ระหว่าง scrape → download
- ใช้: `python scripts/Sebastian_Pipeline.py --step rss`
- Discord notify เมื่อ step done

### ผลลัพธ์ทดสอบ
- 86 items (active D0) จาก 55 depts ใน 16.9 วินาที
- 86 items "missed by process5 scraper" (จะลดเมื่อ sources align)
- Catalog เพิ่มจาก 15 → 75 depts ใน 3 รอบ test

### Followup
- Wire RSS queue → refresh_active_jobs.py
- ตั้ง cron แยก RSS ทุก 30 นาที
- catalog 200+ → re-run filter + curate target list
- Measure: เทียบ process5 traffic ก่อน/หลัง RSS adoption (KPI 70% reduction)
- CGD 2569 ออก → wire enrichment

### 📌 Phase 1 Followup Tasks (อ้างถึง 2026-05-18)

**🅰️ HIGH priority — blocking ของ #3:**
- [ ] **#1 Slow scan ครบ 9999** — workers=1, sleep 2s, background run ~4-5 ชม.
  - แก้: HTTP 429 issue → จะได้ catalog เต็ม (~1000+ depts vs 75 ปัจจุบัน)
  - ปลดบล็อก: target filter จะ effective ขึ้น
  - เลือกเวลา: รันตอนพักนาน หรือ overnight

**🅱️ MEDIUM priority — ทำหลัง #1 + รอ data สะสม:**
- [ ] **#3 Smart filter improvement** — ทำตอน catalog 500+ depts + RSS history สะสม 1 สัปดาห์
  - เพิ่ม keywords: "เทศบาล", "อบต.", "อบจ.", "กรมโยธา", "กรมทางหลวง"
  - Search description + title (full text)
  - Cross-reference all_jobs department text → infer deptId mapping

**🅲️ LOW priority — passive waiting:**
- [ ] **#2 CGD 2569 dataset** — เช็คทุก 3 เดือน
  - ปัจจุบัน: 2568 data only (5M records contracts + 2.5M winners)
  - เมื่อ 2569 ออก: update `EGP_CONTRACT_2569_RIDS` ใน `cgd_api_client.py`
  - แหล่ง check: https://opend.data.go.th/dataset/egp-contact

**Priority logic:**
- #1 blocking #3 (catalog ใหญ่ → filter ฉลาดได้)
- #2 รอนอกการควบคุม → ไม่ทำให้ workflow ติด
- ทำ #1 ใน background → ไม่กิน focus

### Update Phase 1.5 (2026-05-18, 01:30)

**1.5a Wire rss_queue → refresh_active_jobs:**
- `Sebastian_RSS_Scraper.py`: queue ตอนนี้เก็บ full context (projectId, title, deptId, pubDate, link)
- `refresh_active_jobs.py`: เพิ่ม flags `--from-queue`, `--dry-run`, `--limit`
- Logic: jid ใน queue ที่ไม่อยู่ใน all_jobs → fetch detail + insert sparse row (จาก title RSS + getProjectDetail)
- Auto-cleanup queue: remove items ที่ process หรือเข้า all_jobs แล้ว
- ทดสอบ: `--dry-run --limit 5` ผ่าน, queue มี 86 items พร้อม process

**1.5b 30-min cron:**
- `scripts/run_rss_scraper.bat`: wrapper พร้อม log rotation
- `scripts/setup_rss_cron.ps1`: สร้าง Windows Scheduled Task
- Task `BidMaster_RSS_Scraper`: รันทุก 30 นาที, indefinite
- Verified: first auto-trigger เวลา 1:26:56 · Last Result: 0 (success)
- Catalog growing in production: 75 → 95 → 115 → 135 ใน 4 รอบ

**Files added:**
- scripts/run_rss_scraper.bat
- scripts/setup_rss_cron.ps1

**Files modified:**
- scripts/Sebastian_RSS_Scraper.py (queue format)
- scripts/refresh_active_jobs.py (--from-queue support)

---

## งานที่ N+16: Option A + B + Hybrid Catalog (2026-05-18)

### Option A: Wire RSS queue → 02:00 collect (commit 8d22d13)
- เพิ่ม Step 3.5 ใน run_pipeline_collect.bat
- `refresh_active_jobs.py --from-queue --limit 50`
- ใช้ Chrome session ของ 02:00 collect (reuse)
- ทดสอบ live: queue 91 → 86, +5 sparse rows ใน all_jobs

### Option B: Shrink scraper keywords 30 → 4 (commit 1a52fe0)
- Active: นครพนม, บึงกาฬ, บ้านแพง, บึงโขงหลง
- Legacy 28 ตำบล/หน่วยงาน เก็บไว้ใน `DEPT_PROVINCE_MAP_LEGACY`
- Fallback: `--full-keywords`
- Expected: scrape 30-45 → 4-6 นาที, pipeline 100 → 60-70 นาที

### Hybrid Catalog Growth (commit 2d1e1a4)
- Sebastian_RSS_Scraper.py: PROBE_SAMPLE_SIZE 20 → 50
- scan_egp_deptids.py: workers=2, sleep=0.5s, save empty entries
- Slow batch scan รัน background — ครบ 9999 ใน ~74 นาที (ที่ 2.25 req/s)
- Catalog 235 → expected ~850-1500 active depts หลัง scan เสร็จ

### Closed Loop (ทั้งหมดรวมกัน)
```
RSS scraper (every 30 min, probe 50)
  → queue projectId
02:00 collect (4 keywords)
  → Step 3.5: --from-queue --limit 50 (ingest sparse rows)
  → all_jobs ขยายทั่วประเทศ
refresh tracks transitions
  → getProcureResult fires
  → winner_cache + awarded_jobs grow nationwide
```

---

## งานที่ N+17: Mega Session — Phase 2 SaaS + Multi-stage RSS + Postgres (2026-05-18 → 19)

### สถานะ: ✅ เสร็จ (23+ commits)

### สิ่งที่ทำ (เรียงตามเวลา)

**ช่วงค่ำ (Phase 1.5 + Option A/B):**
- Option A: wire RSS queue → 02:00 collect (Step 3.5)
- Option B: shrink scraper keywords 30 → 4
- Hybrid catalog growth: probe 50/run + slow scan
- P0 classifier fix (37 dropped jobs restored)
- Dashboard refresh cron auto

**กลางคืน (RSS + LINE OA):**
- LINE OA Sebastian Phase 2 foundation:
  - Customer Google Sheet schema (12 cols)
  - /customer/[lineUserId] form page (public)
  - /api/line/webhook (welcome + commands)
  - /api/line/customer (REST API)
  - SEBASTIAN_LINE_TOKEN/SECRET (separate from BSC Concrete)
  - LINE OA channel "Sebastian Michaelis" @768itodz live
- ทดสอบ end-to-end: ทักบอท → reply + create customer + status command

**คืน (Research + Migration):**
- 🔥 **Pre-TOR breakthrough**: ค้นพบ param `anounceType` (typo!) ทำให้ RSS ครอบคลุมทุก stage (P0/B0/D0/W0/D1)
- Multi-stage RSS scraper deploy + rotate mode
- **Phase A** (Postgres): Neon Marketplace + schema 7 tables + ETL 11K rows
- **Phase B** (ETL sync): cron every 30 min — Sheet → DB always-fresh mirror

### Commits สำคัญใน session (23 commits)

```
625d7b8 Quick wins: RSS rotate mode + classifier audit
27e4b4d Phase A: Neon Postgres setup + ETL Sheet→DB foundation
d2b1d77 Fix Sebastian_Dashboard_Refresh subprocess encoding
89e4e1d Sebastian LINE OA: separate env vars from BSC Concrete
082682c LINE OA Sebastian Phase 2: web signup + webhook
d479769 Fix P0 + 3 resilience improvements (morning fixes)
933b4e8 Dashboard: enrich catalog with dept names
a575f88 Dashboard: searchable catalog browser on /scrape
f7fbc3b Dashboard: RSS Catalog Tracker on /scrape page
0e7ce84 RSS scraper: support multi-stage polling (P0/B0/D0/W0/D1)
871ed87 Research: RSS supports ALL stages via anounceType param
2d1e1a4 Hybrid catalog growth: probe 50 + slow safe batch scan
1a52fe0 Option B: shrink scraper keywords 30 -> 4
8d22d13 Option A: wire RSS queue ingest into 02:00 collect
0596494 RSS cron: drop .bat wrapper, use pythonw directly
5203f0e RSS cron: hide CMD window (pythonw + Hidden task)
29a6062 Phase 1.5: RSS queue ingestion + 30-min cron
05c1414 Phase 1 RSS-First Pipeline MVP
63e26e2 Dashboard: error boundaries + mobile polish
2f20467 Dashboard: HTTP Basic Auth via middleware
d08dda0 Dashboard: Vercel Blob real-time snapshot
8c5926c Dashboard: 5 pages + Vercel deploy + pipeline integration
```

### Cron tasks ที่รันอยู่
- BidMaster-Collect-0200 (02:00 ทุกวัน)
- BidMaster-Notify-0600 (06:00 ทุกวัน)
- BidMaster_RSS_Scraper (30 นาที, stage rotate)
- BidMaster_Dashboard_Refresh (30 นาที)
- BidMaster_ETL_Sync (30 นาที)

### Followup ค้าง
- Multi-tenant LINE notify (Task #31) — loop customers + filter + push
- bid_history sheet → populate from process5/CGD
- History job analytics (Priority #3)
- Package tiers + pricing UI (Priority #4)
- Claude API for Sebastian Q&A (Priority #5)
- Enrich sparse RSS rows with province from dept_catalog (filter gap)
- Phase C: DB primary, Sheet mirror

### Update (2026-05-19, 01:35) — Discipline + Followups

**คุณกัญจน์ตัดสินใจ:** ทำตามลำดับ priority ไม่กระโดด

**ที่จดไว้เป็น followup สำหรับ Phase ประมวลผลข้อมูล (Priority #3):**
- Bulk pull CGD 2568 (~5M records) → Postgres
- Populate bid_history จาก process5 getProcureResult
- → Foundation สำหรับ Sebastian deep analytics

**Vision document พร้อมแล้ว:**
- `memory/project_product_vision_2026_05_19.md`
- 6 core features + tiers + stickiness + roadmap

**RSS-First architecture ค้นพบ:**
- `docs/rss_full_replacement_research.md` — Chrome-less ทุก step
- เก็บไว้ implement ตอนทำ HTTP migration

---

## งานที่ 19: Classifier Phase 1+2 — Multi-dim tags (2026-05-19)

### สถานะ: ✅ เสร็จ (~30 นาที)

### Root cause / สิ่งที่ทำ
- Classifier เดิมมีมิติเดียว (lifecycle stage 6 buckets) — ไม่มี project type / budget tier / urgency
- เพิ่ม 8 columns ใหม่ใน `all_jobs` (cols S-Z): `project_type`, `construction_subtype`, `budget_tier`, `urgency_tier`, `method_id`, `sme_suitable`, `geographic_precision`, `unspsc_family`
- สร้าง `scripts/classifier_tags.py` — pure-function rule-based classifier
- `scripts/backfill_classifier_tags.py` — backfill 8,832 rows ใน 8.3 วินาที
- Update `Sebastian_Scraper.py` `_build_all_jobs_row` (18 → 26 cols) — row ใหม่ได้ tags ทันทีตอน scrape
- Update `Sebastian_Classifier.py` `ALL_JOBS_HEADERS` (18 → 26 cols)
- Postgres: migration 002 + update `etl_sheet_to_db.py` + sync 8,832 rows

### Fix / ผล
- Distribution 1,000 sample (project_type):
  - ก่อสร้าง 28.5% · บริการ 24.7% · วัสดุ 24.3% · อุปกรณ์ 12.6% · อื่นๆ 9.6% · IT 0.3%
- Postgres full table (8,832 rows):
  - ก่อสร้าง 31.0% · วัสดุ 23.8% · บริการ 22.9% · อื่นๆ 11.8% · อุปกรณ์ 10.2% · IT 0.3%
- Classifier ปกติ: pre_tor 0 / tor_review 5 / active 4 / pending 16 / awarded 307 / cancelled 44

### Files
- `scripts/classifier_tags.py` (NEW) — 8 classification functions + `classify_all()`
- `scripts/backfill_classifier_tags.py` (NEW) — one-time backfill
- `scripts/db_migration_002_classifier_tags.sql` (NEW) — Postgres ALTER TABLE
- `scripts/Sebastian_Scraper.py` (MODIFIED) — `_build_all_jobs_row` produces 26 cols
- `scripts/Sebastian_Classifier.py` (MODIFIED) — `ALL_JOBS_HEADERS` 18 → 26
- `scripts/etl_sheet_to_db.py` (MODIFIED) — INSERT 26 cols + ON CONFLICT UPDATE
- `scripts/db_schema.sql` (MODIFIED) — schema canonical + 4 new indexes

### Followup
- Phase 3: AI Deep Search (Claude API) — รอ HTTP-only migration
- Phase 4: UNSPSC mapping (unspsc_family ยังว่าง)
- Phase 5: Per-customer ranking score

---

## งานที่ 20: HTTP-only Migration — เอา Chrome ออกจาก Pipeline (2026-05-19)

### สถานะ: ✅ เสร็จ (~1.5 ชั่วโมง)

### Root cause / สิ่งที่ทำ
- refresh_active_jobs.py + patch_deadlines.py ใช้ Chrome/Playwright → pipeline crash ถ้า Chrome ไม่เปิด
- Discovery: getProjectDetail / getProcureResult / PDF download ผ่าน HTTP โดยตรงได้ (Mozilla UA + Referer) ไม่ต้อง Cloudflare session
- Search endpoint ติด Cloudflare Turnstile — Sebastian_Scraper.py ยังต้อง Chrome (แต่ graceful fail)

### Fix / ผล
- สร้าง `scripts/process5_http_client.py` — HTTP wrapper สำหรับ 3 endpoints (test ผ่านทันที)
- Rewrite `scripts/refresh_active_jobs.py` — HTTP-only + parallel workers (default 3) + 26-col sparse insert
- Rewrite `scripts/patch_deadlines.py` — HTTP PDF download + pdfplumber parse (88/88 jobs มี templateId)
- `Sebastian_Scraper.py` — graceful fail ถ้า Chrome ไม่อยู่ (exit 0 ไม่ crash pipeline)
- `Sebastian_Pipeline.py` — อัปเดต comment (refresh ไม่ต้อง Chrome แล้ว)

### ผลทดสอบ
- process5_http_client: getProjectDetail + getProcureResult ทั้ง 6 bidders ✅
- refresh_active_jobs --limit 2: 10 cell updates ✅ (ไม่มี Chrome)
- patch_deadlines --limit 3: PDF 3 ชิ้น download + parse deadline ✅ (ไม่มี Chrome)

### Files
- `scripts/process5_http_client.py` (NEW)
- `scripts/refresh_active_jobs.py` (REWRITTEN)
- `scripts/patch_deadlines.py` (REWRITTEN)
- `scripts/Sebastian_Scraper.py` (MODIFIED — graceful fail)
- `scripts/Sebastian_Pipeline.py` (MODIFIED — comments)

### Followup
- Sebastian_Scraper.py search ยังต้อง Chrome (Cloudflare Turnstile) — แต่ RSS cover ทุก stage แล้ว
- Cloud Migration: ตอนนี้ทุก critical path ไม่ต้อง Chrome → deploy cloud ได้แล้ว

---

## งานที่ 21: Cloud Migration — GitHub Actions (2026-05-19)

### สถานะ: ✅ เสร็จ (~1 ชั่วโมง)

### Root cause / สิ่งที่ทำ
- Pipeline รันบน Windows Task Scheduler → ต้องเปิดคอมตลอด
- เปลี่ยนมา GitHub Actions — ฟรี, รัน cloud, ไม่ต้องเปิดคอม

### Fix / ผล
- `requirements.txt` — Python deps สำหรับ cloud
- `sheets_client.py` — รองรับ `GOOGLE_SERVICE_ACCOUNT_JSON` (JSON string env var)
- `.github/workflows/pipeline_daily.yml` — cron 06:00 Thailand (23:00 UTC)
  - Steps: refresh → patch → classify → LINE notify → snapshot → commit state
- `.github/workflows/rss_scraper.yml` — hourly :22/:52
- Push to GitHub: `github.com/kanapr51-stack/bid-master-system` (private)
- ตั้ง 34 GitHub Secrets อัตโนมัติจาก .env + .env.db + credentials/
- Test run สำเร็จ: ✅ 3m18s ทุก step ผ่าน

### Followup
- RSS workflow รอ eGP RSS กลับมา
- Multi-tenant LINE notify (ยังส่งแค่ 1 user)
- Package signup flow + payment

## งานที่ 22: Dashboard RSS Catalog Tracker อัพเดต (2026-05-20)

### สถานะ: ✅ เสร็จ

### Root cause / สิ่งที่ทำ
- `rss_catalog_stats()` ใน dashboard_extractor.py อ่าน total_depts จาก `egp_deptid_catalog.json` (475 entries)
- แต่ scraper จริงรันด้วย 2,111 depts (catalog file ถูก reset โดย git pull หลัง gentle_scan)
- Source of truth ที่ถูกต้อง = `rss_run_*.json` ล่าสุด → `catalog_size` field

### Fix / ผล
- อัพเดต `rss_catalog_stats()` ให้ใช้ `max(catalog_file_count, last_run.catalog_size)` เป็น total_depts
- เพิ่ม fields: `last_run_at`, `last_run_items`, `last_run_new`, `last_run_missed_process5`, `scraper_seen_size`
- Dashboard แสดง: total=2111, active=20, coverage=21.11% (เดิม: 475, 4.75%)
- Commit: c3fd529

### Followup
- commit egp_deptid_catalog.json เมื่อ catalog ขยายใหญ่ขึ้น (ตอนนี้ 475 entries ใน git)
- RssCatalogCard component อาจต้องใช้ last_run_at แสดง "Last Run" timestamp

---

## งาน 2026-05-22 → 2026-05-23: Nationwide scan 4-stage complete + parser fix

### สถานะ: ✅ เสร็จ

### Root cause ที่แก้
1. **RSS parser bug** — link format เปลี่ยน projectId ย้ายจาก URL → `<description>` 
   - คืนก่อน scan ได้ 0/2,603 depts ทำให้คิดว่า RSS feed ล่ม
   - จริงๆ parser อ่าน `projectId=` ใน link แล้วทิ้งทุก item
   - Fix: regex จาก description แทน
2. **HTTP 429 rate limit** — parallel scan 4 ตัว = 320 req/120s เกิน eGP limit 100/120s
   - Fix: SEQUENTIAL only (1 ตัวพร้อมกัน) + 429 retry 120s cooldown
3. **GHA timeout** — workflow budget 23 min แต่ job timeout 15 → cancelled ทุกครั้ง
   - Fix: timeout 15 → 30 min

### Fix / ผล

**Commits:**
- `079e8f8` fix(scan): parse projectId จาก description + 429 retry + per-atype queue
- `472c8b1` fix(gha): RSS scraper timeout 15→30

**Scan results (4 stages × 2,603 depts):**
| Stage | Items | Active depts | 429 events |
|---|---|---|---|
| D0 (active) | 180 | 56 | 10 |
| B0 (TOR draft) | 105 | 47 | 11 |
| W0 (awarded) | 2,125 | 186 | 12 |
| P0 (planning) | 488 | 88 | 13 |
| **รวม** | **2,898** | **377** | 46 |

**Sheets final (Δ จากเริ่มต้นวัน):**
- ✨ **pre_tor: 0 → 488** (ครั้งแรก!)
- tor_review: 86 → 178 (+92)
- **active_bidding: 51 → 278** (+227, **5.4x**)
- pending_award: 8,441 → 10,567 (+2,126)
- awarded_jobs: 363 → 363 ⚠️
- cancelled_jobs: 243 → 267 (+24)
- **Total +2,957 jobs**

### Followup
- **Winner cache fetch** — awarded_jobs ไม่อัปเดตเพราะ refresh ไม่เรียก getProcureResult; แผนแก้ใน `memory/project_winner_cache_todo.md`
- **Pending_award cleanup** — 10,567 เยอะเกิน ส่วนใหญ่น่าจะ stale (ติด step C03/I03 ไม่มี winner)
- **GHA workflow split (Plan B)** — ดู `memory/project_gha_workflow_split_todo.md` ประเมิน 7 วันหลัง 472c8b1
- **5-digit deptIds expansion** — ยังไม่ scan 5K+ อบต./เทศบาล รอ probe 5-10 ตัวก่อนตัดสินใจ
- **LINE Notify re-enable** — ปิดไว้ รอ per-customer province filter

## งานที่ 23: Province Extraction System (2026-05-23)

### สถานะ: ✅ เสร็จ

### สิ่งที่ทำ
ระบบแยกจังหวัดของงาน (text matching cascade 8 ชั้น) แทน substring-only เดิม
- ชั้น: prefix(จ./อ./ต.) → org-cache(CGD) → bare province/อำเภอ/ตำบล (unique only)
- ข้อมูล: thai_geo_raw.csv (อำเภอ unique 99.8%, ตำบล 87.1%) + exclusion list + national-org guard
- org cache 800 หน่วยงาน จาก CGD (นครพนม+บึงกาฬ) — ground-truth, exact-match บน deptSubName

### ผล (validate กับ CGD จริง, ground-truth จากพิกัด GPS)
- precision: นครพนม 99.4% / บึงกาฬ 97.7% / nationwide 81.6% (จำกัดที่งานทางหลวงข้ามจังหวัด)
- production deptSubName ตรงกับ CGD 100% (40/40) → org cache hit ชัวร์
- backfill all_jobs: coverage 41% → 96.2% (11,683/12,146), เหลือว่าง 463 (ปล่อยว่างถูกต้อง)
- แก้ bug admin-province เก่า: ฝายที่นครพนม เคยติดป้ายมุกดาหาร(จว.สำนักงาน) → แก้เป็นนครพนม(ที่ตั้งงาน)

### ไฟล์
สร้าง: scripts/{province_extractor,build_geo_lookup,build_org_cache,test_province_extractor,backfill_province}.py
       data/{amphoe_lookup,tambon_lookup,geo_exclusion_list,cgd_org_province_cache}.json
แก้: scripts/refresh_active_jobs.py (import extract_province แทน inline)
backup: backups/all_jobs_province_*.json

### Followup
- ขยาย org cache เป็น 77 จังหวัด (รัน build_org_cache.py --provinces ...) เมื่อ scale
- nationwide precision ต่ำเพราะงานทางหลวง/ประปาข้ามจังหวัด — Phase 3 ค่อยพิจารณา coordinate

## งานที่ N+26: Schema Migration + Funnel Metrics Upgrade (2026-05-25)

### สถานะ: ✅ เสร็จ (commit ee5e05d)

### สิ่งที่ทำ
1. **Schema migration** — เพิ่ม 5 คอลัมน์ใน all_jobs Google Sheet (AA-AE):
   - discovered_at, ingestion_source, ingestion_version, refresh_count, api_validity_state
   - ต้องขยาย grid ก่อน (resize cols=32) เพราะ sheet ติด max=26
   - ค่าทั้งหมดว่าง (ถูกต้อง — ไม่กรอกย้อนหลัง ตาม ChatGPT review)

2. **pipeline_funnel.py upgrade**:
   - เพิ่ม FUNNEL_TRACKING_STARTED_AT = 2026-05-25 แยก legacy corpus vs operational
   - Discovery freshness section: jobs <24h, median lag, enrich success rate
   - Daily new active_bidding KPI (jobs discovered today)
   - has_discovered_at counter ใน Stage 3 track new-era ingestion

### Sanity Check
- all_jobs: 43,230 rows, 31 columns ✅
- New columns blank = ถูกต้อง (จะเต็มหลัง pipeline run ถัดไป)
- pipeline_funnel.py output ถูกต้อง — active_bidding 46 (⚠️ LOW รอ RSS กลับ)

### Root Cause (column migration error ก่อนหน้า)
- chr(ord('A') + 26) = '[' (invalid) — ต้องใช้ rowcol_to_a1() + resize() ก่อน

### Followup
- รอ GHA runner รัน pipeline ครั้งแรก → ข้อมูล discovered_at จะเริ่มเต็ม
- Monitor active_bidding 24-48h (ตอนนี้ 46, target >100)

## งานที่ N+27: Universe A/B Split + enrichment_version + transitions history (2026-05-25)

### สถานะ: ✅ เสร็จ (commit 5713c84)

### สิ่งที่ทำ
1. **enrichment_version column (AH)** — derived จาก ingestion_version
   - legacy_none = historical corpus ไม่เคยผ่าน process5
   - 2_process5 = operational telemetry era (หลัง 2026-05-25)
   - ALL_JOBS_HEADERS ตอนนี้ 34 cols

2. **_set_base_provenance() helper** — stamp route_reason + classifier_version + enrichment_version พร้อมกัน
   - ทุก path เรียก 1 function แทนที่จะ set 3 ค่าแยก

3. **transitions_history.ndjson** — append-only event log
   - เพิ่ม record ทุกครั้งที่มี job เปลี่ยน sheet
   - format: {run_at, classifier_version, job_id, from, to, type, route_reason, confidence, ...}

4. **pipeline_funnel.py Universe Split section**
   - Universe A count + enriched rate (ควร ~0.2%)
   - Universe B count + target >70% enrich success
   - สถานะตอนนี้: A=43,230 (100%), B=0 รอ pipeline run

### Architecture Insight (ChatGPT)
- classifier_version ≠ enrichment_version (semantically different concepts)
- classifier_version = logic version (always v3_process5, correct)
- enrichment_version = data quality indicator (legacy_none vs v2_process5)

### Followup
- Universe B จะโตหลัง 06:00 พรุ่งนี้ (2026-05-26)
- Target: B enrich success >70%
- transitions_history.ndjson จะเริ่มมีข้อมูลเมื่อ job เปลี่ยน sheet

## งานที่ N+28: Night Sprint — P1 fix + P2 funnel GHA + health archive (2026-05-25)

### สถานะ: ✅ เสร็จ (commits 2745291 + 92d4b8f)

### สิ่งที่ทำ
1. **fix(critical): rowcol_to_a1** — chr(ord(A)+idx) invalid สำหรับ col > Z
   - refresh_count (idx 29 → ^) + api_validity_state (idx 30 → _) ไม่เคยถูก write
   - fix: gspread.utils.rowcol_to_a1(row, col+1)
   - impact: Universe B จะโตได้จริงตั้งแต่ 06:00 พรุ่งนี้

2. **P2: pipeline_funnel.py --export → GHA Step 5.5**
   - data/daily_health_snapshot.json (latest)
   - data/health_snapshots/YYYY-MM-DD.json (archive = time-series operational memory)

3. **RSS State Machine spec** บันทึกใน memory
   - DOWN / RECOVERING / STABLE + controlled catch-up by time window

### ChatGPT confirmed: BMS ผ่าน "minimum viable operational platform threshold" แล้ว
7 capabilities ครบ: ingestion, enrichment, observability, provenance, event history, trend memory, operational semantics

### พรุ่งนี้ 06:00 — monitoring plan
- ดู delta across runs: 06:00, 06:30, 07:00 (ไม่ดูแค่ snapshot เดียว)
- Priority: universe_b_count > 0 → refresh_count_gt0 > 0 → discovered_today > 0 → active_bidding > 46
- Scenario A (healthy) → Portal Recon Sprint
- Scenario B (partial) → Discovery Reliability Sprint
- Scenario C (dead) → inspect write path

### Followup
- Portal Recon Sprint หลัง Universe B confirm

---

## งานที่ N+29: 🎯 Province Search API ค้นพบ + ยืนยัน + Discovery script (2026-05-30)

### สถานะ: ✅ endpoint+auth+discovery พิสูจน์ end-to-end แล้ว — เหลือ token automation + ingest confirm

### ผล end-to-end (scripts/Sebastian_Province_Discovery.py, dry-run)
- ดึง 959 งาน D0 (นครพนม 849 + บึงกาฬ 110) → filter เหลือ **21 งานในอำเภอเป้าหมาย**
- เช่น รพ.บ้านแพง ฿1.8M, อบต.นางัว ฿5.67M, เทศบาลบึงโขงหลง ฿1.4M, วท.บ้านแพง ฿4.52M, รพ.บึงโขงหลง
- token pluggable (--token / env BMS_ANNOUNCEMENT_TOKEN), --dry-run/--ingest/--filter-amphoe
- ingest → projects_seen (source='province_api', province รู้แน่นอน) → notifier เดิม pick up

### ⚠️ Sanity flags (ต้องสืบก่อน production)
- **บึงกาฬ pagination:** ✅ resolved — เป็น rate limit (throttle หลัง ~100 req) ไม่ใช่ data bug. fix: cooldown 30s ทุก 50 req. verify บึงกาฬเดี่ยว = 420/306 active ครบ
- ส่วนใหญ่ของ 21 งานเป็น announce เก่า (6810-6904) → ถ้า ingest ต้องจัดการ backfill ไม่ให้ blast LINE

## งานที่ N+30: Token Service (Discovery Plane Control Plane) (2026-05-30)

### สถานะ: ✅ foundation เสร็จ+test — เหลือ Chrome9222 live test + Playwright canary

### Decision (ChatGPT + Claude converged)
หลัก: **"obtain ≥1 usable token before discovery deadline"** ไม่ใช่ per-request success rate
- KPI = Discovery Readiness Probability = P(token acquired within window), วัด acquisition latency P50/P95/P99
- beta: primary=Chrome9222 (residential IP), fallback=Manual, experimental=Playwright VPS (canary)
- canary ต้องเลียนแบบ production cadence (4-6 burst/วัน) ไม่ใช่ทุก 15 นาที (กัน measurement perturbation)
- B's dependency จริง = browser availability ไม่ใช่ user account (endpoint public ไม่ต้อง login)

### Build (scripts/token_service.py — tested)
- `ITokenProvider` abstraction → สลับ provider ไม่แตะ discovery
- `ManualProvider` (env/file), `Chrome9222Provider` (CDP harvest — built, ยังไม่ test live), `PlaywrightProvider` (stub)
- `TokenService`: single-writer atomic cache + state machine VALID/EXPIRING/REFRESHING/FAILED/EXPIRED
- token parse expiry ในตัว (EGP-ANNOUNCEMENT-KEY:TS_ms:HMAC, TTL 30 นาที)
- telemetry ndjson: time_to_token_ms, refresh_count/failures, provider, state_before
- `Sebastian_Province_Discovery.py` wired → `TokenService.get_valid_token()`
- test: parse/state machine/manual/expired/telemetry ✅, graceful no-token ✅

### Followup
- [ ] Chrome9222 live test (คุณกัญจน์เปิด Chrome --remote-debugging-port=9222)
- [ ] Playwright canary บน VPS (4-6 burst/วัน, เก็บ acquisition latency)
- [ ] digest sender (21 เก่า ย่อ + กรอง deadline / ใหม่ เต็ม) — รอ confirm format

### Root cause ที่นำมาสู่การค้นพบ
RSS เห็นแต่หน่วยงานกลาง (76 deptId active = central gov ทั้งหมด, reverse-map 1/76 match target)
→ อบต./เทศบาล/รพ.สต./โรงเรียน **มองไม่เห็นทาง RSS เลย** → target_hit=0 มาตลอด

### สิ่งที่ค้นพบ (Chrome DevTools บน process5)
Province Search endpoint คืนหน่วยงานท้องถิ่นได้จริง:
```
GET /egp-atpj27-service/pb/a-egp-allt-project/announcement
    ?budgetYear=2569&moiId=480000&announceType=2&page=1   (announceType=2 = D0)
GET .../announcement/sumProjectMoneyAndCount?budgetYear=2569&moiId=480000&announceType=2
```
- **นครพนม (480000) D0 ปี2569 = 849 โครงการ / 85 หน้า** (10/หน้า) — RSS เห็น ~0
- **บึงกาฬ (380000) D0** = มีข้อมูล (อบต./เทศบาล/รพ.บึงกาฬ)
- ตัวอย่าง: อบต.หนองซน, เทศบาลตำบลนาหว้า, รพ.สต.เทศบาล
- announceType numeric (2=D0) ไม่ใช่ text "D0"
- recordsTotal ใน /announcement = 0 เสมอ (lazy) → ต้องใช้ sumProjectMoneyAndCount นับ
- announcementTodayFlag=true ใช้ date range (announceSDate/EDate) แต่ขัดกับ moiId → ไม่ใช้

### Token finding (สำคัญ)
- format: `EGP-ANNOUNCEMENT-KEY:TIMESTAMP:HMAC-SHA256(base64)` → ทั้งหมด base64 อีกชั้น
- **STANDALONE**: ใช้ได้โดยไม่ต้องมี cookies/XSRF/session (proved: token-only call works จาก VPS)
- TTL ~30 นาที, token เดียวใช้ได้หลาย moiId (ไม่ผูก query)
- ❌ ไม่ได้สร้างใน agpc01-web JS (search 25 chunks + scripts.js)
- ❌ ไม่มี interceptor ใส่ X-Announcement-Token (มีแค่ X-Xsrf)
- ❌ generateToken endpoint คืนแต่ AES blob ("Salted__") ไม่ใช่ HMAC format
- ❌ ไม่มี endpoint token/getToken/getAnnouncementToken (404)
- HMAC key brute-force (RDCrypto/egp/etc x msg variants) → ไม่ match

### Followup (เรียงตาม priority)
- [ ] **หา token mint** — capture network ตอนโหลดหน้า search (page-load XHR) เพื่อดูว่า server-mint หรือ client-mint
- [ ] ถ้า client-mint → หา chunk/shell ที่ยังไม่ได้ crawl (micro-frontend shell)
- [ ] Fallback: browser token-farming (Playwright VPS หรือ Chrome debug port 9222 บนเครื่องคุณกัญจน์)
- [ ] หลัง token แก้ได้ → build Sebastian_Province_Discovery.py แทน RSS discovery
- [ ] map 843 target orgs → getProcurementDetail deptId+deptSubId → infoDeptSub province confirm

---

## งานที่ N+31: Chrome9222 Token Provider — live test ผ่าน + แก้ 3 bugs (2026-05-30)

### สถานะ: ✅ เสร็จ — end-to-end harvest→search พิสูจน์แล้ว

### สิ่งที่ทำ
เปิด Chrome `--remote-debugging-port=9222 --user-data-dir=C:/chrome_debug_profile`
→ test `Chrome9222Provider` harvest token จริง → ยิง search API พิสูจน์ token ใช้ได้

### Bugs ที่เจอ + แก้ (token_service.py)
1. **`/json/new` ใช้ GET ไม่ได้** — Chrome 111+ บังคับ PUT (`"unsafe HTTP verb GET"`)
   → ลบ `if False else GET` เหลือ `requests.put`
2. **WebSocket handshake 403** — Chrome 111+ บล็อก ws ที่ส่ง Origin นอก allowlist
   → `websocket.create_connection(..., suppress_origin=True)` (ไม่ต้อง relaunch ใส่ `--remote-allow-origins`)
3. **`parse_token_expiry` +TTL ซ้ำ** — TS_ms ใน token = เวลา**หมดอายุ** (issue+30นาที) ไม่ใช่เวลาออก
   → ลบ `+ TOKEN_TTL_SEC` (verified: live token TS อยู่อนาคต 1,774s ≈ TTL พอดี)
   → กันใช้ token หมดอายุใน 30 นาทีสุดท้าย (ผิดกฎ deadline)

### ผลพิสูจน์ (single clean request)
```
sumProjectMoneyAndCount?moiId=480000&announceType=2
→ {"response":{"responseCode":"0"},"data":{"totalPages":85,"recordsTotal":849}}
```
**นครพนม D0 = 849/85หน้า ตรงกับ memory** → Chrome9222 token ใช้ search ได้ 100%
harvest auto (Turnstile auto-pass residential), time_to_token ~9s, ไม่ต้องคลิกค้นหาเอง

### Bug ที่เจอเพิ่ม (Sebastian_Province_Discovery.py)
- discovery แปล rate-limit (plain text "Rate limit exceeded") เป็น "token reject" → วินิจฉัยผิด
  → เพิ่ม `class RateLimited`, _get raise แยก, count_d0 sentinel -2, fetch_all_d0 backoff+retry

### บทเรียน (lesson learned)
- ❌ รัน 2 discovery เต็ม (2 จังหวัด × ~127หน้า) พร้อมกัน → IP throttle หนัก (>200s ไม่ใช่ 120s)
- ❌ loop ยิงซ้ำตอนโดน ban = **ยืด ban** → ต้องหยุดยิงสนิท รอเงียบ แล้วยิงครั้งเดียว
- ✅ test provider = ต้องพิสูจน์ token "ใช้ได้จริงกับ API" ไม่ใช่แค่ "harvest ได้รูปแบบถูก"

### Followup
- [ ] รัน discovery จริง (จังหวัดเดียวก่อน, ระวัง rate limit) → ingest projects_seen
- [ ] wire เข้า cron/systemd (token harvest ทุก ~25 นาที)
- [ ] digest sender (21 เก่า ย่อ+กรอง deadline / ใหม่ เต็ม) — รอ confirm format
- [ ] Playwright canary บน VPS

---

## งานที่ N+32: Discovery Automation (C) + First Real Ingest (A) (2026-05-30)

### สถานะ: ✅ เสร็จ — pipeline ครบวงจร, ingest จริง 730 rows, sanity ผ่าน

### C: Automation 2 ฝั่ง (commit 2916f77)
**Windows (single writer):**
- `harvest_and_push.py` — ensure Chrome debug → harvest token → scp → VPS:/opt/bms/data/token_state.json
- `harvest_task.bat` + `harvest_hidden.vbs` — Task Scheduler launcher (hidden, ทุก 25 นาที)
- Task `BMS_TokenHarvest` /sc minute /mo 25 — tested: harvest+push OK (refresh เมื่อ expiring)

**VPS (read-only worker):**
- `bms-province-discovery.service` + `.timer` — OnCalendar 00,06,12 UTC (07/13/19 น. ไทย)
- discovery `--worker` (allow_refresh=False) → อ่าน token ที่ push มา ไม่ harvest เอง
- bms อ่าน token (644) + เขียน DB ได้, .env มี BMS_DATA_DIR=/opt/bms/data
- VPS IP + bearer token bypass Cloudflare ได้ (datacenter IP ผ่าน)

### A: First Real Ingest — นครพนม
```
849 โครงการ/85 หน้า → 737 active, 112 ยกเลิก → ingest +730 ใหม่, 7 ทับ rss
🎯 อ.บ้านแพง = 17 รายการ (รพ.บ้านแพง, วิทยาลัยเทคนิคบ้านแพง, ประปาบ้านแพง, อบต.นางัว/นาเข)
```
**ไม่โดน throttle** (single sequential + cooldown 30s/50req ทำงาน) — ต่างจาก bug 2 runs พร้อมกัน

### Sanity check (ผ่านหมด)
- province_api 730 rows ทั้งหมด=นครพนม | duplicate project_id=0 | empty pid/prov=0
- sources อยู่ร่วมกัน: province_api 730 + rss 291 | zero budget=0, max 46.9M

### ⚠️ ความปลอดภัย: province_api rows ยังไม่ wire เข้า notify (ตั้งใจ)
- RSS Notifier อ่าน rss_queue.json (ไม่เห็น projects_seen ที่ ingest ตรง)
- Enrichment Worker กวาด project_locations(pending) — province_api มี 0 entries
- → 730 rows isolated, ไม่ auto-blast → พื้นที่ปลอดภัยสร้าง digest+deadline filter ก่อนส่งจริง
- (หยุด notifier/line-sender timer ชั่วคราวตอนเช็ค แล้วเปิดคืน — RSS flow ต่อเนื่อง)

### Followup
- [ ] **wire province_api → notify** (task B): ใส่ project_locations(hard, known province) หรือ
      path ใหม่ → แต่ต้องกรอง deadline≥today ก่อน + digest งานเก่าแบบย่อ + preview ก่อนส่ง LINE family
- [ ] รัน บึงกาฬ ingest (timer 19:00 จะรันทั้ง 2 จังหวัด)
- [ ] map dept_id (province_api ใส่ dept_id='' — ดึงจาก getProcurementDetail ถ้าต้องการ)

---

## งานที่ N+33: Delivery-Wiring Architecture — APPROVED (ChatGPT+Claude converged 2026-05-30)

### สถานะ: ✅ decision locked — pre-implementation checkpoint

### Finding ที่เปลี่ยน architecture
**Bid deadline ไม่มีใน JSON API เลย** (probe จริง รพ.บ้านแพง 69039168991):
- province-search item: announceDate, modifiedDate, announceWinnerDate
- getProjectDetail: ไม่มี date (มีแค่ stepId/flowSeqno/projectStatus)
- getProcurementDetail: reportDate, announceDate, questionFdate, deliverDay
→ authoritative deadline = **PDF ประกาศเท่านั้น** (patch_deadlines.py: download PDF→pdfplumber→regex "ยื่นข้อเสนอ/ยื่นซอง"→Thai date)
→ templateId/PDF resolution ของงาน API-discovered **ยังไม่พิสูจน์** (search item ไม่มี tor_url)

### APPROVED FLOW (เซ็นอนุมัติทั้ง ChatGPT + Claude)
```
Province Discovery → projects_seen
  → project_locations (source=province_api, need_location=0, qualification_status=pending)  [REUSE ไม่สร้าง table]
  → Qualification Worker
  → Epoch Gate (post-epoch only)              [PRIMARY safety]
  → Resolve PDF Deadline                       [SECONDARY barrier]
  → deadline known? ── no → FAIL-CLOSED (ไม่ส่ง + Discord digest reason=deadline_unresolved)
                     └ yes
  → deadline >= today? ── no → suppress
                         └ yes → notification_queue → LINE
```

### Decisions (Q1-Q4)
- Q1: epoch=primary safety, PDF deadline=secondary, **parse fail → fail-closed** (Trust Acquisition Phase)
- Q2: **ห้ามใช้ stepId+announceDate heuristic** — ยอม 0 notification ชั่วคราว ดีกว่าส่งผิด (Correctness > Coverage @ 5 subs)
- Q3: **reuse project_locations** + เพิ่ม field (source, need_location, qualification_status), worker branch — ไม่สร้าง qualification_pending table
- Q4: **dual epoch** ชั่วคราว (RSS=txt เดิม, province=source_epochs table ใหม่), migrate RSS ทีหลัง (reversible)

### Invariant ใหม่ของ BMS
"**Authoritative Deadline Gate ก่อน Notification Queue**" (ลำดับถัดจาก "Idempotency ก่อน Delivery") — ทุก source ต้องผ่าน, ห้าม trust stepId อย่างเดียว

### Build plan (ลำดับ)
1. **[gating]** verify PDF resolution สำหรับ province_api project (ดึง templateId/PDF ได้ไหม) — ถ้าไม่ได้ = beta เงียบจนแก้
2. set province_epoch = now (suppress 730 backlog)
3. project_locations: เพิ่ม column (source, need_location, qualification_status) + insert province_api target rows
4. Qualification Worker: branch need_location + epoch gate + PDF deadline gate (ครอบ Pass1+Pass2) + fail-closed
5. source_epochs table (province) + is_backfill via source epoch
6. Discord digest: qualification_failed reason=deadline_unresolved
7. preview ก่อนส่ง LINE family จริง

### Implementation risks ที่ต้องระวัง
- Pass 2 repair (Enrichment_Worker.py:221-241) enqueue orphan → deadline gate ต้องครอบ ไม่งั้น province_api หลุดผ่าน
- province_api insert project_locations: location รู้แล้ว (province จาก moiId) → อย่าให้ enrichment_status='success' trigger Pass2 ก่อนผ่าน deadline gate

---

## งานที่ N+34: Deadline Resolution — Phase 0 Characterization (ChatGPT+Claude 100% converged 2026-05-30)

### สถานะ: ✅ decision locked — เริ่ม Experiment 1 (CDP renderability)

### การปรับสำคัญ: BrowserDeadlineProvider = candidate ไม่ใช่ proven
พิสูจน์แล้วจริง: (1) human browser → process3 → เห็น deadline, (2) RSS templateId → PDF → parse ได้
**ยังไม่พิสูจน์:** (1) CDP automate process3 extraction, (2) invitation announcements มี deadline เสมอ
→ BrowserDeadlineProvider ยังเป็น **hypothesis** จนกว่า experiment ผ่าน

### Build order (informational leverage สูงสุด)
1. `IDeadlineProvider` abstraction + `NullDeadlineProvider` (mirror ITokenProvider)
2. Qualification pipeline + epoch suppression + fail-closed (deploy ได้เลยด้วย NullProvider)
3. **Experiment 1: CDP Renderability Probe** ← highest leverage, ทำก่อน
   - คำถาม: CDP reproduce สิ่งที่ human เห็นได้ไหม (navigate process3 → extract HTML → find deadline)
   - วัด: renderability (ไม่ใช่ deadline). failure modes: session/cross-window/postback/JS-timing/anti-automation
4. **Experiment 2: Deadline Presence** — sample 10-20 invitation projects, วัด deadline_presence_rate
5. ถ้าผ่านทั้งคู่ → BrowserDeadlineProvider
6. GreenBook RE = parallel research track (ไม่ block production)

### Metrics ที่จะเก็บ (DeadlineProvider)
deadline_resolution_success_rate, provider_used, resolution_latency, parse_failures

### หลักการ
"Characterize before optimize" → กรณีนี้ "**Characterize before building the dependency**"

## งานที่ N+35: Resolver Direction LOCKED + Exp1 result (2026-05-30)

### Exp1 (CDP renderability) = NEGATIVE → falsified BrowserDeadlineProvider(navigate)
process3 ShowHTMLFile = session-dependent UI artifact (cold navigate/fetch = empty body)
→ ไม่ใช่ resource URL, replicate ต้อง click-through flow (fragile) → ลดเป็น emergency fallback

### Resolver ranking (ChatGPT+Claude 100% converged)
- **Tier A (do first): greenBook → templateId → PROVEN PDF path** (egp-template-service + pdfplumber เดิม)
  → unknown เดียว = "greenBook expose document linkage ได้ reliably ไหม"
- Tier B: CDP click-through automation = emergency fallback (UI fragility)
- Tier C: new extraction (OCR/new endpoint) = ไม่มี evidence อย่าลงทุน

### Build order LOCKED
NOW: 1.IDeadlineProvider 2.NullDeadlineProvider 3.Qualification pipeline 4.Epoch suppression 5.Fail-closed (deploy ก่อน resolver = operational skeleton)
PARALLEL: 6.greenBook RE (highest priority, information-based timebox ~4-8h)
FALLBACK: 7.CDP click-through
DO NOT: rewrite parser / invent extraction / couple pipeline to browser UI

### หลัก: "ปัญหาคือ finding the PDF ไม่ใช่ extract deadline" → bounded change, reuse proven parser

## งานที่ N+36: Qualification schema migration (steps 1-3) (2026-05-30)

### สถานะ: ✅ เสร็จ (offline, ระหว่าง WAF back off)

### ทำ (VPS DB, backup ก่อน)
1. backup: backups/bms_customers_20260530_103357_pre_epoch_schema.db (995KB)
2. **source_epochs table** + province_api epoch = 2026-05-30T10:34:33Z (UTC, ตรง format first_seen_at)
   → **suppress backlog**: backlog(<epoch)=730, new(>=epoch)=0 ✓
   → dual-epoch (Q4): province=table, RSS=txt เดิม
3. **project_locations generalize** (Q3 reuse): +source(default 'rss') +need_location(default 1) +qualification_status
   → 287 rows เดิม = rss/need_location=1 (ไม่กระทบ enrichment worker เดิม)

### artifact
- scripts/deadline_service.py (commit 1854c06): IDeadlineProvider + NullDeadlineProvider (fail-closed)
- scripts/migrate_qualification_schema.py: idempotent migration (versioned, reproducible)

### ค้าง (step 4 — รอ confirm)
- Qualification Worker: epoch gate + DeadlineService.resolve() + fail-closed (ครอบ Pass1+Pass2)
- insert province_api target rows เข้า project_locations (source=province_api, need_location=0, qualification_status=pending)

### WAF incident
brute-sweep greenBook → eGP WAF block → back off. greenBook capture + discovery รอ WAF เคลียร์

## งานที่ N+37: Qualification Worker Pass 3 (step 4) — DEPLOYED + SAFE (2026-05-30)

### สถานะ: ✅ build order 1-5 ครบ — pipeline ครบวงจร, beta เงียบปลอดภัย (fail-closed)

### ทำ (Sebastian_Enrichment_Worker.py + deadline_service.py deployed)
เพิ่ม `qualify_province_api()` (Pass 3) ใน enrichment worker — single-plane (ไม่สร้าง parallel path):
```
candidate = province_api projects_seen post-epoch + subscribed province + ยังไม่ qualify
  → DeadlineService.resolve() [NullProvider = fail-closed ตอนนี้]
  → enqueue เฉพาะ deadline resolved + ยังเปิดยื่นซอง (>= today)
  → audit row enrichment_status='qualified' (RSS Pass1/Pass2 ไม่แตะ — กัน blast 730)
```
วางก่อน RSS batch + independent (ไม่ skip แม้ RSS queue ว่าง)

### Verify (production)
- direct test: 0 candidates, notification_queue 7→7, project_locations 0→0 = SAFE ✅
- full service run: exit 0, "Province qual: 0 post-epoch candidates", RSS flow ไม่กระทบ ✅
- epoch suppression: 730 backlog → 0 candidates ✓

### Decision: deadline gate ครอบ province_api ก่อน, RSS ทีหลัง
RSS path เดิม enqueue โดยไม่มี deadline gate + ทำงานอยู่ → ตามหลัก "อย่า rewrite stable path"
→ province_api รับ gate ก่อน (path ใหม่), RSS migrate เข้า gate = future task

### ค้าง (B — รอ WAF เคลียร์)
- greenBook RE → templateId → PROVEN PDF path → GreenBookDeadlineProvider (แทน NullProvider)
- เมื่อ provider จริงมา: BMS_DEADLINE_PROVIDER=greenbook → pipeline ส่งจริง (ไม่แตะ worker)

## 📍 CHECKPOINT (2026-05-30 ~17:50 ไทย) — คุณกัญจน์เดินทาง จะมาทำต่อ

### สิ่งที่เสร็จแล้ววันนี้ (commits)
- Chrome9222 token provider + automation (Windows harvest 25นาที → VPS worker 3×/วัน) + ingest 730 rows
- Delivery-wiring architecture LOCKED (ChatGPT+Claude 100% — 4 รอบ)
- **Qualification Pipeline skeleton 1-5 ครบ + deployed + SAFE** (db69f70):
  deadline_service(Null/fail-closed) + schema(epoch suppress 730) + worker Pass 3 (epoch+deadline gate)
  → beta เงียบปลอดภัย (ไม่มีทางส่งงานปิดประมูล) จนกว่า resolver จริงมา

### กำลังทำค้าง: B = greenBook RE (resolver จริง)
- ✅ crack param: `greenBook?mode=LINK&methodId=<proj>&tempProjectId=<pid>&pageAnnounceType=<announceCode>`
- ✅ DTO มี field document-link: partFile/filePath/attachName/token (W0 winner = null หมด)
- ⏳ **ยังไม่ทดสอบ invitation (ประกาศเชิญชวน D0)** — ดู RESUME POINT ใน data/research_deadline_resolution_2026_05_30.md

### Resume ทำอะไรต่อ (ลำดับ)
1. หา invitation announceType code (งาน stepId M*/S* ประกวดราคา) → เรียก greenBook ด้วย pageAnnounceType=code นั้น
2. ดู partFile/filePath/token populate ไหม = templateId/PDF link
3. ถ้าได้ → fetch PDF → pdfplumber (patch_deadlines) → deadline → สร้าง GreenBookDeadlineProvider
4. สลับ provider: env BMS_DEADLINE_PROVIDER=greenbook (ไม่แตะ worker) → pipeline ส่งจริง → preview Discord ก่อนส่ง LINE family
⚠️ ห้าม brute param (trip WAF แล้ว 1 ครั้ง) — capture browser หรือยิงทีละ call

### Infra state
- Windows Task BMS_TokenHarvest (25นาที) ทำงาน | VPS timer province-discovery (07/13/19น.) + enrichment(2นาที, มี Pass 3)
- WAF เคลียร์แล้ว | Chrome debug 9222 เปิดอยู่ (profile C:/chrome_debug_profile)

## งานที่ N+38: 🎯 Deadline Resolver พบ + roadmap LOCKED (2026-05-30)

### BREAKTHROUGH (B-2 success, ดีกว่าคาด)
capture cross-tab → เจอ process5 doc-download API (ไม่ใช่ process3 session):
```
infoProcureDocAnnounZip?projectId=X → data.buildName2 = templateId
POST egp-template-service/dant/view-pdf?templateId=X {} → JSON.data = base64(PDF)
base64 → pdfplumber → regex → deadline
```
พิสูจน์: invitation 69059341206 → "เสนอราคา...วันที่ ๕ มิถุนายน ๒๕๖๙" = deadline 5 มิ.ย.2569 ✅
- ใช้ AES generateToken (server-side, ไม่ต้อง browser/process3/Turnstile) → รัน VPS ได้
- infoProcureDocAnnounZip = projectId→templateId ที่หามาทั้งวัน (greenBook = แค่ metadata)
- กลับสู่ PROVEN PDF path (pdfplumber+patch_deadlines) → blast radius ต่ำ

### Roadmap LOCKED (ChatGPT+Claude 100%)
- Phase 1: DocZipPdfDeadlineProvider (track 4 stage แยก: template/download/parse/deadline)
- Phase 2: Presence characterization 20→50 samples หลายหน่วยงาน
  metrics: template_resolution_rate, pdf_download_rate, pdf_parse_rate, deadline_extraction_rate (+by announce_type/method_id/step_id = type-drift check)
- Phase 3: strict fail-closed production enable (Q4 Beta Override = ยกเลิก, ไม่ต้องแล้ว)
- Phase 4: cache (project_deadlines table) + circuit-breaker (429/403 spike→degrade) + coverage analytics

### Caveats ที่ต้อง design
cache (resolve once read many) | multi-stage failure reason | circuit-breaker (กัน WAF) | document-type drift (buildName2 อาจชี้คนละ doc ต่อชนิด)

## งานที่ N+39: Phase 3 — Production Enable (preview mode) DEPLOYED + verified (2026-05-30)

### สถานะ: ✅ pipeline ครบวงจร + resolver จริง + preview go-live gate

### ทำ (ChatGPT+Claude Phase 3 plan)
- **Provider retry (Layer 1)**: deadline_provider_doczip — micro-retry 3x (timeout/conn/5xx), rate-limit แยก
- **Worker (Layer 2) Sebastian_Enrichment_Worker qualify_province_api rewrite**:
  - seed projects_seen(post-epoch) → project_locations(qualification_status='pending')
    (enrichment_status='failed' = constraint อนุญาต + RSS Pass1/Pass2 ไม่แตะ, zero RSS change)
  - macro-retry: provider_error/download_failed → คง pending จน MAX_QUAL_ATTEMPTS(5)
  - circuit breaker: 5 provider errors ติดกัน → abort batch + Discord alert (กัน WAF/outage)
  - **preview mode** (BMS_PROVINCE_NOTIFY_MODE=preview): RESOLVED+open → Discord preview + status=preview_held (ไม่ enqueue LINE) = controlled go-live gate
- env VPS: BMS_DEADLINE_PROVIDER=doczip, BMS_PROVINCE_NOTIFY_MODE=preview

### Verify (production)
- 0 candidates (backlog suppressed) → exit 0, RSS ไม่กระทบ
- provider VPS: resolve 69059341206 → 2026-06-05 (4.3s)
- **preview gate test**: insert งานเปิด → PREVIEW Discord + preview_held + nq ไม่เปลี่ยน (ไม่ enqueue) ✅
- เจอ+แก้ latent bug: enrichment_status CHECK constraint (pending/success/failed) — ใช้ 'failed'

### ค้าง (go-live)
- งานใหม่ post-epoch จริง (discovery รอบหน้า) → preview Discord → คุณกัญจน์ review 1-3 งาน → flip BMS_PROVINCE_NOTIFY_MODE=live → ส่ง LINE จริง
- Phase 4 (deferred): cache project_deadlines, full circuit-breaker analytics

---

# ═══════════════════════════════════════════════════════════════
# 📍 CHECKPOINT ละเอียด — 2026-05-30 21:15 ไทย (Day: family beta)
# ═══════════════════════════════════════════════════════════════

## 🎯 ภาพรวม: วันนี้ทำ Discovery→Delivery ครบวงจร (Province API plane)
จาก "RSS มองไม่เห็นหน่วยงานท้องถิ่น" → "ระบบ ingest งานท้องถิ่น + resolve deadline + พร้อมส่ง LINE (preview gate)"
**18 commits วันนี้** (ทั้งหมด local, ยังไม่ push)

## ✅ งานที่ทำแล้ว (timestamp จาก git)
| เวลา | commit | งาน |
|---|---|---|
| 10:45 | b97c68e | Province Search API discovery (เห็นหน่วยงานท้องถิ่น) |
| 10:55 | 6707159 | Token Service (ITokenProvider + state machine) |
| 13:33 | 0a445c5 | Chrome9222 token provider — live test + แก้ 3 bugs (PUT/origin/expiry) |
| 13:43 | 2916f77 | Token harvest automation (Windows writer + VPS worker) |
| 13:49 | 02d3b91 | First real ingest 730 rows + sanity ผ่าน |
| 16:55 | f9e339a | Delivery-wiring architecture APPROVED (ChatGPT+Claude) |
| 17:17-25 | f1c3af2,ace0c0b | Phase 0 characterization + resolver direction (Exp1 falsify browser-navigate) |
| 17:31-42 | 1854c06,41270ee,db69f70 | skeleton: deadline_service(Null) + schema migration + Pass 3 (fail-closed) |
| 17:47-51 | f3b0d86,b04812a,1e303d2 | greenBook RE → FALSIFIED (แค่ metadata) |
| 20:54 | a7b0357 | 🎯 BREAKTHROUGH: infoProcureDocAnnounZip→view-pdf→pdfplumber resolver |
| 20:57 | 589e146 | DocZipPdfDeadlineProvider (Phase 1) |
| 21:10 | 9d99f3d | Phase 3: retry+circuit-breaker+preview go-live gate |

## 🟢 สถานะระบบ ณ ตอนนี้
| Component | สถานะ | หมายเหตุ |
|---|---|---|
| VPS services (9 ตัว) | ✅ active ทั้งหมด | api/tunnel/rss-scraper/rss-notifier/enrichment/line-sender/province-discovery/daily-digest/backup |
| api_state | HEALTHY | |
| customers active | 5 คน | subscribe นครพนม+บึงกาฬ |
| projects_seen | province_api 730 + rss 291 | |
| province_epoch | 2026-05-30T10:34:33Z | suppress backlog 730 |
| notification_queue | sent 5, failed 2, **pending 0** | (จาก RSS test เก่า) |
| project_locations province_api | 0 (ว่าง) | 0 post-epoch candidates — backlog suppressed |
| Windows Task BMS_TokenHarvest | ทุก 25 นาที | harvest token + push VPS (ensure_chrome auto) |
| next discovery run | Sun 2026-05-31 00:00 UTC (07:00 ไทย) | |
| Deadline resolver | doczip, 95% coverage | env BMS_DEADLINE_PROVIDER=doczip |
| Notify mode | **preview** (go-live gate) | env BMS_PROVINCE_NOTIFY_MODE=preview |

## 🏛️ Architecture สุดท้าย (full pipeline)
```
[Windows] Chrome9222 harvest token (25นาที) → push VPS
[VPS] province-discovery timer (07/13/19น.) → search D0 → ingest projects_seen
[VPS] enrichment-worker (2นาที) Pass 3 qualify_province_api:
    seed post-epoch → project_locations(pending)
    → DeadlineService(doczip): infoProcureDocAnnounZip→view-pdf→pdfplumber→deadline
    → Epoch Gate (suppress backlog) → Deadline Gate (>= today)
    → mode=preview: Discord preview (held) | mode=live: enqueue → LINE
    → retry 2 ชั้น (provider 3x + worker pending→MAX5) + circuit-breaker (5 consec→abort+alert)
```

## ⏳ งานค้าง (Pending)
**ด่วน (go-live — เมื่อมีงานใหม่):**
- [ ] discovery รอบหน้า (07:00 ไทย) ป้อนงาน post-epoch → preview เข้า Discord
- [ ] review 1-3 preview (deadline แม่น? งานตรง target?) → flip BMS_PROVINCE_NOTIFY_MODE=live → ส่ง LINE จริง

**ภายใน sprint:**
- [ ] รัน บึงกาฬ ingest (discovery timer ทำทั้ง 2 จังหวัดอยู่แล้ว แต่ยังไม่เคยรัน บึงกาฬ เต็ม)
- [ ] Phase 4 (deferred): cache project_deadlines (resolve once read many) + circuit-breaker analytics
- [ ] document-type drift: characterize coverage by stepId/announceType (ตอนนี้ทดสอบ D0/ประกวดราคา ล้วน)
- [ ] RSS path migrate เข้า deadline gate (ตอนนี้ province_api เท่านั้นมี gate)

**Defer:**
- [ ] tune Windows harvest 25→20 นาที (เคยเจอ token gap)
- [ ] push to remote (รอ confirm)

## 🔑 บทเรียน/decisions สำคัญวันนี้
1. **Deadline ไม่มีใน JSON API** — อยู่ใน PDF เท่านั้น → infoProcureDocAnnounZip→view-pdf คือ projectId→templateId
2. **fail-closed validated by evidence**: 19/20 backlog = ปิดแล้ว → ไม่มี gate = blast งานปิดใส่ครอบครัว
3. **greenBook = แค่ metadata** (ไม่พก file link) — เกือบหลงทาง
4. **ผม trip WAF 2 ครั้ง** (throttle + brute-sweep) → บทเรียน: capture browser ครั้งเดียว, ห้าม brute, spacing เสมอ
5. Resolver = pure process5 API + AES token (ไม่ต้อง browser) → รัน VPS ได้

## 📂 Resume references
- progress_log.md (งานที่ N+29..N+39 + checkpoint นี้)
- memory: project_delivery_wiring_decision.md, project_province_search_api.md
- data/research_deadline_resolution_2026_05_30.md (probe ทั้งหมด)
