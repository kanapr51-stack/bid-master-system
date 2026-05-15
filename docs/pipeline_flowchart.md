# Sebastian Pipeline Flowchart — 06:00 น. ทุกวัน

```
06:00 น. — Task Scheduler ปลุก Windows
│
▼
🚀 run_pipeline.bat เริ่ม
│
▼
🌐 เปิด Chrome (port 9222, profile แยก C:\Temp\ChromeDebug)
│  รอ 20 วินาที
│
├─────────────────────────────────────────────────────────┐
│  STEP 1: SCRAPER (ใช้ Chrome)                           │
│                                                         │
│  ค้นหาใน eGP process5.gprocurement.go.th               │
│  ├── จังหวัด "นครพนม"  (~5,000-6,000 รายการ/วัน)      │
│  │     [รอ 180s]                                        │
│  └── จังหวัด "บึงกาฬ" (~4,000-5,000 รายการ/วัน)       │
│                                                         │
│  กรอง: title ต้องมี keyword ใดใน 17 รายการ             │
│  เช่น ถนนคอนกรีต, คอนกรีตเสริมเหล็ก,                 │
│       ก่อสร้างถนน, ซ่อมแซมถนน, ฝายคอนกรีต ฯลฯ       │
│                                                         │
│  เก็บเฉพาะงาน ใหม่ (ไม่ซ้ำ seen_ids.json)             │
│                                                         │
│  ✍️ เขียนลง: raw_jobs (Google Sheet)                   │
│              + data/jobs_YYYYMMDD_HHMM.json (backup)   │
└─────────────────────────────────────────────────────────┘
│
▼
├─────────────────────────────────────────────────────────┐
│  STEP 2: CLASSIFIER (ไม่ใช้ Chrome)                     │
│                                                         │
│  อ่าน raw_jobs → จำแนกแต่ละงานตาม procurement type     │
│  + flowName (สถานะใน eGP)                              │
│                                                         │
│  ┌─────────────────┬───────────────────────────────┐   │
│  │ Sheet           │ เงื่อนไข                      │   │
│  ├─────────────────┼───────────────────────────────┤   │
│  │ active_bidding  │ e-bidding + กำลังประมูล       │   │
│  │ awarded_jobs    │ e-bidding + ประมูลแล้ว         │   │
│  │ raw_jobs_related│ งานก่อสร้างทุกประเภท          │   │
│  │ raw_jobs_bidding│ e-bidding ทุกสถานะ             │   │
│  │ raw_jobs_direct │ เฉพาะเจาะจง                   │   │
│  │ raw_jobs_cancel │ ยกเลิก                        │   │
│  └─────────────────┴───────────────────────────────┘   │
│                                                         │
│  ✍️ เขียนลงทุก Sheet (clear + rewrite, คง winner data)  │
└─────────────────────────────────────────────────────────┘
│
▼
├─────────────────────────────────────────────────────────┐
│  STEP 3: WINNER CHECKER (ใช้ Chrome)                    │
│                                                         │
│  อ่าน awarded_jobs + raw_jobs_direct                   │
│  กรองเฉพาะแถวที่ ผู้ชนะประมูล = ว่าง                  │
│                                                         │
│  per งาน — เรียก API 2 ขั้น:                           │
│  ① getContractAvailable?projectId=                     │
│     → corporateName (เซ็นสัญญาแล้ว)                   │
│  ② getProcureResult?projectId=     [fallback]          │
│     → receiveNameTh (ยังไม่เซ็นสัญญา)                 │
│                                                         │
│  ✍️ batch update:                                       │
│     คอลัมน์ O = ผู้ชนะประมูล                           │
│     คอลัมน์ P = ราคาที่ชนะ (บาท)                      │
│     คอลัมน์ Q = วันประกาศผู้ชนะ                       │
└─────────────────────────────────────────────────────────┘
│
▼
🔒 ปิด Chrome
│
▼
├─────────────────────────────────────────────────────────┐
│  STEP 4: LINE NOTIFY (ไม่ใช้ Chrome)                    │
│                                                         │
│  อ่าน active_bidding → ยอดรวมทั้งหมด                   │
│  แสดงรายการ 15 งานแรกในชีท                             │
│  สร้างข้อความสรุปแต่ละงาน:                             │
│    📌 ชื่องาน                                           │
│    💰 งบประมาณ                                         │
│    🏢 หน่วยงาน                                         │
│    🔑 job_id                                            │
│                                                         │
│  ถ้าข้อความยาว > 4,900 ตัว → split ส่งหลายรอบ         │
│                                                         │
│  ✍️ push → LINE Group (LINE Messaging API)              │
└─────────────────────────────────────────────────────────┘
│
▼
✅ Pipeline เสร็จสิ้น
   Log → C:\Bid-Master-System\logs\pipeline_YYYYMMDD.txt
```

## หมายเหตุ LINE Notify

- `TOP_N = 15` → แสดงรายการแค่ 15 งานแรก แต่บอกยอดรวมจริงทั้งหมด
- ถ้าอยากส่งทั้งหมด → ลบ `[:TOP_N]` ใน `Sebastian_LINE_Notify.py` บรรทัด 90
- auto-split จะจัดการเองถ้าข้อความยาวเกิน 4,900 ตัว

## ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|------|---------|
| `run_pipeline.bat` | ตัวหลัก — เปิด Chrome, รัน step 1-4, ปิด Chrome |
| `scripts/Sebastian_Scraper.py` | Step 1 — ดึงงานจาก eGP |
| `scripts/Sebastian_Classifier.py` | Step 2 — จัดหมวด 6 Sheets |
| `scripts/Sebastian_Winner_Checker.py` | Step 3 — ดึงชื่อผู้ชนะ |
| `scripts/Sebastian_LINE_Notify.py` | Step 4 — ส่ง LINE |

อัปเดตล่าสุด: 2026-05-13
