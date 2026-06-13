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

### ต่อไป
- **repredict_followed --apply** (ยังไม่รัน) → refresh /audit งานที่ติดตามให้ใช้ logic ใหม่
- **L3 recency (ตัวจริงที่จะแก้หนองเดิ่น):** หักน้ำหนักข้อมูลเก่า (2562) ไม่ใช่แค่ตั้งธง
- rich-tambon (tn≥5) ยังไม่ blend (effect น้อย defer)
- ของใหญ่ (all-bidders + C เต็ม) รอ evidence เพิ่ม
- memory: project_scope_selection_bug
