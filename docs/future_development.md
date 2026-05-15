# Future Development — ไอเดียพัฒนาบริษัท

รวบรวมโดย Sebastian | อัปเดตอัตโนมัติ

---

<!-- 
รูปแบบแต่ละไอเดีย:

## [ชื่อไอเดีย]
**วันที่บันทึก:** YYYY-MM-DD
**ที่มา:** สรุปสั้นๆ ว่าคุณกัญจน์พูดถึงอะไร

### สิ่งที่ต้องทำ
- [ ] ขั้นตอนที่ 1
- [ ] ขั้นตอนที่ 2
- [ ] ขั้นตอนที่ 3

---
-->

## เชื่อมต่อระบบกับ Obsidian
**วันที่บันทึก:** 2026-04-28
**ที่มา:** คุณกัญจน์อยากให้ Bid Master System เชื่อมต่อกับ Obsidian

### สิ่งที่ต้องทำ
- [x] ~~ติดตั้ง Obsidian บนเครื่อง~~
- [x] ~~เปิด `C:\Bid-Master-System` เป็น Obsidian Vault~~
- [x] ~~ติดตั้ง Plugin: Dataview (query ข้อมูลจาก .md แบบ dynamic)~~
- [x] ~~ติดตั้ง Plugin: Tasks (track checklist ข้ามไฟล์ได้)~~
- [x] ~~ติดตั้ง Plugin: Templater (สร้าง template อัตโนมัติ)~~
- [x] ~~ทดสอบ Dataview query ดึงข้อมูลจาก future_development.md และ work_overview.md~~
- [ ] ตั้งค่า backlinks ระหว่างไฟล์ในระบบ
- [ ] ซิงค์ Obsidian Vault กับระบบ (ถ้าต้องการใช้หลายเครื่อง)

---

## Bid Master Pipeline — ระบบดึงและวิเคราะห์งานประมูลอัตโนมัติ
**วันที่บันทึก:** 2026-04-29 | **อัปเดต:** 2026-04-29
**ที่มา:** คุณกัญจน์ redesign pipeline ใหม่เป็น 4-Sheet + แยก ปร.4/5 Parser ออกจาก TOR AI

### Design ปัจจุบัน (4-Sheet Pipeline)
```
Scraper (ดึงงาน + download เอกสาร) → Sheet 1: raw_jobs
ปร.4/5 Parser → JSON  ─┐
TOR AI Analyzer → JSON  ├→ JSON Merger → Sheet 2: job_specs
                         │
Sheet 2 → Cost Filler → Sheet 3: cost_data_By_Dexter
Sheet 3 output → Ranker → Sheet 4: ranked_jobs
```

### สิ่งที่ต้องทำ
- [x] ~~ออกแบบ architecture overview~~
- [x] ~~เขียน `Sebastian_Scraper.py` — ดึงงานจาก gprocurement.go.th (21 keywords)~~
- [x] ~~ค้นพบ API จริงบน process5, แก้ Cloudflare + Angular binding~~
- [x] ~~Filter พื้นที่: บ้านแพง นครพนม + บึงโขงหลง บึงกาฬ~~
- [ ] **Full Run Test** — รัน Scraper จริง + ทดสอบ download ปร.4, ปร.5, TOR
- [ ] เขียน `Sebastian_PR45_Parser.py` — อ่านตัวเลข/ปริมาณจากตาราง ปร.4, ปร.5 → JSON
- [ ] เขียน `Sebastian_TOR_Analyzer.py` — Claude อ่าน TOR → JSON วัสดุ
- [ ] เขียน `Sebastian_JSON_Merger.py` — ผนวก JSON สองอัน → Combined JSON
- [ ] เขียน `Sebastian_Sheet2_Writer.py` — Combined JSON → Sheet 2: job_specs
- [ ] เขียน `Sebastian_Cost_Filler.py` — Sheet 2 → เติม C11–C17 ใน cost_data_By_Dexter
- [ ] เขียน `Sebastian_Ranker.py` — output Sheet 3 → จัดอันดับ Sheet 4
- [ ] อัปเดต `Sebastian_Pipeline.py` ให้รัน script ใหม่ทั้งหมด
- [ ] ตั้ง Windows Task Scheduler รัน pipeline อัตโนมัติ

---

## cost_data_By_Dexter — ระบบคำนวณต้นทุน
**วันที่บันทึก:** 2026-04-29
**ที่มา:** แก้ bug สูตร G column + จัด layout ให้เรียบร้อย

### สิ่งที่ต้องทำ
- [x] ~~วิเคราะห์ bug สูตร G37-G47 (cell ref ไม่ได้ lock $)~~
- [x] ~~Shift rows 48-113 → 37-102 ลบช่องว่าง 11 แถว~~
- [x] ~~อัปเดต SUM/summary formulas ทุกตัว~~
- [x] ~~แก้ #ERROR! row และ typo ท่อระบย~~
- [ ] เพิ่ม FLOOR() ใน CJ formula (ป้องกันทศนิยม)
- [ ] แก้ MATCH("EJ") ให้ระบุ row range ชัดเจน (ป้องกัน match ผิด)
- [ ] ทดสอบ EJ และ CJ case ด้วยข้อมูลจริง

---

## ระบบ Sheet หลายชั้น — แยก raw_jobs ตามประเภทงานและสถานะ
**วันที่บันทึก:** 2026-05-01
**ที่มา:** คุณกัญจน์เห็นว่า raw_jobs รวมงานที่ไม่เกี่ยวข้อง (เช่น ซื้อนม ล้างแอร์) ปนกัน ต้องการแยกชีทให้ชัดเจน

### Design ที่ต้องการ (6 Sheets)

| # | ชื่อชีท | เนื้อหา | วัตถุประสงค์ |
|---|---------|---------|-------------|
| 1 | `raw_jobs_all` | ทุกงานในพื้นที่ (บ้านแพง + บึงโขงหลง) | ตรวจสอบ manual |
| 2 | `raw_jobs_related` | งานที่เกี่ยวกับบริษัท (ทุก procurement_type, ทุกสถานะ) | ดูงานเกี่ยวข้องทั้งหมด |
| 3 | `raw_jobs_bidding` | งานที่เกี่ยวกับบริษัท + e-bidding + กำลังประมูล | **ชีทหลักสำหรับคำนวณ** |
| 4 | `raw_jobs_awarded` | งานที่เกี่ยวกับบริษัท + e-bidding + ประกาศผู้ชนะ/อนุมัติ | วิเคราะห์คู่แข่งในอนาคต |
| 5 | `raw_jobs_direct` | งานที่เกี่ยวกับบริษัท + วิธีเฉพาะเจาะจง | วิเคราะห์คู่แข่ง |
| 6 | `raw_jobs_cancelled` | งานที่เกี่ยวกับบริษัท + e-bidding + ยกเลิก | เผื่อประมูลใหม่ |

### นิยาม "งานที่เกี่ยวกับบริษัท"
งานก่อสร้าง/งานโยธาที่บริษัทรับได้ เช่น:
- ถนนคอนกรีต, ก่อสร้างถนน, ปูคอนกรีต, คอนกรีตเสริมเหล็ก
- ท่อระบายน้ำ คสล., ฝาย, ลาน, Dowel Bar
- (คุณกัญจน์จะเพิ่ม keyword เพิ่มเติมในอนาคต)

### นิยาม status สำหรับแต่ละชีท
- **กำลังประมูล**: announce_type ∈ {IM, D0, ""} และ step_id ไม่ใช่ W/I
- **ประกาศผู้ชนะ/อนุมัติ**: announce_type ∈ {W0, W1, I0, I1}
- **ยกเลิก**: announce_type หรือ step_id มีสถานะ CA/ยกเลิก

### สิ่งที่ต้องทำ
- [x] ~~กำหนด keyword list — ใช้ keyword เดิมจาก Scraper, คุณกัญจน์จะเพิ่มในอนาคต~~
- [x] ~~สร้าง Sheet: raw_jobs_all~~ ✅
- [x] ~~สร้าง Sheet: raw_jobs_related~~ ✅
- [x] ~~สร้าง Sheet: raw_jobs_bidding~~ ✅
- [ ] สร้าง Sheet: raw_jobs_awarded
- [ ] สร้าง Sheet: raw_jobs_direct
- [ ] สร้าง Sheet: raw_jobs_cancelled
- [ ] เขียน `Sebastian_Classifier.py` — อ่าน raw_jobs → จำแนก → populate 6 ชีท
- [ ] อัปเดต `Sebastian_Pipeline.py` ให้รัน Classifier หลัง Scraper
- [ ] migrate pipeline ให้ใช้ raw_jobs_bidding เป็น input แทน raw_jobs

### หมายเหตุ
- e-bidding ในข้อมูลจริง = string `'e-bidding'`
- กำลังประมูล = announce_type ∈ {IM, D0}
- ประกาศผู้ชนะ = announce_type ∈ {W0, W1}
- เฉพาะเจาะจง = procurement_type = `'เฉพาะเจาะจง'`

---

## เพิ่ม Keywords ให้ละเอียดขึ้น
**วันที่บันทึก:** 2026-05-01
**ที่มา:** คุณกัญจน์จะเพิ่ม keyword ใน Scraper + Classifier หลังจาก LINE Notify เสร็จ

### สิ่งที่ต้องทำ
- [ ] คุณกัญจน์รวบรวม keyword เพิ่มเติมที่ต้องการ
- [ ] เพิ่มใน `CONSTRUCTION_INCLUDE` ใน `Sebastian_Scraper.py`
- [ ] เพิ่มใน `CONSTRUCTION_INCLUDE` ใน `Sebastian_Classifier.py` (ให้ตรงกัน)
- [ ] รัน Scraper + Classifier ใหม่เพื่อ refresh ข้อมูล

---

## ดาวน์โหลด TOR สำหรับงาน e-bidding ที่กำลังประมูล
**วันที่บันทึก:** 2026-05-01
**ที่มา:** ดาวน์โหลด TOR เฉพาะงาน raw_jobs_bidding (e-bidding + IM/D0) — มีแค่ ~5-8 งาน/รอบ ทำได้เร็วมาก

### เหตุผลที่คุ้มค่า
- ข้อมูลที่ได้เพิ่ม: concrete grade, wire mesh spec, dowel bar → ทำให้ cost calculation แม่นยำขึ้น
- ใช้เวลาน้อย: ~5-8 งาน × 4 วินาที = ไม่กี่วินาที
- ไม่ต้องทำทุกงาน (601 งาน) — เฉพาะงานที่จะยื่นราคาจริง

### สิ่งที่ต้องทำ
- [ ] สำรวจ detail page ของ e-bidding job — หา section TOR (ขอบเขตงาน/เงื่อนไข)
- [ ] เพิ่มฟังก์ชัน `download_tor()` ใน `Sebastian_Doc_Downloader.py`
- [ ] ดาวน์โหลดเฉพาะงานที่ procurement_type='e-bidding' + announce_type ∈ {IM, D0}
- [ ] อัปเดต TOR Analyzer ให้อ่าน TOR PDF จริง (ไม่ต้อง fallback BOQ Vision)

---

## ranked_jobs — Dashboard เปรียบเทียบงานประมูล
**วันที่บันทึก:** 2026-04-29
**ที่มา:** Sheet 5 ใน architecture — Overview ทุกงาน เรียงลำดับตามความน่าสนใจ

### สิ่งที่ต้องทำ
- [ ] กำหนด scoring criteria (เช่น margin %, confidence, ระยะเวลา, จังหวัด)
- [ ] เพิ่ม column สำหรับ ranked score
- [ ] เพิ่ม filter: แสดงเฉพาะงานที่ margin > X%
- [ ] เพิ่มสถานะ: new / analyzed / bidding / won / lost
- [ ] เชื่อมกับ cost_data_By_Dexter (คลิกเพื่อเปิดดูรายละเอียด)

---
