# Bid Master System — Progress Log

> เก็บเฉพาะ entry ล่าสุด (~20 อัน). entry เก่ากว่านี้อยู่ใน progress_log_archive.md


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

## งานที่ N+201: เวลาแจ้งเตือนตอนเช้าตั้งเองได้ (bidopen + timeline) (2026-07-12)

### สถานะ: ✅ LIVE (VPS + Vercel)

### ที่มา
กัญจน์: "พวกที่แจ้งเตือนตอน 7:30 อยากให้ตั้งค่าเวลาได้ด้วย" — เดิม bidopen-morning (07:00) +
timeline-reminder (07:30) ยิงเวลาตายตัว. เลือกช่องเดียวคุมทั้งคู่ (approve "โอเค ลุยเลย")

### สิ่งที่ทำ (`2894962`)
- schema v1.41: `daily_notify_log(kind, customer_id, date_th)` marker generic
- `notify_schedule.py` ใหม่ (helper กลาง): pref_time / is_due / mark_sent — DEFAULT_MORNING 07:30
- BidOpen_Morning + timeline_reminder: due-mode per-customer `morningNotifyTime` + `--all`;
  due แต่ไม่มี content = mark เฉยๆ (คง one-shot/วัน — ไม่มี late send แปลกๆ)
- timers 2 ตัว → ทุก 15 นาที · settings เพิ่มช่อง 🌅 เวลาแจ้งเตือนตอนเช้า + 🌙 เวลาสรุป (มี hint)
- **deploy-day guard:** seed marker วันนี้ให้ 4 ลูกค้า ×2 kinds ก่อนรอบ 15:30 — กันแจ้งซ้ำตอนบ่าย
  (เช้านี้ timer เก่าส่งไปแล้ว) → dry-run ยืนยัน due 0/4 ทั้งคู่
- fix แถม: test_bidopen_notify assert copy เก่า ("เจองานที่เกี่ยวกับคุณ/เปิดประมูล") พังค้างมาก่อน
  — ปรับตรง copy จริง

### Verify
- test_notify_schedule (ใหม่ 3 ชุด) + test_timeline_reminder + test_bidopen_notify + test_daily_recap
  เขียวหมด · tsc ผ่าน · VPS migrate v141 + timers ใหม่เดิน · Vercel READY

### N+201.1 (ต่อเนื่อง — กัญจน์ขอ)
- `50c24a5` หน้าตั้งค่า section คำค้น: chips หมวดสำเร็จรูป 12 หมวด (DEFAULT_KEYWORDS_BY_CLASS
  เดิมจากระบบบริษัท — ไม่เคยถูกลบ อยู่ใน portal-data.ts) กดหมวด = เพิ่มคำทั้งชุด / กดซ้ำ = เอาออก
  — Vercel READY (web-only)

### Followup
- พรุ่งนี้ 07:30 = รอบ per-customer แรกของแจ้งเตือนเช้า (recap คืนนี้ 23:00)

## งานที่ N+202: Design — Web Push notification บอร์ด B (2026-07-13/14)

### สถานะ: ✅ design approved / 🚧 รอ implementation plan

### บริบท / Root cause
- LINE push quota เต็ม 300/300 รอบ 2 (24 มิ.ย. + 13 ก.ค. — ใช้หมดใน 13 วัน ~23 msg/วัน, ยังไม่ได้ upgrade ตามแผน 1 ก.ค.)
- ตรวจแล้ว**ไม่มีงานพลาดส่ง**: backlog มิ.ย. เก็บตกครบโดย digest 1 ก.ค., เดือนนี้ send ล่าสุด 13 ก.ค. 19:16 สำเร็จ — งานถัดไปจะเป็นตัวแรกที่ fail
- กัญจน์เลือกไม่ upgrade → เพิ่ม Web Push (VAPID, self-hosted) เป็นช่องแจ้งเตือนของบอร์ด B

### Decision (approve ครบ 5 ส่วน)
- ช่วงทดลอง**ส่งคู่** LINE+browser, สถานะคิวยึด LINE เดิมเป๊ะ, webpush log แยกตาราง (ห้ามปน delivery_log — backlog digest อ่านอยู่)
- เนื้อหาครบทุกประเภทเหมือน LINE (รวม BidOpen_Morning + Daily_Digest ที่ยิงตรง)
- เริ่มที่กัญจน์คนเดียว → เกณฑ์เสถียร = 3 วันติด 0 งานหลุด → ค่อยชวนลูกค้า → ค่อยตัด LINE (เฟสหลัง)
- Spec: docs/superpowers/specs/2026-07-13-web-push-notification-design.md

### Followup
- เขียน implementation plan (writing-plans) → implement
- หมายเหตุ session: มีการแก้ bms_api.py all-jobs filter (sent→sent+failed) แล้ว revert ตามคำสั่งกัญจน์ — ทางแก้นั้นถูกแทนด้วยแผน Web Push นี้

## งานที่ N+203: Web Push แจ้งเตือนผ่าน browser บอร์ด B — LIVE (2026-07-14)

### สถานะ: ✅ deploy ครบ / 🚧 รอ E2E มือกัญจน์ + นับ 3 วันเสถียร

### สิ่งที่ทำ (Subagent-Driven, 11 commits b8b6bb2..69f2fcf, ทุก task ผ่านรีวิว)
- ตาราง `push_subscriptions` + `webpush_delivery_log` (แยกจาก delivery_log เด็ดขาด — backlog digest ไม่กระทบ)
- `scripts/webpush_send.py` ไม่ raise เด็ดขาด, 404/410 → disable อัตโนมัติ, kill switch `BMS_WEBPUSH_DISABLED=1`
- Mirror ที่ choke point `send_line_push/flex` → ทุกข้อความ (รวม BidOpen_Morning/Daily_User_Summary/timeline/Backlog ที่ยิงตรง) ได้ browser push อัตโนมัติ **รวมตอน LINE 429**; LINE logic byte-identical
- Engine: `POST /api/portal/push-subscribe|push-unsubscribe|push-test` (X-BMS-Secret)
- บอร์ด: `/sw.js` + manifest + icons + การ์ด 🔔 บน /portal/world + relay routes (allowlist ช่วงทดลอง = กัญจน์ Ua0d90e8…)
- Final review (fable): READY TO DEPLOY หลังแก้ H1 — **กัน browser เด้งซ้ำตอนคิว retry** (mirror เฉพาะ retry_count=0, `b34ab64`)
- Deploy-time fix: Basic Auth middleware บล็อก /sw.js (401) → ยกเว้น sw.js/manifest/icons ใน matcher (`69f2fcf`)

### Deploy + sanity
- VPS `69f2fcf` synced, pywebpush ใน venv, VAPID keys ใน .env, init_schema แล้ว (ตารางขึ้นครบ), bms-api + line-sender.timer active, sender log สะอาด
- Vercel prod READY + env NEXT_PUBLIC_VAPID_PUBLIC_KEY + PUSH_ALLOWLIST; sw.js/manifest/icons = 200 สาธารณะ
- Sanity: queue duplicates=0, delivery_log 465 rows (LINE เท่านั้น ไม่มีอะไรใหม่แตะ), webpush subs/log = 0 (รอ subscribe แรก)

### Followup
- กัญจน์: เปิด https://bid-master-dashboard.vercel.app/portal/world (มือถือ+คอม) → กดการ์ด 🔔 → "ส่งทดสอบ" ต้องเด้ง ~5 วิ
- เกณฑ์เสถียร 3 วัน: ทุก queue item ของ user ที่มี subscription ต้องมีแถว webpush_delivery_log (เทียบ customer+project+วัน) = 0 งานหลุด → ค่อยชวนลูกค้า (แก้ PUSH_ALLOWLIST) → ค่อยตัด LINE (เฟสหลัง)
- Minor debt (final review: defer ได้): sw.js ไม่มี skipWaiting, push-test blocking ใน async (พอ scale), negative test cross-customer unsubscribe

## งานที่ N+203.1: หน้า "งานทั้งหมด" จัดกลุ่มต่อวัน (2026-07-15)

### สถานะ: ✅ เสร็จ

### สิ่งที่ทำ
- กัญจน์ขอ: แยกงานเป็นช่วงต่อวัน (วันนี้ / เมื่อวาน / วันเก่า) ให้กวาดตาง่าย — เลือกแบบ "หัวข้อคั่นวัน" จาก mockup 2 แบบ
- `dashboard/web/src/app/portal/jobs/_client.tsx`: จัดกลุ่มด้วย sent_at (เวลาไทย, en-CA key), หัวข้อ 📅 วันนี้/เมื่อวาน/วันที่ไทย + จำนวนงาน + เส้นคั่น; ทำงานร่วมค้นหา+ติ๊กกรอง stage เดิม (กรองก่อนแล้วค่อยจัดกลุ่ม); client-side ล้วน ไม่แตะ API
- tsc + build ผ่าน

### Followup
- (ยังค้างจาก N+203) E2E web push มือกัญจน์ + 3 วันเสถียร

## งานที่ N+204: E2E web push ผ่าน — เริ่มนับ 3 วันเสถียร (2026-07-21)

### สถานะ: ✅ E2E ผ่าน / 🚧 เริ่มนับ 3 วันเสถียร

### สิ่งที่ทำ
- กัญจน์กดการ์ด 🔔 บน `/portal/world` (iPhone Safari, iOS 18.7) → อนุญาต notification → กด "ส่งทดสอบ"
- ตรวจ VPS DB ตรงๆ ยืนยันไม่ใช่แค่เห็นแจ้งเตือนเฉยๆ:
  - `push_subscriptions`: 1 แถว, customer_id=2, created_at 2026-07-21T01:27:06+07:00, last_ok_at 01:27:10 (ไม่มี disabled_at)
  - `webpush_delivery_log`: 1 แถว, status=`sent`, attempted_at 01:27:10, ไม่มี error
- สรุป: subscribe + ส่งทดสอบสำเร็จจริงทั้งสาย (browser → engine → VPS DB)

### Followup
- นับ 3 วันเสถียรตั้งแต่ 2026-07-21: ทุก queue item ของ customer_id=2 ต้องมีแถวคู่กันใน `webpush_delivery_log` ครบ (0 งานหลุด) ก่อนเปิด `PUSH_ALLOWLIST` ให้ลูกค้าอื่น + ค่อยพิจารณาตัด LINE
- Minor debt เดิมยังไม่แก้ (defer ได้): sw.js ไม่มี skipWaiting, push-test blocking ใน async, negative test cross-customer unsubscribe

## งานที่ N+205: บอร์ด "งานทั้งหมด" เลิกผูกกับผลส่ง LINE — รับตรงจากสแกน+จับคู่ (2026-07-21)

### สถานะ: ✅ เสร็จ (แก้ local, Sophia SAFE — รอ deploy)

### Root cause (สืบจากคำถามกัญจน์ "ทำไม board ไม่เพิ่มงาน")
- ตรวจ VPS DB พบ `/api/portal/all-jobs` filter เดิม `nq.status='sent'` เท่านั้น → บอร์ดค้างที่แถวสำเร็จล่าสุดของกัญจน์ (customer_id=2) = **2026-07-13T17:15:45** พอดี ตรงกับวันที่ LINE โควต้าเต็ม (300/300) — ตั้งแต่นั้น queue เข้าปกติทุกวันแต่ `status='failed'` (429 rate_limit) หมด บอร์ดเลยไม่โชว์อะไรใหม่เลย ทั้งที่ discovery/matching ทำงานถูกต้อง (ยืนยันแยกกับคำถามก่อนหน้าเรื่อง egp ปิดปรับปรุง 18-19 ก.ค.)
- กัญจน์สั่ง: แก้ให้บอร์ดรับจากการสแกนงานโดยตรง ไม่ผูกกับ LINE, จะเปลี่ยนไปพึ่งบอร์ดเป็นช่องหลักแทน

### Fix (subagent-driven: Sophia sanity audit หลังแก้)
- `scripts/bms_api.py` `portal_all_jobs_json`: `nq.status='sent'` → `nq.status!='cancelled'` (โชว์ sent+failed, กันเฉพาะ queue row ที่ถูก dedup/invalidate ทิ้งจริง — คนละความหมายกับ `source_stage='followed_cancelled'`)
- `scripts/test_portal_all_jobs_api.py`: เพิ่มเคส P6 (`status='cancelled'` → ไม่ขึ้น), แก้ P3 (`failed` → ต้องขึ้น) — PASS
- `dashboard/web` `_client.tsx` + `portal-all-jobs.ts`: แก้ copy "ส่งเมื่อ"/"ระบบเคยส่งให้"/"ส่งใน LINE" → "พบเมื่อ"/"ระบบพบและจับคู่ให้" (timestamp ไม่ได้แปลว่าส่งสำเร็จอีกต่อไป) — tsc ผ่าน

### Sophia audit → SAFE
- customer scoping/dedup ไม่พัง, test_data 0 แถวทั้ง DB (ไม่มีหลุด), ไม่มี `pending` ค้าง, ไม่มี endpoint อื่นพึ่ง query เดิมตกหล่น
- ตัวเลขจริง VPS customer_id=2: เดิม (sent) 58 งาน → ใหม่ (!=cancelled) **74 งาน** (+16 จาก failed ที่ค้างมาตั้งแต่ 24 มิ.ย.)
- พบ 1 แถว `status='cancelled'` จริงบน VPS (id=54, ไม่มี writer โค้ดไหนตั้งค่านี้ในระบบ — คาดว่าถูกแก้มือครั้งเดียว) ไม่กระทบ filter ใหม่

### Deploy — ✅ ครบ (commit f45971d)
- push origin/main สำเร็จ
- VPS: git pull fast-forward 69f2fcf→f45971d, restart bms-api (active, /health 200)
  verify in-process: `portal_all_jobs_json` customer_id=2 คืน **count=74** จริง (รวม 3 งาน 07-19/20 ที่เคย failed)
- Vercel: `npx vercel deploy --prod` → READY, alias bid-master-dashboard.vercel.app

### Followup
- decision "เปลี่ยนไปใช้ board ล้วน" (ลดพึ่ง LINE) — บันทึกไว้เป็นทิศทางใหม่ ยังไม่ได้ตัด LINE จริง (LINE quota คาดรีเซ็ต ~1 ส.ค.)
- แนะนำกัญจน์เปิด `/portal/jobs` เช็คด้วยตาว่าจำนวนงานเพิ่มขึ้นจริงตามที่คาด (74 งาน)

## งานที่ N+206: พลิกกลับ N+198 — ไม่ตั้ง keyword ส่วนตัว = ไม่มีงานแมตช์เลย (2026-07-21)

### สถานะ: ✅ เสร็จ (แก้ local, Sophia SAFE — รอ deploy)

### บริบท (สืบจากคำถามกัญจน์ "ทำไมมันแมตช์งานทั้งที่ไม่ได้ใส่ keyword")
- อธิบายผิดรอบแรกว่า global keyword config (`config/matching_preferences.json`, ~90 คำ, whole_provinces mode ตั้งไว้ 27 มิ.ย.) คือของตั้งใจ — กัญจน์แก้ความเข้าใจ: คำกลางมีไว้ให้ **ติ๊กเลือกเป็น personal keyword** ไม่ใช่ auto-apply ทุกคน
- สืบพบ 2 ระบบแยกกัน: (A) `/api/portal/discover` (per-user, อ่าน `customers.notes.classes[].keywords` จริง) (B) `/api/portal/all-jobs`+LINE queue (global config, ไม่อ่าน personal keyword เลย) — ทั้งคู่มี policy เดิม (N+198) "ไม่ตั้ง keyword = เห็นทั้งจังหวัด" เหมือนกัน
- กัญจน์ยืนยันชัดเจน (ถามย้ำก่อนแก้เพราะกระทบผู้ใช้จริง): **ต้องการพลิกเป็น "ไม่ตั้ง keyword = ไม่มีงานแมตช์เลย" ทั้งระบบ** แม้รู้ว่าลูกค้า active ทั้ง 4 คน (กัญจน์/ณฐมน/Mr.suvit/อัญธิญาน์) **ไม่มีใครตั้ง keyword ไว้เลย** → ผลคือทุกคนจะไม่ได้รับแจ้งเตือนจนกว่าจะเข้าไปตั้งเอง

### ⚠️ ประวัติสำคัญที่ต้องแยกให้ชัด (กันสับสนกับ N+184)
N+184 (ก.ค. 2026) เคยถอด "enforce-cut" (global keyword ตัดสิน cut แล้วไม่ enqueue) ออกเพราะเป็นสาเหตุอินซิเดนต์ใหญ่ (งานก่อสร้างจริงหายเงียบหลายสัปดาห์) — งานรอบนี้**ไม่ได้แตะ enforce-cut/match_job เดิมเลย**, เป็น gate ใหม่คนละชั้น (personal keyword ต่อลูกค้า) `test_province_no_cut.py` ยัง PASS ยืนยันว่า global cut ไม่กระทบ enqueue เหมือนเดิม

### Fix (TDD, Sophia sanity audit ก่อน commit)
- `scripts/customer_keywords.py` (ใหม่): `keywords_from_notes()` — single source parse personal keyword จาก `customers.notes.classes[]` (เดิมมี logic ซ้ำกันคนละที่ระหว่าง bms_api.py/discovery_match.py จนพฤติกรรมไม่ตรงกัน)
- `scripts/discovery_match.py::match()`: ว่าง keywords → return False ทันที (เดิม return True/match ทุกอย่าง)
- `scripts/Sebastian_Customer_DB.py::enqueue_notifications()`: เพิ่ม param `keyword_gate=False` (default ไม่เปลี่ยนพฤติกรรมเดิม) — `True` เพิ่ม `c.notes` เข้า SELECT + เช็คทีละลูกค้า ไม่มี keyword หรือไม่ hit ชื่องาน → skip ไม่ enqueue
- `scripts/Sebastian_Enrichment_Worker.py`: เปิด `keyword_gate=True` 4 จุด (TOR/B0, province_qualified, RSS Pass1 `api_enriched`, RSS Pass2 `repair_pass2`) — **ไม่แตะ** `Sebastian_Winner_Poller.py`'s `enqueue_for_customer()` (followed_winner/prelim/cancelled = opt-in follow อยู่แล้ว ไม่ควรมี gate)
- `scripts/bms_api.py::_classes_from_notes`: refactor ให้เรียก `customer_keywords.keywords_from_notes()` (ลด duplicate)
- Frontend (`portal/settings/_client.tsx`, `portal/world/_client.tsx`): แก้ copy เดิมที่บอก "ไม่ตั้งคำค้น=เห็นทั้งจังหวัด" ให้ตรง policy ใหม่ + `hasPrefs` ต้องมี `totalKeywords>0` ด้วย

### Test (7/7 PASS — Sophia รันซ้ำเองยืนยัน)
- ใหม่: `test_customer_keywords.py`, `test_keyword_gate_no_personal_kw.py` (3 เคส: ไม่ตั้ง→ไม่ enqueue / ตั้งไม่ตรง→ไม่ enqueue / ตั้งตรง→ enqueue)
- แก้: `test_discovery_match.py`, `test_portal_discover_api.py` (พลิก assertion policy เก่า), `test_province_no_cut.py` (เพิ่ม `_set_keywords()` แยก gate ใหม่ออกจาก enforce-cut เดิม)

### Sophia audit → SAFE
- `enqueue_notifications(` ทั้ง repo = 4 call sites ครบทุกจุดมี `keyword_gate=True`; `seed_self_notify.py` (เรียกไม่มี gate) ยืนยันเป็น dev harness ไม่ใช่ prod cron path
- `enqueue_for_customer()` แยกโค้ดจริง ไม่ได้ถูกแตะ (Winner_Poller 3 จุดยังทำงานปกติ)
- `job_matcher._kw_hit` guard เดียวกันทั้ง global/personal keyword (กัน "ท่อ" ชน "ท่องเที่ยว" เหมือนเดิม)
- นับจริง VPS: **4/4 active customers = 0 keyword ตั้งไว้** (ตรงตัวเลขที่อ้าง) → deploy แล้วทุกคนจะไม่ได้รับแจ้งเตือนจนตั้ง keyword เอง
- py_compile + tsc ผ่านหมด, แก้คอมเมนต์ตกค้าง `bms_api.py:1637` (เดิมยังอ้าง N+198)

### Deploy — ✅ ครบ (commit c614252)
- push origin/main สำเร็จ, VPS pull fast-forward f45971d→c614252, restart bms-api (active, /health 200)
- bms-enrichment-worker.service เป็น `oneshot` — รอบถัดไปอ่านโค้ดใหม่เองอัตโนมัติ ไม่ต้อง restart
- Vercel deploy --prod → READY
- Verify จริงบน VPS: `/api/portal/discover` customer กัญจน์ (ไม่มี keyword) → `{biddable: [], planning: []}` ตรงตามคาด

### 🐛 พบบั๊กแยกต่างหาก (ไม่เกี่ยว N+206, ยังไม่แก้)
รัน test บน VPS ตอน deploy พบ `test_portal_discover_api.py` fail ที่ assertion B0/planning (`plan_ids == {'B_FRESH'}` ได้ `set()`) — สืบแล้วเป็นบั๊ก **timezone boundary ใน `job_matcher.tor_is_fresh()`**: ใช้ `date.today()` (system, UTC บน VPS) เทียบกับ timestamp ที่ระบบ stamp เป็นเวลาไทย (+07:00) — ช่วง 17:00-23:59 UTC ทุกวัน (=00:00-06:59 เวลาไทย) วันที่ไทยจะ "ล้ำหน้า" UTC ไป 1 วัน ทำให้ `tor_is_fresh` คำนวณ diff ติดลบ → ถือว่า "ไม่ fresh" ทั้งที่เพิ่งประกาศวันนี้จริง
- **ผลกระทบจริง:** งาน B0 (รับฟังคำวิจารณ์) ที่เพิ่งประกาศ จะหายจาก section "งานใหม่ที่แมตช์" (planning) ในช่วงเวลาดังกล่าวทุกวัน (ไม่กระทบ D0/biddable)
- **ไม่ได้แก้ในรอบนี้** (นอก scope N+206, ไม่ได้แตะโค้ดจุดนี้เลย) — บันทึกไว้เป็นบั๊กแยกรอ priority ถัดไป

### Followup
- **สำคัญ:** ต้องแจ้ง Mr.suvit/ณฐมน/อัญธิญาน์ (LINE reply ฟรีไม่ติด quota) ให้เข้าไปตั้ง keyword ที่ `/portal/settings` เอง ไม่งั้นจะไม่ได้รับแจ้งเตือนอะไรเลยตั้งแต่วันนี้เป็นต้นไป

## งานที่ N+206.1: fix `tor_is_fresh` timezone boundary bug (2026-07-21)

### สถานะ: ✅ เสร็จ

### Debug mantra (reproduce → fail path → falsify → breadcrumb)
- **Repro:** `test_portal_discover_api.py` PASS บน local (~02:00 ไทย) แต่ FAIL บน VPS ตอน deploy N+206 (assertion B0/planning `plan_ids=={'B_FRESH'}` ได้ `set()`) — เวลานั้น VPS = 19:37 UTC (=02:37 ไทย)
- **Fail path:** source trace `job_matcher.tor_is_fresh()` → `today = _dt.date.today()` (system local, ไม่ผูก timezone) เทียบกับ `announce_date`/`first_seen_at` ที่ระบบ stamp เป็นเวลาไทย (+07:00) เสมอ
- **Root cause:** VPS OS timezone = `Etc/UTC` (ยืนยันด้วย `timedatectl`) — ช่วง 17:00-23:59 UTC ทุกวัน (=00:00-06:59 น. ไทย) วันที่ไทย "ล้ำหน้า" UTC 1 วัน → `(today_UTC - announce_date_ไทย).days` ติดลบ → `tor_is_fresh` คืน False ผิด ทั้งที่งานประกาศวันนี้จริง
- **Falsify:** คำนวณมือยืนยัน (`today_UTC=2026-07-20, ad=2026-07-21` → diff=-1 → False) + ยืนยันด้วย fix (Thai-tz aware) → diff=0 → True — ตรงสมมติฐาน 100%
- **Disprove จริง:** เขียน `test_tor_is_fresh_timezone.py` (mock `datetime.datetime`+`datetime.date` จำลอง VPS) → `git stash` revert fix ชั่วคราว → test FAIL ตามคาด (AssertionError) → restore fix → PASS. พิสูจน์ว่า test จับบั๊กได้จริง ไม่ใช่ test หลอกผ่าน

### Fix
- `scripts/job_matcher.py::tor_is_fresh()`: default `today` resolution เปลี่ยนจาก `_dt.date.today()` → `_dt.datetime.now(_dt.timezone(_dt.timedelta(hours=7))).date()` (Thai-aware) — signature เดิมไม่เปลี่ยน, caller ที่ inject `today` เอง (`test_job_matcher.py`) ไม่กระทบ
- ผลต่อ production: `bms_api.py:1672` (`/api/portal/discover` B0 freshness) + `Sebastian_Enrichment_Worker.py:321` (province_qualify B0 path, cron `bms-enrichment-worker.timer` รันทุก **2 นาที**) — ไม่ได้แก้ 2 ไฟล์นี้เลย แค่ default value เปลี่ยนพฤติกรรม

### Sophia audit → SAFE
- รัน test ครบ 6 ไฟล์ที่เกี่ยวข้องเองยืนยัน PASS จริง, grep ทั้ง repo ไม่มี caller อื่นตกหล่น (มีแค่ 2 production caller)
- ยืนยัน timer cadence จริง (`bms-enrichment-worker.timer` ทุก 2 นาที) + VPS timezone จริง (`Etc/UTC`) + ยืนยัน remote ยังเป็นโค้ดเก่า (บั๊กยัง active ก่อน deploy)
- ตรวจ mock logic ละเอียด ไม่มี false-pass path

### Deploy — ✅ ครบ (commit 8481d6f)
- push origin/main, VPS pull fast-forward c614252→8481d6f + restart bms-api, verify /health 200
- bms-enrichment-worker.service = oneshot → รอบถัดไปอ่านโค้ดใหม่เองอัตโนมัติ
- **verify สดตอน 20:23 UTC (ยังอยู่ในช่วงเวลาที่เคยพัง 17:00-23:59 UTC พอดี):** รัน `test_job_matcher.py`/`test_tor_is_fresh_timezone.py`/`test_portal_discover_api.py` บน VPS ตรงๆ → PASS ทั้งหมด — ยืนยัน fix ใช้งานได้จริง ไม่ใช่แค่ทฤษฎี

### Followup
- แก้บั๊ก `tor_is_fresh` timezone boundary เสร็จแล้ว (แยกงาน, ไม่เร่งด่วน — เกิดเฉพาะช่วง 00:00-07:00 เวลาไทย)

## งานที่ N+207: พลิกกลับ N+206 อีกรอบ — ย้าย keyword gate ไปตอนส่งจริงแทน enqueue (2026-07-21)

### สถานะ: ✅ เสร็จ (แก้ local, Sophia SAFE — รอ deploy)

### บริบท (กัญจน์แก้ spec ให้ชัดหลังทดสอบ N+206 จริง)
หลัง deploy N+206 กัญจน์อธิบายสเปกที่ต้องการจริงๆ ชัดกว่าเดิม:
1. **ไม่ตั้ง personal keyword** → แจ้งเตือน (LINE+web push) **ทุกงาน** ในพื้นที่ (ตรงข้ามกับ N+206 ที่เพิ่ง deploy ไป — กลับไปเหมือน N+198 เดิม)
2. **ตั้ง keyword แล้ว** → แจ้งเฉพาะงานที่ตรง
3. **หน้า "งานทั้งหมด"** → ต้องอัปเดตครบทุกงานเสมอไม่ว่าจะตั้ง keyword หรือไม่ — งานที่ personal keyword กรองออกต้องยัง "อัปเดตเงียบๆ" ในลิสต์ (ไม่แจ้งเตือน แต่ยังโชว์)

ข้อ 3 คือจุดที่ N+206 ทำผิด — gate ที่ enqueue ปิดกั้นไม่ให้แถวเข้า `notification_queue` เลย ซึ่งเป็นตารางเดียวกับที่ N+205 ใช้เลี้ยงบอร์ด "งานทั้งหมด" → บอร์ดเลยหยุดอัปเดตไปด้วย ขัดกับข้อ 3

### Fix: ย้าย gate จาก "enqueue" ไป "ส่งจริง"
- **Revert เกือบทั้งหมดของ N+206 กลับ N+198:** `discovery_match.py::match()` (ว่าง=match ทุกงาน), `Sebastian_Customer_DB.py::enqueue_notifications()` (ลบ `keyword_gate` param ทิ้ง — enqueue ให้ทุก subscriber เสมอเหมือนเดิม), `Sebastian_Enrichment_Worker.py` (ลบ `keyword_gate=True` ทั้ง 4 จุด), frontend copy + `hasPrefs` logic กลับเดิม
- **เพิ่มใหม่ (gate ตอนส่งจริง):**
  - `scripts/customer_keywords.py::should_notify(source_stage, project_name, notes_str)` — pure function: `source_stage` ขึ้นต้น `followed_` (opt-in ติดตามเอง) → True เสมอ; ไม่มี personal keyword → True; มี keyword → เช็ค `job_matcher._kw_hit` (reuse guard เดิม)
  - `Sebastian_Customer_DB.py::acquire_batch()` เพิ่ม `c.notes` เข้า SELECT
  - `Sebastian_Customer_DB.py::mark_keyword_skip(queue_id)` (ใหม่) — mark `status='skipped'`, ไม่ retry, **ไม่เขียน delivery_log** (ไม่ใช่ LINE attempt จริง กัน pollute metrics)
  - `Sebastian_LINE_Sender.py::main()` — เช็ค `should_notify()` ทันทีหลัง acquire item **ก่อน** ทุก branch `followed_*` → ถ้า False `mark_keyword_skip` แล้ว `return` ทันที (ไม่เรียก `send_line_push`/`send_line_flex` เลย = webpush mirror ที่ choke point ในนั้นไม่ทำงานอัตโนมัติ ไม่ต้องแก้แยก)

### Test (Sophia รันซ้ำยืนยัน PASS ครบ)
- ใหม่: `test_mark_keyword_skip.py` (seed queue row → mark_keyword_skip → status='skipped', ไม่ retry, ไม่เขียน delivery_log, ยังขึ้น `/api/portal/all-jobs` จริง), เพิ่ม 7 เคส `should_notify` ใน `test_customer_keywords.py`
- Revert: `test_discovery_match.py`, `test_portal_discover_api.py`, `test_province_no_cut.py` กลับ assertion N+198; ลบ `test_keyword_gate_no_personal_kw.py` ทิ้ง (test ของ behavior ที่ revert แล้ว)
- สแกน `test_*.py` ทั้ง repo — ไม่มีตัวไหนพังใหม่ (มีแค่ `test_tor_click.py` เดิมที่ต้องมี Chrome debug port จริง ไม่เกี่ยว)

### Sophia audit → SAFE
- grep `keyword_gate` ทั้ง repo เหลือ 0 hit ในโค้ด (ลบครบ)
- gate ใหม่อยู่ก่อนทุก branch `followed_*` จริง (บรรทัด 700-709 ก่อน 713/750/795)
- webpush mirror choke point (`_mirror_webpush` ใน `send_line_push`/`send_line_flex`) ไม่มีทาง leak เพราะ gate return ก่อนเรียกฟังก์ชันเหล่านี้เสมอ
- `mark_keyword_skip` ไม่ชนกับ `recover_stuck_sending` (mark 'skipped' ทันที ไม่ผ่านช่วง 'sending' ค้าง)
- **ยืนยันสดบน VPS ก่อน deploy:** `notification_queue` = **0 แถวใหม่เลย** ตั้งแต่ N+206 deploy (02:34:27) — ยืนยัน blast radius ตรงตามที่คุณกัญจน์อธิบาย (บอร์ด+LINE หยุดสนิททั้งคู่)

### Followup
- ยังไม่ deploy — รอ push+VPS+Vercel
