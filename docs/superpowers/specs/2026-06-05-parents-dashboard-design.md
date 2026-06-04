# Parents Dashboard — Design Spec

**วันที่:** 2026-06-05
**สถานะ:** design (รอ user review ก่อน writing-plans)
**ที่มา:** กัญจน์ขอเว็บแดชบอร์ดวิเคราะห์ตลาดหมวดงาน ส่งให้พ่อแม่ (เจ้าของ BSC ทรัพย์คอนกรีต + หจก.ยศประทาน) เปิดบนมือถือ

---

## 1. Goal & Audience

หน้าเว็บ **static เดียว เปิดบนมือถือ** สรุปผลวิเคราะห์ตลาดก่อสร้าง (จาก work-type analytics)
ให้พ่อแม่ — **เจ้าของธุรกิจ ไม่ใช่สาย data** — เข้าใจใน 1-2 นาที โดยไม่ต้อง login.

**Success criteria:**
- เปิดบนมือถือได้ทันที (ลิงก์เดียวส่ง LINE), ไม่ต้องล็อกอิน, โหลดเร็ว
- พ่อแม่อ่านรู้เรื่อง: ตลาดใหญ่แค่ไหน / เราอยู่ตรงไหน / หมวดไหนโต-หด / โอกาส
- "สรุปก่อน + กดดูลึกได้" (hero cards → tap ขยายดูตาราง)

## 2. Approach (เลือก A)

**A. Static HTML ฝังข้อมูล** — Python script อ่าน `winner_history.db` → คำนวณ → เขียน
`index.html` ที่ฝังข้อมูลเป็น JSON ในตัว + render ด้วย JS + Chart.js (CDN). Deploy Vercel static.
- snapshot (data ย้อนหลัง static อยู่แล้ว → regenerate เมื่อ backfill ใหม่ โดยรัน script)
- ปฏิเสธ B (fetch Sheet สด = เปราะ/ช้า) และ C (Next.js = หนักเกิน)

## 3. File Structure

| ไฟล์ | หน้าที่ |
|---|---|
| `scripts/build_parents_dashboard.py` | อ่าน DB → คำนวณ size/share/trend → render `index.html` (Jinja-free, f-string + JSON blob) |
| `dashboard/parents/index.html` | **generated** — self-contained: HTML + CSS (mobile-first) + Chart.js CDN + data baked |
| `dashboard/parents/vercel.json` | config deploy static (`cleanUrls`, ไม่ต้อง build) |

**Isolation:** build script = pure (อ่าน DB, เขียนไฟล์, ไม่แตะ Sheet/network). HTML = self-contained
(เปิด offline ได้หลังโหลด Chart.js). คำนวณ reuse logic เดียวกับ `_market_size_sheet.py` /
`_competitor_share_sheet.py` / `_trend_sheet.py` (primary สำหรับ size/share, involvement สำหรับ "เรา").

## 4. Data (คำนวณ build-time จาก winner_history.db, work_type column)

ขอบเขต: งานก่อสร้าง `work_type IS NOT NULL` (52,525 งาน, นครพนม+บึงกาฬ, ปีงบ 2558-2568).

| ส่วน | คำนวณ | ตัวเลขปัจจุบัน (จะดึงสดตอน build) |
|---|---|---|
| Hero | total win_price, จำนวนงาน, ช่วงปี | 46,063 ลบ. / 52,525 งาน / 11 ปี |
| ตลาดตามหมวด | primary × SUM(win_price) + %share | ถนน 55.2%, อาคาร 20.8%, แหล่งน้ำ 9.1%, ราง 3.4%, … |
| อันดับเรา | involvement, อันดับใน merged winners ต่อหมวด | ราง #11, แหล่งน้ำ #18, ถนน #55, อาคาร #180 |
| เทรนด์ | early 2561-62 vs recent 2567-68 %เปลี่ยน | ไฟฟ้า +211%, ดิน +779%, ถนน +69%, แหล่งน้ำ -42%, สะพาน -54% |
| โอกาส | core category ที่ %เทรนด์สูงสุด **และเราไม่เล่น** (our count=0) | ไฟฟ้า/ส่องสว่าง |

> ตัวเลข **ไม่ hardcode** — build script ดึงสดทุกครั้ง (regenerate แล้วถูกต้องเสมอ).

## 5. Page Layout (mobile-first, ภาษาไทย, ธีมเขียว BSC)

1. **Hero** — หัวเว็บ: **"สรุปผลการวิเคราะห์ตลาดงานก่อสร้าง นครพนม-บึงกาฬ ตั้งแต่ปี พ.ศ. [ปีต่ำสุด]-[ปีสูงสุด] จัดทำโดยน้องกัญจน์"** (ช่วงปีดึงสดจาก fiscal_year) · ตัวเลขเด่น **46,063 ล้านบาท** / 52,525 งาน
2. **1️⃣ ตลาดใหญ่แค่ไหน** — โดนัทชาร์ต มูลค่าตามหมวด + ปุ่ม "ดูตารางเต็ม ▸" (expand → ตาราง มูลค่า/%/เฉลี่ยต่องาน)
3. **2️⃣ เราอยู่ตรงไหน** — การ์ดอันดับต่อหมวดที่เราเล่น (ราง #11 เด่น = จุดแข็ง) + expand → ตารางเต็ม (share/อันดับ/เจ้าตลาด)
4. **3️⃣ หมวดไหนโต/หด** — แท่ง + ลูกศร 📈📉 ต่อหมวด + expand → ตารางเทรนด์
5. **💡 โอกาส** — callout เด่น: ไฟฟ้า/ส่องสว่าง โตแรง (เรายังไม่เล่น)
6. **Footer** — "ข้อมูล ณ [build date] · ที่มา CGD/eGP"

**UX:** expand = `<details>`/`<summary>` (native, ไม่ต้อง JS lib). ตัวเลขใหญ่ อ่านง่าย. font ไทย
(Sarabun/Prompt จาก Google Fonts). touch-friendly.

**ธีมสี: ขาว-แดง** (กัญจน์เลือก) — พื้นหลังขาว, accent/หัวข้อ/แท่งชาร์ตสีแดง (`#C62828` แดงเข้มอ่านง่าย,
hover/รอง `#E53935`), ตัวอักษรเทาเข้ม `#222`. โทนสะอาด อ่านสบายตาบนมือถือ.

## 6. Deploy & Privacy

- Deploy: Vercel static (`vercel deploy --prod` ที่ `dashboard/parents/`) → ลิงก์ `*.vercel.app`
- ส่งลิงก์ทาง LINE ให้พ่อแม่
- Privacy: public แบบ unlisted + `<meta name="robots" content="noindex">` (ไม่ขึ้น Google). ข้อมูลคู่แข่ง
  = public record CGD/eGP → ความเสี่ยงต่ำ. รหัสผ่านเบาๆ = optional เพิ่มภายหลัง (YAGNI ตอนนี้)

## 7. Out of scope (YAGNI)

- ❌ login/auth · ❌ live data fetch · ❌ multi-page · ❌ filter interactive · ❌ ทุก 10 tab ดิบ
- ❌ per-customer / SaaS multi-tenant (นี่คือหน้าภายในครอบครัว)

## 8. Resolved (กัญจน์ confirm 2026-06-05)

1. **ธีมสี = ขาว-แดง** (พื้นขาว + accent แดง `#C62828`)
2. **หัวเว็บ** = "สรุปผลการวิเคราะห์ตลาดงานก่อสร้าง นครพนม-บึงกาฬ ตั้งแต่ปี พ.ศ. [min]-[max] จัดทำโดยน้องกัญจน์"
   (ช่วงปีดึงสดจาก data, ปัจจุบัน 2558-2568)
