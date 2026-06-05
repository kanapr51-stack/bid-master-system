# Runbook — VPS State Migration + Deploy-Sync (execution log)

แผน: `docs/superpowers/plans/2026-06-05-vps-state-migration-deploy-sync.md` (v2.1)
Operator: Claude (+ กัญจน์) · Reviewer: ChatGPT (async)

## Execution Discipline (บังคับ)
- Rule #0: assumption ผิด → ABORT + restore + วิเคราะห์ใหม่ (ห้ามแก้สด)
- Rule #1: Exit Criteria ต้องผ่าน 100% · Rule #2: Abort > Improvise
- Rule #3: Operator 1 / Reviewer 1 · Rule #4: timestamp ทุก milestone (ด้านล่าง)
- Window Phase 2: target 15 นาที / hard-stop 30 นาที · Group B = ABORT TRIGGER

---

## Milestone Log (timestamp)

### PHASE 0 — Freeze + Backup + Audit (NON-DISRUPTIVE, services ยังรัน)
> ปรับจากแผน: Phase 0-1 ทำก่อน window → ไม่ stop production ตอนนี้ (ย้าย stop ไปต้น Phase 2). Phase 0 backup = baseline สด; consistent backup จริงทำตอน Phase 2 window.

- **2026-06-05 ~13:59 UTC** — เริ่ม Phase 0 (services running)
- forensic snapshot: `/opt/bms/backups/migration_20260605_135936/forensic.txt` (HEAD/status/timers/services/sha256) + local `backups/vps_migration_20260605_135936/`
- backup: app.tgz (11M) + data.tgz (559K) + env.bak + 32 systemd units → VPS **และ** local ✓

#### Hidden-writer audit (ChatGPT blind spot #7)
- `lsof +D /opt/bms/app/data` = **ว่าง** (ไม่มี process เปิดค้าง) ✓
- `crontab -l` = **none** · `/etc/cron* refs opt/bms` = **none** → **ไม่มี hidden cron writer** ✓ (ข้อกังวลใหญ่สุดของ ChatGPT = clear)
- scripts ใช้ `parent.parent/data`: เยอะ (~20+) แต่ส่วนใหญ่เป็น probe/builder/one-off (cgd_*, probe_*, build_*, debug_*) — ไม่ใช่ active timer

#### ⚠️ FINDING: timer list ใหญ่กว่าที่แผนเขียน (ต้องอัปเดต stop-list Phase 2)
timers/services ที่มีจริงบน VPS (จาก forensic):
```
bms-api.service, bms-tunnel.service (long-running)
bms-enrichment-worker.timer, bms-rss-notifier.timer, bms-rss-scraper.timer ⬅️ ใหม่ (active writer rss_queue/seen!)
bms-line-sender.timer, bms-deadman.timer, bms-canary.timer, bms-shadow-audit.timer
bms-daily-digest.timer, bms-daily-user-summary.timer
bms-province-discovery.timer, bms-province-discovery-full-bkg.timer,
bms-province-discovery-full-nkp.timer, bms-province-discovery-full.timer ⬅️ variants
bms-crossprobe.timer ⬅️ ใหม่
bms-backup.timer
```
→ **Phase 2 stop-list ต้องครอบ rss-scraper + crossprobe + discovery-full variants ทั้งหมด** (ไม่งั้นมี writer แอบเขียน state กลาง window)

**EXIT CRITERIA Phase 0:** backup VPS+local ✓ · lsof=none ✓ · cron clean ✓ · hidden writers จด ✓ · (stop = deferred to Phase 2)

---

### PHASE 1 — Wire state routing (repo-only) + dry-run reconcile ✅ เสร็จ
- **2026-06-05** — commits: bms_paths heal (Task 1.0), regression test + wire 8 scripts (1.2-1.5, `3bbd842`), service-entry heal+log_paths (1.6). push origin → `236dcc7`
- tests: `test_runtime_paths.py` PASS (8 scripts) · `test_bms_paths_heal.py` PASS · py_compile OK ทุกไฟล์
- decision: CATALOG/TARGET (egp_deptid_catalog, target_deptids) = ASSET คง DATA_DIR (committed seed, auto-rediscover) — ไม่ route runtime

#### Task 1.7 Reconcile dry-run (read-only) — 🎯 ZERO Group B
ตรวจ VPS working-tree vs origin/main (blob-existence + CR-normalized + find-object ใน history):
- **Group A (take origin ปลอดภัย):** Province_Discovery, RSS_Scraper, bms_api, discovery_catchup, harvest_and_push, matching_preferences (known blob) + Customer_DB, Daily_Digest, LINE_Sender, job_matcher (CRLF-only) + Enrichment_Worker, health_deadman (VPS = committed version เก่า แค่ตามหลัง, normalized blob พบใน history c68c9dd/25ebe61)
- ไฟล์อื่นที่ origin มี VPS ไม่มี = new files → reset สร้างให้ (Group A trivial)
- **Group B = 0** ✅ → assumption "VPS = scp จาก origin แค่ตามหลัง ไม่มี orphan hotfix" **CONFIRMED** → `git reset --hard origin/main` Phase 2 ปลอดภัย
- หมายเหตุ: line-ending Windows CRLF→VPS เป็นเรื่องปกติ (origin เก็บ LF) ไม่ใช่ logic diff

**EXIT CRITERIA Phase 1:** test PASS ✅ · inventory+audit cross-check ✅ · entry heal+log_paths ✅ · origin มี Phase 1 (236dcc7) ✅ · **dry-run = A/C ล้วน ไม่มี B ✅**

→ **GATE: Phase 2 (window) = CONDITIONAL GO ผ่านแล้ว** (รอ กัญจน์ นัด window + confirm)

#### Inventory: runtime-state files + accessors (Task 1.1)
| state file | type | active writers/readers |
|---|---|---|
| rss_queue.json | RUNTIME | W: RSS_Scraper · R: RSS_Notifier, queue_health, dashboard_extractor, refresh_active_jobs |
| rss_seen_ids.json | RUNTIME | W: RSS_Scraper · R: pipeline_funnel |
| api_ingestion_state.json | RUNTIME | W: Enrichment_Worker · R: queue_health |
| resolve_heartbeat.json | RUNTIME | W: Enrichment_Worker · R: health_deadman |
| resolve_plane_state.json | RUNTIME | W/R: Enrichment_Worker |
| rss_notifier_epoch.txt | RUNTIME (Tier3) | W/R: RSS_Notifier (cp -n, BOOTSTRAP_REQUIRED) |
| dept_failure_state.json, seen_ids.json | RUNTIME | RSS_Scraper |
| egp_deptid_catalog.json, target_deptids.json, egp_w0_catalog.json | ASSET? | RSS_Scraper เขียน → ตรวจ write_text (ดู Task 1.4) |

---

## Rollback log

### 2026-06-05 22:34 — Phase 2 ABORT #1 (sudo blocker, clean)
- window เปิด 22:23 → Task 2.0 gate ผ่าน (backup OK, audit ยืนยัน timer list) → **stop services ล้มเหลว: `sudo systemctl stop` ต้อง password (ssh non-interactive)**
- `sudo -n -l` = password required → **bms user ไม่มี NOPASSWD sudo เลย** → Operator (Claude ผ่าน ssh key) หยุด/สตาร์ท service เองไม่ได้
- **ABORT (Rule #2: ไม่หา/เดา sudo password)**. ยืนยันระบบ untouched: timers+api+tunnel active, HEAD=f5311f7, state ยังอยู่ app/data → **ไม่ต้อง rollback**
- ⚠️ side-finding: Phase 0 `sudo lsof +D app/data` น่าจะ no-op (sudo เงียบ) → "lsof clean" **ยังไม่ verify จริง** (crontab non-sudo valid; cron-grep sudo unverified). ต้องทำ lsof ใหม่ตอนมี sudo
- BLOCKER: ต้องแก้ sudo access ก่อนรัน Phase 2 ใหม่ (option A: NOPASSWD scoped / option B: กัญจน์รัน sudo เอง / option C: sudo script)

### 2026-06-05 23:21-23:36 — Phase 2 SUCCESS ✅ (window 15 นาที, ตรง target)
แก้ sudo: กัญจน์ตั้ง `passwd bms` + `/etc/sudoers.d/bms-operator` (`bms NOPASSWD: /usr/bin/systemctl, /usr/bin/lsof`) → verified `sudo -n` ทำงาน

**ลำดับจริง (มี deviation ที่จัดการตาม discipline):**
1. 23:21 redo lsof audit (sudo จริง) = ว่าง ✓ · stop 14 timers+api+tunnel (23:22, NONE_RUNNING)
2. fresh backup (migration_window_20260605_162250) + copy 8 state files app/data→/opt/bms/data · **checksum 8/8 OK**
3. validate: ⚠️ `ingestion_run_history.json` BOM → **false-positive** (validator ใช้ utf-8 แทน utf-8-sig; ไฟล์เดิมมี BOM, parse utf-8-sig ได้, checksum ตรง = ไม่ torn) → ไม่ abort
4. **DEVIATION 1:** `git fetch`/`reset` ล้มเหลว = `.git/objects` + `refs/heads/main` + `deploy/*` **root-owned** (git ops เก่ารันด้วย root) → reset ค้างครึ่งทาง. **ไม่ improvise** → escalate กัญจน์รัน `sudo chown -R bms:bms /opt/bms/app`
5. หลัง chown: root-owned=0 → fetch ทำงาน (236dcc7→64794f6) → `git reset --hard origin/main` → **HEAD=64794f6=GitHub เป๊ะ (full sync, ไม่ใช่แค่ 236dcc7)**
6. vps_vs_origin.patch (75224 บรรทัด) เก็บก่อน reset · Group B re-confirm = 0
7. imports 9/9 OK (transitive deps) · start services 23:33 · **log_paths = RUNTIME_DIR=/opt/bms/data** · ไม่มี DUAL-READ HEAL (copy ครบ)
8. verify: app/data ไม่ถูกแตะหลัง cutover ✓ · write ไป /opt/bms/data ✓ · **ส่งซ้ำ=0** (4 sends = งานเดียว 21:00 ก่อน window, first-time) · 0 errors
9. **`git pull` = "Already up to date"** → deploy-debt end-goal พิสูจน์แล้ว

**Lessons:** (L) validator ต้อง utf-8-sig · (L) `.git` root-owned จาก sudo-git เก่า = blocker ซ่อน → chown เป็นส่วนของ migration · (L) Phase 0 lsof no-op เพราะ sudo เงียบ → ต้อง verify sudo ก่อน trust audit

**RESULT: #1 Deploy-Debt + #2 Data Split-Brain = RESOLVED.** เหลือ Phase 3 (48h watch, cutoff set) + Phase 4 (gitignore app/data state + ถอด heal) = non-disruptive follow-up

### 2026-06-06 ~00:00 — Phase 3 leak-watch จับ missed writer (Phase 1 inventory พลาด) → fix
- **leak จริง:** `app/data/api_ingestion_state.json` ถูกเขียนหลัง cutoff. ต้นเหตุ = **vps_canary** (เขียน api_ingestion_state ลง app/data ทุก 30น — docstring บอกจงใจ "worker อ่าน app/data") + **Sebastian_LINE_Sender** (อ่าน app/data = stale). worker อ่าน /opt/bms/data → **canary→worker WAF signal ขาด** = functional split-brain
- Phase 1 inventory โฟกัส enrichment/rss/health แต่พลาด canary+line-sender (เพราะ grep แรกไม่ครอบ DATA_DIR-variable + ไม่ได้ enumerate ทุก timer-service)
- **fix (commit 5dec644):** wire vps_canary + Sebastian_LINE_Sender + seed_self_notify → bms_paths.runtime_path. deploy via `git pull` (ไม่ scp!) + restart canary/line-sender + sync api_ingestion_state app/data→/opt/bms/data + reset cutoff
- **verify:** trigger canary → เขียน /opt/bms/data (16:56) ✓, app/data frozen (16:43) ✓, canary HEALTHY signal ทำงาน. leak_watch.sh = 0 leak
- **Phase 3 watch active:** cron `*/30 * * * * /opt/bms/data/leak_watch.sh` (48h) → log /opt/bms/data/logs/leak_watch.log
- L-008: inventory ต้อง enumerate **ทุก active timer-service** ไม่ใช่แค่ grep pattern (canary/line-sender หลุดเพราะ grep แรกแคบ). Phase 3 leak-watch = safety net จับของที่ inventory พลาด (ทำงานจริง!)
