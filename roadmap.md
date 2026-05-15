# Bid Master System — Roadmap

อัปเดต: 2026-05-07

---

## Vision

```
ปัจจุบัน          →      ระยะสั้น           →      ระยะยาว
Bid Tool              LINE OA Sebastian          Living Knowledge Base
(คำนวณต้นทุน)         (ทุกคนในบริษัทใช้ได้)      (โตตามที่พนักงานใช้จริง)
```

**หลักการหลัก:**
- Sebastian ไม่ได้ถูกออกแบบมาล่วงหน้าว่าจะเก็บอะไร
- ทุกอย่างเกิดจากพนักงานส่งข้อมูลเข้ามา แล้ว Sebastian เรียนรู้และจัดให้เอง
- Sebastian รู้ว่าตัวเองไม่รู้อะไร และถามเพื่อเติมช่องว่างนั้น
- ยิ่งใช้มาก Sebastian ยิ่งรู้จักโรงงานมากขึ้น — โดยไม่มีใครต้องกรอกข้อมูลทีเดียวทั้งหมด

---

## Phase 0 — งานค้างปัจจุบัน

| งาน                                            | ผู้ทำ     | หมายเหตุ                          |
| ---------------------------------------------- | --------- | --------------------------------- |
| กรอกราคา/หน่วย column H ใน cost_data_By_Dexter | คุณกัญจน์ | unblock cost step                 |
| LINE Notify Token                              | คุณกัญจน์ | แจ้งเตือนหลัง pipeline รัน        |
| ซื้อ Domain (bscconcrete.co.th)                | คุณกัญจน์ | ผูก Vercel                        |
| Open Graph Image                               | Sebastian | รูป preview ตอนแชร์ LINE/Facebook |

---

## Phase 1 — LINE OA Sebastian (Foundation)

> เป้าหมาย: Sebastian อยู่ใน LINE พร้อมรับข้อมูลจากทุกคนในบริษัท

### คุณกัญจน์เตรียม
- [ ] สร้าง LINE Official Account (ฟรี)
- [ ] LINE Channel Access Token + Channel Secret

### Sebastian สร้าง
- [ ] Webhook Server (Next.js บน Vercel) รับข้อความจาก LINE
- [ ] เชื่อม Claude API
- [ ] ทะเบียนพนักงาน — ผูก LINE User ID → ชื่อ + Role
- [ ] ระบบลงทะเบียน — พิมพ์ "ลงทะเบียน" ครั้งแรก
- [ ] RBAC — Sebastian เช็ค role ก่อนตอบทุกครั้ง
- [ ] เชื่อม Google Sheets (Knowledge Base ปัจจุบัน)

### หลังจาก Phase 1 เสร็จ
```
✅ ทุกคนคุยกับ Sebastian ได้
✅ จำกัดการเข้าถึงตาม role
✅ คุณกัญจน์สั่ง pipeline ผ่าน LINE ได้
✅ พนักงานส่งข้อมูลอะไรก็ได้ — Sebastian เริ่มเรียนรู้
```

---

## Phase 2 — Adaptive Knowledge Base

> เป้าหมาย: Sebastian เรียนรู้จากพนักงาน จัดระเบียบข้อมูลเอง และถามเมื่อไม่รู้

### 2A — รับข้อมูลและจัดโฟลเดอร์เอง

```
พนักงานส่งข้อมูลอะไรก็ได้
          ↓
Sebastian อ่าน → เข้าใจบริบท → หา folder ที่เหมาะสม
          ↓
     มี folder นี้แล้ว?
     ใช่ → บันทึกเข้าไปเลย
     ไม่ใช่ → สร้าง folder ใหม่ + แจ้งคุณกัญจน์
          ↓
Sebastian จำ pattern → ครั้งต่อไปไม่ต้องถามแล้ว
```

**ตัวอย่าง:**
> ช่างส่งรูปใบเสร็จน้ำมันมาครั้งแรก
> Sebastian: "จัดไว้ใน Fleet/น้ำมัน ได้เลยไหมครับ?"
> ช่าง: "ได้"
> → Sebastian จำ → ครั้งต่อไปบันทึกอัตโนมัติ

---

### 2B — Self-Building Knowledge Base (ถามเมื่อไม่รู้)

Sebastian ตรวจจับสิ่งที่ตัวเองไม่รู้ และถามเพื่อเติมช่องว่าง

```
พนักงานถาม: "ถังน้ำมันในโรงงานเหลือเท่าไหร่?"
                    ↓
Sebastian เช็ค Knowledge Base — ไม่รู้ขนาดถัง
                    ↓
Sebastian ถามกลับ: "ขนาดถังน้ำมันเท่าไหร่ครับ?"
                    ↓
ใครก็ได้ตอบ: "5,000 ลิตร"
                    ↓
Sebastian บันทึกลง KB → ครั้งต่อไปตอบได้เลยโดยไม่ถามซ้ำ
```

ยิ่งพนักงานถามมาก Sebastian ก็ยิ่งรู้จักโรงงานมากขึ้นเรื่อยๆ เอง

---

### 2C — Two-Tier Data Verification (ป้องกันข้อมูลผิดเพี้ยน)

แยกข้อมูลเป็น 2 ประเภท เพื่อให้คุณกัญจน์เป็นด่านกรองข้อมูลสำคัญ

```
Soft Data (ข้อมูลชั่วคราว)     Hard Data (ข้อมูลถาวร)
────────────────────────       ──────────────────────
ใครส่งมาก็บันทึกได้ทันที       Sebastian แจ้งคุณกัญจน์ก่อน
เช่น: น้ำมันวันนี้ 40L          เช่น: ขนาดถัง 5,000L
      ซื้อทรายวันนี้             ค่าแรงต่อวัน
      บันทึกหน้างาน              ทะเบียนรถ/เครื่องจักร
```

**Flow ของ Hard Data:**
```
Sebastian ได้ข้อมูลใหม่ประเภท Hard
                ↓
Sebastian แจ้งคุณกัญจน์ใน LINE ทันที:
"มีพนักงานแจ้งว่าถังน้ำมันขนาด 5,000 ลิตร
 ✅ ยืนยัน  หรือ  ❌ แก้ไข?"
                ↓
คุณกัญจน์ ✅ → บันทึกถาวร
คุณกัญจน์ ❌ และแก้ไข → บันทึกค่าที่ถูกต้อง
```

Sebastian รู้เองว่าข้อมูลไหนเป็น Hard — ไม่ต้องสอนทุกเรื่อง

---

## Phase 3 — Integration & Intelligence

> เป้าหมาย: Sebastian เชื่อมข้อมูลข้ามโฟลเดอร์ + ดึงข้อมูลจากระบบภายนอก

### Integration ที่วางแผน

| ระบบ                        | วิธีเชื่อม       | Sebastian ทำอะไรได้                |
| --------------------------- | ---------------- | ---------------------------------- |
| ระบบลายนิ้วมือ (มีอยู่แล้ว) | Import CSV/Excel | วิเคราะห์ attendance trend         |
| e-GP (มีอยู่ล้วแ)           | Scraper          | ประมูล + Market Intelligence       |
| Google Drive                | API              | เก็บไฟล์ขนาดใหญ่ + ส่งลิงก์ใน LINE |

### Cross-data Intelligence

เมื่อ Knowledge Base สะสมข้อมูลมากพอ Sebastian วิเคราะห์ข้ามโฟลเดอร์ได้:

```
"เดือนที่แล้วต้นทุนน้ำมันต่องานเท่าไหร่?"
→ Sebastian ดึง Fleet + Project Archive มาคำนวณ

"งานบ้านแพงล็อตนี้คุ้มไหมถ้าเทียบกับงานที่แล้ว?"
→ Sebastian ดึง Procurement + Project Archive + Supplier มาเปรียบเทียบ
```

---

## Phase 4 — Deploy to Backup PC

> เป้าหมาย: Sebastian รัน 24 ชม. โดยไม่ต้องพึ่งเครื่องหลัก

```
เครื่องหลัก  →  พัฒนา + ทดสอบเท่านั้น
เครื่องสำรอง →  Sebastian รันตลอด 24 ชม.
```

**ย้ายโดย:** Copy folder + `.env` + `service_account.json`
→ ติดตั้ง Python/Chrome/Playwright → ตั้ง Task Scheduler ใหม่

---

## Phase 5 — Claude Skills (เมื่อ pattern ชัดแล้ว)

> ไม่ได้กำหนดล่วงหน้า — Skill เกิดขึ้นเองเมื่อมี workflow ที่ทำซ้ำบ่อยพอ

```
Sebastian สังเกตว่า "คุณกัญจน์สั่งแบบนี้ทุกวัน"
→ Sebastian เสนอ: "อยากให้ผมสร้าง /ชื่อ-skill สำหรับงานนี้ไหมครับ?"
→ คุณกัญจน์อนุมัติ → Sebastian สร้าง Skill ให้เลย
```

---

## Timeline (ยืดหยุ่น ไม่ lock)

```
Q2 2026  Phase 0 → Phase 1 (Foundation)
Q3 2026  Phase 2A+2B+2C (Adaptive KB + Self-Building + Verification)
Q4 2026  Phase 3 (Integration + Cross-data Intelligence)
Q1 2027  Phase 4 (Deploy Backup PC)
ต่อไป    Phase 5 (Skills โตตาม pattern จริง)
```

> **หมายเหตุ:** Timeline เป็นแนวทาง ไม่ใช่ข้อบังคับ
> แต่ละ Phase เริ่มได้เมื่อพร้อม

---

## วิธีเพิ่มความสามารถใหม่ให้ Sebastian

```
1. คุณกัญจน์หรือพนักงานส่งข้อมูลประเภทใหม่มา
   → Sebastian เรียนรู้และจัดให้
   ─── หรือ ───
   คุณกัญจน์บอก Sebastian ว่า "อยากให้ทำ X"
2. Sebastian แจ้งว่าต้องเตรียมอะไร
3. Sebastian สร้างและเพิ่มเข้าระบบ
```
