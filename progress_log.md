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

## งานที่ N+156: Backfill บ้าน 12K (residential home-fetch) — เริ่ม (2026-06-20)

### สถานะ: ⏳ กำลังรัน background (เครื่องบ้าน residential)

### บริบท (จาก debug session "ทำไม bid_results น้อย")
- bid_results = เฉพาะงานแข่งประมูล (e-bidding) ที่ดึง bidder ครบ — มีแค่ 1,075/13,170 (8%) ของ 2 จังหวัดบ้าน
- เพราะ backfill รันเฉพาะปีล่าสุด + เป็น fetch ทีละงาน rate-limit · eGP ยังเก็บงานเก่าครบ (ดึง 2563 ได้ 12 ราย)
- กลยุทธ์: ดึงจากเน็ตบ้าน (residential) เลี่ยง WAF VPS (`_backfill_home_fetch.py`, ADR-003)

### สิ่งที่ทำ
- VPS `select_candidates(นครพนม+บึงกาฬ, fy 2558-2569)` → **12,093 candidates** (seen 1,015 excluded) → scp local
- รัน `_backfill_home_fetch.py` background (เครื่องบ้าน): 27 done, 12,066 todo · ~9 ชม · resumable (results.json)
- เสร็จ → scp results → VPS import (record_bid_results) → bid_results ครบทั้งบ้าน

### Followup
- เมื่อ fetch เสร็จ: scp backfill_results.json → VPS → import → verify count เพิ่ม
- profile/head-to-head ของทุก customer รวยขึ้น (ของกัญจน์ 28 งานแข่งเก่าจะเข้าครบ)

## งานที่ N+157: Portal company — ผลงานที่ชนะทุกวิธีจัดซื้อ (proc_type) + filter (2026-06-20)

### สถานะ: ✅ code+test เสร็จ · ⏸ รอ deploy + verify VPS

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

### Followup (ค้าง)
- **deploy:** scp `bms_api.py`+`portal_views.py` → VPS → restart bms-api
- **⚠️ verify VPS:** (1) `cgd_winners` มี data ไหม (local 0 rows — ต้อง push จากเครื่องบ้าน `cgd_sync_to_vps.py --push`?) (2) eGP `bid_results.bidder_name` ↔ CGD `winner` match rate จริง (normalize bridge หจก./ห้างฯ แล้ว แต่ดูสะกดอื่น)
- **🐛 root-cause (defer):** ซ่อม CGD ingestion column-misalignment → winner_tin ถูก → re-sync → กลับไป join ด้วย tin (key ที่ถูก)
