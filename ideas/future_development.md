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

---

## [DATA] method_group + กู้ proc_type ที่ shift (จด 2026-06-04)

**งานที่ 1 — คุณกัญจน์สั่งจดไว้ทำทีหลัง**

winner_history มี field `proc_type` (วิธีจัดซื้อฯ) 20 ประเภท แต่ใช้ไม่สะดวก:
- **เพิ่มคอลัมน์ `method_group`** จัด 3 กลุ่ม:
  - `เลือกตรง` = เฉพาะเจาะจง (503K) + ตกลงราคา (40K) + พิเศษ/กรณีพิเศษ (373)
  - `แข่งขัน` = e-bidding (8,436) + ประกวดราคาทางอิเล็กฯเก่า (668) + สอบราคา (1,148) + คัดเลือก (1,289) + e-market (6)  ← **กลุ่มที่ BMS แจ้งเตือนได้**
  - `ไม่ชัด` = แถวที่ proc_type โดน column-shift
- **กู้ 61,510 แถวที่ shift** — ค่า proc_type = "วิธีการจัดหา ประกาศเชิญชวนทั่วไป คัดเลือก เฉพาะเจาะจง" (label leak แบบ L-006). ลอง recover method จริงจาก raw_json field อื่น / announceType. ถ้ากู้ไม่ได้ = mark `ไม่ชัด`
- **คุณค่า:** กรอง "เฉพาะงานแข่งขัน" (ที่ BMS หาให้ได้จริง) แยกจากงานเลือกตรง (เจ้าถิ่น). insight: บริษัทกัญจน์ชนะ 88% แบบเลือกตรง, แค่ 10% e-bidding → BMS = เครื่องมือบุกตลาดแข่งขัน

## [MATCHING] เทรน BMS classifier จากชื่องาน winner 617K (จด 2026-06-04)

**งานที่ 2 — คุณกัญจน์อยากใช้ชื่องาน winner data มาเทรน BMS คัดกรองเก่งขึ้น**

ข้อมูลมี **label พร้อมแล้ว** = field `ชื่อประเภทโครงการ`: จ้างก่อสร้าง 6,825 / ซื้อ 30,883 / จ้างทำของบริการ 11,899
- **💡 killer insight:** กรอง `ชื่อประเภทโครงการ='จ้างก่อสร้าง'` จะตัด false-positive ทั้ง 2 ตัวที่เคยหลุด (เลเซอร์=ซื้อ, อีเวนต์=บริการ) — แม่นกว่าเดา keyword
- **4 วิธีใช้ (เรียงคุ้ม):**
  1. **กรองด้วยประเภทโครงการ** (ต่ำ effort) — ⚠️ ต้องเช็คก่อนว่า **live getProcurementDetail มี field นี้ไหม**
  2. **ขุด keyword/negative** จาก 6,825 งานก่อสร้างจริง เทียบ 28 คำปัจจุบัน (ดูตกอะไร)
  3. **สร้าง eval set** (label=ประเภทโครงการ) → วัด precision/recall matcher
  4. LLM/embedding classifier (future, เข้าใจคำพ้อง)
- **อย่าทำ:** fine-tune (Claude fine-tune ไม่ได้ + YAGNI 5 users) / ML กล่องดำ (ขัด "user พิมพ์ keyword เองได้")
- **ข้อจำกัด:** ชื่องาน train ได้แค่แกน "ใช่ก่อสร้างไหม" — **ไม่ช่วย location** (ตำบล API null = ปัญหาแยก)

## Work-Type Analytics — Phase 2 backlog (กัญจน์สนใจ 2026-06-04)
ต่อยอดจาก taxonomy work_type โดยตรง (มูลค่าธุรกิจสูง):
1. **Market size by work type** — มูลค่า+จำนวนงานรวมต่อหมวด (ทั้งตลาด/ต่อจังหวัด/ต่อปี)
2. **Competitor market share by work type** — ส่วนแบ่งตลาด % ของแต่ละเจ้าต่อหมวด (เราอยู่อันดับไหน)
3. **Work-type trend over time** — เทรนด์งานแต่ละหมวดตามปีงบ (หมวดไหนโต/หด)

หมายเหตุ: ทั้ง 3 ข้อ **พึ่ง classification ที่แม่น** — ดู open issue tie-break (precision สะพาน).

---

## [PORTAL] เว็บ follow = ฐานข้อมูลส่วนตัวของลูกค้า (2026-06-08)

คุณกัญจน์เสนอตอนทำ follow-link: ให้หน้าเว็บ follow กลายเป็น Portal ส่วนตัวต่อ user

- ดู "งานทั้งหมดที่ฉันติดตามอยู่" + สถานะ lifecycle (B0->D0->W0->ประกาศผล)
- พองานถึงประกาศผู้ชนะ -> ข้อมูลผู้ประมูลทั้งหมด (ผู้ชนะ/คู่แข่ง/ราคา) ไปอยู่ในหน้านั้นเลย
- โน้ตส่วนตัวต่องาน (เก็บไว้ว่าอยากจำอะไรเกี่ยวกับงานนี้)

ข้อมูลส่วนใหญ่มีแล้ว (followed_jobs lifecycle + bid_results + closed-loop prediction)
ที่ใหม่ = per-user token + dashboard list + notes table
ตรงกับ project_client_surface_decision (LINE + Web Portal). วางเป็น Phase 2 หลัง follow-link
spec: docs/superpowers/specs/2026-06-08-follow-link-signed-token-design.md (section Future work)

---

## [PRICE] คาดราคาแยกตามประเภทถนน — แอสฟัลท์ติก vs คอนกรีต (2026-06-09)

คุณกัญจน์ชี้: งานถนน 2 ประเภทมี % ลดจากราคากลาง **ต่างกันมาก** → ห้ามรวมกันตอนคาดราคา
- ถนนคอนกรีต ในตำบล X → อ้างอิงเฉพาะถนนคอนกรีตในตำบล X เท่านั้น
- ถนนแอสฟัลท์ติก → อ้างอิงเฉพาะแอสฟัลท์ติกในตำบลเดียวกัน
- = เพิ่มมิติ road_subtype เข้า reference filter (เดิม proc_type=วิธีแข่งราคา + ตำบล)

ก่อนทำต้อง probe ก่อน (evidence-first):
1. classify road_subtype จากชื่องาน (keyword แอสฟัลต์/แอสฟัลท์ติก/ลาดยาง vs คอนกรีต/คสล.) + ตรวจ sample ว่าแยกได้จริง
2. วัด discount เฉลี่ยแต่ละประเภท ว่าต่างกันจริงเท่าไร (ยืนยัน hypothesis ก่อน implement)
3. ค่อย wire เข้า Price Prediction / cgd_intel / closed-loop

memory: project_price_by_road_type · related: project_cgd_market_insight (proc_type filter), project_value_principle

---

## [SUB-2] Competitor Trend Learning Loop (2026-06-09, รอ spec หลัง Sub-1)

กัญจน์ขอ: ทุก W0 → เก็บผล observe เอง (bid_results real-time) ลง DB ต่อยอด cgd_winners (lag เป็นเดือน)
- คำนวณ **เทรนด์ส่วนลดต่อบริษัท**: บริษัทนี้ลดมาก/น้อย/เท่าครั้งก่อน — ทั้งในตำบลเดียวกัน + ข้ามตำบล
- เก็บเทรนด์ลง DB → feed กลับเข้า prediction/intel ครั้งหน้า (บริษัทกำลังลดแรงขึ้น → ปรับคาดราคา)
- = learning loop (สะสม→วิเคราะห์เทรนด์→ป้อนกลับ) คนละ concern จาก notification
- พึ่ง W0 results ที่ Sub-1 (แจ้ง 2 รอบ) ทำให้ไหลเข้ามา
- memory: reference_egp_prelim_summary_api, project_event_centric_queue

## 🐛 Scope-selection bug ใน price predictor (2026-06-12)
- closed-loop จริง: งาน 69059227331 (ถนน อ.บุ่งคล้า) ระบบคาด 1.17–1.23M (ตำบล n=2, ลด 40.3%) แต่จริง 1,334,500 (ลด 33.7%) → หลุดกรอบบน +8.6%
- root cause: select_competitors lock scope ตำบลทันทีเมื่อ distinct winner ≥1; ตำบลนี้มีแค่ 2 งานของ หจก.มงคลธรรม บริษัทเดียว (ลด 43%+37.5% ดุผิดปกติ) → median เบ้
- ถ้าใช้ อ.บุ่งคล้า (n=31, median 32%) → คาด ~1.37M ใกล้จริงมาก
- เทียบ: งาน 69059132412 (อาคาร, scope อำเภอ n=3) คาดแม่น ✅ — ปัญหาอยู่ที่ "ตำบลบางเกินไป" โดยเฉพาะ
- แนวทางที่ค้างเสนอกัญจน์: (a) guard min distinct-winners≥2 + min-n ก่อนใช้ตำบลทับอำเภอ (b) blend ตำบล+อำเภอถ่วงน้ำหนักด้วย n (c) shrinkage ดึง median ตำบลเข้าหาอำเภอเมื่อ n น้อย
- memory: project_scope_selection_bug

---

## ▶ NEXT SESSION (queued 2026-06-20): หน้า "ส่องคู่แข่ง" (company page) — มิติงานประมูล vs เจาะจง + ราคาสูงสุด + filter

**ที่มา:** กัญจน์สั่งระหว่าง backfill บ้านกำลังรัน — "ทำ session หน้า"

**ต้องทำ (หน้า `/portal/company` ใน `portal_views.render_company_page` + `company_profile`/แหล่งใหม่):**
1. **แยกสถิติ งานประมูล (competitive) vs งานเจาะจง (specific)** — จำนวน + มูลค่า แยกตาม proc_type
   - competitive = COMPETITIVE_SET (e-bidding/สอบราคา/คัดเลือก) · เจาะจง/ตกลงราคา = อีกกลุ่ม
2. **งานมูลค่าสูงสุด (overall)** — ชื่องาน + มูลค่า (win_price)
3. **แยก: สูงสุดของประมูล** เท่าไหร่ + **สูงสุดของวิธีอื่นๆ** เท่าไหร่ (2 ตัวเลขแยก)
4. **ตัวเลือก/filter: เลือกดูตามประเภทการจัดซื้อจัดจ้าง** (proc_type) — ให้ user กรอง view ได้

**แหล่งข้อมูล:** ใช้ **`cgd_winners`** (มี proc_type, win_price, budget, project_name ครบทุกวิธี — ไม่ใช่แค่ bid_results ที่เป็นเฉพาะ competitive)
- match บริษัทที่ดูด้วย **ชื่อ** (cgd_winners.winner = bidder_name) เหมือน head_to_head ใช้ our_name
- ระวัง: company_profile ปัจจุบันดึงจาก bid_results (competitive เท่านั้น) → ฟีเจอร์นี้ต้องเพิ่ม query CGD โดยตรง
- หมายเหตุ insight: ของกัญจน์ 282 ชนะ = 79% เจาะจง / 21% แข่ง → การแยกนี้สำคัญมากเชิง positioning

**ไม่ใช่ bug — เป็น feature เพิ่ม** · ทำ inline TDD ได้ (เหมือน head-to-head N+155)
