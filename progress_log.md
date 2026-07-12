# Bid Master System — Progress Log

> เก็บเฉพาะ entry ล่าสุด (~20 อัน). entry เก่ากว่านี้อยู่ใน progress_log_archive.md


## งานที่ N+180: CHECKPOINT — ก่อนเปลี่ยน session (2026-06-30)

### สถานะ: ⏸ pause เปลี่ยน session

### ✅ เสร็จแล้ว session นี้ (บอร์ด B = bid-master-dashboard.vercel.app/portal/world เป็นตัวหลัก)
- N+176 customer store เว็บ→engine SQLite (เลิก Sheets/googleapis), cold start 9s→1.2s
- N+177 บอร์ดโชว์งานติดตามจริง (GET /api/portal/jobs reuse _portal_jobs) + ⭐→job_stars + expires_at=created+30
- N+178 LINE Login จริง (LINE_LOGIN_* บน Vercel, provider เดียวกับบอท) เลิก dev-mock → กัญจน์ login เห็น 15 งาน
- N+179 เก็บของหลอก: หน้าแพ็กเกจ PAYMENT SUCCESS/QR/Demo → "แจ้งความสนใจ"→Discord admin (POST /api/portal/upgrade-request); ซ่อนปุ่มกระดิ่ง/COMING SOON/เร็วๆนี้
- HEAD=5ca5317, VPS git=origin สะอาด, sanity เขียว (5 ราย/0 ซ้ำ)

### 🎯 NEXT ACTION (session หน้า): Phase 2 บอร์ด B
**ยังไม่มี spec/plan — ต้อง brainstorm ก่อน** (superpowers:brainstorming)
2 งานหลัก (เรียงตามคุณค่า):
1. **keyword matching ราย user** — ตอนนี้ engine match แค่จังหวัด (subscription_provinces). keyword/งบ/รัศมีที่ลูกค้าตั้งในหน้า "บริษัท" (notes.classes) เซฟได้แต่ยังไม่กรองงาน → ทำให้ keyword/งบ มีผลจริงกับการ match/แจ้งเตือน. ดู [[project_matching_design]] [[project_matching_per_tenant_debt]]
2. **section discovery "งานใหม่ที่แมตช์"** — บอร์ดโชว์งานใหม่ในพื้นที่/keyword ที่ลูกค้ายังไม่ติดตาม (ตอนนี้โชว์เฉพาะ followed_jobs). ต้องสร้าง matching query บน projects_seen (จังหวัด+keyword). spec เดิม 2026-06-30-portal-real-jobs-design.md ระบุ discovery เป็น Phase 2

### ⚠️ Gate/gotcha สำคัญ (zero-context ต้องรู้)
- **บอร์ด 2 ตัว**: A=`api.butler-bms.com/portal` (HTML จากลิงก์ LINE, มีอยู่เดิม) · B=`bid-master-dashboard.vercel.app/portal/world` (Next.js, ตัวหลักใหม่). งานทำกับ B
- **deploy B**: engine scp `scripts/bms_api.py`→VPS root@45.76.156.166 (`~/.ssh/bms_vps`, user bms, restart `bms-api.service`) + web `cd dashboard/web && vercel deploy --prod --yes`
- **VPS git reconcile หลัง scp+push**: ต้อง stash+ff-pull (CRLF diff หลอก — ใช้ `git diff --ignore-cr-at-eol`); ดู [[project_deploy_debt]]
- **vercel env add ห้ามผ่าน PowerShell pipe** (ใส่ BOM) → ใช้ bash printf
- **secret**: BMS_INTERNAL_SECRET ตั้งแล้วทั้ง VPS .env + Vercel (ค่า A0W4kkq8... — ดูใน scratchpad/bms_secret.txt ถ้าต้อง)
- engine test: asyncio direct + scratch DB copy (BMS_DATA_DIR) ห้ามแตะ prod
- ลูกค้าจริงมี follow: Ua0d90e8(กัญจน์ 15), ณฐมน 7, Mr.suvit 8

### ค้าง/ระวัง (เล็ก)
- Sebastian Chat quota ring (world) = ตัวเลขเฉยๆ แชตจริงใน LINE (ไม่ถึงกับหลอก)
- Postgres (หน้าประวัติ) ยังแยกจาก SQLite engine

## งานที่ N+181: Phase 2 บอร์ด B — section "งานใหม่ที่แมตช์" (discovery + per-user keyword matching) (2026-07-01)

### สถานะ: ✅ DEPLOYED (engine+web) & VERIFIED — เหลือ git push (creds กัญจน์) + VPS git reconcile

### สิ่งที่ทำ (SDD: brainstorm→spec→plan→6 tasks subagent-driven→final review opus)
- spec `docs/superpowers/specs/2026-06-30-portal-discovery-design.md` · plan `docs/superpowers/plans/2026-06-30-portal-discovery.md`
- **scope ปลอดภัย**: discovery board เท่านั้น — ไม่แตะ LINE pipeline / `config/matching_preferences.json` / `job_matcher.match_job` (final review ยืนยัน airtight)
- engine: `discovery_match.py` (pure matcher: province AND + keyword OR reuse `job_matcher._kw_hit` guards + negative safety net + budget range, budget=0 ผ่าน) · `_classes_from_notes` (รวม keyword/งบ ราย user จาก notes.classes) · `GET /api/portal/discover` (2 กลุ่ม biddable D0 deadline≥today / planning B* tor_is_fresh≤14d, ตัด followed, sort+limit 30) · `POST /api/portal/follow` (reuse `_record_follow`) · extract `_job_location_deadline` (DRY จาก `_portal_jobs`)
- web: `getDiscoverJobs` + relay route `/api/portal/follow` (secret server-side) · section "✨ งานใหม่ที่แมตช์" บน world + `DiscoverCard` (ชิป matched_keywords + งบ + countdown + ปุ่มติดตาม, ⭐ แยก) + 3 empty states

### Verify (prod, real data)
- engine scp `bms_api.py`+`discovery_match.py` → `/opt/bms/app/scripts/`, `bms-api.service` active
- smoke: 403 (bad secret) ✓ · 200 envelope `{ok,jobs:{biddable,planning}}` ✓
- กัญจน์ (Ua0d90e8): provinces=[นครพนม,บึงกาฬ] แต่ **keywords=[]** → discover คืนว่าง = empty-state ถูกต้อง (ยังไม่ตั้ง keyword หน้าเว็บ; matching LINE ใช้ global config)
- **read-only simulation** (kws=คอนกรีต/ถนน/ท่อ/ก่อสร้าง/อาคาร บน 1,182 candidate 2 จว.) → **biddable=11 planning=1** matched_keywords/deadline/location ถูก → พิสูจน์ pipeline ครบ
- web `vercel deploy --prod` READY, aliased `bid-master-dashboard.vercel.app`
- tests เขียว 5/5: discovery_match, classes_from_notes, discover_api, follow_api, portal_jobs (regression)
- SDD: 6 task ผ่าน review (Task 3&4 มี fix wave 1 รอบ: Task3 revert D0 ตาม spec + test hermetic; Task4 add 400 case) + final review opus = READY, 0 Critical/Important

### Followup (ค้าง)
- 🔴 **git push origin main** — sandbox นี้ push (write creds) ไม่ผ่าน → กัญจน์รัน `git push origin main` เอง (local HEAD=b23db16, origin ยัง b0cafa7)
- 🔴 **VPS git reconcile** หลัง push: `cd /opt/bms/app && git stash -u && git pull --ff-only && git stash drop` (VPS มี scp'd bms_api.py + untracked discovery_match.py → ให้ git คุมหลัง push)
- 🟡 **users ต้องตั้ง keyword หน้า "บริษัท"** ถึงจะเห็น discovery (ตอนนี้ทุกคน keywords=[] → เห็น empty-state prompt) — คือ value ของฟีเจอร์ขึ้นกับ user ตั้งค่า
- Minor debt (จาก review): `_classes_from_notes` ไม่ guard non-dict JSON (latent, web เขียน dict เสมอ); `portal-jobs.ts` ไม่มี `server-only` guard; `&quot;` vs Thai curly quotes (cosmetic)

### Followup ✅ SEED keyword ให้ลูกค้าเดิม (2026-07-01)
- พบ: ลูกค้าทุกคน notes ว่าง (classes=0) — subscription_provinces มาจาก LINE onboarding ไม่ใช่เว็บ → discovery ว่าง + web gate ไม่ผ่าน
- seed: สร้าง business class 1 อันต่อคน (shape ตรง `classes/_client.tsx:1033`) geo.provinces=subscription_provinces เดิม + keywords=global config `keywords` (89 คำ ก่อสร้าง/จ้าง) → notes. idempotent (เฉพาะ classes=0), online backup ก่อน (`/opt/bms/data/backups/bms_customers_pre_kwseed_20260701_071556.db`)
- 5 ลูกค้า seeded (Ua0d90e8/Ucb1758f/Ua93a6f5/U9e2e34e/U574d245 ทั้งหมด นครพนม+บึงกาฬ)
- verify endpoint จริง: ทุกคน discover → **12 biddable + 1 planning** matched_keywords ถูก ✅
- หมายเหตุ: งาน "ซื้อ" โผล่ด้วย (discovery ไม่มี proc split — ตัดทีหลังได้ถ้าต้องการ); DB บน VPS มี notes ราย user แล้ว (ต่างจาก global config LINE pipeline ที่ยังเหมือนเดิม)

## งานที่ N+182: ย้าย Harvest Node ไปเครื่องใหม่ (single-writer cutover) (2026-07-01)

### สถานะ: ✅ เสร็จ — เครื่องใหม่เป็น writer เดียว, เครื่องเก่า task disabled (รอยืนยัน auto-run รอบถัดไป)

### สิ่งที่ทำ
- setup เครื่องใหม่ตาม `docs/setup_harvest_node.md` เฟส 1-4 ครบ (repo/py/pkg/chrome/.ssh/.env, แก้ bat/vbs python path, Phase 3 manual harvest ผ่าน token+scp, Task Scheduler 25 นาที + startup script)
- ขนของลับ 2 ไฟล์ (`bms_vps`+`.env`) ผ่าน LAN http.server ชั่วคราว (เน็ตบ้านเดียวกัน IP เดียว) แทน USB — โค้ดดึงจาก GitHub
- ตอบข้อกังวลเครื่องใหม่: (1) "bypass Turnstile" ไม่ถูก — โค้ดใช้ browser จริงที่ Turnstile ปล่อยผ่านเอง อ่าน token ที่เว็บแจก frontend (ดู `token_service.py:134`), ไม่ solve/forge อะไร (2) "ต้อง login" ผิด — profile เครื่องเก่ามี cookie แค่ 3 (Xsrf-Token+TS* WAF) ไม่มี login/cf_clearance → copy profile ไม่ช่วย, ผ่านด้วย network-trust สดทุกรอบ

### Verify (ก่อนตัด)
- VPS `token_state.json`: provider `chrome9222_warm` (เครื่องใหม่) สดกว่า local เครื่องเก่า (`chrome9222`) → พิสูจน์ push เครื่องใหม่ landed จริง
- disable `BMS_TokenHarvest` เครื่องเก่า (Status: Disabled) → VPS token (158s) สดกว่า local เครื่องเก่า (812s แช่แข็ง) = ยืนยันเครื่องใหม่เป็น writer เดียว
- ปิดช่อง LAN 8731 + ลบ secret ที่ staged; scheduler.py/dashboard เครื่องเก่าไม่ใช่ harvester (ไม่ refresh token)

### Followup
- ✅ **auto-run เครื่องใหม่ยืนยันแล้ว** — VPS token provider พลิก `chrome9222_warm`→`chrome9222` (Task Scheduler รัน Chrome9222Provider เองสำเร็จ) = harvest ย้าย 100%
- ✅ ไข `chrome9222_warm` — เครื่องใหม่มี temp debug script `harvest_now.py` (ไม่อยู่ใน repo) ตั้ง label เอง แล้ว harvest_and_push reuse token valid → push label นั้นไป VPS; token ถูกต้อง cosmetic เท่านั้น
- ✅ **RSS_Probe disabled** (ต้อง admin) — telemetry เขียน `rss_availability_log.ndjson` ที่ไม่มี consumer active (VPS ทำ RSS จริงผ่าน `bms-rss-scraper`); ไม่กระทบงานจริง
- ✅ **ลบ harvest startup เครื่องเก่า** — `BMS_HarvestOnLogon.vbs` ใน Startup folder รัน harvest_and_push ตอน login → เปิด Chrome 9222 (Chrome เด้งทุก boot). ปิด task อย่างเดียวไม่พอ (คนละตัว). ย้ายออก backup ที่ `backups/BMS_HarvestOnLogon.vbs.disabled_*` → เครื่องเก่าไม่เปิด Chrome harvest ตอน boot อีก (เครื่องใหม่ยังต้องมี startup นี้)

### CGD decision: B (คง CGD ไว้เครื่องเก่าก่อน) — ดู [[project_cgd_api_blocks_datacenter]]
- CGD (discovery 05:00 + winner_refresh 21:30 รายวัน) residential-only (VPS 403), **ยัง active** — คงไว้เครื่องเก่า
- StartWhenAvailable=True → เครื่องเก่า**เปิดวันละครั้งตอนสะดวกพอ** (รันชดเชยรอบที่พลาด) ไม่ต้องเปิด 24 ชม.
- 🔜 **ปลดเครื่องเก่าเต็ม (งานแยก ทีหลัง):** ขน `winner_history.db` **7.8GB** ไปเครื่องใหม่ผ่าน LAN + ตั้ง 2 task + **ต่อสาย sync ให้ auto** (`cgd_sync_to_vps.py --push` ตอนนี้ไม่มี task เรียก = manual/ค้าง)
- เครื่องเก่าเหลือ non-BMS: `scheduler.py` + `dashboard/server.py` (แอปอื่น ไม่เกี่ยว BMS)

## งานที่ N+184: Implementation plan — คืนพฤติกรรมแจ้งเตือน (สเตจ 1) (2026-07-02)

### สถานะ: ✅ เสร็จ (แผน) — พร้อม subagent-driven execute

### สิ่งที่ทำ
- `superpowers:writing-plans` → `docs/superpowers/plans/2026-07-02-notification-restore.md` จาก spec APPROVED `2026-07-01-notification-restore-design.md`
- สืบโค้ดจริงก่อนเขียน: cut/digest เกิดเฉพาะ `BMS_MATCHING_MODE=enforce` (บรรทัด 429-440 ใน `qualify_province_api`); shadow ไม่ตัด. production รัน enforce → นั่นคือสาเหตุ. labels lifecycle มีครบใน `Sebastian_LINE_Sender.format_notification` (bid_open/prelim/winner/cancelled). `build_follow_link` คืน `''` เงียบเมื่อ secret หาย = จุด silent-bypass

### แผน = 5 task TDD (standalone `python scripts/test_*.py`)
1. **Enrichment** — เพิ่ม param `dsvc=None` (inject test) + เลิก `is_digest` + เลิก enforce-cut (B0+D0) → งาน province เปิดอยู่ enqueue เสมอ, match_job ยัง shadow-log, soft label คงไว้
2. **Verify labels** — test ล็อกป้าย 4 แบบ (คาดว่าไม่ต้องแก้ code)
3. **Daily summary → recap** — `fetch_today_sent`+`fetch_notes_due`; build_message ใหม่ (นับวันนี้+รายการ+todo พรุ่งนี้+โน้ต due); ลบ digest wiring + `test_daily_digest.py`
4. **follow-link fail-loud** — `build_follow_link(strict=True)` raise แทนคืน '' [[feedback_never_bypass_send_path]]
5. **ลบ 89-keyword seed** — `clear_keyword_seed.py` idempotent, dry-run default, รันจริง (`--apply`) ใน Rollout หลัง backup

### Self-review
- API/schema ที่เทสต์อ้าง verify แล้วมีจริง (`add_subscription`, `format_notification`, `is_test_data` migration v1.6, `customers.notes`, `job_notes.entry_date`). ไม่มี placeholder. spec coverage ครบ 4 เป้า+6 component

### Followup / Gate
- 🔴 **prereq deploy คงเดิม: กัญจน์อัปเกรด LINE paid** ก่อน enforce instant (code+shadow ทำก่อนได้)
- Rollout: push→VPS reconcile→shadow 1 วัน→test-send ตัวเอง→backup+ลบ seed→ตั้ง 23:00 recap→Sophia sanity

---

## งานที่ N+183: CHECKPOINT — ก่อนเปลี่ยน session (2026-07-01)

### สถานะ: ⏸ pause เปลี่ยน session

### ✅ เสร็จ session นี้
- **N+181 Phase 2 discovery** DEPLOYED (engine+web, origin+VPS=bfb0eff) + seed keyword 89 คำให้ลูกค้า 5 ราย → discovery board มีงานจริง 12+1
- **สืบบั๊ก LINE "ค้างงานเดียว"**: พบ notification_queue หยุดตั้งแต่ 25 มิ.ย. — enrichment worker `match_job` cut งานเป็น `filtered_no_match` (ก่อสร้างบางงานหายผิด) + งานก่อสร้างทั้งจังหวัด batch เป็น `qualified_digest` ส่งรอบเดียว 23:00; backlog digest เห็นแค่งานที่เคย fail
- **ปิด user Hong** (active=0) + **ส่ง LINE backlog** 2 รอบ (รอบ 2 = 70 ข้อความ **พัง ไม่มีชื่อ/ลิงก์** เพราะเรียก `format_notification` ดิบ ข้าม `_plain_text_body`+quick_reply — กัญจน์ตัดสินใจ "พลาดแล้วพลาดไป")
- **บทเรียน** → memory [[feedback_never_bypass_send_path]]: อย่าประกอบข้อความ LINE เอง reuse canonical path + test-send ตัวเองก่อน broadcast + verify output ก่อนเคลม
- **brainstorm + spec** พฤติกรรมแจ้งเตือนใหม่ (approved)

### 🎯 NEXT ACTION (session หน้า): เขียน implementation plan สเตจ 1
- **skill:** `superpowers:writing-plans` → อ่าน spec `docs/superpowers/specs/2026-07-01-notification-restore-design.md` (APPROVED) แตกเป็น task ย่อย TDD
- **สเตจ 1 = คืนพฤติกรรมแจ้งเตือนแบบเดิม** (ก่อน phase-B category UI):
  1. งาน D0 ทั้งจังหวัด (นครพนม+บึงกาฬ, **ไม่กรอง** รวมนอกสาย) → enrichment worker เลิก cut/digest → `enqueue_notifications()` ทุกงาน → line-sender ส่ง **instant เต็ม (ชื่อ+ลิงก์ดูประกาศ+ลิงก์ติดตาม)** อัตโนมัติ
  2. followed jobs เลื่อนเฟส → ส่งทันที + ป้ายหัวข้อ (ประกาศวันยื่นซอง/สรุปราคาเบื้องต้น/ผู้ชนะ) — verify winner-poller labels
  3. **23:00 = สรุปประจำวัน** (count วันนี้ + todo พรุ่งนี้ = งานยื่นซองพรุ่งนี้ **+ โน้ต job_notes/timeline due**) — แก้ `Sebastian_Daily_User_Summary.py`
  4. ลบ seed 89-keyword
- **priority: ไม่พลาดงาน** = ห้ามตัดทิ้งเงียบ, fail-loud
- หลังเขียนแผน → execute (subagent-driven) → **shadow test** (log ปริมาณ/วัน) → deploy

### ⚠️ Gate/gotcha
- 🔴 **PREREQ ก่อน deploy instant: กัญจน์ต้องอัปเกรด LINE OA เป็น paid** (free 300/เดือน แต่ instant ทุกงาน ~400-500/เดือน) — เขียนแผน+โค้ด+shadow ได้ก่อน รอแค่ deploy-enforce. เช็ค quota: `/v2/bot/message/quota` (ตอนนี้ limited:300, ใช้ 91)
- **reuse line-sender path** (enqueue → sender) ห้าม re-implement (บทเรียนวันนี้)
- VPS: engine `/opt/bms/app/scripts/`, DB `/opt/bms/data/bms_customers.db` (BMS_DATA_DIR), รัน manual ต้อง `set -a && . ./.env && set +a`; git push ผ่าน `git -c credential.helper='!gh auth git-credential' push` (manager hang)
- **phase-B (ทีหลัง):** ปุ่มติ๊กหมวด 5 หมวดบน Board B — spec `docs/superpowers/specs/2026-07-01-category-matching-design-DRAFT.md`

### ค้าง/ระวัง
- seed 89-keyword ยังอยู่ (ลบตอนทำสเตจ 1)
- discovery ตอนนี้ 07/13/19; winner-poller 07:15/13:15/19:15/01:15 — กัญจน์เคยถามอยากได้ 07/12/18 (ปรับได้ทีหลัง)

## งานที่ N+185: DEPLOY Notification Restore สเตจ 1 → VPS LIVE (2026-07-02)

### สถานะ: ✅ deployed & verified (LINE upgrade ยังค้าง)

### สิ่งที่ทำ
- merge feat/notification-restore → main (`331b775`, --no-ff), push origin, tests 10/10 เขียว
- VPS deploy (ssh key `~/.ssh/bms_vps`): backup DB → `git pull --ff-only` (bfb0eff→331b775) → restart bms-api (active, portal 200). workers เป็น timer รับโค้ดใหม่เอง
- verify VPS env: `BMS_FOLLOW_SECRET` SET (fail-loud ไม่ crash), mode=live, matching=enforce (ตัวที่ cut), keyword-first=shadow. service โหลด `EnvironmentFile=.env`
- **canary:** reset 1 งานเปิด (69039214713 "ปรับปรุงผิวจราจรแอสฟัลท์ ถนนเทพนคร" นครพนม deadline วันนี้ — งานถนนที่โดน cut ผิดเป๊ะ) → enqueue+sent ถึง customer 2 (Kan Kan=กัญจน์) → **กัญจน์ verify มือถือ: ชื่อ+ลิงก์ดูประกาศ+ติดตาม ครบ** ✅
- **backlog reset:** 69 filtered_no_match → pending (backup ก่อน). enrichment churn: expired→suppress (ไม่เปลือง quota), open→enqueue. **open backlog remaining=0** (completeness reviewer resolved). filtered=0 ทุก batch (no-cut ยืนยัน)

### ผล
- 12 งานจริง enqueue (province_qualified 31 rows + B0 tor_review 16 = 47 fanout), drain 1/นาที ผ่าน bms-line-sender.timer
- **quota: 100→~110** ใช้จริงน้อยมาก (backlog ส่วนใหญ่หมดอายุ). จบ ~156 << 300
- งานนอกสายโผล่ด้วย (แพะ/เครื่องซักผ้า/เช่า) = พฤติกรรม "ไม่กรอง" ที่ approve → phase-B category tick กรองทีหลัง

### ค้าง (Rollout ที่เหลือ)
- 🔴 **LINE paid upgrade** ก่อน quota หมด (~กลางเดือน ก.ค.) — กัญจน์ทำเอง
- clear_keyword_seed --apply (ยังไม่รัน — กระทบ web board B ไม่กระทบ LINE)
- ตั้ง cron 23:00 recap (daily summary เดิม 20:00)
- (defer) Discord alert เมื่อ follow-secret หาย (final review แนะนำ)

## งานที่ N+186: Board 2 (/portal/world) — เก็บฟีเจอร์หลอกให้เป็นของจริง (2026-07-04)

### สถานะ: ✅ เสร็จ + LIVE (push+deploy ครบ 2026-07-05)

### ที่มา
กัญจน์สั่งไล่อ่านโค้ดบอร์ด 2 หา "ฟีเจอร์หลอก" แล้ว approve ลำดับแก้: tier ผิดคน → ดาว discovery → กดดูรายละเอียด → Sebastian Chat → expiry จริง (ทำ overnight autonomous)

### สิ่งที่ทำ (5 commits)
1. `bd55310` **tier ผิดคน (bug โชว์ข้อมูลเท็จ):** web `toCustomer()` ทิ้ง `customers.tier` → `getTierId` เดา active→standard ทำให้ trial ทุกคนขึ้นป้าย "มาตรฐาน 1,800฿ ต่ออายุอัตโนมัติ". แก้: อ่าน tier column จริง (validate กับ TIERS) + copy "ต่ออายุอัตโนมัติ" → "ใช้ได้ถึง {วันที่}" + profile page ใช้ getTierId เดียวกัน
2. `b0d9838` **ดาว discovery persist:** `/api/portal/discover` ส่ง `starred` ต่อการ์ด (join job_stars) + เว็บ init ดาวรวม discovery (เดิมกด ★ แล้วรีเฟรชดาวหายทั้งที่ DB บันทึก)
3. `2081d83` **การ์ดกดดูรายละเอียดได้:** endpoint ใหม่ `GET /api/portal/board-token` mint token canonical (follow_token, p=None) → การ์ดทุกใบลิงก์เข้าหน้า detail เดิม `/portal/job` (ผู้ยื่น/คู่แข่ง/โอกาสชนะ/โน้ต — reuse ทั้งหน้า) + การ์ด "รอผล" โชว์ prelim_low+จำนวนผู้ยื่น
4. `486fef9` **ซ่อน Sebastian Chat quota:** ไม่มีแชท AI จริง (LINE=เมนู keyword) + chatUsed ไม่มีตัวนับ → gate `SEBASTIAN_CHAT_LIVE=false` เปิดคืนบรรทัดเดียวเมื่อสร้างจริง
5. `95d459d` **expiry จริง + เครื่องมือแอดมิน:** migration v138 `customers.expires_at` (additive) + `/api/portal/customer` ใช้ค่าจริงก่อน fallback created+30 + `set_customer_tier.py` (--list / --user --tier --expires, dry-run default) ปิด loop อัปเกรด

### Sanity
- test 18 ไฟล์ผ่านหมด (test_portal_* ทั้งชุด + winner_poller×3 + set_customer_tier ใหม่) + `tsc --noEmit` สะอาดทุก commit
- **Sophia verdict: SAFE** — scope ตรงทุก commit, migration additive/idempotent, X-BMS-Secret ครบ, token p=None ไม่ leak ข้าม customer (ยืนยัน /portal/job ไม่ผูก pid กับ token), dry-run guard จริง, test รันบน tempdir ไม่แตะ prod

### Deploy (2026-07-05 กัญจน์ confirm "push + deploy เลย")
- push origin `331b775..19c681d` ✅
- **VPS ดิสก์เต็ม 100% ตอน backup!** root cause จริง (แก้ 2026-07-06): backup_db.py **มี retention 14 วันอยู่แล้วและทำงานปกติ** แต่ DB โต 439MB→1.9GB หลัง backfill สกลนคร → 14 วัน ≈ 27GB + migration backups มือใน data/backups อีก 11G ล้นดิสก์ 52G. prune มือเหลือ daily เต็ม 3 วัน + predeploy → 100%→61%. daily 0704/0705 เป็นไฟล์ขาด (ก็อปตอนดิสก์เต็ม — เงียบ!) ลบทิ้ง
- **fix ถาวร `4578031`:** RETAIN_DAYS 14→5 (~9.5G) + ตรวจขนาด backup เทียบต้นฉบับ ขาด→ลบ+exit 1 (กัน backup เสียเงียบ). verify จริงบน VPS: บันทึก 20260706 เต็ม 1.9G, prune 0701 อัตโนมัติ, ดิสก์นิ่ง 65%
- **git push ค้างเงียบ:** GCM เปิด re-auth UI ที่ session กดไม่ได้ → ตั้ง repo-local `credential.helper=!gh auth git-credential` (push ปกติใช้ได้แล้ว ไม่ต้อง override) — ดู memory [[project_git_push_gcm_hang]]
- VPS: backup pre_v138 → pull ff-only → restart bms-api → verify: expires_at column ✅ health 200 ✅ board-token 403 (no secret) ✅
- Vercel: `vercel deploy --prod` READY, /portal/world → 307 login (ถูกต้อง)

### ค้าง / defer
- **ตัดสินใจ Sebastian Chat:** สร้างจริง (LINE AI chat + ตัวนับ quota) หรือเอาออกจาก perks หน้า packages ด้วย — การ์ดซ่อนแล้วแต่ perks ใน TIERS ยังโฆษณาอยู่
- **defer (ต้อง design):** matching ระดับอำเภอ/ตำบล/GPS (UI เก็บแล้ว engine ใช้แค่จังหวัด — เกี่ยว matching_design soft-include), isSME/isMIT/notifyTime เก็บแต่ไม่ใช้
- ~~หมายเหตุ: หน้า detail ที่ลิงก์ไปเป็นธีมเก่า (ฟ้า-ขาว) ไม่แมตช์ธีมทอง world~~ → ทำแล้ว N+187

## งานที่ N+187: หน้ารายละเอียดงานธีม Board B — /portal/job/[pid] (2026-07-06)

### สถานะ: ✅ เสร็จ + **LIVE (push+deploy ครบ 2026-07-07 กัญจน์ confirm "Push บอก Deploy เลย")**
- push origin `6eb3b72..dc978ed` ✅
- VPS: pull ff-only → `sudo -n systemctl restart bms-api` → verify: health 200 ✅ job-detail/job-note 403 (no secret) ✅ หน้าเก่า /portal/job ยังเสิร์ฟ 200 ✅ (หมายเหตุ: bms-api ฟัง 127.0.0.1:**8000** ไม่ใช่ 8500)
- Vercel: deploy --prod READY, /portal/job/[pid] อยู่ใน build; ไร้ login → 307 /portal/login ✅ api job-note ไร้ session → 401 ✅

### ที่มา
กัญจน์: กด "ดูรายละเอียด" จากการ์ด Board B แล้วเด้งไปหน้า engine ธีม A ไม่กลมกลืน → สั่ง**สร้างหน้าใหม่ธีม B เลย ไม่แก้หน้า A** (LINE links ใช้หน้า A ต่อ). ตัดสินใจก่อนไปนอน: จัดเต็มเท่าหน้าเดิม + ชื่อบริษัทลิงก์หน้าบริษัทธีม A ไปก่อน → มอบให้ทำ autonomous จนจบ

### สิ่งที่ทำ (3 commits)
1. `3b0fa9f` spec `docs/superpowers/specs/2026-07-06-board-b-job-detail-design.md`
2. `dd7b04c` **engine:** เพิ่ม 3 JSON endpoints ท้าย bms_api.py (append-only ไม่แตะหน้า A):
   `GET /api/portal/job-detail` (job_detail เดิม + notes/overview/starred + href บริษัทธีม A mint follow_token ฝั่ง engine),
   `POST /api/portal/job-note` (add/edit/delete/save_overview คืน state ใหม่), `POST /api/portal/job-calc` (Gates)
   + `test_portal_job_detail_api.py`
3. `ee0e3c0` **web:** `/portal/job/[pid]` page+client ธีม B ครบทุก section (หัวงาน/ราคากลาง/คาดราคา/
   เดดไลน์+countdown/ตารางคู่แข่ง/ตารางโอกาสชนะ/เครื่องคำนวณ/ผู้ยื่น/โน้ตภาพรวม/ไทม์ไลน์/ดาว⭐)
   + proxy job-note/job-calc + `p-table` CSS + การ์ด world ชี้ลิงก์ภายใน (เลิกใช้ getJobDetailBase/board-token ฝั่งเว็บ — endpoint engine ยังอยู่)

### Sanity / verify
- engine: test ใหม่ผ่าน + test_portal_notes/star_api/jobs_api/routes เดิมผ่าน
- web: `npm run build` ผ่าน (Next 16, params เป็น Promise)
- **e2e จริง:** stub server รันโค้ด bms_api จริงบน scratch DB + `next dev` + session cookie จริง →
  หน้า render ครบ section, note add/calc/star ผ่าน proxy, ไร้ cookie = 401, world ไม่เหลือลิงก์ token เก่า
- shape intel ตรวจกับซอร์ส cgd_intel/bid_field แล้ว (tin เติมท้าย, rows tuple→array, conf tuple)
- Sophia: code review ผ่านทุกข้อ (append-only ✅ secret guard ✅ cross-tenant guard 2 ชั้น ✅ ไม่มี silent error ✅
  test แยก tempdir ✅) — verdict STOP แค่เพราะ sub-agent SSH VPS ไม่ได้ (ตรวจ DB สดไม่ได้);
  main thread ตรวจเองแล้ว (`ssh bms@VPS` key `~/.ssh/bms_vps`): customers ทดสอบ/U1/U9=0,
  pid 69000000001=0, note e2e=0 → **ปิดเป็น SAFE** (โค้ดยังไม่ deploy — เทสต์ทั้งหมดรัน scratch DB local เท่านั้น)

### Followup
- ~~push + deploy (VPS engine + Vercel)~~ ✅ LIVE 2026-07-07
- ~~phase ถัดไป (ถ้าเอา): หน้าบริษัทธีม B~~ → ทำแล้วใน N+188
- LINE links ยังเข้าหน้า A ตามตั้งใจ — ถ้าอยากให้ LINE เข้าหน้า B ต้องคิดเรื่อง login/LIFF ก่อน

---

## งานที่ N+188: หน้าบริษัทธีม Board B — /portal/company/[tin] ปิดชุดธีม B (2026-07-07)

### สถานะ: ✅ เสร็จ + **LIVE (push+deploy ครบ 2026-07-07 กัญจน์ confirm "push + deploy เลย")**
- push origin `cfc5dec..808e1e7` ✅
- VPS `/opt/bms/app`: fetch รอบแรก timeout ถึง github (transient — รอบสองผ่าน) → ff-merge `808e1e7`
  → restart bms-api → verify: health 200 ✅ company-detail ไร้ secret 403 ✅ หน้า A /portal/job + /portal/company ยัง 200 ✅
- Vercel: deploy --prod READY (51s), `/portal/company/[tin]` อยู่ใน build; ไร้ session → 307 /portal/login ✅ error scan สะอาด ✅

### ที่มา
กัญจน์: "ทำหน้าบริษัทธีม B ต่อเลยทำชุดเสร็จเลย เดี๋ยวฉันจะนอนแล้ว" — ปิด gap สุดท้ายจาก N+187
(ชื่อบริษัทในหน้า job detail ธีม B ยังเด้งไปหน้าบริษัทธีม A)

### สิ่งที่ทำ
1. spec `docs/superpowers/specs/2026-07-07-board-b-company-page-design.md`
2. **engine** (`bms_api.py`):
   - `GET /api/portal/company-detail` ใหม่ (read-only ล้วน — reuse company_profile/head_to_head/
     won_portfolio/area_portfolio ของหน้า A ทั้งชุด, guard secret เหมือนตัวอื่น)
   - `_job_detail_payload()`: href บริษัทเปลี่ยนเป็น relative ธีม B `/portal/company/<tin>?from=..`
     / `?area_ids=..&area_label=..` — เลิก mint follow_token (เว็บ auth ด้วย session)
   - + `test_portal_company_detail_api.py` (ใหม่), อัปเดต assertion ใน test_portal_job_detail_api
3. **web:** `/portal/company/[tin]` page+client ธีม B ครบเท่าหน้า A: หัวบริษัท+SME+stat 4 ช่อง /
   ⚔️ h2h เทียบกับเรา / 📊 ยื่น–ชนะรายปี + 💸 histogram ส่วนลด (สีกราฟ #B8893A/#579E6A —
   ผ่าน dataviz validator บน surface มืด) / 🏆 won portfolio + chips filter proc (server refetch) /
   📍 ผลงานในพื้นที่ / ประวัติแยกรายปี — ทุกรายการงานลิงก์กลับ `/portal/job/<pid>` ธีม B
4. หน้า A เดิมไม่แตะ: `portal_views.py` diff = 0

### Sanity / verify
- engine: test ใหม่ + test job-detail เดิม ผ่านทั้งคู่ (scratch DB tempdir)
- web: `npm run build` ผ่าน — route `/portal/company/[tin]` ขึ้น
- **e2e จริง:** uvicorn bms_api scratch :8123 + `next start` :3111 + session cookie จริง →
  หน้า render ครบทุก section, proc filter กรองลิสต์ถูก (รายชื่องาน 2→1), ลิงก์บริษัทใน
  job page เป็น `/portal/company/<tin>?from=<pid>`, ไม่เหลือลิงก์ `?t=` ธีม A, not-found การ์ดขึ้น
- Sophia: **SAFE** — read-only ยืนยัน (ไม่มี write/migration), portal_views diff=0, secret guard ครบ,
  ไม่มี silent error, token flow route อื่นไม่กระทบ, tsc สะอาด, test scratch DB ไม่แตะ DB จริง
  (local DB มี test customer เก่า 2 แถว pre-existing — ไม่เกี่ยว diff นี้)

### Followup
- ~~push + deploy (VPS engine + Vercel)~~ ✅ LIVE 2026-07-07
- LINE links ยังเข้าหน้า A ตามตั้งใจ (เหมือน N+187)

---

## งานที่ N+189: การ์ด "★ งานที่สนใจ" กดกรองบอร์ดได้จริง (2026-07-07)

### สถานะ: ✅ เสร็จ + LIVE (push `0684401` + Vercel READY 53s; เว็บอย่างเดียว ไม่แตะ engine)

### Root cause
กัญจน์รายงาน "ปุ่มดูงานสนใจใช้ไม่ได้จริง" — การ์ด ★ ใน summary grid ของ `/portal/world`
เป็น SumCard **ไม่มี href/onClick ตั้งแต่เกิด** (การ์ดอื่นในกริดกดได้หมด เลยดูเหมือนปุ่มหลอก).
ประวัติ: section รายการงานติดดาวเคยมีในเวอร์ชันเก่า ถูกถอดตอน rework `3fc988a` เหลือแต่ตัวเลข

### Fix (กัญจน์เลือก: กรองบอร์ดทันที ไม่สร้างหน้าใหม่)
`world/_client.tsx`: SumCard รับ `onClick`+`active` → กดการ์ด ★ = toggle กรองทั้ง
Tracked + Discovery เหลือเฉพาะงานติดดาว (การ์ดเรือง gold + ✓ ตอน active, chip โชว์ `★ n/รวม`),
กดซ้ำ = กลับ; มี empty-state ทั้งสอง section ตอนกรองแล้วว่าง; ดาวหมด = ปิดกรองอัตโนมัติ

### Verify
- `npm run build` ผ่าน; SSR e2e (engine scratch + next start + follow/star U1 จริง) →
  หน้า render ครบ การ์ด ★ โผล่ ไม่มี error boundary

---

## งานที่ N+190: การ์ด "งานทั้งหมด" + หน้า /portal/jobs — ทุกงานที่ส่ง LINE ขึ้น Board B (2026-07-07)

### สถานะ: ✅ เสร็จ + LIVE (push `2e6e308..182dfa3`; VPS restart + all-jobs คืน 51 งานจริงของ Kan Kan; Vercel READY 53s, /portal/jobs เด้ง login ถูกต้อง)

---

## งานที่ N+191: CHECKPOINT — ก่อนเปลี่ยน session (2026-07-07)

### สถานะ: ⏸ pause เปลี่ยน session

### ✅ เสร็จแล้ว session นี้ (ทั้งหมด LIVE บน VPS+Vercel)
- **N+188** หน้าบริษัทธีม Board B `/portal/company/[tin]` — ปิดชุดธีม B ครบเส้น world→job→company
  (`a885229` spec · `bdafaf7` engine company-detail · `808e1e7` web · `86a6944` docs)
- **N+189** การ์ด "★ งานที่สนใจ" กดกรองบอร์ดได้จริง — เดิมเป็นการ์ดตัวเลขเฉยๆ (`0684401`)
- **N+190** การ์ด "📋 งานทั้งหมด" + หน้า `/portal/jobs` — ทุกงานที่เคยส่ง LINE (51 งานย้อนหลัง
  + งานใหม่ขึ้นเอง, อ่าน notification_queue read-only ไม่แตะระบบส่ง) (`2e6e308`+`182dfa3`+`89284d4`)
- เช็คข้อมูล Kan Kan หลังกัญจน์เผลอกดเล่น portal — ไม่มีอะไรเพี้ยน (จังหวัด/keyword/ดาวครบ)

### 🎯 NEXT ACTION (session หน้า)
- **ไม่มีงาน dev ค้างบังคับ** — รอกัญจน์สั่ง. งานใหญ่ถัดไปตามคิวเดิม = **phase-B category tick UI
  บน Board B** (spec DRAFT `docs/superpowers/specs/2026-07-01-category-matching-design-DRAFT.md`,
  UI decision accordion หมวดพับ+chip จดในดราฟต์แล้ว) — เริ่มด้วย superpowers:brainstorming ต่อยอด
  ดราฟต์ให้ approve ก่อน แล้ว writing-plans
- ⚠️ เช็คค้างจาก N+185: (1) กัญจน์ upgrade LINE OA เป็น paid หรือยัง (quota 300 จะตันกลาง ก.ค.
  — เช็ค /v2/bot/message/quota) (2) `clear_keyword_seed --apply` ยังไม่รัน (3) cron recap 23:00 ตั้งหรือยัง

### ค้าง/ระวัง
- การ์ด Sebastian Chat ยังซ่อนอยู่ — **รอกัญจน์ตัดสินใจสร้างจริง/ตัดจาก perks packages**
- LINE links ยังเข้าหน้าธีม A ตามตั้งใจ (ถ้าจะให้เข้าธีม B ต้องคิด login/LIFF ก่อน)
- uncommitted ใน working tree = runtime data (cgd_discovery_seen/rss_log/settings.local +
  db-shm/-wal จาก Sophia read-only) — ไม่ใช่งานค้าง อย่า git add -A

### ที่มา
กัญจน์: "ทุกงานที่ส่งต่อจากนี้ต้องขึ้น board B ด้วย + การ์ดใหม่ 'งานทั้งหมด' ดูง่ายๆ ไม่ต้องเลื่อน LINE"
ตัดสินใจ: รวมงานย้อนหลัง (มี ~51 งานใน queue อยู่แล้ว) + หน้าใหม่แยก

### หลักการ (ไม่แตะระบบส่ง LINE เลย)
notification_queue บันทึกทุกการส่งอยู่แล้ว (snapshot ชื่อ/จังหวัด + source_stage) →
อ่านตรงจากตารางนี้: งานเก่าขึ้นทันที งานใหม่ขึ้นเอง

### สิ่งที่ทำ
1. spec `docs/superpowers/specs/2026-07-07-board-b-all-jobs-design.md`
2. engine: `GET /api/portal/all-jobs` (read-only; sent+ไม่ใช่ test data, dedup ต่อ project
   เอารอบล่าสุด, stage map followed_winner→won ฯลฯ, คืน count ไม่ติด limit) + test ใหม่
3. web: `/portal/jobs` ธีม B (ค้นหา client-side, ป้าย stage ชุด STAGE_META, ลิงก์ detail,
   ไฮไลต์งานติดดาว) + การ์ด "📋 งานทั้งหมด" บน world (href /portal/jobs, engine ล่ม=ซ่อน)

### Verify
- test all-jobs ใหม่ผ่าน + regression job-detail/company-detail/jobs_api/notes ผ่าน
- `npm run build` ผ่าน (route /portal/jobs ขึ้น)
- SSR e2e: seed queue 3 แถว (P1 ส่ง 2 รอบ) → dedup ถูก, ป้าย stage ถูก, การ์ด world โชว์,
  ค้นหา/ลิงก์ครบ, ไม่มี error boundary
- Sophia: **SAFE** — read-only ยืนยัน, ไฟล์ระบบส่ง LINE ไม่ถูกแตะ, test-data ถูกกรอง
  (COALESCE(is_test_data,0)=0 ตรวจกับ DB จริงแล้ว), test scratch tempdir, เว็บไม่แตะ DB ตรง

---

## งานที่ N+192: ติ๊กกรอง phase หน้า "งานทั้งหมด" + ป้าย "รับฟังคำวิจารณ์" (2026-07-08)

### สถานะ: ✅ เสร็จ LIVE (commit `e103b78` — Vercel Production Ready ยืนยันแล้ว 2026-07-08)

### ที่มา
กัญจน์: "อยากให้งานทั้งหมดใน board B ติ๊กได้ว่าอยู่ phase ไหน เช่น รับฟังคำวิจารณ์" —
brainstorm เคาะ: ติ๊ก = **กรอง**, เฉพาะหน้า `/portal/jobs`, เปลี่ยนป้าย ⚪ "ระยะวางแผน"
→ "รับฟังคำวิจารณ์" (ตรวจ prod DB: ป้ายนี้มาจาก `province_tor_review*` ล้วน 56/253 แถว)
approve แล้วสั่ง "ทำให้หมดเลย เดี๋ยวฉันนอน" (spec `0e68f93`)

### สิ่งที่ทำ (client-side ล้วน — ไม่แตะ engine API / DB / ระบบส่ง LINE)
- `jobs/_client.tsx`: แถว chip กรอง stage ใต้ช่องค้นหา — นับจำนวนต่อ stage (เลขนิ่งจากงานทั้งหมด),
  ติ๊กหลายอัน=OR, ร่วมช่องค้นหา=AND, ไม่ติ๊ก=เห็นทั้งหมด, stage 0 งานไม่แสดง chip,
  ติ๊กอยู่=chip gold+✓ (aria-pressed), empty state แยกกรณีค้นหา/ติ๊ก
- ป้าย `pre` เปลี่ยนชื่อ 2 จุด: `jobs/_client.tsx` STAGE_LABEL + `world/_client.tsx` STAGE_META

### Verify (sanity = build + e2e จริง; ไม่แตะ DB → ไม่ต้อง Sophia)
- `npm run build` ผ่าน
- playwright e2e (uvicorn bms_api scratch :8123 `--ws none` + next start :3111 + cookie จริง):
  chip 3 อันเรียงถูก+เลขถูก (2/1/2, prelim/cancelled ไม่มีงาน=ไม่โชว์), ติ๊ก tor→2 งาน+"พบ 2 จาก 5",
  ติ๊กเพิ่ม won→3, ติ๊ก+ค้น "อาคาร"→1, ค้นนอก stage→empty state, เอาติ๊กออก→5 ครบ,
  world ไม่มีป้ายเก่าเหลือ — PASS
- เกร็ดเครื่อง dev: uvicorn+websockets เวอร์ชันชนกัน (`ServerProtocol` import fail) → รัน `--ws none`

### Followup
- ~~ยืนยัน Vercel deployment READY~~ ✅ Ready (Production) ยืนยัน 2026-07-08 เช้า

## งานที่ N+193: ทดลอง LightGBM ทำนาย %ส่วนลดประมูล — backtest (2026-07-10)

### สถานะ: ✅ เสร็จ (ผล: FAIL ตามเกณฑ์ที่ตั้งไว้ก่อนรัน — พับไว้ก่อน)

### สิ่งที่ทำ
- คุณกัญจน์เสนอไอเดียใช้ LightGBM ทำนายราคาที่ควรประมูล → ทำ offline backtest ก่อนตัดสิน (ไม่แตะ pipeline)
- ข้อมูล: winner_history.db งาน e-bidding + ราคา valid = 27,766 แถว (clean เหลือ 27,276; ตัด discount <0 หรือ >70)
- Time split จาก project_id prefix YYMM: train 21,780 (ก่อน ก.ค. 2566) / test 5,496 (หลัง)
- เทียบ 3 วิธี: global median / hierarchical median (dept×work_type×province, min n=5) / LightGBM (MAE objective + quantile p20/p80)
- สคริปต์: `scripts/probe_lightgbm_discount_experiment.py` → ผล `data/lightgbm_discount_experiment.json`

### ผล (MAE บน test, หน่วย = จุด% ของส่วนลด)
| วิธี | MAE | MedAE | MAE 2 จว.เป้าหมาย |
|---|---|---|---|
| global median | 13.24 | 12.74 | 13.43 |
| hier median | 10.52 | 7.82 | 10.94 |
| **LightGBM** | **9.78** | **7.13** | **10.13** |

- เกณฑ์ตั้งก่อนรัน: lgb_mae ≤ 0.90 × hier_mae → ได้ ratio **0.929 = FAIL** (ดีกว่า baseline แค่ ~7%)
- Quantile band p20-p80 กว้างเฉลี่ย 20 จุด% แต่ coverage แค่ 47.7% (เป้า 60%) — ช่วงที่ให้ยังใช้ตั้งราคาจริงไม่ได้
- Feature importance: log_budget > ym(เวลา) > mid_ratio > dept — work_type/province แทบไม่ช่วย (work_type ว่างเป็นส่วนใหญ่ทั่วประเทศ)

### บทเรียน / เหตุผลที่พับ
- ความคลาดเคลื่อน ±7-10 จุด% ใหญ่กว่า median ส่วนลด (12.5%) — ทุกวิธียังหยาบเกินใช้เคาะราคาจริง
- สอดคล้อง memory market-regime: ตัวขับส่วนลดจริงคือความเข้มการแข่งขัน/ระบอบหน่วยงาน ซึ่ง **ไม่มีใน feature set** (จำนวนผู้ยื่นอยู่ใน bid_results ที่ยัง coverage บาง)
- ทางฟื้นคืนชีพ: (1) backfill bid_results → ได้ feature จำนวนผู้ยื่น (2) backfill work_type (3) two-stage: จำแนกระบอบก่อนค่อย regress — ค่อยทำหลัง bid_results backfill (ทิศทางเดียวกับ B′ อยู่แล้ว)

### Followup
- ไม่มีงานบังคับ — revisit หลัง bid_results backfill มี coverage พอ

## งานที่ N+194: backfill bid_results → พบว่าเสร็จแล้ว 99% + LightGBM v2 PASS (2026-07-10)

### สถานะ: ✅ เสร็จ

### สิ่งที่ทำ / ค้นพบ
- กัญจน์สั่ง "เริ่ม backfill bid_results" → ตรวจก่อนพบว่า**รอบ fetch 22-24 มิ.ย. ทำไว้ครบแล้ว**:
  VPS bid_results = 240,727 แถว / 37,703 งาน ครอบคลุม competitive jobs ~99% ทั้ง 4 จังหวัด
  (นครพนม 8,615/8,686 · บึงกาฬ 4,468/4,497 · สกลนคร 10,625/10,751 · อุดร 13,985/14,111)
- เศษที่เหลือ ~340 งาน = error/empty เดิม (งานไม่ประกาศผล) — ไม่คุ้มไล่เก็บ
- แก้ความเข้าใจ v1: winner_history ไม่ใช่ "ทั่วประเทศ" — คือ 4 จังหวัดนี้เอง (นคพ/บก/สกล/อุดร)
- → ข้าม fetch, ทำ LightGBM v2 ทันที: export n_bidders/งาน จาก VPS (join ติด 99.3% ของ training set)
  เพิ่ม feature 2 แบบ: expected_n (ประวัติ dept×work_type×province — รู้ก่อนยื่น, ใช้จริงได้)
  vs n_bidders จริง (ceiling — leak, วัดเพดาน)

### ผล (MAE test 5,496 งาน, time split เดิมจาก v1)
| วิธี | MAE | MedAE | MAE 2 จว. |
|---|---|---|---|
| hier median (baseline) | 10.52 | 7.82 | 10.94 |
| lgb v1 (ไม่มี competition) | 9.78 | 7.13 | 10.13 |
| **lgb deployable (expected_n)** | **9.33** | **6.37** | **9.20** |
| lgb ceiling (n จริง — leak) | 8.06 | 4.54 | 8.32 |

- **deployable ratio = 0.886 ≤ 0.90 → PASS** (v1 = 0.929 FAIL) · ceiling 0.766
- ยืนยัน hypothesis: ความเข้มการแข่งขันคือ feature ที่ขาด; ช่อง deployable→ceiling (MedAE 6.37→4.54)
  = กำไรที่เหลือถ้าทำนาย "จำนวนคู่แข่ง" แม่นขึ้น (two-stage — งานถัดไปถ้าไปต่อ)
- สคริปต์ `scripts/probe_lightgbm_discount_experiment_v2.py` → `data/lightgbm_discount_experiment_v2.json`
  (n_bidders export: `data/_backfill_home/vps_n_bidders.csv` — ไม่ commit ตาม pattern โฟลเดอร์)

### Followup
- ตัดสินใจ: ต่อสาย quantile band ("ยื่นต่ำกว่า X ชนะ ~Y%") เข้าการ์ดราคา หรือทดลอง two-stage ก่อน — รอกัญจน์

## งานที่ N+195: ML discount band บนหน้างาน Board B (2026-07-10 → 11)

### สถานะ: ✅ **LIVE ครบ VPS+Vercel (2026-07-11 กัญจน์ confirm "push + deploy เลย")**
- push origin `3b58dbc..003890e` ✅
- VPS: backup pre_v139 (sqlite backup API 1.9G) → venv `pip install lightgbm` 4.6.0 → deploy.sh (pull ff → migrate v139 → restart bms-api active) ✅
- verify จริง 3 งาน: ml_band sane (อาคาร 15M → p80 10.5% / ถนน 2.3M → 32.8% ระบอบ local / ไฟฟ้า → 21.4% **โดยงานนี้ไม่มีตาราง winrate** = use case หลักทำงาน) + persist ลง price_predictions.ml_* โดยแถว B′ เดิม (area_disc_lo) ไม่ถูกแตะ ✅ health 200 ✅
- Vercel: deploy --prod ● Ready (build 49s) ✅

### ที่มา
กัญจน์เลือกทางเลือก 1 จาก N+194: ต่อสาย LightGBM quantile เข้าการ์ดราคา (ไม่ทำ two-stage ก่อน)
ตำแหน่ง: หน้า detail Board B `/portal/job/[pid]` ใต้ตาราง B′ (ไม่ใส่ LINE — quota+แก้ไม่ได้ / ไม่ใส่ Board A — กำลังเลิกใช้)

### สิ่งที่ทำ
- `6b3197d` engine: migration v139 (price_predictions +ml_* 6 คอลัมน์ แยกจาก area_* ของ B′)
  + `train_discount_band.py` (เทรน quantile p50/p80, refit ทั้งก้อนหลังหา best_iter, export data/models/ ~7MB เข้า git)
  + `discount_band.py` inference (fail-open ทุกทาง, gate 4 จังหวัด, dept map eGP→CGD exact→prefix→missing)
  + `save_ml_band` upsert เฉพาะ ml_* รับ conn caller ได้
- `a3bc145` portal+web: job_detail คำนวณสด+persist (try แยกชั้น) + key `ml_band` → MlBandCard ธีม B
  โชว์ได้แม้ไม่มีตาราง winrate (use case หลัก = งานที่ B′ ข้อมูลบาง)
- deviation จาก v2: production ตัด mid_ratio (ไม่มีราคากลางเก็บ) + district (geocode เพี้ยน 85%) + เพิ่ม agency
  → MAE ratio 0.922 (v2=0.886) แต่ **calibration ของคำที่ขึ้นการ์ดแม่น: bid@p80 → ชนะจริง 80.7%, bid@p50 → 50.8%**
  worst-case dept ไม่ map → 82.2% (เพี้ยนทางระวังเกิน = ปลอดภัยต่อคำเคลม)

### Sanity
- test_discount_band ใหม่ 7 ชุด + regression (portal_views/job_detail_api/routes/audit/price_prediction) + tsc — เขียวหมด
- Sophia ตรวจครึ่งแรก (ยืนยัน test ไม่เขียน DB จริง) แล้วโดน session limit — main thread ตรวจส่วนที่เหลือเอง:
  migration v139 idempotent (init_schema 2 รอบบน temp DB, คอลัมน์เก่าครบ), models ไม่ติด gitignore,
  write-on-read = single-row upsert ผ่าน conn caller บน WAL (pattern เดียวกับ notes)
- smoke ตัวเลขตรง domain: อบต.ถนน p50~30% (ระบอบ local) / กรมทางหลวง ~0.1% (central ชิดเพดาน)

### Deploy checklist (รอ confirm)
1. push origin (2 commits: 6b3197d, a3bc145)
2. VPS: `pip install lightgbm` (ใหม่!) → pull → migrate (v139) → restart bms-api → verify ml_band ใน /api/portal/job-detail
3. Vercel: deploy --prod
4. หลัง deploy: เปิดงานจริง 1-2 งานดูบรรทัดใหม่ + ตรวจ price_predictions.ml_* เริ่มมีค่า

### Followup
- closed-loop: พอ W0 มา actual_price เทียบ ml_price_p80 ได้เลย (คอลัมน์อยู่แถวเดียวกัน) — วัด calibration จริงหลังมีผลสัก 20-30 งาน
- ML band เทรนจาก snapshot 2026-07-10 — ควร retrain เป็นรอบ (เช่น รายไตรมาส) ยังไม่ตั้งอัตโนมัติ (YAGNI จนกว่าจะพิสูจน์คุณค่า)

## งานที่ N+196: Auto-competitor win-rate — เดาคู่แข่งอัตโนมัติบน Board B (2026-07-12)

### สถานะ: ✅ **LIVE บน VPS (2026-07-12 กัญจน์ confirm "deploy เลย")**
- push origin `afa62c3..b9ac36e` (7 commits) → VPS pull ff → restart bms-api active → health 200 ✅
- verify งานจริง 6 งาน (live DB, ต้อง BMS_DATA_DIR=/opt/bms/data): ทำนายครบทุกงาน —
  🟢 local 9-20 auctions + 🟡 อำเภอ 2 งาน, สนามใหญ่ p กระจายต่ำตามจริง (0.28-0.36), ไม่มี garbage ✅
- end-to-end งาน 69079051288 (งบ 2.277M, ยื่น -15%): โอกาสรวม 15% สมเหตุผล (คู่แข่ง attend ~94%
  beat-us 47-79%) + HTML มี string ใหม่ครบ ✅

### ที่มา
กัญจน์ขอ: เครื่องคำนวณโอกาสชนะบน Board B ไม่ต้องติ๊กชื่อคู่แข่งเอง — ระบบเดาเองว่า
"บริษัทไหนจะมา กี่ %" แล้วรวมเป็นโอกาสชนะเลย (ยังติ๊กออก/เพิ่มชื่อได้)
เลือกแนวทาง A: attendance-weighted Gates — P_eff = 1 − p_attend×(1−P_beat) เข้า gates_winrate เดิม

### สิ่งที่ทำ
- brainstorm + สำรวจโค้ด: form ปัจจุบัน `portal_views.py:532` → `calc_custom_winrate` (`cgd_intel.py:867`)
- spec: `docs/superpowers/specs/2026-07-11-auto-competitor-winrate-design.md`
  - p_attend = สัดส่วน auctions (recency-weighted) ที่บริษัทโผล่ จาก `_field_auctions` ladder เดิม (🟢→🟡→🟠)
  - threshold ≥0.15 cap 10 · clamp [0.05,0.95] · ข้อมูล < MIN_AUCTIONS → fallback ฟอร์มเดิม
  - ติ๊กจากกลุ่มทำนาย = ใช้ p ทำนาย · กลุ่มรอง/พิมพ์เพิ่ม = 1.0 · invariant: p_attend=1 ทุกตัว → เลขเดิมเป๊ะ
  - แตะ 3 ไฟล์ engine เท่านั้น (bid_field/cgd_intel/portal_views) — web/bms_api ไม่แตะ

### Implement (แผน: docs/superpowers/plans/2026-07-12-auto-competitor-winrate.md, commit a729278)
- `03efa6e` bid_field: `attendance_probs()` — ladder 🟢→🟡→🟠, recency-weighted appearance share,
  clamp [0.05,0.95], threshold ≥0.15, cap 10, fail-open → None + test_attendance.py 6 tests
- `ed1f88e` cgd_intel: `calc_custom_winrate(..., attend_probs=None)` → P_eff = 1−pa×(1−P) ก่อน Gates
  + breakdown key `attend_pct` · invariant attend=1.0 = เลขเดิมเป๊ะ (test บังคับ)
- `7c8d82f` cgd_intel: `_build_intel` แนบ `predicted_attendees` (population เดียวกับคาดราคา)
- `45fa77f` portal_views: job_detail ส่ง attend_probs + ฟอร์ม 2 กลุ่ม (คาดว่าจะมายื่น pre-tick +
  เจ้าอื่นในพื้นที่) + breakdown "โอกาสมา X% · ถ้ามา ชนะคุณ ~Y%" + fallback ฟอร์มเดิมเมื่อข้อมูลบาง

### Sanity
- regression 7 ไฟล์เขียวหมด: test_attendance / test_cgd_intel / test_winrate / test_winrate_grid /
  test_portal_views / test_portal_page / test_portal_jobs
- Sophia audit → **SAFE**: read-only ล้วน ไม่มี write path ใหม่, tests isolate (tempdir/in-memory),
  VPS live DB ไม่มีแถวเขียนใหม่หลัง N+195, invariant ยืนยันด้วยเทสจริง
- ⚠️ local data/bms_customers.db stale (2026-05-29) + bid_results ว่าง → verify กับงานจริงทำได้เฉพาะ
  บน VPS หลัง deploy (แบบเดียวกับ N+195)

### Deploy checklist (รอ confirm)
1. push origin (6 commits: spec/plan/4 code)
2. VPS: pull ff → restart bms-api (ไม่มี migration/dependency ใหม่) · Vercel ไม่ต้อง deploy
3. หลัง deploy: เปิดงานจริง 1-2 งานดูกลุ่ม "คาดว่าจะมายื่น" + กรอกราคาดู "โอกาสชนะรวม" + Σp_attend ≈ n_mean

### Followup
- closed-loop: พอ W0 มา เทียบรายชื่อที่ทำนาย vs ผู้ยื่นจริง (precision/recall) หลังมีผลสัก 20-30 งาน

## งานที่ N+197: ปุ่มติดตามจากหน้า "งานทั้งหมด" /portal/jobs (2026-07-12)

### สถานะ: ✅ LIVE ครบ VPS + Vercel

### ที่มา
กัญจน์: "ตรงดูงานทั้งหมด สามารถกดติดตามงานได้จากตรงนั้นเลย" — เดิมต้องเข้าหน้างานก่อน
spec: docs/superpowers/specs/2026-07-12-follow-from-all-jobs-design.md (approved "โอเค")

### สิ่งที่ทำ
- `655cfd5` engine: /api/portal/all-jobs เพิ่ม flag `followed` (query followed_jobs status='active'
  1 ครั้ง/request) + test seed followed active/unfollowed ใน test_portal_all_jobs_api.py
- `40c2a70` web: SentJob.followed + ปุ่ม 🔔 ติดตาม/ติดตามแล้ว บน SentJobCard (preventDefault กันเด้ง
  เข้า detail) + handleFollow optimistic Set + revert on fail (pattern world) — reuse POST /api/portal/follow เดิม
- ไม่มีปุ่มยกเลิกติดตามจากลิสต์ (YAGNI — world ก็ไม่มี)

### Sanity / Verify
- test_portal_all_jobs_api + test_portal_jobs เขียว · tsc ผ่าน
- deploy: VPS pull+restart health 200 · Vercel READY (build 57s, alias bid-master-dashboard.vercel.app)
- verify จริงบน VPS: ลูกค้า top-follower มี 59 งานในลิสต์ → followed=true 7 งาน ตรง DB active 7 แถวเป๊ะ
- เส้นกดติดตาม (POST /follow → _record_follow) เป็นของเดิมที่ live บน world อยู่แล้ว — ไม่ได้แตะ

### Followup
- (ไม่มี — feature ครบตาม spec)

## งานที่ N+197.1: ยกเลิกติดตามได้จากหน้า "งานทั้งหมด" (2026-07-12)

### สถานะ: ✅ LIVE ครบ VPS + Vercel

### ที่มา
กัญจน์: "เมื่อกดติดตามได้แล้ว ก็อยากให้ยกเลิกติดตามได้ด้วย" — ต่อยอด N+197
spec: docs/superpowers/specs/2026-07-12-unfollow-from-all-jobs-design.md

### สิ่งที่ทำ
- `729ed63` engine: POST /api/portal/unfollow (mirror follow, เรียก _record_unfollow เดิมของ Board A)
  + test toggle roundtrip: unfollow → followed=false/DB unfollowed → follow กลับ → true/active + 403/404
- `c35921b` web: relay route /api/portal/unfollow ใหม่ + ปุ่ม "ติดตามแล้ว" เลิก disabled →
  handleToggle optimistic สองทิศ (revert on fail) — ไม่มี confirm dialog (misclick กู้ได้ด้วยกดซ้ำ)
- เส้น follow เดิมไม่แตะ

### Verify
- test_portal_all_jobs_api เขียว · tsc ผ่าน · VPS health 200 · Vercel READY
- roundtrip จริงบน VPS (ลูกค้าจริง, งานเก่าไม่เคย follow): follow → active → unfollow → unfollowed
  ตรง DB ทุกขั้น (จบที่ unfollowed row เฉยๆ — ไม่กระทบ notification)
- gotcha ระหว่าง verify: .env บน VPS อ่านใน python ต้อง strip \r (CRLF) ไม่งั้น secret เพี้ยน → 403

### Followup
- (ไม่มี)

## งานที่ N+197.2: ยกเลิกติดตามจากบอร์ด "งานที่ติดตาม" หน้า world (2026-07-12)

### สถานะ: ✅ LIVE (Vercel — web-only, ไม่แตะ VPS)

### สิ่งที่ทำ
- `fb55d86` world/_client.tsx ไฟล์เดียว: TrackedJobCard เพิ่มปุ่ม "ติดตามแล้ว" แถวล่างขวา
  → กด = unfollow แต่**การ์ดคงอยู่** ปุ่มสลับเป็น "ติดตาม" (undo ในที่ กันกดพลาดการ์ดวูบหาย)
  → reload ครั้งถัดไปงานที่ unfollowed หายเอง (engine กรอง active อยู่แล้ว)
- state `unfollowed` Set + handleTrackedToggle optimistic สองทิศ — reuse เส้น follow/unfollow N+197.1
- spec: docs/superpowers/specs/2026-07-12-unfollow-world-tracked-design.md

### Verify
- tsc ผ่าน · Vercel READY (58s) · เส้นหลังบ้าน = ตัวที่ verify roundtrip จริงไปแล้วใน N+197.1

### Followup
- (ไม่มี) — ครบชุด follow/unfollow ทุกจุดที่โชว์สถานะติดตาม (world tracked + งานทั้งหมด)

## งานที่ N+198: "ไม่มีคีย์เวิร์ด = เห็นทั้งจังหวัด" + รัน clear_keyword_seed จริง (2026-07-12)

### สถานะ: ✅ LIVE + apply แล้ว (ปิดหนี้ค้างจาก N+185)

### ที่มา
กัญจน์ถามว่า "งานใหม่ที่แมตช์" กรองจากไหนทั้งที่สั่งให้ตั้งไม่มีคีย์เวิร์ดแล้ว → ตรวจพบ
`clear_keyword_seed --apply` ไม่เคยรันบน prod (ค้าง N+185) ทุกบัญชียังแบก seed 89 คำจาก N+181
และรันเฉยๆ ไม่ได้เพราะโค้ด discover เดิม "ไม่มี keyword → คืนว่าง"

### สิ่งที่ทำ
- `a51b9cc` semantic ใหม่ (board discovery เท่านั้น): keywords ว่าง = ไม่บังคับคำ เห็นทั้งจังหวัด
  (`discovery_match.py` gate เฉพาะเมื่อมีลิสต์ + `bms_api.py` เลิก short-circuit) — จังหวัด/negative/
  งบ/followed/deadline กรองเหมือนเดิม; บัญชีมี keyword พฤติกรรมเดิมเป๊ะ
- tests: no-keyword เห็นทั้งจังหวัด + negative/budget/province ยังตัด + UNOKW เคส endpoint เต็ม
- ops: backup DB 1.86GB (/opt/bms/backups/bms_customers_pre_clear_seed_20260712_070329.db)
  → dry-run 5 customer → `--apply` → classes ว่างครบทั้ง 4 บัญชี active

### Verify
- test_discovery_match / test_portal_discover_api / test_clear_keyword_seed / test_portal_all_jobs_api เขียว
- VPS health 200 · discover ของ Kan Kan: biddable 3 + planning 6 ทั้งจังหวัด chips ว่าง
  (มีงานไฟฟ้าเคเบิลใต้ดินที่ seed เดิมเคยตัด) · LINE pipeline ไม่ถูกแตะ

### Followup
- เหลือเช็คจาก N+185: LINE OA paid upgrade + cron recap 23:00 (clear_keyword_seed ปิดแล้ว)

## งานที่ N+198.1: fix regression — "พื้นที่ครอบคลุม = 0" หลังเคลียร์ seed (2026-07-12)

### สถานะ: ✅ LIVE ครบ VPS + Vercel

### Root cause
กัญจน์เจอเอง: การ์ด "พื้นที่ครอบคลุม" หน้า world นับจังหวัดจาก notes.classes[].geo.provinces
(ถูกเคลียร์เป็น [] ใน N+198) ไม่ใช่จาก subscription_provinces ที่แจ้งเตือนจริง → โชว์ 0 ทั้งที่
subscribe 2 จังหวัด + เงื่อนไข hasPrefs ยังบังคับ totalKeywords>0 (ขัด semantic ใหม่ N+198
— จะโชว์กล่อง "ไปตั้งค่า" แทนงาน)

### Fix (`47fee58`)
- engine /api/portal/customer เพิ่ม field `provinces` จาก subscription_provinces (source of truth)
- web: Customer.provinces → world นับ provincesCount = union(subscription, classes) +
  hasPrefs = มีพื้นที่ก็พอ (เลิกบังคับคำค้น)

### Verify
- test_portal_discover_api (+เคส provinces) + test_set_customer_tier เขียว · tsc ผ่าน
- VPS: customer API ของ Kan Kan คืน provinces ['นครพนม','บึงกาฬ'] · Vercel READY

### Lesson
เคลียร์ค่า config ที่ UI derive ต่อ — ต้อง grep ทุกจุดที่อ่านค่านั้นก่อน apply (คราวนี้เช็คแค่
discover endpoint ไม่ได้เช็ค SumCard/hasPrefs ฝั่ง client)

### N+198.2 (ต่อเนื่อง — กัญจน์ขอ)
- `77add25` การ์ด Keywords: ไม่มีคำค้น → โชว์ "ทั้งจังหวัด" แทนเลข 0 (+SumCard ย่อ font เมื่อ value เป็นคำ)
  — Vercel READY (web-only)

## งานที่ N+199: หน้า "ตั้งค่า" แบน แทนระบบบริษัท (2026-07-12)

### สถานะ: ✅ LIVE (Vercel — web-only)

### ที่มา
กัญจน์: แถบ "บริษัท" → "ตั้งค่า" + ถอดระบบบริษัท (เพิ่มขั้นตอนเกินจำเป็น; กดการ์ดพื้นที่ครอบคลุม
แล้วเจอหน้าให้เพิ่มบริษัทก่อน = ใช้ไม่ได้)

### สิ่งที่ทำ (`5444720` — ลบ 1,173 บรรทัด เพิ่ม 194)
- หน้าใหม่ `/portal/settings`: พื้นที่ครอบคลุม (chips จาก customer.provinces, read-only + "แจ้ง
  Sebastian เพื่อเปลี่ยน") · คำค้น (chips เพิ่ม/ลบ, ว่าง = ทั้งจังหวัด) · ช่วงงบ (บาท, 0 = ไม่จำกัด)
- Data shape เดิม: เซฟเป็น hidden class เดียว `notes.classes[0]` (id='settings') — engine
  `_classes_from_notes` อ่านต่อทันที ไม่แตะ matching; ว่างหมด → `classes: []`
- nav "บริษัท"→"ตั้งค่า" (GearIcon) · world ตัดการ์ด "บริษัทของฉัน" + การ์ดพื้นที่/Keywords ชี้ settings
- `/portal/classes` → redirect settings · ลบ classes/_client.tsx (1,138 บรรทัด) · company-stats ชี้ settings

### Verify
- tsc + next build ผ่าน (route ครบ) · Vercel READY · smoke: /portal/settings → 307 login (auth ทำงาน),
  /portal/classes → 307 /portal/settings

### Followup
- แผน "phase-B category tick UI" (spec DRAFT 2026-07-01) **ตกยุคแล้ว** — ระบบบริษัท/หมวดถูกถอด
  ตามทิศทางใหม่ของกัญจน์ (ตั้งค่าแบน + default ทั้งจังหวัด)
- จังหวัด read-only — เปิดให้ลูกค้าแก้เองเมื่อ product นิ่งขึ้น (ตอนนี้แจ้งผ่านแอดมิน)

### N+199.1 (ต่อเนื่อง — กัญจน์ทดลองแล้วโอเค + ขอเพิ่ม)
- `2b5a0a5` การ์ดที่ 4 ในหน้าตั้งค่า: Toggle SME / MIT + เวลาแจ้งเตือน (เก็บ notes root:
  isSME/isMIT/notifyTime — ตัวแก้เดิมตายไปพร้อม classes/_client) + โปรไฟล์ filter hidden class
  id='settings' ออกจากการ์ดบริษัท (กันโผล่เป็นบริษัทปลอม) — Vercel READY

## งานที่ N+200: เวลาแจ้งเตือนมีผลจริง — daily recap ตาม notifyTime ของลูกค้า (2026-07-12)

### สถานะ: ✅ LIVE (VPS + Vercel) — รอดูรอบส่งจริงคืนนี้ 20:00

### ที่มา
กัญจน์: "ต่อสายให้เลย ให้เวลาแจ้งเตือนมีผลจริง" — ช่องเวลาในหน้าตั้งค่า (N+199.1) เดิมเซฟได้
แต่ recap ยิงเวลาเดียวทั้งระบบ (timer 23:00 ไทย ตัวเดียว)

### สิ่งที่ทำ (`5ad6d16`)
- schema v1.40: `daily_recap_log(customer_id, date_th, sent_at)` marker กันส่งซ้ำ
- `Sebastian_Daily_User_Summary.py`: due-mode (default) — `is_due` = now ≥ notifyTime (จาก notes,
  default 20:00) AND ยังไม่ mark วันนี้ → self-healing ถ้า timer พลาดรอบ; `--all` = manual ส่งทุกคน
- **ฉบับเช้า** (notifyTime ก่อนเที่ยง): สรุปงาน "เมื่อวาน" + เปิดยื่นซอง/โน้ต "วันนี้"
  (ฉบับเย็นเดิม: วันนี้ + พรุ่งนี้) — กันข้อความ "วันนี้ยังไม่มีงาน" ตอน 6 โมงเช้าที่ผิดกาล
- timer: 23:00 เดียว → ทุก 15 นาที (OnCalendar *:00/15 Asia/Bangkok, Persistent)
- web: default เวลาแจ้งเตือน 06:00 → 20:00 ทั้ง settings/profile/world (ตรง engine)

### Verify
- test_daily_recap 6 ชุดเขียว (notify_time parse / is_due+marker / morning variant) + regression
- VPS: backup pre_v140 (1.86GB) → migrate → dry-run จริง: ลูกค้า 4 คน default 20:00, [14:54] due 0/4
  ถูกต้อง · timer ใหม่ next fire 15:00 ไทย · health 200 · Vercel READY
- ปิดหนี้ N+185 อีกข้อ: "cron recap 23:00" — แทนด้วยระบบ per-customer แล้ว

### N+200.1 (ต่อเนื่อง — กัญจน์ขอ)
- `9501608` default เวลาสรุป 20:00 → **23:00 ทุกคน** (engine DEFAULT_NOTIFY + web fallback 3 หน้า)
  — deploy VPS+Vercel แล้ว; timer อ่านสคริปต์สดทุกรอบ ไม่ต้อง restart อะไร

### Followup
- คืนนี้ 23:00 รอบส่งจริงรอบแรก (ทุกคน default 23:00 + กัญจน์ตั้งเอง 23:00) — สคริปต์
  Discord-notify เองอยู่แล้ว ("📋 Daily recap ... ส่ง X/Y")
- เหลือจาก N+185: LINE OA paid upgrade (quota 300) อย่างเดียว
