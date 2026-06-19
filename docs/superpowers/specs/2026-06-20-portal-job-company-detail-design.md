# Portal Phase 2b — หน้า detail งาน + ประวัติบริษัท (Phase 1)

**วันที่:** 2026-06-20
**สถานะ:** design approved (รอ user review spec)
**ขอบเขต:** Phase 1 เท่านั้น (Phase 2 = head-to-head + discount-by-area → defer, ดูท้ายเอกสาร)

---

## 1. เป้าหมาย

เดิม (N+149) การ์ดกลุ่ม "🏆 ประกาศผู้ชนะทางการ" ในหน้า `/portal` กดแล้ว expand ผู้ยื่นแบบ inline.
เปลี่ยนเป็น **กดแล้วเด้งไปหน้า detail แยก** (ย้อนกลับได้) ที่แสดงผู้ยื่นทุกราย + ราคา + ส่วนลดจากราคากลาง
และจากแต่ละผู้ยื่น **กดเข้าดูหน้าประวัติบริษัท** (สถิติ + timeline รายปี + ส่วนลดที่ชอบเสนอ — กราฟ) ที่โตเองตามงานที่ระบบดึงผลเพิ่ม

## 2. Success criteria (verifiable)

1. กดการ์ดผู้ชนะใน `/portal` → โหลดหน้า `/portal/job?t=…&pid=…` แสดงผู้ยื่นครบเท่าจำนวนแถวใน `bid_results` ของงานนั้น
2. หน้า job แต่ละแถวผู้ยื่นกดได้ → `/portal/company?t=…&tin=…` แสดงชื่อบริษัทตรงกับ tin
3. หน้า company: `total_bids` = `COUNT(*)` ใน bid_results ของ tin นั้น, `wins` = `SUM(is_winner)`, win-rate = wins/bids
4. timeline แยกรายปีถูกต้อง: ผลรวม bids ทุกปี = total_bids
5. ทุกหน้ามีปุ่มย้อนกลับที่ใช้ได้จริง (job→/portal, company→job เดิม)
6. token ปลอม/หมดอายุ → หน้า "ลิงก์ไม่ถูกต้อง" (เหมือน `/portal` เดิม)
7. test query + smoke render PASS; ถ้ามี JS → `node --check` ผ่าน

## 3. แหล่งข้อมูล (live บน VPS: `bms_customers.db` SQLite เท่านั้น)

- `bid_results(project_id, bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme, result_flag)` — 5,242 แถว / 1,084 งาน / 1,189 บริษัท (tin ครบ)
- `projects_seen(project_id, project_name, budget, province)` — budget = ราคากลาง
- ❌ ไม่ใช้: Postgres (`bid_history_queries.py`/`db_client` — ไม่ deploy), `winner_history.db` (0 byte บน VPS)

**ปี** ดึงจาก `project_id[:2]` (eGP: 2 หลักแรก = พ.ศ. เช่น `69`→2569). parse ไม่ได้ → bucket "ไม่ทราบปี"
**ส่วนลด** = `(1 - price/budget) * 100` เฉพาะ `budget > 0` (บางงาน budget=0 → ไม่แสดงส่วนลด)

## 4. สถาปัตยกรรม

โมดูลใหม่ **`scripts/portal_views.py`** — query + render 2 หน้านี้ แยกจาก `bms_api.py` (กันบวม + เทสต์อิสระ)
`bms_api.py` เพิ่มแค่ 2 route ที่ verify token แล้วเรียก `portal_views`:

```
@app.get("/portal/job")      # t, pid → HTMLResponse
@app.get("/portal/company")  # t, tin, from(optional) → HTMLResponse
```

verify token ใช้กลไกเดิมของ `/portal` (`follow_token.verify_token` → user).
**กัน circular import:** `portal_views` ไม่ import `bms_api`. route ใน `bms_api` เปิด conn ด้วย `get_conn()` เดิมแล้ว **ส่ง `conn` เป็น argument** เข้าฟังก์ชันของ `portal_views` (data layer รับ conn, ไม่เปิดเอง)

### Data layer (ใน `portal_views.py`)

- `job_detail(conn, pid) -> dict | None`
  คืน `{job:{project_id, name, location, budget}, bidders:[{name, tin, price, agree, is_winner, is_sme, discount}]}`
  bidders เรียง `is_winner DESC, price ASC`; discount = None ถ้า budget≤0
- `company_profile(conn, tin) -> dict | None`
  คืน `{name, tin, is_sme, total_bids, wins, win_rate, provinces:[...], discount_hist:[{lo,hi,count}], discount_avg, by_year:[{year, bids, wins, jobs:[{project_id, name, is_winner, price, discount}]}]}`
  - provinces = distinct `projects_seen.province` ของงานที่บริษัทยื่น (ตัดค่าว่าง)
  - discount_hist = bucket ส่วนลด price_proposal vs budget เป็นช่วง 5% (0–5,5–10,…,≥40) เฉพาะ budget>0
  - by_year เรียงปีใหม่→เก่า; jobs ในปีเรียง project_id DESC

### Render layer (ใน `portal_views.py`)

- `render_job_page(data, token, exp) -> str`
- `render_company_page(data, token, from_pid, exp) -> str`
- ใช้ head/CSS สไตล์เดียวกับ `_portal_page_html` (มือถือ-first, การ์ดขาว). escape ทุก field ด้วย `html.escape`

## 5. หน้า detail งาน (`/portal/job`)

- **ปุ่มบน:** `← งานที่ติดตาม` → `/portal?t=<token>`
- **หัวงาน:** 🏗️ ชื่อ · 🆔 ID · 📍 พื้นที่ (ถ้ามี) · 💰 ราคากลาง X บาท (ถ้า budget>0)
- **ตารางผู้ยื่น:** ลำดับ · `🏆` ถ้าผู้ชนะ · ชื่อบริษัท (เป็นลิงก์→ `/portal/company?t&tin&from=<pid>`) · `🏷SME` · ราคาเสนอ · ส่วนลด% (— ถ้าไม่มี budget); ผู้ชนะไฮไลต์เขียว
- pid ไม่พบใน bid_results → "ไม่พบรายละเอียดงานนี้"

## 6. หน้าประวัติบริษัท (`/portal/company`)

- **ปุ่มบน:** `← กลับไปงาน` → `/portal/job?t&pid=<from>` (ถ้ามี from) ไม่งั้น `/portal?t`
- **หัว:** 🏢 ชื่อบริษัท · 🏷SME · tin
- **การ์ดสถิติ (แถว stat):** ยื่น `total_bids` · ชนะ `wins` · win-rate `win_rate%` · จังหวัด `len(provinces)`
- **กราฟ 1 — ยื่น/ชนะ รายปี:** inline SVG/CSS bar ต่อปี (แท่งยื่น + แท่งชนะซ้อน/คู่) เห็น trend
- **กราฟ 2 — ส่วนลดที่ชอบเสนอ:** histogram CSS bar จาก discount_hist (แกน x = ช่วง%, y = จำนวนงาน) + เส้น/ป้าย discount_avg
- **Timeline แยกรายปี:** ต่อปี header "ปี 2569 — ยื่น N ชนะ M" แล้ว list งาน: ชื่อ (ลิงก์→ `/portal/job?t&pid`) · ✅ชนะ/▫️แพ้ · ราคาเสนอ · ส่วนลด%
- tin ไม่พบ → "ไม่พบประวัติบริษัทนี้"

## 7. แก้การ์ดผู้ชนะใน `_portal_page_html` (bms_api.py)

- **ลบ** inline expand เดิม (N+149): `.more`/`.detail`/`job clickable` toggle + JS `.clickable` handler + การสร้าง bidder table ใน `_card` (won)
- การ์ด won กลายเป็น **ลิงก์** ไป `/portal/job?t=<token>&pid=<pid>` พร้อมป้าย "ดูผู้ยื่นทั้งหมด →"
- `_portal_page_html` ต้องรับ `token` (ปัจจุบันรับแค่ groups, exp) เพื่อสร้างลิงก์ → เพิ่มพารามิเตอร์ `token`
- `job["bidders"]` ใน `_portal_jobs` ไม่จำเป็นต่อหน้า list อีก (detail page query เอง) — คงไว้ได้/เอาออกตอน plan (surgical)
- search bar เดิม (N+148) ยังทำงาน (กรอง `.job`); การ์ด won ที่เป็นลิงก์ต้องยังมี text ให้ search match (ชื่อ/ID อยู่ในลิงก์)

## 8. Edge cases

- budget=0 / price ว่าง → ส่วนลด "—"
- bidder_name ว่าง → "(ไม่ระบุชื่อ)"
- บริษัทยื่นงานเดียว/ไม่เคยชนะ → win-rate 0%, กราฟยังเรนเดอร์ได้ (แท่งเดียว)
- project_id parse ปีไม่ได้ → กลุ่ม "ไม่ทราบปี" ท้ายสุด
- งานผู้ชนะที่ยังไม่มี bid_results (announce W แต่ poll ไม่ได้) → การ์ดยังลิงก์ได้ แต่หน้า job แสดง "ไม่พบรายละเอียด"
- token หมดอายุ → reuse หน้า invalid เดิม

## 9. การทดสอบ

- `test_portal_views.py` (seed SQLite ใน tmp):
  - job_detail: จำนวน bidders, sort ผู้ชนะก่อน, discount คำนวณถูก, budget=0 → None
  - company_profile: total_bids/wins/win_rate, by_year ผลรวม=total, discount_hist bucket ถูก, provinces dedup
  - render smoke: หน้า job มีลิงก์ company + ส่วนลด; หน้า company มี stat + กราฟ (มี `<svg`/bar) + timeline รายปี; escape ทำงาน
- ถ้ามี JS (กราฟ inline ไม่ต้องมี JS — bar เป็น CSS width) → ไม่มี JS ใหม่; ถ้ามี ใช้ `node --check`

## 10. Deployment

- เพิ่มไฟล์ใหม่ `portal_views.py` → ต้อง scp **ทั้ง `bms_api.py` + `portal_views.py`** ขึ้น VPS แล้ว `systemctl restart bms-api`
- verify content == HEAD (normalize CRLF `tr -d '\r'`) + render หน้าใหม่กับ user/tin จริงบน VPS

## 11. Phase 2 (defer — ต้องวางรากก่อน)

- **มุมเทียบกับ "เรา" (multi-tenant):** ต้องเพิ่ม field map `customers → บริษัทของ tenant` (tin/ชื่อ) + ถามตอน onboarding ก่อน ถึงจะรู้ว่า "เรา" คือใคร
- **ส่วนลดแยกอำเภอ→ตำบล:** งานใน bid_results มีพิกัดแค่ ~7/1,084 → ต้อง parse อำเภอ/ตำบลจากชื่องาน (province_extraction style) ให้ครอบคลุมก่อน
