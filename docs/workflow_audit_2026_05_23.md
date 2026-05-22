# Workflow Audit — 2026-05-23 (สำหรับคุณกัญจน์ดูตอนตื่น)

ผลการตรวจ workflow ทั้ง 4 ตัวอย่างละเอียด — **ยังไม่แก้ จดไว้ก่อน** ตามที่สั่ง

Audit เริ่ม: 04:50 ICT 2026-05-23

Severity:
- 🔴 **HIGH** — กระทบ SaaS/customer ทันที
- 🟡 **MEDIUM** — กระทบ data quality ระยะกลาง
- 🟢 **LOW** — code smell, dead code, optimization

---

## 🎯 TL;DR — ลำดับความสำคัญ (HIGH issues ก่อน)

| # | Issue | Workflow | Impact |
|---|---|---|---|
| 1.1 | queue_for_lookup ลืม anounce_type | rss_scraper | P0 items จาก GHA cron ไม่เข้า pre_tor sheet |
| 1.2 | --global ignore --stage | rss_scraper | B0 global poll ไม่ทำงาน |
| 4.1 | refresh --expand timeout (11K vs 30 min) | pipeline_daily | **Pipeline daily fail ทุกวันจากนี้** |
| 4.2 | snapshot ไม่ upload Vercel Blob | pipeline_daily | Dashboard แสดงข้อมูลเก่า |
| 2.1 | gentle_scan poll D0 อย่างเดียว | gentle_scan | dept ที่มีแต่ W0/P0 หายไป |
| 2.2 | catalog ครบแล้ว → gentle_scan no-op | gentle_scan | Discovery หยุดทำงานถาวร |
| 3.1 | catalog_discovery default d0 mode no-op | catalog_discovery | Weekly run ไม่ทำอะไร |
| 4.3 | LINE Notify ปิดไว้ | pipeline_daily | SaaS pilot ไม่พร้อม |

**ที่กระทบทันที (พรุ่งนี้เช้า 06:00):**
- **Pipeline daily จะ fail แน่นอน** (refresh --expand ใช้เวลา 7+ ชม > 30 min budget)
- Dashboard ข้อมูลเก่า (snapshot ไม่ upload)

---

## 1️⃣ rss_scraper.yml + Sebastian_RSS_Scraper.py + refresh_active_jobs.py

### 🔴 ISSUE 1.1 (HIGH) — `queue_for_lookup` ลืม anounce_type → P0 items หาย

**ที่ไหน:** `scripts/Sebastian_RSS_Scraper.py:283-313` (`queue_for_lookup`)

**ปัญหา:** RSS items มี field `anounceType` (camelCase) จาก `fetch_dept` line 178
แต่ `queue_for_lookup` คัดลอกแค่ projectId/title/deptId/pubDate/link → **ลืม anounceType**

```python
# line 300-308
queue.append({
    "projectId": pid,
    "title": item.get("title", ""),
    "deptId": item.get("deptId", ""),
    "pubDate": item.get("pubDate", ""),
    "link": item.get("link", ""),
    "queued_at": now,
    "source": "rss",
    # ❌ ไม่มี anounce_type !
})
```

**ผลกระทบ:** `refresh_active_jobs.py:361` อ่าน `q_item.get("anounce_type", "")` ได้ค่าว่าง
- P0 items จาก GHA cron → getProjectDetail ล้มเหลว (P0 ไม่มีใน DB) → q_atype="" → **fallback ไม่ทำงาน → ทิ้งงาน**
- ผลคือ pre_tor sheet จะไม่เพิ่มจาก GHA cron แม้ poll P0 ได้

**Fix:** เพิ่ม `"anounce_type": item.get("anounceType", "")` ใน queue dict

### 🔴 ISSUE 1.2 (HIGH) — `--global --stage B0` ไม่ทำงาน (silent ignore)

**ที่ไหน:** `scripts/Sebastian_RSS_Scraper.py:882`
```python
result = poll_global_rss(anounce_types=["D0", "P0", "W0"], queue_new=args.queue)
```
**Hardcoded** `["D0", "P0", "W0"]` — ไม่ดู `args.stage`

**ผลกระทบ:** `.github/workflows/rss_scraper.yml:39` รัน:
```yaml
python scripts/Sebastian_RSS_Scraper.py --stage B0 --global --queue || true
```
ตั้งใจให้ poll B0 globally → จริงๆ poll D0+P0+W0 ซ้ำ → **B0 ไม่ได้ scan globally เลย**

**Fix:** ใน main(), ถ้ามี --stage + --global ให้ override list เป็น [args.stage]

### 🟡 ISSUE 1.3 (MEDIUM) — step name lies

**ที่ไหน:** `.github/workflows/rss_scraper.yml:30`
```yaml
- name: Global RSS poll (D0+P0+W0+B0 all-Thailand)
```
แต่จริงๆ ทำได้แค่ D0+P0+W0 (B0 fail ตาม Issue 1.2) — confusing สำหรับคนที่ดู GHA log

### 🟡 ISSUE 1.4 (MEDIUM) — refresh ไม่ batch + ใช้เวลายาว

**ที่ไหน:** `refresh_active_jobs.py` step สุดท้าย timeout 10 min
- หากเจอ batch 2K+ items (เหมือนคืน W0) จะใช้เวลาเกิน 10 min → step fail
- ตอน scan ทั้งประเทศคืนนี้ใช้ ~10 min @ 5 workers สำหรับ 2.3K items → cut close

**Fix idea:** Add `--max-items N` flag จำกัด 200-500 ต่อ run, queue ที่เหลือไว้รอบหน้า

### 🟢 ISSUE 1.5 (LOW) — TARGET_KEYWORDS dead code

**ที่ไหน:** `scripts/Sebastian_RSS_Scraper.py:329-330`
```python
TARGET_KEYWORDS = ["นครพนม", "บึงกาฬ", "บ้านแพง", "บึงโขงหลง", ...]
```
ตกค้างจากช่วงก่อนเปลี่ยนเป็น SaaS nationwide — ใช้แค่ใน probe_all_depts ตอน save_all_w0=False ซึ่งไม่ใช่ default path

**Fix:** เก็บไว้สำหรับ catalog_discovery `--probe-w1` (target area discovery) หรือลบทิ้งถ้าไม่ใช้แล้ว

### 🟢 ISSUE 1.6 (LOW) — walrus operator ใน _process_one ดูสับสน

**ที่ไหน:** `refresh_active_jobs.py:133`
```python
if ps_raw := fields.get("project_status_raw", ""):
```
- ใช้ walrus operator
- ตัวแปร `ps_raw` ถูก define ใน if-block ก่อนหน้า (line 117) อยู่แล้ว — overlap scope
- Logic ถูก แต่อ่านยาก — refactor ทีหลังได้

### ✅ ที่ทำงานถูกต้อง
- 429 retry logic (เพิ่งเพิ่ม)
- Per-atype queue file ใน scan_all_depts.py
- Negative cache (skip 7872/9999 depts → save time)
- Blacklist mechanism (เพิ่งเพิ่ม — รอ verify จาก GHA run)
- Workflow split D0/B0/P0 (เพิ่งเพิ่ม)
- Winner fetch ใน new_jids path (เพิ่งเพิ่ม)

---

## 2️⃣ gentle_scan_morning.yml + gentle_scan_egp.py

### 🟡 ISSUE 2.1 (MEDIUM) — gentle_scan โพล D0 อย่างเดียว

**ที่ไหน:** `scripts/gentle_scan_egp.py:77`
```python
r = session.get(RSS_URL, params={"deptId": dept_id}, timeout=12)
```
ไม่ส่ง `anounceType` → eGP default = D0

**ผลกระทบ:** Dept ที่มีงานแต่อยู่ใน stage W0/B0/P0 อย่างเดียว (ไม่มี D0) → **ไม่ถูกค้นพบ** เข้า catalog
- ผลต่อ SaaS: dept ที่ post P0 (planning) เท่านั้น (ไม่เคย D0) จะหายไป
- คาดผลกระทบ: 5-15% ของ active depts

**Fix:** เพิ่ม `params["anounceType"] = "D0"` หรือ probe หลาย stage (D0+P0)

### 🟡 ISSUE 2.2 (MEDIUM) — catalog "ครบแล้ว" → gentle_scan exit ทันที

**ที่ไหน:** `scripts/gentle_scan_egp.py:111-126`
```python
pending = [n for n in range(1, SCAN_END + 1) if n not in known_ids]
if not pending:
    log("✅ Catalog already complete!")
    return
```

**ปัญหา:** ตอนนี้ catalog เต็ม 9999 entries แล้ว (จาก scan_all_depts.py + Sebastian_RSS_Scraper.py probe-all) → gentle_scan จะ exit ทันทีทุกครั้งที่รัน
- ไม่มี **re-scan logic** สำหรับ dept ที่เคย scan = ว่าง (ไม่ใช่ทุก dept ที่ว่างวันนี้ จะว่างตลอดไป)
- Negative cache (3 วัน) มีใน Sebastian_RSS_Scraper.py แต่ **gentle_scan ไม่มี**

**ผลกระทบ:** Gentle scan workflow 03:00 ทุกวันจะ no-op หลังจากครั้งแรกที่ catalog เต็ม

**Fix:** เพิ่ม logic เหมือน Sebastian_RSS_Scraper.py — ถ้า scanned_at > N วัน + item_count=0 → re-probe

### 🟢 ISSUE 2.3 (LOW) — parse_items regex ไม่รองรับ P-prefixed projectIds

**ที่ไหน:** `scripts/gentle_scan_egp.py:68`
```python
pid_match = re.search(r"\b(\d{11,12})\b", item["description"])
```
ไม่ match `P69050012229` (P0 stage)

**ผลกระทบ:** ต่ำ — script นี้ใช้แค่ `len(items)` สำหรับ catalog count ไม่ได้ใช้ projectIds ตรงๆ ในการ routing

**Fix:** เปลี่ยน regex เป็น `r"(P?\d{11,12})"` เพื่อความ consistent

### 🟢 ISSUE 2.4 (LOW) — recent_results เก็บ "timeout" สำหรับ non-200 ทั้งหมด

**ที่ไหน:** `scripts/gentle_scan_egp.py:166-167`
```python
else:
    recent_results.append("timeout")
```
HTTP 429, 500, network error ทั้งหมดถูก counted เป็น "timeout" → metric สับสน

**ผลกระทบ:** Logic adaptive cooldown ยังทำงานถูก (มอง total non-ok rate) แต่ log สับสน

### ✅ ที่ทำงานถูกต้อง
- Adaptive cooldown (timeout > 30% → 120s pause)
- Safe-stop (timeout > 70% → break)
- Resume-aware (skip catalog entries)
- Periodic save ทุก 50 entries
- Shuffle deptIds (ไม่ hammer sequential ranges)
- max-minutes flag honored (75 min ใน GHA)

---

## 3️⃣ catalog_discovery.yml (default mode = "d0")

### 🟡 ISSUE 3.1 (MEDIUM) — Default mode "d0" no-op หลังจาก catalog เต็มแล้ว

**ที่ไหน:** `scripts/Sebastian_RSS_Scraper.py:374`
```python
if not total:
    log("✅ probe-all: catalog ครบแล้ว (ไม่มี ID ที่ยังไม่ได้ probe)")
    return {"found": 0, "target_area": [], "total_probed": 0}
```

**ปัญหา:** Catalog ตอนนี้มี 9999 entries (full DEPT_ID_RANGE) → probe-all default mode ไม่มี ID ใหม่ที่จะ probe → no-op
- Workflow รันทุกพุธ 01:00 → log "ครบแล้ว" → exit
- **Discovery หยุดทำงานถาวร** (ถ้า DEPT_ID_RANGE จำกัด 1-9999)

**ผลกระทบ:** ไม่ค้นพบ activity เปลี่ยนแปลงรายสัปดาห์ใน dept ที่เคย empty
- เช่น dept 5000 เคย empty ก่อน → วันนี้เริ่ม post งาน → catalog ไม่ได้ update

**Fix idea:** เพิ่ม `--probe-all --force-rescan` ที่ re-probe stale entries (เหมือน RSS scraper's negative cache 3 days)

### 🟢 ISSUE 3.2 (LOW) — workflow ไม่มี per-step timeout

**ที่ไหน:** `.github/workflows/catalog_discovery.yml:31`
- Job timeout-minutes: 90
- ไม่มี step-level timeout

**ผลกระทบ:** ถ้า probe_all hang/slow → ใช้ทั้ง 90 min ของ job
- Worst case: 9999 depts × workers=20 × 5s timeout = ~2500s = 42 min (ปกติ) แต่ถ้า server ห่วยทั้ง 9999 อาจถึง 90 min

**Fix:** เพิ่ม step timeout 60 min

### 🟢 ISSUE 3.3 (LOW) — w1 mode ใช้ TARGET_KEYWORDS (old province filter)

**ที่ไหน:** `scripts/Sebastian_RSS_Scraper.py:409`
```python
title_blob = " ".join(it.get("title", "") for it in items)
is_target = any(kw in title_blob for kw in TARGET_KEYWORDS)
```
ตกค้างจากช่วง pilot นครพนม/บึงกาฬ — ใช้กรอง target_deptids.json

**ผลกระทบ:** SaaS nationwide ไม่ได้ใช้ keyword filter → mode w1 จะเก็บแค่ 2 จังหวัดนี้
- Phase 2 pilot นครพนม จะใช้ — keep ไว้

### 🟢 ISSUE 3.4 (LOW) — gentle_scan mode duplicates gentle_scan_morning.yml

**ที่ไหน:** `.github/workflows/catalog_discovery.yml:54`
```bash
elif [ "$MODE" = "gentle_scan" ]; then
  python scripts/gentle_scan_egp.py --max-minutes 75
```
รัน script เดียวกับ gentle_scan_morning.yml ที่รันทุก 03:00

**ผลกระทบ:** Redundant — แค่ให้ manual trigger ได้ ไม่เสียหาย

### ✅ ที่ทำงานถูกต้อง
- Mode dispatch (workflow_dispatch options)
- d0_repair mode (probe-429) ที่ workers=8, delay=0.3s — gentle
- w0_full mode สร้าง egp_w0_catalog.json สำหรับ post-process
- force_all=True ใน w1/w0_full ignores catalog → fresh data

---

## 4️⃣ pipeline_daily.yml + 5 scripts

### 🔴 ISSUE 4.1 (HIGH) — `refresh --expand` จะ timeout ทุกครั้งจากนี้

**ที่ไหน:** `refresh_active_jobs.py:254-266` (--expand mode)
```python
for sn in ("active_bidding", "tor_review", "pending_award"):
    ws = open_sheet(SPREADSHEET_ID, sn)
    ...
```

**สถิติปัจจุบัน:**
- active_bidding: 276
- tor_review: 178
- pending_award: **10,567**
- รวม: **~11,021 jobs**

**Throughput จริง:** ~25 items/min @ workers=5 (จาก D0 refresh เมื่อคืน 240 items ใน 8 min)
**Time needed:** 11,021 / 25 = **440 นาที = 7.3 ชม.**
**Job timeout:** 30 นาที → **DEAD ON ARRIVAL**

**หลักฐาน:** GHA run ของ 2026-05-22 06:00 = **30m17s cancelled** ✗

**Fix idea:**
- เพิ่ม `--limit N` ใน workflow (e.g., 300/run) + rotate ผ่าน sheets
- หรือ split เป็น sub-jobs ทำคนละ sheet

### 🔴 ISSUE 4.2 (HIGH) — Dashboard snapshot generate แต่ไม่ upload

**ที่ไหน:** `.github/workflows/pipeline_daily.yml:58-59`
```yaml
echo "=== Step 5: Dashboard snapshot ==="
python scripts/dashboard_extractor.py || true
```

**ปัญหา:** dashboard_extractor.py สร้าง `dashboard/web/public/snapshot.json` บน GHA runner แต่:
- ❌ ไม่ commit กลับเข้า repo (commit step skip dashboard/ files)
- ❌ ไม่ upload ไป Vercel Blob ผ่าน `Sebastian_Upload_Snapshot.py`

**ผลกระทบ:** dashboard.bid-master.com (Vercel) แสดงข้อมูลเก่า/ไม่เปลี่ยน
- ลูกค้า/คุณกัญจน์เปิดดู dashboard → numbers ไม่ตรงกับ Sheet

**Fix:** เพิ่ม step `python scripts/Sebastian_Upload_Snapshot.py` หลัง dashboard_extractor

### 🟡 ISSUE 4.3 (MEDIUM) — LINE Notify ถูกปิด → SaaS pilot ไม่พร้อม

**ที่ไหน:** `.github/workflows/pipeline_daily.yml:55-56`
```bash
echo "=== Step 4: LINE Notify (ปิดชั่วคราว — รอ province filter สำหรับ SaaS) ==="
# python scripts/Sebastian_LINE_Notify.py || true
```

**ผลกระทบ:** ลูกค้า SaaS Phase 2 (นครพนม) ไม่ได้รับ alert งานใหม่ → ไม่มี product จริง

**Pre-req ก่อน enable:**
1. Multi-tenant province filter (filter งานตามจังหวัดของลูกค้าแต่ละคน)
2. Per-customer subscription state (LINE userId/groupId แยกตามลูกค้า)
3. Rate limiting (กัน LINE API flood)

### 🟡 ISSUE 4.4 (MEDIUM) — patch_deadlines.py sequential

**ที่ไหน:** `scripts/patch_deadlines.py:197`
```python
for i, (row, template_id) in enumerate(has_template, 1):
    pdf_bytes = download_pdf(template_id)
```
ไม่ใช้ ThreadPoolExecutor → ดาวน์โหลด PDF ทีละไฟล์

**ผลกระทบ:** ถ้ามี 100 jobs ต้อง patch → 100 × ~3s = 5 นาที (พอ)
แต่ถ้า 500+ → กิน budget ของ pipeline

**Fix:** parallel ด้วย workers=3 (PDF เป็นไฟล์ใหญ่ ไม่ควรเยอะ)

### 🟢 ISSUE 4.5 (LOW) — workflow commit step ไม่รวม dashboard files

**ที่ไหน:** `.github/workflows/pipeline_daily.yml:64-68`
```yaml
git add data/winner_cache_bootstrap.json \
        data/transitions_latest.json \
        data/sheet_snapshot.json \
        data/scrape_baseline.json || true
```

ขาด: `dashboard/web/public/snapshot.json`, `dashboard/data/snapshot.json`

**ผลกระทบ:** Vercel preview deployment ที่ใช้ bundled snapshot (fallback) จะเก่า

**Fix:** ตัดสินใจ — ถ้าจะใช้ Vercel Blob (ISSUE 4.2 fix) → ไม่ต้อง commit, ถ้าใช้ bundled → commit

### ✅ ที่ทำงานถูกต้อง
- Step 1-5 chain (refresh → patch → classify → notify → snapshot)
- set -e ป้องกัน silent failure
- || true ใน step ที่ไม่ critical (patch, notify, snapshot)
- ENV vars ครบ (Discord, LINE, Anthropic, Vercel)
- Cron 06:00 ICT ถูกต้อง (23:00 UTC)

---

## 5️⃣ Cross-cutting Issues (ข้าม workflow)

### 🟡 ISSUE X.1 (MEDIUM) — Concurrent writes ที่ rss_queue.json

**ที่ไหน:** ทุก workflow + scan_all_depts ทำ write ที่ `data/rss_queue.json`
- rss_scraper.yml: ทุก :22 :52 — queue items + remove processed
- pipeline_daily.yml: 06:00 — refresh consume queue (เคย happen ในเดือนนี้)
- gentle_scan: ไม่เขียน (read-only ต่อ catalog)
- scan_all_depts.py: เขียน per-atype queue file (ดี ไม่ conflict)

**ปัญหา:** ถ้า rss_scraper :22 รันใน window เดียวกับ pipeline_daily → race condition
- Pipeline อาจ remove items ที่ rss_scraper เพิ่งเพิ่ม
- ไม่มี file locking

**ผลกระทบ:** ต่ำ — runtime overlap น้อยมาก (ทั้งคู่เร็ว) แต่เป็น latent bug

**Fix idea:** atomic write + retry หรือ Redis queue (Phase 3 migration)

### 🟡 ISSUE X.2 (MEDIUM) — Git push conflicts ที่ main

**ที่ไหน:** ทุก workflow push commit ขึ้น main
- rss_scraper: chore: rss catalog [skip ci]
- gentle_scan: chore: gentle_scan [skip ci]
- catalog_discovery: chore: catalog probe [skip ci]
- pipeline_daily: chore: auto-update state files [skip ci]

**ปัญหา:** ถ้า 2 workflows เสร็จใกล้กัน → push เดี๋ยวก็ rejected
- `git push || true` ทำให้ไม่ crash แต่ commit หาย

**หลักฐาน:** วันนี้เราเจอเอง — rebase ก่อน push หลายรอบเพราะ GHA cron ชน

**Fix idea:** `git pull --rebase --autostash` ก่อน push หรือ retry loop

### 🟢 ISSUE X.3 (LOW) — Secrets เหมือนกันใน 4 workflows

**ที่ไหน:** ENV setup ใน rss_scraper.yml, pipeline_daily.yml (gentle/catalog ไม่ใช้ secrets)

**ผลกระทบ:** ต่ำ — แค่ duplicate code ใน yml. ถ้าจะ rotate secret ต้องแก้ทั้ง 2 ไฟล์

**Fix idea:** ใช้ GitHub Reusable Workflows + composite actions

### 🟢 ISSUE X.4 (LOW) — ไม่มี monitoring/alerting เมื่อ workflow fail

**สังเกต:** workflow fail หลายรอบที่ผ่านมา (วันนี้ 11 ครั้ง RSS, 1 ครั้ง pipeline) แต่ไม่มี Discord alert → คุณกัญจน์ไม่รู้

**Fix idea:** เพิ่ม step `if: failure()` → ส่ง Discord notify

---

## 6️⃣ สิ่งที่ Audit ไม่ครอบคลุม (จงใจ — เพราะ scope)

- **Sebastian_Pipeline.py** — orchestrator alternative; pipeline_daily.yml ไม่ได้ใช้ตัวนี้
- **Sebastian_Classifier.py logic** — ตรวจ flow แต่ไม่ deep-test classification rules
- **process5_http_client.py** — Cloudflare workaround code
- **Sebastian_Discord_Notify.py / LINE_Notify.py** — แค่ smoke check
- **dashboard/web/*** — Next.js frontend (มี AGENTS.md เตือนว่าไม่ใช่ standard Next.js)
- **GHA secret values** — ไม่ตรวจว่า rotate/expire เมื่อไหร่

---

## 7️⃣ คำแนะนำลำดับการแก้ (ถ้าจะแก้พรุ่งนี้)

### Tier 1 — ก่อน 06:00 (กัน pipeline daily ล้ม)
1. **ISSUE 4.1**: เพิ่ม `--limit 300` ใน workflow (or rotate sheets)

### Tier 2 — เร่ง (ภายในวัน)
2. **ISSUE 1.1**: เพิ่ม `anounce_type` ใน queue_for_lookup() — fix P0 leak
3. **ISSUE 4.2**: เพิ่ม Sebastian_Upload_Snapshot.py step
4. **ISSUE 1.2**: fix --global honor --stage

### Tier 3 — ช้า (ภายในอาทิตย์)
5. **ISSUE 2.2 + 3.1**: re-scan stale catalog entries (gentle_scan + catalog_discovery)
6. **ISSUE 2.1**: gentle_scan รวม P0 ด้วย
7. **ISSUE X.2**: rebase ก่อน push

### Tier 4 — ทีหลัง (ก่อน SaaS launch)
8. **ISSUE 4.3**: LINE Notify per-province filter + re-enable

---

## 🧾 Closing note

Audit นี้ใช้เวลาประมาณ 45 นาที (04:50 — 05:35 ICT)
อ่านโค้ดจริง 8 ไฟล์: 4 yml + 4 .py
อ้างอิงหลักฐานจาก: gh run list, real catalog state, sheet counts ปัจจุบัน

ไม่ได้แก้อะไรในโค้ดเลย — ตามที่คุณกัญจน์สั่ง

**ลายเซ็น:** Claude session 2026-05-22→23 ก่อนนอน


