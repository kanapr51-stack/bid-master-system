# Design (DRAFT — ยังไม่ approve): หมวดหมู่งานแบบติ๊กเอา/ไม่เอา แทน keyword-cut

วันที่: 2026-07-01 · สถานะ: **DRAFT — pause ระหว่าง brainstorm** (รอเคาะ mapping + approve; กัญจน์จะกลับมาทำต่อ)
ที่มา: สืบจากบั๊ก "LINE ส่งงานค้างแค่งานเดียว" (N+181 investigation) → พบ enrichment worker `match_job()` โหมด enforce cut งานก่อสร้างจริงบางส่วนเป็น `filtered_no_match` → หายจาก LINE. กัญจน์สั่งเปลี่ยนวิธี: เลิกกรอง keyword ซ่อน → หมวดหมู่ให้ user ติ๊ก

## Decisions ที่ยืนยันแล้ว (จาก brainstorm)
1. **ขอบเขต**: ระบบหมวดคุมทั้ง **board discovery + LINE** (ตรรกะชุดเดียว จบปัญหา board/LINE ไม่ตรงกัน)
2. **หมวด (5)**: 🏢 อาคาร · 🛣️ ถนน · 💧 ชลประทาน · 📦 วัสดุ/ซื้อของ · 🔖 อื่นๆ (= ไม่เข้า 4 หมวดแรก) — "เอาทุกหมวดที่เคยพูดกัน"
3. **กติกา default (สำคัญ กัญจน์ย้ำ)**: **ติ๊ก 0 หมวด = เห็นงานทั้งจังหวัด** (ไม่กรอง); ติ๊ก ≥1 = เฉพาะหมวดที่ติ๊ก
4. งานเข้าได้หลายหมวด (ถนนคอนกรีต = ถนน+วัสดุ) → ติ๊กหมวดใดก็เห็น (OR)
5. **UI = ติ๊กซ้อน 2 ชั้น (nested, กัญจน์ยืนยัน 2026-07-02)**: ติ๊ก**ทั้งหมวด**ได้ (= เลือกทุก keyword ในหมวดนั้น) **และ**กางหมวดออกมาติ๊ก**รายคำ**ในหมวดได้อีกชั้น (fine-grained) — เผื่อคนอยากปรับ keyword เอง. 89 คำเดิม = คลังตัวเลือกที่เอามาจัดลง 5 หมวด (ดู arch ล่าง) → ทั้งหมวดเป็น toggle ก้อน, ข้างในเป็น checkbox รายคำ
   - ⚠️ pref shape ต้องรองรับ 2 ชั้น: `notes.categories: string[]` (แค่ระดับหมวด) **ไม่พอ** → เก็บแบบ `{หมวด: "all" | [selected keywords]}` (ติ๊กทั้งหมวด=`"all"`, ติ๊กบางคำ=ลิสต์คำ) เพื่อ resolve เป็น effective keyword set ตอน match
   - **Layout ที่เลือก (กัญจน์ 2026-07-02): accordion "หมวดพับ + chip แนวนอน"** — ห้ามแนวตั้ง (89 คำยาวเกิน). หน้าตา: แต่ละหมวดเป็นแถวมี checkbox หัวหมวด + ปุ่ม "กาง ▸/▾"; หมวด default พับไว้ (ไม่กินที่); กางแล้วคำโผล่เป็น **chip ตัดบรรทัดเอง** (wrap) แตะเปิด/ปิดรายคำ. ติ๊กหัวหมวด = เลือกทุกคำในหมวด (`"all"`)

## สถาปัตยกรรมที่เสนอ (ยังไม่ approve รายละเอียด)
- **`config/job_categories.json`**: 5 หมวด → ชุด keyword (ยก 89 คำเดิม + material มาจัดลง)
- **`scripts/job_categories.py`** (pure): `categories_of(project_name) -> set[str]` (reuse `job_matcher._kw_hit` guard); ไม่เข้า 4 หมวด → `{"อื่นๆ"}` — ใช้ร่วม board + LINE
- **เก็บ pref**: `notes.categories: string[]` (ว่าง = ทั้งจังหวัด); ลบ 89-keyword seed (N+181) ทิ้ง
- **LINE (เฟส B, เสี่ยง)**: enrichment worker **เลิก cut ด้วย match_job** → qualify งานทั้งจังหวัด + เก็บหมวด; ย้ายตัวกรองไปตอนส่ง (`Sebastian_Daily_User_Summary` + queue) กรองต่อ user ตาม categories (ว่าง=ทั้งจังหวัด) → digest รายวันเหมือนเดิม
- **Board B (เฟส A, ปลอดภัย)**: 5 checkbox หมวด เขียน notes.categories; discovery กรองด้วยหมวดเดียวกัน
- **Rollout 2 เฟส**: A=classifier+config+Board B+discovery (ไม่แตะ LINE) · B=flip LINE (shadow→enforce)

## อัปเดต 2026-07-01 (ทำไปแล้ว + decision ใหม่)
- ✅ **ปิด user Hong** (active=0, id=3 Ucb1758f) — พี่ไม่ดูแล้ว (เก็บ record กู้คืนได้)
- ✅ **ส่ง backlog ฉบับเต็ม ทีละข้อความ** (format_notification เต็ม) ให้ 4 users active: Kan/ณฐมน/Mr.suvit 16 งาน, อัญธิญาน์ 18 งาน + แจ้งนำคนละ 1 = **70 ข้อความ** (quota 91/300). แจ้งนำ: "ตัด keyword ออก รับงานทุกงานในพื้นที่ + ส่งงานย้อนหลัง 24 มิ.ย.–1 ก.ค." dedup: re-send งานที่เคยได้แค่ digest ย่อ (backlog_digest), ไม่ส่งซ้ำงานที่เคยได้เต็ม
- 🆕 **decision: default = "ไม่มี keyword = เห็น/ส่งทุกงานในจังหวัด"** (ไม่ใช่ empty). backlog แบบ per-job ยืนยันแล้ว (กัญจน์เลือก "ทุกงานจริงๆ ทีละข้อความ" รวมงานนอกสาย)

## 🔴 ค้าง phase-B (ต้องแก้โค้ด — ทำ session หน้า)
- **บอร์ด discovery**: ตอนนี้ "ไม่มี keyword = ว่างเปล่า" → ต้องแก้เป็น "= ทั้งจังหวัด (D0/B ทั้งหมด)" ก่อน ไม่งั้นบอร์ดโล่งเมื่อลบ seed
- **LINE going-forward**: enrichment worker เลิก match_job cut → ส่งทุกงานในจังหวัด (เสี่ยง, test shadow ก่อน)
- **ลบ 89-keyword seed** (N+181): ทำพร้อมแก้บอร์ดข้างบน (ลบเดี่ยว=บอร์ดโล่ง)
- แล้วค่อยทำ category UI (checkbox 5 หมวด) ทีหลังสุด

## ค้างต้องเคาะก่อน implement
1. **mapping keyword→หมวด** (ร่าง: เมรุ/หอประชุม/ตลาดสด→อาคาร · ผิวจราจร/แอสฟัลท์/ลาดยาง→ถนน · ฝาย/ขุดลอก/ท่อ/เขื่อน/ตลิ่ง/ประปา→ชลประทาน · คอนกรีตผสมเสร็จ/ลูกรัง/หินคลุก→วัสดุ) — ยังไม่ทำ
2. แบ่ง 2 เฟส หรือรวดเดียว
3. default ลูกค้าเดิม = ไม่ติ๊ก (ทั้งจังหวัด) ยืนยันแล้ว

## บริบทบั๊กที่ทำให้เกิดงานนี้ (อ้างอิง)
- enrichment worker `qualify_province_api` (`Sebastian_Enrichment_Worker.py:426-435`): match_job enforce → cut → `filtered_no_match` (ดรอป)
- construction whole-province → match_job send whole_province_keyword → `qualified_digest` → `Sebastian_Daily_User_Summary` ส่ง digest
- match_job whole_province **cut ทุกงาน ซื้อ** (purchasing_excluded) → material/BSC lead ไม่เคยเข้า LINE (อยู่บน board discovery เท่านั้น)
- ตรวจจริง N+181: กัญจน์ 12 งานเปิดแมตช์ → แจ้ง LINE แค่ 3 พลาด 9 (ซื้อ/แพทย์ตัดถูก ~6, ก่อสร้างตัดผิด ~3)
