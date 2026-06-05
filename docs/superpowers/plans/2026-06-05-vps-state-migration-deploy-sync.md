# VPS Runtime-State Migration + Git Deploy-Sync — Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v2 changelog (หลัง ChatGPT review รอบ 2 — fold 8 จุด):** (1) dual-read transition + loud log, (2) `vps_vs_origin.patch` ก่อน reset --hard, (3) stop bms-api **บังคับ**, (4) checksum verify หลัง copy, (5) hidden-writer audit (Phase 0), (6) lightweight startup validation (parse+type+not-empty, ไม่ทำ field schema), (7) note: write-time guard มีใน `runtime_path` แล้ว, (8) **Exit Criteria ต่อ phase**.

**Goal:** ทำให้ production VPS มี "source of truth ชัด" — แยก runtime state ออกจาก code dir แล้ว sync VPS code ให้ตรง GitHub (origin/main) อย่างปลอดภัย โดยไม่ทำให้ RSS dedup/state หาย (กันส่งงานซ้ำให้ลูกค้า)

**Architecture:** ปัญหา 2 อย่าง (Deploy-Debt + Data Split-Brain) เป็นเรื่องเดียวกัน เพราะ runtime JSON state (rss_queue, rss_seen_ids, api_ingestion_state, resolve_heartbeat ฯลฯ) ถูกเขียนใน `/opt/bms/app/data` ซึ่งเป็น **โฟลเดอร์โค้ดที่ git track** → git reset/pull จะลบ live state. แก้โดย route runtime-state ทุกตัวผ่าน `bms_paths.runtime_path()` (helper ที่ build ไว้แล้ว, fail-loud) → state ย้ายไป `BMS_DATA_DIR=/opt/bms/data` (นอก code dir) → แล้ว git sync ถึงปลอดภัย. **ลำดับสำคัญ: แก้ state-routing ก่อน, git sync ทีหลัง** (ตรงข้ามกับสัญชาตญาณ "sync code ก่อน").

**Tech Stack:** Python 3 (stdlib), SQLite, systemd timers, git, bash. helper: `scripts/bms_paths.py` (มีอยู่แล้ว — `runtime_path()` / `asset_path()` / `log_paths()`).

**Key facts (จาก audit 2026-06-05 N+88):**
- VPS git HEAD = `f5311f7` (06-01) · GitHub origin/main = `c077938`+ · VPS working-tree diff 178-1049 บรรทัด/ไฟล์ (11 scripts ถูก scp ทับ git HEAD ไม่เคยเลื่อน)
- `.env BMS_DATA_DIR=/opt/bms/data` ✓ · `bms_customers.db` อยู่ /opt/bms/data ถูกแล้ว (สดวันนี้) ✓
- **แต่** JSON state เขียนสดที่ `/opt/bms/app/data`: rss_queue, rss_seen_ids, api_ingestion_state, rss_run_state, resolve_heartbeat, rss_stage_rotation
- runtime-state scripts ใช้ `Path(__file__).parent.parent / "data"` (= app/data) ไม่ใช่ BMS_DATA_DIR
- `bms_paths.py` ยัง DORMANT (no caller) — แผนนี้คือการ "เปิดจราจรสะพาน"

---

## Invariant (ห้ามละเมิดทุก phase)
1. **repo `data/` = read-only assets เท่านั้น** (config/seed/lookup) · **BMS_DATA_DIR = runtime writes ทั้งหมด**
2. **"writer wins ไม่ใช่ newest-file wins"** — ตอน migrate state ห้าม overwrite ไฟล์ที่ใหม่กว่าด้วยไฟล์เก่า
3. timers ต้องหยุดก่อนแตะ state/git (กัน write ระหว่าง migrate → torn state)
4. ทุก phase มี rollback ที่กลับได้ใน < 5 นาที **และ Exit Criteria ชัด** (ห้ามขึ้น phase ถัดไปจนกว่า criteria ครบ)
5. **Definition of Done ของ migration ไม่ใช่ "ทำเสร็จ" แต่คือ "verify 48h ว่าไม่มี writer หลุดไป app/data"** (failure ประเภทนี้ surface ทีหลัง)
6. **fail-loud เสมอ**: `runtime_path()` มี guard อยู่แล้ว (raise ถ้า path escape ออกนอก RUNTIME_DIR) → เขียนเข้า app/data ผ่าน helper ไม่ได้. dual-read fallback (transition) ต้อง **log ดังๆ** ทุกครั้งที่ตกไป old (silent corruption > hard crash = ห้าม)

---

## 🚦 Execution Discipline (v2.1 — ChatGPT final review) — บังคับวันรันจริง
> "ความเสี่ยงหลักเหลือที่ execution discipline ไม่ใช่ตัวแผน" — กฎหน้างาน:

- **Rule #0 (สำคัญสุด):** ถ้ามีข้อมูลใหม่ที่ทำให้ **assumption หลักของแผนผิด → ABORT + restore + วิเคราะห์ใหม่. ห้ามแก้สด/คิดสด/ตัดสินใจสด กลาง migration**
- **Rule #1 — ห้ามข้าม Exit Criteria:** ต้องผ่าน **100%** (checksum 95% = ไม่ผ่าน). ไม่ครบ = ไม่ขึ้น phase ถัดไป
- **Rule #2 — Abort > Improvise:** เจออะไรที่ runbook ไม่ได้เขียนไว้ → abort ไม่ใช่ improvise (incident ส่วนใหญ่มาจาก "ขอแก้นิดเดียว")
- **Rule #3 — Single Operator:** Operator = 1 คน (Claude + กัญจน์อยู่ด้วย), Reviewer = 1 (ChatGPT async). ห้ามแก้พร้อมกันหลายฝั่งกลาง window
- **Rule #4 — Timestamp ทุก milestone** ลง runbook (เช่น `20:01 stop · 20:05 backup · 20:07 checksum OK · 20:11 restart`) — มีค่าตอน rollback/forensic

### ⏱️ Time-box / Abort Triggers (window Phase 2)
- **Window target = 15 นาที · Hard-stop = 30 นาที** → เกิน 30 นาทียังไม่ผ่าน Exit Criteria = **rollback ทันที**
- **🛑 Group B (hotfix เฉพาะ VPS ที่ไม่อยู่ origin) โผล่กลาง window = ABORT TRIGGER** — แปลว่า assumption "VPS==origin (scp มา)" ผิด. ไม่ cherry-pick สด. abort → restore → ตรวจ Group B ใน local → push → เริ่ม window ใหม่. (Group B ควรถูกจับใน **dry-run Task 1.7 ก่อน window** อยู่แล้ว)

### Go / No-Go gate
- **Phase 0-1 = GO** (ไม่แตะ production state)
- **Phase 2+ = CONDITIONAL GO** — เปิด window ได้ต่อเมื่อ review ผลจริงจาก Phase 0 audit + Phase 1 tests + hidden-writer scan + **reconcile dry-run inventory (ต้องเป็น Group A/C ล้วน, ไม่มี B)**

---

## File Structure

**สร้างใหม่:**
- `docs/runbooks/vps-state-migration.md` — runbook + rollback log (เก็บ output แต่ละ phase + `vps_vs_origin.patch`)
- `scripts/verify_runtime_paths.py` — leak detector: ไม่มี runtime-state file ถูกแตะใน app/data หลัง cutoff (Phase 3, 48h watch)
- `scripts/validate_state_files.py` — lightweight startup validation (parse + top-level type + not-empty) เรียกก่อน start services (Phase 2)

**แก้ helper:**
- `scripts/bms_paths.py` — เพิ่ม `heal_legacy_state(*names)` (dual-read transition: ถ้า RUNTIME_DIR/name หาย แต่ app/data/name มี → copy + log ดังๆ) เรียกที่ entry ของแต่ละ service ช่วง transition, ถอดออก Phase 4. (`runtime_path` guard เขียน app/data ไม่ได้ — มีแล้ว ไม่แตะ)

**แก้ (Phase 1 — wire bms_paths):** runtime-state writers/readers (รายการเต็มสร้างใน Task 1.1). ตัวที่ confirm แล้ว:
- `scripts/Sebastian_RSS_Scraper.py:43` (DATA_DIR → runtime สำหรับ rss_queue/rss_seen_ids/dept_failure_state/rss_run; egp_deptid_catalog/target_deptids = ก้ำกึ่ง ดู Task 1.1)
- `scripts/Sebastian_RSS_Notifier.py:31-32` (rss_queue read, rss_notifier_epoch.txt)
- `scripts/Sebastian_Enrichment_Worker.py:50-51,123` (resolve_plane_state, api_ingestion_state, resolve_heartbeat)
- `scripts/health_deadman.py:40-41` (resolve_heartbeat READER — ต้องชี้ dir เดียวกับ Enrichment_Worker)
- `scripts/queue_health.py:11-12` · `scripts/pipeline_funnel.py:39` · `scripts/dashboard_extractor.py:266` · `scripts/refresh_active_jobs.py:275` (readers)
- `scripts/vps_canary.py` · `scripts/Sebastian_Province_Discovery.py` (ตรวจใน Task 1.1)

**ไม่แก้ (read-only assets — คงใน repo):** winner_history.db ภายใต้ BMS_DATA_DIR อยู่แล้ว, config/*, lookup, seed.

---

## PHASE 0 — Freeze + Backup (no production mutation)

### Task 0.1: Freeze policy

- [ ] **Step 1: ประกาศ freeze** — ห้าม deploy feature/scp ใหม่จนจบ Phase 4. จดใน progress_log + Discord.

- [ ] **Step 2: Forensic snapshot (v2.1) — text เดียวตอบ "cutover ระบบอยู่สถานะไหน"**

> ไม่ใช่ backup (กู้คืน) แต่เป็นหลักฐาน state ณ จุดเริ่ม. เก็บใน backup folder + local

Run:
```bash
TS=$(date +%Y%m%d_%H%M%S)
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && { echo '=== TS ==='; date -Is; \
   echo '=== git HEAD ==='; git rev-parse HEAD; \
   echo '=== git status ==='; git status --short; \
   echo '=== git stash ==='; git stash list; \
   echo '=== timers ==='; systemctl list-timers 'bms-*' --no-legend; \
   echo '=== services ==='; systemctl list-units --type=service 'bms-*' --no-legend; \
   echo '=== sha256 state ==='; sha256sum /opt/bms/data/*.json /opt/bms/app/data/*.json 2>/dev/null; \
   } > /opt/bms/backups/forensic_\$(date +%Y%m%d_%H%M%S).txt; ls -t /opt/bms/backups/forensic_*.txt | head -1"
```
Expected: path ของ forensic_*.txt — ดึงลง local ด้วย (`scp ... forensic_*.txt backups/`). บันทึก HEAD ที่เห็น (คาด `f5311f7`)

### Task 0.2: Full backup (code + data + db + env + systemd)

- [ ] **Step 1: หยุด timers + bms-api + tunnel (freeze ทั้งหมด — consistency > availability สำหรับ 5 users)**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "sudo systemctl stop bms-enrichment-worker.timer bms-rss-notifier.timer \
   bms-line-sender.timer bms-province-discovery.timer bms-province-discovery-full-bkg.timer \
   bms-canary.timer bms-deadman.timer bms-shadow-audit.timer bms-daily-digest.timer \
   bms-daily-user-summary.timer bms-api.service bms-tunnel.service && echo STOPPED"
```
Expected: `STOPPED`. **stop bms-api ด้วย (บังคับ, v2)** — กัน read-old/write-new ระหว่าง copy. LINE retry webhook ได้บ้าง + นัด off-hours window 10-15 นาที. (ChatGPT review รอบ 2: production เล็ก consistency สำคัญกว่า availability)

- [ ] **Step 2: ยืนยันไม่มี process เขียน state ค้าง**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "systemctl list-units --state=running 'bms-*' --no-legend | grep -v 'api\|tunnel' || echo NONE_RUNNING"
```
Expected: `NONE_RUNNING`

- [ ] **Step 3: Backup ทุกอย่างเป็น tarball + db ออกมานอก /opt/bms**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "TS=\$(date +%Y%m%d_%H%M%S); mkdir -p /opt/bms/backups/migration_\$TS && \
   tar czf /opt/bms/backups/migration_\$TS/app.tgz -C /opt/bms app && \
   tar czf /opt/bms/backups/migration_\$TS/data.tgz -C /opt/bms data && \
   cp /opt/bms/app/.env /opt/bms/backups/migration_\$TS/env.bak && \
   sudo cp -r /etc/systemd/system/bms-* /opt/bms/backups/migration_\$TS/ 2>/dev/null; \
   ls -la /opt/bms/backups/migration_\$TS && echo \$TS > /tmp/migration_ts.txt"
```
Expected: เห็น app.tgz, data.tgz, env.bak, bms-*.{service,timer}

- [ ] **Step 4: ดึง backup ลงเครื่อง local ด้วย (off-VPS copy)**

Run:
```bash
TS=$(ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cat /tmp/migration_ts.txt")
mkdir -p backups/vps_migration_$TS
scp -i ~/.ssh/bms_vps "bms@45.76.156.166:/opt/bms/backups/migration_$TS/*" "backups/vps_migration_$TS/"
ls -la "backups/vps_migration_$TS/"
```
Expected: ไฟล์ครบบน local

### Task 0.3: Audit hidden writers (v2 — ChatGPT blind spot #7)

> หา writer ที่ไม่ใช่ service หลัก: ad-hoc script, cron เก่า, manual command, process ที่เปิด app/data ค้าง

- [ ] **Step 1: ใครเปิดไฟล์ใน app/data อยู่ (หลัง stop services ควรว่าง)**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "sudo lsof +D /opt/bms/app/data 2>/dev/null || echo 'NONE (ไม่มี process เปิดค้าง — ดี)'"
```
Expected: `NONE` (ถ้ามี = ยังมี writer ค้าง ต้องหา/หยุดก่อน)

- [ ] **Step 2: cron / systemd writers อื่นที่อาจแตะ app/data**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "echo '--- crontab ---'; crontab -l 2>/dev/null | grep -v '^#' || echo none; \
   echo '--- /etc/cron* ---'; sudo grep -rl 'opt/bms' /etc/cron* 2>/dev/null || echo none; \
   echo '--- all bms timers/services ---'; systemctl list-unit-files 'bms-*' --no-legend; \
   echo '--- scripts เขียน app/data ไม่ผ่าน bms_paths ---'; cd /opt/bms/app && \
   grep -rln \"parent.parent.*data\\|/ .data.\" scripts/*.py | head"
```
Expected: list ครบ — จดใน runbook ว่ามีตัวไหน "หลุดสายตา". ตรวจ Windows-side ด้วย (memory: ps1 tasks เขียน repo ฝั่ง Windows ไม่ใช่ VPS — confirm ว่าไม่ได้ rsync/scp data ขึ้น VPS)

- [ ] **Step 3: จดทุก writer ที่เจอใน runbook → ใช้ cross-check กับ inventory Task 1.1**

Expected: เซ็ต writers จาก audit ⊆ เซ็ตที่จะ wire ใน Phase 1 (ถ้ามีตัวนอกเหนือ = ต้องเพิ่มใน Phase 1)

**🔙 ROLLBACK (Phase 0):** ถ้าอะไรพลาด → `systemctl start` timers + bms-api + tunnel กลับ. ยังไม่แตะ state/git เลย ปลอดภัย 100%.

**✅ EXIT CRITERIA (Phase 0):**
- [ ] timers + bms-api + tunnel = stopped (`NONE_RUNNING`)
- [ ] backup ครบ (app.tgz + data.tgz + env + systemd) ทั้งบน VPS **และ** local
- [ ] `lsof +D app/data` = NONE (ไม่มี writer เปิดค้าง)
- [ ] รายชื่อ hidden writers จดใน runbook ครบ

---

## PHASE 1 — Wire runtime-state ผ่าน bms_paths (code-only, ใน repo local)

> ทำบน local repo → commit → push GitHub. **ยังไม่แตะ VPS.** โค้ดนี้จะขึ้น VPS พร้อม git sync ใน Phase 2 (แก้ chicken-and-egg: ไม่ต้อง scp routing code แยก).

### Task 1.0: เพิ่ม `heal_legacy_state()` ใน bms_paths (dual-read transition, v2)

**Files:** Modify `scripts/bms_paths.py`, Create `scripts/test_bms_paths_heal.py`

- [ ] **Step 1: Write failing test**
```python
"""test_bms_paths_heal.py — heal_legacy_state copy old→new + log, ไม่ทับ new ที่มีอยู่."""
import os, sys, tempfile, json
from pathlib import Path
d = tempfile.mkdtemp(); os.environ["BMS_DATA_DIR"] = d
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import bms_paths
legacy = bms_paths._REPO_ROOT / "data" / "_heal_test.json"
legacy.write_text('{"x":1}', encoding="utf-8")
try:
    healed = bms_paths.heal_legacy_state("_heal_test.json")   # new หาย → copy จาก old
    assert healed == ["_heal_test.json"], healed
    assert json.loads(bms_paths.runtime_path("_heal_test.json").read_text())["x"] == 1
    bms_paths.runtime_path("_heal_test.json").write_text('{"x":2}', encoding="utf-8")
    healed2 = bms_paths.heal_legacy_state("_heal_test.json")  # new มีแล้ว → ไม่ทับ
    assert healed2 == [], healed2
    assert json.loads(bms_paths.runtime_path("_heal_test.json").read_text())["x"] == 2
    print("✅ PASS heal_legacy_state")
finally:
    legacy.unlink(missing_ok=True)
```

- [ ] **Step 2: Run → FAIL** — `BMS_ENV=dev python scripts/test_bms_paths_heal.py` → AttributeError (ยังไม่มี heal)

- [ ] **Step 3: เพิ่มฟังก์ชันใน bms_paths.py (ก่อน log_paths)**
```python
import shutil  # เพิ่มบน import

def heal_legacy_state(*names: str) -> list:
    """dual-read transition (time-boxed, ถอด Phase 4): ถ้า runtime file หายแต่ legacy app/data มี
    → copy + LOG ดังๆ (= copy migration พลาด, ต้องสืบ). คืน list ที่ heal. ไม่ทับ runtime ที่มีอยู่."""
    healed = []
    for name in names:
        new = runtime_path(name)
        if new.exists():
            continue
        old = (_REPO_ROOT / "data" / name)
        if old.exists():
            shutil.copy2(old, new)
            print(f"[bms_paths] ⚠️ DUAL-READ HEAL: {name} หายใน {RUNTIME_DIR} → copy จาก {old} "
                  f"(migration copy พลาด? ต้องสืบ)", file=sys.stderr)
            healed.append(name)
    return healed
```

- [ ] **Step 4: Run → PASS** — `BMS_ENV=dev python scripts/test_bms_paths_heal.py` → `✅ PASS`

- [ ] **Step 5: Commit**
```bash
git add scripts/bms_paths.py scripts/test_bms_paths_heal.py
git commit -m "feat(bms_paths): heal_legacy_state — dual-read transition + loud log (v2 ChatGPT #1)"
```

### Task 1.1: สร้าง inventory เต็มของ runtime-state references

**Files:** Create `docs/runbooks/vps-state-migration.md`

- [ ] **Step 1: enumerate ทุก reference ของ runtime-state ใน active scripts**

Run:
```bash
rg -n "parent\.parent\s*/\s*[\"']data[\"']|DATA_DIR\s*=.*data|/ \"data\"" scripts --glob '!**/archive/**' \
  | rg -v "winner_history|backups|downloads|test_run|ai_results"
```

- [ ] **Step 2: แยกแต่ละ reference เป็น 2 กลุ่ม แล้วจดตาราง ใน runbook**

จดตาราง: `script:line | filename | RUNTIME (mutate) / ASSET (read-only) | writer/reader`
- **RUNTIME** (ต้อง wire → `runtime_path`): rss_queue, rss_seen_ids, api_ingestion_state, rss_run_state/rss_run_*, resolve_heartbeat, resolve_plane_state, rss_stage_rotation, rss_notifier_epoch.txt, dept_failure_state, seen_ids, discord_reply/waiting (ถ้า active บน VPS)
- **ASSET** (คงไว้ → `asset_path` หรือไม่แตะ): egp_deptid_catalog, target_deptids, egp_w0_catalog (seed/lookup ที่ commit ใน repo), winner_history.db, config/*
- ตัดสิน egp_deptid_catalog/target_deptids: ถ้า scraper **เขียน** ทับ runtime → RUNTIME; ถ้าเป็น lookup ที่ commit → ASSET. ตรวจจาก `rg -n "egp_deptid_catalog|target_deptids" scripts/Sebastian_RSS_Scraper.py` (มี `.write_text` ไหม) → ถ้าเขียน = RUNTIME

- [ ] **Step 3: Commit runbook (ตาราง inventory)**
```bash
git add docs/runbooks/vps-state-migration.md
git commit -m "docs(runbook): VPS state-migration inventory (runtime vs asset)"
```

### Task 1.2: เขียน test ว่า runtime-state scripts ใช้ bms_paths (regression guard)

**Files:** Create `scripts/test_runtime_paths.py`

- [ ] **Step 1: Write failing test** — ตรวจว่าไฟล์เป้าหมายไม่มี hardcoded `parent.parent / "data" / "<runtime-file>"`

```python
"""test_runtime_paths.py — กัน regression: runtime-state ต้องผ่าน bms_paths ไม่ hardcode app/data."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = Path(__file__).parent
RUNTIME_FILES = [
    "rss_queue.json", "rss_seen_ids.json", "api_ingestion_state.json",
    "resolve_heartbeat.json", "resolve_plane_state.json", "rss_stage_rotation.json",
    "rss_notifier_epoch.txt", "dept_failure_state.json",
]
# ไฟล์ที่ถูก migrate แล้ว (เพิ่มทีละตัวเมื่อ wire เสร็จ)
MIGRATED = [
    "scripts/Sebastian_RSS_Scraper.py", "scripts/Sebastian_RSS_Notifier.py",
    "scripts/Sebastian_Enrichment_Worker.py", "scripts/health_deadman.py",
    "scripts/queue_health.py", "scripts/pipeline_funnel.py",
    "scripts/dashboard_extractor.py", "scripts/refresh_active_jobs.py",
]
BAD = re.compile(r'parent\.parent\s*/\s*["\']data["\']\s*/\s*["\']([^"\']+)["\']')
fails = []
for rel in MIGRATED:
    p = Path(__file__).parent.parent / rel
    if not p.exists():
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        m = BAD.search(line)
        if m and m.group(1) in RUNTIME_FILES:
            fails.append(f"{rel}:{i} ยัง hardcode app/data → {m.group(1)}")
if fails:
    print("❌ FAIL:"); [print("  " + f) for f in fails]; sys.exit(1)
print(f"✅ PASS {len(MIGRATED)} scripts ใช้ bms_paths สำหรับ runtime-state")
```

- [ ] **Step 2: Run → FAIL** (ยังไม่ wire)

Run: `python scripts/test_runtime_paths.py`
Expected: FAIL ลิสต์ไฟล์ที่ยัง hardcode

### Task 1.3: Wire Sebastian_Enrichment_Worker.py + health_deadman.py (คู่ writer/reader ของ resolve_heartbeat — ทำคู่กันกัน split)

**Files:** Modify `scripts/Sebastian_Enrichment_Worker.py:50-51,123`, `scripts/health_deadman.py:40-41`

- [ ] **Step 1: Enrichment_Worker — เพิ่ม import + เปลี่ยน 3 path**

แทนที่ (บรรทัด ~50-51):
```python
RESOLVE_STATE_PATH   = Path(__file__).parent.parent / "data" / "resolve_plane_state.json"
API_STATE_PATH    = Path(__file__).parent.parent / "data" / "api_ingestion_state.json"
```
เป็น:
```python
import bms_paths  # noqa: E402  (sys.path มี scripts/ แล้วจาก import เดิม)
RESOLVE_STATE_PATH = bms_paths.runtime_path("resolve_plane_state.json")
API_STATE_PATH     = bms_paths.runtime_path("api_ingestion_state.json")
```
และบรรทัด ~123:
```python
RESOLVE_HEARTBEAT_PATH = bms_paths.runtime_path("resolve_heartbeat.json")
```

- [ ] **Step 2: health_deadman.py — เปลี่ยน reader ให้ชี้ที่เดียวกัน**

แทนที่ (บรรทัด 40-41):
```python
APP_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
RESOLVE_HB_FILE = os.path.join(APP_DATA_DIR, "resolve_heartbeat.json")
```
เป็น:
```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bms_paths  # noqa: E402
RESOLVE_HB_FILE = str(bms_paths.runtime_path("resolve_heartbeat.json"))
```
(ตรวจว่า `import sys` มีอยู่แล้วด้านบน)

- [ ] **Step 3: รัน test (local, ตั้ง BMS_ENV=dev กัน fail-loud)**

Run: `BMS_ENV=dev python scripts/test_runtime_paths.py 2>&1 | tail -3`
Expected: ยัง FAIL (เหลือ scripts อื่น) แต่ 2 ตัวนี้หายจาก list

- [ ] **Step 4: Commit**
```bash
git add scripts/Sebastian_Enrichment_Worker.py scripts/health_deadman.py
git commit -m "refactor(state): wire Enrichment_Worker+health_deadman → bms_paths.runtime_path (resolve_heartbeat คู่ writer/reader)"
```

### Task 1.4: Wire Sebastian_RSS_Scraper.py + Sebastian_RSS_Notifier.py (rss_queue/seen — คู่ writer/reader)

**Files:** Modify `scripts/Sebastian_RSS_Scraper.py:43-51`, `scripts/Sebastian_RSS_Notifier.py:31-32`

- [ ] **Step 1: RSS_Scraper — แยก RUNTIME ออกจาก ASSET**

หลังบรรทัด 43-44 (`DATA_DIR = ...; DATA_DIR.mkdir`):
```python
import bms_paths  # noqa: E402
# RUNTIME (mutate ทุกรอบ) → BMS_DATA_DIR
RSS_SEEN_FILE        = bms_paths.runtime_path("rss_seen_ids.json")
RSS_QUEUE_FILE       = bms_paths.runtime_path("rss_queue.json")
SCRAPER_SEEN_FILE    = bms_paths.runtime_path("seen_ids.json")
DEPT_FAIL_STATE_FILE = bms_paths.runtime_path("dept_failure_state.json")
# ASSET (lookup/seed ที่ commit ใน repo) → คง DATA_DIR (app/data)
CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"
TARGET_FILE  = DATA_DIR / "target_deptids.json"
```
ลบบรรทัดเดิม 46-51 ที่ซ้ำ (CATALOG/TARGET คงไว้, RSS_SEEN/QUEUE/SCRAPER_SEEN/DEPT_FAIL ย้าย). **ตรวจ**: ถ้า Task 1.1 พบ scraper `.write_text` ทับ egp_deptid_catalog/target_deptids เป็น runtime → ย้ายเป็น runtime_path ด้วย. rss_run_<ts> report ก็ → runtime_path.

- [ ] **Step 2: RSS_Notifier — เปลี่ยน 2 path (บรรทัด 31-32)**
```python
import bms_paths  # noqa: E402
RSS_QUEUE_PATH = bms_paths.runtime_path("rss_queue.json")
EPOCH_PATH     = bms_paths.runtime_path("rss_notifier_epoch.txt")
```
**⚠️ epoch = Tier3**: `bms_paths` ไม่ default เงียบ (fail-loud) — ถ้า /opt/bms/data ไม่มี epoch ตอน migrate ต้อง copy มาก่อน (Phase 2) ไม่งั้น notifier bootstrap ผิด.

- [ ] **Step 3: รัน test**

Run: `BMS_ENV=dev python scripts/test_runtime_paths.py 2>&1 | tail -3`
Expected: 2 ตัวนี้หายจาก list

- [ ] **Step 4: Commit**
```bash
git add scripts/Sebastian_RSS_Scraper.py scripts/Sebastian_RSS_Notifier.py
git commit -m "refactor(state): wire RSS Scraper+Notifier runtime-state → bms_paths (asset แยก)"
```

### Task 1.5: Wire readers (queue_health, pipeline_funnel, dashboard_extractor, refresh_active_jobs)

**Files:** Modify `scripts/queue_health.py:11-12`, `scripts/pipeline_funnel.py:39`, `scripts/dashboard_extractor.py:266`, `scripts/refresh_active_jobs.py:275`

- [ ] **Step 1: แต่ละไฟล์ — import bms_paths + เปลี่ยน reader path**

`queue_health.py:11-12`:
```python
import bms_paths
QUEUE_FILE = bms_paths.runtime_path("rss_queue.json")
STATE_FILE = bms_paths.runtime_path("api_ingestion_state.json")
```
`pipeline_funnel.py:39`: `seen_file = bms_paths.runtime_path("rss_seen_ids.json")`
`dashboard_extractor.py:266`: `queue_file = bms_paths.runtime_path("rss_queue.json")`
`refresh_active_jobs.py:275`: `queue_file = bms_paths.runtime_path("rss_queue.json")`
(เพิ่ม `import bms_paths` + `sys.path.insert(0, str(Path(__file__).parent))` ถ้ายังไม่มี)

- [ ] **Step 2: รัน test → PASS**

Run: `BMS_ENV=dev python scripts/test_runtime_paths.py`
Expected: `✅ PASS 8 scripts ใช้ bms_paths`

- [ ] **Step 3: smoke import ทุกตัว (ไม่ crash)**

Run: `BMS_ENV=dev python -c "import sys; sys.path.insert(0,'scripts'); import queue_health, pipeline_funnel, bms_paths; print('import OK')"`
Expected: `import OK`

- [ ] **Step 4: Commit + push GitHub**
```bash
git add scripts/queue_health.py scripts/pipeline_funnel.py scripts/dashboard_extractor.py scripts/refresh_active_jobs.py scripts/test_runtime_paths.py
git commit -m "refactor(state): wire readers → bms_paths + regression test (รวม Phase 1 state routing)"
git push origin main
```
Expected: push สำเร็จ → origin/main มี state-routing ครบ

### Task 1.6: เรียก heal_legacy_state + log_paths ที่ entry ของ service หลัก (v2)

**Files:** Modify `scripts/Sebastian_Enrichment_Worker.py`, `scripts/Sebastian_RSS_Notifier.py`, `scripts/Sebastian_RSS_Scraper.py`, `scripts/health_deadman.py` (ต้น main/entry)

- [ ] **Step 1: เพิ่ม 2 บรรทัดที่ต้น main แต่ละ service** (ก่อนอ่าน state ครั้งแรก)
```python
_STATE_FILES = ["rss_queue.json", "rss_seen_ids.json", "api_ingestion_state.json",
                "resolve_heartbeat.json", "resolve_plane_state.json", "rss_notifier_epoch.txt"]
bms_paths.heal_legacy_state(*_STATE_FILES)   # dual-read transition (ถอด Phase 4)
bms_paths.log_paths(*_STATE_FILES)           # instrumentation: ยืนยัน RUNTIME_DIR เดียวกัน
```
(แต่ละ service ใส่เฉพาะ state ที่ตัวเองใช้ก็ได้ — แต่ใส่ครบ idempotent ไม่เสียหาย)

- [ ] **Step 2: smoke test** — `BMS_ENV=dev python -c "import sys;sys.path.insert(0,'scripts');import Sebastian_Enrichment_Worker, health_deadman;print('OK')"`
Expected: `OK` (ไม่ crash ตอน import)

- [ ] **Step 3: Commit + push**
```bash
git add scripts/Sebastian_Enrichment_Worker.py scripts/Sebastian_RSS_Notifier.py scripts/Sebastian_RSS_Scraper.py scripts/health_deadman.py
git commit -m "feat(transition): service entry heal_legacy_state + log_paths (v2 dual-read + observability)"
git push origin main
```

### Task 1.7: Reconcile dry-run ก่อน window (v2.1, read-only) — จับ Group B ก่อนเปิด window

> diff VPS-worktree vs origin/main เป็น **read-only** (git fetch+diff ไม่ mutate) → ทำได้โดยไม่ต้องหยุด service. เป้าหมาย: รู้ Group A/B/C **ก่อน** เปิด maintenance window. ถ้ามี Group B = แก้ใน local ก่อน, **ห้ามเปิด window จนกว่าเหลือ A/C ล้วน**

- [ ] **Step 1: fetch + diff ทุก script ที่ต่าง (read-only บน VPS)**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && git fetch origin 2>&1 | tail -1 && \
   for f in \$(git diff --name-only origin/main -- 'scripts/*.py' 'config/*'); do \
     echo \"\$f : \$(git diff origin/main -- \$f | wc -l) บรรทัด\"; done"
```
Expected: list ไฟล์ + ขนาด diff. ตัวที่ 0 บรรทัด = Group A (==origin)

- [ ] **Step 2: ดู diff จริงของแต่ละไฟล์ที่ > 0 → จัด A/B/C ใน runbook**
```bash
ssh ... "cd /opt/bms/app && git diff origin/main -- scripts/<file>.py"
```
- A = ต่างเพราะ scp version ใหม่ที่ == origin (จริงๆ คือ git ยังไม่ commit) → take origin
- **B = มี logic ไม่อยู่ origin** → cherry-pick กลับ local repo, commit, push, fetch ใหม่, **ทำซ้ำจนเหลือ A/C**
- C = hotfix ชั่วคราว/debug → ทิ้ง

- [ ] **Step 3: ยืนยัน "เหลือ A/C ล้วน, ไม่มี B" → gate เปิด window**

Expected: จด inventory ใน runbook ว่าทุกไฟล์ = A หรือ C. **นี่คือเงื่อนไข Conditional-Go ของ Phase 2** (Group B = ห้ามเปิด window จน resolve ใน local)

**🔙 ROLLBACK (Phase 1):** เป็น commit ใน repo local/GitHub ล้วน — `git revert` ได้. **VPS ยังไม่ถูกแตะ** (dry-run = read-only) จึงไม่มีผลกับ production.

**✅ EXIT CRITERIA (Phase 1):**
- [ ] `test_runtime_paths.py` PASS (ทุก runtime-state script ใช้ bms_paths)
- [ ] `test_bms_paths_heal.py` PASS
- [ ] inventory table ใน runbook ครบ + cross-check กับ hidden-writer audit (Task 0.3) แล้ว
- [ ] service หลักทุกตัว import ได้ (smoke) + เรียก heal+log_paths ที่ entry
- [ ] origin/main มี Phase 1 ครบ (push แล้ว) · **VPS ยังไม่ถูกแตะ**
- [ ] **reconcile dry-run (Task 1.7) = Group A/C ล้วน, ไม่มี B** (ถ้ามี B = resolve ก่อน, ยังไม่เปิด window)

---

## PHASE 2 — Migrate live state + Git sync VPS (in maintenance window, timers ยัง stop)

> ✅ ก่อนเริ่ม: ยืนยัน Phase 0 backup ครบ + timers stopped + Phase 1 อยู่บน origin/main แล้ว

### Task 2.1: Copy live runtime-state จาก app/data → /opt/bms/data (writer-wins)

- [ ] **Step 1: เทียบไฟล์ที่ใหม่กว่า (writer-wins, ไม่ทับของใหม่ด้วยของเก่า)**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "for f in rss_queue.json rss_seen_ids.json api_ingestion_state.json resolve_heartbeat.json \
            resolve_plane_state.json rss_stage_rotation.json rss_notifier_epoch.txt \
            dept_failure_state.json seen_ids.json rss_run_state.json; do \
     a=/opt/bms/app/data/\$f; b=/opt/bms/data/\$f; \
     printf '%-28s app=%s  data=%s\n' \$f \"\$([ -f \$a ] && stat -c%y \$a | cut -d. -f1 || echo -)\" \"\$([ -f \$b ] && stat -c%y \$b | cut -d. -f1 || echo -)\"; \
   done"
```
Expected: ตารางเวลา. **กฎ:** copy เฉพาะตัวที่ app/data ใหม่กว่า /opt/bms/data (หรือ /opt/bms/data ไม่มี)

- [ ] **Step 2: Copy ตัวที่ app/data ใหม่กว่า (ทำมือทีละไฟล์ตามผล Step 1)**

Run (ตัวอย่าง — ปรับตาม Step 1):
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cp -v /opt/bms/app/data/rss_queue.json /opt/bms/data/ && \
   cp -v /opt/bms/app/data/rss_seen_ids.json /opt/bms/data/ && \
   cp -v /opt/bms/app/data/api_ingestion_state.json /opt/bms/data/ && \
   cp -v /opt/bms/app/data/resolve_heartbeat.json /opt/bms/data/ && \
   cp -v /opt/bms/app/data/resolve_plane_state.json /opt/bms/data/ && \
   cp -vn /opt/bms/app/data/rss_notifier_epoch.txt /opt/bms/data/"
```
Expected: copy สำเร็จ (`-n` สำหรับ epoch = ไม่ทับถ้ามีแล้ว, กัน Tier3 พัง)

- [ ] **Step 3: verify checksum (v2 — แข็งกว่า count, ยืนยัน copy byte-identical)**

Run (ต่อไฟล์ที่ copy):
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "for f in rss_queue.json rss_seen_ids.json api_ingestion_state.json resolve_heartbeat.json resolve_plane_state.json; do \
     a=\$(sha256sum /opt/bms/app/data/\$f 2>/dev/null | cut -d' ' -f1); \
     b=\$(sha256sum /opt/bms/data/\$f 2>/dev/null | cut -d' ' -f1); \
     [ \"\$a\" = \"\$b\" ] && echo \"OK  \$f\" || echo \"MISMATCH \$f (a=\$a b=\$b)\"; \
   done"
```
Expected: `OK` ทุกไฟล์ที่ copy (MISMATCH = copy ไม่ครบ/ผิด → หยุด)

- [ ] **Step 4: lightweight startup validation (v2 — กัน torn file จาก hard-kill) — สร้าง validator**

**Files:** Create `scripts/validate_state_files.py`
```python
"""validate_state_files.py — lightweight: parse + top-level type + not-empty (ไม่ทำ field schema).
กัน torn/partial JSON (เช่น process ถูก hard-kill ตอนเขียน). รัน BMS_DATA_DIR=/opt/bms/data python ...
"""
import json, os, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
DATA = Path(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"))
# (filename, expected_type, allow_empty)
SPEC = [
    ("rss_queue.json", list, True), ("rss_seen_ids.json", list, False),
    ("api_ingestion_state.json", dict, False), ("resolve_heartbeat.json", dict, True),
    ("resolve_plane_state.json", dict, True),
]
fails = []
for name, typ, allow_empty in SPEC:
    p = DATA / name
    if not p.exists():
        continue  # ไม่มี = heal_legacy_state จะจัดการตอน start (ไม่ fail ที่นี่)
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        fails.append(f"{name}: parse FAIL ({e}) — torn file?"); continue
    if not isinstance(v, typ):
        fails.append(f"{name}: type {type(v).__name__} != {typ.__name__}")
    elif not allow_empty and len(v) == 0:
        fails.append(f"{name}: ว่าง (ควรมีข้อมูล)")
if fails:
    print("❌ STATE VALIDATION FAIL:"); [print("  " + f) for f in fails]; sys.exit(1)
print("✅ state files valid (parse + type + not-empty)")
```

Run:
```bash
scp -i ~/.ssh/bms_vps scripts/validate_state_files.py bms@45.76.156.166:/opt/bms/app/scripts/  # ขึ้นชั่วคราว (จะตามมาใน git sync)
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python /opt/bms/app/scripts/validate_state_files.py"
```
Expected: `✅ state files valid` (ถ้า ❌ = torn file → ใช้ backup ตัวนั้นแทน, อย่า proceed)

### Task 2.2: Reconcile confirm (in-window) — ยืนยันตรงกับ dry-run Task 1.7

> reconcile หลักทำเป็น dry-run ใน Task 1.7 ก่อน window แล้ว (เหลือ A/C ล้วน). Task นี้ = **confirm สั้นๆ** ว่าสถานะไม่เปลี่ยน

- [ ] **Step 1: re-fetch + diff ซ้ำ ยืนยันยังเป็น A/C ล้วน (เหมือน Task 1.7)**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && git fetch origin 2>&1 | tail -1 && \
   for f in \$(git diff --name-only origin/main -- 'scripts/*.py' 'config/*'); do \
     echo \"\$f : \$(git diff origin/main -- \$f | wc -l) บรรทัด\"; done"
```
Expected: ตรงกับ inventory dry-run (Task 1.7)

- [ ] **Step 2: 🛑 ถ้าเจอ Group B ที่ dry-run ไม่เคยเห็น = ABORT TRIGGER**

**ไม่ cherry-pick สด. ไม่แก้สด.** → abort window: restore backup, start services, ปิด window. แล้วไปตรวจ Group B ใน local (นอก window) → push → นัด window ใหม่. (Rule #0 + Rule #2: Group B กลาง window = assumption ผิด ไม่ใช่งานย่อย)
Expected: ปกติควรไม่มี B (dry-run จับไปแล้ว) → ผ่านไป Task 2.3

### Task 2.3: Git sync VPS → origin/main (atomic, ตอนนี้ปลอดภัยเพราะ state ออกนอก app/data แล้ว)

- [ ] **Step 1: hard reset app → origin/main + clean untracked code (เก็บ data/ ไว้)**

**Run (v2: export `vps_vs_origin.patch` ก่อน reset — เครื่องย้อนเวลาเผื่อมี hotfix ที่ลืม):**
```bash
TS=$(ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cat /tmp/migration_ts.txt")
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && git diff origin/main > /opt/bms/backups/migration_$TS/vps_vs_origin.patch && \
   git status --short > /opt/bms/backups/migration_$TS/vps_status_at_reset.txt && \
   wc -l /opt/bms/backups/migration_$TS/vps_vs_origin.patch"
scp -i ~/.ssh/bms_vps "bms@45.76.156.166:/opt/bms/backups/migration_$TS/vps_vs_origin.patch" "backups/vps_migration_$TS/"
```
Expected: patch ถูกเก็บทั้ง VPS + local (tracked diff ทั้งหมด; untracked = app.tgz Phase 0 คุมอยู่). **ห้าม reset จนกว่า patch ถูกเก็บ**

แล้วจึง reset:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && git reset --hard origin/main && \
   git clean -fd -e 'data/' scripts/ docs/ config/ && \
   git rev-parse HEAD"
```
Expected: HEAD = `c077938`+ (ตรง origin). **`-e 'data/'`** = ไม่ลบ app/data (กันลบ state เผื่อยังมี reader หลุด — safety net จนกว่า Phase 3 verify)

- [ ] **Step 2: ยืนยัน working tree สะอาด (เหลือแต่ data/ ที่ ignore ทีหลัง)**

Run: `ssh ... "cd /opt/bms/app && git status --short | grep -vE '^.. data/' || echo CLEAN"`
Expected: `CLEAN`

- [ ] **Step 3: ตรวจ transitive deps ครบ (กัน near-miss N+87 ซ้ำ)** — ทุก import resolve ได้

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && for s in Sebastian_Enrichment_Worker Sebastian_RSS_Notifier health_deadman job_matcher Sebastian_Daily_Digest; do \
     BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c \"import sys;sys.path.insert(0,'scripts');import \$s;print('OK \$s')\" || echo \"FAIL \$s\"; done"
```
Expected: `OK` ทุกตัว

**🔙 ROLLBACK (Phase 2):** restore จาก backup: `tar xzf /opt/bms/backups/migration_<TS>/app.tgz -C /opt/bms` + `data.tgz` → `systemctl start` timers + bms-api + tunnel. กลับสู่สภาพก่อน migrate ทุกอย่าง (< 5 นาที). (ถ้าเจอ hotfix หายทีหลัง → `git apply vps_vs_origin.patch`)

**✅ EXIT CRITERIA (Phase 2):**
- [ ] state copy ครบ + **checksum ตรงทุกไฟล์** (Task 2.1 Step 3)
- [ ] `validate_state_files.py` = ✅ valid (ไม่มี torn file)
- [ ] `vps_vs_origin.patch` ถูกเก็บทั้ง VPS + local (ก่อน reset)
- [ ] reconcile: ไม่มีกลุ่ม B ค้าง (hotfix เฉพาะ VPS จัดการครบ)
- [ ] VPS HEAD == origin/main · `git status` clean (เหลือแต่ data/)
- [ ] import ทุก service OK (transitive deps ครบ)
- [ ] **services ยัง stopped** (ยังไม่ start จนกว่า Phase 3 เริ่ม)

---

## PHASE 3 — Verify (startup instrumentation + 48h watch) ⭐ สำคัญสุด

> ตอบโจทย์ "failure surface ทีหลัง" — ต้องพิสูจน์ว่าไม่มี writer/reader ตกค้างชี้ app/data

### Task 3.1: ยืนยัน log_paths + heal อยู่บน VPS แล้ว (เพิ่มใน Phase 1.6, มากับ git sync Phase 2)

> log_paths + heal_legacy_state ถูกเพิ่มที่ service entry แล้วใน Task 1.6 และขึ้น VPS พร้อม git reset Phase 2.3 → **ไม่ต้องเพิ่มซ้ำ** แค่ยืนยัน

- [ ] **Step 1: ยืนยันโค้ด entry มี heal+log_paths บน VPS**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && grep -l 'heal_legacy_state' scripts/Sebastian_Enrichment_Worker.py scripts/Sebastian_RSS_Notifier.py scripts/health_deadman.py && echo PRESENT"
```
Expected: `PRESENT` (3 ไฟล์มี) — ถ้าไม่มี = git sync Phase 2 ไม่ครบ ให้ตรวจ

### Task 3.2: สร้าง verify_runtime_paths.py + restart timers + watch

**Files:** Create `scripts/verify_runtime_paths.py`

- [ ] **Step 1: เขียน verifier — alert ถ้า runtime-state file ถูกแตะใน app/data หลัง cutoff**
```python
"""verify_runtime_paths.py — เตือนถ้ามี runtime-state file ใน app/data ที่ถูกเขียนหลัง migration cutoff
(= มี writer หลุดยังชี้ app/data). รันเป็น cron heartbeat 48h แรก."""
import os, sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
APP_DATA = Path("/opt/bms/app/data")
RUNTIME = {"rss_queue.json","rss_seen_ids.json","api_ingestion_state.json","resolve_heartbeat.json",
           "resolve_plane_state.json","rss_stage_rotation.json","rss_notifier_epoch.txt","dept_failure_state.json"}
cutoff = float(os.environ.get("MIGRATION_CUTOFF_TS", "0"))
stale = []
for f in RUNTIME:
    p = APP_DATA / f
    if p.exists() and p.stat().st_mtime > cutoff:
        stale.append(f"{f} (mtime {time.ctime(p.stat().st_mtime)})")
if stale:
    print("❌ WRITER หลุด — ยังเขียน app/data หลัง cutoff:"); [print("  "+s) for s in stale]; sys.exit(1)
print("✅ ไม่มี writer แตะ app/data หลัง cutoff (single source ของจริง)")
```

- [ ] **Step 2: commit + push + pull VPS** (รวม validate_state_files.py จาก Phase 2 ให้เข้า git ด้วย)
```bash
git add scripts/verify_runtime_paths.py scripts/validate_state_files.py
git commit -m "feat(verify): runtime-path leak detector + state validator (48h watch)"
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main"
```

- [ ] **Step 3: validate state ก่อน start (กัน torn file) → บันทึก cutoff → restart ทุก service (รวม bms-api + tunnel ที่ stop ไป Phase 0)**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python /opt/bms/app/scripts/validate_state_files.py && \
   date +%s > /opt/bms/data/migration_cutoff_ts.txt && \
   sudo systemctl start bms-enrichment-worker.timer bms-rss-notifier.timer bms-line-sender.timer \
   bms-province-discovery.timer bms-canary.timer bms-deadman.timer bms-shadow-audit.timer \
   bms-daily-digest.timer bms-daily-user-summary.timer bms-province-discovery-full-bkg.timer \
   bms-api.service bms-tunnel.service && echo STARTED"
```
Expected: `✅ state files valid` แล้ว `STARTED` (validate fail = ไม่ start, ใช้ backup ไฟล์นั้นก่อน). **bms-api + tunnel กลับมาแล้ว = ปิด maintenance window**

- [ ] **Step 4: รอ 1-2 รอบ timer (enrichment ทุก 2 นาที) แล้ว verify log_paths ชี้ /opt/bms/data**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "sleep 150; journalctl -u bms-enrichment-worker.service --since '3 min ago' | grep bms_paths | tail -5"
```
Expected: `[bms_paths] RUNTIME_DIR=/opt/bms/data` (ไม่ใช่ app/data)

- [ ] **Step 5: verify ไม่มี writer หลุด (รันทันที + ทิ้งไว้ check 48h)**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "MIGRATION_CUTOFF_TS=\$(cat /opt/bms/data/migration_cutoff_ts.txt) /opt/bms/venv/bin/python /opt/bms/app/scripts/verify_runtime_paths.py"
```
Expected: `✅ ไม่มี writer แตะ app/data หลัง cutoff` — ถ้า ❌ → มี script ตกหล่น (กลับ Phase 1 wire เพิ่ม)

- [ ] **Step 6: sanity ทั้งระบบ (ไม่ส่งงานซ้ำ)** — เทียบ delivery_log + notification_queue ก่อน/หลัง

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "python3 -c \"import sqlite3; c=sqlite3.connect('/opt/bms/data/bms_customers.db'); print('sent 24h:', c.execute(\\\"SELECT COUNT(*) FROM delivery_log WHERE attempted_at>=datetime('now','-1 day')\\\").fetchone()[0]); print('queue pending:', c.execute(\\\"SELECT COUNT(*) FROM notification_queue WHERE status='pending'\\\").fetchone()[0])\""
```
Expected: ไม่มี spike การส่ง (ถ้า sent พุ่ง = dedup หาย = ROLLBACK ทันที)

- [ ] **Step 7: ตั้ง cron heartbeat รัน verify_runtime_paths ทุก 6 ชม. ช่วง 48h** (เผื่อ writer หลุดโผล่ทีหลัง)
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "(crontab -l 2>/dev/null; echo '0 */6 * * * MIGRATION_CUTOFF_TS=\$(cat /opt/bms/data/migration_cutoff_ts.txt) /opt/bms/venv/bin/python /opt/bms/app/scripts/verify_runtime_paths.py >> /opt/bms/data/logs/leak_check.log 2>&1') | crontab - && echo CRON_SET"
```
Expected: `CRON_SET` (ลบ cron นี้ออก Phase 4 หลังครบ 48h)

**🔙 ROLLBACK (Phase 3):** ถ้า verify ❌ หรือ sent spike → `systemctl stop` timers+bms-api+tunnel, restore data.tgz backup, `git reset` กลับ commit ก่อน Phase 3, start. สอบ writer ที่หลุดใน local ก่อนลองใหม่. **heal_legacy_state จะ self-heal ไฟล์ที่ copy พลาด + log เตือน** (ไม่ outage ทันที แต่ต้องสืบ).

**✅ EXIT CRITERIA (Phase 3):**
- [ ] `log_paths` ทุก service journal แสดง `RUNTIME_DIR=/opt/bms/data` (ไม่ใช่ app/data)
- [ ] `verify_runtime_paths.py` = ✅ (0 writer แตะ app/data) — **ต่อเนื่อง 48h ผ่าน cron**
- [ ] ไม่เห็น `DUAL-READ HEAL` log (ถ้าเห็น = copy พลาด, สืบก่อน)
- [ ] delivery_log ไม่ spike (ไม่ส่งงานซ้ำ) · queue ทำงานปกติ
- [ ] bms-api + tunnel กลับมา (window ปิด)

---

## PHASE 4 — Lock-in: git-only deploy + ignore app/data state

### Task 4.1: gitignore runtime-state ใน app/data (กันปนกลับ)

**Files:** Modify `.gitignore`

- [ ] **Step 1: ถอน runtime-state ออกจาก git tracking + ignore**
```bash
git rm --cached data/rss_queue.json data/rss_seen_ids.json data/api_ingestion_state.json \
  data/rss_stage_rotation.json 2>/dev/null
printf '\n# runtime state — อยู่ที่ BMS_DATA_DIR (/opt/bms/data) เท่านั้น (bms_paths)\ndata/rss_queue.json\ndata/rss_seen_ids.json\ndata/api_ingestion_state.json\ndata/resolve_heartbeat.json\ndata/resolve_plane_state.json\ndata/rss_stage_rotation.json\ndata/rss_notifier_epoch.txt\ndata/dept_failure_state.json\n' >> .gitignore
```

- [ ] **Step 2: commit + push + pull VPS**
```bash
git add .gitignore && git commit -m "chore(state): untrack+ignore runtime-state (single authority = BMS_DATA_DIR)"
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main && rm -f data/rss_queue.json data/rss_seen_ids.json data/api_ingestion_state.json && echo DONE"
```
Expected: app/data ไม่มี runtime-state แล้ว (เหลือแต่ /opt/bms/data)

### Task 4.2: เขียน deploy runbook + อัปเดต bms_paths สถานะ

**Files:** Modify `docs/runbooks/vps-state-migration.md`, `scripts/bms_paths.py` (ลบ DORMANT note)

- [ ] **Step 1: จด deploy procedure ใหม่ใน runbook**
```
DEPLOY (ใหม่ — เลิก scp):
  1. local: commit → git push origin main
  2. VPS:  cd /opt/bms/app && git pull --ff-only origin main
  3. VPS:  sudo systemctl restart <service ที่เกี่ยว> (ถ้าเป็น daemon; timer ไม่ต้อง)
  ห้าม scp ไฟล์เดี่ยวเป็นวิธีหลักอีก (= เหตุ deploy-debt + near-miss N+87)
```

- [ ] **Step 2: อัปเดต bms_paths.py docstring — เปลี่ยน "DORMANT" เป็น "ACTIVE (migrated N+88)"**

แก้บรรทัด 13-16 (STATUS block) เป็น:
```python
⚠️ STATUS 2026-06-XX: ACTIVE — runtime-state ทุกตัว route ผ่าน helper นี้แล้ว (migration N+8x).
deploy ผ่าน git pull เท่านั้น (เลิก scp). ดู docs/runbooks/vps-state-migration.md
```

- [ ] **Step 3: commit + push + pull VPS + update memory**
```bash
git add docs/runbooks/vps-state-migration.md scripts/bms_paths.py
git commit -m "docs(deploy): git-only runbook + bms_paths ACTIVE (deploy-debt + split-brain ปิด)"
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main && git rev-parse HEAD"
```
Expected: VPS HEAD == origin/main — **source of truth ตรงกัน 1 เดียว**

- [ ] **Step 4: ลบ app/data backup safety net (หลัง 48h verify ผ่าน)**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "MIGRATION_CUTOFF_TS=\$(cat /opt/bms/data/migration_cutoff_ts.txt) /opt/bms/venv/bin/python /opt/bms/app/scripts/verify_runtime_paths.py && echo '48h OK — ลบ safety net ได้'"
```
Expected: ✅ ผ่าน → ปิด migration. อัปเดต memory `project_deploy_debt` ว่า #1+#2 RESOLVED

### Task 4.3: ถอด dual-read transition + leak-check cron (หลัง 48h verify ผ่าน, v2)

> heal_legacy_state เป็น transition ชั่วคราว — เมื่อ verify 48h แล้วว่าไม่มี writer หลุด ก็ถอดออก (กลับสู่ fail-loud แท้)

- [ ] **Step 1: ลบบรรทัด heal_legacy_state() ที่ service entry (เก็บ log_paths ไว้ได้ — มีประโยชน์ต่อ)**

แก้ทุก service entry: ลบ `bms_paths.heal_legacy_state(*_STATE_FILES)` (คง `log_paths` ไว้)

- [ ] **Step 2: ลบ leak-check cron + commit/push/pull**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "crontab -l 2>/dev/null | grep -v verify_runtime_paths | crontab - && echo CRON_CLEAN"
git add scripts/Sebastian_Enrichment_Worker.py scripts/Sebastian_RSS_Notifier.py scripts/Sebastian_RSS_Scraper.py scripts/health_deadman.py
git commit -m "chore(transition): ถอด heal_legacy_state หลัง 48h verify (กลับ fail-loud แท้)"
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main && echo DONE"
```
Expected: `CRON_CLEAN` + `DONE`

**🔙 ROLLBACK (Phase 4):** revert commits (git history สะอาดแล้ว) + pull VPS. low risk เพราะ state แยกเรียบร้อยแล้ว. (ถ้าถอด heal เร็วไป → revert Task 4.3 commit กลับมาได้)

**✅ EXIT CRITERIA (Phase 4):**
- [ ] runtime-state untrack + gitignore แล้ว (app/data ไม่มี runtime-state)
- [ ] VPS HEAD == origin/main · `git status` clean
- [ ] deploy ทดสอบผ่าน git pull สำเร็จจริง (ทำมาแล้วตั้งแต่ Phase 3.2)
- [ ] heal_legacy_state ถอดแล้ว (หลัง 48h) · leak-check cron ลบแล้ว
- [ ] memory `project_deploy_debt` = #1+#2 RESOLVED

---

## Definition of Done
- [ ] VPS `git rev-parse HEAD` == `origin/main` (source of truth ตรงกัน)
- [ ] `git status` บน VPS = clean (ไม่มี dirty/untracked code)
- [ ] `verify_runtime_paths.py` ผ่านต่อเนื่อง 48h (ไม่มี writer แตะ app/data)
- [ ] log_paths แสดง `RUNTIME_DIR=/opt/bms/data` ทุก service
- [ ] ไม่มี duplicate notification (delivery_log ไม่ spike หลัง cutover)
- [ ] deploy ครั้งถัดไปทำผ่าน `git pull` สำเร็จ (พิสูจน์ Phase 3.1/3.2 แล้ว)
- [ ] memory `project_deploy_debt` อัปเดต: #1 Deploy-Debt + #2 Split-Brain = RESOLVED

## Rollback Philosophy (รวม)
ทุก phase กลับได้: Phase 0-1 = ยังไม่แตะ VPS (revert commit). Phase 2 = restore tarball < 5 นาที. Phase 3-4 = git revert + pull. **safety net หลัก = (ก) timers stopped ตอน migrate, (ข) app/data ไม่ลบจน 48h verify, (ค) full tarball ทั้ง local+VPS.**
