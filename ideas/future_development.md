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
