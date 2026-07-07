# Bid Master System — Progress Log

> เก็บเฉพาะ entry ล่าสุด (~20 อัน). entry เก่ากว่านี้อยู่ใน progress_log_archive.md

## งานที่ N+169: Backfill สกลนคร เสร็จ + import VPS (2026-06-23)

### สถานะ: ✅ เสร็จ

### สิ่งที่ทำ
- รีสตาร์ท `_backfill_home_fetch.py` (เครื่องบ้าน) resume จาก checkpoint 2,190/10,751 ที่ค้างไว้ตอนปิดเครื่องเดินทาง — รันต่อจนจบเอง: `DONE: stored=8455 empty=91 error=15, total_in_results=10,736`
- import เข้า VPS `bid_results`: backup prod DB ก่อน (`bms_customers_pre_skn_backfill_import_20260623_063415.db`) → smoke test 5 sample (idempotent re-run ยืนยัน) → รันจริง `_backfill_home_import.py /tmp/skn_backfill_results.json` → **stored_projects=10,628, bid_rows=86,861**
- `bid_results` รวม: 82,897 → **157,946 แถว** (+75,049) · `/health` OK หลังเสร็จ
- ลบไฟล์ temp บน VPS แล้ว (`/tmp/skn_backfill_results.json`, `_backfill_home_import.py`)
- คืนค่า `standby-timeout-dc` กลับ 15 นาที (ของเดิมก่อนปิด sleep กัน backfill ค้างตอน 2026-06-21) — เจอ bug เล็ก: `powercfg /change` รับหน่วยเป็น**นาที**ไม่ใช่วินาที ตอน revert รอบแรกใส่ 900 (ตั้งใจ=วินาที) กลายเป็น 900 นาที (15 ชม.) โดยไม่ตั้งใจ แก้เป็น `15` ถูกแล้ว

### Followup
- backfill นครพนม+บึงกาฬ + สกลนคร ครบทั้ง 3 จังหวัดแล้ว (bid_results coverage เพิ่มมาก)
- ของค้างเดิมจาก N+164 ยังไม่แก้: FY2568 proc_type anomaly ของสกลนคร (label รวมไม่แยกประเภท) ก่อน wire เข้า default ของ `backfill_bidders.py --provinces`/daily timer
- ยังไม่ลบไฟล์ local `data/_backfill_home/` (skn_* + เดิม) — ข้อมูลขึ้น DB ครบแล้ว รอกัญจน์ยืนยันก่อนเคลียร์

## งานที่ N+170: เพิ่มอุดรธานีเป็นจังหวัดที่ 4 + เริ่ม backfill (2026-06-23)

### สถานะ: 🚧 กำลังรัน background (เครื่องบ้าน residential)

### สิ่งที่ทำ (ตามแบบ N+164 ทุกขั้น)
- `_winner_history_build.py` PROVS += อุดรธานี, `cgd_sync_to_vps.py` TARGET += อุดรธานี (commit `12fb986`)
- `_winner_history_build.py` bulk fetch CGD: โดน quota ครั้งเดียว (calls=700, ค้างที่ 2561 file6) → retry รอบ 2 ผ่านครบ **ไม่โดน quota ซ้ำ** (ต่างจาก สกลนคร ที่โดน 3 รอบ) — รวม winner_history ทั้ง 4 จังหวัด = 1,962,449 แถว (อุดรธานี เดี่ยว 657,184 แถว ปี 2558-2568)
- `cgd_sync_to_vps.py --push` → VPS `cgd_winners` (local SSH client timeout 600s แต่ remote merge ทำงานต่อจนจบจริง — ยืนยันด้วย count ตรงกัน 1,962,449) → อุดรธานี = **753,882 แถว บน VPS**
- 🐛 **เจอ anomaly เดิมซ้ำ**: FY2568 อุดรธานี ก็ proc_type label รวมไม่แยกประเภทเหมือนสกลนคร (ยืนยันเป็น CGD source-side ไม่ใช่ province-specific) → ใช้ scope FY2558-2567 (10 ปี) เหมือนเดิม
- candidate generation **ต้องรันบน VPS** (backfill_bidders.py คิวรี cgd_winners จาก local bms_customers.db ของเครื่องที่รัน — เครื่องบ้านไม่มีข้อมูล cgd_winners เลย จึงต้อง query บน VPS แล้ว scp กลับ ไม่ใช่รัน local) → ได้ **14,111 candidates** (FY2558-2567)
- เริ่ม residential fetch `_backfill_home_fetch.py ../data/_backfill_home/udt_backfill_cands.json ../data/_backfill_home/udt_backfill_results.json` กำลังรัน background

### Followup
- รอ fetch เสร็จ (คาด ~10-12 ชม. ตามขนาด 14,111 งาน) → import เข้า VPS `bid_results` (`_backfill_home_import.py` path arg เดิม) ตามแบบ N+169
- ของค้างสะสม (ทั้งสกลนคร+อุดรธานี): ตัดสินใจ FY2568 proc_type anomaly ก่อน wire เข้า default `backfill_bidders.py --provinces`/daily timer


## งานที่ N+169: winner-poller upsert cgd_winners + backfill orphans (2026-06-23)

### สถานะ: ✅ เสร็จ + deploy VPS

### Investigation (debug-mantra)
กัญจน์รายงาน is_winner=0 + ไม่มี cgd_winners (งาน 69059453079). สืบแล้ว = **ไม่ใช่ bug** —
eGP สด stepId=S01 + priceAgree=None ทุกราย → ผู้ชนะยังไม่ประกาศจริง. DB mirror ถูก. poller คุมงานนี้ (2 follower) จะ mark เมื่อ award ออก.

### Gap จริงที่เจอ + Fix
winner-poller mark bid_results.is_winner แต่ไม่เขียน cgd_winners → awarded jobs มองไม่เห็นในเครื่องคิด Win% จนกว่า CGD open-data sync ตามทัน (เดือน). เจอ 3 orphans (is_winner=1, ไม่มี cgd_winners).
- เพิ่ม `SubscriptionStore.upsert_cgd_winner` + เรียกใน `poll_winners` (guard bidders≥2 + budget>0). winner_tin=None (เพี้ยน), proc_type=e-bidding, idempotent. TDD: test_winner_poller +1
- merge main `4409644` → scp 2 ไฟล์ (Customer_DB, Winner_Poller) → restart bms-api · backup predeploy_20260623_192210
- backfill 2/3 orphans (69059132412, 69059227331; ตัวที่ 3 ไม่มี budget ข้าม) → orphans 3→1

### ผล
ยศประทาน 159 งานใน pool เครื่องคิด · 69059227331 (จาก scope-selection bug เดิม) เข้า pool แล้ว

## งานที่ N+170: lookup_company.py — competitor profiler 11 ปี (2026-06-23)

### สถานะ: ✅ merged main (6bbfd5c) · tool รัน local

### สิ่งที่ทำ
tool ดึงโปรไฟล์คู่แข่งเชิงลึกจากประวัติชนะประมูล CGD ทั้งประเทศ 2558-2568 ด้วย q-sweep 96 resources
(RID ปีเก่าใน data/_cgd_rids_*.json) — ไม่ต้อง sync ทั้งจังหวัด. compute_profile = pure (เทสต์แยก).
สถิติ: ฐานจังหวัด/วิธีจัดซื้อ/หมวดงาน/%ลดแยก e-bidding-vs-เฉพาะเจาะจง/ขนาดงาน/trend. graceful 429.

### ผลกับ หจก.หนองหว้า การก่อสร้าง
25 งาน/11ปี · ฐาน=สระแก้ว(17) · มูลค่ารวม 19.4M · e-bidding median ลด 10.8% (3.6-17.7%) · เฉพาะเจาะจง 0%
= ผู้รับเหมารายเล็กสระแก้ว ทำซ่อม/ปรับปรุงอาคารโรงเรียนเป็นหลัก แข่งไม่ดุ

### หมายเหตุ
ใช้: `python scripts/lookup_company.py "ชื่อบริษัท"` · ติด CGD quota 1000/วัน (~96 calls/ครั้ง) · ต้องมี OPEND_USER_TOKEN + _cgd_rids files (local)

## งานที่ N+171: แก้ Discovery false-alarm "พลาด full sweep" (catch-up quiet retry) — DEPLOYED (2026-06-24)

### สถานะ: ✅ เสร็จ + deploy VPS (commit 8ce6436) · debug-mantra ครบ 4 ขั้น

### Root cause (ยืนยันจาก journalctl VPS 2026-06-23 12:30 UTC = 19:30 ไทย)
กัญจน์เห็น Discord เด้ง "🔄 พลาด full sweep นครพนม รอบ 19:30 → รันให้ทันที" บ่อย (ไม่ได้ปิดเครื่อง).
ไม่ใช่ WAF/token (เคยเดา) และไม่ใช่เครื่องบ้านปิด:
- full sweep จังหวัดเดียว paginate เกิน rate budget → `หน้า 55 rate-limited — abort` → `partial_abort=True` → 378 active (จาก ~774)
- partial → เงื่อนไขเดิม `not partial_abort` ตก → **ไม่เขียน marker** `last_fullsweep_480000.json`
- catch-up (`discovery_catchup.py`) เช็คแค่ marker → ไม่เจอ → เด้ง "พลาด" + re-run ทุก harvest cycle (15m)
- re-run บางรอบ window ว่าง → จบครบ 774 → เขียน marker. **ไม่มีงานหายจริง = false alarm** (incremental คุม freshness, full sweep = reconciliation safety-net)
- ฝั่ง incremental มี throttle `CATCHUP_RETRY_SEC=20m` แต่ฝั่ง full-sweep ไม่มี (followup ค้างจาก N+131)

### Fix (A: quiet retry — กัญจน์เลือก, surgical 2 ไฟล์)
- `Sebastian_Province_Discovery.py`: เขียน marker **ทุกรอบ** (รวม partial) ติด flag `partial`; per-sweep report ใส่ป้าย `⚠️ partial (ชน rate limit)` เมื่อ partial_abort
- `discovery_catchup.py`: full-sweep retry **เงียบ** (ไม่เด้ง "พลาด") + throttle 20m (ใช้ marker.ts) + **alert เฉพาะถ้า retry แล้วยัง partial ซ้ำ** (rate budget ตันจริง)
- verify: py_compile (local+VPS venv) + logic-sim 5 เคสผ่าน (complete=skip, partial-recent=throttle quiet, stale/no-marker=run)

### Deploy note (deploy debt)
VPS `git pull` โดน block: 5 ไฟล์ (Customer_DB/Winner_Poller/bid_field/cgd_intel/portal_views) มี local diff สมมาตร ~3900± = **CRLF/LF noise** ไม่ใช่ content จริง ([[project_deploy_debt]]). 2 ไฟล์ fix สะอาด → deploy แบบ `git checkout origin/main -- <2 files>` เลี่ยง merge. **full migration ของ 5 ไฟล์ CRLF ยังค้าง** (แยกทำ)

### Followup
- ดูผล slot ถัดไป: นครพนม 07:30 / บึงกาฬ 08:30,20:30 ไทย — ควรเงียบ (ไม่มี "พลาด")
- C (root, ไม่ทำตอนนี้): pagination resume ให้ full sweep จังหวัดเดียววิ่งจบรอบเดียวใน budget
- จัดการ deploy-debt CRLF 5 ไฟล์บน VPS (renormalize .gitattributes)


## งานที่ N+172: แจ้งงานยกเลิกโครงการ + แก้ Board (cancelled-project notification) (2026-06-25)

### สถานะ: ✅ เสร็จ (local main, 4 commits) · ⏳ ยังไม่ deploy VPS · brainstorming→spec→plan→TDD ครบ

### ที่มา
พ่อกัญจน์เห็นงานที่ยกเลิกโครงการแล้วค้างอยู่ใน "สรุปราคาเบื้องต้น" บน Web Board + อยากให้แจ้งเตือนงานยกเลิก

### Root cause
lifecycle ฝั่ง DB/Board = B0→D0→PRELIM→W0 **ไม่มี stage ยกเลิก** → Board group ตาม last_stage_notified
งานเคยขึ้น PRELIM แล้วยกเลิกทีหลังค้างใน prelim ตลอด. legacy Sheets classifier ตรวจยกเลิกได้ แต่ไม่ถูกพอร์ตมาฝั่ง DB/Board/notification

### Fix (4 task TDD, piggyback winner-poller ไม่สร้าง cron ใหม่)
1. `Sebastian_Classifier.py`: extract `_cancel_note` + `is_cancelled()` (R / D1,W1 / B*) — classify_by_stepid พฤติกรรมเดิมคงเดิม (regression test ครอบ B*+winner→awarded)
2. `Sebastian_Winner_Poller.py`: cancellation pass (param `resolve_status=None`) วนทุก active follow → get_project_detail → is_cancelled → enqueue `followed_cancelled` + mark `CANCELLED` + close + ข้าม poll winner; fail-safe error=ไม่ false-cancel
3. `Sebastian_LINE_Sender.py`: `format_cancelled_notification` + dispatch block (re-derive note ตอน render เหมือน prelim) → ผ่าน queue→digest เดิม (ช่วง LINE quota เต็มจะรวมใน digest 1 ก.ค. เอง)
4. `bms_api.py`: groups["cancelled"] เช็ค lsn=="CANCELLED" ก่อน prelim + chip + badge bx + render section

### Verify (verifiable success criteria — ผ่านหมด)
- test_is_cancelled (3 สัญญาณ + classify regression), test_winner_poller_cancel (enqueue+mark+close+skip+fail-safe+backward-compat), test_format_cancelled, test_portal_cancelled (PC=cancelled ไม่ใช่ prelim) — + regression test_winner_poller / test_portal_jobs เขียวหมด
- backfill: ไม่ต้องเขียนแยก — งานยกเลิกค้างถูกจับในรอบ poll แรกหลัง deploy
- commits: 3cccc8f / fbc2f02 / f382bea / 76bc055 · spec+plan ใน docs/superpowers/

### Sophia sanity verdict: ✅ SAFE TO PROCEED
- dedup ✅ (source_stage="followed_cancelled" UNIQUE 3-col ไม่ชน sibling), classify regression ✅ (B*+winner→awarded), fail-safe ✅ (verify ด้วยรันจริง), valid=False จาก getProjectDetail → is_cancelled("","","")=(False,"") ปลอดภัย, last_stage_notified="CANCELLED" ไม่ break code path ไหน (star_metrics/_STAGE_RANK ใช้ .get fallback)
- ⚠️ verify live VPS queue schema ไม่ได้ (ไม่มี SSH key) — แต่ followed_prelim/winner LIVE ใช้ dedup 3-col เดียวกันอยู่แล้ว = migrate แล้วโดยปริยาย (low risk)
- ⚠️ operational cost: getProjectDetail ทุก active follow/รอบ poller (~6ชม.) เพิ่มโหลด eGP ถ้า follow list โต — จับตา

### ✅ DEPLOYED VPS (2026-06-25) — กัญจน์ confirm "deploy เลย"
- push origin 066bbdd→97f19f8 (6 commits) · VPS `bash scripts/deploy.sh` ff-pull clean (CRLF debt reconciled แล้ว ไม่ค้าง) + init_schema v1.14 + bms-api restart → active
- ssh key = `~/.ssh/bms_vps` (session แรก fail เพราะไม่ระบุ -i; Sophia ก็ fail เพราะงี้) · VPS `bms@45.76.156.166`
- pre-deploy verify: live queue schema = `UNIQUE(customer_id,project_id,source_stage)` 3-col ✅ (Sophia unknown เคลียร์) · 6 test รัน venv prod เขียวครบ · poller+bms_api import OK
- ผลทันที: Board กลุ่ม ❌ ยกเลิกโครงการ LIVE · winner-poller cancellation pass รอบถัดไป 12:15 UTC (19:15 ไทย) · การ์ดยกเลิก→queue→digest (LINE quota เต็ม รวมส่ง ~1 ก.ค.)
- `bms-winner-poller.timer` enabled (รัน 06:15 + ~6ชม.)

### Followup
- จับตา operational cost: cancellation pass เรียก getProjectDetail ทุก active follow/รอบ — ถ้า follow list โตค่อยจำกัด stage/cache (ตอนนี้ follow น้อย ไม่มีปัญหา)


## งานที่ N+173: Location backfill + forward resolve — เติมตำบล/พิกัด province_api (2026-06-26)

### สถานะ: ✅ เสร็จ + DEPLOYED VPS + verified drain เริ่มแล้ว · Sophia SAFE

### ที่มา
กัญจน์ถามทำไม board กลุ่ม "ยื่นซอง" ไม่ขึ้นตำบล (ขึ้นแค่ "จ.X"). debug เจอ: ไม่ใช่ bug การ์ด — **moi_name (ตำบล) ว่าง** ในงาน source=province_api (enrichment_status=failed placeholder). board render location จาก moi อยู่แล้ว → moi ว่าง = ขึ้นแค่จังหวัด

### ขนาด + root cause
- **1,117/2,781 แถว (40%)** project_locations มี province แต่ moi=NULL — ทั้งหมด province_api, จังหวัด นครพนม 750+บึงกาฬ 367, ช่วง 30พ.ค.–24มิ.ย. (ไม่ใช่ history 10 ปี = winner_history.db คนละชุด)
- province_api ลงทะเบียน moi=NULL; การดึง location จริง (getProcurementDetail) เกิดเฉพาะใน pass แจ้งเตือน (gate RESOLVED+open) → งานไม่ผ่าน gate ค้าง NULL
- พิสูจน์: getProcurementDetail คืน moi+อำเภอ+พิกัดจริง (ข้อมูลมีใน eGP แค่ไม่เคยดึง). dept_name fallback ได้ตำบลเดียวกัน (อบต.ตั้งชื่อตามตำบล) แต่ getProcurementDetail ดีกว่า (ที่ตั้งงานจริง+อำเภอ+พิกัด+ครอบทุกหน่วยงาน)

### Fix (2 task TDD, worker pass เดียวแก้ทั้ง backfill+forward)
- `cc1a3a0` `resolve_missing_locations(log, resolve_detail, sleep_sec)` ใน Sebastian_Enrichment_Worker.py: selector source=province_api+moi NULL+attempts<3 → getProcurementDetail → save_project_location_raw (ตำบล/อำเภอ/พิกัด), tambon_from_dept fallback, _bump_locfill_retry (stop@3). batch=8, sleep 1.5s
- `d198c4b` เสียบใน main() หลัง cooldown gate (INC-001) → skip ตอน WAF ร้อน
- self-healing: งานใหม่ moi ว่างถูกเก็บรอบถัดไปเอง (อุดรอยรั่ว — มิ.ย. ตกหล่นเพิ่ม 42)
- spec `cf64b22` + plan ครบ · test_resolve_missing_locations 6 เคสเขียว (local+prod venv)

### Deploy + verify (DEPLOYED 2026-06-25 ~17:29 UTC)
- push c4b04f1→d198c4b · deploy.sh ff-pull + bms-api restart · schema source col ยืนยัน (ปิด Sophia ⚠️)
- รอบ worker 17:30 (โค้ดใหม่): resolve 5 งานจริง (ต.ท่ากกแดง/นาสวรรค์/คำแก้ว/โนนสว่าง coord=True) → "Location resolve: เติม 5 งาน"
- NULL-moi 1117→1112, เติมแล้ว 45→50 · drain ~5-8/รอบ (timer ~2นาที) → เกลี้ยงใน ~ไม่กี่ชม.

### Followup
- ~~drain~~ ✅ เสร็จ: 696 งานได้ตำบล (1117→421), 421 ที่เหลือ = งานระดับจังหวัด/รพ./สนง. ที่ eGP ไม่มีตำบลจริง (attempts≥3, ตันถูกต้อง ไม่ใช่ bug)
- ~~(idea) แสดงอำเภอบน board~~ ✅ **เสร็จ+DEPLOYED** (576cc98): `_portal_jobs` resolve อ.จากตำบล (`amphoes_of_tambon`, unique→โชว์ กำกวม→ข้าม). verify จริง: ต.นาทม อ.นาทม จ.นครพนม. test_portal_amphoe 3 เคส+regression เขียว
- ✅ dept-fallback backfill (one-time): 3 งาน local ตกค้างเพราะ `enrichment_attempts`≥3 สืบทอดจาก enrichment เดิม (locfill selector <3 ตัดก่อนได้ลอง) — bug ไม่ใช่ resolve พลาด (ทั้ง getProcurementDetail+dept fallback คืนตำบลได้). แก้: เติม moi จาก tambon_from_dept ข้าม attempts gate (ฟรี ไม่ยิง API). นาหว้า/เวินพระบาท/มหาชัย → NULL-moi 421→418. งานใหม่ไม่โดน (attempts เริ่ม 0)

---

## งานที่ N+175: ส่งงานก่อสร้างทั่ว 2 จังหวัด (whole-province) + daily digest (2026-06-27)

### สถานะ: ✅ DEPLOYED VPS (2026-06-27) ทั้ง 2 ส่วน · self-sanity เทสต์เขียว (Sophia ติด session limit → fallback รันเอง)

### ที่มา
กัญจน์/พ่อ: เอางานก่อสร้างทั้งนครพนม+บึงกาฬ (ไม่เอาแค่ 21 ตำบล), ตัดงานซื้อ/เวชภัณฑ์, ส่งทุกคน. วัดจริง: ~21 งานก่อสร้าง/วัน (จาก D0 ~55/วัน; ซื้อ ~21, อื่น ~13 ตัด)

### ส่วน 1 — matching whole-province ✅ (commit local, ยังไม่ deploy)
- `job_matcher.match_job`: ถ้า province ∈ `whole_provinces` → ตัด is_procurement, keyword(ก่อสร้าง) required, neg, else send (ไม่สนตำบล). reason='whole_province_keyword'
- config `whole_provinces:["นครพนม","บึงกาฬ"]` (target_tambons เก็บไว้เผื่อปิดโหมด). keyword pre-filter+ตัดซื้อ ยังทำงานเหมือนเดิม
- test_job_matcher +5 เคส (CFG_WP) เขียว · commit ~ (local, ยังไม่ push)
- **ยังไม่ deploy โดยตั้งใจ**: ถ้าเปิดก่อนมี digest → quota รีเซ็ต ~1ก.ค. จะเด้งทีละงาน ~21/วัน = สแปม

### ส่วน 2 — daily digest (ยังไม่เริ่ม) — TODO next session
ปัจจุบันส่ง "ทีละงาน": worker enqueue (Sebastian_Enrichment_Worker.py:439 source_stage=province_qualified/_soft) → notification_queue → LINE_Sender push ทีละ item. Daily_User_Summary = แค่ heartbeat นับ (ไม่ลิสต์งาน).
ต้องทำ: (a) Daily_User_Summary ลิสต์งานก่อสร้างที่ qualified วันนี้ใน 2 จว. เป็น 1 ข้อความ (ใช้ bid_open.format_job_bullets) · (b) กันเด้งทีละงานของ discovery: ให้ LINE_Sender ข้าม source_stage discovery (province_qualified/_soft/api_enriched/rss_provisional/province_tor_review*) — followed_* (winner/prelim/cancelled/bid_open) ยัง instant เหมือนเดิม.
ความเสี่ยง: LINE_Sender เป็น core (การ์ดผู้ชนะ/เตือนเส้นตายผ่านตัวนี้) → ต้อง TDD + Sophia ระวัง. ไม่มี deadline เร่ง (quota เต็มถึง ~1ก.ค.)

### ส่วน 2 — daily digest ✅ DEPLOYED (วิธี: ไม่แตะ LINE_Sender เลย)
- worker (Sebastian_Enrichment_Worker.py): D0 RESOLVED+open + decision=send + reason=whole_province_keyword → is_digest → qualification_status='qualified_digest' (ไม่ enqueue per-job) stats['digest']. init is_digest=False กัน NameError (mmode off/shadow)
- Sebastian_Daily_User_Summary.py: fetch_digest_jobs (qualified_digest) + build_message ลิสต์ (reuse bid_open.format_job_bullets) + main ดึง digest 1 ครั้ง/ส่งทุกคน/mark_digest_listed หลัง ok>0 (ไม่ dry-run). dedup ด้วย status qualified_digest→digest_listed
- test_daily_digest.py (fetch/build/mark) + test_job_matcher +5 เคส เขียว · regression resolve_missing_locations/backfill/bid_results_source เขียว
- deploy: push 3922623 → deploy.sh ff-pull+migrate+bms-api active · verify VPS: whole_provinces โหลด, match_job ตำบลนอกเป้า→send/ซื้อ→cut, daily dry-run ok (digest=0 รอ worker รอบใหม่)
- delivery model: discovery งานก่อสร้างทั่วจังหวัด = digest วันละครั้ง (timer bms-daily-user-summary 20:00 เดิม) · followed_* (winner/prelim/cancelled/deadline) ยัง instant ผ่าน LINE_Sender เหมือนเดิม
- หมายเหตุ: quota LINE เต็มถึง ~1ก.ค. → ถ้าส่งไม่ออก ok=0 → ไม่ mark → digest สะสมจนส่งได้ (ไม่หาย). going-forward only (งานที่ filter ไปแล้วก่อน deploy ไม่ย้อนมา)

---

## งานที่ N+174: Ongoing Bidder Capture — เก็บผู้ยื่นทุกราย ทุกงาน หลังจากนี้ (นครพนม+บึงกาฬ) (2026-06-27)

### สถานะ: ✅ DEPLOYED VPS (2026-06-27) · Sophia SAFE · service run success · timer active

### ที่มา
กัญจน์ถามระบบเก็บผู้ยื่นทุกรายของทุกงาน (ไม่ใช่แค่ followed) ไหม → ไม่ครบ: `bid_results` (ผู้ยื่นทุกราย) มาแค่ 2 ทาง = followed jobs (winner_poller) + backfill จังหวัดเป้าหมาย (competitive เท่านั้น). cgd_winners/winner_history เก็บแค่ผู้ชนะทั่วประเทศ. กัญจน์อยากเก็บ "ทุกราย ทุกงาน หลังจากนี้" นครพนม+บึงกาฬ รวมเฉพาะเจาะจง

### Decision (brainstorming)
- scope: นครพนม+บึงกาฬ, ทุก proc_type รวมเฉพาะเจาะจง, **going-forward ไม่ใช่ backfill**
- เฉพาะเจาะจง (84%, ผู้ยื่นรายเดียว=ผู้ชนะ) → **คัดลอกจาก cgd_winners ไม่เรียก API** (ประหยัด ~84% + กัน WAF)
- ปมที่เจอ: "รวมเฉพาะเจาะจง" + "สด" ชนกัน — แหล่งเดียวที่มีเจาะจงครบคือ CGD ซึ่ง lag 8-9 เดือน → user เลือก **เอาทั้งคู่**
- แนวทาง A: โมดูลใหม่ `ongoing_bidder_capture.py` (2 pass) + คอลัมน์ `source` (`procure_api`/`cgd_copy`)

### ดีไซน์ (spec: docs/superpowers/specs/2026-06-27-ongoing-bidder-capture-design.md)
- Pass 1 LIVE: projects_seen 2 จังหวัด, อายุในช่วง (heuristic — ไม่มี deadline ใน schema) → getProcureResult
- Pass 2 CGD-FILL: cgd_winners delta (epoch floor) → เจาะจง copy / แข่ง API backstop
- `_migrate_v136` เพิ่ม source col · idempotent (NOT IN bid_results + INSERT OR REPLACE) · epoch state file
- timer ใหม่ 03:00 · coexist กับ winner_poller + backfill-bidders ผ่าน NOT IN bid_results

### Implement (6 task TDD, commit ทีละ task: 986fc7d→fdbb0e0 + fix)
- T1 `986fc7d` v136 bid_results.source + record_bid_results(source=) · T2 `e1bac89` scaffold state(epoch)/seen
- T3 `717c329` Pass2 CGD-FILL (เจาะจง copy / แข่ง API backstop) · T4 `476502c` Pass1 LIVE (age-window poll)
- T5 `64594fa` run loops+main+Discord (API-only pacing) · T6 `fdbb0e0` systemd timer 03:00
- fix: run_live ไม่พักหลัง API ตัวสุดท้าย (Sophia note)
- test: 5 ไฟล์ใหม่ + regression backfill_bidders เขียวหมด · dry-run epoch_date=2026-06-27 epoch_fy=2569
- deviation: Pass2 floor = fiscal_year>=epoch_fy (announce_date เป็น Thai date เทียบ ISO ไม่ได้ + ทน full-re-push)
- **Sophia SAFE** (ทุก test ผ่าน, migration register ถูก, callers เดิมไม่แตก default source, idempotent/pacing/epoch ok)

### Deploy ✅ DEPLOYED (2026-06-27, confirm by กัญจน์)
- push c6da5b1 → deploy.sh (pull+migrate+restart bms-api active) → source col ยืนยันบน VPS
- install+enable bms-ongoing-bidder-capture.timer (next 2026-06-28 03:00 UTC = 10:00 ไทย)
- oneshot run: Result=success exit 0, ทั้ง 2 pass รัน (candidates 0/0 ถูกต้อง — epoch=วันนี้ → Pass1 เริ่มมีงาน +7วัน; Pass2 รอ CGD ปล่อย FY2569), Discord ส่ง
- post-migration sanity (VPS): bid_results 240,674 แถว, source dist=[('procure_api',240674)], NULL=0 (backfill ครบ), duplicate(pid,tin)=0 ✅

### Followup #1 (ทำแล้ว 2026-06-27): seen-set Pass 1 — ปิด NOTE Sophia ✅ DEPLOYED
- MAX_LIVE_TRIES=21: empty ครบ 21 ครั้ง→เลิก poll (งานยกเลิก/ไม่ประกาศผลไม่ค้าง re-poll); stored ล้าง counter; error ไม่นับ
- tries dict ใน data/ongoing_capture_live_tries.json (gitignore) · test ใหม่ 2 เคส + suite เขียว
- commit 221f82e · push+deploy.sh VPS · oneshot run success · grep MAX_LIVE_TRIES=4 ยืนยันโค้ดใหม่ live
- **Sophia SAFE** (followup): threshold ไม่มี off-by-one (poll 21 ครั้งพอดีแล้วหยุด), error transient-safe (เฉพาะ empty นับ), stored ล้าง counter, Pass 2 ไม่กระทบ, gitignore ครบ

### Followup #2 (defer): VPS cgd_winners sync incremental+schedule
- ตอนนี้ full re-push → synced_at ใช้เป็น floor ไม่ได้. ไม่เร่งด่วน: CGD ปล่อย FY2569 อีก ~8-9 เดือน (กลางปี 2570)
- **action เตือน:** พอ FY2569 ออก → รัน manual cgd_sync 1 รอบ แล้ว Pass 2 เก็บเฉพาะเจาะจงได้เอง (ไม่ต้องสร้าง infra ตอนนี้)

## งานที่ N+176: เว็บบอร์ดช้า → รวม customer store เว็บเข้า engine DB (เลิก Sheets) (2026-06-30)

### สถานะ: ✅ DEPLOYED (2026-06-30) — TTFB 8.99s→1.17s cold / 0.17s warm; E2E ผ่าน Vercel เก็บจังหวัดไทยถูก; sanity เขียว (5 ราย/0 ซ้ำ/0 test)

### ⚠️ Deploy debt: deploy ด้วย scp(VPS)+vercel CLI — **โค้ดยังไม่ commit/push** (Sebastian_Customer_DB.py, bms_api.py, customers.ts, vercel.ts, package.json, lock). ต้อง commit กัน VPS git pull ทับ scp'd files (ดู [[project_deploy_debt]])

### Root cause (วัดจริง)
- `/portal/world` cold start TTFB **8.99s** — เพราะเว็บ `import { google } from "googleapis"` (lib ยักษ์) ใน `dashboard/web/src/lib/customers.ts` → serverless cold start อืด
- บั๊กเงียบ: เว็บเขียน customer config (class/จังหวัด/⭐) → **Google Sheets อย่างเดียว**, engine (SQLite) ไม่เห็น = ปุ่มหลอก. เว็บ **ไม่เคยเรียก bms_api เลย** (grep ยืนยัน). ดู [[project_customer_store_split]]
- 3 store ไม่ sync: Sheets(เว็บ) / SQLite(engine `/opt/bms/data/bms_customers.db`) / Postgres(หน้าประวัติ)
- Decision (กัญจน์): Option A — เว็บเขียนตรงเข้า engine DB ผ่าน bms_api, province-level ก่อน

### สิ่งที่ทำ (โค้ด — เทส local ผ่านหมด)
- `Sebastian_Customer_DB.py`: `_migrate_v137()` +notes/email/phone บน customers (idempotent ✅)
- `bms_api.py`: `GET/POST /api/portal/customer` (keyed line_user_id, X-BMS-Secret) — POST แตก `notes.classes[].geo.provinces` → `subscription_provinces` (province-first). GUARD: ไม่ทับจังหวัดถ้าแตกไม่ได้ (กัน wipe ค่าจากแชต LINE) ✅
- `dashboard/web/src/lib/customers.ts`: เขียนใหม่ getCustomerByLineId/upsertCustomer → คุย bms_api (fetch), คงรูป Customer เดิม → **call site ไม่ต้องแก้**. ทิ้ง `googleapis` (ออกจาก package.json, tsc exit=0) ✅
- `vercel.json`: region `sin1`
- backup prod DB แล้ว: `/opt/bms/backups/bms_customers_20260630_094431.db` (1.95GB)

### Verify ก่อนทำ
- migration: เพิ่ม notes/email/phone, re-run idempotent OK
- endpoint (asyncio direct): parse จังหวัด unique ✅, 403 guard ✅, upsert→subscription_provinces ✅, phone-only ไม่ wipe จังหวัด ✅, เปลี่ยน notes→จังหวัดตาม ✅, ไม่ซ้ำ ✅
- tsc --noEmit exit=0, googleapis removed

### Followup (รอ deploy — prod ต้อง confirm)
- VPS: ส่ง bms_api.py+Sebastian_Customer_DB.py → run init_schema (v137) → restart bms_api → เช็ค BMS_INTERNAL_SECRET ตั้งจริง
- Vercel: ตั้ง env BMS_API_URL=https://api.butler-bms.com + BMS_INTERNAL_SECRET → deploy
- Migrate: อ่าน Sheets customers(notes) ของ 5 รายเดิม → POST /api/portal/customer (กันค่าเว็บเดิมหาย)
- Sophia sanity + วัด TTFB ใหม่เทียบ 9s
- defer: expires_at เว็บ (engine ไม่มีคอลัมน์ → daysLeft โชว์ 30), ⭐ บนเว็บ (notes.starred) ยังคนละที่กับ job_stars, จังหวัด/อำเภอ/keywords flat ส่งเป็น "" (province มาจาก notes.classes)

## งานที่ N+177: บอร์ด /portal/world โชว์งานจริง Phase 1 (section งานที่ติดตาม) + ⭐→job_stars (2026-06-30)

### สถานะ: ✅ DEPLOYED & VERIFIED

### สิ่งที่ทำ (brainstorm→spec→plan→inline execute ตาม superpowers)
- spec: `docs/superpowers/specs/2026-06-30-portal-real-jobs-design.md` · plan: `docs/superpowers/plans/2026-06-30-portal-real-jobs-phase1.md`
- engine: `GET /api/portal/jobs` (reuse `_portal_jobs`, +budget ใน dict) + `POST /api/portal/star` (toggle job_stars) — pattern X-BMS-Secret เดียวกับ /api/portal/customer. test 2 ไฟล์ผ่าน
- web: `lib/portal-jobs.ts` (getPortalJobs), route `/api/portal/star` (relay session→engine), `world/page.tsx` ดึงงานจริงแทน SEED_JOBS, `world/_client.tsx` render ตาม stage (🔵ยื่นซองได้/🟡รอผล/🏆รู้ผล/⚪วางแผน/❌ยกเลิก) + empty state. ⭐ ผูก project_id จริง เขียน job_stars (เลิก notes.starred บนบอร์ด)

### Verify (prod)
- engine smoke: กัญจน์ได้ 14 งานจริง (won7/prelim3/bidding2/cancelled2) ชื่อ/budget ครบ
- ⭐ E2E (throwaway): toggle ON→true OFF→false, cleaned
- TTFB /portal/world: 1.1s cold/0.47s warm (ไม่ถดถอย)
- sanity เขียว: customers 5/0 test/0 ซ้ำ, followed_jobs 30 + job_stars 4 ไม่เพี้ยน, 0 orphan, queue 184
- commit T1-T5 + push (HEAD=3fc988a), VPS git reconcile (stash+ff-pull) = origin/main สะอาด

### Followup (Phase 2 — defer)
- section "งานใหม่ที่แมตช์" (discovery): ต้องสร้าง matching query บน projects_seen (จังหวัด+keyword) — ยังไม่ทำ
- card discovery: matchedKeywords/ระยะทาง/sme

## งานที่ N+178: LINE Login จริงบนบอร์ด B (เลิก dev-mock) (2026-06-30)

### สถานะ: ✅ DEPLOYED & VERIFIED — กัญจน์ตัดสินใจยกบอร์ด B (Next.js) เป็นหลัก

### Root cause
บอร์ด B (`bid-master-dashboard.vercel.app`) login เป็น dev-mock ทุกคน (Vercel ไม่มี LINE_LOGIN_* env) → ทุกคนกลายเป็น "Dev User (Mock)" 0 งาน → บอร์ดว่าง. ลูกค้าจริงเข้าเป็นตัวเองไม่ได้มาตั้งแต่ต้น → ใช้บอร์ด A (ลิงก์ LINE token) เป็นหลัก

### Fix
- ตั้ง Vercel env (printf กัน BOM): LINE_LOGIN_CHANNEL_ID=2010559564, LINE_LOGIN_CHANNEL_SECRET, LINE_LOGIN_REDIRECT_URI=https://bid-master-dashboard.vercel.app/api/auth/line/callback
- channel = provider เดียวกับบอท → userId ตรง Ua0d90e8
- redeploy; กัญจน์ปรับ channel Developing→Published เอง (error "channel developing status")
- ลบ dev-mock id 13 ตกค้าง

### Verify
- /api/auth/line redirect → access.line.me จริง (ไม่ใช่ mock)
- กัญจน์ login จริง → เห็น 15 งาน; DB ยัง 5 ราย ไม่มี mock/บัญชีใหม่โผล่ ✅

### Followup (บอร์ด B จะเป็นหลัก — ของหลอก/ค้างที่ต้องเก็บ)
- 🔴 หน้าแพ็กเกจ: กดอัปเกรด→"PAYMENT SUCCESS" ปลอม (ไม่มีจ่ายเงินจริง แค่เซฟ tierId)
- 🟡 ปุ่มกระดิ่งแจ้งเตือน (world) = ของประดับ; Sebastian Chat quota = ตัวเลขเฉยๆ; company-stats "COMING SOON"; documents บางหมวด "เร็วๆนี้"
- ⚠️ keyword/งบ/รัศมี เซฟได้แต่ engine ใช้แค่จังหวัด match (Phase 2)
- Phase 2: section discovery "งานใหม่ที่แมตช์"

## งานที่ N+179: เก็บของหลอกบนบอร์ด B (แพ็กเกจปลอม + ปุ่มประดับ) (2026-06-30)

### สถานะ: ✅ DEPLOYED & VERIFIED — บอร์ด B จะเป็นตัวหลัก

### สิ่งที่ทำ
- 🔴 หน้าแพ็กเกจ: ตัด PAYMENT SUCCESS ปลอม + PromptPay QR ปลอม + "ยืนยันว่าชำระแล้ว (Demo)" + ไม่เปลี่ยน tier เอง → เปลี่ยนเป็น **flow แจ้งความสนใจ**: กด "สนใจแพ็กเกจ X" → confirm (สรุป+ราคาโดยประมาณ ไม่มีใบเสร็จ/VAT) → "แจ้งความสนใจ" → "ได้รับเรื่องแล้ว ทีมงานติดต่อกลับ"
- engine `POST /api/portal/upgrade-request {tier,billing}` → ส่ง Discord แจ้ง admin (lazy import Sebastian_Discord_Notify) + test (mock Discord)
- web route `/api/portal/upgrade-request` relay session→engine
- ซ่อนของประดับ: ปุ่มกระดิ่งแจ้งเตือน (world TopBar), block COMING SOON สถิติเชิงลึก (company-stats), block "เร็วๆนี้" สรุป TOR/BOQ (documents)

### Verify (prod)
- upgrade-request: 403 guard ✅, happy path กัญจน์ premium → {ok:true} + Discord เด้งจริง
- vercel build ผ่าน (ไม่มี unused/type error), tsc exit=0
- push afc9b69 + VPS git reconcile (stash+ff-pull) = origin สะอาด

### ของหลอก/ค้างที่เหลือบนบอร์ด B (Phase ต่อ)
- Sebastian Chat quota ring (world) = ตัวเลขเฉยๆ (แชตจริงใน LINE) — ยังคงไว้ (ไม่ถึงกับหลอก แค่ข้อมูล)
- keyword/งบ/รัศมี เซฟได้แต่ engine match แค่จังหวัด (Phase 2 keyword matching)
- section discovery "งานใหม่ที่แมตช์" (Phase 2)

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
