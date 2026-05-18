# RSS-First Full Replacement Research (2026-05-19)

## 🎯 Goal

หา API ทดแทน Chrome-based calls สำหรับ:
- getProjectDetail (Step 3 REFRESH)
- getProcureResult (Step 3 REFRESH + winners)
- PDF deadline parsing (Step 4 PATCH_DEADLINES)
- Budget, province, district extraction

→ ผลคือ **ทั้ง pipeline สามารถรันได้โดยไม่ต้องใช้ Chrome** = scale ได้ทั้งประเทศ

## 🔥 4 Discoveries

### Discovery #1: RSS supports ALL stages (เมื่อวาน — 2026-05-18)
- `anounceType` typo bypass: P0/B0/D0/D1/W0/W1/W2/15
- ดูครบใน `rss_full_coverage_discovery.md`

### Discovery #2: getProjectDetail via direct HTTP ✅
- URL: `https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement/getProjectDetail?projectId=X`
- Headers: User-Agent (Mozilla) + Referer (process5)
- Returns JSON: projectId, **deptSubName**, methodId, typeId, stepId, flowId, projectStatus, announceType, isSect7
- **NO Chrome required!**

### Discovery #3: getProcureResult = **bid_history goldmine** ✅
- URL: `https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement/getProcureResult?projectId=X`
- Returns JSON: projectCost, deliverDay, **procureResultList** (ALL bidders)
- Each bidder: receiveNameTh, receiveTin, **priceProposal**, resultFlag (P/N), priceAgree (only winner), scoreTypeId (SME), jointVentureAndConsortiumsResponseList
- **NO Chrome required!**

Example response (project 68119564509):
```json
{
  "procureResultList": [{
    "considerDesc": "โครงการก่อสร้างถนนคอนกรีต...",
    "procureResultDataResponse": [
      {"receiveNameTh": "ห้างหุ้นส่วนจำกัด เซ็นจูรี่บึงกาฬ", "priceProposal": 7659000.0, "resultFlag": "P", "priceAgree": 7659000.0, "scoreTypeId": "SME"},
      {"receiveNameTh": "ห้างหุ้นส่วนจำกัด ดี ดี คอนสตรัคชั่น1980", "priceProposal": 6900000.0, "resultFlag": "N", "priceAgree": null},
      {"receiveNameTh": "ห้างหุ้นส่วนจำกัด ธนภูมิคอนกรีต", "priceProposal": 6285000.0, "resultFlag": "N"},
      {"receiveNameTh": "ห้างหุ้นส่วนจำกัด ปุริวัฒน์", "priceProposal": 5670000.0, "resultFlag": "N"},
      {"receiveNameTh": "ห้างหุ้นส่วนจำกัด อุดรรุ่งนิรันดร์", "priceProposal": 6250000.0, "resultFlag": "N"},
      {"receiveNameTh": "ห้างหุ้นส่วนจำกัด เอส.เอ็ม.ซี การโยธา", "priceProposal": 7700000.0, "resultFlag": "P", "scoreTypeId": "SME"}
    ]
  }]
}
```

→ **ALL 6 bidders, prices, pass/fail flags, SME info** — perfect for competitor analysis!

### Discovery #4: PDF download via direct HTTP ✅
- URL: `https://process5.gprocurement.go.th/egp-template-service/dwnt/view-pdf-file?templateId={UUID}`
- templateId comes from RSS `<link>` field
- Headers: Mozilla UA + Referer
- Returns: PDF (application/pdf, ~100KB)
- **NO Chrome required!**

PDF contains ALL missing fields:
- **ราคากลาง** (budget): ๑,๖๓๘,๓๐๓.๗๕ บาท
- **วันยื่นข้อเสนอ** (deadline): ๒๐ พฤษภาคม ๒๕๖๙
- **วันประกาศ** (publish): ๑๑ พฤษภาคม ๒๕๖๙
- **ชื่อหน่วยงาน** (dept): สำนักงานปลัดสำนักนายกรัฐมนตรี
- ที่อยู่หน่วยงาน (province/district)
- เอกสารแนบเลขที่
- เงื่อนไขผู้เข้าร่วม

Parse with `pdfplumber` (Python — already installed):
```python
import io, pdfplumber, requests
H = {'User-Agent': 'Mozilla/5.0...', 'Referer': 'https://process5.gprocurement.go.th/'}
r = requests.get(pdf_url, headers=H, timeout=30)
with pdfplumber.open(io.BytesIO(r.content)) as pdf:
    text = pdf.pages[0].extract_text()
    # extract deadline, budget via regex
```

## 🚀 Architecture หลัง full RSS-First migration

```
                  RSS (multi-stage rotation)
                          ↓ projectId + templateId
        ┌─────────────────┴─────────────────┐
        ↓                                   ↓
getProjectDetail (HTTP)              PDF download (HTTP)
  - stepId, status, dept              - budget, deadline
  - announceType                      - province, district
        │                                   │
        └───────────────┬───────────────────┘
                        ↓
              all_jobs row (full populated)
                        ↓
              getProcureResult (HTTP)
                        ↓
              bid_history (ALL bidders + prices)
                        ↓
                  ANALYTICS QUERIES
```

## 📊 Scalability hệ thống

| Operation | Per project | 10K projects | 10K × 10 parallel |
|---|---|---|---|
| RSS poll | (batch) | 5 min | 5 min |
| getProjectDetail | ~1s | 2.7 hr | **17 min** |
| getProcureResult | ~1s | 2.7 hr | **17 min** |
| PDF download + parse | ~3-5s | 13.8 hr | **1.4 hr** |
| **Total** | ~5-7s | ~19 hr | **~2 hr** ⭐ |

→ Phase 3 (77 จังหวัด) **ทำได้ใน 2-3 ชั่วโมง** ด้วย parallel HTTP

## 🎯 Implications

### ✅ Removes ALL Chrome dependencies
- Sebastian_Scraper.py search loop → ไม่ต้องใช้
- refresh_active_jobs.py → เปลี่ยนเป็น HTTP-only
- patch_deadlines.py → เปลี่ยนเป็น HTTP-only
- Pipeline ทุก step → cloud-deployable

### ✅ Cloudflare ไม่กระทบเลย
- RSS subdomain ปลอด Cloudflare ✓
- process5 API endpoints (getProjectDetail/Result + PDF) ผ่าน Cloudflare ได้ ด้วย Mozilla UA + Referer
- Search endpoint ที่ติด Cloudflare → ไม่ต้องใช้แล้ว

### ✅ Scale ทั้งประเทศได้
- 10K projects/day × 5-7s/project (parallel) = 2-3 hours
- Vercel function (parallel = unlimited)
- Cloud cron schedule ได้

### ✅ Pipeline ลดเหลือ ~30 นาที (จาก 100 นาที)

### ✅ bid_history populate ได้ทั่วประเทศ
- ทุก awarded project → ดึง bidders ทั้งหมด
- Competitor analysis แม่นยำ
- Pricing intel ครบ

## 🛠️ Implementation Plan

### Phase 1: HTTP-only client wrappers (~2 ชั่วโมง)
- `scripts/process5_http_client.py` — wrapper สำหรับ getProjectDetail/Result + PDF
- Headers: Mozilla UA + Referer
- Retry logic
- Error handling

### Phase 2: Replace refresh_active_jobs (~1-2 ชั่วโมง)
- Drop Playwright/Chrome dependency
- Use process5_http_client
- Parallel workers (5-10)

### Phase 3: Replace patch_deadlines (~1-2 ชั่วโมง)
- Direct PDF download + pdfplumber parse
- No Chrome navigation
- Parallel batch

### Phase 4: bid_history populate (~2-3 ชั่วโมง)
- Loop all awarded projects
- Call getProcureResult per project
- Parse bidders into bid_history table

### Phase 5: Pipeline restructure (~1-2 ชั่วโมง)
- Pipeline 02:00 = HTTP-only
- Drop Chrome from collect.bat
- Run faster (~30 min)

### Phase 6: Cloud migration (~3-4 sessions, Phase 3 SaaS)
- Vercel cron → calls process5 HTTP APIs
- No need for Windows Task Scheduler
- Parallel workers via Vercel function concurrency

## ⚠️ Caveats / Risk

1. **Headers detection** — process5 might add bot detection. Always use Mozilla UA + Referer.
2. **Rate limiting** — HTTP path might have different limits than RSS. Test before pushing.
3. **Chrome session cookies** — direct HTTP doesn't have cookies. If endpoint requires auth → break. (Currently no auth needed for these endpoints.)
4. **PDF template variations** — different agencies may use different PDF formats. Need robust regex.
5. **Endpoint stability** — government might add CSRF / token requirements in future. Plan for fallback.

## 📚 References

- Discovery via brute-force HTTP probing + pdfplumber test
- Validated 2026-05-19 with multiple project IDs
- See `scripts/process5_http_client.py` (to be created)
