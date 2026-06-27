# Bid Master System — Progress Log

> เก็บเฉพาะ entry ล่าสุด (~20 อัน). entry เก่ากว่า N+122 อยู่ใน progress_log_archive.md

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

---

## งานที่ N+141: RECENT_FY += 2569 (รวมปีงบปัจจุบัน) → validate ต.บึงโขงหลง (2026-06-16)

### สถานะ: ✅ DONE — 2569 deployed VPS (ae39c43) · validation: บึงโขงหลงยัง 🟠 (เพดานยืน) · นาทม 🟢 ไม่ regression

### สิ่งที่ทำ
- `cgd_intel.py:27` `RECENT_FY = ("2566","2567","2568")` → **เพิ่ม `"2569"`** (กัญจน์สั่ง 2026-06-16). เหตุผล: 2569=ปีงบปัจจุบัน งานสด recency-weight 1.0 แต่ถูก hard SQL filter ตัดทิ้ง → ESS พื้นที่บางขาดงานสดที่ควรนับมากสุด
- RECENT_FY ใช้เป็น hard filter ใน `_fetch`/`_fetch_scope` (cgd_intel) + `competitor_trend` → กระทบ price scope + winrate ladder (`_scope_ids`→`_field_auctions`)
- เขียน `scripts/_validate_winrate_tambon.py` — เรียก `intel_context()` ต.บึงโขงหลง+ต.นาทม, เปิด log `bid_field` เห็นบรรทัด `winrate ... conf=<tier>` (tier จริง ไม่เดาจาก emoji)

### Verify (local — code ไม่พัง)
- **test_cgd_intel(BMS_ENV=dev) · test_winrate_grid · test_bid_field = ALL PASS** · py_compile clean
- ไม่มี test hardcode len(RECENT_FY)==3; fixture ใช้ fy=2568 (อยู่ใน set ทั้งก่อน/หลัง)

### ⚠️ Validation บล็อก: ข้อมูลอยู่ VPS
- local `bms_customers.db`: cgd_winners=0, bid_results=0 · `winner_history.db` ไม่มี table bid_results → **validate ต.บึงโขงหลง รันบน dev ไม่ได้**
- SSH dev→VPS = Permission denied (ตรงกับ resume note) → กัญจน์ต้อง `git pull` + รัน validate บน VPS เอง

### NEXT (กัญจน์ บน VPS)
1. confirm push → `git pull` บน VPS
2. `BMS_DATA_DIR=/opt/bms/data python3 scripts/_validate_winrate_tambon.py`
3. ดู conf tier ต.บึงโขงหลง: 🟠 จังหวัด (เพดานโครงสร้างยืน) หรือ 🟡/🟢 (2569 ปลดล็อก)

### ✅ ผล validation บน VPS (BMS_DATA_DIR=/opt/bms/data, ae39c43)
- **ต.บึงโขงหลง:** `conf=จังหวัด ess=142.5 k_local=9` → **ยัง 🟠 จังหวัด** (2569 ไม่ปลดล็อก). อำเภอ full-field concrete-contested = **3 งานเท่าเดิม** (เดชา28%/ชัยฤทธิ์41%/ว่องเจริญ36%) < MIN_AUCTIONS(5). จังหวัด 35→**36 งาน** 300→**314 ราย** (fy2569 active แต่ +1 งานเท่านั้น = coverage 2569 ยังบาง ปีงบเพิ่งเริ่ม/poll ไม่ทัน) → **ยืนยันเพดานโครงสร้าง N+140**: อำเภอบึงโขงหลงเล็กเกินไป งาน concrete-contested ไม่ถึง 5 ไม่ว่าปีไหน
- **ต.นาทม:** `conf=local ess=16.8 k_local=8` → **ยัง 🟢 local ไม่ regression** · 6 งานอำเภอ 47 ราย · 🏆 2B เจ้าตลาด หจก.เอส.ที.เค.เพาเวอร์ (ชนะ 60% 3/5, ลด ~39%) ยังโผล่ → 2569 ปลอดภัย ไม่ทำของเดิมพัง

### บทเรียน / decision
- **2569 = keep** — ไม่ regression + จะช่วยเองเมื่อ coverage fy2569 หนาขึ้น (ตอนนี้บางเพราะปีงบเพิ่งเริ่ม)
- **บึงโขงหลงปลดล็อก 🟡 ด้วย data ไม่ได้** (backfill หมดแล้ว + 2569 หมดแล้ว ยัง 3 งาน) → เหลือแค่ B″ (ผ่อน cf / center intermediate scope) หรือ **ยอมรับ 🟠 = คำตอบสถิติที่ถูก** (อำเภอ data น้อยจริง center จังหวัดปลอดภัยกว่า)
- 🔍 จุดที่ B″ น่าทำสุด = **center column** บึงโขงหลงโชว์ "เฉลี่ย 9 ผู้ยื่น (±6)" จากจังหวัด แต่อำเภอจริง ~3-4 ราย → ตาราง%อาจให้ภาพสนามแน่นเกินจริง (center ที่ intermediate=อำเภอ จะใกล้ความจริงกว่า แม้ conf ยัง 🟠)

### ✅ DECISION (กัญจน์ 2026-06-16): ยอมรับ 🟠 บึงโขงหลง — ปิดงาน
- 🟠 จังหวัด = คำตอบสถิติที่ถูกสำหรับอำเภอ data น้อย (center จังหวัดปลอดภัยกว่าเดา n จาก 3 งาน). 2569 keep.
- **B″ (center-intermediate) = defer** → เก็บเป็น offline monitor ก่อน (วัด center error หลายพื้นที่ค่อยตัดสิน) ตามแผน B″ เดิม + value-principle (evidence ก่อน hypothesis)
- Win-Rate B′ closed-loop สมบูรณ์: นาทม 🟢 + 2B เจ้าตลาด · บึงโขงหลง 🟠 graceful + price sacred

### Followup
- ~~rotation progress_log~~ ✅ done (N+142) · ~~B″ offline monitor~~ ✅ implemented (N+142)
- ดู [[project_winrate_bprime_coverage_limit]]

---

## งานที่ N+142: B″ offline center-error monitor (observe-only) + rotate progress_log (2026-06-16, overnight)

### สถานะ: ✅ code+test DONE (commit local รอกัญจน์ review+deploy เช้า · ไม่ push)

### สิ่งที่ทำ (autonomous คืนกัญจน์นอน)
1. **rotate progress_log** N+101..N+121 → archive (1120→576 บรรทัด, เหลือ 20 entry · commit แยก)
2. **B″ offline monitor** — ตอบ decision N+141 ("เก็บ monitor วัด center error ก่อนตัดสิน B″"):
   - `bid_field._center_stats(auctions)` — สกัด centering math (mean/sd→ns/k_mid) จาก `_evaluate_winrate` (DRY, refactor behavior-preserving)
   - `bid_field._log_center_breadcrumb(...)` — **observe-only**: เมื่อ ladder ผ่อน (conf!=None) เขียน ndjson เทียบ center stats 3 scope (local/อำเภอ/จังหวัด) + delta_mean + amphoe_eligible. exception-safe (ห้ามทำการ์ดพัง)
   - wire ใน `field_and_winrate` — 3 บรรทัด หลังได้ grid/conf (ไม่แตะ output)
   - `scripts/analyze_center_monitor.py` — `summarize()` + decision branch (eligible≥5 ∧ %Δ≥2 ≥50% → "B″ คุ้ม")
   - spec: `docs/superpowers/specs/2026-06-16-winrate-center-monitor-design.md`

### Verify (TDD — RED→GREEN ทุกชิ้น)
- `test_center_monitor.py` 7 tests PASS (center_stats · breadcrumb เขียน/skip/exception-safe · integration field_and_winrate · summarize)
- **regression: test_winrate_grid + test_bid_field + test_cgd_intel = ALL PASS** → พิสูจน์ observe-only ไม่เปลี่ยน output
- py_compile clean · analysis render ถูก (synthetic 6 recs: median Δ=4.0, %≥2=60%)

### NEXT (กัญจน์ เช้า)
1. review diff → push (commit local 3 ก้อน: rotate · monitor · [N+142 doc])
2. deploy VPS → monitor เริ่มสะสม breadcrumb เงียบๆ ตอน D0 จริงที่ผ่อน 🟡/🟠
3. หลังสะสม ~2 สัปดาห์ → `analyze_center_monitor.py` ดู distribution → ตัดสิน B″ ด้วย evidence จริง

### Followup
- monitor = observe-only ยังไม่เปลี่ยน centering (= B″ เอง ยัง defer ตาม decision N+141)
- ดู [[project_winrate_bprime_coverage_limit]]

---

## งานที่ N+143: Discovery ล่มตอนเดินทาง → diagnose harvest ผูกเน็ตที่ Cloudflare ไว้ใจ (2026-06-17)

### สถานะ: 🔴 discovery down (รอ auto-heal ตอนกลับเน็ตบ้าน) · 📝 diagnose + decision บันทึกแล้ว · ไม่แตะ prod

### อาการ
กัญจน์เดินทาง เครื่องบ้านปิดทั้งวัน → VPS discovery fail ทุกรอบตั้งแต่ ~13:00 (16 มิ.ย. เวลาไทย):
`❌ ไม่ได้ token (provider=manual, state=expired)`. รอบสำเร็จล่าสุด 07:00 (16 มิ.ย.) = +0 งานใหม่ → ตอนหลุดไม่มีงานค้าง. VPS service อื่น (winner-poller/line-sender/enrichment/canary/deadman) ปกติ.

### Root cause (เชิงสถาปัตยกรรม — ไม่ใช่ bug)
harvest X-Announcement-Token ผูกกับ **"เน็ตที่ Cloudflare จัดว่าไว้ใจ (residential)"** ไม่ใช่ IP เฉพาะ:
- เน็ตบ้าน → path `cfturnstile/validate` (มี blessed token) → harvest จับได้ auto
- hotel wifi / mobile hotspot → path `cfturnstile/bypasscloudflare` (**ไม่มี** token)

### ลองทุกทางจาก laptop เน็ตเดินทาง — ตันหมด (พิสูจน์แล้ว)
1. mint generateToken (curl) → reject `validateCfTurnTile:false`
2. generateToken **ในหน้า browser** (มี cf_clearance) → ก็ reject (token ไม่ portable)
3. อ่าน token จาก localStorage/sessionStorage → ไม่มี (SPA สร้างสดทุก req)
4. ปุ่มค้นหา disabled ถาวร → trigger search ให้ token หลุดไม่ได้
5. harvest validate (browser-level + waitForDebuggerOnStart + fresh profile) → เน็ตนี้วิ่ง bypasscloudflare ไม่มี token
6. ทดสอบ hotspot ตรงๆ → ยัง bypasscloudflare เหมือนเดิม

### Decision
- **ปล่อย auto-heal ตอนกลับบ้าน** (gap เสี่ยงต่ำ — +0 งานล่าสุด, D0 เงียบ). อย่างมงงม harvest เน็ตเดินทางอีก
- **ต้อง decouple ก่อนกัญจน์ย้ายหอ** (เน็ตหออาจไม่ residential → เสี่ยงตันถาวร) → residential-proxy ให้ VPS (ADR-003) / RPi พกพา
- บันทึก memory `project_harvest_network_trust.md` (กัน Claude ครั้งหน้างมซ้ำ)

### Tooling สร้างไว้ (ยังไม่ commit — experimental/diagnostic)
`scripts/harvest_existing_tab.py`, `scripts/harvest_fresh_browser.py` (browser-level CDP harvest + diagnostic endpoint logging)

### NEXT
- กัญจน์กลับถึงเน็ตบ้าน + เปิดเครื่อง → discovery resume + catch-up เอง
- ~~ก่อนย้ายหอ: ร่างแผน residential-proxy decoupling~~ ✅ ร่างแล้ว (N+144, ADR-004)
- ดู [[project_harvest_network_trust]] · [[project_incident_control_plane]] · [[project_deploy_debt]]

---

## งานที่ N+144: Harvest Token Decoupling plan (ADR-004) — probe-first (2026-06-17, overnight)

### สถานะ: ✅ draft เสร็จ (รอกัญจน์ review+เลือก · ยังไม่ implement) — `docs/superpowers/specs/2026-06-17-harvest-token-decoupling-plan.md`

### ที่มา
followup N+143 "ทางเลือก ข" — ตัด discovery จาก "PC บ้าน + เน็ต residential เดียว" ก่อนกัญจน์ย้ายหอ.

### แก่นของแผน (probe-first, อย่า assume → ซื้อ hardware ก่อนเวลา)
- **Key unknown:** `harvest_and_push.py:10` เขียนว่า "VPS/datacenter เสี่ยง challenge" — แต่เป็น assumption **ก่อน** JA3 fix (5997fdf ที่ทำ VPS discovery search ผ่าน 0 challenge). **ยังไม่เคย test VPS harvest token โดยตรง** (N+143 พิสูจน์แค่ laptop เน็ตเดินทาง)
- **Decision tree ถูก→แพง:** PROBE 1 = headless Chrome บน VPS ดู response path (`cfturnstile/validate` มี token vs `bypasscloudflare` ไม่มี). ได้ → **Option 0 ฟรี** (port harvest ไป VPS เลิก scp). ตัน → PROBE 2 residential proxy trial → Option A. ตันทั้งคู่ → Option C ชั่วคราว (WakeToRun)
- **🔑 insight:** **RPi (candidate เดิม) แก้ N+143 ไม่ตรงปม** — ปมคือผูก "network-trust" ไม่ใช่ "device". RPi ในหอที่เน็ตไม่ residential = ตันเท่าเดิม. ทาง decouple จริง = 0 หรือ A (ตัด dependency เรื่องประเภทเน็ต)

### NEXT (กัญจน์ หลัง discovery heal)
1. รัน PROBE 1 บน VPS (headless Chrome → log path) = ฟรี ตอบ unknown ใหญ่สุด
2. ผลออก → เลือก Option 0/A → implement
3. เพิ่ม alert harvest_stale>60m (deadman มีบางส่วน)

### Followup
- ทั้ง resolve plane (ADR-003 VPS throttled ✅) + harvest plane (ADR-004 รอ) decouple = ตัด PC บ้านหมด → ปิด [[project_deploy_debt]] ก้อนใหญ่
- ดู [[project_harvest_network_trust]] · [[project_incident_control_plane]]

---

## งานที่ N+145: Backfill ทั้งจังหวัด — WAF block VPS → pivot residential home-fetch (2026-06-18)

### สถานะ: 🚧 fetch กำลังรันบนเครื่องบ้าน (~2,606 งาน, ETA ~2 ชม.) · รอ sync กลับ VPS

### บริบท
กัญจน์ขอ backfill bid_results **ทั้งจังหวัด** (นครพนม+บึงกาฬ) — เดิมทำเฉพาะ 3 อำเภอเป้าหมาย (N+140). dry-run: **2,632 candidate** (FY2566-69, competitive-set, ทุกประเภทงาน ไม่ใช่แค่ก่อสร้าง)

### 🐛 Root cause: ไม่ใช่ rate-limit แต่เป็น WAF block (ยืนยันด้วย raw HTTP)
- ลอง trickle บน VPS → batch 1 **stored=26 error=74** (74% fail ตั้งแต่ call แรก)
- diag single-call: `generateToken` POST **status 200 แต่ body = F5 BIG-IP "Request Rejected ... support ID"** (ไม่ใช่ JSON token) → **WAF reject IP datacenter**
- VPS time ตอนเทสต์ = ~01:16 ไทย ยังโดน 74% → ไม่ใช่ time-of-day แต่เป็น IP datacenter ไม่ถูกไว้ใจ (ตรง [[project_discovery_nodata_waf_turnstile]] + [[project_harvest_network_trust]])
- **เทสต์เครื่องบ้าน (residential): token POST 200 → JSON token จริง** → eGP WAF ไว้ใจ IP บ้าน

### Approach B (กัญจน์เลือก): fetch บ้าน → sync VPS — ไม่ขยับ DB 460MB
1. VPS: `select_candidates` dump → `/tmp/backfill_cands.json` (2,606 หลัง dedup) → scp ลงบ้าน
2. บ้าน: `scripts/_backfill_home_fetch.py` (ONE-OFF) — get_procure_result ทีละงาน, resumable, dump `data/_backfill_home/backfill_results.json` = `{pid:{bidders,announce_date}}`. smoke 3/3 ผ่าน · checkpoint แรก **25/25 stored error=0**
3. (รอ) scp results กลับ VPS → import ผ่าน `record_bid_results` (storage path เดิม test แล้ว, INSERT OR REPLACE ปลอดภัย PK project+tin)

### หยุด trickle VPS แล้ว (pkill) — ได้ +26 งาน (bid_results 1055→1081) ไม่เสียหาย

### NEXT (เมื่อ fetch เสร็จ)
1. scp `backfill_results.json` → VPS → import (verify bid_results jobs เพิ่ม ~2,600)
2. sanity: duplicate, winner sane → ลบ `_backfill_home_fetch.py` + temp files
3. คิด durable fix: residential-proxy (ADR-004) ให้ VPS ยิงเองได้ ไม่ต้องพึ่งเครื่องบ้าน
- ดู [[project_harvest_network_trust]] · [[project_winrate_bprime_coverage_limit]]

---

## งานที่ N+146: False-positive matcher — งานไตเทียมหลุด LINE → negative keyword surgical (2026-06-19)

### สถานะ: ✅ เสร็จ (deploy VPS + verify)

### บริบท
กัญจน์เช็ก discovery รอบ 00:25 (catchup จากฟลุค harvest token บนเน็ตเดินทาง) — ส่ง LINE ไป **3 งาน** (customer 2-5) ไม่ใช่ 0 ตามที่ผมเดาจาก Discord summary. 1 ใน 3 = **"ซ่อมแซมระบบน้ำบริสุทธิ์สำหรับเครื่องไตเทียม" (รพ.ธาตุพนม)** = งานการแพทย์ ไม่เกี่ยวก่อสร้าง

### 🐛 Root cause
- keyword ก่อสร้าง `"ท่อ"` (substring) ไปโดน **"เดินท่อ / ท่อน้ำทิ้ง"** ในชื่องาน → `passes_keyword=(True,'ท่อ')`
- `negative_keywords` = **ว่าง `[]`** → ไม่มีตัวกรองออก → keyword✓ + จังหวัด✓ + หาตำบลไม่ได้ → `soft_include` → ส่ง LINE
- (บทเรียนผม: ดู product DB `delivery_log`/`notification_queue` เป็น source of truth ไม่ใช่ Discord summary — Discord "ไม่แจ้ง LINE" สะท้อนแค่ filter อำเภอ pilot ไม่ใช่ queue ต่อ tenant)

### Fix: surgical negative `"น้ำบริสุทธิ์"` (ไม่ใช่ "ไตเทียม")
- sanity scan 2,430 ชื่องาน: "น้ำบริสุทธิ์" โดน **1 งานพอดี** (ตัวที่ผิด) — zero collateral
- **ไม่ใช้ "ไตเทียม"** เพราะจะตัด **"จ้างก่อสร้างซ่อมแซมศูนย์ไตเทียม"** (อาคาร = งานก่อสร้าง legit) = false negative
- ไม่ทำ rule ใหญ่ (จ้างเหมาบริการ+เครื่อง/ระบบ) — งานบริการแพทย์ส่วนใหญ่ถูกตัดอยู่แล้ว (ซื้อ→material gate / จ้างเหมาไม่โดน keyword), ตรง design recall-biased+reactive negative

### Verify (VPS, config deploy แล้ว)
- ไตเทียม → `❌ CUT (negative:น้ำบริสุทธิ์)` · ถนนนาทม×2 / ผิวทางศรีสงคราม / ชลประทาน → `✅ ผ่าน` (ไม่มี regression)
- backup: `backups/matching_preferences_local_20260619_023621.json` + VPS `.bak_20260619_023621.json`
- deploy แบบ scp ไฟล์ตรง (ไม่ git pull) เพราะ VPS git (ae39c43) ≠ local main (fed5704) diverged — deploy debt

### Followup
- ⚠️ **per-tenant matching debt:** negative นี้ global=profile ก่อสร้างเท่านั้น. รับ tenant อุปกรณ์การแพทย์เมื่อไหร่ "ไตเทียม/เอกซเรย์" = positive ของเขา → matching prefs ต้องแยก per-tenant ([[project_architecture_decision_subscribe_filter]]). อย่าทำตอนนี้ (YAGNI)
- ถ้างานบริการแพทย์หลุดมาอีก → เติม negative แม่นๆ ทีละตัว (reactive loop)

## งานที่ N+147: Portal "งานที่ติดตาม" — UI 5 ปรับ (ชื่อเต็ม/แยก PRELIM-W0/countdown/rename) (2026-06-20)

### สถานะ: ✅ เสร็จ (deploy VPS scp + restart)

### บริบท
กัญจน์ขอแก้หน้า `/portal` (ลิงก์ "งานของฉัน") 6 อย่าง. ทำได้ 5 ใน `scripts/bms_api.py` ไฟล์เดียว. ข้อ 6 (deadline+countdown ขั้นประชาพิจารณ์ B0) **defer** — ไม่มี data (B0 ข้าม deadline gate, `Sebastian_Enrichment_Worker.py:311`)

### สิ่งที่ทำ (`_portal_jobs` data + `_portal_page_html` view)
1. ชื่องานเต็ม — เอา `[:80]` ออก
2. แยกการ์ด **PRELIM (สรุปราคาเบื้องต้น)** vs **W0 (ประกาศผู้ชนะทางการ)** — สัญญาณ = `followed_jobs.last_stage_notified` (เพิ่ม group "prelim" + อ่าน lsn ใน query). prelim โชว์ราคาต่ำสุดจาก bid_results price_proposal (graceful ถ้าไม่มี)
3. "กำลังประมูล" → "ประกาศวันยื่นซอง"
4. Countdown `_countdown_th` (เหลือ N วัน/วันนี้/เลยกำหนด) + `_fmt_date_th` วันที่ ISO→ไทย (graceful fallback) บนการ์ด bidding
5. "รับฟังความเห็น" → "รับฟังคำประชาวิจารณ์"

### Verify
- test เดิม `test_portal_page.py` + `test_portal_jobs.py` อัปเดต label ใหม่ + เพิ่มเคส prelim → **PASS** ทั้งคู่
- render จริง: ชื่อ 130+ ตัวไม่ตัด ✓ · 4 กลุ่มแยกถูก ✓ · countdown "เหลืออีก N วัน" ✓
- deploy: VPS bms_api.py sha == local HEAD (ไม่มี hotfix ค้าง) → backup `.bak` + scp + `systemctl restart bms-api`

### Followup
- ข้อ 6 ประชาพิจารณ์ deadline = defer (ต้องเพิ่ม ingestion ดึงวันสิ้นสุดวิจารณ์ร่าง TOR จาก eGP)
- คำ "รับฟังคำประชาวิจารณ์" ใส่ตามที่กัญจน์ขอ (ระบบเดิมใช้ "รับฟังคำวิจารณ์")

## งานที่ N+148: Portal — แถบค้นหา + ID งานใต้ชื่อ (2026-06-20)

### สถานะ: ✅ เสร็จ (deploy VPS scp + restart)

### สิ่งที่ทำ (`_portal_page_html`)
- **🆔 ID งานใต้ชื่อ** ทุกการ์ด (`.jid`)
- **🔍 แถบค้นหา** client-side: `<input id=q>` + inline JS filter `.job` ตาม textContent (ค้นชื่อ/ID/พื้นที่) — wrap แต่ละกลุ่มใน `.gw` เพื่อซ่อนหัวกลุ่มที่ไม่มีผล + `#nohit` ตอนไม่เจอ. ไม่มี endpoint ใหม่ (กรองเฉพาะงานที่ติดตามในหน้า ~5-15 งาน)
- แถบค้นหาโผล่เฉพาะ n>0 (หน้าว่างไม่มี)

### Verify
- test_portal_page อัปเดต (มี search/jid/JS assert) + test_portal_jobs → PASS
- deploy: VPS content == HEAD (normalize CRLF→LF: e0c5fb5) → backup + scp + restart bms-api active

### หมายเหตุ deploy debt
- scp จาก Windows = CRLF → VPS hash ≠ git LF hash เสมอ (content เท่ากัน). เช็ค divergence ต้อง `tr -d '\r'` ก่อน sha256 ไม่งั้น false-positive

## งานที่ N+149: Portal — การ์ดผู้ชนะกดได้ → กางผู้ยื่นทุกราย (2026-06-20)

### สถานะ: ✅ เสร็จ (deploy VPS scp + restart)

### สิ่งที่ทำ
- **data** (`_portal_jobs`): won job เพิ่ม `job["bidders"]` = ผู้ยื่นทุกราย (เพิ่ม `is_sme` ใน query bid_results) sort ผู้ชนะก่อน→ราคาเสนอ asc
- **view** (`_card` won): การ์ด `job clickable` + `▾ ดูผู้ยื่นทั้งหมด (N ราย)` toggle → `.detail` ตารางผู้ยื่น (ลำดับ/🏆ผู้ชนะ/🏷SME/ราคาเสนอ). JS เพิ่ม handler `.clickable` (guard `if(q)` รอบ search เดิม, clickable รันเสมอ)
- เอาบรรทัดสรุป competitors (👥 3 ราย) ออก — แทนด้วย detail เต็ม

### Verify
- test_portal_page (+clickable/detail/SME assert) + test_portal_jobs (+bidders sort assert) → PASS
- **node --check** script ที่ render → JS syntax OK (กัน brace เพี้ยน — เคยมี stray `}` ระหว่างทาง)
- render จริง: 3 ราย ผู้ชนะขึ้นก่อน + SME + ราคาเรียง ✓

## งานที่ N+150: Portal Phase 2b/1 — หน้า detail งาน + ประวัติบริษัท (2026-06-20)

### สถานะ: ✅ เสร็จ + LIVE (subagent-driven 6 tasks + final review + deploy)

### บริบท
กัญจน์ขอ: กดการ์ดผู้ชนะ → เด้งหน้าแยก (ย้อนกลับได้) เห็นผู้ยื่นทุกราย + ส่วนลดจากราคากลาง + กดบริษัทดูประวัติ (อัปเดตตามงานที่ประมูล). ทำ **Phase 1** (Phase 2 = มุมเทียบ multi-tenant + ส่วนลดแยกอำเภอ/ตำบล → defer เพราะติด data: customers ไม่เก็บบริษัท tenant + งานใน bid_results มีพิกัดแค่ 7/1084). spec+plan: `docs/superpowers/{specs,plans}/2026-06-20-portal-job-company-detail*`

### สิ่งที่ทำ — โมดูลใหม่ `scripts/portal_views.py` (data+render แยกจาก bms_api)
- `job_detail(conn,pid)` → ผู้ยื่นทุกราย sort ผู้ชนะก่อน→ราคา + ส่วนลด `(1-price/budget)*100` (budget>0)
- `company_profile(conn,tin)` → สถิติ (ยื่น/ชนะ/win-rate/จังหวัด) + discount histogram (bucket 5%) + by_year (ปีจาก project_id[:2], ใหม่→เก่า)
- `render_job_page` / `render_company_page` → HTML มือถือ + **กราฟ inline CSS bar** (ไม่พึ่ง chart lib) + escape ครบ
- `bms_api`: 2 route `/portal/job` + `/portal/company` (verify token เดิม) + การ์ด won เปลี่ยนจาก expand inline (N+149) เป็น **ลิงก์** ไป `/portal/job` (ลบ `.clickable/.detail` JS+CSS, `_portal_page_html` รับ `token`)

### Process: subagent-driven (skill)
- 6 code tasks × (implementer haiku/sonnet + task reviewer sonnet) ทุก task spec✅ quality approved
- **final whole-branch review (opus): READY** — URL↔route ตรง 6 เส้น (กับดัก `from`/`from_`), token ทุก route, escape ครบ, ไม่มี circular import
- ledger: `.superpowers/sdd/progress.md`

### Verify
- 4 test suites PASS (portal_views/routes/page/jobs) + compile OK
- deploy VPS scp 2 ไฟล์ → content==HEAD `a3ee218`, active, import OK
- **e2e real-data:** งาน 68089533088 (ราคากลาง 981,714) ผู้ชนะส่วนลด 16.2% ✓ · company page stat+กราฟ+timeline ✓ · งาน budget=0 → ส่วนลด "—" graceful ✓
- commits 74ce63f..067f1bb (6) + deploy

### Followup
- Phase 2: (1) เพิ่ม map customers→บริษัท tenant (มุมเทียบ "เรา") (2) parse อำเภอ/ตำบลจากชื่องาน (ส่วนลดแยกพื้นที่)
- cleanup เล็ก (ไม่บล็อก): `agree` field ใน job_detail ไม่ถูกใช้, `_baht` ซ้ำ bms_api/portal_views
- ~~การ์ดกลุ่มอื่น (bidding/prelim) ยังไม่ลิงก์~~ → ทำใน N+151

## งานที่ N+151: Portal Polish A — ทุกกลุ่มการ์ดลิงก์ detail + detail ปรับตาม stage (2026-06-20)

### สถานะ: ✅ เสร็จ + LIVE

### สิ่งที่ทำ
- `_card` (bms_api): bidding/prelim/pre เป็นลิงก์ `/portal/job` ด้วย (เดิมเฉพาะ won) + hint "ดูรายละเอียด →"
- `job_detail` (portal_views): คืน `deadline` (project_locations) + `pred_lo/pred_hi` (price_predictions) — ทั้งคู่ try/except OperationalError กัน dev DB ไม่มี column/table
- `render_job_page`: โชว์ ⏰ยื่นซอง + ⏳countdown + 💵คาดราคา ตามที่มี; งานไม่มีผู้ยื่น → "ยังไม่มีผู้ยื่น" แทนตารางว่าง
- เพิ่ม `_fmt_date_th`/`_countdown_th` + TZ_TH ใน portal_views (dup เล็กกัน import bms_api)

### Verify
- 4 test suites PASS (เพิ่มเคส `render_job_page_bidding` + ทุกกลุ่มลิงก์ใน test_portal_page) + compile OK
- deploy scp 2 ไฟล์ → hash ตรง HEAD (bms_api 5739e59, portal_views 82f49ad), active, import OK
- e2e จริง: งาน 68109435680 (deadline ผ่านแล้ว, 0 ผู้ยื่น) → "ยังไม่มีผู้ยื่น" + ยื่นซอง + countdown ✓; search filter ยังทำงาน
- commit bc7da7f · backup `.bak_20260620_133443`

### Followup
- ~~Polish B (โน้ตต่องาน write path)~~ → ทำใน N+152

## งานที่ N+152: Portal Polish B — ไทม์ไลน์งานสร้างเอง (รางรถไฟ) + โน้ต CRUD (2026-06-20)

### สถานะ: ✅ เสร็จ + LIVE (subagent-driven 4 code tasks + final review opus + deploy)

### บริบท
กัญจน์ขอ: ในหน้า `/portal/job` ให้ user สร้างแผนงานเอง — จดวันที่ + สิ่งที่จะทำ (เช่น "21 ม.ค. โทรหาช่าง") เรียงเป็นรางรถไฟ เพิ่ม/แก้/ลบได้. **ไม่ใช่** timeline อัตโนมัติจากระบบ — user สร้างเองล้วน. spec/plan: `docs/superpowers/{specs,plans}/2026-06-20-portal-job-timeline-notes*`

### สิ่งที่ทำ
- **schema** (`Sebastian_Customer_DB`): `_migrate_v128()` สร้าง `job_notes(id,customer_id,project_id,entry_date,note,created_at,updated_at)` — เรียกใน init_schema
- **data** (`portal_views`): `list/add/edit/delete_job_note` + `_valid_date` — ownership `WHERE id=? AND customer_id=?`, validate note/date, parameterized SQL
- **render** (`render_job_page(...,notes=None)`): section "🚂 ไทม์ไลน์ของฉัน" — ฟอร์มเพิ่ม (`<input type=date>`+text) + ราง (`.rail`/`.rstation` CSS จุด+เส้น) แต่ละ entry แก้/ลบได้. ไม่มี JS. เลิก early-return ตอน bidders ว่าง (timeline ขึ้นทุกกรณี)
- **routes** (`bms_api`): GET `/portal/job` resolve customer + notes; POST `/portal/job/note` (add/edit/delete → 303 redirect). customer derive จาก token ไม่เชื่อ client

### Process: subagent-driven
- 4 code tasks × (impl haiku/sonnet + review sonnet) ทุก task spec✅ approved
- **final review opus: READY** — form field names ↔ POST handler ตรงเป๊ะ, security ครบ (auth/ownership/escape/parameterized/no-JS), migration idempotent

### Verify
- 6 test suites PASS + compile OK
- deploy 3 ไฟล์ → init_schema สร้าง job_notes (7 cols) → hash==HEAD (Sebastian_Customer_DB 96f323a, portal_views 54125b3, bms_api 94741b3), active
- **e2e prod จริง:** GET render timeline+add form ✓ · write→ownership(foreign delete กันได้)→cleanup net-zero ✓ (ใช้ sentinel pid ไม่แตะงานจริง)
- commits e6b7b1e..7efb5e8 (4) · backup `.bak_20260620_142817`

### Followup
- ~~reminder/แจ้งเตือนตามวันที่ใน timeline~~ → ทำใน N+153 (shadow)
- cleanup: `_baht`/date helpers ซ้ำ bms_api↔portal_views (ยอมรับได้ กัน circular import)

## งานที่ N+153: Timeline Reminder — LIVE (07:30, วันนี้+พรุ่งนี้) (2026-06-20)

### สถานะ: ✅ LIVE บน VPS (timer enabled, ส่ง LINE จริง)

### อนุมัติ go-live
กัญจน์: "07:30 โอเค เตือนล่วงหน้า 1 วันด้วย เปิด live เลย" → แก้เตือน **วันนี้+พรุ่งนี้** (ป้าย [วันนี้]/[พรุ่งนี้]) + ExecStart `--live` + enable timer. next run = 2026-06-21 07:30 ไทย.
- **ของจริงแล้ว!** customer 2 (Ua0d90e8) เพิ่งทดสอบเพิ่มไทม์ไลน์จริง (งาน 69059453079: "โทรหาข้อมูลงาน" 21 มิ.ย. + "โทรหาช่าง" 23 มิ.ย.) → พรุ่งนี้ 07:30 จะได้เตือนจริง = ฟีเจอร์ครบวงจรมีคนใช้
- token live โหลดได้ (172) · ใช้ send_line_push ตัวเดียวกับ daily-summary (proven prod)

### บริบท
ต่อยอด N+152 (job_notes timeline). เตือนเมื่อถึงวันที่ที่ user จดไว้ (entry_date == วันนี้). ทำตอน user หลับ → ทำแบบ **observe-only** กัน LINE เด้งโดยไม่ตั้งใจ (pattern shadow/canary ของโปรเจกต์)

### สิ่งที่ทำ — `scripts/timeline_reminder.py`
- `find_due_reminders(conn, today)` → job_notes entry_date==วันนี้ ของ customer active, จัดกลุ่มต่อ user (รวมหลายงาน/รายการเป็นข้อความเดียว)
- `build_reminder_text` → ข้อความ LINE "🚂 ไทม์ไลน์วันนี้..."
- **SAFE-BY-DEFAULT:** รันเฉยๆ = dry-run (shadow log `data/timeline_reminder_log.ndjson`); ต้อง `--live` ถึง push (ใช้ `Sebastian_LINE_Sender.send_line_push`)
- systemd unit `bms-timeline-reminder.{service,timer}` (07:30 ไทย) — **สร้างไว้ ยังไม่ enable**, ExecStart shadow (ต้องเติม `--live` เอง)

### Verify
- test_timeline_reminder PASS (กรอง active+วันนี้ ถูก, group ต่อ user/งาน, build text)
- deploy scp script → shadow-run บน prod: insert today-note → เจอ 1 due user + ข้อความถูก → delete net-zero ✓ (ไม่ส่ง LINE)
- commit cce97c4

### Followup
- ดูผลรอบจริงพรุ่งนี้ 07:30 (journalctl -u bms-timeline-reminder) ว่าส่งถึง customer 2 จริง
- เผื่ออนาคต: ปุ่ม "เตือนแล้ว/เลื่อน" ในข้อความ · ปรับรอบเวลาต่อ user
- commit 6bc0e6a (go-live) ต่อจาก cce97c4 (shadow)

## งานที่ N+154: Portal — โน้ตภาพรวม (job_overview) แยกจากไทม์ไลน์ (2026-06-20)

### สถานะ: ✅ เสร็จ + LIVE

### บริบท
กัญจน์: "อยากมีโน้ตอีกอันจดภาพรวม ไม่ใช่ไทม์ไลน์" → free-form note 1 อันต่องาน (ไม่มีวันที่) แยกจากไทม์ไลน์ (job_notes ที่มี entry_date)

### สิ่งที่ทำ (inline TDD — เล็กกว่า Polish B)
- **schema** `_migrate_v129()`: `job_overview(customer_id, project_id, note, created_at, updated_at, PK(customer,project))` — 1 โน้ต/งาน/คน
- **data** (`portal_views`): `get_job_overview` (คืน '' default) + `save_job_overview` (upsert UPDATE→INSERT, note ว่าง=ลบ, ต่อ customer)
- **render** `render_job_page(...,overview="")`: `_render_overview` section "📝 โน้ตภาพรวม" (textarea prefilled + 💾) วางเหนือไทม์ไลน์ + CSS `.ovf`
- **route**: GET fetch overview; POST action `save_overview` (reuse `/portal/job/note`)

### Verify
- 7 test suites PASS (เพิ่ม overview ใน schema/notes/views/routes test) + compile OK
- deploy 3 ไฟล์ + init_schema สร้าง job_overview → hash==HEAD (Sebastian_Customer_DB 5e4c53b, portal_views 8c25195, bms_api f0b0530), active
- e2e prod: save→read "ภาพรวมทดสอบ"→empty=delete net-zero ✓
- commit 04cdbf9 · backup `.bak_<ts>`

### โครงโน้ต 2 แบบในหน้า detail
- 📝 **โน้ตภาพรวม** (job_overview) = free-form 1 อัน แก้ทับ — ภาพรวม/คนติดต่อ/เงื่อนไข
- 🚂 **ไทม์ไลน์ของฉัน** (job_notes) = หลาย entry มีวันที่ เรียงราง + reminder 07:30

## งานที่ N+155: Portal Phase 2 (part 1) — มุมเทียบเรา (head-to-head) (2026-06-20)

### สถานะ: ✅ เสร็จ + LIVE

### บริบท
กัญจน์เลือก Phase 2 มุมเทียบเรา. ใช้ **ยศประทานรุ่งฯ (tin 0483547000471) เป็น "เรา" ก่อน (seed)**, self-serve picker (ให้ลูกค้าตั้งบริษัทเอง) ไว้ทำทีหลัง. data รวย: เราเจอ ภูริพัฒน์ 25 งาน, ปฐมโชคชัย 19, ...

### สิ่งที่ทำ (inline TDD)
- **schema** v130: `customers +company_tin` (บริษัทของ tenant; NULL=ยังไม่ตั้ง). **seed customer 2 (กัญจน์) = 0483547000471**
- **data** `head_to_head(conn, our_tin, competitor_tin)`: งานที่ยื่นด้วยกัน → shared/our_wins/their_wins/other + ราคาเทียบต่องาน (None ถ้า tin เดียวกัน/ไม่เจอกัน)
- **render** `render_company_page(...,h2h)`: section "⚔️ เทียบกับ <our_name>" (เจอกัน/เราชนะ/เขาชนะ/% + แถวงาน 🟢เรา/🔴เขา/⚪อื่น + ราคา) โชว์เฉพาะมี h2h
- **route** company resolve `company_tin` ของ viewer → คำนวณ h2h → ส่ง render

### Verify
- 7 test suites PASS + compile OK
- deploy 3 ไฟล์ + init_schema (company_tin) + seed กัญจน์ → hash==HEAD (Sebastian_Customer_DB cf56de3, portal_views 22ab5b8, bms_api 79f0c98), active
- **e2e prod:** กัญจน์ดู ภูริพัฒน์ → เจอกัน 25 · เราชนะ 8 · เขาชนะ 0 · section ⚔️ + แถวงานครบ
- commit a9c1b9b

### Followup (Phase 2 ที่เหลือ)
- **self-serve picker:** หน้า portal ให้ลูกค้าค้น+เลือกบริษัทตัวเอง (set company_tin) — ตอนนี้ seed มือ เฉพาะกัญจน์
- ส่วนลดแยกอำเภอ→ตำบล (ยังติด: ต้อง parse location จากชื่องาน)
- seed company_tin ให้ tenant อื่น (Hong/ณฐมน/Mr.suvit) เมื่อรู้บริษัท

## งานที่ N+156: Backfill บ้าน 12K (residential home-fetch) (2026-06-20 → 2026-06-22)

### สถานะ: ✅ เสร็จ — fetch + import ขึ้น VPS แล้ว, coverage 2 จังหวัดเกือบเต็ม

### บริบท (จาก debug session "ทำไม bid_results น้อย")
- bid_results = เฉพาะงานแข่งประมูล (e-bidding) ที่ดึง bidder ครบ — มีแค่ 1,075/13,170 (8%) ของ 2 จังหวัดบ้าน
- เพราะ backfill รันเฉพาะปีล่าสุด + เป็น fetch ทีละงาน rate-limit · eGP ยังเก็บงานเก่าครบ (ดึง 2563 ได้ 12 ราย)
- กลยุทธ์: ดึงจากเน็ตบ้าน (residential) เลี่ยง WAF VPS (`_backfill_home_fetch.py`, ADR-003)

### สิ่งที่ทำ
- VPS `select_candidates(นครพนม+บึงกาฬ, fy 2558-2569)` → **12,093 candidates** (seen 1,015 excluded) → scp local
- รัน `_backfill_home_fetch.py` background (เครื่องบ้าน) — เสร็จ 2026-06-21 22:05: `stored=5993 empty=50 error=3, total_in_results=12090` (cumulative รวมรอบก่อน)
- **2026-06-22: import ขึ้น VPS** — เขียน `_backfill_home_import.py` (one-off, อ่าน JSON → `store.record_bid_results(pid, bidders, fetched_at=announce_date)` แบบเดียวกับ `backfill_bidders.py` production), smoke-test ผ่าน temp DB ก่อน (5 sample projects, idempotent re-run ยืนยัน todo=0 ไม่ insert ซ้ำ), backup prod DB ก่อน (`bms_customers_pre_backfill_import_20260622_052605.db`), รันจริงบน VPS: **stored_projects=11,999, bid_rows=87,394** ใน ~53s
- Sanity หลัง import: bid_results รวม 5,242→82,856 แถว, distinct projects 1,075→13,066 สำหรับ 2 จังหวัด (นครพนม 8,609 + บึงกาฬ 4,457 ≈ เต็ม universe 13,170) · dup PK (project_id,bidder_tin) = 0 · winner price_agree cross-check กับ `cgd_winners.win_price` ตรง · พบ 167 projects มี winner row >1 — ตรวจ sample แล้วเป็นงานจัดซื้อหลาย lot (เช่น เวชภัณฑ์) ที่แต่ละ lot มีผู้ชนะของตัวเอง ไม่ใช่ bug
- ลบไฟล์ temp บน VPS แล้ว (`/tmp/backfill_results.json`, `_backfill_home_import.py`) · `/health` OK หลังเสร็จ

### Followup
- profile/head-to-head ของทุก customer รวยขึ้น (ของกัญจน์ 28 งานแข่งเก่าเข้าครบแล้ว)
- ยังไม่ลบไฟล์ local `data/_backfill_home/` (43MB) + `scripts/_backfill_home_fetch.py`/`_backfill_home_import.py` — รอกัญจน์ยืนยันก่อนเคลียร์ (ข้อมูลขึ้น DB แล้ว ไฟล์ local เป็น artifact เดิมไม่จำเป็นต้องเก็บต่อ)

## งานที่ N+157: Portal company — ผลงานที่ชนะทุกวิธีจัดซื้อ (proc_type) + filter (2026-06-20)

### สถานะ: ✅ LIVE (deploy + e2e prod verified 2026-06-20)

### บริบท (กัญจน์ขอ 4 ข้อ)
1. แยกสถิติประมูล vs เจาะจง (จำนวน+มูลค่า) · 2. งานมูลค่าสูงสุด · 3. สูงสุดประมูล vs วิธีอื่น · 4. filter proc_type

### 🐛 Foundation bug ที่เจอระหว่างทำ (สำคัญ — followup)
- `bid_results` = e-bidding เท่านั้น → ไม่มีงานเจาะจง → 4 ข้อทำจาก bid_results ไม่ได้ → ต้องใช้ `cgd_winners` (winner-only ทุกวิธี)
- **`winner_history.db` column เพี้ยน:** `winner_tin` = วันที่ ("7 มี.ค. 68"), `contract_no` = ราคา. งานประมูล 2 จว. winner_tin สะอาดแค่ **0.9%** (101/10,637). กัญจน์ tin `0483547000471` หาไม่เจอ. source='CGD' ทั้งหมด
- **แต่ `winner` (ชื่อ) ถูกต้อง** → ยศประทาน 282 งาน, ภูริพัฒน์ แยก 3 บริษัทตามชื่อ
- **กัญจน์ตัดสิน:** name-join now + ซ่อม winner_tin ทีหลัง

### สิ่งที่ทำ (inline TDD, surgical)
- `portal_views.won_portfolio(conn, name, proc)`: join `cgd_winners.winner` ด้วย **normalized name** (`_norm_name` ตัด prefix นิติบุคคล+space, `_prefilter_key` คำยาวสุดทำ LIKE prefilter กัน full-scan 617K). bucket `_proc_group` → bid(COMPETITIVE_SET)/specific(เฉพาะเจาะจง)/other. คืน groups{count,value} + top_overall/top_bid/top_nonbid + jobs(filtered by proc)
- `_render_won`: section 🏆 stat ประมูล/เจาะจง/รวม + 💎 มูลค่าสูงสุด + 🥇🥈 สูงสุดแยกวิธี + filter chips (server-side `?proc=`) + job list. CSS `.chips/.chip`
- `render_company_page(...,won)` + route `/portal/company?proc=` ส่ง `data["name"]` → won_portfolio

### Verify
- test_portal_views: +won_portfolio +render_company_won (normalized match, substring-guard เอ vs เอบีซี, proc filter, degrade None) — PASS ทั้ง 11 บล็อก + compile OK
- **real-data (winner_history 617K):** หจก.ยศประทาน=282(ประมูล44/เจาะจง238/💎9.05M), ภูริพัฒน์ซัพพลาย=17, ภูริพัฒน์กรุ๊ป=11 (แยกถูก). ทั้งชื่อย่อ/เต็ม match ตรงกัน
- Sophia skip: เป็น query/render logic, product DB local ว่าง (Sophia ไม่มีอะไรตรวจ) — sanity จริงคือ real-data ข้างบน

### Deploy + verify VPS (✅ เสร็จ)
- scp 2 ไฟล์ → /opt/bms/app/scripts → hash==local (LF-norm) → restart bms-api active + import OK
- `cgd_winners` บน VPS = 617,357 rows (นครพนม 390K+บึงกาฬ 227K), winner name ครบ
- **name-join match: ผู้ชนะ e-bidding 460/467 = 98.5%** (miss = นอก 2 จว./eGP สะกดเพี้ยน); ผู้ยื่นทั้งหมด 65%
- e2e prod: หจก.สกลนครประกิตก่อสร้าง → 281 งาน ฿82.3M (ประมูล 19/เจาะจง 262), section 🏆+chips ครบ

### Followup (ค้าง)
- **🐛 root-cause (defer):** ซ่อม CGD ingestion column-misalignment → winner_tin ถูก → re-sync → กลับไป join ด้วย tin (key ที่ถูก) ดู memory [[project_winner_tin_corruption]]
- name-join miss eGP typo (กิจการร่่วมค้า ่ ซ้ำ / ดีเวลอเมนท์) — ยอมรับได้ตอนนี้

## งานที่ N+158: ตั้งชื่อเว็บ portal = "BMS Bid Board" (2026-06-20)

### สถานะ: ✅ LIVE

### สิ่งที่ทำ
- brainstorm ชื่อกับกัญจน์ → เลือก **BMS Bid Board** (กระดานงานประมูลที่ติดตาม)
- `_portal_page_html`: `<title>` + หัวเว็บ "🗂 BMS Bid Board" + sub "งานที่คุณติดตาม (N)" (เพิ่ม `.sub` CSS)
- LINE reply พิมพ์ "bid board"/"board" ก็เปิดได้ + ข้อความ "เปิด BMS Bid Board — ..."
- deploy bms_api.py → hash==local → restart active → render verify title+header ผ่าน

## งานที่ N+159: Bid Board — ชิป filter ติ๊กเลือกประเภทงาน (2026-06-20)

### สถานะ: ✅ LIVE

### บริบท
กัญจน์อยากติ๊กเลือกว่าจะดูประเภทไหน "ในตอนนี้" (transient) — 4 ประเภทตรงกับ groups เดิม (bidding/prelim/pre/won)

### สิ่งที่ทำ (`_portal_page_html`)
- ชิป checkbox 4 อัน (🔵ยื่นซอง/📊สรุปราคา/🟣ประชาวิจารณ์/🏆ผู้ชนะ) ใต้ search — เฉพาะประเภทที่มีงาน, แสดงเมื่อ ≥2 ประเภท, default ติ๊กครบ
- `.gw` เพิ่ม `data-key`; JS รวม search+checkbox เป็น `apply()` เดียว (กลุ่มโชว์เมื่อ ติ๊ก && มีงาน match คำค้น) — client-side ไม่ reload, ไม่จำข้ามรอบ (YAGNI)
- CSS `.filters/.fchip(.on)` pill toggle

### Verify
- py compile + **node --check JS ผ่าน** + render local (chips/data-key/fck ครบ)
- deploy → hash==local → restart active → render prod: filters row+2chips+data-key+apply ผ่าน
- **แก้ตาม feedback กัญจน์:** เปลี่ยนจาก multi-toggle (ติ๊กออก) → **single-select แบบแท็บ** (ปุ่ม "ทั้งหมด" default + กดประเภท=ดูอันเดียว). button data-key, JS `sel` state. node --check ผ่าน, deploy hash==local active

## งานที่ N+160: ⭐ ที่สนใจ — interest-star layer ใน Bid Board (2026-06-21)

### สถานะ: ✅ เสร็จ (code+test, รอ push/deploy)

### บริบท
กัญจน์อยากมีดาว "ที่สนใจ" อีกชั้นในงานที่ติดตามอยู่แล้ว เพื่อกรองดูเฉพาะงานที่สนใจที่สุด — คนละความหมายกับ ⭐ เดิม (LINE postback `star:<project_id>` → `followed_jobs.starred_at` = เริ่มติดตาม). ออกแบบผ่าน `superpowers:brainstorming` (spec commit `9921c5a`) + วางแผนผ่าน `superpowers:writing-plans` (plan commit `40364c6`, `docs/superpowers/plans/2026-06-21-portal-interest-star.md`) แล้วรันด้วย Subagent-Driven Development บน worktree `worktree-portal-interest-star` (consent จากกัญจน์) — 6 task, implementer+reviewer subagent ต่อ task

### Fix / ผล
- Task 1: ตาราง `job_stars(customer_id, project_id, created_at, PK(customer_id,project_id))` ใน `Sebastian_Customer_DB.py` (`_migrate_v131`) — commit `e8200e2`
- Task 2: `portal_views.toggle_star`/`starred_project_ids` data layer — commit `7e56127`
- Task 3: ปุ่มดาวหน้า job detail (`render_job_page` param `starred`) — commit `fd7f9e3`
- Task 4+5: route `/portal/star_toggle?t=&pid=&back=board|job` + wiring `portal_job_get` — commit `92459c7`
- Task 6: ปุ่มดาว + ชิป filter "⭐ ที่สนใจ" อิสระบน Bid Board listing (`_card` เปลี่ยนจาก `<a class="job joblink">` ห่อทั้งใบ เป็น `<div data-starred>` ครอบ sibling `<a class="star">`+`<a class="joblink">` เลี่ยง nested `<a>`) — commit `d51f2dc`
- ทุก task ผ่าน task-reviewer (spec ✅ + quality Approved, ไม่มี Critical/Important finding)
- Sophia sanity audit: **SAFE** — SQL parameterized ครบ, `_h.escape` ครบ, `back` whitelist 2 ค่า (ไม่ open-redirect), customer-scoping ผ่าน token เสมอ, ไม่กระทบ `followed_jobs.starred_at`/LINE postback เดิม
- Regression เต็ม 5 ไฟล์ทดสอบ (`test_portal_notes/views/page/routes/stars.py`) — ทุกตัว `OK`

### Followup
- รอกัญจน์สั่ง merge `worktree-portal-interest-star` → main + push/deploy VPS (ไม่ได้ทำใน task นี้ตามแผน)
- ก่อนรอ merge ต้องทำ final whole-branch code review (most capable model) + `superpowers:finishing-a-development-branch` ต่อ

## งานที่ N+161: Bid Board win% ladder เต็ม N + รายชื่อคู่แข่งครบ คลิกไปหน้าบริษัท (2026-06-22)

### สถานะ: ✅ เสร็จ (code+test ครบ Task 1-7, Sophia SAFE) — รอกัญจน์ confirm deploy VPS

### บริบท
ออกแบบผ่าน `superpowers:brainstorming` (spec commit `c9d02e2`, `docs/superpowers/specs/2026-06-22-bidboard-intel-table-design.md`) + `superpowers:writing-plans` (plan `docs/superpowers/plans/2026-06-22-bidboard-intel-table.md`, 7 tasks) รันแบบ inline (ไม่ใช้ subagent — กัญจน์หลับแล้ว ไม่มีคนตอบคำถาม subagent). เปลี่ยน 2 อย่าง: (1) ตาราง win%-by-bidders จาก 3 จุด a/b/c เป็น ladder เต็ม N=1..max จริงจากข้อมูล (N=1 = 100% เสมอ) (2) โชว์ผู้รับเหมาทุกคนที่ป้อนการคำนวณ (ไม่ใช่ top 3) เป็นลิงก์คลิกไปหน้า `/portal/company`, คลิกแล้วเห็นผลงานในพื้นที่นั้นๆ ก่อนผลงานทั้งหมด

### Fix / ผล
- Task 1 (`scripts/bid_field.py`, commit `d1ce125`): `_center_stats` ladder เต็ม `ns=[1]+range(2,max+1)`, `_evaluate_winrate` hardcode N=1=100%, `field_and_winrate` คืน `grid` dict แทน text lines
- Task 2/3 (`scripts/cgd_intel.py`, commit `2ee9c95`): ลบ `SHOW_N=3` cap → `_scope_block` คืน `companies` list ครบทุกบริษัท (ไม่ใช่ text bullet); `_build_intel` ประกอบ `company_tables`(ต่อ scope)+`winrate_table`(grid+conf+basis) ใส่ใน return dict; เพิ่ม `_resolve_tin(conn,name)` หา tin จาก `bid_results` (normalized name match, graceful None)
- Task 4 (`scripts/portal_views.py`, commit `2033fa2`): `job_detail()` ส่งผ่าน `company_tables`/`winrate_table`; `render_job_page()` render ตาราง HTML ใหม่ 2 อัน (`_render_company_tables` คลิกไป `/portal/company` ถ้า resolve tin ได้/เทาถ้าไม่ได้, `_render_winrate_table` ladder เต็ม N=1..max)
- Task 5 (`scripts/portal_views.py`, commit `fa0d175`): `area_portfolio(conn,name,project_ids)` exact-match ผลงานบริษัทเฉพาะ project_ids ที่ส่งมา (ไม่ fuzzy geo — bid_results พิกัดบาง ~7/1084); `render_company_page()` เพิ่ม section "📍 ผลงานในพื้นที่นี้" ก่อน timeline รายปี
- Task 6 (`scripts/bms_api.py`, commit `ff4c9c4`): route `/portal/company` รับ `area_ids`/`area_label` query param ส่งต่อเข้า area_portfolio + render
- Task 7: regression 9 ไฟล์ test ที่เกี่ยวข้องทั้งหมด ALL PASS/OK ไม่มี traceback; Sophia ตรวจ SQL injection(parameterized ทั้ง `_resolve_tin`/`area_portfolio`), XSS(`area_label` escaped), None-safety, N=1=100% hardcode, ไม่มี silent error → **verdict: SAFE TO PROCEED**
- พบ side-effect: `Sebastian_LINE_Sender.py:_round2_warned_names` พึ่ง `cgd_intel.SHOW_N` จริง (top-3 LINE disclaimer) — แก้เป็น hardcode `3` ตรง (ไม่เกี่ยวกับ web ladder ใหม่, LINE ยังจำกัดความยาวเดิม)
- พบ plan inconsistency 3 จุดตอนเขียน test จริง (ไม่อยู่ใน plan ตั้งแต่แรก แก้ระหว่างทำ): (1) plan's test assert "1ราย"/"4ราย" ไม่มีเว้นวรรค ขัดกับ render code ที่ใส่เว้นวรรค "N ราย" (ตรงกับ convention เดิมในไฟล์) → ใช้แบบเว้นวรรค (2) `test_area_portfolio_exact_match_only` fixture R3 winner จริงๆตรงกับหจก.A (ไม่ตรงกับ comment "winner≠หจก.A") → แก้ id list เป็น `["R1","R2","R4"]` ให้ R4(คนละบริษัท)สาธิต filter จริง (3) "ปี 2568" ขึ้นซ้ำในกราฟแถบ "ยื่น–ชนะ รายปี" ก่อน timeline อยู่แล้ว → assert position ด้วย marker `class="yhead"` เฉพาะ timeline แทน
- Regression รอบแรก (Task 2/3): 19 ไฟล์ test ที่ import cgd_intel/bid_field — พบ 4 ไฟล์ test เก่าที่ assert bullet text "หจก.X" in lines ต้องแก้เป็น assert บน `company_tables` structured data: `test_cgd_intel.py`, `test_road_subtype.py`(2 จุด), `test_water_subtype.py`(2 จุด)

### Followup
- ✅ Deploy VPS เสร็จ (2026-06-22): push origin/main (`a9d3f77`→`00fd79b`, 7 commits) → VPS `git pull` fast-forward สะอาด → `systemctl restart bms-api` → `/health` OK (`{"ok":true,"db":true}`)

## งานที่ N+162: bms-backfill-bidders timer รายวัน — ปิดช่องว่าง "งานไม่มีคนติดตาม = ไม่เก็บ bid_results" (2026-06-22)

### สถานะ: ✅ เสร็จ

### บริบท
หลัง backfill 12K (N+156) เสร็จ คุณกัญจน์ถามว่าระบบเก็บผู้ยื่นซอง+ผู้ชนะ+ราคาของ **ทุกงาน** จริงไหม (ไม่ใช่แค่งานติดตาม) — ตรวจแล้วพบช่องว่างจริง: `bms-winner-poller` (timer เดิม ทุก 6 ชม.) poll เฉพาะงานที่มีลูกค้ากด follow เท่านั้น งานที่ไม่มีคนติดตามจะไม่ถูกเก็บ `bid_results` อัตโนมัติเลย ต้องรัน `backfill_bidders.py` มือเป็นระยะ

### สิ่งที่ทำ
- คุณกัญจน์ถามเรื่อง schedule (สัปดาห์ละครั้ง ใช้เวลา 12 ชม. มั้ย) → อธิบาย: 12 ชม.รอบแรกคือ catch-up ของเก่าทั้งหมด (12 ปี/12,093 งาน) ครั้งเดียว ไม่ใช่ค่าใช้จ่ายที่ต้องเสียซ้ำทุกรอบ — `backfill_bidders.py` มี `NOT IN bid_results` กันดึงซ้ำในตัวอยู่แล้ว รอบถัดไปจะดึงแค่งานปิดใหม่ (~19 งาน/สัปดาห์ ≈ 30 วินาที)
- คุณกัญจน์เลือก **รายวัน** (ถี่กว่าที่เสนอ, ข้อมูลสดกว่า + batch เล็กกว่า = WAF risk ต่ำกว่าด้วย)
- 🐛 พบ bug ก่อน deploy: `backfill_bidders.py --fy` default hardcode `"2567,2568,2569"` — timer รันถาวรจะค้างปีงบเก่าเงียบๆหลัง 1 ต.ค.2569 (FY2570 เริ่ม) → เขียน `current_fy(today=None)` คำนวณปีงบไทย (ต.ค.-ก.ย.) จากวันนี้จริง, default เปลี่ยนเป็น `f"{fy_now-1},{fy_now}"` (ไม่ตายตัว) + test `test_current_fy()` ครอบ 4 case (ก่อน/หลัง 1 ต.ค.)
- dry-run บน VPS จริงด้วย default ใหม่: เหลือแค่ **5 candidates** (ของเก่าจาก backfill 12K ถูกตัดหมดแล้ว) → รันจริง `stored=4 empty=1 error=0` เสร็จใน <10s ตรงบน VPS เลย (ไม่ต้องผ่านเน็ตบ้านเหมือนรอบ bulk — volume เล็กพอ ไม่โดน WAF)
- เขียน `deploy/systemd/bms-backfill-bidders.{service,timer}` (ตาม pattern `bms-winner-poller` เดิม) — รายวัน 02:00 UTC (09:00 ไทย, หลัง full-bkg sweep 01:30) → scp ขึ้น VPS เป็น root → `daemon-reload` + `enable --now` → ทดสอบ trigger มือ 1 ครั้ง `Result=success`

### Fix / ผล
- `bid_results` coverage ไปข้างหน้า: ครอบทุกงานปิดใหม่ใน 2 จังหวัด ไม่จำกัดแค่งานติดตามอีกต่อไป
- commit: `a5f4129` (fix current_fy) + `b053ac7` (deploy timer files), push origin/main แล้ว
- timer ถัดไป: 2026-06-23 02:00 UTC

### Followup
- ไม่มี — เสร็จสมบูรณ์ รอดูผลรันอัตโนมัติรอบแรกพรุ่งนี้

## งานที่ N+163: LINE notification format — หัวข้อขึ้นก่อนชื่องาน + TOR review เลิกเป็นการ์ด (2026-06-22)

### สถานะ: ✅ เสร็จ

### บริบท
คุณกัญจน์แจ้ง 2 จุดในแจ้งเตือน LINE: (1) "🔔 พบงานเปิดกำหนดวันยื่นซองใหม่" ควรขึ้นเป็นหัวข้อก่อน แล้วค่อยชื่องาน (ปัจจุบันสลับกัน) (2) งานสเตจ "เปิดฟังคำประชาพิจารณ์" (TOR review, ก่อนกำหนดยื่นซอง) ยังเป็นการ์ด flex อยู่ อยากให้เป็น plain-text แบบเดียวกับ D0

### Root cause
- `Sebastian_LINE_Sender.py` `main()`: ข้อความ D0 ต่อกันแบบ `full_name + "\n" + text` (ชื่องานนำหน้า header เสมอ — `text` มาจาก `format_notification()` ซึ่งบรรทัดแรกคือ header)
- TOR review (`source_stage="province_tor_review"`) ถูก enqueue ด้วย `announce_type="B0"` (ไม่ใช่ "D0") → dispatch condition เดิมเช็คแค่ `announce_type=="D0"` → ตกไปสาย `else` (flex card + ปุ่ม feedback) ทุกครั้ง

### Fix
- เพิ่ม `_plain_text_body(text, full_name)` — pure function แยก header บรรทัดแรกออกมา แล้วแทรกชื่องานเป็นบรรทัดที่ 2 (header → ชื่องาน → ส่วนที่เหลือ)
- เพิ่ม `_is_plain_text_stage(item)` — `announce_type=="D0"` **หรือ** `source_stage.startswith("province_tor_review")` → ใช้ plain text เหมือนกัน (ไม่ใช่การ์ด)
- ทั้งคู่ extract ออกมาเป็น pure function แยกได้ (เดิม logic ฝังอยู่ใน `main()` ไม่มี test คลุม) + เขียน test ใหม่ 2 ตัวใน `test_d0_quickreply.py`
- commit `d60f32c`, push origin/main แล้ว — **ยังไม่ deploy VPS** (รอ confirm)

### Followup
- รอกัญจน์ confirm deploy VPS (`bms_api.py`/`Sebastian_LINE_Sender.py` ไม่ต้อง restart service อะไร เพราะ LINE sender รันผ่าน timer แยก ไม่ใช่ long-running service — แค่ git pull พอ)

## งานที่ N+164: เพิ่มสกลนครเป็นจังหวัดที่ 3 — เต็มรูปแบบ (2026-06-22, 🚧 ค้าง CGD quota)

### สถานะ: 🚧 ค้าง — โดน CGD Open Data quota วันนี้ รอวันถัดไป resume ต่อ

### บริบท
คุณกัญจน์ขอเพิ่มสกลนครเป็นจังหวัดที่ 3 แบบเต็มรูปแบบ (เหมือนนครพนม+บึงกาฬ) หลังเสร็จงาน N+162 — ตรวจพบว่าสกลนครยังไม่มีข้อมูลพื้นฐานอะไรเลยในระบบ (ไม่ใช่แค่ขาด `bid_results`): `cgd_winners` (VPS) = 0 แถว, `winner_history.db` (local, ต้นทางจาก CGD Open Data) = 0 แถว เพราะ `_winner_history_build.py`/`cgd_sync_to_vps.py` hardcode `PROVS`/`TARGET` ไว้แค่ 2 จังหวัดเดิมตั้งแต่ต้น

### สิ่งที่ทำ
- แก้ `_winner_history_build.py` PROVS += สกลนคร, `cgd_sync_to_vps.py` TARGET += สกลนคร (commit `e12b575`)
- รัน `_winner_history_build.py` (CGD CKAN bulk fetch, **คนละขั้นกับ bid_results backfill** — bulk 1,000 แถว/call ไม่ใช่ทีละงาน จึงเร็วกว่ามาก ไม่ใช่ 7-8 ชม.) — โดน "API None (quota/error)" 3 รอบติด (calls=224, 265, ~1) รวม **67/96 combos** (ปีงบ 2568-2563 ครบ, 2562 ได้ 3/9, 2561-2558 ยังไม่ทำ) → สรุป: โดน rate-limit/quota จริง ไม่ใช่ transient — หยุด retry รอวันถัดไป
- sync ของที่มีตอนนี้ (819,392 แถว 3 จังหวัด) เข้า VPS `cgd_winners` แล้วสำเร็จ (`push()` idempotent, merge ซ้ำได้ปลอดภัย) — สกลนคร 202,035 แถว (FY2568-2565 ครบ, 2565 partial) ขึ้น VPS แล้ว

### Update 2026-06-22 (ต่อ): quota reset เร็วกว่าคาด — winner_history ครบ + เจอ bug ใหม่
- quota CGD reset ภายในชั่วโมงเดียว (ไม่ต้องรอข้ามวันจริง) — retry ต่อจนครบ **96/96 combos** สกลนคร (รวมทุกปีงบ 2558-2568) — เจอ `sqlite3.OperationalError: database is locked` ทรานเซียนต์ 1 ครั้งระหว่าง retry (lock ค้างจาก process ก่อนหน้าปิดไม่ทันที) → retry อีกทีผ่านปกติ
- `cgd_sync_to_vps.py --push` รอบที่ 2 (ข้อมูลครบ 1,208,567 แถว 3 จังหวัด) สำเร็จ → VPS `cgd_winners` สกลนคร = **591,210 แถว ครบทุกปีงบ 2558-2568**
- 🐛 **พบ data anomaly ใหม่**: `cgd_winners.proc_type` ของสกลนคร **เฉพาะปีงบ 2568** เป็น label รวม `"วิธีการจัดหา ประกาศเชิญชวนทั่วไป คัดเลือก เฉพาะเจาะจง"` (ไม่แยกเป็น e-bidding/คัดเลือก/เฉพาะเจาะจง แบบปีอื่นๆ/จังหวัดอื่นๆ) → ไม่ match `COMPETITIVE_SET` เลย → `backfill_bidders.py --provinces สกลนคร --dry-run` (default fy ปัจจุบัน) ได้ **0 candidates** ทั้งที่มีงานจริง 59,143 รายการปีนั้น — เช็คนครพนม/บึงกาฬ ปีงบเดียวกันแล้ว **ไม่เจอปัญหานี้** (label แยกปกติ) → เป็น anomaly เฉพาะ resource file ของสกลนครปีงบ 2568 จาก CGD ไม่ใช่ schema เปลี่ยนทั้งระบบ
- scope ปีงบ 2558-2567 (10 ปี, label สะอาด) ของสกลนคร dry-run ได้ **10,751 candidates** — ขนาดใกล้เคียง backfill เดิม (12,093 งาน 2 จังหวัด) → เริ่ม residential fetch รอบใหม่ (`_backfill_home_fetch.py` ปรับให้รับ path arg แล้ว, commit `b4754cb`) ด้วยไฟล์แยก `data/_backfill_home/skn_backfill_cands.json`/`skn_backfill_results.json` — กำลังรัน background (คาด ~9-12 ชม. เหมือนรอบเดิม)

### Followup (ค้าง)
1. รอ residential fetch สกลนคร (2558-2567, 10,751 งาน) เสร็จ → import เข้า `bid_results` (ปรับ `_backfill_home_import.py` ให้รับ path arg เหมือนกัน หรือเขียนใหม่คล้ายเดิม)
2. **ตัดสินใจเรื่อง FY2568 proc_type anomaly ก่อน wire เข้า daily timer** — ตัวเลือก: (a) เพิ่ม literal label นี้เข้า `COMPETITIVE_SET` เฉพาะ query สกลนคร (b) รอ CGD แก้ที่ต้นทาง แล้ว re-sync (c) ใช้ fallback อื่น (เช่น  contains "ประกาศเชิญชวนทั่วไป") — ยังไม่ฟันธง รอตัดสินใจ
3. เพิ่มสกลนครเข้า default ของ `backfill_bidders.py --provinces` (เช็คก่อน deploy — อาจ hardcode 2 จังหวัดเดิมเหมือนที่เจอกับ `--fy`/TARGET) แล้ว deploy timer ใหม่ — **ทำได้เฉพาะหลังแก้ #2** ไม่งั้น timer จะมองไม่เห็นงานปีงบปัจจุบันของสกลนครเงียบๆ

## งานที่ N+165: แก้ /portal/company โหลดช้า — missing index + full-scan LIKE (2026-06-22)

### สถานะ: ✅ เสร็จ

### บริบท
คุณกัญจน์รายงานหน้า Bid Board (`/portal/company`) โหลดช้ามาก โดยเฉพาะบริษัทที่มีผลงาน 100+ งาน — ตรวจ root cause พบว่า**งานของผมเองในวันนี้ (sync สกลนคร เข้า `cgd_winners`) ทำให้ปัญหาเดิมที่ซ่อนอยู่เด่นชัดขึ้น** เพราะ `cgd_winners` โตจาก 617K → 1.2M แถวทันที

### Root cause (ยืนยันด้วย benchmark จริงบน VPS ก่อนแก้)
1. `company_profile()` query `WHERE bidder_tin=?` บน `bid_results` — ไม่มี index ใช้ได้เลย (PK เดิม `(project_id,bidder_tin)` ช่วยไม่ได้เพราะ tin ไม่ใช่คอลัมน์แรก) → `EXPLAIN QUERY PLAN` ยืนยัน `SCAN bid_results`
2. `won_portfolio()` query `WHERE winner LIKE '%key%'` บน `cgd_winners` — LIKE มี wildcard นำหน้า ใช้ index ไม่ได้โดยธรรมชาติ → **วัดจริง 3,015ms, match 213,812 แถว** ก่อนกรองด้วย Python normalized-name ซ้ำอีกชั้น — เป็นตัวการหลักของความช้า

### Fix
- `_migrate_v132`: `CREATE INDEX idx_bid_results_tin ON bid_results(bidder_tin)`
- `_migrate_v133`: เพิ่ม column `cgd_winners.normalized_winner` (precompute ด้วย `portal_views._norm_name` เดิม) + index + backfill แถวเก่า (resumable, เช็ค `IS NULL` กันรันซ้ำหนักทุก startup)
- `cgd_sync_to_vps.merge_winners()` ต้องคำนวณ `normalized_winner` ทุกครั้งที่ merge ด้วย — เพราะ `INSERT OR REPLACE` เขียนทั้งแถว ถ้าไม่ใส่จะเคลียร์ค่ากลับเป็น NULL ทุกรอบ sync ครั้งถัดไป (เกือบเป็น bug ซ้อน bug)
- `won_portfolio()` เปลี่ยนจาก LIKE-prefilter+Python-filter เป็น indexed exact match บน `normalized_winner` ตรงๆ

### ผล (วัดจริงบน VPS หลัง deploy)
- migration ครั้งแรก (backfill 1.2M แถว) ใช้เวลา **2m46s** — one-time cost, รันแล้วครั้งเดียวพอ
- `won_portfolio`: **3,015ms → 10ms (เร็วขึ้น ~300x)** — ยืนยันด้วย `EXPLAIN QUERY PLAN` เปลี่ยนจาก scan เป็น `SEARCH ... USING INDEX idx_cgd_winners_normwin`
- `company_profile`: query plan เปลี่ยนเป็น `SEARCH ... USING INDEX idx_bid_results_tin` ถูกต้อง — เลขเวลาที่วัดได้ (149ms) สูงกว่า baseline เดิม (33ms) เพราะช่วงนั้น residential fetch สกลนครกำลังเขียน `bid_results` พร้อมกันอยู่ (lock contention ชั่วคราว) — โครงสร้าง query plan ถูกแล้ว ปัญหาจริง (full scan) หายไป, จะ scale ดีขึ้นเรื่อยๆเมื่อตารางโตต่อ
- backup DB ก่อน migrate (`bms_customers_pre_perf_index_20260622_074249.db`, 929MB) + restart `bms-api` แล้ว `/health` OK
- commit `c4fa4ef`, push + deploy VPS ครบ

### Followup
- ไม่มี — ปิดงานสมบูรณ์ (เป็น side-effect ที่ดีจาก N+164 ที่ทำให้เจอ bug ที่ซ่อนมานาน)

## งานที่ N+166: Bid Board readability pass — พื้นหลังนวล + Thai line-height + ตาราง win% เป็นการ์ดมือถือ + แก้ a11y emoji (2026-06-22)

### สถานะ: ✅ เสร็จ

### บริบท
คุณกัญจน์ขอให้ไปค้นคว้าวิธีทำเว็บให้น่าอ่าน/อ่านง่าย (dispatch fork agent ค้นคว้า NN/g, WCAG, Cadson Demak/Microsoft Thai typography, 2025 mobile-table UX research) แล้วขอให้ลงมือแก้ตาม checklist ทันที + เพิ่มโจทย์ "พื้นหลังสีอ่อนๆสวยๆ ไม่จืดชืดเหมือนสีขาวล้วน" + ย้ำ "ห้ามเสียข้อมูล"

### สิ่งที่ทำ (ตรงตาม checklist ที่ค้นคว้ามา)
1. **พื้นหลัง**: `body{background:#f5f6f8}` → `linear-gradient(160deg,#f3f7fc 0%,#fbf7f0 100%)` (ฟ้าอ่อน→ครีมอ่อน) — เช็ค luminance สูงพอ ไม่กระทบ contrast ตัวอักษรเทาเดิม (เลย darken `.meta` จาก #777→#666 เพิ่ม safety margin ด้วย เพราะ #777 บนขาวล้วนเดิมก็ contrast ~4.48:1 ชนเส้น AA 4.5:1 อยู่แล้ว)
2. **line-height ไทย**: เพิ่ม `line-height:1.8` ที่ body (ไทยมีวรรณยุกต์/สระบน-ล่าง ต้องการพื้นที่มากกว่าอังกฤษตามคำแนะนำ Cadson Demak/Microsoft) — แยก `.itbl{line-height:1.4}` ไม่ให้ตารางข้อมูลยืดยาวเกินจำเป็น
3. **ตาราง win%-ladder บนมือถือ**: เพิ่ม `class="itbl wr"` + `data-label` ทุก `<td>` ใน `_render_winrate_table()` + media query `max-width:480px` พลิกแต่ละแถวเป็นการ์ดแนวตั้ง label:value (เลิกพึ่ง scroll แนวนอนที่ research บอกว่าคนหาไม่เจอ) — **ไม่เสียข้อมูลแม้คอลัมน์เดียว** ยืนยันด้วย test ใหม่เช็ค data-label ครบทุก N
4. **ตัวเลขเด่น**: เพิ่ม `.feature` class (ใหญ่+หนา+พื้นสีฟ้าอ่อน) ให้บรรทัด "คาดราคา" บนหน้างาน — ตัวเลขที่ตัดสินใจสำคัญสุดต้องเด่นสุด ตาม F-pattern eye-tracking research
5. **แก้ a11y**: `cgd_intel._conf_tag()` 2 จาก 3 branch คืน emoji เปล่าๆ (🟡/🟢 ไม่มีคำ) ขัด WCAG 1.4.1 (สีห้ามเป็นสัญญาณเดียว) → เพิ่มคำกำกับเป็น "🟡 ปานกลาง"/"🟢 มั่นใจ" — audit ทั่ว codebase แล้ว จุดอื่นที่ลูกค้าเห็น (head_to_head, winrate_table conf) มีคำกำกับอยู่แล้ว ไม่ต้องแก้
6. **ไม่แก้**: ไม่เพิ่ม custom Thai webfont (Sarabun ฯลฯ) — สถาปัตยกรรมไม่มี JS/รูปภาพเดิมดีอยู่แล้วสำหรับผู้ใช้เน็ตช้าในชนบท คงไว้ตามคำแนะนำ

### Verification
- generate ตัวอย่างหน้างานจริงด้วยข้อมูลสมมุติ ตรวจ HTML output ด้วยมือ (ไม่มี browser/screenshot tool ในเครื่องนี้) — markup ถูกต้อง ไม่มี tag ค้าง
- test ใหม่: `test_conf_tag_always_has_text()` (cgd_intel) + ขยาย `render_job_page_winrate_table_full_ladder` เช็ค `data-label`/`class="itbl wr"` ครบ
- regression sweep 10 ไฟล์ test ที่เกี่ยวข้อง ALL PASS
- commit `8de9cac`, push + deploy VPS (`git pull` fast-forward, restart `bms-api`, `/health` OK)

### Followup
- ไม่มี — เสร็จสมบูรณ์ตาม checklist ที่คุณกัญจน์ขอ

### Update 2026-06-22 (ต่อ): กัญจน์ feedback 2 รอบ — แก้ตาราง win% ต่อ
- **รอบ 1**: label/value ในตาราง (มือถือ) ห่างกันเกินไป — `justify-content:space-between` ดันค่าไปขอบขวาสุดของการ์ด → เปลี่ยนเป็น "ป้าย: ค่า" ชิดกัน (`gap:6px` ไม่มี space-between) (commit `051e1b1`)
- **รอบ 2**: กัญจน์ไม่ชอบ card-transform เลย — บอกว่าแยกเป็นหลายกล่องลอย (1 กล่อง/แถว) ไม่รู้สึกเป็นตารางเดียว ขอกลับเป็นตารางจริงกล่องเดียวมีเส้นกรอบ (grid) → **ถอด card-transform ทิ้งทั้งหมด** (ไม่มี `wr` class/`data-label`/media query แยกกล่องแล้ว), แก้ `.itbl` ให้มี border-right+border-bottom ทุก cell (ตัดขอบนอกสุดด้านขวา/ล่างออก กันซ้อนกับกรอบ `.tblwrap`), `.tblwrap` เป็นกล่องเดียวมีขอบ+มุมโค้งรอบนอก — กลายเป็นตารางสเปรดชีตจริงในกล่องเดียว ไม่ใช่การ์ดหลายกล่องอีกต่อไป (commit `98892fe`)
- L: card-transform เป็น pattern ที่ research แนะนำสำหรับตารางกว้างมาก แต่ตารางนี้มีแค่ ~6-8 คอลัมน์ — กัญจน์ (ผู้ใช้จริง) ชอบตารางจริงมากกว่า บทเรียน: research ทั่วไปไม่ได้ fit ทุก use case เสมอ ต้องเช็ค feedback ผู้ใช้จริงก่อนยึดติด pattern เดียว
- deploy VPS ทั้ง 2 รอบแล้ว `/health` OK

## งานที่ N+167: แก้ /portal/job โหลดช้า — composite index cgd_winners + index bid_results.normalized_name (2026-06-22)

### สถานะ: ✅ เสร็จ

### บริบท
คุณกัญจน์รายงานว่าเข้าหน้ารายละเอียดงาน (`/portal/job`) โหลดนานมาก — ตรวจแบบเดียวกับ N+165 (วัดจริงก่อนแก้)

### Root cause (วัดจริงบน VPS)
- `intel_context()` ของงานก่อสร้างถนนจริง 1 งาน ใช้เวลา **3,679ms**
- `cgd_intel._fetch()` filter `province=? AND fiscal_year IN(...) AND proc_type IN(...) AND project_name LIKE(...)` — index เดิม (`idx_cgdw_province`) กรองได้แค่ province (390,108 แถวสำหรับนครพนม) แล้ว scan ทุกแถวเช็คที่เหลือเอง = 601ms/call × `_build_intel()` เรียกหลายรอบ (ตำบล/อำเภอ/จังหวัด) ต่อหน้า
- `cgd_intel._resolve_tin()` (เรียกต่อบริษัทที่โผล่ในตาราง) ใช้ `bidder_name LIKE '%key%'` บน `bid_results` — full scan วัดจริง 173ms/call

### Fix
- `_migrate_v134`: composite index `cgd_winners(province, fiscal_year, proc_type)` — ยืนยันด้วย query ตรงว่า filter 3 คอลัมน์นี้ (ก่อน LIKE) เหลือแค่ 1,108 แถว จาก 390,108 (ลด 350x)
- `_migrate_v135`: เพิ่ม `bid_results.normalized_name` (precompute เหมือน N+165) + index, อัปเดต `record_bid_results()` ให้เขียนคอลัมน์นี้ทุกครั้ง (กัน INSERT OR REPLACE เคลียร์ค่าเป็น NULL ตอนงานเดิมถูกเขียนซ้ำ เช่น winner-poller), `_resolve_tin()` เปลี่ยนเป็น indexed exact match

### ผล (วัดจริงทีละขั้นบน VPS งานเดียวกัน)
- baseline: 3,679ms → หลังแก้ cgd_winners index: 691ms (5.3x) → หลังแก้ bid_results index: **407ms (รวม ~9x จาก baseline)**
- ยืนยัน query plan เปลี่ยนจาก `SCAN`/`SEARCH...USING INDEX idx_cgdw_province` เป็น `SEARCH...USING INDEX idx_cgdw_prov_fy_proc` ถูกต้อง
- backup DB ก่อน migrate ทั้ง 2 ครั้ง, migration เร็ว (index สร้าง 9.6s + 0.7s, ไม่มี backfill หนักเหมือน v133)
- commit `d711466` + `45b417b`, push + deploy VPS ครบ, regression sweep 12 ไฟล์ test ALL PASS

### Followup
- ไม่มี — 407ms ถือว่าเร็วพอสำหรับตอนนี้ ถ้ากัญจน์ยังรู้สึกช้าอยู่ค่อยมาดูจุดต่อไป (เช่น `_resolve_tin` ยังเรียกซ้ำต่อบริษัทแม้ cache ใน scope เดียวกันแล้ว)

## งานที่ N+168: Custom Win% Calculator — กรอกราคา+คู่แข่งเอง คำนวณโอกาสชนะให้ (2026-06-22)

### สถานะ: ✅ เสร็จ — กัญจน์อนุมัติให้ทำจนเสร็จเองแบบ autonomous (ไปนอนแล้ว)

### บริบท
คุณกัญจน์อยากให้ระบบทำนายราคามีโหมดเจาะจง: กรอกราคาที่ตัวเองอยากยื่นเอง + เลือก/พิมพ์คู่แข่งที่คาดว่าจะมา แล้วคำนวณโอกาสชนะให้ — ต่างจากตาราง win%-by-N-bidders เดิม (generic, ไม่เจาะจงบริษัท) ออกแบบผ่าน `superpowers:brainstorming` (spec `docs/superpowers/specs/2026-06-22-custom-winrate-calculator-design.md`) + `superpowers:writing-plans` (plan 6 task) รัน inline (กัญจน์ไปนอน ไม่มีคนตอบ subagent)

### สิ่งที่ทำ (5 commit, `60fca30`→`0da2b28`)
1. **`cgd_intel.py`**: `_build_intel()` เพิ่ม `median` ต่อ company_tables block + เพิ่ม `scope_rows` ใน return (rows เดียวกับที่ทำ company_tables) — ฟังก์ชันใหม่ `_cdf_3pt()` (piecewise-linear CDF จาก p25/median/p75, clamp 5-95%), `_resolve_competitor_name()` (หาชื่อ normalized match ใน rows), `calc_custom_winrate()` (core: แปลงราคา→%ลด, หาสถิติคู่แข่งหรือ fallback ค่าเฉลี่ยพื้นที่, รวมหลายคู่แข่งด้วย independence)
2. **`portal_views.py`**: `job_detail(conn, pid, calc_params=None)` เพิ่ม param ใหม่ (optional, ไม่กระทบ caller เดิม) + `_render_custom_calc_form()` (checkbox จาก company_tables dedupe + textarea พิมพ์ชื่อเพิ่ม + ราคา + ผลลัพธ์พร้อม disclaimer)
3. **`bms_api.py`**: `GET /portal/job` รับ query param ใหม่ (`calc_my_price`/`calc_competitors`/`calc_extra`) + route ใหม่ `POST /portal/job/calc` (form→303 redirect กลับ GET พร้อม params, ใช้ `\x1f` คั่นชื่อบริษัทกัน comma ชนชื่อจริง) — ไม่มี schema/DB เปลี่ยนเลย
4. **🐛 พบ + แก้ math bug ตั้งแต่ตอนเขียนแผน (ก่อนโค้ดจริง)**: spec draft แรกเขียนทิศทาง `win_pct_against` สลับกัน (label บอกว่าเป็นโอกาสเราชนะ แต่สูตรจริงคือโอกาสคู่แข่งชนะ) → แก้ spec (`151626d`) ก่อนเขียนโค้ด, ยืนยันด้วยมือ: `win_pct_against = (1-CDF)*100` = โอกาสคู่แข่งชนะเรา (เขาลดลึกกว่า), `overall_win_pct = ∏CDF_i` = โอกาสเราชนะทุกคน — Sophia ตรวจโค้ดจริงซ้ำอีกชั้น ยืนยันตรงทิศ
5. **🐛 พบ arithmetic error ในแผนเอง**: test fixture คาด median=11.0 จาก `_pct([9,10,11,12],50)` — คำนวณจริงด้วย python ก่อนเขียนแผนได้ 10.5 (ไม่ใช่ 11.0) → แก้ assertion ในแผนก่อนรัน

### Verification
- TDD ครบทุก task (เขียน test fail ก่อน → implement → pass) — เพิ่ม test 5 ฟังก์ชันใน `test_cgd_intel.py` (basic/multi-competitor/fallback/dedupe/invalid) + 1 ฟังก์ชันใน `test_portal_views.py` (form+result render)
- regression sweep 7 ไฟล์ test ที่เกี่ยวข้อง ALL PASS ทุกรอบ (หลังทุก task)
- Sophia ตรวจทิศทางสูตร + SQL injection + None-safety + backward-compat + XSS (เสริม ไม่ได้ขอ) → **verdict: SAFE TO PROCEED**
- deploy VPS: ไม่มี schema change เลย → แค่ `git pull` + restart `bms-api`, ไม่ต้อง backup DB พิเศษ

### Followup
- ไม่มี — ฟีเจอร์ใช้งานได้เต็มรูปแบบ ดูผลตอนกัญจน์ตื่นมาทดสอบจริงบนมือถือ

## Checkpoint 2026-06-22 17:30+ — ปิดเครื่อง (กัญจน์เดินทาง)

**สถานะระบบ ณ จุดนี้:**
- ทุกงานวันนี้ (N+162 ถึง N+168) commit + push ขึ้น `origin/main` ครบแล้ว, HEAD = `7583c00`, deploy VPS ล่าสุดแล้วทุกตัว, `bms-api` `/health` OK
- ไม่มี uncommitted change ของงานที่ทำวันนี้ (ไฟล์ที่ยังค้าง modified/untracked ใน git status เป็นของเก่าจากก่อนเริ่ม session ไม่เกี่ยวกับงานวันนี้ ไม่ได้แตะ)

**backfill สกลนคร (bid_results, ขั้นที่เหลือของ N+164) — หยุดเมื่อปิดเครื่อง:**
- checkpoint ล่าสุด: **2,165 / 10,751 งาน** (~20%) บันทึกลง `data/_backfill_home/skn_backfill_results.json` แล้ว (resumable, ไม่เสีย progress)
- รันบนเครื่องนี้ (เน็ตบ้าน) เท่านั้น — ปิดเครื่อง/เปลี่ยนเครือข่ายแล้วหยุดทำงานทันที ไม่มีทางรันต่อระหว่างเดินทางได้ (eGP บล็อกเน็ตที่ไม่ใช่ residential)
- **Resume ตอนกลับมา:** `cd scripts && python _backfill_home_fetch.py ../data/_backfill_home/skn_backfill_cands.json ../data/_backfill_home/skn_backfill_results.json` (path arg แบบใหม่จาก commit `b4754cb`) — จะข้ามงานที่ทำไปแล้วอัตโนมัติ
- หลัง fetch ครบ 10,751: ต้อง import เข้า VPS `bid_results` ต่อ (ขั้นที่ยังไม่ทำ) ตามแผนเดิมใน N+164's followup

**ของอื่นที่ค้างจากวันนี้ (ไม่เร่ง):**
- N+164: ตัดสินใจเรื่อง FY2568 proc_type anomaly ของสกลนคร (label รวมไม่แยกประเภท) ก่อน wire เข้า daily timer — ยังไม่ฟันธง
- N+167 followup: ถ้า /portal/job ยังรู้สึกช้าอยู่ (ปัจจุบัน ~407ms) มีจุดต่อไปคือ `_resolve_tin` เรียกซ้ำต่อบริษัท

ไม่มีอะไรเร่งด่วนต้องทำต่อทันที — ปิดเครื่องได้เลยครับ

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

### สถานะ: 🚧 ส่วน 1 (matching) เสร็จ+commit local **ยังไม่ push/deploy** · ส่วน 2 (digest) ยังไม่เริ่ม

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
