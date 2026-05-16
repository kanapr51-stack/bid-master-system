# Scraper Optimization v2 — Industry & Academic Best Practices (2026-05-17)

**Goal:** ดึงข้อมูล eGP เร็ว + คุณภาพดี (detection of issues + auto-recovery)

**Research sources (10 papers + 5 industry guides reviewed):**
- Apache Nutch AdaptiveFetchSchedule
- Stanford IR Book — Crawler Architecture / URL Frontier
- Apify "Web Scraping Best Practices 2026"
- ScrapeHero, Scrapfly, Brightdata — rate limit guides
- nature.com — Neural Prioritization for Web Crawling (2025)
- Microsoft Research — Site-level knowledge for incremental crawling

---

## 📚 10 Industry Best Practices Found

| # | Practice | Bid Master ปัจจุบัน | Action |
|---|---|---|---|
| 1 | **API-First** (check official API) | ✅ ตรวจแล้ว — CGDContract = contracts only | Phase 2: integrate for awarded |
| 2 | **Resilient selectors** (id > data-* > semantic) | N/A (เราใช้ API ไม่ใช่ HTML parse) | — |
| 3 | **Exponential backoff + jitter** | ❌ ใช้ static 90s cooldown | **Implement** |
| 4 | **Politeness rate limit** (0.5-1 req/s small site) | ✅ Sleep 1.5s + cooldown 90s/80reqs | OK |
| 5 | **Proxy rotation** | ❌ 1 IP | Skip (Cloudflare risk) |
| 6 | **Dynamic content handling** | ✅ Playwright + Cloudflare token | OK |
| 7 | **Incremental write (no buffer)** | ⚠️ Buffer in memory ใน main() | **Improve** |
| 8 | **Deduplication tracking** | ✅ seen_ids.json | OK |
| 9 | **Structured monitoring + alerts** | ⚠️ มี log ปกติ ไม่มี JSON metrics | **Implement** |
| 10 | **Legal compliance** (robots.txt) | ⚠️ ไม่ได้เช็ค | Low priority (public data) |

---

## 🔬 4 Academic Techniques to Adopt

### 1. ⭐⭐⭐⭐⭐ **Content Hash Signature** (Nutch pattern)

**Concept:**
- Hash response page 1 body → cache
- Next time: hash again → if same → skip pagination
- More robust than jid (handles reordering, deletions)

**Why better than jid-only:**
- jid mismatch on reorder → false positive (treats as new when isn't)
- Hash mismatch only on actual change → accurate

**Implementation:** ~30 lines

### 2. ⭐⭐⭐⭐ **Adaptive Fetch Schedule** (Nutch DEC_FACTOR=0.2)

**Concept:**
- Track per-keyword change history (last 7 runs)
- Keyword always 0 new → reduce frequency (every 3 days instead of daily)
- Keyword often new → keep daily

**Math:**
- DEC_FACTOR (unchanged): interval × 1.2 (increase)
- INC_FACTOR (changed): interval × 0.8 (decrease)
- Clamp: min 1 day, max 7 days

**Expected savings:**
- ~10-15 keywords stable (no new for weeks) → check every 3-7 days
- Saves another 50-70% on those keywords

### 3. ⭐⭐⭐⭐ **Exponential Backoff with Jitter**

**Concept:**
- Replace static 90s cooldown
- `wait = min(base * (2 ** attempt), max_wait) + random.uniform(0, jitter)`
- e.g., 30s → 60s → 120s → 240s + jitter

**Why:**
- Sometimes rate limit clears in 30s, sometimes 5 min
- Static 90s wastes time when actually 30s suffices
- Jitter avoids "retry storm" (multiple workers retry same time)

### 4. ⭐⭐⭐ **Circuit Breaker**

**Concept:**
- Track consecutive rate-limited responses
- If 3+ in row globally → halt 5 min
- Auto-recover after timer

**Why:** prevents wasting requests when API completely blocked

---

## 🛡️ Quality Improvements

### Schema Validation
```python
def validate_response(body):
    if not isinstance(body, dict): return False
    if body.get("response", {}).get("responseCode") != "0": return False
    items = body.get("data", {}).get("data", [])
    if not isinstance(items, list): return False
    if items and not items[0].get("projectId"): return False  # schema changed?
    return True
```

**Action:** Discord alert if validation fail rate >10%

### Structured Logging (JSON)
```json
{
  "ts": "2026-05-17T02:15:00",
  "keyword": "ตำบลโพนทอง",
  "duration_ms": 7300,
  "pages_fetched": 1,
  "items": 10,
  "new_items": 0,
  "rate_limited_pages": 0,
  "incremental_skip": true,
  "status": "success"
}
```

Save to `logs/scrape_metrics_YYYY-MM-DD.jsonl` (one line per keyword run)

### Anomaly Detection (Discord alerts)
- Total scrape time > 2× baseline (rate limit?)
- Zero items across all keywords (schema break?)
- Validation fail >10% (API changed?)
- Rate limited >50% (need backoff?)

---

## 📊 Expected Combined Impact

| Improvement | Speed | Quality |
|---|---|---|
| Content hash (vs jid only) | +5% accuracy | +Reliability |
| Adaptive frequency | +50% on stable keywords | — |
| Exponential backoff | +20% on rate-limited days | — |
| Circuit breaker | -90% wasted requests when down | — |
| Schema validation | — | +Detect breaking changes |
| Structured logs | — | +Debuggability |
| Anomaly alerts | — | +Proactive fixing |

**Cumulative estimated speedup (typical day):**
- Phase 1 (incremental jid): 85 min → 5 min (17x)
- + Phase 2 (these improvements): 5 min → **3-4 min** (additional 25-40%)

**Quality (issue detection):**
- Now: bugs found by user
- After: Discord alert within 1 hour of issue

---

## 🛠️ Implementation Priority

**Phase 2A (TODAY):** High-impact, low-risk
1. ✅ Content hash change detection
2. ✅ Exponential backoff + jitter
3. ✅ Structured JSON logging
4. ✅ Anomaly Discord alerts

**Phase 2B (NEXT WEEK):** Medium-impact, more testing needed
5. Adaptive fetch schedule (per-keyword frequency)
6. Schema validation framework
7. Circuit breaker

**Phase 3 (FUTURE):** Distributed/parallel
8. Multi-context (if needed)
9. Proxy rotation (if Cloudflare strict)

---

## 📑 References

- [Apache Nutch AdaptiveFetchSchedule (apache.org)](https://nutch.apache.org/apidocs/apidocs-2.0/org/apache/nutch/crawl/AdaptiveFetchSchedule.html)
- [Stanford IR Book — URL Frontier](https://nlp.stanford.edu/IR-book/html/htmledition/the-url-frontier-1.html)
- [Web Scraping Best Practices 2026 (Apify)](https://use-apify.com/blog/web-scraping-best-practices-2026)
- [Strategic Caching in Web Scraping (webscraping.pro)](https://webscraping.pro/strategic-caching-in-web-scraping-minimizing-footprint-maximizing-efficiency/)
- [Distributed Web Crawling Guide (BrightData)](https://brightdata.com/blog/web-data/distributed-web-crawling)
- [Optimization Techniques for Focused Web Crawlers (ResearchGate)](https://www.researchgate.net/publication/377711447_Optimization_Techniques_for_Focused_Web_Crawlers)
- [AI driven web crawling for semantic extraction (Nature 2025)](https://www.nature.com/articles/s41598-025-25616-x)
