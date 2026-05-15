# ภาพรวมงานและระบบ Bid Master

## งานปัจจุบัน

คุณกัญจน์รับผิดชอบ:
- คำนวณต้นทุนงานรับเหมาก่อสร้าง (หจก. ยศประทานรุ่งเรืองทรัพย์)
- คำนวณต้นทุนคอนกรีตผสมเสร็จ (BSC ทรัพย์คอนกรีต)
- สร้างระบบประมูลงานภาครัฐแบบอัตโนมัติ

---

## ระบบ Bid Master — Pipeline (อัปเดต 2026-05-10)

```
gprocurement.go.th (process5 — Angular SPA)
         │
         ▼
[ Sebastian_Scraper.py ]
  - ค้นหาด้วย keyword: นครพนม / บึงกาฬ
  - filter ด้วย 17 construction keywords
  - Dedup ด้วย seen_ids.json
  - บันทึก project_status (กำลังประมูล/ประมูลแล้ว/ยกเลิก)
         │
         ▼
[ Sebastian_Classifier.py ]
  - จำแนกงานเข้า 6 raw_jobs_* sheets
  - active_bidding = e-bidding กำลังประมูล (ชีทหลัก)
         │
         ▼ (เฉพาะ active_bidding)
[ Sebastian_Doc_Downloader.py ]
  - 2-step API: listProjectPriceBuildZipByProjectId → downloadFileTest
  - ดึง ZIP → แตกไฟล์ pB0–pB4.pdf
  - bันทึกลง downloads/<job_id>/
         │
         ▼
[ Sebastian_TOR_Analyzer.py + Sebastian_PR45_Parser.py ]
  - Claude Vision อ่าน pB1/pB2 → W, L, T, St, grade, dowel, joint
  - Claude Vision อ่าน pB3 (ปร.5) → budget_price
  - cache ผลลัพธ์เป็น tor_result.json ต่อ job
         │
         ▼
[ Sebastian_JSON_Merger.py + Sebastian_Sheet2_Writer.py ]
  - ผนวก JSON → combined.json
  - upsert ลง SHEET: job_specs
         │
         ▼
[ Sebastian_Cost_Filler.py ]
  - เติม C11–C17 ใน cost_data_By_Dexter
  - รอ 3s → อ่าน output (ต้นทุน, ราคาประมูล, % กำไร)
         │
         ▼
[ Sebastian_Ranker.py ]
  - score: margin(40%) + budget(30%) + confidence(20%) + completeness(10%)
  - บันทึกลง SHEET: ranked_jobs
         │
         ▼
[ Sebastian_LINE_Notify.py ]
  - ส่งสรุป TOP 5 งานไป LINE
  - ต้องการ LINE_NOTIFY_TOKEN ใน .env
```

**รันอัตโนมัติทุกวัน 06:00 น.** ด้วย Windows Task Scheduler (`BidMaster-DailyPipeline`)

---

## โครงสร้าง Google Sheets

### raw_jobs — ข้อมูลดิบทั้งหมด

| Sheet | ความหมาย | สถานะ |
|-------|---------|-------|
| `raw_jobs_all` | ทุกงานในพื้นที่ 2 จังหวัด | ✅ 593+ งาน |
| `raw_jobs_related` | งานก่อสร้างที่เกี่ยวข้อง | ✅ 35+ งาน |
| `raw_jobs_bidding` | e-bidding ทั้งหมด (ไม่กรองสถานะ) | ✅ มีข้อมูล |
| `raw_jobs_direct` | วิธีเฉพาะเจาะจง | ✅ 28+ งาน |
| `raw_jobs_awarded` | ประกาศผู้ชนะ | ✅ สร้างแล้ว |
| `raw_jobs_cancelled` | ยกเลิก | ✅ สร้างแล้ว |
| `active_bidding` | e-bidding **กำลังประมูล** ← ชีทหลัก | ⚠️ รอรัน Scraper ใหม่ |
| `awarded_jobs` | e-bidding ที่ประมูลแล้ว | ⚠️ รอรัน Scraper ใหม่ |

### pipeline sheets — ประมวลผล

| Sheet | ความหมาย | เติมโดย |
|-------|---------|---------|
| `job_specs` | ข้อมูล merged (W,L,T,grade,dowel...) | Sebastian_Sheet2_Writer.py |
| `cost_data_By_Dexter` | template คำนวณต้นทุน | Sebastian_Cost_Filler.py |
| `ranked_jobs` | จัดอันดับงานตาม score | Sebastian_Ranker.py |

---

## Script Files — สถานะปัจจุบัน

| Script | หน้าที่ | สถานะ |
|--------|---------|-------|
| `Sebastian_Scraper.py` | ดึงงาน → raw_jobs_all | ✅ ทำงานได้ |
| `Sebastian_Classifier.py` | จำแนก → 6 sheets + active_bidding | ✅ ทำงานได้ |
| `Sebastian_Doc_Downloader.py` | ดาวน์โหลด ZIP เอกสาร | ✅ ทำงานได้ |
| `Sebastian_PR45_Parser.py` | อ่าน ปร.4/5 → JSON | ✅ ทำงานได้ |
| `Sebastian_TOR_Analyzer.py` | Claude Vision อ่าน TOR → JSON | ✅ ทำงานได้ |
| `Sebastian_JSON_Merger.py` | ผนวก JSON → combined | ✅ ทำงานได้ |
| `Sebastian_Sheet2_Writer.py` | combined → job_specs | ✅ ทำงานได้ |
| `Sebastian_Cost_Filler.py` | job_specs → cost_data_By_Dexter | ✅ ทำงานได้ |
| `Sebastian_Ranker.py` | cost results → ranked_jobs | ✅ ทำงานได้ |
| `Sebastian_LINE_Notify.py` | ส่งสรุปไป LINE | ✅ เขียนแล้ว รอ token |
| `Sebastian_Winner_Checker.py` | ดึงชื่อผู้ชนะ → awarded_jobs | ✅ เขียนแล้ว รอทดสอบ |
| `Sebastian_Pipeline.py` | Master runner ทุก step | ✅ ทำงานได้ |
| `sheets_client.py` | Service Account auth | ✅ ทำงานได้ |

---

## โครงสร้าง Sub Agent

| Sub Agent | บทบาท | สถานะ |
|-----------|--------|-------|
| **Sebastian** | หัวหน้า — บริหาร pipeline, ออกแบบระบบ | ✅ Active |
| **Natalia** | จดบันทึก สรุป backup ตารางเวลา | ✅ Active |
| **Dexter** | เขียนโค้ด สูตร Sheets คำนวณต้นทุน | ✅ Active |
| **Joyce** | อ่านเอกสาร TOR ถอดมิติ-วัสดุ-เหล็ก | ✅ Active |

---

## สิ่งที่ยังค้างอยู่

| งาน | เหตุผลที่ค้าง |
|-----|-------------|
| กรอกราคา/หน่วย column H ใน cost_data_By_Dexter | รอคุณกัญจน์กรอก → รัน `--step cost` ใหม่ |
| LINE_NOTIFY_TOKEN | รอคุณกัญจน์รับ token จาก notify-bot.line.me |
| รัน Scraper ใหม่ | ให้ข้อมูลไหลเข้า active_bidding + awarded_jobs |
| กรอก concrete.md | Mix Design + ราคาวัตถุดิบ BSC |
| กรอก general_construction.md | ต้นทุนงานก่อสร้างทั่วไป |
