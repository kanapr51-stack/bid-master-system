# VPS Runtime-State Migration + Git Deploy-Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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
4. ทุก phase มี rollback ที่กลับได้ใน < 5 นาที
5. **Definition of Done ของ migration ไม่ใช่ "ทำเสร็จ" แต่คือ "verify 48h ว่าไม่มี writer หลุดไป app/data"** (failure ประเภทนี้ surface ทีหลัง)

---

## File Structure

**สร้างใหม่:**
- `docs/runbooks/vps-state-migration.md` — runbook + rollback log (เก็บ output แต่ละ phase)
- `scripts/verify_runtime_paths.py` — verify ไม่มี runtime-state file ตกค้างใน app/data (ใช้ Phase 3 + cron heartbeat)

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

- [ ] **Step 2: Snapshot สถานะ git ปัจจุบันของ VPS (เป็นหลักฐาน rollback)**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && git rev-parse HEAD > /tmp/vps_head_before.txt && \
   git status --short > /tmp/vps_status_before.txt && \
   git stash list > /tmp/vps_stash_before.txt; cat /tmp/vps_head_before.txt"
```
Expected: พิมพ์ `f5311f7...`

### Task 0.2: Full backup (code + data + db + env + systemd)

- [ ] **Step 1: หยุด timers (freeze runtime writes)**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "sudo systemctl stop bms-enrichment-worker.timer bms-rss-notifier.timer \
   bms-line-sender.timer bms-province-discovery.timer bms-province-discovery-full-bkg.timer \
   bms-canary.timer bms-deadman.timer bms-shadow-audit.timer bms-daily-digest.timer \
   bms-daily-user-summary.timer && echo STOPPED"
```
Expected: `STOPPED`. (bms-api.service / bms-tunnel.service ปล่อยรันได้ — read-mostly; ถ้าต้องการเข้มสุดให้ stop ด้วย)

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

**🔙 ROLLBACK (Phase 0):** ถ้าอะไรพลาด → `systemctl start` timers กลับ. ยังไม่แตะ state/git เลย ปลอดภัย 100%.

---

## PHASE 1 — Wire runtime-state ผ่าน bms_paths (code-only, ใน repo local)

> ทำบน local repo → commit → push GitHub. **ยังไม่แตะ VPS.** โค้ดนี้จะขึ้น VPS พร้อม git sync ใน Phase 2 (แก้ chicken-and-egg: ไม่ต้อง scp routing code แยก).

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

**🔙 ROLLBACK (Phase 1):** เป็น commit ใน repo local/GitHub ล้วน — `git revert` ได้. **VPS ยังไม่ถูกแตะ** จึงไม่มีผลกับ production.

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

- [ ] **Step 3: verify counts (rss_queue/seen ไม่ลดลง)**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "python3 -c \"import json; print('queue:', len(json.load(open('/opt/bms/data/rss_queue.json')))); print('seen:', len(json.load(open('/opt/bms/data/rss_seen_ids.json'))))\""
```
Expected: ตัวเลข > 0 และ ≥ ค่าก่อนหน้า (ไม่หาย)

### Task 2.2: Reconcile code — diff VPS worktree vs origin/c077938 (หา hotfix เฉพาะ VPS)

- [ ] **Step 1: fetch origin บน VPS แล้ว diff worktree ปัจจุบัน vs origin/main ทีละไฟล์**

Run:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "cd /opt/bms/app && git fetch origin 2>&1 | tail -1 && \
   for f in \$(git diff --name-only HEAD -- 'scripts/*.py'); do \
     n=\$(git diff --no-index --stat /dev/null /dev/null 2>/dev/null; git diff origin/main -- \$f | wc -l); \
     echo \"\$f : diff-vs-origin \$n บรรทัด\"; \
   done"
```
Expected: ตาราง diff. **diff-vs-origin = 0 → VPS worktree == origin (scp มาตรงแล้ว, take origin ปลอดภัย). > 0 → มี logic ต่าง ต้องดูก่อน**

- [ ] **Step 2: ไฟล์ที่ diff > 0 — ดู diff จริง ตัดสิน A/B/C**

Run (ต่อไฟล์ที่ diff>0): `ssh ... "cd /opt/bms/app && git diff origin/main -- scripts/<file>.py"`
จดใน runbook: **กลุ่ม A** (==origin, take origin) / **กลุ่ม B** (มี logic จริงไม่อยู่ origin → cherry-pick กลับ local, commit, push, fetch ใหม่) / **กลุ่ม C** (hotfix ชั่วคราว/ขยะ → ทิ้ง)
**⚠️ ถ้าเจอกลุ่ม B → หยุด, กลับไปทำใน local repo, push, แล้วเริ่ม Task 2.2 ใหม่** (กัน commit ขยะบน VPS)

- [ ] **Step 3: ยืนยันไม่มีกลุ่ม B ค้าง (ทุก diff = A หรือ C)**

Expected: confirm ใน runbook ว่าจัดการ B ครบ — เหลือแต่ A/C ก่อนไป Task 2.3

### Task 2.3: Git sync VPS → origin/main (atomic, ตอนนี้ปลอดภัยเพราะ state ออกนอก app/data แล้ว)

- [ ] **Step 1: hard reset app → origin/main + clean untracked code (เก็บ data/ ไว้)**

Run:
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

**🔙 ROLLBACK (Phase 2):** restore จาก backup: `tar xzf /opt/bms/backups/migration_<TS>/app.tgz -C /opt/bms` + `data.tgz` → `systemctl start` timers. กลับสู่สภาพก่อน migrate ทุกอย่าง (< 5 นาที).

---

## PHASE 3 — Verify (startup instrumentation + 48h watch) ⭐ สำคัญสุด

> ตอบโจทย์ "failure surface ทีหลัง" — ต้องพิสูจน์ว่าไม่มี writer/reader ตกค้างชี้ app/data

### Task 3.1: เพิ่ม startup log_paths ใน service หลัก

**Files:** Modify `scripts/Sebastian_Enrichment_Worker.py`, `scripts/Sebastian_RSS_Notifier.py`, `scripts/health_deadman.py` (เพิ่มที่ต้น main)

- [ ] **Step 1: เพิ่ม 1 บรรทัดที่ entry แต่ละ service**
```python
bms_paths.log_paths("rss_queue.json", "rss_seen_ids.json", "api_ingestion_state.json", "resolve_heartbeat.json")
```
→ stderr จะพิมพ์ `[bms_paths] RUNTIME_DIR=/opt/bms/data` ทุกรอบ (verify dir เดียวกันจริง)

- [ ] **Step 2: commit + push + (sync VPS ด้วย git pull — ตอนนี้ทำได้แล้ว!)**
```bash
git add scripts/Sebastian_Enrichment_Worker.py scripts/Sebastian_RSS_Notifier.py scripts/health_deadman.py
git commit -m "feat(observability): log_paths startup instrumentation (verify single runtime dir)"
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main && git rev-parse HEAD"
```
Expected: VPS HEAD เลื่อนตาม origin (**git pull ทำงานแล้ว = deploy debt หาย**)

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

- [ ] **Step 2: commit + push + pull VPS**
```bash
git add scripts/verify_runtime_paths.py
git commit -m "feat(verify): runtime-path leak detector (48h watch)"
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main"
```

- [ ] **Step 3: บันทึก cutoff timestamp + restart timers**
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 \
  "date +%s > /opt/bms/data/migration_cutoff_ts.txt && \
   sudo systemctl start bms-enrichment-worker.timer bms-rss-notifier.timer bms-line-sender.timer \
   bms-province-discovery.timer bms-canary.timer bms-deadman.timer bms-shadow-audit.timer \
   bms-daily-digest.timer bms-daily-user-summary.timer bms-province-discovery-full-bkg.timer && echo STARTED"
```
Expected: `STARTED`

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

**🔙 ROLLBACK (Phase 3):** ถ้า verify ❌ หรือ sent spike → `systemctl stop` timers, restore data.tgz backup, `git reset` กลับ commit ก่อน Phase 3, start timers. สอบ writer ที่หลุดใน local ก่อนลองใหม่.

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

**🔙 ROLLBACK (Phase 4):** revert commits (git history สะอาดแล้ว) + pull VPS. low risk เพราะ state แยกเรียบร้อยแล้ว.

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
