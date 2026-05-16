# Scraper Optimization Research (2026-05-17)

**Goal:** ลดเวลา scrape eGP จาก ~50-60 นาที ให้เร็วที่สุด

---

## 📊 Research Findings

### R1: Hidden Bulk Endpoints
**Result:** ❌ ไม่มี

ทดลอง 19 endpoint patterns บน `process5.gprocurement.go.th/egp-atpj27-service`:
- `getAllProjects`, `exportData`, `bulkSearch`, `listProject`, `getProjects` → ทั้งหมด 404
- `swagger-ui.html`, `v3/api-docs`, `api-docs` → 404 (no public OpenAPI)
- `actuator`, `health` → 404 (Spring endpoints not exposed)
- `robots.txt`, `sitemap.xml` → 404 (no public sitemap)

**Conclusion:** eGP ไม่เปิด bulk endpoint สาธารณะ — ต้องใช้ search API ปกติ

### R2: Pagination Size Test
**Result:** ❌ ไม่สามารถทดสอบได้

ลอง `size=10/20/50/100/200/500/1000` — ทุก response ได้ `text_len=28`
- text_len=28 = `{"validateCfTurnTile":false}` (Cloudflare blocked)
- ปัญหา: direct fetch จาก browser context **ไม่มี valid Turnstile token**
- Token จะ valid ก็ต่อเมื่อ trigger ผ่าน click button (Scraper ทำอยู่)

**Implication:** ไม่สามารถ explore parameter ผ่าน probe ตรงๆ — ต้องผ่าน UI flow

### R3: Other eGP Services
**Result:** ❌ ไม่เจอ shortcut

- `process3.gprocurement.go.th` → 200 (เก่า, redirect ไป process5)
- `getRecentlyUpdated`, `getNewToday` → 404
- No alternative scraping target found

### R4: Open Data API ⭐ **MAJOR FIND**

**พบ Official API** ของรัฐบาลไทย:

**Endpoint:** `https://opend.data.go.th/govspending/cgdcontract`

**Source:** CGDContract — Thailand Government Spending (กรมบัญชีกลาง)

**Spec:**
- Method: GET (REST/JSON)
- Auth: API key (register ที่ https://opend.data.go.th/register_api)
- Params: `year`, `dept_code`, `budget_start`, `budget_end`, `offset`, `keyword`, `winner_tin`
- Summary endpoint: `summary_cgdcontract`

**⚠️ Limitation:** API ให้ข้อมูล **สัญญา (contracts, post-winner)** ไม่ใช่ **ประกาศเชิญชวน (active bids)**
- ดี: สำหรับ awarded_jobs / bid_history / cost benchmarking
- ไม่ดี: ใช้แทน Scraper ไม่ได้ — ไม่มีงานที่กำลังประมูล

**3rd-party:** Apify มี scraper "Thai e-GP Procurement Contracts" ราคา $0.01/1000 results
- ใช้ official Open Data API
- ก็เน้น contracts เหมือนกัน

### R5: G-LEAD Method (จาก previous research)

- ใช้ official source: gprocurement.go.th
- Updates daily (ส่ง email .xlsx)
- ราคา 799 บาท/เดือน — suggest automated overnight scrape

**No special trick** — ก็ scrape เหมือนเรา แต่ overnight + daily delivery

---

## 🎯 Realistic Speedup Opportunities

### Opportunity 1: ⭐⭐⭐⭐⭐ Incremental Scraping (BIGGEST WIN)

**Concept:**
- Cache `latest_publish_date_per_keyword`
- ทุกครั้ง scrape — ดึงแค่ page 1 ก่อน
- ถ้าทุก job ใน page 1 มี `publish_date <= cached_latest` → ไม่มีงานใหม่ → skip keyword
- ถ้ามีงานใหม่ → ดึงต่อจนกว่าจะเจอ cached

**Estimated speedup:**
- Most days: 5-10/28 keywords จะมีงานใหม่ → fetch แค่ 5-10 keywords × 1 page = ~2 นาที
- Versus current: 28 keywords × ~3 min = 85 min
- **Speedup: ~95% (85 min → 2-5 min)**

**Risk:** ต้องการ assumption ว่า eGP sort by publish_date desc — ต้อง verify

### Opportunity 2: ⭐⭐⭐ Parallel Browser Contexts

**Concept:** Run 2-3 Playwright contexts in parallel
- Each handle subset of keywords
- Theoretical 2-3x speedup

**Risk:**
- Cloudflare per-IP rate limit — ทำพร้อมกันอาจโดน 429
- ต้อง different IPs (proxy) → cost + complexity

**Estimated:** 2x speedup, but +50% complexity

### Opportunity 3: ⭐⭐ Use Open Data API for Awarded

**Concept:** CGDContract API → backfill awarded_jobs + bid_history
- ไม่ต้อง scrape สำหรับ awarded
- เร็วกว่า (REST/JSON, no Cloudflare)
- Sanctioned by government

**Limitation:**
- API key registration required
- ไม่ครอบคลุม active bids
- Update frequency อาจ daily (snapshot, not real-time)

**Estimated:** ลด Scraper workload 30-40% (awarded jobs ไม่ต้อง refresh)

### Opportunity 4: ⭐ Keyword Round-Robin

**Concept:** Scrape 10/28 keywords ต่อรอบ rotation
- Round 1: keyword #1-10
- Round 2: keyword #11-20
- Round 3: keyword #21-28
- รอบ rotate ใช้เวลาเฉลี่ย ~30 min แทน 85 min

**Trade-off:** Coverage delay 3 รอบ (3 วัน?) — bad for time-sensitive

**Estimated:** 65% speedup per run, but data 3x stale

---

## 📋 Recommended Implementation Plan

### Phase 1 (NOW): Incremental Scraping
1. เพิ่มไฟล์ `data/scraper_state.json`:
   ```json
   {
     "keyword_states": {
       "ตำบลโพนทอง": {
         "last_scraped_at": "2026-05-17T02:00:00",
         "latest_publish_date": "15/05/2026",
         "latest_jid": "69049xxxxx"
       },
       ...
     }
   }
   ```
2. แก้ `search_keyword_process5()`:
   - Fetch page 1 first
   - Compare items against cached `latest_publish_date`
   - If all items ≤ cached → return (no new)
   - If new found → continue pagination until reach cached
3. Update state after successful scrape

**Expected outcome:** 85 min → 5-10 min on typical days (90%+ speedup)

### Phase 2 (NEXT): Open Data API for Awarded
1. Register API key at opend.data.go.th
2. Build new module `scripts/cgdcontract_api.py`:
   - Pull contracts for our provinces (นครพนม, บึงกาฬ)
   - Match by job_id → update awarded_jobs + bid_history
3. Schedule weekly run (Sunday 02:00)
4. ลด refresh_active_jobs scope (no need to fetch winner for old jobs)

**Expected outcome:**
- awarded_jobs always-fresh winner data
- Less Cloudflare load
- Foundation for Phase B (bid_history) automation

### Phase 3 (LATER): Multi-context Parallelization
- If Phase 1+2 still slow → consider parallel contexts
- Needs proxy IPs (cost: ~$10-50/month)
- Justification: only if scrape needs to be < 5 minutes

---

## ⚠️ Cloudflare Reality

**eGP ใช้ Cloudflare Turnstile** สำหรับป้องกัน bots:
- Direct API calls (without browser session) → blocked
- Must go through Playwright with valid Turnstile token
- Tokens auto-validate per browser context (cookie-based)

**Implication:**
- Cannot bypass Playwright requirement
- Cannot scrape from server-side without browser
- ที่ G-LEAD ทำได้ = ก็ใช้ Playwright/Selenium/Puppeteer เหมือนกัน

---

## 🔬 What I Couldn't Verify (limits of this research)

1. **Max page size** — couldn't test (Cloudflare blocked probes)
   - Worth trying: trigger search via UI → captured URL with `size=100` → see if works
2. **Sort order** — Scraper assumes sorted by date but didn't verify
   - Critical for incremental to work — must verify before Phase 1
3. **Open Data API depth** — couldn't reach documentation URL
   - Need API key first → register → explore

---

## 💡 Implementation Priority

1. **TODAY**: Implement Phase 1 (incremental) — verify sort assumption first
2. **THIS WEEK**: Register Open Data API key → test CGDContract
3. **LATER**: Phase 2 (CGDContract integration) once Phase 1 stable
4. **DEFER**: Phase 3 (parallel) unless absolutely necessary
