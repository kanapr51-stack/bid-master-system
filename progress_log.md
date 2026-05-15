# Bid Master System — Progress Log

---

## งานที่ 1: แก้ Sheet cost_data_By_Dexter

### สถานะ: ✅ เสร็จแล้ว (2026-04-29)

**สิ่งที่ทำ:**
- ~~Shift rows 48-113 (เก่า) → rows 37-102 (ใหม่) ลบช่องว่าง 11 แถว~~
- ~~แก้ bug G column ใน DB/RB rows: เพิ่ม $ lock + B column condition~~
- ~~เพิ่ม Section 6 (งาน Joint) คืน: Metal Cap, Joint Filler, Sealer EJ/CJ (rows 50-54)~~
- ~~เพิ่ม Section 7 header "ท่อระบาย" + Shift ท่อระบาย→rows 56-58~~
- ~~อัปเดต SUM: I65=SUM(I22:I63), I75=SUM(I69:I74), I86=SUM(I79:I85)~~
- ~~อัปเดต summary refs: G91=I65, G92=I75, G93=I86, G94=G91+G92+G93~~
- ~~G101=G94*B100 (ราคาประมูล Factor F), G103=% กำไร~~
- ~~แก้ #ERROR! row (====formula) → blank~~
- ~~แก้ typo "ท่อระบย" → "ท่อระบาย"~~
- ~~ล้าง rows 103-120~~

**โครงสร้างปัจจุบัน:**
| Row | Content |
|-----|---------|
| 1-21 | ข้อมูลโครงการ (W, L, T, St, Sh, CJ, EJ, Factor F) |
| 22-36 | Section 1-4: ดิน, ทราย, คอนกรีต, Wire Mesh |
| 37-49 | Section 5: Dowel Bar / Tie Bar (DB10-RB25) |
| 50-54 | Section 6: งาน Joint (Metal Cap, Filler, Sealer EJ/CJ) |
| 55 | header Section 7: ท่อระบาย |
| 56-63 | Section 7-8: ท่อระบาย + อื่นๆ |
| 65 | ■ รวมต้นทุนวัตถุดิบ =SUM(I22:I63) |
| 69-74 | ค่าแรงงาน |
| 75 | ■ รวมค่าแรง =SUM(I69:I74) |
| 79-85 | ค่าเครื่องจักร |
| 86 | ■ รวมเครื่องจักร =SUM(I79:I85) |
| 91-103 | สรุปต้นทุน, Factor F, ราคาประมูล, % กำไร |

---

## งานที่ 2: Python Scraper — gprocurement.go.th

### สถานะ: ✅ ทำงานได้จริง (2026-04-29)

**ไฟล์:** `scripts/Sebastian_Scraper.py`

**สิ่งที่ค้นพบและทำสำเร็จ:**
- ~~ค้นพบว่า process3 (เก่า) ถูกปิด → เว็บย้ายมา process5 (Angular SPA)~~
- ~~ค้นพบ API จริง: `process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement`~~
- ~~แก้ปัญหา Cloudflare Turnstile — รอปุ่มค้นหา enabled ก่อน search~~
- ~~แก้ปัญหา Angular form binding — ใช้ `keyboard.type()` แทน `fill()`~~
- ~~Pagination ผ่าน `page.evaluate(fetch(url))` ในบริบท browser~~
- ~~Multi-keyword search 21 keywords บน session เดียว ไม่ต้อง reload~~
- ~~Filter เฉพาะพื้นที่: อ.บ้านแพง นครพนม + อ.บึงโขงหลง บึงกาฬ~~
- ~~Deduplication ด้วย projectId (จาก API โดยตรง)~~
- ~~บันทึก seen_ids.json + local JSON backup~~

**Keywords (21 รายการ):**
- Tier 1: ถนนคอนกรีต, ก่อสร้างถนนคอนกรีต, ปูคอนกรีต, คอนกรีตเสริมเหล็ก
- Tier 2: ก่อสร้างถนน, ซ่อมแซมถนน, ปรับปรุงถนน, งานโยธา, ท่อระบายน้ำ คสล., Dowel Bar, คอนกรีตผสมเสร็จ, ฝายคอนกรีต, ลานคอนกรีต ฯลฯ

**วิธีรัน:**
```
1. Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\Temp\ChromeDebug"
2. python scripts/Sebastian_Scraper.py
```

**ยังขาด:**
- [ ] ทดสอบ `append_jobs_to_sheet` full run จริงกับ Sheets
- [ ] TOR URL — process5 API ไม่ return ลิงก์ PDF (ต้องเปิดหน้ารายละเอียด projectId แยก)

---

## งานที่ 3: Document Downloader

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_Doc_Downloader.py`

- อ่านงาน status='new' + D0/M-step จาก Sheet 1
- ลอง API endpoint 3 รูปแบบสำหรับ file list
- Fallback: navigate ไป detail page → capture API + HTML links
- จำแนก pr4, pr5, tor จากชื่อไฟล์
- Download ไปยัง `downloads/<job_id>/`
- อัปเดต status: docs_downloaded / docs_failed

---

## งานที่ 4: ปร.4/5 Parser

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_PR45_Parser.py`

- รองรับ PDF (pymupdf) และ Excel (openpyxl)
- Auto-detect ปร.4 vs ปร.5 จากชื่อไฟล์และเนื้อหา
- ปร.4: แยก line items → {description, quantity, unit, unit_price, total}
- ปร.5: ดึง direct_cost, overhead_pct, profit_pct, total_price

---

## งานที่ 5: TOR AI Analyzer

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_TOR_Analyzer.py`

- อ่าน TOR PDF → clean + prioritize relevant sections
- เรียก Claude API (claude-sonnet-4-6) ครั้งเดียวต่องาน
- Output: W, L, T, St, grade, dowel_bar, tie_bar, wire_mesh, CJ, EJ, confidence

---

## งานที่ 6: JSON Merger + Sheet 2 Writer

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_JSON_Merger.py` + `scripts/Sebastian_Sheet2_Writer.py`

- Merger: ผนวก JSON (ปร.4/5) + JSON (TOR) + raw_job → Combined JSON
- Writer: Combined JSON → Sheet 2 (job_specs)
- Sheet 2 columns: job_id, title, W, L, T, St, grade, dowel, wire_mesh, CJ, EJ, budget, scores

---

## งานที่ 7: Cost Filler

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_Cost_Filler.py`

- อ่าน Sheet 2 status='analyzed'
- เติม C11=W, C12=L, C13=T, C14=St, C16=CJ, C17=EJ ใน cost_data_By_Dexter
- รอ 3 วินาทีให้ Sheets recalculate
- อ่าน output: I65, I75, I86, G94, G101, G103
- บันทึก cost_results JSON สำหรับ Ranker

---

## งานที่ 8: Ranker

### สถานะ: ✅ เขียนเสร็จ (รอทดสอบ)

**ไฟล์:** `scripts/Sebastian_Ranker.py`

- โหลด cost_results JSON
- Score: margin(40%) + budget(30%) + confidence(20%) + completeness(10%)
- บันทึกลง Sheet 4 (ranked_jobs) เรียงอันดับสูง → ต่ำ

---

## Master Pipeline

**ไฟล์:** `scripts/Sebastian_Pipeline.py`

```
python Sebastian_Pipeline.py                    # รันทั้ง 5 steps
python Sebastian_Pipeline.py --step scrape
python Sebastian_Pipeline.py --step download
python Sebastian_Pipeline.py --step analyze
python Sebastian_Pipeline.py --step cost
python Sebastian_Pipeline.py --step rank
```

---

## แผนงานถัดไป (เรียงตามลำดับ)

1. ~~**Full Run Test (Scraper)** — เปิด Chrome → รัน Scraper จริง → ตรวจ Sheet 1~~ ✅ 601 งาน
2. ~~**Full Run Test (Doc Download)** — รัน Doc Downloader → ยืนยัน API endpoint~~ ✅
3. ~~**Test ปร.4/5 Parser** — Claude Vision อ่าน PDF สแกนได้~~ ✅
4. ~~**Test TOR Analyzer** — Vision อ่าน pB2 ได้ W/L/T~~ ✅
5. ~~**End-to-end Test** — รัน full pipeline 1 งานสำเร็จ~~ ✅ job 69049122041
6. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน cost step ใหม่
7. **Task Scheduler** — ตั้ง Windows Task Scheduler รันอัตโนมัติ

---

## Checkpoint — 2026-04-29 22:47

### สถานะล่าสุด
Pipeline redesign เสร็จสมบูรณ์ (4-Sheet design)

### สิ่งที่เพิ่งทำ
- อัปเดต `work_overview.md` + `future_development.md` เป็น 4-Sheet design ใหม่
- เพิ่ม `seq_no`, `announce_type`, `step_id` ลง job dict ใน `Sebastian_Scraper.py`
- เขียน script ใหม่ครบ 6 ไฟล์:
  - `Sebastian_Doc_Downloader.py` — Chrome CDP download ปร.4/5/TOR
  - `Sebastian_PR45_Parser.py` — อ่าน ปร.4 (BOQ) + ปร.5 (price summary)
  - `Sebastian_TOR_Analyzer.py` — Claude API วิเคราะห์ TOR → JSON
  - `Sebastian_JSON_Merger.py` — ผนวก JSON สองอัน → combined
  - `Sebastian_Sheet2_Writer.py` — combined JSON → Sheet 2 (job_specs)
  - `Sebastian_Cost_Filler.py` — Sheet 2 → เติม C11-C17 → อ่าน output Sheet 3
  - `Sebastian_Ranker.py` — cost results → score → Sheet 4
- อัปเดต `Sebastian_Pipeline.py` ให้ครอบคลุม 5 steps ใหม่

### สิ่งที่ยังไม่ได้ทำ
- ยังไม่ได้รัน Full Run Test (ต้องการ Chrome port 9222)
- ยังไม่ทราบ exact API endpoint สำหรับ document download (Doc Downloader มี fallback + debug capture)
- ยังไม่ได้ตั้ง Task Scheduler

### ต้องทำต่อ
1. เปิด Chrome: `Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\Temp\ChromeDebug"`
2. รัน `python scripts/Sebastian_Scraper.py` → ตรวจ Sheet 1
3. รัน `python scripts/Sebastian_Doc_Downloader.py` → ดู `downloads/debug/` → หา API endpoint
4. ต่อ pipeline ตามผลที่ได้

---

## Checkpoint — 2026-05-07

### สถานะล่าสุด
Scraper routing fix + data integrity fixes เสร็จสมบูรณ์

### สิ่งที่เพิ่งทำ
- ~~แก้ `Sebastian_Scraper.py`: e-bidding jobs → raw_jobs_bidding ด้วย (เดิมเขียนแค่ raw_jobs)~~
- ~~คัดลอก 2 งาน e-bidding ที่ตกค้างจาก raw_jobs → raw_jobs_bidding: 69019024418, 69039054231~~
- ~~แก้ job_specs: ชื่อ column ไทยครบ 40 คอลัมน์, มี/ไม่มี แทน Y/N, สูง/กลาง/ต่ำ แทน high/medium/low~~
- ~~แก้ Scraper filter: กรองเฉพาะงานก่อสร้าง (CONSTRUCTION_KEYWORDS) ไม่ผ่านแค่พื้นที่~~
- ~~เพิ่ม Tier system: Tier 1 (ถนนคอนกรีต) = คำนวนเต็ม, Tier 2 = ยังไม่ได้คำนวน~~
- ~~เพิ่ม tor_result.json cache ใน TOR Analyzer~~
- ~~เพิ่มฟิลด์ใหม่ใน TOR: warranty_period_days, required_tests, required_delivery_documents, special_conditions~~
- ~~แก้ Doc Downloader: ตรวจ renamed folder ก่อนสร้างใหม่~~

### raw_jobs_bidding ปัจจุบัน (6 งาน)
| job_id | ชื่องาน (สั้น) | status |
|--------|----------------|--------|
| 68129570964 | บำรุงถนน นพ.3023 | no_boq |
| 69019077732 | เสริมผิวแอสฟัลท์ | docs_downloaded |
| 69049020320 | เพิ่มค่าสัมประสิทธิ์ผิวทาง | no_boq |
| 68119260653 | ปรับปรุงถนนแอสฟัลต์ติก | docs_downloaded |
| 69019024418 | เสริมผิวจราจรด้วยแอสฟัลท์คอนกรีต | **new** |
| 69039054231 | ปรับปรุงถนนคอนกรีตเสริมเหล็ก | **new** |

### ต้องทำต่อ
1. รัน Doc Downloader สำหรับ 2 งาน status='new' (ต้องการ Chrome port 9222)
2. รัน pipeline: analyze → merge → sheet2_writer สำหรับงานใหม่
3. กรอกราคา/หน่วย ใน cost_data_By_Dexter column H (รอ Phase 0)

---

## Checkpoint — 2026-04-30 03:35

### สถานะล่าสุด
Scraper Full Run Test สำเร็จสมบูรณ์

### สิ่งที่เพิ่งทำ
- รัน `Sebastian_Scraper.py` พร้อม Tier 0 keywords (บ้านแพง, บึงโขงหลง)
- ได้งานใหม่ **601 รายการ** บันทึกลง Sheet 1 (raw_jobs) + `data/jobs_20260430_0335.json`
  - บ้านแพง: 300/300 ✅
  - บึงโขงหลง: 299/300 (1 ซ้ำ) ✅
  - ลานคอนกรีต: 2 bonus
- Tier 1/2 keywords โดนrate limit หลัง Tier 0 แต่ได้ 0 พื้นที่อยู่แล้ว — ไม่กระทบ
- Session reinit ทำงานถูกต้อง (20s cooldown + Cloudflare Turnstile ผ่าน)

### สิ่งที่ยังไม่ได้ทำ
- ยังไม่ได้รัน Doc Downloader
- ยังไม่ทราบ exact API endpoint สำหรับ document download
- ยังไม่ได้ตั้ง Task Scheduler

### ต้องทำต่อ
1. รัน `python scripts/Sebastian_Doc_Downloader.py` → ดู `downloads/debug/` → หา API endpoint
2. ต่อ pipeline ตามผลที่ได้

---

## Checkpoint — 2026-05-01 14:25

### สถานะล่าสุด
**End-to-End Pipeline ผ่านครั้งแรก** ✅

### API Endpoints ที่ค้นพบ (สำคัญมาก)
| Endpoint | Method | Header | หมายเหตุ |
|----------|--------|--------|----------|
| `/egp-project-service/listProjectPriceBuildZipByProjectId?projectId={pid}` | GET | `apikey: Liaqv30xLpFGOlJPW1N0hPKJkbO7vWUS` | ดึง zipFileId |
| `/egp-upload-service/v1/downloadFileTest?fileId={zipFileId}` | GET | ไม่ต้องการ | ดาวน์โหลด zip จริง |

### โครงสร้าง BOQ Zip
```
pB0.pdf — ประกาศราคากลาง
pB1.pdf — รายการตรวจสอบประมาณการ (มี T, St)
pB2.pdf — แบบมาตรฐานงานถนน (มี W, L, T, CJ)
pB3.pdf — แบบสรุปราคากลาง (ปร.5) ← อ่านด้วย Claude Vision → budget_price
pB4.pdf — แผนที่โครงการ
```

### Script ที่แก้ไขวันนี้
- `Sebastian_Doc_Downloader.py` — เขียนใหม่ทั้งหมด ใช้ 2-step API flow
- `Sebastian_PR45_Parser.py` — เพิ่ม Claude Vision fallback สำหรับ PDF สแกน
- `Sebastian_TOR_Analyzer.py` — เพิ่ม `analyze_job_tor_vision()` อ่าน pB1/pB2/pB3
- `Sebastian_Sheet2_Writer.py` — เพิ่ม upsert (อัปเดตแถวที่มี W/L ใหม่)
- `Sebastian_Cost_Filler.py` — แก้ OUTPUT_CELLS (I77, I84, G91, G98, G100) + default CJ=10, EJ=100 (มาตรฐานถนน คสล. ไทย)

### ผลทดสอบ job 69049122041 (บ้านแพง ถนน คสล.)
- budget จาก Sheet 1: 497,000 บาท
- budget จาก ปร.5 (Vision): 491,741.89 บาท ✅
- W=5.0, L=145.0, T=0.15 (Vision จาก pB2) ✅
- Pipeline: download → analyze → cost → rank ผ่านครบ ✅
- ต้นทุน = 2,030 บาท (ผิด) เพราะ **ยังไม่ได้กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H

### Sheet ที่สร้างใหม่
- `job_specs` (Sheet 2) — สร้างวันนี้ มี 5 งาน

### ต้องทำต่อ
1. **คุณกัญจน์กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H
2. รัน `python scripts/Sebastian_Pipeline.py --step cost` ใหม่
3. ตั้ง Windows Task Scheduler

---

## Checkpoint — 2026-05-01 (session 2)

### สถานะล่าสุด
Task Scheduler พร้อมใช้งาน — pipeline รันอัตโนมัติทุกเช้า 06:00 น.

### สิ่งที่ทำสำเร็จ
- ~~**Windows Task Scheduler** — ลงทะเบียน `BidMaster-DailyPipeline` รันทุก 06:00 น.~~ ✅
- ~~**ปิด Sleep อัตโนมัติ** — AC Power Sleep เดิม 45 นาที → ตั้งเป็น Never~~ ✅
- ~~**แก้ CJ/EJ defaults** — CJ=10m, EJ=100m (มาตรฐานถนน คสล. ไทย)~~ ✅

### Pipeline ที่รันได้จริงตอนนี้ (06:00 น. ทุกวัน)
```
scrape → download → analyze → rank
```

### สิ่งที่ยังค้างอยู่ (ยังไม่รวมใน pipeline อัตโนมัติ)
| งาน | สาเหตุ | ต้องทำ |
|-----|--------|--------|
| Cost step | ราคา/หน่วย ใน cost_data_By_Dexter column H ยังว่าง | คุณกัญจน์กรอกราคา → รัน cost step ใหม่ |
| Classifier (6 Sheets) | `Sebastian_Classifier.py` ยังไม่ได้เขียน | เขียน script + สร้าง 3 sheet ที่เหลือ |

### 6-Sheet System — สถานะ
| Sheet | สถานะ |
|-------|-------|
| `raw_jobs_all` | ✅ สร้างแล้ว (ยังว่าง — รอ Classifier) |
| `raw_jobs_related` | ✅ สร้างแล้ว (ยังว่าง — รอ Classifier) |
| `raw_jobs_bidding` | ✅ สร้างแล้ว (ยังว่าง — รอ Classifier) |
| `raw_jobs_awarded` | ❌ ยังไม่สร้าง |
| `raw_jobs_direct` | ❌ ยังไม่สร้าง |
| `raw_jobs_cancelled` | ❌ ยังไม่สร้าง |

### ต้องทำต่อ
1. **คุณกัญจน์กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost` ใหม่
2. ~~เขียน `Sebastian_Classifier.py` + สร้าง 3 sheet ที่เหลือ~~ ✅
3. เพิ่ม cost step เข้า `run_pipeline.bat` (เมื่อ step 1 เสร็จ)

---

## Checkpoint — 2026-05-01 (session 3)

### สถานะล่าสุด
6-Sheet Classification system เสร็จสมบูรณ์

### สิ่งที่ทำสำเร็จ
- ~~**Sebastian_Classifier.py** — เขียนเสร็จ + รันสำเร็จ~~ ✅
- ~~**สร้าง 3 sheet ที่เหลือ** — raw_jobs_awarded, raw_jobs_direct, raw_jobs_cancelled~~ ✅
- ~~**เพิ่ม classify step** ใน Sebastian_Pipeline.py และ run_pipeline.bat~~ ✅
- ~~**แก้ province filter** — เช็ค keyword + province ตรงกัน (ไม่ใช่แค่ keyword ใน text)~~ ✅
  - ก่อน: กรองแค่ "บ้านแพง" ใน title → งานจากจังหวัดอื่นหลุดเข้ามา
  - หลัง: ต้องมี "บ้านแพง" ใน text AND province = "นครพนม" ถึงจะผ่าน
  - แก้ทั้ง `Sebastian_Scraper.py` และ `Sebastian_Classifier.py`

### 6-Sheet System — สถานะปัจจุบัน ✅ ครบทั้ง 6 ชีท
| Sheet | งาน | ความหมาย |
|-------|-----|----------|
| `raw_jobs_all` | 593 | ทุกงานในพื้นที่ (บ้านแพง นครพนม + บึงโขงหลง บึงกาฬ) |
| `raw_jobs_related` | 35 | งานก่อสร้างที่เกี่ยวกับบริษัท |
| `raw_jobs_bidding` | 4 | e-bidding + กำลังประมูล ← ชีทหลักสำหรับคำนวณ |
| `raw_jobs_awarded` | 0 | ประกาศผู้ชนะ (ยังไม่มีในรอบนี้) |
| `raw_jobs_direct` | 28 | วิธีเฉพาะเจาะจง |
| `raw_jobs_cancelled` | 0 | ยกเลิก (ยังไม่มีในรอบนี้) |

### Pipeline อัตโนมัติ 06:00 น. (ครบแล้ว ยกเว้น cost)
```
scrape → download → classify → analyze → rank
```

### ยังค้าง (เรียงตามลำดับความสำคัญ)
1. **LINE Notify** — ส่งสรุป ranked_jobs ไป LINE หลัง pipeline รัน (รอ token จากคุณกัญจน์)
2. **เพิ่ม Keywords** — คุณกัญจน์จะเพิ่ม keyword ใน Scraper + Classifier ให้ละเอียดขึ้น
3. **Cost step** — รอคุณกัญจน์กรอกราคา/หน่วยใน cost_data_By_Dexter column H

---

## Checkpoint — 2026-05-06

### สิ่งที่ทำสำเร็จ
- ~~**Service Account auth**~~ — แก้ `sheets_client.py` เปลี่ยนจาก ADC (หมดอายุ) → Service Account ✅
- ~~**Share Sheets กับ SA**~~ — Bid Master + BSC Orders share กับ `bid-master-sheets@bid-master-sheets.iam.gserviceaccount.com` ✅
- ~~**Full pipeline run**~~ — Step 1-4, 6 ผ่าน / Step 5 มี bug ✅
- ~~**Rate limit fix**~~ — Pagination detect → sleep 60s → retry / Search timeout → reinit + sleep 120s → retry / Loading spinner wait ✅
- ~~**Bug Step 5 Cost**~~ — แก้ `get_all_records(expected_headers=...)` ✅
- ~~**Doc Downloader เปลี่ยน source sheet**~~ — อ่านจาก `raw_jobs_bidding` แทน `raw_jobs` (download เฉพาะ 4 งาน e-bidding) ✅

### Pipeline ปัจจุบัน
```
scrape → classify → download PDF (raw_jobs_bidding เท่านั้น) → analyze → cost → rank
```

### ต้องทำต่อ
1. คุณกัญจน์กรอกราคา/หน่วยใน cost_data_By_Dexter column H → รัน `--step cost` ใหม่
2. LINE Notify token

---

## Checkpoint — 2026-05-06 (BSC Website session)

### สิ่งที่ทำสำเร็จ — BSC Website (bsc-website-wine.vercel.app)

**Booking System:**
- ~~**OrderModal disclaimer**~~ — เพิ่มกล่อง ✓ 3 ข้อ (ไม่มีมัดจำ, ยกเลิกได้, ทีมโทรกลับ) ✅
- ~~**BookingHighlight popup**~~ — floating card มุมล่างขวา โผล่หลัง scroll 400px มี X ปิดได้ ✅
- ~~**Booking cards หน้า /products**~~ — 3 การ์ดระหว่าง header กับสินค้า 01 ✅
- ~~**แยก lean กับ 240/2**~~ — แยกเป็น 2 options ใน OrderModal.tsx ✅

**SEO:**
- ~~**Google index แล้ว**~~ — ยืนยันผ่าน Search Console (site: query ขึ้นผล) ✅
- ~~**Sitemap.xml**~~ — `app/sitemap.ts` ✅
- ~~**robots.txt**~~ — `app/robots.ts` ✅
- ~~**Metadata แต่ละหน้า**~~ — layout.tsx สำหรับ /products, /about, /contact ✅

**Portfolio:**
- ~~**หน้า /portfolio**~~ — 40 รูป, filter 5 หมวด, lightbox คลิกดูเต็มจอ ✅
- ~~**caption มืออาชีพ**~~ — เปลี่ยนชื่อรูปทุกใบให้เป็นทางการ ✅
- ~~**Photo Marquee หน้าแรก**~~ — 2 แถวไหลสวนทาง infinite scroll ✅
- ~~**ลิงก์ผลงานใน Navbar**~~ — เพิ่ม "ผลงาน" ระหว่างสินค้า-เกี่ยวกับเรา ✅

### ยังค้าง
1. **คุณกัญจน์กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **LINE Notify token** → implement notification
3. **Domain** — ซื้อ `bscconcrete.co.th` หรือ `bscconcrete.com` แล้วผูก Vercel
4. **Open Graph image** — รูป preview ตอนแชร์ใน LINE/Facebook

---

## Checkpoint — 2026-05-08

### สิ่งที่ทำสำเร็จวันนี้

- ~~**แก้ Scraper keywords**~~ — เปลี่ยนจาก 21 keywords → ค้นหาด้วยจังหวัด `นครพนม` + `บึงกาฬ` แล้วใช้ 17 keywords เป็น filter ✅
- ~~**ลบ district filter**~~ — ไม่จำกัดแค่ บ้านแพง/บึงโขงหลง แล้ว ได้งานทั้ง 2 จังหวัด ✅
- ~~**แก้ rate limit retry**~~ — เปลี่ยนจาก 300s → 120s ตรงๆ (จาก pattern จริง: 60s ไม่พอ, 120s พอเสมอ) ✅
- ~~**รัน Scraper สำเร็จ**~~ — นครพนม 2,980 / บึงกาฬ 3,790 = 6,770 รายการ, ใหม่ 142 งาน ✅
- ~~**เพิ่ม project_status column**~~ — ดึงจาก flowName ใน API (กำลังประมูล / ประมูลแล้ว / ยกเลิก / กำลังเตรียม) ✅
- ~~**สร้าง sheet active_bidding**~~ — e-bidding กำลังประมูล → ชีทหลักคำนวณ ✅
- ~~**สร้าง sheet awarded_jobs**~~ — e-bidding ที่ประมูลแล้ว ✅
- ~~**แก้ Doc Downloader**~~ — อ่านจาก `active_bidding` แทน `raw_jobs_bidding` ✅
- ~~**สร้าง Sebastian_Winner_Checker.py**~~ — ดึงชื่อบริษัทผู้ชนะจาก greenBook API W0 ✅

### ต้องทำต่อ (เรียงลำดับ)
1. **รัน Scraper อีกครั้ง** — เพื่อให้ข้อมูลไหลเข้า `active_bidding` และ `awarded_jobs` (2 sheets ยังว่างอยู่)
2. **รัน Winner Checker** (ต้องการ Chrome port 9222) — ดึงชื่อบริษัทผู้ชนะใน `awarded_jobs`
3. **กรอกราคา/หน่วย** ใน `cost_data_By_Dexter` column H → รัน cost step

---

## Checkpoint — 2026-05-10

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Sebastian_LINE_Notify.py**~~ — เขียนเสร็จ (แต่ต้องแก้ใหม่ — ดูด้านล่าง) ⚠️
- ~~**Sebastian_Pipeline.py**~~ — เพิ่ม step notify (step 7/7) ✅
- ~~**work_overview.md**~~ — อัปเดตให้ตรงกับ pipeline จริงปัจจุบัน ✅

### ⚠️ LINE Notify ปิดให้บริการแล้ว (31 มี.ค. 2568)
`Sebastian_LINE_Notify.py` ที่เขียนไว้ใช้ LINE Notify API ซึ่งปิดตัวแล้ว — ต้องเปลี่ยนไปใช้ทางเลือกอื่น

ทางเลือกที่กำลังพิจารณา:
- **LINE Messaging API** — ต้องสร้าง LINE Official Account + รู้ User ID ตัวเอง
- **Telegram Bot** — ง่ายที่สุด ฟรีไม่จำกัด รอการตัดสินใจจากคุณกัญจน์

### ต้องทำต่อ (เรียงลำดับ)
1. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **เลือกระบบ Notify** — LINE Messaging API หรือ Telegram → แก้ `Sebastian_LINE_Notify.py`
3. ~~**รัน Scraper ใหม่** → ให้ active_bidding + awarded_jobs มีข้อมูล~~ ✅

---

## Checkpoint — 2026-05-10 (session 2)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Scraper: เพิ่ม district/subdistrict extraction**~~ — regex ดึง อำเภอ/ตำบล จาก title+department ✅
- ~~**awarded_jobs: เพิ่ม 3 column ผู้ชนะ**~~ — ผู้ชนะประมูล, ราคาที่ชนะ (บาท), วันประกาศผู้ชนะ ✅
- ~~**รัน Scraper**~~ — นครพนม 5,990 / บึงกาฬ 4,510 = 10,500 รายการ, ใหม่ 130 งาน ✅

### ผล Sheets หลังรัน
| Sheet | ผล |
|-------|-----|
| `raw_jobs` | +130 งานใหม่ |
| `awarded_jobs` | +38 งาน (e-bidding ประมูลแล้ว) ← พร้อมรัน Winner Checker |
| `active_bidding` | ยังว่าง — ไม่มี e-bidding กำลังประมูลใหม่ในพื้นที่ตอนนี้ |

### ต้องทำต่อ (เรียงลำดับ)
1. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **รัน Winner Checker** → ดึงชื่อผู้ชนะสำหรับ 38 งานใน awarded_jobs (ต้องการ Chrome port 9222)
3. **เลือกระบบ Notify** — LINE Messaging API หรือ Telegram

---

## Checkpoint — 2026-05-10 (session 3)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**แก้ Classifier ทั้งหมด**~~ — เปลี่ยน filter บ้านแพง/บึงโขงหลง → ทั้งจังหวัด นครพนม+บึงกาฬ ✅
- ~~**เพิ่ม active_bidding + awarded_jobs**~~ ใน Classifier output (clear+rewrite พร้อม preserve winner data) ✅
- ~~**ลบ raw_jobs_all**~~ ออกจาก Classifier (ไม่จำเป็น) ✅
- ~~**แก้ raw_jobs header**~~ — col13: quantity_note→project_status, col14: seq_no→quantity_note ✅
- ~~**แก้ regex district/subdistrict**~~ — เปลี่ยนจาก `[^\s,จ]`/`[^\s,อ]` → `\S+` (ไม่หยุดกลางคำ) ✅
- ~~**รัน Classifier**~~ — ผลครบทุกชีท ✅

### ผล Sheets หลัง Classifier รัน
| ชีท | งาน | หมายเหตุ |
|-----|-----|---------|
| `raw_jobs_related` | 419 | ครอบทั้งจังหวัด (จากเดิม 36) |
| `raw_jobs_bidding` | 15 | e-bidding กำลังประมูล |
| `active_bidding` | 15 | พร้อม Doc Downloader อ่าน |
| `raw_jobs_awarded` | 98 | e-bidding ประมูลแล้ว |
| `awarded_jobs` | 98 | พร้อม Winner Checker อ่าน |
| `raw_jobs_direct` | 292 | เฉพาะเจาะจง |
| `raw_jobs_cancelled` | 12 | ยกเลิก |

### ต้องทำต่อ (เรียงลำดับ)
1. **กรอกราคา/หน่วย** ใน cost_data_By_Dexter column H → รัน `--step cost`
2. **รัน Winner Checker** → ดึงชื่อผู้ชนะ 98 งานใน awarded_jobs (ต้องการ Chrome port 9222)
3. **เลือกระบบ Notify** — LINE Messaging API หรือ Telegram

---

## Checkpoint — 2026-05-11

### เปลี่ยนแผน: ตัด Cost/Rank อัตโนมัติออก

**เหตุผล:** ตัวแปรเยอะเกินไป, cost_data column H ค้างมาตั้งแต่ 1 พ.ค. ไม่ได้กรอก
**แผนใหม่:** pipeline อัตโนมัติหา+แจ้งงาน, พ่อคำนวนเองผ่านชีทที่สร้างขึ้นใหม่

### สิ่งที่ทำสำเร็จวันนี้

- ~~**เปลี่ยน Sebastian_LINE_Notify.py**~~ — จาก LINE Notify API (ปิดแล้ว) → LINE Messaging API ✅
- ~~**ทดสอบ LINE Notify**~~ — ส่ง 15 งานเข้า LINE Group สำเร็จ ✅
- ~~**ยืนยัน Vercel env vars**~~ — LINE_CHANNEL_ACCESS_TOKEN + LINE_GROUP_ID มีอยู่ใน production แล้ว ✅
- ~~**BSC website order notify**~~ — โค้ดมีอยู่แล้วใน send-order/route.ts พร้อมใช้งาน ✅

### Pipeline ปัจจุบัน (แผนใหม่)

```
ส่วนอัตโนมัติ (06:00 น.):
scrape → classify → [Winner Checker แยก] → LINE notify

ส่วน manual (พ่อทำเอง):
รับ LINE → ค้น ID ใน eGP → กรอก W/L/T ในชีทคำนวน → ได้ปริมาณวัสดุ
```

### สถานะ Sheets

| Sheet | งาน | สถานะ |
|-------|-----|-------|
| `active_bidding` | 15 | ✅ พร้อมใช้ |
| `awarded_jobs` | 98 | ✅ รอ Winner Checker |
| `raw_jobs_related` | 419 | ✅ |
| `raw_jobs_direct` | 292 | ✅ |

### ต้องทำต่อ

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ (งานถัดไป)
2. **รัน Winner Checker** — ดึงชื่อผู้ชนะ 98 งาน (ต้องการ Chrome port 9222)

---

## Checkpoint — 2026-05-11 (session 2)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**เปลี่ยนแผน**~~ — ตัด Analyze, Rank, Download ออกจาก pipeline ✅
- ~~**แก้ run_pipeline.bat**~~ — ลำดับถูกต้อง + ตัด step ที่ไม่ใช้ + เพิ่ม LINE Notify ✅
- ~~**ยืนยัน Task Scheduler**~~ — BidMaster-DailyPipeline สถานะ Ready ✅
- ~~**Chrome เปิดอัตโนมัติ**~~ — run_pipeline.bat จัดการเองทุกวัน ไม่ต้องทำเอง ✅

### Pipeline ปัจจุบัน (แผนใหม่ สมบูรณ์)

```
06:00 น. ทุกวัน (Task Scheduler)
  → เปิด Chrome Debug อัตโนมัติ
  → Step 1: Scrape (ใช้ Chrome)
  → Step 2: Classify (ไม่ใช้ Chrome)
  → ปิด Chrome
  → Step 3: LINE Notify → ส่งรายการ active_bidding เข้า LINE Group
```

### พับเอาไว้ก่อน (ยังไม่ทำ)
- Download step — โหลด PDF (รอแผนในอนาคต)
- Analyze step — TOR Analyzer (รอแผนในอนาคต)
- Rank step — จัดอันดับ (รอแผนในอนาคต)

### ต้องทำต่อ
1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ
2. **รัน Winner Checker** — ดึงชื่อผู้ชนะ 98 งานใน awarded_jobs (ต้องการ Chrome port 9222)

---

## Checkpoint — 2026-05-11 (session 3 — ก่อนนอน)

### สถานะระบบ ✅ พร้อมรันตี 6

- เครื่องเปิดอยู่ + เสียบปลั๊ก
- Task Scheduler: Ready — NextRun 11/05/2026 06:00 น.

### Pipeline ที่จะรันตี 6

```
เปิด Chrome อัตโนมัติ
  → Step 1: Scrape
  → Step 2: Classify
  → Step 3: Winner Checker (ดึงชื่อผู้ชนะ awarded_jobs)
  → ปิด Chrome
  → Step 4: LINE Notify → ส่งเข้า LINE Group
```

### ต้องทำต่อ (รอเช้า)
1. เช็ค LINE ว่า Sebastian ส่งผลมาไหม
2. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ

---

## Checkpoint — 2026-05-12

### สถานะระบบ

- Pipeline ตี 6 รันสำเร็จ ✅ (Sebastian แจ้งใน Discord 06:00–06:36 น.)
- LINE Notify ไม่ส่ง ⚠️ — สาเหตุ: ข้อความเกิน 5,000 ตัว (LINE API limit) เพราะ TOP_N=50

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Discord Bot ทำงานได้**~~ — Sebastian_Discord_Bot.py online ✅
- ~~**ask_discord.py two-way test**~~ — GSD ส่งคำถาม → คุณกัญจน์ตอบใน Discord → รับคำตอบได้ ✅
- ~~**แก้ LINE ข้อความยาวเกิน**~~ — ลด TOP_N จาก 50 → 15 + เพิ่ม auto-split (>4,900 ตัว) ✅
- ~~**ทดสอบ LINE ส่งสำเร็จ**~~ — ส่ง 15 งานเข้า LINE Group ✅

### Discord Bot files
| ไฟล์ | หน้าที่ |
|------|---------|
| `Sebastian_Discord_Bot.py` | Bot หลัก — listen ตลอด |
| `ask_discord.py` | GSD ถาม → รอคำตอบจาก Discord |
| `start_sebastian_bot.bat` | รัน Bot + auto-restart |

### ต้องทำต่อ (ก่อน session ถัดไป)

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ
2. ~~**รัน Winner Checker** — ดึงชื่อผู้ชนะ awarded_jobs~~ ✅ (ดูด้านล่าง)
3. **ตั้ง Discord Bot startup** — รัน start_sebastian_bot.bat อัตโนมัติเมื่อเปิดเครื่อง

---

## Checkpoint — 2026-05-12 (session 2 — Winner Checker fix)

### Root Cause: Winner Checker ไม่ได้ชื่อผู้ชนะ

`Sebastian_Winner_Checker.py` เดิมใช้ `greenBook` API (`pageAnnounceType=W0`) → ลองอ่านฟิลด์ `winnerName`, `vendorName`, `companyName`, `announceSubDesc` — **ทุกฟิลด์ null** greenBook มีแค่ metadata ไฟล์ ไม่มีชื่อบริษัทเลย ผล "อัปเดต 82 งานสำเร็จ" ในเช้าวันก่อนคือการเขียน empty string ลง Sheet

### API ที่ถูกต้อง (ค้นพบจาก Angular bundle `egp-aann09-web/594.e5359f451f8e5894.js`)

| Endpoint | ฟิลด์ที่ใช้ | ใช้เมื่อ |
|----------|------------|---------|
| `getContractAvailable?projectId=` | `contractAvailableResponse[0].corporateName` + `contractPrice` + `contractDate` | เซ็นสัญญาแล้ว |
| `getProcureResult?projectId=` | `procureResultDataResponse[].receiveNameTh` (flag P/W/A) + `priceAgree`/`priceProposal` | ประกาศผู้ชนะแล้วแต่ยังไม่เซ็นสัญญา |

Base: `process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement`

### สิ่งที่ทำสำเร็จ

- ~~**เขียนใหม่ `fetch_winner_info()`**~~ — 2-tier: getContractAvailable → fallback getProcureResult ✅
- ~~**ทดสอบ debug_winner_test.py**~~ — 5 งานแรก ✅ ทุกงานได้ชื่อบริษัท ✅
- ~~**รัน Winner Checker เต็ม**~~ — awarded_jobs 79/115 อัปเดตสำเร็จ ✅
- ~~**ลบ debug scripts ชั่วคราว**~~ — ล้าง scripts/ เรียบร้อย ✅

### ผล Winner Checker full run

| Sheet | ผล |
|-------|-----|
| `awarded_jobs` | **79/115 งานได้ชื่อผู้ชนะ** ✅ |
| `raw_jobs_direct` | 300 งานประมวลผล — ส่วนใหญ่ไม่มีข้อมูล (วิธีเฉพาะเจาะจงไม่ผ่าน contract API) |

36 งานที่เหลือใน awarded_jobs ไม่มีข้อมูล — เป็นงานใหม่มาก, ยกเลิก, หรือไม่ผ่านระบบสัญญาปกติ

### Pipeline ปัจจุบัน (สมบูรณ์)

```
06:00 น. ทุกวัน:
  → Step 1: Scrape
  → Step 2: Classify
  → Step 3: Winner Checker (getContractAvailable + getProcureResult)
  → ปิด Chrome
  → Step 4: LINE Notify (15 งาน, auto-split)
```

### ต้องทำต่อ

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ (**สำคัญที่สุด**)
2. **ตั้ง Discord Bot startup** — รัน start_sebastian_bot.bat อัตโนมัติเมื่อเปิดเครื่อง

---

## Checkpoint — 2026-05-13 (session 2)

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Discord Bot startup อัตโนมัติ**~~ — เพิ่ม Windows Registry Run key `HKCU\...\Run\SebastianDiscordBot` → รัน `start_sebastian_bot.bat` ทุกครั้งที่ login (ไม่ต้องการ admin rights) ✅
- ~~**ชีทคำนวนถนน คสล.**~~ — สร้าง sheet `calc_road` ใน Bid Master Spreadsheet ✅
  - กรอกแค่ L (ความยาว) ที่ C5 → เห็นปริมาณวัสดุทันที
  - ตัวแปร: W, L, T, St, Sh, CJ, EJ (มีค่า default แล้ว)
  - ผลลัพธ์: คอนกรีต, ทรายรองพื้น, Wire Mesh, Dowel Bar, Metal Cap, Joint Filler/Sealer, ไหล่ทาง
  - script: `scripts/create_calc_sheet.py`

### Phase 0 — เสร็จสมบูรณ์ ✅

| งาน | สถานะ |
|-----|-------|
| ชีทคำนวน W/L/T → ปริมาณวัสดุ | ✅ `calc_road` sheet พร้อมใช้ |
| Discord Bot startup อัตโนมัติ | ✅ Registry Run key ตั้งแล้ว |

### ต้องทำต่อ (Phase 1)

1. **คุณกัญจน์สร้าง LINE Official Account** (ฟรี ที่ developers.line.biz) → ส่ง Channel Access Token + Channel Secret
2. Sebastian สร้าง Webhook Server (Next.js บน Vercel) รับข้อความจาก LINE + เชื่อม Claude API

---

## Checkpoint — 2026-05-13 (รอบบ่าย — fix pipeline)

### Pipeline 06:00 fail: Chrome ไม่ผูก port 9222 → เสียเวลา 90 นาที

**Root cause:**
- `wmic.exe` ถูกลบใน Windows 11 25H2 (build 26200) → คำสั่ง kill Chrome เก่าใน `run_pipeline.bat` ทำงานไม่ได้แบบเงียบๆ
- `run_pipeline.bat` ลบเฉพาะ `lockfile` แต่ Chrome ใช้ `SingletonLock`/`SingletonCookie`/`SingletonSocket` เป็น lock จริง
- ไม่มี health-check หลัง start Chrome → playwright รอ 3 นาที × 15 รอบ = 45 นาทีต่อ step (Scraper + Winner Checker = 90 นาที)

**สิ่งที่แก้ใน `run_pipeline.bat`:**
- ~~แทน `wmic process delete` (2 จุด) ด้วย PowerShell `Get-CimInstance Win32_Process | Stop-Process`~~ ✅
- ~~เพิ่มลบ `SingletonLock` / `SingletonCookie` / `SingletonSocket` (Chrome lock จริง)~~ ✅
- ~~เพิ่ม health-check `http://127.0.0.1:9222/json/version` (รอสูงสุด 60s, fail fast)~~ ✅
- ~~ใช้ `SET CHROME_OK=1` gate Step 1 (Scraper) และ Step 3 (Winner Checker) — ถ้า Chrome ไม่ขึ้น ข้ามไป Step 2 + Step 4 ยังรันได้ตามปกติ~~ ✅
- ~~แก้ nested `%ERRORLEVEL%` → `if errorlevel 1` (batch parse-time gotcha)~~ ✅

**ผลคาด:** Pipeline พรุ่งนี้ 06:00 ถ้า Chrome ขึ้นไม่ได้ จะ fail fast ใน 60s แทน 90 นาที และยังได้ Step 2 (Classify) + Step 4 (LINE Notify) จากข้อมูลเดิมในชีท

---

## Checkpoint — 2026-05-13

### สิ่งที่ทำสำเร็จวันนี้

- ~~**Complete DEPT_SEARCH_TERMS integration**~~ — เพิ่ม 28 หน่วยงานเข้า main() loop หลัง province loop ✅
  - รอ 60s cooldown ก่อนเริ่ม dept loop
  - wait 15s ระหว่าง dept แต่ละชื่อ (เดิมออกแบบ 30s แต่ลดลง)
  - ไม่กรอง FILTER_KEYWORDS — รับทุกงานจากหน่วยงานเหล่านั้น
  - ยังคง dedup กับ seen_ids

- ~~**Discord step notifications ใน run_pipeline.bat**~~ ✅
  - ส่ง 🚀 เมื่อ pipeline เริ่ม
  - ส่ง ✅/❌ หลังแต่ละ step พร้อมชื่อ log file เมื่อ error
  - เพิ่ม `--notify` flag ให้ `ask_discord.py` CLI

- ~~**Claude Code Stop hook**~~ — เพิ่มใน `~/.claude/settings.json` ✅
  - ping Discord ทุกครั้งที่ Claude ตอบเสร็จ: "✅ Sebastian เสร็จแล้ว — กลับมาดูผลได้เลยครับ"
  - 0 token cost (pure Discord API call)

### เวลารัน pipeline โดยประมาณ
| ส่วน | เวลา |
|------|------|
| Province search (นครพนม + 180s + บึงกาฬ) | ~12–15 นาที |
| Dept search (60s cooldown + 28 หน่วยงาน × 15s) | ~11–13 นาที |
| Classifier + Winner Checker + LINE Notify | ~5 นาที |
| **รวม** | **~28–35 นาที** |

### ต้องทำต่อ

1. **สร้างชีทคำนวน** — พ่อกรอก W/L/T → ได้ปริมาณวัสดุ (**สำคัญที่สุด**)
2. **ตั้ง Discord Bot startup** — รัน start_sebastian_bot.bat อัตโนมัติเมื่อเปิดเครื่อง

---

---

## Pipeline Chrome Connect — Fail-fast (2026-05-13)

### สถานะ: ✅ แก้แล้ว

**ปัญหา:** Pipeline วันที่ 13 พ.ค. เสียเวลา **90 นาที** ไปกับการรอ Chrome
- Step 1 (Scraper) fail หลัง 45 นาที — `RuntimeError: เชื่อมต่อ Chrome ไม่ได้`
- Step 3 (Winner Checker) fail หลัง 45 นาที — error เดียวกัน

**Root cause hypothesis:**
- `run_pipeline.bat` health-check `/json/version` **ผ่าน** (Chrome HTTP ตอบ)
- แต่ playwright `connect_over_cdp()` (CDP WebSocket) **fail** — Chrome ค้าง/zombie
- `connect_browser()` ใช้ playwright default timeout 180s × 15 retries = 45 นาที

**สิ่งที่แก้:**
- ~~`Sebastian_Scraper.py:218-228` connect_browser(): retry 15→3, timeout=5000ms, log exception type~~
- ~~`Sebastian_Winner_Checker.py:121-130` connect_browser(): pattern เดียวกัน~~

**ผลที่คาดหวัง:** ถ้า Chrome connect fail อีก จะ fail ภายใน **~30 วินาที** (เดิม 45 นาที) — ทั้ง pipeline ประหยัด 89 นาทีต่อรอบที่ Chrome พัง

**ยังไม่ได้แก้ (รอสังเกตว่ายังเกิดอีกไหม):**
- [ ] เพิ่ม CDP WebSocket health-check ใน `run_pipeline.bat` (เดิมเช็คแค่ HTTP `/json/version`)
- [ ] เพิ่ม Chrome restart logic เมื่อ connect fail ครั้งแรก

---

## Checkpoint — 2026-05-13 (session — วันยื่นซอง fix)

### สถานะ: ✅ เสร็จสมบูรณ์

**ปัญหา:** `active_bidding` ทั้ง 17 งาน มี `deadline = ""` เพราะ eGP search API ไม่ return วันยื่นซอง

**Root cause ที่ค้นพบ:**
- Search API คืนแค่ metadata, ไม่มี deadline field
- ลอง 20+ API endpoints — ทั้งหมด 404 หรือ no data
- วันยื่นซองอยู่ใน **ไฟล์ PDF ประกาศเชิญชวน** (blob URL) เท่านั้น

**วิธีแก้ที่ทำงานได้จริง (PDF approach):**
1. ค้นหาด้วยชื่อหน่วยงาน (เช่น "สามผง") → interceptAPI response → หา row index ของ pid
2. Click `a.btn-icon` ใน row นั้น → Angular router ไปหน้า detail `/procurement/{encrypted_token}`
3. Click description icon ใน TABLE4 (ประกาศเชิญชวน D0) → TABLE1 โหลด
4. Click `file_download` icon ใน TABLE1 → new page เปิด blob URL
5. `FileReader.readAsDataURL(blob)` → base64 → `pdfplumber.open(BytesIO(...))` → extract text
6. Thai numeral conversion (`๐-๙` → `0-9`) + regex หาวันที่

**ผลการรัน patch_deadlines.py:**
| job_id | วันยื่นซอง | เหลือ |
|--------|-----------|-------|
| 69049366395 | 12/05/2569 | -1 วัน (หมดแล้ว) |
| 69049365887 | 18/05/2569 | +5 วัน ✅ |
| 68119422244 | 28/04/2569 | -15 วัน (หมดแล้ว) |

**วิเคราะห์ 14 งานที่ไม่มี deadline:**

| สาเหตุ | จำนวน | แก้ได้? |
|--------|-------|---------|
| keyword กว้างเกิน (นครพนม/บึงกาฬ/กรุงเทพฯ) → pid อยู่ page 2+ | 5 งาน | ✅ เพิ่ม pagination |
| งานประมูลแล้ว (W0) — ไม่แสดงใน active search | 1 งาน | ❌ deadline ไม่มีความหมายแล้ว |
| ไม่มี D0 ยัง (ยังร่างอยู่/รอประกาศ) | 3 งาน | ❌ ตอนนี้ — pipeline รัน scraper ทุกวันจะจับได้เอง |
| หน่วยงานนอกพื้นที่ (มุกดาหาร) | 2 งาน | ❌ ไม่จำเป็นต้องแก้ |
| keyword ค้นไม่เจอ (งานหมดอายุ/department ไม่ตรง) | 3 งาน | ⚠️ ลอง paginate ก่อน |

**ไฟล์ที่แก้ไข:**
- `scripts/Sebastian_Scraper.py` — rewrite `fetch_deadline_via_pdf()` แทน direct URL approach เดิม
- `scripts/patch_deadlines.py` — rewrite ทั้งหมดด้วย PDF approach + Thai numeral handling

**Pipeline ที่รันวันนี้:**
```
patch_deadlines.py → Classifier → LINE Notify (ส่งสำเร็จ 2 part)
```

LINE แสดง "📆 ยื่นซอง: 18/05/2569  ⏳ เหลือ 5 วัน" สำหรับงาน 69049365887 ✅

**ต้องทำต่อ (ถ้าต้องการ deadline ครบ):**
- [ ] เพิ่ม pagination ใน `fetch_deadline_via_pdf()` — ค้นหาทุก page จนกว่าจะเจอ pid (แก้กรณี keyword กว้างเกิน)

---

## Rate Limit Research & Parallel Batching (2026-05-15)

### สถานะ: ✅ เสร็จแล้ว — Pipeline runtime 2hr → ~45-60 min

### ปัญหาเดิม
Pipeline ใช้เวลา 2 ชั่วโมง (06:00-08:00) ส่วนใหญ่เสียให้ rate limit:
- ~20 hits × 120s = ~40 นาที นอนรอเฉยๆ
- Sequential pagination 1.5s/หน้า × ~600 หน้า/จังหวัด

### วิธีทดสอบ
สร้าง 4 test scripts (ลบทิ้งแล้ว) ทดสอบจริงกับ eGP API:
1. `explore_egp_api.py` — จับ URL pattern + capture announcementToken
2. `test_egp_pagesize.py` — ทดสอบ pageSize parameters ทุกชื่อ
3. `test_egp_burst.py` — หา parallel burst threshold
4. `test_multi_context.py` — ทดสอบว่า rate limit ผูกกับ token หรือ IP
5. `test_rate_threshold.py` — หา sustained rate ที่ปลอดภัย

### สิ่งที่ค้นพบ

**1. PageSize ตายตัว = 10 รายการ/หน้า**
- ทดสอบทุก parameter (pageSize, size, limit, perPage, rows, recordsPerPage, max, count, take, ฯลฯ) → server ignore ทั้งหมด
- ความหมาย: นครพนม 5990 รายการ = 599 หน้า (ไม่ใช่ 300 หน้าที่ 20/หน้า)

**2. Rate limit ผูกกับ IP ไม่ใช่ session token**
- ทดสอบ: สร้าง 2 browser contexts (cookies/tokens แยก)
- หลอม context A ด้วย burst → context B ทดสอบทันที
- ผล: context B โดน rate limit เลย 20/20 → ผูกกับ IP
- ความหมาย: เปิดหลาย contexts ไม่ช่วย ต้องใช้ proxy เท่านั้น

**3. Rate limit threshold: ~100 reqs / 120s window**
- 1 req/s sustained → hit ที่ req 110 (~106s)
- 1.5 req/s sustained → hit ที่ req 100 (~66s)
- 3 req/s sustained → hit ที่ req 80-100 (~28s)
- ความหมาย: ส่งเร็วก็โดนเท่ากับส่งช้า

**4. Parallel burst เร็วมาก (ภายใน threshold)**
- 20 parallel requests พร้อมกัน → 50ms each
- 80 parallel (4 batches) → ผ่านสบาย
- 100+ → เริ่มโดน

### กลยุทธ์ที่ใช้: Burst-then-Wait

แทน sequential 1.5s/หน้า → **burst 80 reqs ใน 5s แล้วรอ 90s** (ให้ requests aged out จาก rate limit window)

```python
BATCH_SIZE      = 20      # 20 parallel/batch
BATCHES_PER_GROUP = 4     # 4 × 20 = 80 reqs/group
GROUP_COOLDOWN  = 90      # รอเต็ม window
RATE_LIMIT_RECOVERY = 90  # ถ้าโดนก็รอ 90s
```

**Effective rate: ~0.84 req/s** (vs 0.5-0.65 req/s ของ sequential + rate limit hits เดิม)

### ผลลัพธ์
- Province 600 หน้า: ~12 นาที (เดิม ~30 นาที)
- Total pipeline: ~45-60 นาที (เดิม 2 ชั่วโมง) = **2-2.5x faster**
- ปริมาณงานเท่าเดิม (ไม่ตัด max_pages ไม่มี early-exit) — ปลอดภัย 100%

### ไฟล์ที่แก้
- `scripts/Sebastian_Scraper.py` — `search_keyword_process5()` rewrite ใช้ parallel batching + ใส่ try/except dept loop
- `scripts/Sebastian_Classifier.py` — เพิ่ม pending_award + tor_review classification
- `scripts/Sebastian_LINE_Notify.py` — ส่ง 2 ส่วน (active + tor_review)
- `scripts/Sebastian_Winner_Checker.py` — เพิ่ม column "% ลดจากราคากลาง"
- `scripts/create_new_sheets.py` — สร้าง pending_award + tor_review sheets (รันแล้ว)
- `run_pipeline.bat` — เพิ่ม wait หลัง kill Chrome + หลัง health-check ผ่าน

---

## Checkpoint — 2026-05-15 (SaaS Roadmap Research Session)

### สิ่งที่ทำในวันนี้

**1. Proxy / Rate Limit Legal Analysis**
- สรุป: proxy bypass = gray area ตาม พ.ร.บ. คอมพิวเตอร์ มาตรา 7
- eGP ไม่มี ToS เป็นลายลักษณ์อักษร แต่ data.go.th มีแค่ static CSV ล้าหลัง 1.5 ปี
- สรุป: ไม่แนะนำ proxy, ไม่คุ้ม risk vs reward

**2. eGP API Sort Order — ทดสอบจริง**
- เขียน `test_sort_order.py` ยิง API กับ Chrome debug port ที่เปิดอยู่
- ผล: **API sort by `announceDate` DESC (ใหม่→เก่า) ยืนยัน 100%**
  - Page 1-5: ทั้งหมด 2026-05-15 (วันทดสอบ)
  - Page 10: 2026-05-14
  - Page 15: 2026-05-13
- พบ outlier: page 1 มี 1 งาน announceDate=2026-05-08 โผล่ขึ้นมา (re-announce)
- ความหมาย: early-exit แบบ date-based ใช้ได้ แต่ต้องมี buffer ≥2 วัน
- คุณกัญจน์ตัดสินใจ: **ไม่ทำ early-exit** (ความเสี่ยงพลาดงาน detection ยาก)
- ลบ test script ทิ้งแล้ว

**3. SaaS Vision & Roadmap 2**
- คุณกัญจน์เปิดเผย business vision: ปล่อยเช่าระบบให้ผู้รับเหมารายอื่น
  - 1,500 บาท/เดือน/จังหวัด/บริษัท
  - เป้า 90 บริษัท × 77 จังหวัด = **6,930 บริษัท** → Revenue ceiling ~10.4M/เดือน
- บันทึก Roadmap 2 เข้า memory (`project_saas_roadmap.md`):
  - **Phase 1 (ปัจจุบัน):** ใช้เอง 2 อำเภอ — stable ก่อน
  - **Phase 2 (Pilot):** 5-10 ลูกค้านครพนม 3-4 สัปดาห์ — 6 ขั้นตอน multi-tenant
  - **Phase 3 (Scale):** Cloud + PostgreSQL + 77 จังหวัด + บริษัท SaaS
- **คุณกัญจน์สั่ง: ยึด Roadmap นี้ ห้ามออกนอกเส้นทาง**
- เพิ่ม Mermaid Flowchart ขนาดกะทัดรัดเข้า roadmap.md

### ไฟล์ที่เปลี่ยน
- `C:\Users\Ace\.claude\projects\C--Bid-Master-System\memory\project_saas_vision.md` — สร้างใหม่
- `C:\Users\Ace\.claude\projects\C--Bid-Master-System\memory\project_saas_roadmap.md` — สร้างใหม่ (Roadmap 2)
- `MEMORY.md` — เพิ่ม 2 entries ใหม่

### สถานะ Pipeline ปัจจุบัน
- Pipeline ทำงาน: 45-60 นาที/รัน, รัน 06:00 น. ทุกวัน
- Phase 1 stable — ไม่มี optimization ค้างอยู่
- รอคุณกัญจน์ตัดสินใจเริ่ม Phase 2 เมื่อพร้อม

---

## Checkpoint — 2026-05-15 (Sheet Redesign — IN PROGRESS)

> **สำหรับ Claude ID ใหม่:** อ่าน `docs/sheet_redesign_plan.md` แล้วทำต่อจาก Phase ที่ค้าง

### เหตุผล
คุณกัญจน์รายงาน: "scrape ดูราบรื่น แต่ใส่ Google Sheet มั่วไปหมด งานหมดวันยื่นซองโผล่ใน active_bidding, ไม่มี reset, ความน่าเชื่อถือตกหนัก"

Inspect 17 sheets เจอ root causes:
- Sheet duplicate / legacy เยอะ (raw_jobs vs raw_jobs_all, ranked_jobs ตัด Ranker ไปแล้ว, dashboard test, ฯลฯ)
- Schema ไม่ consistent (publish_date eng vs วันที่ประกาศ ไทย)
- Classifier ไม่ filter deadline → 7 งาน e-bidding หมดอายุ -1 ถึง -77 วัน ค้างใน active_bidding
- Append-only ไม่มี reset cycle

### การตัดสินใจ (user)
| คำถาม | คำตอบ |
|---|---|
| Backup | local JSON dump (SA ไม่มี Drive quota) |
| tor_review | เก็บไว้ (Phase 2 SaaS) |
| Migration | Big bang — ล้าง+rebuild |
| Scraper | เขียน all_jobs ตัวเดียว → Classifier rebuild derived |

### Phases
| # | Phase | Status |
|---|---|---|
| 1 | Backup → `backups/sheets_2026-05-15_2046/` | ✅ 17 sheets, 11,294 rows |
| 2 | Blueprint → `docs/sheet_redesign_plan.md` | ✅ |
| 3 | สร้าง all_jobs schema (15 cols) | ✅ |
| 4 | Migrate raw_jobs.json → all_jobs | ✅ 8,690 unique rows |
| 5 | แก้ Sebastian_Scraper เขียน all_jobs (upsert) | ✅ |
| 6 | แก้ Sebastian_Classifier state machine | ✅ active=11 / pending=18 / awarded=132 |
| 7 | แก้ LINE_Notify (schema ใหม่), Winner_Checker (cache file), patch_deadlines (all_jobs) | ✅ |
| 8 | ลบชีทเก่า 11 ตัว | ✅ เหลือ 7 ชีท |
| 9 | Test E2E (Classifier + LINE_Notify dry-run) | ✅ |

### ผลลัพธ์สุดท้าย

**Sheet structure (17 → 7):**
- `all_jobs` 8,690 rows — Source of Truth
- `active_bidding` 7 งาน — งานก่อสร้างในพื้นที่ deadline ≥ วันนี้
- `pending_award` 17 งาน — deadline หมด ยังไม่ประกาศผู้ชนะ
- `awarded_jobs` 132 งาน — มี winner data
- `tor_review` reserved (Phase 2 SaaS)
- `calc_road` + `cost_data_By_Dexter` (manual ของพ่อ — ไม่แตะ)

**Scripts ที่แก้:**
| File | เปลี่ยน |
|---|---|
| `Sebastian_Scraper.py` | upsert all_jobs (1 sheet) แทน append 3 sheets |
| `Sebastian_Classifier.py` | rewrite — state machine + clear/rewrite + province + construction filters |
| `Sebastian_LINE_Notify.py` | อ่าน schema ใหม่ (publish_date / deadline / days_remaining) |
| `Sebastian_Winner_Checker.py` | rewrite — เขียน `data/winner_cache_bootstrap.json` แทน sheet ตรง ๆ |
| `patch_deadlines.py` | source = all_jobs, auto-trigger Classifier rebuild |
| `migrate_to_all_jobs.py` (ใหม่) | one-time migration script |
| `build_winner_cache.py` (ใหม่) | bootstrap winner cache จาก backup |

**Pipeline ใหม่:**
```
Scraper          → upsert all_jobs (1 sheet, single source of truth)
Patch deadlines  → fetch missing deadlines → update all_jobs → rebuild
Classifier       → clear+write 3 derived sheets (state machine)
Winner Checker   → update winner_cache.json → rebuild
LINE Notify      → อ่าน active_bidding (clean จาก Classifier)
```

**ปัญหาเดิม → แก้แล้ว:**
- ❌ งานหมดวันยื่นซองโผล่ใน active → ✅ Classifier filter ตาม deadline ทุกครั้ง
- ❌ ไม่มี reset → ✅ clear+rewrite ทุก pipeline run
- ❌ Schema ไม่ consistent → ✅ schema เดียว all_jobs + extra ใน derived
- ❌ ความน่าเชื่อถือตก → ✅ source of truth ตัวเดียว

### Backup
- Local JSON: `backups/sheets_2026-05-15_2046/` (17 sheets, 11,294 rows)
- Drive copy: ผู้ใช้ทำเอง 1 คลิก (File → Make a copy)

---

## Checkpoint — 2026-05-15 (Bug investigation: filter เข้มเกินไป)

> **สำหรับ ID ใหม่:** อ่าน `docs/sheet_redesign_plan.md` + entry นี้

### Bug ที่ user รายงาน
- active_bidding / pending_award มีแต่งานที่ keyword "นครพนม"
- งานที่ scrape ผ่าน dept_search_terms (เช่น "ตำบลโพนทอง", "เทศบาลตำบลศรีสงคราม") หายไป
- มีงานยื่นซองวันนี้ที่พ่อสนใจ — ไม่ขึ้น

### Root cause hypothesis
Classifier filter `is_in_target_province()` หา "นครพนม"/"บึงกาฬ" ใน province + fallback ใน search_keyword/title/department
- งานที่ scrape ด้วย dept_search → search_keyword = "ตำบลโพนทอง" (ไม่มีชื่อจังหวัด)
- province field อาจว่างหรือเป็นชื่อหน่วยงานต้นสังกัด
- ถ้า title + department ก็ไม่มี "นครพนม"/"บึงกาฬ" → ตก filter

### กำลังสืบ
- นับ province distribution ใน all_jobs (e-bidding + กำลังประมูล)
- หาตัวอย่างงานที่ skipped_off_province
- แก้ filter ให้ครอบคลุม dept-source jobs

### Diagnosis
29 e-bidding "กำลังประมูล" ใน all_jobs:
- 20 มี province="นครพนม"/"บึงกาฬ" (ผ่าน filter เก่า)
- 5 search_keyword จาก dept_search (เช่น "เทศบาลตำบลศรีสงคราม", "อบต.ดงบัง"):
  - 2 ตัวเป็น cross-province false match (อบต.ไผ่ล้อม จ.พิษณุโลก, อบต.หนองแวง จ.มหาสารคาม) — ถูกต้องที่ตัด
  - 3 ตัวเป็นงานในนครพนมจริง — ถูกตัดผิด ❌
- 4 อื่น ๆ (มุกดาหาร 3, กรุงเทพ HQ ทำงานในนครพนม 1)

### Root cause
1. `is_in_target_province` ดู province field + fallback "นครพนม"/"บึงกาฬ" string match
2. งาน dept_search มี search_keyword = "เทศบาลตำบลศรีสงคราม" (ชื่อเต็ม) — ไม่มี "นครพนม" → ตก filter
3. ไม่ได้ใช้ `DEPT_PROVINCE_MAP` ของ Scraper (28 entries) เป็น fallback

### Fix (2026-05-15 21:46)
แก้ `Sebastian_Classifier.is_in_target_province()`:
- Case A: `province` ตรงเป้า → True
- Case C: `province` มีค่าแต่ไม่ใช่เป้า → True ถ้า title มี "จ.นครพนม"/"จังหวัดนครพนม" (HQ ทำงานต่างจังหวัด); else False (ตัด cross-province false match)
- Case B: `province` ว่าง → fallback ดู title/dept + DEPT_PROVINCE_MAP key (substring match)

### ผลหลัง fix
| Sheet | ก่อน | หลัง |
|---|---|---|
| active_bidding | 7 | **8** (+1 อบต.ดงบัง) |
| pending_award | 17 | 17 |
| awarded_jobs | 132 | 132 |
| skipped off-province | 93 | 82 |

### หมายเหตุ
- jid=69049235336 (อบต.ดงบัง) — deadline ว่าง → patch_deadlines จะดึงให้รอบถัดไป
- งาน user สนใจที่หาย (อาจเป็น) jid=69049235336 → ตอนนี้อยู่ใน active แล้ว ✅

---

## Setup (ครั้งแรก)

```bash
pip install playwright pymupdf openpyxl anthropic gspread google-auth
playwright install chromium
```

สร้างไฟล์ `.env` ที่ root:
```
ANTHROPIC_API_KEY=sk-ant-...
```
