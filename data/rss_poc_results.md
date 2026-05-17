# RSS POC Results (2026-05-17)

## ✅ Findings — RSS Feed ใช้งานได้จริง

### Endpoint
```
URL:    https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml
Method: GET
Auth:   ไม่ต้อง
Cloudflare: ❌ ไม่ติด (subdomain แยกจาก process5)
```

### Required Headers (สำคัญ!)
ถ้าไม่มี User-Agent → server reset connection (ConnectionResetError 10054)

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}
```

### Encoding
- Server บอก `ISO-8859-1` (ผิด!)
- จริงคือ **TIS-620** หรือ Windows-874 (cp874)
- `r.content.decode('tis-620')` ใช้งานได้ — 92 Thai chars decode สำเร็จ

### RSS Item Schema
```xml
<item>
  <title>ประกวดราคาซื้อโครงการบูรณาการระบบสำรวจ...</title>
  <description>69049437914, ประกวดราคาอิเล็กทรอนิกส์ (e-bidding), ประกาศเชิญชวน</description>
  <link>https://process5.gprocurement.go.th/.../view-pdf-file?templateId=...</link>
  <pubDate>2026-05-15</pubDate>
</item>
```

**Description format:** `<projectId>, <method>, <stage>`
- projectId = 11-12 digits (เช่น `69049437914`)
- method = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)" หรืออื่นๆ
- stage = "ประกาศเชิญชวน" (D0 เท่านั้น)

---

## ⚠️ Limitations ที่พบ

### 1. RSS = D0 (active_bidding) ONLY
**Tested:** ลอง `?annType=P0`, `?annType=B0`, `?annType=W0` — ทุกอันได้ items เดียวกัน
**Conclusion:** RSS feed นี้ครอบคลุมเฉพาะ **ประกาศเชิญชวน (D0 = active_bidding)** ไม่รวม:
- ❌ pre_tor (P0)
- ❌ tor_review (B0)
- ❌ awarded (W0)
- ❌ cancelled (D1)

**Verified:** ลอง URL variations (egpplanrss, egpwinnerrss, egptordraftrss, etc.) → ทุกอัน HTTP 404

### 2. ต้อง filter ด้วย `deptId`
ไม่ใส่ deptId → return 0 items (only baseline ที่ไม่มี items)

### 3. announceType params ไม่ทำงาน
ลอง `annType`, `type`, `announceType`, `announce_type` — ค่าไม่ผลต่อ output

### 4. Max 3-20 items per feed
RSS ของ dept หนึ่ง return ~3-20 items ล่าสุด → ต้องรู้ dept_id ของหน่วยงานเป้าหมายไว้

---

## 📊 Test Results Summary

| Test | สถานะ | หมายเหตุ |
|---|---|---|
| HTTP 200 ทุก request | ✅ | ไม่ติด Cloudflare |
| Encoding TIS-620 → UTF-8 | ✅ | ภาษาไทยอ่านได้ |
| projectId extract | ✅ | regex `\d{11,12}` ใช้งานได้ |
| Multiple announceType filter | ❌ | server ignore — D0 only |
| deptId filter | ✅ | 0703=20 items, 0708=13 items |
| Cross-match กับ CGD API | ⚠️ | RSS = 2569 jids, CGD = 2568 contracts → not yet (รอ 2569 contract data) |

---

## 🎯 Use Cases ที่ใช้งานได้

### ✅ Replaceable scraper part: **active_bidding pipeline**

ปัจจุบัน: scrape process5 หา keyword "นครพนม" ทั่วๆ → กรอง → 87 นาที + Cloudflare

หลังเปลี่ยน:
1. RSS poll ทุก deptId ของหน่วยงานเป้าหมาย (รัฐบาลในนครพนม + บึงกาฬ + กรมระดับชาติที่ทำในจังหวัด) ทุก 30 นาที
2. extract projectId
3. enrich ผ่าน CGD API (เฉพาะที่ใหม่)
4. classify → active_bidding sheet

### ❌ ยังต้อง scraper สำหรับ
- pre_tor (P0/Q*)
- tor_review (B0/U*)
- cancelled (D1)
- ดึง deadline / budget detail (RSS มีแค่ projectId/title/link)

---

## 🛣️ Next Steps (Phase 1)

1. **หา deptId catalog** ของหน่วยงานเป้าหมาย:
   - กรมทางหลวงชนบทนครพนม
   - โยธาธิการนครพนม / บึงกาฬ
   - อบจ.นครพนม / บึงกาฬ
   - เทศบาล/อบต. ใน อ.บ้านแพง + อ.บึงโขงหลง
   - กรมระดับชาติ (ทล., ทล.ชนบทกรุงเทพฯ, ประปาภูมิภาค, ฯลฯ)
   
   **Method:** scan deptId 0001-9999 + filter จาก title text → save catalog

2. **เขียน `Sebastian_RSS_Scraper.py`**:
   - Poll RSS ทุก deptId ทุก 30 นาที
   - Dedupe ด้วย projectId
   - Enrich ผ่าน CGD API → all_jobs row update
   - Detection: ถ้า projectId หายไปจาก RSS แสดงว่าหมดเวลา → keep status ปัจจุบัน

3. **ลดบทบาท process5 scraper**:
   - ใช้เฉพาะ pre_tor / tor_review / cancelled
   - ใช้ Patchright (Phase 1.5) ถ้า Cloudflare ยังบล็อกมาก

---

## 🔗 Files Generated
- `scripts/probe_egp_rss.py` — POC script
- `data/rss_probe_results.json` — full test data
- `data/egp_deptid_scan.json` — initial deptId scan (empty result, รอ refined search)
- `data/rss_poc_results.md` — this report
