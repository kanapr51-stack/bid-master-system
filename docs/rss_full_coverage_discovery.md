# RSS Full Coverage Discovery (2026-05-18)

## 🎯 Discovery

POC เก่าทดสอบ `announceType` (correct spelling) → server ignored → คิดว่า RSS = D0 only

**ความจริง:** parameter ที่ใช้คือ `anounceType` (กระทรวงพิมพ์ผิด — ขาดตัว n)

ใช้ได้ทุก stage:

```
P0 → แผนการจัดซื้อจัดจ้าง (Pre-TOR) ⭐
B0 → ร่างเอกสารประกวดราคา (TOR Review) ⭐
D0 → ประกาศเชิญชวน (active_bidding)
D1 → ยกเลิกประกาศเชิญชวน (cancelled)
D2 → เปลี่ยนแปลงประกาศเชิญชวน
W0 → ประกาศผู้ชนะ (awarded)
W1 → ยกเลิกประกาศผู้ชนะ
W2 → เปลี่ยนแปลงประกาศผู้ชนะ
15 → ประกาศราคากลาง
```

## 📊 Implications

### Cloudflare ไม่ใช่ปัญหาอีกต่อไป
- RSS subdomain (process.gprocurement.go.th) ไม่มี Cloudflare
- ทุก stage มี RSS endpoint
- Process5 scraper อาจไม่ต้องใช้สำหรับ stage tracking

### Pipeline ใหม่ที่ทำได้
```
RSS poll (anounceType=P0) → Pre-TOR ทั่วประเทศ
RSS poll (anounceType=B0) → TOR Review ทั่วประเทศ
RSS poll (anounceType=D0) → Active bidding ทั่วประเทศ
RSS poll (anounceType=W0) → Awarded ทั่วประเทศ
RSS poll (anounceType=D1) → Cancelled ทั่วประเทศ
+ CGD CKAN → backfill 2568 awarded
+ process5 getProjectDetail → enrich per-project detail (point lookup)
```

→ **ไม่ต้องพึ่ง search-based scraping อีก** (ที่ติด Cloudflare)
→ **ไม่ต้องลงทุน proxy / Patchright** (Phase 1.5 ไม่จำเป็น)
→ **G-LEAD gap ปิดได้!**

## 🛠️ Implementation Plan

### Update Sebastian_RSS_Scraper.py
1. รับ param `--stage` (P0/B0/D0/W0/D1)
2. Loop ทุก dept × stage
3. Save แยกตาม stage ใน catalog

### Stage rotation strategy
- 5 cron jobs (ทุก 30 นาที, stagger 6 นาที):
  - 00:06, 00:36 → P0
  - 00:12, 00:42 → B0
  - 00:18, 00:48 → D0
  - 00:24, 00:54 → W0
  - 00:30, 01:00 → D1

หรือ:
- 1 cron ทุก 30 นาที → cycle ผ่าน 5 stages ครั้งละ stage
- 2.5 ชม. coverage ครบทุก stage

## 🔗 Source

จาก:
- เทศบาลเมืองเขลางค์นคร doc: https://www.kelangnakorn.go.th/kelang/?p=20759
- Live test 2026-05-18 ~21:00

## ⚠️ Caveats

1. B0 บาง dept ติด timeout ชั่วคราว — server load (ไม่ใช่ block IP)
2. มีคำว่า "access window" ใน doc (12:01-12:59 + 17:01-08:59) — verify ว่ากระทบไหม
3. process3 (subdomain เก่า) vs process (subdomain ใหม่) — ใช้ process ตัวใหม่
