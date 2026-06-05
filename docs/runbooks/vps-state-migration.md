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
(ว่าง — ยังไม่มี rollback)
