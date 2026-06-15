# Bid Master System — Progress Log

> เก็บเฉพาะ entry ล่าสุด (~20 อัน). entry เก่ากว่า N+101 อยู่ใน progress_log_archive.md

## งานที่ N+101: MOI/พิกัด Location Disambiguation Phase A — LIVE (2026-06-07)

### สถานะ: ✅ เสร็จ LIVE (commit 9cea29a) — checkpoint-based execution 3 จุด ผ่านครบ

### Flow: brainstorm → spec (architect review 9.7/10 + 3 action items) → plan → executing-plans inline + checkpoint review
- **Evidence trigger:** พ่อยืนยัน intel มีประโยชน์ + อยากได้ตำบลเป๊ะ → evidence-backed
- **Checkpoint 1 Foundation:** geo_reverse.py (reverse_geocode + amphoes_of_tambon, self-contained) + capture location ตอน resolve (swap fix, 0 API เพิ่ม) + save_project_location_raw (persist raw only)
- **Checkpoint 2 Intelligence:** resolve_location runtime chain (geo→tambon→dept→province) + confidence + trace(list) · select_competitors(amphoe) · wire project_id · ลบ resolve_tambon
- **Checkpoint 3 Production:** golden test (amphoe>province) + resolution-source metric log + backfill (--dry-run default, --limit 20)

### Deploy + verify (4 rollout conditions ครบ)
- push 9cea29a · VPS backup pre_moidisambig (437M) · backfill --execute --limit 20 → 8/11 OK (3 skip ไม่มี location ใน API)
- **spot-check 8 งาน: amphoe ถูกต้องทางภูมิศาสตร์ 8/8** (โพนทอง→บ้านแพง, โพธิ์หมากแข้ง→บึงโขงหลง, นากั้ง→ปากคาด, บ้านต้อง→เซกา)
- **end-to-end:** 69059132412 → "งานอาคาร อ.บ้านแพง" (disambiguation สำเร็จ ไม่ degrade!) · 69059379413 → "ต.โพธิ์หมากแข้ง อ.บึงโขงหลง" (ตำบล!) · นาทม → province graceful (ข้อมูลน้อย)
- precision: ไม่ลด (province→ตำบล/อำเภอ ที่ข้อมูลพอ) → ไม่ rollback

### Insight (calibration)
confidence ส่วนใหญ่ LOW/MEDIUM เพราะ tambon centroid ห่างพิกัดงานหลาย km — **แต่ "อำเภอ" ถูก** (อำเภอหยาบกว่า border error). ตอกย้ำ design ที่ defer confidence UI จน calibrate (architect action #3)

### Guardrails ที่ผ่าน: INC-001 (0 API เพิ่ม + backfill low-rate) · precision preserve (amphoe=None→province ไม่ใช่ WHERE NULL) · persist raw/compute derived · traceability (resolution_trace)

### Followup
- **Phase B (defer):** TIS-1099 รหัส→ชื่ออำเภอ → promote MOI ชั้น 1 (district_moi_id เก็บไว้แล้วตั้งแต่ A)
- calibrate confidence (เก็บ 100-200 งาน) → ค่อยโชว์ UI
- backfill งาน active ที่เหลือ (รอบนี้ limit 20, มี 11 candidate ทำครบแล้ว)


## งานที่ N+102: Observe location resolution_source — ตั้ง weekly auto (2026-06-07)

### สถานะ: ✅ เสร็จ LIVE (commit 52f18ad + systemd timer บน VPS)

### ทำอะไร
- `scripts/observe_location_resolution.py` — สรุป distribution ของ source/confidence (compute สด จาก resolve_location, read-only, ไม่ยิง API). `summarize()` TDD 2 test PASS
- systemd `bms-observe-location.{service,timer}` บน VPS — รายสัปดาห์ (อาทิตย์ 20:30 ไทย) ส่ง Discord. verify service run = success + Discord ส่งสำเร็จ

### 📊 Baseline (2026-06-07, intel universe 9 งาน)
- **resolve อำเภอได้ 8/9 (88.9%)** — เดิม 0% (degrade จังหวัดหมด)
- ชั้นที่ใช้: **geo=8** · province=1 → lat/lng ทำงานเกือบทั้งหมด → **ยืนยัน defer Phase B/TIS ถูก**
- confidence: MEDIUM=4 · LOW=5 (ไม่มี HIGH — tambon centroid ห่างพิกัดงานหลาย km, แต่อำเภอถูก) → ต้อง calibrate threshold ก่อนโชว์ UI

### ใช้ตัดสินใจ
- Phase B (MOI/TIS): trigger = ถ้า geo coverage ตก หรือ lat/lng resolve อำเภอผิด (ตอนนี้ยังไม่เจอ) หรือต้องการ confidence HIGH authoritative
- calibrate: เก็บ trend ราย wk → ปรับ distance threshold (LOW เยอะแต่อำเภอถูก = threshold strict ไป)


## งานที่ N+103: Price Prediction + Closed-Loop Verify (Credibility Engine) — LIVE (2026-06-07)

### สถานะ: ✅ เสร็จ LIVE (commit dad735d) — executing-plans inline + checkpoint review 3 จุด (A/B/C)

### Flow: brainstorm (flag prescriptive→reframe เป็น prediction+measurement) → spec (review 3/3 + real-time) → plan → TDD
- **Checkpoint A (Prediction@D0):** v122 price_predictions + helpers · refactor intel_context (DRY) · predict_winning_price + predict_lines (โชว์ %→ราคา) · wire D0 (การ์ด + เก็บ idempotent)
- **Checkpoint B (Closed-loop@W0):** compare_prediction (in-range+error%+update) · Winner_Poller verify_hook + Discord real-time (running accuracy) · การ์ดผู้ชนะบรรทัดเทียบคาด vs จริง
- **Checkpoint C (Production):** push dad735d · VPS backup pre_priceprediction · v122 migrate · verify end-to-end

### Deploy verify (production จริง)
- การ์ด D0 (งาน 69059327097): "💵 คาดราคา 0.7–1.1 ลบ. (ลด 0–34% จากราคากลาง 1.1) · เจ้าตัวเต็ง บัญชาศรีสงคราม ~26%" + เก็บ prediction ลง DB ✅
- accuracy summary: verified=0 (รองาน awarded — loop primed 1 prediction)

### Principle (กัญจน์แก้ความเข้าใจ)
ราคา = **prediction เชิงสถิติ ไม่ใช่คำสั่ง** (พ่อแม่คำนวณต้นทุนเอง) · คุณค่า = **credibility: คาดตรงสะสม → สถิติน่าเชื่อขึ้น** · closed-loop แจ้ง real-time ทุกครั้งที่มีผล (ไม่รอ weekly)

### tests: test_price_prediction + test_winner_poller + test_winner_card + test_cgd_intel เขียวครบ
### SP2 (defer): calibration/error-analysis (3ปีเก่าไป/วัสดุแกว่ง) — รอ accuracy data จาก SP1
### หมายเหตุ: closed-loop ให้ผลจริงเมื่องาน followed เดินถึงประกาศผล (W0) — Winner_Poller รอบถัดไป


## งานที่ N+104: Fix 2 bugs (province='' + lat/lng swap) — verify งานจริง (2026-06-07)

### สถานะ: ✅ เสร็จ LIVE (commit 7288330) — systematic-debugging (root cause ก่อนแก้)

### Trigger: ทดสอบ price prediction กับงานจริง 69059075454 (พ่อสนใจ) → การ์ดว่างเปล่า → debug

### Bug 1 — province='' (intel หาคู่แข่งไม่เจอ)
- Root: projects_seen.province ว่าง (extraction จากชื่องานล้มเหลว — ชื่อไม่มี 'จังหวัด') ทั้งที่ project_locations.province_name='บึงกาฬ' มีอยู่ (MOI authoritative)
- Fix: `backfill_provinces_from_locations()` (existing) + `_save_success` เขียน province กลับ projects_seen เมื่อว่าง (schema sanction). backfill VPS = 4 rows

### Bug 2 — lat/lng swap (resolve amphoe ผิด → เชียงของ 8,018 กม.)
- Root: eGP API mislabel (field latitude=longitude จริง). get_procurement_detail ส่งต่อ mislabel → consumer 2 ตัวจัดการต่างกัน (_enrich ไม่แก้/save_raw swap) = inconsistent
- Fix ที่ source: get_procurement_detail swap read ที่เดียว + เอา swap ออกจาก save_project_location_raw (กัน double) + migrate v123 normalize row เก่า (latitude>90→สลับ)

### Verify (งาน 69059075454)
- province ='' → 'บึงกาฬ' · lat/lng 104/17.9 → 17.9/104 (ถูก) · resolve amphoe เชียงของ → **บึงโขงหลง**
- การ์ด D0: "💡 ราคาอ้างอิง (งานถนน ต.โพธิ์หมากแข้ง อ.บึงโขงหลง)" + คู่แข่ง + คาดราคา 0.7–0.8 ลบ. ✅ ระดับตำบลครบ

### tests: 5 suite เขียวครบ (cgd_sync v123+backfill · price_prediction · cgd_intel · winner_poller · winner_card)
### บทเรียน: 1 source mislabel → compensate ที่ boundary ที่เดียว (ไม่ให้ consumer แก้เอง) · authoritative data (MOI) ควร backfill canonical field


## งานที่ N+105: Scope-local stats + Dual-block + Plain-text delivery (2026-06-08)

### สถานะ: 🚧 code เสร็จ+commit local (9441d0e), tests ครบ — รอ push ลง remote (transfer hang) → VPS verify

### Flow: brainstorm (Q&A) → spec → autonomous build (กัญจน์สั่งไม่ต้อง checkpoint review, พักผ่อน)

### Build (TDD)
- **scope-local stats:** `_company_stats_from_rows` — per-company นับเฉพาะ scope rows (ไม่เอาประวัติบริษัท). ลบ company_stats/_fetch_winner (broad). แก้ความสับสน per-company% vs area%
- **dual-block:** `_build_intel` — ตำบลเสมอ (0 งาน→"ยังไม่มี") + อำเภอเมื่อตำบล<TAMBON_MIN(5). คาดราคาอิงตำบล (ไม่มี→อำเภอ→จังหวัด). `_scope_block` + `_conf_tag` ต่อบล็อก
- **plain-text delivery:** followed_bid_open ส่ง `send_line_push` (text, จบ 1 ข้อความ ไม่ flex/ปุ่ม — งาน followed แล้ว)
- intel_context = resolve + _build_intel (budget param, คืน {lines, prediction})
- tests: test_cgd_intel (13) + price_prediction + winner_poller + winner_card + cgd_sync เขียวครบ

### Data finding (จากที่กัญจน์สงสัย "ตำบลมี 3 งาน")
ต.โพธิ์หมากแข้ง งานถนน 3 ปี = 36 งาน แต่ **33 จ้างตรง (92%)** → เหลือ 3 e-bidding = สนามจริง. ยืนยัน 91% market เฉพาะเจาะจง → dual-block จำเป็น

### คง 3 ปี (FY2566-68)
### NEXT: push ลง remote → VPS pull → verify การ์ด text dual-block งาน 69059075454


## งานที่ N+106: ปรับ output การ์ด D0 ตามกัญจน์ 6 ข้อ — LIVE (2026-06-08)

### สถานะ: ✅ เสร็จ LIVE (commit 51f1016) — ทำทีละสเต็ป (2 batch) + test ทุกสเต็ป (กัญจน์สั่ง กันพลาด)
- N+105 (scope-local + dual-block + plain-text) commit 9441d0e ก็ LIVE ในรอบเดียวกัน

### 6 ข้อที่ปรับ (verify งานจริง 69059075454)
1. หัวข้อ → "⭐ งานที่คุณติดตามกำหนดวันยื่นซองแล้ว!" (จากเดิม "เปิดประมูลแล้ว")
2. ชื่อบริษัทเต็ม — เอา `[:24]` ออกใน `_scope_block` (text ธรรมดาไม่จำกัดความยาว)
3. ชื่องานเต็ม — เก็บ `plan_project_name` จาก getProcurementDetail ตอน capture (RSS title ตัด body ที่ "ทางหลว"; API ให้เต็ม "ทางหลวงชนบท (ทถ.7-201)")
4. กำหนดยื่นซอง — ⏰ line มีใน format อยู่แล้ว + PDF enrichment resolve ได้ (9 มิ.ย. 09.00-12.00 + ⌛ เหลือ N วัน). resolve ตอน followed job เลื่อน B0→D0
5. 📍 ต./อ. ในหัว — `intel_context` คืน tambon/amphoe → format_notification ใช้ "📍 ต.X อ.Y จ.Z"
6. ลบ. → บาท — predict_lines โชว์บาทเต็ม + ปัดหลักพัน (705,000–779,000)

### Delivery: followed_bid_open = `send_line_push` (text ธรรมดา จบ 1 ข้อความ ไม่ flex/ปุ่ม) [N+105]
### bug fix รอบนี้: lat/lng swap (source) + province backfill + scope-local stats [N+104/105]

### Followup (priority lock, ดู [[project_value_principle]])
- **validate กับพ่อ** — ส่งการ์ดจริงให้ดู (กัญจน์กำลังทำ) → evidence ว่า intel/ราคาคาดช่วยตัดสินใจไหม
- รองาน followed เลื่อน D0 → closed-loop เริ่มวัด credibility


## งานที่ N+107: intel + quick-reply ทุกงาน D0 ที่ match (อุด follow-timing gap) (2026-06-08)

### สถานะ: 🚧 code+test เสร็จ (commit 93bb66d) — รอ push → VPS verify

### Flow: brainstorm (กัญจน์จับ gap "กดสนใจตอน D0") → spec → TDD

### Gap ที่แก้
intel เดิมขึ้นเฉพาะ followed_bid_open (ติดตามตั้งแต่ B0 → เลื่อน D0). ถ้ากดสนใจตอน D0 เลย → last_stage_notified=D0 → bid_open_followups (ต้องการ B*) ไม่ทริก → ไม่ได้ intel

### Build (TDD)
- **gate intel/plain-text บน `announce_type=="D0"`** (ทุก stage ไม่ใช่แค่ followed) ใน format_notification
- หัวข้องานใหม่ (ยังไม่ตาม) = "🔔 พบงานเปิดกำหนดวันยื่นซองใหม่" · ติดตามแล้ว = "⭐ งานที่ติดตามกำหนดวันยื่นซองแล้ว!"
- **Quick Reply** (ปุ่มลอยใต้ text — text กดปุ่มในตัวไม่ได้): `send_line_push(+quick_reply)` + `_text_message` + `_quick_reply_items` (⭐ ติดตาม ถ้ายังไม่ตาม + ❌ ไม่เกี่ยว)
- `is_following(customer_id, project_id)` (Customer_DB) กันโชว์ ⭐ ซ้ำ
- send path: D0 → send_line_push(text, qr) · non-D0 → flex เดิม
- webhook รับ postback star:/fb: อยู่แล้ว (ไม่ต้องแก้)
- tests: test_d0_quickreply (4) + test_cgd_intel wiring (D0 ทุก stage) เขียว

### ผล: ทุกงาน D0 ที่ match → เห็น intel ทันที + กดติดตามได้จาก chip (ไม่ว่ากดก่อน/ตอน/หลัง D0)
### spec: docs/superpowers/specs/2026-06-08-intel-all-d0-quickreply-design.md
### NEXT: push → VPS pull → verify render งานใหม่ D0


## งานที่ N+108: DECISION — follow link แบบ LIFF (option A) สำหรับ multi-job D0 (2026-06-08)

### สถานะ: 📌 ตัดสินใจแล้ว — รอทำ session ใหม่ (กัญจน์ขอเปิด session ใหม่ก่อน)

### ปัญหาที่เจอ (กัญจน์จับได้)
quick-reply (ปุ่มลอย ที่เพิ่งทำ N+107) LINE โชว์**เฉพาะข้อความล่าสุด** → ถ้าหลายงาน D0 เด้งพร้อมกัน ปุ่ม ⭐ ของงานก่อนหน้าหาย กดติดตามไม่ได้

### ตัดสินใจ: option A = LIFF follow link
- ข้อความ D0 = text ธรรมดา + **ลิงก์ LIFF ในเนื้อข้อความ** (ต่องาน, เลื่อนกดของเก่าได้ ไม่หาย)
- แตะลิงก์ → มินิเว็บใน LINE → กด "ติดตาม" 1 ครั้ง → endpoint บันทึก followed_jobs
- ตรงแผน client = LINE + Web Portal (LIFF) [[project_client_surface_decision]]
- quick-reply (N+107) = **interim** ใช้ต่อได้ระหว่างทำ (ดีตอนงานเดียว)

### TODO session ใหม่
1. **กัญจน์ต้อง register LIFF app** ใน LINE Developer Console เอง (ผมทำแทนไม่ได้) → ได้ LIFF ID
2. brainstorm/spec: หน้า LIFF follow + endpoint (FastAPI bms_api) บันทึก follow จาก LIFF userId
3. format_notification (D0) แทรกลิงก์ LIFF + เอา quick-reply ออก (หรือคงไว้คู่)
4. identify user จาก LIFF (liff.getProfile userId → map customer)

### เริ่ม session ใหม่: บอก "ทำ LIFF follow link ต่อ" → resume จากนี่

## งานที่ N+109: CHECKPOINT — ก่อนเปลี่ยน session (2026-06-08)

### สถานะ: ⏸ pause เปลี่ยน session (กัญจน์ขอ execute ใน session หน้า)

### ✅ เสร็จแล้ว session นี้ (brainstorm → spec → plan ครบ)
- ตัดสินใจสถาปัตยกรรม: **follow-link ใช้ signed-token ไม่ใช่ LIFF** (bot รู้ userId อยู่แล้ว → ฝังใน token ได้, ไม่ต้องสร้าง LINE Login channel/LIFF SDK). LIFF เลื่อนไป Portal Phase 2
- ยืนยัน infra: HTTPS พร้อม — `https://api.butler-bms.com` (Let's Encrypt+Certbot, nginx→FastAPI:8000, /health live)
- Spec (approved): `docs/superpowers/specs/2026-06-08-follow-link-signed-token-design.md` (commits ea572e4, f692718, 32ceeb0)
- Plan (7 tasks): `docs/superpowers/plans/2026-06-08-follow-link-signed-token.md` (commit 4efac8f)
- Idea Portal Phase 2 เก็บลง `ideas/future_development.md` (uncommitted — ดูค้าง)

### 🎯 NEXT ACTION (session หน้า)
- **Execute plan แบบ subagent-driven** (กัญจน์เลือก): `docs/superpowers/plans/2026-06-08-follow-link-signed-token.md`
- ใช้ skill `superpowers:subagent-driven-development` — dispatch subagent สดต่อ 1 task, review ระหว่าง task
- ลำดับ: Task 1 (follow_token.py) → 2 (bms_api helpers) → 3 (routes) → 4 (sender wiring) → 5 (sanity) → 6 (deploy) → 7 (log)
- ⚠️ **Task 6 = deploy VPS มี gate: ต้อง confirm กัญจน์ก่อน `git push`** (CLAUDE.md) + ตั้ง `BMS_FOLLOW_SECRET` ใน `/opt/bms/app/.env`
- ⚠️ implementation จริงให้ log เป็น **N+110** (N+109 = checkpoint นี้แล้ว)

### ค้าง/ระวัง
- design ผ่าน review: expiry 120 วัน (โชว์ user) · status unfollow=`'unfollowed'` (แยกจาก system `'closed'`) · token bearer OK สำหรับ MVP · token เผื่อ portal (`p=None`)
- VPS **ไม่มี sqlite3 CLI** → sanity ใช้ `python3 -c`
- uncommitted: ideas/future_development.md (+ data/* runtime, settings.local.json — ปกติไม่ commit)
- Portal Phase 2 = spec ถัดไป (รายการงานติดตาม + lifecycle + bid_results + โน้ตต่องาน)

---

## งานที่ N+110: follow-link signed-token toggle — LIVE (2026-06-09)

### สถานะ: ✅ เสร็จ — deployed VPS + e2e verified (subagent-driven, 6 commits)

### Root cause (อุดอะไร)
quick-reply ⭐ ใต้ข้อความ D0 **หายเมื่อหลายงานเด้งพร้อมกัน** (LINE แสดง quick-reply เฉพาะข้อความล่าสุด — N+108 gap). เลื่อนกลับไปกดงานเก่าไม่ได้ → ติดตามไม่ทัน

### Fix (signed-token ไม่ใช่ LIFF)
ลิงก์ติดตาม **อยู่ในเนื้อข้อความ** (เลื่อนกดงานเก่าได้ไม่หาย) → หน้าเว็บ toggle ติดตาม/ยกเลิกตามสถานะจริง
- `scripts/follow_token.py`: HMAC stateless token (u+p+exp, base64url.sig). secret=`BMS_FOLLOW_SECRET`, exp 120 วัน, p=None เผื่อ portal
- `bms_api.py`: `_record_unfollow`(status=`'unfollowed'` แยกจาก system `'closed'`) / `_follow_status` / `_fmt_exp_th` / `_follow_page_html` (มือถือ-first, escape) + `DB_PATH` env override + GET/POST `/follow` (GET side-effect-free, write gated หลัง verify_token)
- `Sebastian_LINE_Sender.py`: `build_follow_link` (มินต์ token, exception-safe คืน `''` ไม่ทำ D0 พัง) + D0 branch แทรกลิงก์ แทน quick-reply (`quick_reply=None`)

### Process (subagent-driven-development + two-stage review)
- 7 tasks, fresh subagent ต่อ task + spec-review → code-quality-review ทุก task
- 🐛 **bug จับได้จาก review**: `build_follow_link` except เรียก `log()` แต่ `log` เป็น nested func ใน `main()` (ไม่ใช่ module global) → จะ `NameError` ถ้า make_token พลาด (อุด safety net รั่ว). fix → `print(stderr)` + เพิ่ม test exception path
- 🐛 **bug fixture**: test seed `projects_seen` ขาด `first_seen_at` (NOT NULL no-default) → เติม

### ผล (verified)
- local test 5/5: token(roundtrip/tamper/expiry/portal) · bms_follow(toggle state machine) · follow_link(+exception path) · followed_jobs(regression) · idempotent(follow→unfollow→follow=1 row)
- deploy VPS: push c73c0fb→97a8297 (5 feat/fix commits) · set .env (secret+base_url) · pull ff · restart bms-api active
- **e2e production curl**: health ok · invalid-token page ok · GET inactive→POST follow(active)→POST unfollow(inactive) ครบ · DB `{active:8, unfollowed:1}` (8 real follows untouched, test row=unfollowed แยกถูก)
- sender EnvironmentFile = .env เดียวกัน → timer รอบหน้ามินต์ลิงก์ได้

### Commits
- `c0bb1fb` follow_token.py + tests
- `4e43d45` bms_api helpers + DB_PATH env
- `fed250a` GET/POST /follow routes
- `e5b0ac7` D0 follow-link แทน quick-reply
- `97a8297` fix build_follow_link except (log NameError) + test
- (+ N+110 progress)

### Followup
- Portal Phase 2 = spec ถัดไป (รายการงานติดตาม + lifecycle + bid_results + โน้ตต่องาน)
- `_quick_reply_items` ยังคงนิยามไว้ (unused) เผื่ออนาคต
- ⏳ validate user-facing จริง: รอ D0 ใหม่เด้ง → ดูลิงก์ในข้อความ + ลองกด toggle

---

## งานที่ N+111: คาดราคาแยกประเภทผิวถนน (concrete vs asphalt) — ✅ LIVE บน VPS (2026-06-09)

### สถานะ: ✅ implement + test + **deployed VPS** (commit 76fee27/3437bca, push→VPS pull ff 3437bca, กัญจน์ approve caveat). verified บน production cgd_winners จริง

### Requirement (กัญจน์ ก่อนนอน 2026-06-09)
งานถนนมี 2 ประเภท (แอสฟัลท์ติก/คอนกรีต) %ลดจากราคากลางต่างกันมาก → คาดราคางานคอนกรีต ให้อ้างอิงเฉพาะถนนคอนกรีตในตำบลนั้น (ไม่เอาแอสฟัลต์ปน)

### Evidence-first PROBE (ก่อน implement — `scripts/_probe_road_subtype_discount.py`, ผล `data/probe_road_subtype_discount.json`)
ข้อมูลจริง winner_history.db 617K, competitive-set + FY2566-68 + **price_valid=1** + asphalt-precedence classify:
- **concrete** n=723 median **25%** (p25-75 5.9-36) · **asphalt** n=468 median **14%** (p25-75 0.3-29.3 กว้างมาก) · unknown n=513 median 0.2%
- ✅ ยืนยัน hypothesis: concrete vs asphalt ต่างกัน ~11 จุด + รูปร่างต่างกัน → ห้าม pool
- **impact จริง** (นครพนม งบ1ล้าน): pooled ลด 0-35% (กว้างไร้ประโยชน์) → concrete-only 24-41% / asphalt-only 21-37% (แคบ ใช้ได้). pooled p25=0 ถูกลากด้วย asphalt-maintenance/unknown ที่ลด~0%

### ⚠️ Caveats (เจอจาก probe — ต้อง flag ก่อน deploy)
1. **asphalt bimodal**: เสริมผิว/บูรณะ (งานกรมทางหลวง win≈ราคากลาง) median ~9% vs ก่อสร้างใหม่ ~21%. variance สูงกว่า concrete
2. **ต่างตามจังหวัด**: นครพนม asphalt 25% แต่ **บึงกาฬ asphalt 0.84%** (near-zero, highway-style) — subtype filter ช่วยตัด concrete contamination แต่ไม่แก้ confound job-nature/agency
3. **`price_valid` flag**: cgd_intel `_fetch` **ไม่ได้เช็ค price_valid** (เดิม) → อาจมี quality issue เดิม. **แยกประเด็น ไม่ bundle** (จะกระทบ prediction ทุกหมวด ไม่ใช่แค่ถนน) — แนะนำพิจารณาเพิ่มทีหลัง

### Implementation (cgd_intel.py, back-compat)
- `road_subtype(name)` → 'asphalt'|'concrete'|None. **asphalt ชนะ concrete** ("แอสฟัลท์ติกคอนกรีต"=ผิวแอสฟัลต์)
- `_fetch(..., subtype=)`: concrete→LIKE concrete-kw AND NOT asphalt-kw · asphalt→LIKE asphalt-kw · None→pool เดิม
- `_build_intel(..., subtype=)` ส่งต่อ 3 _fetch · `intel_context` คำนวณ subtype จาก project_name อัตโนมัติ
- back-compat: subtype default None (งานไม่ใช่ถนน/select_competitors legacy ไม่กระทบ)
- sparsity: subtype ลด n → fallback ladder ตำบล→อำเภอ→จังหวัด + conf-tag เดิมรองรับ. ไม่มี concrete เลย→omit (ดีกว่าคาดผิดประเภท)

### Test
- `test_road_subtype.py` 4/4 (classifier asphalt-precedence + _fetch filter + _build_intel + intel_context e2e)
- regression: test_cgd_intel 13/13 (ต้อง `BMS_DATA_DIR` set local) + test_price_prediction PASS

### Deploy (✅ 2026-06-09)
- กัญจน์ approve caveat → push origin main → VPS `git pull --ff-only` (ff 3437bca สะอาด). **ไม่ต้อง restart** (LINE_Sender/Winner_Poller เป็น timer-based หยิบโค้ดใหม่ทุกรอบ · bms-api ไม่ import cgd_intel)
- verify บน VPS: test_road_subtype 4/4 + cgd_winners จริง (นครพนม ถนน งบ1ล้าน) pooled 0-35% → concrete 24-41%/asphalt 21-37% (ตรง local เป๊ะ n=700/289/145)

### Next (รอ observe + เผื่อทำต่อ)
- ⏳ validate ผลจริง: รอ D0 ถนนใหม่เด้ง → ดูการ์ดคาดราคาว่าแยกประเภทถูก (พ่อ review) + closed-loop accuracy เมื่อถึง W0
- เผื่อ improve: classify "unknown" 30% (ลูกรัง/หินคลุก/บูรณะไม่ระบุผิว) · **price_valid filter = แยก ticket** (กระทบทุกหมวด)

---

## งานที่ N+112: แจ้ง W0 2 รอบ + วิเคราะห์ละเอียด — LIVE บน VPS (2026-06-09)

### สถานะ: ✅ Round 1 LIVE + e2e ส่งจริงถึงกัญจน์ (Round 2 รอผลทางการ) · subagent-driven 10 commits + 1 e2e hotfix

### ที่มา (จาก debug 69059075454)
W0 ไม่เด้งเพราะระบบตรวจ `getProcureResult` (ผลทางการ) อย่างเดียว ซึ่ง lag — "สรุปราคาเบื้องต้น" (ราคาต่ำสุด, เปิดเผย~เที่ยง) อยู่ service `egp-agpc01` ที่ไม่ได้ใช้. RE สำเร็จ (pure-API chain) → feature แจ้ง 2 รอบ (Option C, กัญจน์เลือก).

### Build (spec→plan→subagent-driven+TDD, 10 tasks)
- **T1** `save_prediction` upsert (ทับค่าล่าสุด ไม่ลบ actual) · **T2** `compare_prediction` เทียบ**กรอบบน** (area_price_hi, held=actual≤hi) + `compare_prediction_provisional` (display-only)
- **T3/4** `prelim_summary.py`: parse + `fetch_prelim_summary` pure-API (encryptApiKey→genReportPrice→viewPdf→pdfplumber) + greenBook gate
- **T5** `cgd_intel.analyze_bidders`/`company_area_history` (Round2 breakdown ต่อราย + ประวัติ in/out ตำบล + ป้าย warned/🔸เจ้าประจำหลุดtop3/หน้าใหม่)
- **T6** `format_prelim_notification` (Round1) · **T7** `format_winner_detailed` (Round2)
- **T8** Winner_Poller **stage machine D0→PRELIM→W0** (prelim pass + formal pass รวม PRELIM, Round2 ยิงได้แม้ข้าม Round1) + verify_hook held
- **T9** wire: followed_prelim→Round1, followed_winner→detailed + poller resolve_prelim live
- test 11/11 (7 ใหม่ + 4 regression) · ทุก task ผ่าน 2-stage review

### Deploy + e2e (✅)
- push (10 commits) → VPS pull ff → re-save prediction concrete (upsert: กรอบบน 779k→**729,774**)
- 🐛 **e2e จับ bug**: PDF มี footer boilerplate "...๒ ซอง...จะไม่มีการแสดงข้อมูลราคา" **ทุกใบ** → parse guard เดิมตัดงานมีราคาทิ้งเป็น 2-ซองผิด. fix (commit b237336): has_price จากเลขในบรรทัด "รายการพิจารณาที่" (`findall[-1]` กันเลขมิติ) ไม่ใช่ boilerplate. test เพิ่ม footer+เลขมิติ reproduce
- **Round 1 ส่งจริงถึงกัญจน์** (cust2): ราคาต่ำสุด **740,000** · ผู้เสนอ 3 ราย · 🎯 เทียบกรอบบน 729,774 → **สูงกว่า 1.4%** (ส่วนลดจริง 27%) — closed-loop เบื้องต้นตรงเป๊ะกับที่กัญจน์เห็น (730 vs 740)
- หมายเหตุ: ข้อความผิด (2-ซอง) ถูกส่งก่อน fix 1 ครั้ง → re-send ฉบับถูกแล้ว

### เหลือ / Followup
- ⏳ **cadence timer 6h→2h**: แก้ไม่ได้ (bms มี NOPASSWD เฉพาะ systemctl ไม่รวม sed) → กัญจน์รันเอง: `sudo sed -i 's|^OnCalendar=.*|OnCalendar=*-*-* 00/2:15:00|' /etc/systemd/system/bms-winner-poller.timer && sudo systemctl daemon-reload && sudo systemctl restart bms-winner-poller.timer`
- ⏳ **Round 2 e2e**: รอ getProcureResult มีผู้ชนะทางการ (poller formal pass จะยิง Round2 detailed อัตโนมัติ — follow @ PRELIM)
- ▶ **Sub-2** (ถัดไป): Competitor Trend Learning Loop (เก็บ bid_results→เทรนด์ส่วนลดต่อบริษัท→feed กลับ prediction). ดู ideas/future_development.md

---

## งานที่ N+113: Competitor Trend — recency-weighted adaptive discount (Sub-2a) — LIVE บน VPS (2026-06-10)

### สถานะ: ✅ LIVE (subagent-driven 5 commits, test 9/9, ทุก task ผ่าน 2-stage review) + real-data sanity ผ่าน

### โจทย์ (กัญจน์)
prediction เดิมใช้ percentile แบบ flat (ทุกงานน้ำหนักเท่ากัน ไม่สนวันที่) → ไม่เรียนจากผลล่าสุด. ขอ "คาดราคาปรับตามผลจริง — งานล่าสุดน้ำหนักมากสุด แต่ไม่เร็วเกิน + เทรนด์แยกบริษัท". คำถามทดสอบ design: "คาด 70 จริง 80 → ครั้งหน้า 79 ไหม" → **ไม่ (overfit)** ตอบด้วย EWMA: 70→73 หลังครั้งแรก → ~80 เมื่อ 5-7 งานยืนยัน

### Build (spec→plan→subagent-driven+TDD, 5 tasks)
- **`competitor_trend.py`** (ใหม่): `ewma`(α0.3, recency)/`median`/`ewma_trend`(↑↓→, n<3→None)/`recency_adjusted_pct`(เลื่อน percentile ตาม ewma-median delta, damped ≤CAP 8 จุด)
- series รวม 2 แหล่ง เรียงเวลา: `area_win_series` (ผู้ชนะ — cgd_winners + bid_results winner) · `company_series` (พฤติกรรมบริษัท — cgd win + bid proposal, ตำบล→จังหวัด)
- **prediction adaptive**: `_build_intel` track basis_sub/dist → `recency_adjusted_pct(area_win_series)` ก่อน predict (subtype-aware ตาม N+111)
- **Round 2 เทรนด์ต่อบริษัท**: `analyze_bidders` ใช้ `company_series`+`ewma_trend` (แทน median เดิม) · format โชว์ "ล่าสุด~X%"
- design: EWMA recency แต่ damped + guard n<MIN_N(3) ไม่ปรับ (กัน noise/sparse). closed-loop Sub-1 (เก็บ คาด vs จริง) = เชื้อเพลิงของ feedback

### Deploy + sanity (✅)
- push (4 feat commits) → VPS pull ff e371d76
- real-data: **announce_date 100%** (617K) → recency ทำงานเต็ม. นครพนม concrete 289 จุด: median 33.7%→**ewma 27.8%** (ล่าสุดลดน้อยลง) → flat 23.6-40.6% → **adaptive 17.7-34.8%** (delta -5.9 = ปรับขึ้นราคา ตลาดแข่งน้อยลง). tambon sparse (โพธิ์หมากแข้ง) ไม่ over-adjust (robust)
- test: 5 ใหม่ + regression (cgd_intel 13/13, price_prediction, compare_upper_bound, winner_poller_prelim) ผ่าน

### Followup
- ▶ **Sub-2b**: ถ่วงน้ำหนัก "ผู้น่าจะยื่น" ใน prediction (speculative — รอ design)
- ▶ **Sub-2c**: รายงานเทรนด์ตลาดรวม
- ⏳ observe: bid_results สะสมเพิ่ม → recency จะมีน้ำหนักงานที่เรา observe เองมากขึ้น (ตอนนี้ส่วนใหญ่ยัง cgd_winners)

---

## งานที่ N+114: Portal Phase 2a — dashboard read-only — LIVE บน VPS (2026-06-10)

### สถานะ: ✅ LIVE (subagent-driven 4 commits, test 5/5, ทุก task ผ่าน 2-stage review) + e2e curl ผ่าน

### โจทย์
ลูกค้าเห็นงานติดตามเฉพาะข้อความ LINE ทีละครั้ง — ไม่มี "ดูรวม". Portal = เว็บหน้าเดียวต่อยอด follow-link (`follow_token` p=None = portal-token ที่วางไว้ N+110)

### Build (spec→plan→subagent-driven+TDD, 5 tasks, แตะ bms_api.py)
- `_portal_jobs(user_id)`: followed_jobs (active+closed, ซ่อน unfollowed) → join projects_seen/locations/predictions/bid_results → จัดกลุ่ม **won/bidding/pre** (won = มีผู้ชนะ/announce W*)
- `_portal_page_html(groups)`: การ์ดมือถือ-first จัดกลุ่ม stage + lifecycle dots ●━━●━━○ + คาดราคา + ผู้ชนะ/คู่แข่ง + empty state + escape (XSS)
- `GET /portal?t=<portal_token p=None>`: verify → portal | invalid/no_customer (reuse `_follow_page_html`) · `_portal_link` + `PUBLIC_BASE_URL`
- webhook keyword "งานของฉัน"/"portal" → reply ลิงก์ portal + เพิ่มใน help

### Deploy + e2e (✅)
- push → VPS pull ff dd434db → **restart bms-api** (route ใหม่) → active
- e2e: mint portal token (customer 2 กัญจน์) → `curl /portal` → **"งานที่คุณติดตาม (5)"** + กลุ่ม กำลังประมูล/รับฟังความเห็น render ครบ
- test 5/5 (2 ใหม่ + regression follow 3) ผ่าน · routes /follow + /portal

### Followup → Portal 2b
- โน้ตต่องาน (write + ตารางใหม่) · unfollow จาก portal · per-job detail page
- ⏳ validate user-facing: กัญจน์ลองพิมพ์ "งานของฉัน" ใน LINE จริง + เปิดดูในมือถือ

---

## งานที่ N+115: CHECKPOINT — ก่อนเปลี่ยน session (2026-06-10)

### สถานะ: ⏸ pause เปลี่ยน session (กัญจน์ขอทำ 2 เรื่องต่อใน session หน้า)

### ✅ เสร็จแล้ว session นี้ (6 feature LIVE บน VPS)
- N+110 follow-link signed-token · N+111 ราคาถนน subtype concrete/asphalt · N+112 แจ้ง W0 2 รอบ (prelim+formal) · discovery แยก target/นอกเป้า · N+113 Competitor Trend recency EWMA · **N+114 Portal 2a dashboard** (35390e3)
- ทุก feature ผ่าน brainstorm→spec→plan→subagent-driven+TDD + deploy + e2e

### 🎯 NEXT ACTION (session หน้า — กัญจน์สั่ง 2 เรื่อง, validation feedback จากการใช้จริง)

**เรื่อง 1 — 🐛 followed-bid-open ไม่โชว์ราคาคาดการณ์ (investigate):**
- อาการ: LINE เด้งแจ้ง "งานที่ติดตามประกาศวันยื่นซองแล้ว" (followed_bid_open / advance B0→D0) แต่**ไม่มีบรรทัดราคาชนะที่คาดการณ์** (💵 คาด X–Y)
- งานที่น่าจะ trigger: 69059374770 / 69059379413 (โพธิ์หมากแข้ง, กัญจน์ follow, advance D0)
- **hypothesis (ต้อง verify ก่อนแก้ — ใช้ systematic-debugging):** `cgd_intel.intel_context` คืน prediction=None เพราะตำบลโพธิ์หมากแข้ง competitive data sparse (3 e-bidding) → `_build_intel` omit prediction. หรือ path followed_bid_open ใน `Sebastian_LINE_Sender` ไม่แนบ prediction. **ตรวจ:** รัน intel_context ของ 2 งานนั้นบน VPS ดูว่าได้ prediction ไหม + ดู format_notification path
- ไฟล์: `scripts/cgd_intel.py` (_build_intel, predict_winning_price), `scripts/Sebastian_LINE_Sender.py` (format_notification D0 path)

**เรื่อง 2 — ✏️ แก้ Portal (กัญจน์จะระบุเพิ่ม):**
- ที่ propose ไว้แล้ว: เพิ่มกลุ่ม **"⏳ รอประกาศผลทางการ"** ใน portal สำหรับงาน `followed_jobs.last_stage_notified='PRELIM'` (เห็นราคาเบื้องต้นแล้วแต่ผลทางการยังไม่เข้า) — แยกจาก "กำลังประมูล". แก้ `_portal_jobs` grouping (เพิ่ม key 'prelim' เช็ค last_stage_notified) + `_portal_page_html` + ดึงราคาเบื้องต้นจาก prelim_summary/bid_results
- เคส: 69059075454 ตอนนี้อยู่ "กำลังประมูล" (ถูกตาม eGP) แต่กัญจน์คาดว่าควรอยู่ "รอประกาศ"
- **กัญจน์จะบอกรายละเอียดที่อยากแก้เพิ่มเอง** ตอน session หน้า → เริ่มด้วยถาม/brainstorm ก่อน build
- ไฟล์: `scripts/bms_api.py` (`_portal_jobs` ~line 340+, `_portal_page_html`). spec/plan portal: docs/superpowers/{specs,plans}/2026-06-10-portal-phase2a-dashboard*

### ค้าง/ระวัง (followup เดิม)
- ⏳ **cadence timer 6h→2h**: กัญจน์รัน sudo เอง (bms ไม่มี NOPASSWD sed) — คำสั่งใน N+112
- ⏳ **Round 2 e2e**: รอ getProcureResult มีผู้ชนะทางการ → poller formal pass ยิงเอง (follow @ PRELIM พร้อม)
- ▶ Portal 2b (โน้ต/unfollow/detail) · Sub-2b (ถ่วงผู้น่าจะยื่น, speculative) · Sub-2c (รายงานตลาด)
- VPS HEAD = 35390e3 (sync กับ main) · bms-api active · timers healthy · token harvest มี gap เป็นช่วงๆ (SPOF รู้อยู่)

## งานที่ N+116: Fix followed-bid-open ไม่โชว์ราคาคาด (root cause = location column เพี้ยน) (2026-06-11)

### สถานะ: ✅ code fix เสร็จ (TDD + verified real data) · backfill + deploy ค้าง

### Root cause (systematic-debugging)
- งาน 69059327097 (ต.นาทม อ.นาทม นครพนม) followed_bid_open ส่ง 06-10 21:03 ไม่มี 💵 คาดราคา
- price_predictions พิสูจน์: 374770/379413 มี prediction ตอนส่ง (06-09) → resume note เดาผิดงาน. ตัวจริง = 327097
- **คอลัมน์ cgd_winners.district/subdistrict เพี้ยน** (reverse-geocode พิกัด snap ไปอำเภอเมือง) → งานตำบลนาทมจริง 15 งาน competitive recent-3y ถูก tag เป็น ในเมือง/เมืองนครพนม/นาคู่ → `_fetch(district='นาทม')`=0 → `_build_intel` คืน None → ไม่มีบรรทัดราคาคาด
- instinct กัญจน์ถูก: ข้อมูลมีจริง (ค้นด้วยชื่องาน "ตำบลนาทม" เจอ 105 งาน, competitive recent-3y 15 งาน)

### Fix (กัญจน์เลือก: ทำทั้งคู่ + ย้อนลึกเมื่อข้อมูลน้อย+ป้าย)
- **cgd_intel._fetch**: match location ด้วย `(subdistrict=? OR project_name LIKE %ตำบลX%)` + `(district=? OR %อำเภอY%)` — ชื่องาน = ground truth, column = belt-and-suspenders
- **_fetch include_old + _fetch_scope**: recent-3y ก่อน, ถ้าคู่แข่ง<MIN_COMPETITORS ย้อนทุกปีงบ + ป้าย "📜 รวมข้อมูลเก่ากว่า 3 ปี"
- **competitor_trend._area_where**: name-OR-column เหมือนกัน (สอดคล้อง _fetch — recency series เห็นข้อมูลตรงกัน)
- TDD: +4 test ใหม่ (name-match, include_old, old-label, trend name-match). ทุก test (8 ไฟล์ที่ import) PASS

### Verify real data (VPS, non-deploy)
- 327097: ตำบลนาทม 4 งาน + อำเภอนาทม 13 งาน → 💵 คาด 815k–1.12M ✅ (เดิม None)
- 374770/379413: ยังทำงาน + ข้อมูลมากขึ้น (name-match เจอเพิ่ม), 379413 โชว์ป้ายข้อมูลเก่า ✅ ไม่ regress

### Decision update (หลัง investigate ต่อ)
- **ข้าม backfill** — redundant: consumer เดียวของ cgd_winners.district/subdistrict คือ intel/trend (ตอนนี้ name-match แล้ว). backfill จากชื่อ = ตั้งคอลัมน์เท่ากับ name-LIKE อยู่ดี + ไม่มี consumer อื่น → risk ล้วน (กัญจน์ confirm ข้าม)
- **เพิ่ม match ย่อ ต./อ.** แทน: ชื่อ CGD เขียนทั้ง 'ตำบลX' (436) และ 'ต.X' (71) — LIKE จับทั้งสอง (cgd_intel._fetch + competitor_trend._area_where). TDD +1 test. verified 327097 ตัวเลขไม่เพี้ยน

### Followup
- Deploy VPS (confirm push) + e2e verify — task #4

### Retroactive resend (N+116, ต่อ)
- audit งานที่ส่งพร้อมราคา 14 งาน → 11 เปลี่ยน (หลายงานเดิม "ไม่มีราคา" = โดน bug เดียวกัน), 3 None ถูกต้อง (ไม่ใช่งานถนน: เลเซอร์/งานอาหาร/ซื้อคอนกรีต province ว่าง)
- กรอง active(deadline≥06-11)+มีผู้ติดตาม → 3 งาน (327097 06-18, 374770/379413 06-15). ส่งการ์ด "🔄 อัปเดตราคาคาด" 6 ข้อความ (DRY preview ก่อน) สำเร็จทั้งหมด
- Q1 coverage: งานถนน ref 1,392 → 56% ชื่อระบุตำบล (กู้ 675 ที่ column ผิด), 43% ไม่ระบุ→ตกระดับอำเภอ/จังหวัด (ไม่หาย). Q2: logic ใหม่ไม่ retroactive อัตโนมัติ → resend มือเฉพาะงาน active

## งานที่ N+117: Work-nature filter (จ้างก่อสร้าง vs ซื้อ) — แก้ช่วงคาดราคากว้าง (2026-06-11)

### สถานะ: ✅ code เสร็จ (TDD + verified) · รอ deploy

### ปัญหา (จาก feedback กัญจน์)
ช่วง %ส่วนลดกว้างเกินใช้ไม่ได้ (327097 ต.นาทม ลด 5–32% → 770k–1.08M). สาเหตุ: reference pool รวม
งาน "ซื้อ" (วัสดุ เหล็ก/คอนกรีตผสมเสร็จ ลด ~0–2%) กับ "จ้างก่อสร้างถนน" (ลด ~25–38%) — คนละลักษณะงาน

### Fix
- `work_nature(project_name)` → purchase (มี "ซื้อ") | construction. คู่กับ road_subtype
- thread intel_context → _build_intel → _fetch_scope → _fetch + competitor_trend (area_win_series/_area_where)
- _fetch กรอง: construction → NOT LIKE %ซื้อ% · purchase → LIKE %ซื้อ%
- TDD +2 tests (work_nature, _fetch filter). ทุก test (8 ไฟล์) PASS

### Verify real data
- 327097: ตำบลนาทม 2 งาน (ตัดซื้อออก) ลด 29–35% → คาด 744k–815k (ช่วง 71k จากเดิม 307k) ✅
- 374770/379413: ยังทำงาน. 374770 ยังกว้าง (6–32%) เพราะงานก่อสร้างจริงลด 0% (single-bidder) = Step 2

### Followup
- Step 2: บีบ band/anchor (max = ส่วนลดลึกสุด, ช่วง ~5%) สำหรับ construction ที่มี outlier 0%

## งานที่ N+118: Step 2 Contested-focus prediction (2026-06-11)

### สถานะ: ✅ code เสร็จ (TDD + verified) · รอ deploy

### Research ก่อน (docs/research_discount_factors_2026_06_11.md)
ส่วนลด bimodal: no-competition (~0%) vs contested (~32-36%). ปัจจัย: ประเภทหน่วยงาน(อบต 32%/อบจ 1%) >
ขนาดงบ(>10ลบ.→8%) > จังหวัด. เคสกัญจน์ อบต 1-3ลบ. แข่งจริง 82% ลด 31-42%. จำนวนคู่แข่งวัดไม่ได้ (bid_results ว่าง)

### Fix (brainstorm → spec → TDD)
- CONTESTED_MIN_DISCOUNT=15 + `_fetch(contested_only)` → ตัดงานลด<15% (no-competition mode)
- thread intel_context→_build_intel→_fetch_scope→_fetch + competitor_trend (recency series ก็ contested)
- intel_context: contested-first, ถ้าพื้นที่ไม่มีงานแข่ง → fallback ทั้งหมด + ป้าย "⚠️ แข่งขันน้อย"
- เพิ่ม median ("ปกติ ~X%") + framing "ถ้ามีคู่แข่ง ผู้ชนะลด" + label "(งานแข่งจริง)"
- auto ตัดงานใหญ่/อบจ/>10ลบ. (อยู่ใน low mode → ถูกตัด). TDD +3 tests

### Verify real data (block = prediction สอดคล้อง)
- 327097 ต.นาทม: 29-35% (ปกติ 32%) → 744k-815k (เดิม 5-32%/770k-1.08M)
- 374770 โพธิ์หมากแข้ง: 28-33% (ปกติ 31%) → 649k-697k (เดิม 0-26% มี outlier)
- 379413: 20-33% (ปกติ 25%) → 454k-543k

### Followup
- bid_results สะสม → อนาคตวัดจำนวนคู่แข่งจริงได้ → segment แม่นขึ้น
- agency/budget segment (defer — contested-focus ครอบคลุมแล้ว)

## งานที่ N+119: Market-regime pricing + 3 งานการ์ด → DEPLOYED (2026-06-11)

### สถานะ: ✅ DEPLOYED VPS (commit a0cf7ae, migration v124+v125 + repredict applied)

### Research (กัญจน์ challenge หลายรอบ → evidence)
- ตัวขับ %ส่วนลด = **ระบอบตลาด/หน่วยงาน** ไม่ใช่ budget/คู่แข่ง/ชั้น (getProcureResult n=144, corr budget-ผู้ยื่น=0.00)
- "ถนน" ปน 2 ตลาด: ท้องถิ่น 26-30% vs กรมทางหลวง 0.3% (Simpson's paradox)
- อบจ. คนละระบอบ (1.9% ชิดเพดาน ไม่ใช่ 31% แบบ อบต.) → แยก provincial
- ทฤษฎีชั้น = เส้นแบ่งสิทธิ์ที่ 10ลบ. (กัญจน์อยู่ชั้น6 <10ลบ ล้วน). BUG: winner_tin=ขยะ(วันที่)
- docs/research_market_regime_discount.md + research_subtype_discount_variance.md

### Price logic ใหม่ (A+B+C + subtype + อบจ)
- A: agency_market(dept) 3-way local/provincial/central → กรอง reference pool
- B: contested floor ต่อหมวด (ถนน/ขุด=15, อาคาร/ราง/water_struct=5)
- C: ฐานความแม่นยำ = ค่ากลาง (median) + framing win/lose (คาด≤ชนะ→ความแม่นยำ / >→ความคลาดเคลื่อน)
- subtype: ถนน concrete/asphalt + แหล่งน้ำ ขุด/โครงสร้าง (water_subtype)

### 3 งานการ์ดก่อน deploy
1. ⏰ เวลายื่นซอง — DocZip ดึง time + schema v125 deadline_time (province_api path)
2. 📄 ลิงก์ประกาศ — public eGP URL ทุกงาน (RSS pdf / fallback projectId)
3. 🔄 repredict_followed.py — re-predict งานปักหมุด (5 งาน applied, ค่ากลาง 456k-1076k)

### Deploy (push→pull→migrate→repredict)
- 12 commit pushed → VPS git pull ff → init_schema (v124 median + v125 deadline_time)
- repredict --apply: 5 งานปักหมุด ได้ prediction ใหม่ (ทั้งหมด "ใหม่" ไม่ทับเดิม)
- services = oneshot timer → ใช้โค้ดใหม่อัตโนมัติ ไม่ต้อง restart

### Followup
- ⚠️ Sebastian_Customer_DB.py __main__ มี smoke test ที่ insert test customer/project ลง prod
  (รันตอน migrate) — ครั้งหน้าใช้ init_schema() ตรงๆ. มี test data Uxxxxxxxxx_TEST ค้าง prod (cleanup ได้)
- competitor_trend._area_where ยังไม่มี water_subtype filter (recency series งานน้ำปน)
- ถนนหินคลุก/ลูกรัง (~42%) ยังไม่แยก subtype ที่ 3 (n=39<80)
- งาน >10ลบ ไม่มี handling (นอกตลาดกัญจน์)

## งานที่ N+120: ส่ง D0 ครบวงจร 2 งาน + แก้ bug ราคา (2026-06-12)

### สถานะ: ✅ ส่งแล้ว 4 ลูกค้า × 2 งาน (resend_d0_jobs.py --all --live)

### Context
งาน 69059227331 (ถนนคอนกรีต หนองเดิ่น) + 69059132412 (อาคารสำนักงานโพนทอง) ประมูล 12 มิ.ย. 9-12 น.
ตอนเข้า LINE ครั้งแรกปักหมุดไม่ได้ (ระบบยังไม่นิ่ง) → resend ครบวงจร approval-gated (กัญจน์ก่อน→approve→ทุกคน)

### สร้าง resend_d0_jobs.py
- --list / --customer(เฟส1) / --all-except / --all, dry-run default
- การ์ด = format_notification D0 (intel/ราคา logic ใหม่) + ⏰เวลา + 📄ลิงก์ + ⭐follow-link (text, ตาม N+108)
- --resolve-deadline: เติมวัน+เวลาสด (DocZip) ถ้าขาด

### Bug/fix ที่กัญจน์จับได้ระหว่างตรวจราคา (สำคัญ)
1. 🐛 **ลิงก์ประกาศ** — procsearch.sch สร้างจาก projectId ไม่ได้ (E4514). ของจริง = view-pdf-file?templateId=buildName2
   (จาก infoProcureDocAnnounZip). `process5_http_client.get_announce_pdf_url()`. verified WebFetch→PDF จริง
2. 🐛 **asphalt keyword** — "แอสฟัสต์คอนกรีต" (สะกดผิด) หลุดเข้า concrete pool → _ASPHALT_KW root "แอสฟั".
   หนองเดิ่นมีแอสฟัลต์ปน concrete 7 งาน → แก้แล้ว concrete median 40% (เดิม 38% ปน)
3. ➕ **building new/reno** — อาคารปรับปรุง 17.8% vs สร้างใหม่ 12.4% (+5.4). building_kind() เฉพาะอาคาร
   (research: ถนน/น้ำ confound DOH). docs/research_building_reno_2026_06_12.md

### Followup
- ขยาย new/reno → ถนน(−5)/แหล่งน้ำ(+3) ใน local market (DOH ตัดแล้ว gap เหลือ ~3-5 จุด) + fallback กัน pool บางเกิน
- ไฟฟ้า/ราง: งานปรับปรุงน้อย (n=4/11) แยกไม่ได้ รอข้อมูล
- repredict 5 followed jobs เดิม + งานใหม่ ด้วย asphalt fix (อาจมี concrete ปน)
- เก็บ templateId ตอน enrichment (เลี่ยง API call ลิงก์ตอนส่ง)

## งานที่ N+121: Price Prediction Audit View — สร้าง + DEPLOYED (2026-06-12)

### สถานะ: ✅ เสร็จ + LIVE บน VPS (commits bf1972e→07c9b41)

### สิ่งที่ทำ
หน้า internal `/audit` (auth `BMS_AUDIT_KEY`) ให้กัญจน์ดูทุกการทำนายราคา + กดดูวิธีคิด+ข้อมูลดิบ
แช่แข็ง ณ ตอนทำนาย (audit-grade) + closed-loop คาด vs จริง. ผ่าน brainstorm→spec→plan→TDD.
- `explain_json` snapshot (inputs/classify/scope/analysis/raw_records/output) ใน price_predictions (_migrate_v126)
- capture ที่ `_build_explain` ใน cgd_intel (fail-open: พังไม่กระทบ prediction/ส่งงาน)
- wire ที่ save_prediction (LINE_Sender + repredict)
- `/audit` list + `/audit/{id}` detail ใน bms_api (shared-secret)

### ผล
- TDD 5/5 PASS (รวม invariant: re-predict ไม่ลบ actual_price/closed-loop)
- Deploy VPS: pull 8d29767→07c9b41, migration บน live DB (explain_json=True), restart bms-api
  verify no-key=401 / with-key=200 ✅
- URL: https://api.butler-bms.com/audit?key=*** (internal)

### Followup
- Sophia gate: รองาน D0 ใหม่ที่มี explain จริง → dispatch ตรวจ output ตรงกับที่ส่งลูกค้า
- การทำนายเก่า (ก่อน deploy) = "ไม่มีข้อมูล explain" (ปกติ)

## งานที่ N+122: Audit View v2 (ชื่องาน/stage/PRELIM/หมวดงาน) — DEPLOYED (2026-06-12)

### สถานะ: ✅ เสร็จ + LIVE บน VPS (commits 72c95b5→5a38d7d)

### สิ่งที่ทำ
ต่อยอด /audit ตามที่กัญจน์ขอ 4 ข้อ (brainstorm→spec→plan→TDD):
- ชื่องาน (join projects_seen) + stage B0→D0→PRELIM→W0 (จาก followed_jobs, ก้าวหน้าสุด)
- ราคา PRELIM + คาด vs จริง(เบื้องต้น) — prelim_* cols (v127, แยกจาก official), capture ที่ prelim notification
- บล็อกหมวดงาน: หมวด/หมวดย่อย/ประเภท(สร้างใหม่-ปรับปรุง)/ระบอบตลาด → label ไทย

### ผล
- TDD 9/9 PASS (รวม invariant: prelim ไม่แตะ official actual_price)
- Deploy: ติด .git root-owned (sudo git เก่า) → แก้ chown -R bms:bms .git → pull/migration/restart สำเร็จ (prelim_price=True, active, 200)

### Followup
- prelim ราคาเก็บงานใหม่ที่ถึง PRELIM หลัง deploy (ชื่อ+stage+หมวดงาน เห็นทันที 7 งาน backfill)
- Sophia gate: ตรวจ prelim_*/explain เมื่อมีข้อมูลจริงสะสม

## งานที่ N+123: แก้บั๊กคาดราคางานพื้นที่เป้าหมาย (resolve + province fallback) — LIVE (2026-06-12)

### สถานะ: ✅ เสร็จ + verify production (commits 3c41ad5, 4e7e6b7)

### Root cause (systematic-debugging, 2 ชั้น)
งานรั้ว 69069138608 (อ.บึงโขงหลง = พื้นที่เป้าหมาย) ไม่มีราคาคาด ทั้งที่บึงกาฬมีรั้ว 8 ราย:
1. **resolve_location เพี้ยน:** geo (พิกัด, dist 7km) snap ข้ามอำเภอ → คืน (ตำบลบึงโขงหลง, อ.เซกา) = คู่ไม่มีจริง → _fetch 0
2. **scope-local ไม่ fallback:** อ.บึงโขงหลง 0 precedent งานรั้ว (8 งานอยู่อำเภออื่น) → None

### Fix
1. `_reconcile_amphoe` — ตำบล unique→1 อำเภอ เชื่อตำบล>geo (N+116 structured>geo)
2. `province fallback` ใน _build_intel — อำเภอว่าง+จังหวัด distinct≥3 → คาดจากจังหวัด+ป้าย "ข้ามพื้นที่ เชื่อมั่นต่ำ", explain scope="จังหวัด (ข้ามพื้นที่)". <3 = ยัง None
+ deploy.sh/verify_job.sh + .gitattributes (sh=LF)

### ผล
- verify VPS: resolve=บึงโขงหลง ✅, ผลคาดราคา=มีราคาคาด ✅
- TDD 6 test (resolve_amphoe 4 + province_fallback 2) + regression 10 ไฟล์ผ่าน
- **เจอจาก audit view human-check ครั้งแรก** = ฟีเจอร์พิสูจน์คุณค่า

### Followup
- re-predict งานรั้วให้โผล่ใน /audit (repredict_followed --apply)

---

## งานที่ N+124: Predictor Credibility Layers — design spec (2026-06-13)

### สถานะ: 📝 design เสร็จ (รอ implement) — เอกสารล้วน ยังไม่แตะโค้ด predictor

### ที่มา (closed-loop จริง 2 งาน เปิดราคา 12 มิ.ย.)
งาน 69059227331 (ถนนหนองเดิ่น): ระบบคาด 1.17–1.23M (ลด 40%) · จริง 1,334,500 (ลด 33.7%) ❌ หลุดกรอบ
- root cause: filter เข้ม (concrete+new+floor) → 3 ปีล่าสุดในตำบลว่าง → include_old ย้อน 2562 → มงคลธรรมเจ้าเดียวเก่า 7 ปี ทับอำเภอบุ่งคล้าสด (32%≈จริง)
- เทียบ 69059132412 (อาคารโพนทอง scope อำเภอ): คาดแม่น ✅

### ผล (design กับกัญจน์ทั้งวัน)
- spec `docs/superpowers/specs/2026-06-12-predictor-credibility-layers-design.md`
- 2 ตัวแปรหลัก: **Z** (เรตสนาม: #งาน+#บริษัทอิสระในตำบล → blend ตำบล↔อำเภอ) · **C** (เจ้าใหญ่จะมายื่นไหม → overlay) — แยกแกนกัน
- หลักกัน double-count: แยกเจ้าใหญ่ออกก่อนคำนวณเรตสนาม
- ภาคผนวก A: Decision Flow 5 เฟส (อนาคต render บน /audit)
- ยุบ L2(vs-self)+L4 = โมเดลพฤติกรรมรายเจ้า · ตัด vs-market (เหลือ fallback newcomer)

### 🌙 ทำคืน 13 มิ.ย. (autonomous ตอนกัญจน์นอน) — commit local เท่านั้น ยังไม่ push/deploy
1. **วิจัย Z** (0a68031): ทฤษฎี Bühlmann k=EPV/VHM=3.2 + backtest 2,961 งาน (RMSE ดีสุด k=3-5) ตรงกัน
   → สูตร **Z=n/(n+3)**, n ดิบ (eff ไม่ช่วย), ผูกขาด→C ไม่ใช่ Z. doc `docs/research/2026-06-13-z-formula-credibility.md`
2. **วิจัย C** (e3e5d2f): frequency แกนหลัก (เจ้าถิ่น≥5→90% · ขาจร→13%). **แต่ C-จาก-win over-predict** (มงคลธรรม
   C=90% แต่ไม่มาจริง) → C ยังไม่พร้อม drive overlay จนกว่ามี all-bidders. doc `2026-06-13-c-participation.md`
3. **Implement helper** (18e1c47): `credibility_z()` + `blend_disc()` ใน cgd_intel + TDD (test_z_blend 3 ผ่าน) · full suite 22/22 ผ่าน

### 🌅 เช้า 13 มิ.ย. — wire เสร็จ (e3fd31e)
- ✅ **wire blend_disc เข้า `_build_intel`** (surgical: เฉพาะ path ตำบลบาง tn<5 ที่ดึงอำเภออยู่แล้ว)
  - กัญจน์เลือกป้าย UX: **"อิงตำบล+อำเภอ · น้ำหนักตำบล X%"** (โปร่งใส โชว์น้ำหนัก)
  - TDD +1 (`test_build_intel_blends_thin_tambon`) · suite 22/22 + price/trend/repredict/audit ผ่านหมด
  - หมายเหตุ: `test_build_intel_dual` ยังผ่าน (substring "อิงตำบล" ใน label blend) — tighten ได้ทีหลัง

### 🚀 DEPLOYED (13 มิ.ย. 13:54) — push 50a74f1 + deploy.sh บน VPS (service active, health 200)
- **blind test 2 เคส (ก่อน deploy):**
  - โพธิ์หมากแข้ง 69059075454 (ตำบลดี สด+2เจ้า): เดิม blend ทื่อ→709K ดุเกิน vs จริง 740K → **เพิ่ม gate** (50a74f1) → ตำบลล้วน 730K ห่างจริง 10K ✅
  - หนองเดิ่น 69059227331 (ตำบลสงสัย): blend → ~38% (1.26M) ยังดุเกินจริง 33.7% (1.33M) — **L1 แก้ไม่หาย ต้อง L3**
- **gate:** blend เฉพาะตำบล "น่าสงสัย" (t_old หรือ distinct<2) · ตำบลดี→ตำบลล้วน (do-no-harm)
- **บทเรียน:** L1 credibility blend = improvement เล็ก+ปลอดภัย ไม่ใช่ game-changer (backtest RMSE 8.92→8.75)

### 📍 END OF DAY 13 มิ.ย. — full arc (N+124..N+135)
**Deployed บน prod แล้ว 3 รอบ:** L1 Z-blend+gate · L3 recency · *(win-headline+1a รอ deploy)*
| commit | คือ | prod |
|---|---|---|
| L1 Z-blend + suspect-gate | ตำบลสงสัย(เก่า/เจ้าเดียว)→blend, ตำบลดี→ตำบลล้วน | ✅ deployed |
| L3 recency (half-life 1) | ถ่วง percentile ตามอายุ, ข้อมูลเก่าจาง | ✅ deployed |
| `c55269d` win-headline a/b/c | แนะนำยื่นราคา→โอกาสชนะ 75/50/25% (win≠แม่น) | ⏳ **รอ deploy** |
| `64b7cf3` 1a all-bidders | poller เก็บ bidders ตอน prelim | ⏳ **รอ deploy** |
| `dfff803` spec + `c1ad730` plan | all-bidders 1b (broad capture, ต่อ winner_sweep) | 📋 รอ implement |

**บทเรียนใหญ่:** "แม่น (RMSE) ≠ ชนะ" — โมเดล optimize ผิด objective. asymmetric: แพ้งาน>>กำไรบาง → headline a/b/c. · L1/L3 = improvement เล็ก+ปลอดภัย ไม่ใช่ game-changer (backtest RMSE ขยับนิดเดียว). · n_eff = wash (ไม่ทำ).

### ▶ RESUME รอบหน้า
1. **deploy 2 commit ค้าง** (win-headline+1a): `bash scripts/deploy.sh` + `repredict_followed --apply`
2. **implement 1b** จาก `docs/superpowers/plans/2026-06-13-allbidders-capture-1b.md` (4 tasks TDD พร้อม)
3. แล้ว เฟส 2 (ใช้ all-bidders ใน predictor) · B (self-calibrate win-rate) · C
- memory: project_scope_selection_bug · spec `2026-06-12-predictor-credibility-layers-design.md`

---

## งานที่ N+125: CHECKPOINT — ก่อนเปลี่ยน session (2026-06-13)

### สถานะ: ⏸ pause เปลี่ยน session (predictor วันมหากาพย์เสร็จ, รอ implement 1b)

### ✅ เสร็จแล้ว session นี้ (deployed prod, commit 54bd7c8)
L1 Z-blend(n/(n+3))+gate · L3 recency(half-life 1) · win-headline a/b/c · 1a all-bidders capture · 1b spec+plan

### 🎯 NEXT ACTION (session หน้า)
- **Implement 1b** จาก `docs/superpowers/plans/2026-06-13-allbidders-capture-1b.md` (4 tasks TDD)
- skill: **`superpowers:executing-plans`** · ✅ **consent ทำบน main แล้ว** (ไม่แยก branch)
- ⚠️ verify Task 3: `sweep_egp` มี caller อื่นนอก main ไหม ก่อนเปลี่ยน return เป็น tuple
- test: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/<test>.py`

### ค้าง/ระวัง
- prod=VPS, deploy `bash scripts/deploy.sh` (กัญจน์รันเอง — SSH จาก dev ไม่ได้)
- หลัง 1b: เฟส 2 (all-bidders ใน predictor) · B (self-calibrate win-rate) · C · backfill

---

## งานที่ N+126: Implement 1b all-bidders capture — DONE (รอ deploy) (2026-06-13)

### สถานะ: ✅ code เสร็จ (3 commits) · ⏸ รอ push+deploy VPS (Task 4 manual)

### สิ่งที่ทำ (TDD ตาม plan 4 tasks)
- **T1** `efee2dc` record_bid_results name-fallback — dedup key = tin or `name:<name>` → เก็บ bidder ไม่มี TIN ครบ (เดิม PK ชนเหลือ 1) · regression competitor_trend ผ่าน (อ่าน bidder_name)
- **T2** `c719bc8` `persist_bid_results()` helper — sequential (1 connection) + fail-open (พังต่อ job ไม่ทำ sweep ล้ม)
- **T3** `a01619f` `sweep_egp` คืน `(winners, bidders_by_jid)` + main เรียก persist → เก็บ all-bidders (winner+loser+prelim) ลง bid_results · ไม่เพิ่ม API call

### Verify
- เช็ค caller `sweep_egp` = 1 ตัวเดียว (main:490) ก่อนเปลี่ยน return เป็น tuple ✅ (resolve checkpoint concern)
- 4 test ผ่านหมด: bid_results / winner_sweep / winner_poller / competitor_trend_series

### Deploy ✅ (2026-06-13)
- push `4c61b5c` → VPS `deploy.sh` fast-forward สำเร็จ · schema v1.13 ready · bms-api active
- **baseline `bid_results jobs: 1`** (ก่อน 1b เก็บผ่าน path 1a poller เท่านั้น) → เทียบหลัง winner_sweep timer รอบถัดไป ควรพุ่งขึ้น (winner+loser+prelim)

### Followup
- ⏳ verify หลัง winner_sweep timer รันรอบถัดไป — bid_results jobs ต้อง > 1 มากๆ
- ถัดไป: เฟส 2 (ใช้ all-bidders ใน predictor) · B (self-calibrate win-rate)

## งานที่ N+127: เฟส 2A Backfill Engine — code DONE (รอ run VPS) (2026-06-14)

### สถานะ: ✅ code เสร็จ (subagent-driven, 4 tasks TDD) · ⏸ รอ push + run VPS (Task 5 manual)

### บริบท (brainstorm → spec → plan → implement)
เฟส 2 (all-bidders ใน predictor) แตกเป็น **2A (evidence/backfill)** + **2B (dominant-detection predictor, ทีหลังเมื่อมีข้อมูล)**. north-star ของกัญจน์: จับ pattern "เจ้าใหญ่ชนะขาดลอย" (เช่น หนองเดิ่น/งาน 67129346506 ผู้ชนะลดลึกกว่ากลุ่ม ~20%) → เสนอราคา 2 ฉากทัศน์ (เจ้าใหญ่มา/ไม่มา). 2A = เติม loser history ก่อน
- spec: `docs/superpowers/specs/2026-06-13-allbidders-backfill-2a-design.md`
- plan: `docs/superpowers/plans/2026-06-13-allbidders-backfill-2a.md`
- probe ยืนยัน: `getProcureResult` คืน full field งานเก่า (งานทดสอบ 46 ผู้ยื่น + losers)

### สิ่งที่ทำ — `scripts/backfill_bidders.py` (writer ล้วน ไม่แตะ predictor)
- **T1** select_candidates — filter cgd_winners (จังหวัด/COMPETITIVE_SET/fy/win_price>0) + ตัดที่มีใน bid_results + seen
- **T2** backfill_one — fetch+store, **`fetched_at=announce_date`** (recency 2B ถูก), fail-open (stored/empty/error)
- **T3** run loop — checkpoint `backfill_seen.json` (resume 2 ชั้น) + progress ETA
- **T4** CLI main() — `--provinces/--fy/--limit/--dry-run`
- ทุก task: spec-review + code-quality-review (subagent) + final holistic review = Ready to ship
- review fixes: limit is-not-None · log {} path · ETA · drop _t alias · test dry_run/limit · 2B note (TIN-fallback `name:%`)

### Verify
- test `scripts/test_backfill_bidders.py` ผ่านหมด (select/backfill_one/run-resume/dry_run+limit)
- smoke `--dry-run` บน dev = candidates 0 (cgd_winners ว่าง) ไม่ traceback
- scope: นครพนม+บึงกาฬ · competitive set · FY2567-2569 ~3-4K งาน ≈ 2-3 ชม.

### Followup — Task 5 (manual, VPS)
1. `git push origin main` → VPS `bash scripts/deploy.sh`
2. **R1 gate:** `--dry-run` นับ candidate (ถ้า << ~3-4K = cgd_winners ไม่ครบ → ทบทวน Approach B)
3. probe `--limit 100` (วัด error/rate-limit) → 4. full run (nohup) → 5. verify bid_results losers>0
- หลัง 2A สะสมข้อมูล → brainstorm **2B** (dominant-detection) ด้วย evidence จริง

### 🐛 Deploy debug (2026-06-14) — R1 ผ่าน แต่ probe เจอ rate-limit → fix cooldown
- R1 gate: **candidates 3046** ✅ (cgd_winners บน VPS ครบ ไม่ต้อง Approach B)
- probe --limit 100: **stored=26 error=74** — พังรวดหลัง ~job 26
- diag (`_diag_egp.py`, single call): token_len 252, **status 200**, body ครบ → endpoint/token ปกติ
- root cause: **generateToken rate-limit เมื่อยิงเร็ว** (~26-30/รอบ ตรง memory) ไม่ใช่ WAF/IP block (ถ้าบล็อกต้อง 0 สำเร็จ)
- **fix `7091b75`:** batch-cooldown ทุก 25 งาน พัก 130s (>2 นาที, winner_sweep pattern) + CLI `--cooldown-every/--cooldown-sec` · TDD ผ่าน
- ⏳ next: re-probe ยืนยัน error ต่ำ → full run (~5-6 ชม. cooldown รวม, overnight) → verify · ลบ `_diag_egp.py` ทีหลัง

### ✅ Resolution (2026-06-14) — cooldown ใช้ได้ + full run started
- ⚠️ บทเรียน: probe2 (limit 60) error สูง **เพราะรัน 2 process ชนกัน** (เขียน log เดียวกัน, ยิง generateToken 2 เท่า) ไม่ใช่ cooldown พัง
- clean probe (limit 30, **process เดียว**): **stored=30 empty=0 error=0** ✅ → cooldown 25/130s แก้ rate-limit ได้จริง
- **full run started** PID 1133624 (nohup, ~2,900 งานเหลือ, seen=112 เสร็จแล้ว) → `/tmp/backfill_full.log` · ~5-6 ชม. overnight
- monitor: `tail -n6 /tmp/backfill_full.log` · done: `grep เสร็จ ...`
- พรุ่งนี้: verify losers>0 → ลบ `_diag_egp.py` → brainstorm **2B dominant-detection** ด้วย evidence จริง
- ⚠️ กฎ: backfill ห้ามรันซ้อน (1 process เท่านั้น) ไม่งั้น token throttle

### 🐛 Full run ตันที่ ~150 → auto-trickle (2026-06-14 เช้า)
- full run จบแบบ **stored=149 error=2770** — cooldown 130s/25 ทนได้ ~149 งาน แล้วโดน throttle ยาวจนจบ run
- diag หลัง run: **status 200** → IP **ฟื้นเอง** (block ชั่วคราว ไม่ถาวร) → VPS ยิงได้ ~150/ช่วง แล้วต้องพักนาน (ชม.) — ตรง INC-001
- มีข้อมูลแล้ว: **bid_results jobs=278, rows=1371, losers=1094** (evidence ตั้งต้น 2B พอ)
- **fix: auto-trickle** (ไม่เขียนโค้ดใหม่) — bash loop `--limit 100 --cooldown-every 999` ×30 batch เว้น 25 นาที/batch (gap = ตัว recover จริง). resumable ข้ามงานเสร็จ. PID 1159209 → `/tmp/backfill_trickle.log` · ~1 วัน hands-off
- monitor: `grep -E "เสร็จ|batch" /tmp/backfill_trickle.log | tail`
- fallback ถ้า trickle ตัน: Approach B (รันจากเครื่องบ้าน residential + sync)
- ขนาน: เริ่ม brainstorm 2B ได้เลย (มี evidence 1094 losers)

---

## งานที่ N+128: เฟส 2B Dominant-Detection — code DONE (รอ deploy) (2026-06-14)

### สถานะ: ✅ code เสร็จ (subagent-driven 4 tasks TDD + 3-stage review) · ⏸ รอ push+deploy · 2A trickle ยังรัน

### Evidence ที่ใช้ออกแบบ (จาก backfill จริง 224 auctions)
- `_analyze_bidfield.py`: ขาดลอย gap>10% = **24%** · gap>20% = 8% · กลุ่มเกาะแน่น **CV 3.9%** · เฉลี่ย 5.9 ราย/งาน
- → 2B graceful: โชว์เฉพาะ scope ที่มีโครงสร้างขาดลอย (76% สูสีใช้ a/b/c เดิม)

### สิ่งที่ทำ — `scripts/bid_field.py` (โมดูลใหม่, ไม่แตะ headline a/b/c)
- **T1** `analyze_field` — tiered (Tier1 ระบุชื่อเจ้าใหญ่+show-rate · Tier2 structural · Tier0 gate)
- **T2** `field_lines` — baht 2 ฉากทัศน์ (เจ้าใหญ่มา/ไม่มา)
- **T3** `_field_auctions` — read bid_results JOIN cgd_winners(budget) + ตัด outlier disc>60%
- **T4** `field_block` + เชื่อมเข้า `cgd_intel._build_intel:588` (4 บรรทัด ต่อท้าย predict_lines, graceful)
- review fixes: tiebreak by gap (ไม่ใช่ชื่อไทย) · docstring keys · `_field_auctions` catch DatabaseError (parent) กันการ์ดพัง

### Verify
- `test_bid_field.py` ผ่านหมด (tier1/2/0+gate · field_lines · read+outlier · end-to-end+gate)
- regression `test_cgd_intel.py` + `test_winrate.py` ผ่าน (field_block คืน [] เมื่อ bid_results ว่าง → predictor เดิมไม่กระทบ)
- spec/plan: `docs/superpowers/{specs,plans}/2026-06-14-dominant-detection-2b*`

### ✅ v2 PIVOT + LIVE (2026-06-14) — evidence พลิก landslide → market-leader
- verify จริงต่อ scope: **landslide หายาก 5-10%** (ไม่ใช่ 24% aggregate) · เจ้าตลาดชนะ **"ชิดๆ" gap~4จุด** → exploit "ไม่มา=กำไรงาม" ใช้ไม่ได้
- **แต่มีเจ้าตลาดชัด** → pivot จับ **win-frequency**: `analyze_field` คืน `leaders[]` (ลง≥5 ∧ ชนะ≥40%) · `field_lines` โชว์ "เจ้าตลาด + ชนะ X% + ลดเฉลี่ย Y% + เจ้าตลาดลดได้ถึง Z% ต้องลดลึกกว่านี้"
- fix: "ต้องลด" ใช้ disc **ลึกสุด** ในกลุ่ม (ไม่ใช่คนชนะเยอะสุด) กันแนะนำต่ำเกินจนแพ้
- **LIVE บน prod** (commit 9f31e83) · verify จริง 4/5 scope จับเจ้าตลาด: นครพนม=บัญชาศรี/เมืองทอง · บึงกาฬ=ริชบียอนด์/ศิรประภา/พัฒนกิจ
- test_bid_field ผ่านหมด · regression predictor เดิมผ่าน · spec อัปเดต v2 (§6b/§7b)

### Followup
- ⏳ รอกัญจน์ sanity-check: เจ้าตลาด + %ลด ตรงตลาดจริงไหม · threshold (ชนะ40%/ลง5) เหมาะไหม
- 2A trickle ยังรัน (PID 1159209) → scope อื่นจะ activate เพิ่มเมื่อข้อมูลพอ
- เมื่อ trickle ครบ: review threshold final + ลบ debug scripts (`_diag_egp.py`, `_analyze_bidfield.py`, `_verify_2b.py`)

---

## งานที่ N+129: CHECKPOINT — ก่อนเปลี่ยน session (2026-06-14)

### สถานะ: ⏸ pause เปลี่ยน session (กัญจน์จะติด rate limit) — กำลัง iterate UX scope เจ้าตลาด 2B

### ✅ เสร็จแล้ว session นี้ (เฟส 2 ครบ 1b+2A+2B — ทั้งหมด LIVE บน prod)
- **1b** all-bidders capture (winner_sweep) · **2A** backfill engine + auto-trickle (PID 1159209 ยังรัน, มี ~352 jobs FY67-68)
- **2B v2 เจ้าตลาด intel** (pivot จาก landslide หลัง evidence จริง: landslide หายาก 5-10%, แต่เจ้าตลาดชัด ชนะ 48-83%)
- iterate scope การ์ด: จังหวัด → **ล่าสุด `bb5d95e` = ตำบล→อำเภอ (graceful hide, ไม่ขึ้นจังหวัด) + ป้าย scope**
- ทุก commit push แล้ว (origin/main = bb5d95e) · test_bid_field + regression predictor ผ่านหมด

### 🎯 NEXT ACTION (session หน้า)
1. **รอกัญจน์ redeploy VPS + รัน `_show_card.py`** (commit bb5d95e) — ดูว่าเจ้าตลาด ตำบล/อำเภอ โชว์หรือ hide
   - คำสั่ง VPS: `cd /opt/bms/app && git pull && bash scripts/deploy.sh && BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python scripts/_show_card.py`
   - คาด: พื้นที่เป้าหมาย (นาทม/บึงโขงหลง) ข้อมูล <5 → **เจ้าตลาด hide** (ถูกต้องตามที่กัญจน์ขอ "ตำบลถ้าพอ ไม่พอไม่โชว์")
2. ตาม result: ถ้า hide เยอะไป → คุยปรับ (ลด MIN_AUCTIONS? หรือยอมรับ?) · ถ้าโชว์ดี → 2B จบ
3. **open UX**: ควรมีคำเชื่อม a/b/c(ราคาตำบล ลดดุ 28-41%) vs เจ้าตลาด(ลด 14-29%) ไหม — กัญจน์ถามแล้วยังไม่สรุป

### ค้าง/ระวัง
- ⚠️ deploy = กัญจน์รันเอง VPS (SSH จาก dev ไม่ได้) · backfill ห้ามรันซ้อน (1 process)
- debug scripts รอลบ: `_diag_egp.py` `_analyze_bidfield.py` `_verify_2b.py` `_show_card.py`
- ถัดไปหลัง 2B: **B = self-calibrate win-rate** (headline a/b/c ยังเป็น heuristic) · trickle เติมข้อมูล
- spec/plan 2B: `docs/superpowers/{specs,plans}/2026-06-14-dominant-detection-2b*` (spec มี v2 pivot §6b/§7b)

---

## งานที่ N+130: Discovery alert noise — root cause = WAF Turnstile + tier-1 fix (2026-06-14)

### สถานะ: ✅ เสร็จ (tier 1) — รอ deploy VPS เพื่อมีผล

### Root cause (ขุด journalctl VPS — systematic debugging)
- กัญจน์กังวล Discord เด้ง 🟠 NO_DATA + "พลาด discovery รอบ 19:00" ซ้ำ 2 รอบ
- **smoking gun** (full-nkp 12:30 UTC): `🔑 token OK เหลือ 1507s` → `❌ validateCfTurnTile` ทันที
  → token สด แต่ server ปฏิเสธ = **Cloudflare Turnstile/WAF challenge IP ของ VPS** (INC-001 กลับมา) ไม่ใช่ token หมดอายุ
- challenge เป็น **intermittent** (catch-up 19:10/19:40 scan 40 ผ่าน) → ยังไม่มีงานหายจริง + ตลาดเงียบ (announce ล่าสุด 06-12)
- cascade: reject → all_recs ว่าง → heartbeat no_data → (a) deadman NO_DATA (b) catch-up เด้ง "พลาด slot" ทุก harvest cycle

### Fix (tier 1 — 3 ไฟล์, ไม่แตะ data)
- `Sebastian_Province_Discovery.py`: แก้ข้อความ "token หมดอายุ" (หลอก) → "WAF/Cloudflare challenge IP (token สด)" + heartbeat ติด `reason=server_reject`
- `health_deadman.py`: NO_DATA alert รายงาน fact "server reject แม้ token สด" (ไม่เดาสาเหตุเกิน)
- `discovery_catchup.py`: `CATCHUP_RETRY_SEC=20m` — กัน re-fire ซ้ำตอน WAF (ใช้ ts heartbeat = last attempt). sim ยืนยัน incident 2 spam → เหลือ 1 + กู้คืนทัน
- py_compile ผ่านทั้ง 3 · ยังไม่ push

### Followup
- **ต้อง deploy VPS** ถึงมีผล: `cd /opt/bms/app && git pull && bash scripts/deploy.sh`
- tier 2 (ถ้าเอา): retry/backoff เมื่อเจอ Turnstile · tier 3: ADR-003 residential IP fallback ([[project_incident_control_plane]])
- full-sweep catch-up (lines 113-129) ยังไม่ใส่ cooldown — secondary, ใช้ marker คนละตัว (followup ถ้า spam)
- memory: `project_discovery_nodata_waf_turnstile`

---

## งานที่ N+131: Discovery WAF/JA3 durable fix (tier 2) — code เสร็จ (2026-06-14)

### สถานะ: ✅ DEPLOYED + verified จาก VPS (5997fdf) — 0 challenge ⇒ JA3 = root cause ยืนยัน

### สิ่งที่ทำ (subagent-driven, brainstorm→spec→plan→execute)
- ต้นตอ tier-1 = WAF Turnstile (N+130). tier-2 นี้แก้ root cause = **JA3 fingerprint**: `requests` ธรรมดา → Cloudflare จับเป็น bot
- หลักฐาน: RSS เจอปัญหาเดียวกันบนโดเมนเดียวกัน แก้ด้วย curl_cffi chrome120 แล้ว (รันบน VPS ได้)
- **Task 1** `_is_challenge` (body marker > status + content-type) · **Task 2A** `_get` → curl_cffi impersonate chrome120 + ตัด UA + exception ไม่กลืน bug + CF_CHALLENGE · **Task 2B** retry/backoff (2/4/8s+jitter ×3) + CF_RECOVERED
- spec: `docs/superpowers/specs/2026-06-14-discovery-waf-ja3-fix-design.md` (กัญจน์ review 5 condition) · plan: `docs/superpowers/plans/2026-06-14-discovery-waf-ja3-fix.md`
- test ครบ (`scripts/test_discovery_http.py` 7 ตัว) ผ่านหมด · py_compile OK · **smoke จริง: count_d0(นครพนม)=877/88หน้า ผ่าน curl_cffi**
- commits: afe3ee7 (Task1) · a3d2e86+a32da05 (Task2A+quality fix) · 6fbe72d (Task2B)

### ✅ เสร็จครบ
1. Task 0 pin curl_cffi==0.15.0 (VPS+local ตรง) `5997fdf`
2. push + deploy VPS สำเร็จ (Schema v1.13, bms-api active)
3. **verify จาก VPS: discovery scan นครพนม 877/บึงกาฬ 445 สำเร็จ 0 challenge 0 retry** = JA3 คือเหตุจริง (IP เดิม+token เดิม เปลี่ยนแค่ fingerprint = ผ่าน)

### Followup (เบา)
- ติดตาม metric `journalctl -u 'bms-province-discovery*' | grep -c CF_CHALLENGE` 1-2 วัน ยืนยันอีกชั้น (คาดใกล้ 0)
- full-sweep catch-up cooldown ยังไม่ทำ (secondary, §9 plan) — ทำถ้ายัง spam
- ADR-003 defer ต่อ (มีหลักฐานว่าไม่จำเป็น)
- กลับไป 2B เจ้าตลาด/self-calibrate (checkpoint N+129) ได้

---

## งานที่ N+132: งาน B — conditional win-rate (self-calibrate ตามจำนวนผู้ยื่น) — code DONE (รอ deploy) (2026-06-15)

### สถานะ: ✅ code+test เสร็จบน dev (subagent-driven 4 tasks) — รอ deploy VPS + ดูการ์ดจริง

### Root cause / สิ่งที่ทำ
- heuristic เดิม: a/b/c win% = 75/50/25 ตายตัว (percentile rank ผู้ชนะ). insight: ในประมูลซองปิด ชนะ ⇔ ลดดุกว่าผู้ชนะ ⇒ winner-CDF = percentile เดิม → "full-field unconditional" = ของซ้ำ
- **B = conditional ตามจำนวนผู้ยื่น** (จุดที่ full-field 2A เพิ่มค่าจริง): F_bid (CDF disc ผู้ยื่นรายเดียว) + n stats (mean±SD) → win% = `F_bid(disc)^k` · ตาราง 3 คอลัมน์ dynamic = mean−SD/mean/mean+SD ราย
- กัญจน์ขอเพิ่ม: บรรทัด `📈 สถิติจาก N งาน · M ผู้ยื่น` (sample size = ความน่าเชื่อถือ)

### Fix / ผล
- `bid_field.py`: `_cdf` + `winrate_grid` (pure, gate None เมื่อ <5 auctions) + `winrate_lines` (render) + `field_and_winrate` (อ่าน `_field_auctions` **รอบเดียว** ป้อนทั้ง 2B+B)
- `cgd_intel.predict()`: แทนบล็อก a/b/c ด้วยตาราง B เมื่อมี grid · ไม่มี → fallback `predict_lines` เดิม (graceful) · 2B เจ้าตลาดต่อท้ายเหมือนเดิม
- `test_winrate_grid.py`: 7 เคส (math F^k / columns mean±SD / monotonic / gate / render / end-to-end / gate-fallback) — ผ่านหมด
- backward-compat: test_winrate / test_bid_field / test_competitor_trend_series ผ่านหมด · py_compile OK
- spec: `docs/superpowers/specs/2026-06-15-conditional-winrate-b-design.md` · plan: `docs/superpowers/plans/2026-06-15-conditional-winrate-b.md`
- commits: 7f0e342 (T1) · 4b19e22 (T2) · 5924d01 (T3) + review fixes

### Followup
- **deploy VPS**: `cd /opt/bms/app && git pull && bash scripts/deploy.sh` แล้วดู `_show_card.py` — scope full-field ≥5 เห็นตาราง · scope บางเห็นการ์ดเดิม
- ตาราง B โผล่จริงต้องรอ backfill 2A ครบ (ตอนนี้ ~924/3032) — ยิ่งครบยิ่งหลาย scope
- ถัดไป: validate iid assumption (F^k vs winner-CDF จริง) หลัง trickle ครบ · R2 recency-weight F_bid (ถ้า drift)

---

## งานที่ N+133: B.1 — เลือกราคาแถวจาก win เป้าหมาย (invert F_bid) — code DONE (รอ push/deploy) (2026-06-15)

### สถานะ: ✅ code+test+review เสร็จ (b052b71 + footer fix) — รอ push + redeploy VPS

### Root cause (เจอจาก deploy จริง N+132)
- deploy แล้วการ์ดนาทมโชว์ตาราง B จริง แต่ output แย่: ราคา 3 แถวมาจาก winner p25/p75 → สนาม disc ลึก+แคบ ทำ **win% แบน 86-100% ทุกแถว** + **2 แถวยุบติดกัน** (1,222,800 vs 1,223,143 ต่าง 343 บาท) → ตารางไม่ช่วยตัดสินใจ

### Fix (B.1)
- เลิกใช้ winner p25/p75 เป็นราคาแถว → **คำนวณราคาที่ให้ win=target (75/50/25) ที่สนามปกติ** จาก inverse-CDF: `disc = quantile(bids, (t/100)^(1/k_mid))` · win% คอลัมน์ k = `(t/100)^(k/k_mid)` → คอลัมน์ตรงค่าเฉลี่ย = target เป๊ะ
- `winrate_grid(auctions, budget, targets=(75,50,25))` ตัด param `prices` · ตัด `_cdf` เพิ่ม `_quantile` · gate ราคายุบ <2 แถว → None (fallback)
- ripple: `field_and_winrate`/`predict()` เลิกส่ง prices
- smoke (data ต่อเนื่อง): คอลัมน์กลาง 75/50/25 เป๊ะ · ราคาไล่ระดับไม่ยุบ (1,138,622/1,171,015/1,218,701) ✅
- test 6 เคส + backward-compat ผ่านหมด · spec §10b อัปเดต · review = ready to merge

### Followup
- **push + redeploy VPS** แล้วดู `_show_card.py` นาทม → ควรเห็นตารางไล่ระดับมีความหมาย (ไม่ใช่ 86-100% แบน)
- **ปัญหา #3 ยังไม่แก้:** เลขงานตาราง (`_field_auctions`) ≠ บล็อกคู่แข่ง (winner-stats) — UX แยกประเด็น
- validate iid หลัง backfill ครบ (ตอนนี้ ~924/3032)

---

## งานที่ N+134: #3 ตาราง B ใช้ population เดียวกับราคา (project_ids) — code DONE (รอ deploy) (2026-06-15)

### สถานะ: ✅ code+test+review เสร็จ pushed (eb9457e) — รอ redeploy VPS

### Root cause (debug-mantra + breadcrumb prod)
- B.1 deploy แล้วเห็น "ตาราง 11 งาน" ข้าง "บล็อกคู่แข่ง ตำบล4/อำเภอ6" → งง
- breadcrumb: bid_results ตำบลนาทม = **4** (<5) → ตาราง fall-through ไป**อำเภอ = 11** (ไม่กรอง year/subtype) ส่วนคู่แข่งอำเภอ (กรอง) = 6
- 2 สาเหตุ: (1) table fall-through scope กว้างกว่าที่โชว์ (2) `_field_auctions` ไม่กรอง fiscal_year/subtype/nature ที่ price/`_fetch` กรอง

### Fix (option A — population เดียวกับราคา)
- `_field_auctions(... project_ids=)` → ดึงเฉพาะ id ที่ price ใช้ (`used_rows` กรองครบ) แทน scope-match กว้าง
- `_fetch` SELECT เพิ่ม `project_id` → `used_rows` มี id · `predict()` เลิก scope-loop ตำบล→อำเภอ ส่ง `_ids` จาก used_rows
- ป้าย `📈 จาก N งานที่มีข้อมูลผู้ยื่นครบ` (subset ≤ คู่แข่ง ชัดเจน — win-rate ใช้ได้เฉพาะงานที่รู้ผู้ยื่นครบ)
- review fixes: dedupe used_rows blend (audit n/raw_records ไม่ซ้ำ) · ลบ `field_block` (dead หลังเลิก loop)
- test +project_ids mode · backward-compat (cgd_intel/bid_field/winrate/competitor/road/water) ผ่านหมด

### Followup
- **redeploy VPS** → ดู `_show_card.py` นาทม: ตาราง "N งาน" ควร ≤ คู่แข่ง + population ตรงกัน (subtype/year เดียวกัน)
- tradeoff รับแล้ว: ตาราง B โผล่น้อยลง (กรองแคบ) จนกว่า backfill ครบ
- validate iid หลัง backfill ครบ

---

## งานที่ N+135: 🎯 Closed-loop validation แรกของ B.1 (งานจริง 69059374770) (2026-06-15)

### สถานะ: ✅ validation สำเร็จ — **filter จัดเต็ม + อ่านคอลัมน์ตรง n จริง = แม่น 0.04%** (n=1)

### เคส
- งานจริงกำลังประมูล: ถนน คสล. ต.โพธิ์หมากแข้ง อ.บึงโขงหลง จ.บึงกาฬ · งบ 971,000 · อบต. (scope ที่เคยเป็น [[project_scope_selection_bug]])
- ดึง id → `get_procurement_detail` → `format_notification` · PRELIM → `prelim_summary.fetch_prelim_summary`

### ผลจริง (PRELIM 15 มิ.ย. 12:05): ผู้ยื่น **5 ราย** · ต่ำสุด **690,000** (ลด **28.9%**)

### เทียบ — ไล่ filter หลายระดับ (รุ่น 50%, งบ 971k)
| filter | full-field | 50%-rung | ลด | ห่างจริง |
|---|---|---|---|---|
| road รวม (ไม่กรอง subtype) | 129 | 687,217 | 29.0% | 0.4% |
| concrete เท่านั้น | 86 | 670,395 | 31.0% | 2.0% |
| **จัดเต็ม (concrete+nat+mkt+wk+contested)** | **37** | 667,728 | 31.2% | 2.3% |

→ **ข้อสรุปพลิก:** filter จัดเต็ม **ก็ขึ้นตารางได้** (40 full-field ที่ scope จังหวัด ≥5) — ที่งานนี้ตารางไม่ขึ้นบน prod เพราะติด **scope local (ตำบล blend) <5** ไม่ใช่เพราะ filter เยอะ

### 🎯 insight คุณกัญจน์ — อ่านคอลัมน์ตรง n จริง (win=F_bid^k, k น้อย→ลดน้อยก็ชนะ)
เส้น 50%-win ต่อจำนวนผู้ยื่น (filter จัดเต็ม):
| ผู้ยื่น | 2 | **5 (จริง)** | 8 | 10 |
|---|---|---|---|---|
| ราคา 50% | 757,149 | **690,430** | 661,239 | 645,476 |
| ลด% | 22.0 | **28.9** | 31.9 | 33.5 |

**ที่ 5 ราย = 690,430 (ลด 28.9%) vs จริง 690,000 (ลด 28.9%) → ห่าง 430 บาท = 0.04% · ส่วนลดตรงทศนิยม** 🎯
+ สวิงคู่แข่ง 2→10 ราย = 757k→645k (**112,000**) ⇒ ยืนยันว่าตารางหลายคอลัมน์จำเป็น

### ข้อสรุป + ทิศทาง (decided by กัญจน์ 2026-06-15)
- ✅ ใช้ **filter จัดเต็ม** (เหมือนราคา ทุก dimension) — ไม่ผ่อน subtype
- ✅ **B′ = ผ่อนแค่ scope** (win-rate fallback ตำบล→อำเภอ→จังหวัด เมื่อ local <5) ให้ตารางขึ้น
- 🔜 refinement: center คอลัมน์ด้วย n ของ **local scope** (งานเล็กพื้นที่เป้าหมาย ~3-5 ราย) ไม่ใช่ province mean (8)
- ⚠️ ยัง n=1 — เก็บ closed-loop เพิ่มยืนยัน calibration
- memory: [[project_winrate_closed_loop]] · [[project_value_principle]]

---

## งานที่ N+136: CHECKPOINT — ก่อนเปลี่ยน session (2026-06-15)

### สถานะ: ⏸ pause เปลี่ยน session — B/B.1/#3 จบ+deploy+validate แล้ว · B′ ไว้ session หน้า

### ✅ เสร็จแล้ว session นี้ (ทั้งหมด pushed + deployed บน VPS, origin/main = `54f02c8`)
- **งาน B** (conditional win-rate ตาราง 3 คอลัมน์ ตามจำนวนผู้ยื่น) — code+test+review, LIVE
- **B.1** (invert F_bid — ราคาแถวจาก win เป้าหมาย 75/50/25, แก้ปัญหา win% แบน 86-100% + ราคายุบ) — LIVE, verify การ์ดจริงนาทมไล่ระดับสวย
- **#3** (ตาราง B ใช้ population เดียวกับราคา ผ่าน project_ids จาก used_rows — กรอง subtype/year ตรงราคา) — LIVE
- **closed-loop validation แรก** (งานจริง 69059374770 โพธิ์หมากแข้ง): filter จัดเต็ม + อ่านคอลัมน์ตรง n จริง (5 ราย) → ทำนายผู้นำ **แม่น 0.04%** (690,430 vs จริง 690,000)
- Discovery JA3 fix (N+131) ยัง LIVE · backfill 2A trickle ต่อ (~924+/3032, PID 1187503)

### 🎯 NEXT ACTION (session หน้า) — งาน B′ (decided กัญจน์: ใช้ filter จัดเต็ม ผ่อนแค่ scope)
**3 ชิ้น (จากหลักฐาน closed-loop วันนี้):**
1. **ผ่อน scope สำหรับ win-rate** — fallback ตำบล→อำเภอ→จังหวัด เมื่อ local full-field <5 (ให้ตารางขึ้น). คง filter cf จัดเต็มเหมือนราคา. ป้าย "อิงจว." ชัด
2. **recency-weight F_bid** — `winrate_grid` ตอนนี้แบนเรียบ (R2) ไม่ถ่วงปี · ฝั่งราคาถ่วงแล้ว (`recency_weight` half-life 1ปี) → ใส่ให้ F_bid เพราะใช้ include_old ทุกปี
3. **center คอลัมน์ด้วย n ของ local scope** — ไม่ใช่ province mean (งานเล็กพื้นที่เป้าหมาย ~3-5 ราย, province mean=8 ลึกเกิน)
- **วิธีทำ:** `superpowers:brainstorming` → spec → `superpowers:writing-plans` → `superpowers:subagent-driven-development`
- ไฟล์เกี่ยว: `scripts/bid_field.py` (winrate_grid/_field_auctions/field_and_winrate) · `scripts/cgd_intel.py` predict() ~584 · spec เดิม `docs/superpowers/specs/2026-06-15-conditional-winrate-b-design.md`

### ค้าง/ระวัง
- ⚠️ deploy = กัญจน์รันเอง VPS (`cd /opt/bms/app && git pull && bash scripts/deploy.sh`) · SSH จาก dev ไม่ได้
- ⚠️ คำสั่ง python -c หลายบรรทัดบน VPS terminal **ตัดบรรทัดกลางสตริง** → ใช้ heredoc ไฟล์ `/tmp/*.py` เสมอ
- closed-loop เก็บเพิ่ม (n>1) ระหว่างทาง B′ ได้ — งานที่ PRELIM แล้วใช้ `prelim_summary.fetch_prelim_summary(pid, method_id)`
- test เดิมต้องผ่าน: test_winrate_grid / test_bid_field / test_cgd_intel (BMS_ENV=dev) / test_winrate

## งานที่ N+137: CHECKPOINT — B′ design+plan เสร็จ พร้อม execute (2026-06-15)

### สถานะ: ⏸ pause เปลี่ยน session — spec+plan committed, รอ subagent-driven execution (กัญจน์เลือกเริ่ม session หน้า)

### ✅ เสร็จแล้ว session นี้ (committed บน main, `c1d8b90`)
- **Brainstorm B′ → design freeze** — แก้ tension "ผ่อน scope vs price=local" (กัญจน์จับว่าราคาต้องอิง local)
- **ปรึกษา ChatGPT 2 รอบ → converge 8/8** (`/report-to-chatgpt`): KS runtime-gate + ESS-blend → ถอยเป็น B″ + offline monitor. ChatGPT ยอมรับว่า Claude ถูกทั้ง 2 จุด
- **spec** `docs/superpowers/specs/2026-06-15-winrate-b-prime-design.md` — review กัญจน์ 8.5/10, แก้ 3 จุด (MIN_N_AUCTIONS=3, assisted disclaimer เน้น, fail_reason log) commit `a059601`
- **plan** `docs/superpowers/plans/2026-06-15-winrate-b-prime.md` — 7 tasks TDD bite-sized, self-review เทียบ spec ครบ commit `c1d8b90`

### 🎯 NEXT ACTION (session หน้า) — EXECUTE plan B′
- **พิมพ์ "resume"** → อ่าน checkpoint นี้ → invoke `superpowers:subagent-driven-development` ชี้ไป plan `docs/superpowers/plans/2026-06-15-winrate-b-prime.md`
- dispatch implementer subagent ต่อ task (7 tasks) + two-stage review (spec → quality) ต่อ task · fresh subagent ต่อ task (ส่ง full task text ไม่ให้อ่าน plan เอง)
- **3 knobs:** (1) scope ladder mirror ราคา ผ่อน อำเภอ→จังหวัด · (2) recency-weighted quantile + ESS floor=6 · (3) center n local (MIN_N_AUCTIONS=3)
- ไฟล์แก้: `scripts/bid_field.py` (หลัก) · `scripts/cgd_intel.py` (integration ~586) · `scripts/test_winrate_grid.py`
- **หลักการห้ามพลาด:** price sacred (assisted คงบล็อกราคา local + ตารางต่อท้าย, 🟢 เท่านั้นที่แทน a/b/c) · F ก้อนเดียว (center=target)

### ค้าง/ระวัง
- ⚠️ deploy = กัญจน์รัน VPS เอง (SSH จาก dev ไม่ได้) · python -c หลายบรรทัดบน VPS พัง → heredoc /tmp/*.py
- Task 7 มี Sophia sanity audit + progress_log N+137→138 update ก่อน final commit
- เริ่ม implementation ต้องอยู่บน branch — ตอนนี้ main · subagent-driven แนะนำ branch ก่อน execute (หรือ worktree)
- uncommitted เดิม (settings.local/discovery_seen/rss_log + debug scripts) = runtime ไม่เกี่ยว B′ ไม่ต้อง commit

---

## งานที่ N+138: Win-Rate B′ — ladder+recency+local-n — DONE (2026-06-15)

### สถานะ: ✅ เสร็จ (code+test) — branch `worktree-winrate-b-prime` · รอกัญจน์ merge + deploy VPS

### สิ่งที่ทำ (subagent-driven-development, 7 tasks TDD บน worktree)
ทำตาม plan `docs/superpowers/plans/2026-06-15-winrate-b-prime.md` ครบ 7 task · fresh subagent ต่อ task + two-stage review (spec→quality) ต่อ task · Sophia sanity audit = SAFE
- **T1** `_weighted_quantile` (recency-weighted Hazen) + recency import → `12a7238`
- **T2** `_field_auctions` 4-tuple (+fiscal_year) + fix 2B consumers รับ 4-tuple → `54d46ae`
- **T3** `_evaluate_winrate` source-of-truth (gate auctions≥5 + ESS≥6 + recency CDF + local-n center + fail_reason) → `19aa5df`
- **T4** `winrate_lines` conf tag 🟢🟡🟠 + assisted disclaimer → `a8e5e8c`
- **T5** `field_and_winrate` ladder (local→อำเภอ→จังหวัด ผ่าน `_scope_ids`→`_fetch_scope`+cf) + breadcrumb log → `8e944f1`
- **T6** `cgd_intel._build_intel` integration: 🟢 ตารางแทน a/b/c · 🟡🟠 คงราคา local + ตารางต่อท้าย (price sacred) → `075dea1`
- **T7** verification: py_compile + 5 test files ALL PASS + Sophia SAFE

### 2 decision เบี่ยงจาก spec (ตรวจ + ยืนยันแล้ว)
1. **ESS = Σw (ไม่ใช่ Kish `(Σw)²/Σw²`)** — spec เขียนสูตร Kish ผิด: Kish=n เมื่อน้ำหนักเท่ากัน → งานเก่าทั้งหมดผ่าน gate (ขัดเจตนา). test+comment ของ spec เองต้องการให้งานเก่า fail → มีแต่ Σw (recency-effective count) ที่ทำได้. independent review ยืนยัน. **design doc แก้แล้ว**
2. **scope ladder ใช้ `_fetch_scope`+cf (กัญจน์เลือก Option A)** — implementer คนแรกเลี่ยงไป query bid_results ตรง (ทิ้ง cf) เพราะ test data ไม่สมจริง (fy=2569 นอก RECENT_FY, win_price=NULL). แก้กลับเป็น spec + แก้ test data (fy="2568", win_price>0) → "population เดียวกับราคา" ตามหลักแกน

### Verify (DoD)
`test_winrate_grid`(14) · `test_bid_field`(5) · `test_cgd_intel`(22) · `test_winrate` · `test_recency` = ALL PASS · py_compile clean · Sophia SAFE

### Followup
- กัญจน์ merge `worktree-winrate-b-prime` → main + deploy VPS (heredoc /tmp/*.py)
- B″ (out of scope): hierarchical shrinkage, KS shape-gate, k-clamp, auto-tier ESS floor — เก็บ offline monitor data ก่อน
- progress_log 1004 บรรทัด → rotation ค้าง (ทำหลัง merge บน main)

---

## งานที่ N+139: Win-Rate B′ — deploy VPS + closed-loop validation แรก (2026-06-15)

### สถานะ: ✅ LIVE บน VPS (origin/main d543cf1 → git pull + deploy.sh) · worker timers ใช้โค้ดใหม่รอบถัดไป

### ผล validation (2 งานจริง พื้นที่ข้อมูลบาง — เดิม B.1 ตารางไม่ขึ้น)
1. **ต.นาทม อ.นาทม นครพนม** (งบ 2.0M) — ตำบล 4 งาน/อำเภอ 6 งาน · ราคา local อิงตำบล+อำเภอ (น้ำหนักตำบล 57%) 1.18M(75%)/1.22M(25%) · **ตาราง 🟠 อิงจังหวัด** จาก 61 งาน 611 ราย, center 8 ผู้ยื่น(±5)
2. **ต.บึงโขงหลง อ.บึงโขงหลง บึงกาฬ** (งบ 1.5M) — ตำบล 2/อำเภอ 3 · ราคา local อิงตำบล 0.89M/1.09M · **ตาราง 🟠 อิงจังหวัด** จาก 35 งาน 300 ราย, center 9(±6)

### ✅ ของหลักทำงานครบตาม design
- ตารางขึ้นในพื้นที่บาง (เดิมไม่ขึ้น) · **price sacred**: ราคา local "💵 แนะนำราคายื่น" คงอยู่ + ตารางต่อท้าย · ⚠️ disclaimer "ราคาด้านบนยังอิงตำบล..." · conf 🟠 ถูก

### 🔍 Observation (ขีดจำกัดข้อมูล ไม่ใช่ bug)
- ทั้ง 2 งาน **ผ่อนถึง 🟠 จังหวัด** (ไม่หยุด 🟡 อำเภอ) + **center 8-9 ผู้ยื่น** (ไม่ใช่ 3-5 ของพื้นที่จริง)
- **root:** ตำบล/อำเภอมี full-field auctions (งานที่มี bid_results รายชื่อผู้ยื่นครบ) < MIN_AUCTIONS(5) → gate ไม่ผ่าน → ladder ผ่อนถึงจังหวัด; และ local full-field < MIN_N_AUCTIONS(3) → n-centering fallback ใช้ n จังหวัด (8) ตามที่ design ตั้งใจ (local <3 = n noisy)
- **คอขวดจริง = bid_results coverage** (getProcureResult poll ไม่ครบทุกงาน) → ขีดจำกัดข้อมูล ไม่ใช่ logic. แก้ด้วย backfill ผู้ยื่นพื้นที่เป้าหมาย ไม่ใช่แก้โค้ด
- **B″ candidate:** center บน intermediate scope (อำเภอ n) แทนกระโดดจังหวัด เมื่อ local full-field <3 แต่อำเภอพอ
- ดู [[project_winrate_bprime_coverage_limit]]

### Followup
- backfill bid_results ตำบล/อำเภอเป้าหมาย (บ้านแพง/บึงโขงหลง/นาทม) → ปลดล็อก 🟡 อำเภอ + center local จริง
- rotation progress_log (>1000 บรรทัด) ยังค้าง

---

## งานที่ N+140: Targeted backfill 3 อำเภอ → ต.นาทม ปลดล็อก 🟢 local (2026-06-16)

### สถานะ: ✅ พิสูจน์ loop B′ + backfill ครบ — นาทม จาก 🟠 จังหวัด → 🟢 อำเภอจริง + 2B เจ้าตลาดโผล่

### สิ่งที่ทำ
- เพิ่ม `--districts` filter ใน `backfill_bidders.py` (กรองอำเภอจากชื่องาน LIKE — geocode column เพี้ยน 85%) + test `commit fb3e7af` push origin
- รัน targeted backfill 3 อำเภอ (นาทม/บึงโขงหลง/บ้านแพง · นครพนม+บึงกาฬ · fy 2566-68) บน VPS — 113 candidates
- 🐛 รอบแรก crash: `PermissionError backfill_seen.json` (เจ้าของ root จาก trickle เดิม, รันเป็น bms เขียน checkpoint ไม่ได้) → fix `chown bms:bms` (ssh root) → rerun resume (113→65, bid_results dedup ตัดที่เก็บแล้ว) → `✅ stored=65 empty=0 error=0`

### ผล (closed-loop validation รอบ 2)
- coverage: นาทม 23→**53** · บึงโขงหลง 10→**24** · บ้านแพง 33→**72**
- **ต.นาทม:** 🟠 จังหวัด(63 งาน, center 8) → **🟢 local**(6 งานอำเภอจริง 47 ราย, คอลัมน์ 5/8/11) · a/b/c ถูกตารางแทน (🟢) · **🏆 2B เจ้าตลาดโผล่** ("เอส.ที.เค.เพาเวอร์ ชนะ 60% 3/5") — เพราะ full-field ≥5 แล้ว
- **ต.บึงโขงหลง:** ยัง 🟠 — อำเภอมี winner concrete+แข่งจริง+RECENT_FY **แค่ 3 งาน** → ไม่มีทางถึง MIN_AUCTIONS(5) = **เพดานเชิงโครงสร้าง** (backfill ไม่ช่วย) · price sacred ทำงาน (ราคา local + disclaimer ครบ)

### บทเรียน
- backfill bid_results = lever ปลดล็อก 🟢/🟡 ได้จริง **เมื่ออำเภอมี cf-winner ≥5** · อำเภอที่ winner cf-filtered <5 = ติด 🟠 ถาวร (ต้องผ่อน cf หรือแก้ threshold = B″)
- ค้าง: **RECENT_FY ตัดปี 2569 (ปัจจุบัน)** — งานสด weight 1.0 ไม่ถูกนับ → fix ให้รวม 2569 ช่วย ESS พื้นที่บางทุกที่ (กัญจน์ยังไม่ตัดสิน)
- ดู [[project_winrate_bprime_coverage_limit]]
