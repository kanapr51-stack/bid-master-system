# Future Development Ideas

---

## [FEATURE] Role-Based Access Control (2026-05-07)

จำกัดการเข้าถึงข้อมูลตาม role ของแต่ละคน — Sebastian เช็ค role ก่อนตอบทุกครั้ง

### วิธีทำงาน

- เก็บ "ทะเบียนพนักงาน" ใน Google Sheet ผูก LINE User ID → ชื่อ + Role
- พนักงานลงทะเบียนครั้งแรกโดยพิมพ์ "ลงทะเบียน" ใน LINE OA (ทำครั้งเดียว)
- Sebastian ดึง role ของผู้ส่งทุกครั้งก่อนตอบ

### Role Structure (ร่าง — รอคุณกัญจน์กำหนดตำแหน่งจริง)

| Role | ดูได้ | ทำได้ |
|------|-------|-------|
| owner | ทุกอย่าง | ทุกอย่าง รวมถึงสั่ง pipeline |
| lead (หัวหน้างาน) | attendance ทั้งทีม, รายงานต้นทุน | บันทึกข้อมูลทีม |
| staff (ช่าง/คนงาน) | ข้อมูลตัวเอง | บันทึกตัวเอง (น้ำมัน, มางาน) |

### หมายเหตุ
- Role structure จริงรอคุณกัญจน์กำหนดตำแหน่งในบริษัทก่อน
- ระบบนี้เป็นส่วนหนึ่งของ LINE OA Sebastian

---

## [BIG VISION] Bid Master System → Company OS (2026-05-07)

คุณกัญจน์ต้องการยกระดับ Bid Master System จาก "ระบบคำนวณต้นทุน" → **คลังความรู้ของบริษัท** ที่ครอบคลุมทุกด้าน

### โครงสร้าง Module ที่วางแผน

```
📦 Bid Master System — Company OS
├── 🏗️  Module 1: Procurement Intelligence (ปัจจุบัน)
│         งานประมูล e-GP, ต้นทุน, ranking
│
├── 📊  Module 2: Market Intelligence
│         ราคาตลาดจริงในพื้นที่, คู่แข่งที่ชนะบ่อย, BOQ benchmark
│
├── 👷  Module 3: HR & Attendance
│         สถิติมา/ขาด/ลา, ค่าแรงจริงรายคน, ประวัติพนักงาน
│
├── 🚛  Module 4: Fleet & Fuel
│         สถิติการใช้น้ำมัน, บันทึก maintenance, ชั่วโมงเดินเครื่อง
│
├── 🧱  Module 5: Supplier & Materials
│         ราคาวัสดุที่ซื้อจริง, ซัพพลายเออร์ที่ใช้, ประวัติราคา
│
└── 📁  Module 6: Project Archive
          งานที่ทำเสร็จแล้ว, กำไร/ขาดทุนจริง, บทเรียนที่เรียนรู้
```

### Workflow การเพิ่ม Module ใหม่

> คุณกัญจน์บอก Sebastian ชื่อ Module
> Sebastian วิเคราะห์ → แจ้งว่าต้องเตรียมไฟล์/เอกสารอะไรบ้าง
> คุณกัญจน์เตรียมไฟล์ → Sebastian ออกแบบ + สร้างระบบ

### ข้อมูล 2 ชั้นที่ AI จะใช้

- **External**: ข้อมูลจากเว็บ (e-GP, ราคากลาง, ผลประกาศ)
- **Internal**: ข้อมูลภายในบริษัท (ราคาจริง, คนงาน, เครื่องจักร)
- **Cross-module retrieval**: AI ดึงความรู้ข้ามโมดูลเพื่อให้การวิเคราะห์แม่นขึ้นเรื่อยๆ

---

## [BIG VISION] LINE OA Sebastian — Company AI Interface (2026-05-07)

ให้ทุกคนในบริษัทสามารถคุยกับ Sebastian และอัปเดตข้อมูลได้ผ่าน LINE

### Architecture

```
พนักงาน/หัวหน้า/คุณกัญจน์
        ↓ (LINE OA — แยก chat ส่วนตัว แต่ข้อมูลรวมที่เดียว)
Sebastian (Claude API + Webhook Server บน Vercel)
        ↓
Bid Master Knowledge Base (Google Sheets + Google Drive)
```

### สิ่งที่ทุกคนทำได้ผ่าน LINE

**Input (ส่งเข้าระบบ):**
- พิมพ์ข้อความ: "วันนี้ใช้น้ำมัน 40 ลิตร รถ TK-1"
- ส่งรูปภาพ: ใบเสร็จ, รูปหน้างาน → Sebastian อ่านด้วย Vision
- ส่งไฟล์: PDF, Excel → Sebastian parse + บันทึก

**Output (รับจากระบบ):**
- ข้อความ / ตาราง
- รูปภาพ (กราฟ, summary)
- ลิงก์ Google Drive (เอกสารที่ Sebastian เตรียมให้)
- Flex Message (การ์ดสวยๆ)

### Use Cases หลัก

| ใคร | พิมพ์ | Sebastian ทำ |
|-----|-------|-------------|
| ช่าง | "มาทำงานแล้วครับ" | บันทึก attendance + เวลา |
| ช่าง | รูปใบเสร็จน้ำมัน | Vision อ่านตัวเลข → Fleet Sheet |
| หัวหน้า | "งานประมูลอาทิตย์นี้?" | ดึง ranked_jobs มาสรุป |
| คุณกัญจน์ | "งาน 69049122041 อยากประมูล เตรียมเอกสารให้" | สร้างไฟล์ → ส่ง Drive link |
| คุณกัญจน์ | "กำไรเดือนที่แล้วเท่าไหร่?" | วิเคราะห์ข้ามโมดูล → ตอบ |

### ข้อจำกัด LINE OA

- ส่ง PDF/Excel โดยตรงไม่ได้ → ใช้ Google Drive link แทน
- Free tier มี message quota → ถ้าใช้เยอะอาจเสีย LINE Messaging API fee (ราคาถูก)

---

## [PLAN] Deployment — เครื่องหลัก → เครื่องสำรอง (2026-05-07)

### กลยุทธ์ 2 เครื่อง

```
เครื่องหลัก  → พัฒนา feature ใหม่ (VS Code + Claude Code)
เครื่องสำรอง → รัน Sebastian 24 ชม. (ไม่ต้อง sleep, เชื่อมเน็ตตลอด)
```

### สิ่งที่ต้องย้ายเมื่อ deploy จริง

| อะไร | วิธี |
|------|------|
| `C:\Bid-Master-System\` | Copy folder |
| `.env` (API keys) | Copy ไฟล์ |
| `service_account.json` | Copy ไฟล์ |
| Python + pip packages | `pip install` ใหม่ |
| Chrome + Playwright | ติดตั้งใหม่ |
| Windows Task Scheduler | ตั้งใหม่ |
| Google Sheets | ไม่ต้องย้าย (cloud อยู่แล้ว) |

### Timeline

1. ตอนนี้ → สร้าง + ทดสอบบนเครื่องหลัก
2. พร้อม deploy → Copy ไปเครื่องสำรอง + ทดสอบซ้ำ
3. รันจริง → เครื่องสำรองเปิดทิ้งไว้ตลอด

---

## [INTEL] Procurement Lifecycle Duration Analytics (ChatGPT, 2026-05-25)

เมื่อ transitions_history.ndjson สะสมข้อมูลพอ จะ query ได้:

### time_between_states

`
P0 → M03 = avg 14 days
M03 → W03 = avg 21 days
W03 → awarded = avg 7 days
`

### Intelligence ที่ได้

| คำถาม | ประโยชน์ |
|---|---|
| stage ไหนนานสุด | procurement intelligence |
| agency ไหนช้า | analytics insight |
| average award lag | customer value |
| cancellation pattern | bid strategy |

### Implementation (future, เมื่อมี Universe B data)

1. aggregate transitions_history.ndjson ตาม job_id
2. sort by timestamp → คำนวณ duration per stage
3. group by agency / procurement_type / province

**Why:** BMS จะตอบได้ว่า "งานประเภทนี้ปกติประกาศผู้ชนะภายในกี่วัน" — procurement intelligence moat

---

---

## [STRATEGIC] LINE-first → LIFF/Web Portal → แอพ native (2026-06-02)

คำถามคุณกัญจน์: "จะทำเป็นแอพเลยดีมั้ย" (ถามไว้ก่อน)

### ข้อสรุป: แอพ native ยังไม่คุ้มตอนนี้ — ลำดับที่ควรเดิน
1. **LINE OA (now)** — user อยู่ใน LINE อยู่แล้ว, zero install friction, push cost แค่ 0.4% รายได้
2. **LIFF / Web Portal เปิดในLINE** — rich UX (dashboard, ติดดาวงาน, คลังเอกสาร, filter) โดยไม่ต้องโหลดแอพ
3. **แอพ native** — เฉพาะเมื่อชน limit จริง (offline, background scan, push หนัก, user ขอเอง)

### เหตุผลไม่ทำแอพก่อนพิสูจน์ value
- ผู้รับเหมาต่างจังหวัด/สูงวัย = friction โหลดแอพสูง → user หาย
- dev cost iOS+Android+store+maintenance สูง
- retention แอพที่ไม่เปิด = ถูกลบ

### LINE OA pricing reference (ไทย, ส.ค.2024)
Free 300 / Basic 1,280บ 15,000 / Pro 1,780บ 35,000 / เกิน +0.10บ/ข้อความ. นับ per-recipient. carousel = lever ลดจำนวนข้อความ

---

## [FEATURE] Multi-Stage Notification Roadmap — ขยายจาก D0 (2026-06-04)

ที่มา: กัญจน์ถาม "เราแจ้งเตือน D0 อย่างเดียวใช่มั้ย" → ใช่ (verify: RSS `NOTIFY_TYPES={"D0"}` + province discovery `announceType=2`). กัญจน์จัดลำดับ priority การขยาย

### ลำดับเวลาจัดซื้อภาครัฐ
```
U0 ร่าง TOR/ประชาพิจารณ์ → P0 แผนจัดซื้อ → D0 เปิดยื่นซอง(ตอนนี้แจ้ง) → W0 ผู้ชนะ
```
*(หมายเหตุ: ตามเวลาจริง P0 แผน มาก่อน U0 ร่าง — แต่ priority การ "ทำ feature" กัญจน์เลือกตามคุณค่า ไม่ใช่ตามเวลา)*

### 🎯 Priority ที่กัญจน์สั่ง (2026-06-04): U0 → P0 → W0

**1️⃣ U0 — รับฟังประชาพิจารณ์ / ร่าง TOR** (ทำก่อน — actionable สุด)
- = ร่างประกาศ+ร่างเอกสารประกวดราคา เปิดให้วิจารณ์ ~3 วันก่อนเปิดจริง (catalog: stepId U03, sheet tor_review)
- **value:** เห็น**สเปกงานจริง**ก่อนเปิด → เตรียม BOQ/ราคา/คน + **ถ้าสเปกล็อกไม่เป็นธรรม ทักท้วงได้** (สิทธิ์ตามระเบียบ) = ได้เปรียบจริง ไม่ใช่แค่รู้ก่อน
- ⚠️ feasibility: RSS scraper ปัจจุบันยังไม่เห็น U0 ใน STAGE_CODES (ดึง D0/B0/W0/D1/P0) → ต้องเช็คว่าดึง U0 ได้ไหมตอน implement

**2️⃣ P0 — แผนการจัดซื้อจัดจ้าง** (รู้ไกลสุด)
- = หน่วยงานประกาศแผนว่าจะซื้ออะไรปีงบนี้ (code: `"P0": "pre_tor"`, sheet pre_tor "ขั้นวางแผน")
- **value:** วางแผนกำลังคน/วัสดุล่วงหน้าหลายเดือน · แต่ยังไม่มีสเปก/ไม่แน่ว่าเปิดเมื่อไหร่
- ⚠️ ตอนนี้คิว 0 P0 items (verify title จริงไม่ได้ — อ้าง code comment) · ไม่มี deadline → template แยก

**3️⃣ W0 — ประกาศผู้ชนะ** (competitive intelligence)
- = ใครชนะ ราคาเท่าไหร่ (มี winner cache อยู่แล้ว, คิวมี W0 1886 items)
- **value:** วิเคราะห์คู่แข่ง + ตั้งราคารอบหน้า (รู้ว่าเจ้าไหนชนะที่ราคาเท่าไหร่ในพื้นที่)

### ข้อควรระวังรวม
- แต่ละ stage **template ต่างกัน** (U0=ร่าง/วิจารณ์ได้, P0=แผนไม่มี deadline, W0=ผลชนะ) — ห้ามใช้ template D0 ซ้ำ
- filter พื้นที่+keyword ทุก stage (กัน spam)
- **defer จน beta D0 พิสูจน์ value ก่อน** (D0 core ต้องนิ่ง) → แล้วทำตามลำดับ U0→P0→W0
