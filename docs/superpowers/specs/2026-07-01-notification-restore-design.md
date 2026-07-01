# Design: คืนพฤติกรรมแจ้งเตือนแบบเดิม (instant + เต็ม + ทั้งจังหวัด + lifecycle labels + สรุป 23:00)

วันที่: 2026-07-01 · สถานะ: **APPROVED (กัญจน์ 2026-07-01) — pre-implementation**
ที่มา: สืบบั๊ก "LINE ส่งงานค้างแค่งานเดียว" → พบงานก่อสร้างทั้งจังหวัดถูกกอง `qualified_digest` ส่งรอบเดียว 23:00 (ช้า + ย่อ) + match_job cut งานบางส่วนหาย. กัญจน์ขอคืนพฤติกรรมเดิม: เจอปุ๊บส่งปั๊บ เต็มรูปแบบ. นี่คือ **สเตจ 1** (ก่อน phase-B category UI — ดู [[project_matching_design]] + `2026-07-01-category-matching-design-DRAFT.md`)

## เป้าหมาย (priority: **ไม่พลาดงาน** = เอียงไป "ส่งไว้ก่อน ไม่ตัดทิ้ง")
1. งานใหม่ในนครพนม+บึงกาฬ (**ทั้งจังหวัด ไม่กรอง** รวมงานนอกสาย) → **ส่งทันที เต็มรูปแบบ** (ชื่องาน + ราคากลาง + deadline + **ลิงก์ดูประกาศ** + **ลิงก์ติดตาม**) — เลิกกองรอ 23:00
2. งานที่ติดตามเลื่อนเฟส → ส่งทันทีที่ตรวจเจอ + **ติดป้ายหัวข้อชัด**: "ประกาศวันยื่นซอง" / "สรุปราคาเบื้องต้น" / "ประกาศผู้ชนะอย่างเป็นทางการ"
3. **23:00 = สรุปประจำวัน** (ไม่ใช่ส่งงาน): วันนี้ส่งกี่งาน + พรุ่งนี้ต้องทำอะไร (งานยื่นซองพรุ่งนี้ **+ โน้ต job_notes/timeline ที่ถึงกำหนด**) + มีงานไหนบ้าง
4. ลบ seed 89-keyword (N+181) — ไม่ใช้แล้ว (= ทั้งจังหวัด)

## Success criteria (วัดได้)
1. งาน D0 ใหม่ใน 2 จังหวัด (ทุกงาน ไม่กรอง) → มี row ใน `notification_queue` ภายในรอบ enrichment ถัดไป (ไม่ค้าง qualified_digest)
2. line-sender ส่งงานนั้นเป็นข้อความเต็ม (มีชื่องาน + ลิงก์ดูประกาศ + ลิงก์ติดตาม) — verify ด้วย **test-send เข้า LINE กัญจน์เอง เปิดดูจริง**
3. งานติดตามที่เลื่อนเฟส (PRELIM/W0/cancelled/deadline) → ส่งพร้อมหัวข้อป้ายถูกต้องครบ 3-4 แบบ
4. 23:00 → ข้อความสรุป (count วันนี้ + todo พรุ่งนี้รวมโน้ต + รายการงาน) ไม่ใช่การส่งงานก่อสร้างแบบเดิม
5. ไม่มีงาน D0 ในพื้นที่ที่ resolve เปิดแล้วถูก `filtered_no_match` ตัดทิ้ง (completeness)
6. `config/matching_preferences.json` ไม่ถูกลบ (ยังใช้ shadow logging ได้) แต่**ไม่ cut** อีกต่อไป

## ⚠️ ข้อจำกัดสำคัญ — LINE QUOTA (ต้องตัดสินใจ)
Free plan = **300 ข้อความ/เดือน**. instant per-job × 4 user:
- งาน D0 ใหม่ ~2-3/วัน × 4 คน = ~8-12/วัน = **~240-360/เดือน**
- + สรุป 23:00 (4/วัน = 120/เดือน) + lifecycle + bidopen เช้า
- **รวม ~400-500+/เดือน → เกิน 300 แน่นอน** → เดือน 24 มิ.ย.ที่ quota เต็มจะเกิดซ้ำ

**นี่คือเหตุผลที่ระบบเดิม batch เป็น digest วันละครั้ง** (4/วัน=120/เดือน พอดี quota). "ไม่พลาดงาน + instant + ทุกคน" **แลกมาด้วย quota**
**ทางเลือก (ต้องเคาะก่อน deploy):**
- (ก) **อัปเกรด LINE เป็น paid plan** (เพิ่ม quota) — ตรง requirement "ไม่พลาด" สุด · **แนะนำ**
- (ข) instant เฉพาะ **followed jobs + งานที่ผ่านหมวด** ส่วนงานทั้งจังหวัดอื่นๆ ยังรวม digest (ประนีประนอม quota)
- (ค) instant ทุกงานแต่ยอมรับว่าพอ quota หมด = ส่งไม่ออกจนสิ้นเดือน (เสี่ยงพลาด — ขัด priority)

## สถาปัตยกรรม / Data flow (ใช้ทางส่งจริง — ไม่ประกอบเอง)
```
discovery (07/13/19) → projects_seen (province_api, นครพนม/บึงกาฬ)
  → enrichment worker (ทุก 2 นาที): resolve deadline → เปิดอยู่?
      → [เปลี่ยน] enqueue_notifications() ทุกงาน (ไม่ cut)  → notification_queue
  → line-sender (ทุก 1 นาที): _is_plain_text_stage → _plain_text_body(ชื่อ) + 📄ดูประกาศ + ⭐ติดตาม → ส่ง
followed jobs → winner-poller (07:15/13:15/19:15/01:15): getProjectDetail/prelim/getProcureResult
  → เลื่อนเฟส → enqueue (followed_bid_open / followed_prelim / followed_winner) → line-sender ติดป้าย
23:00 → Daily_User_Summary [เปลี่ยนเนื้อหา]: recap ไม่ใช่ deliver
```

## Components (แก้อะไรบ้าง)
1. **`Sebastian_Enrichment_Worker.py` `qualify_province_api`** — จุดหลัก: เลิก `is_digest`/`filtered_no_match` cut สำหรับงาน province เปิด → `enqueue_notifications()` ทุกงาน (match_job รันได้แต่ shadow=log เฉยๆ ไม่ drop). ผลคืองานเข้า notification_queue → line-sender ส่ง instant เต็ม (ชื่อ+ลิงก์ครบ อัตโนมัติจากทางเดิม)
2. **`Sebastian_Winner_Poller.py` / line-sender labels** — verify ป้ายหัวข้อครบ: followed_bid_open="ประกาศวันยื่นซองแล้ว", followed_prelim="สรุปราคาเบื้องต้นแล้ว", followed_winner="ประกาศผู้ชนะอย่างเป็นทางการแล้ว" (ส่วนใหญ่มีแล้ว — ตรวจ + เติมถ้าขาด)
3. **`Sebastian_Daily_User_Summary.py`** — เปลี่ยนจาก "ส่ง qualified_digest" เป็น **recap**: (a) นับ delivery_log วันนี้ (b) งาน deadline=พรุ่งนี้ (c) job_notes/timeline ที่ due พรุ่งนี้ (d) รายการงานวันนี้
4. **ลบ seed**: เคลียร์ notes.classes (89-keyword) ของ 5 ราย (idempotent, backup ก่อน) — หรือปล่อยว่าง = ทั้งจังหวัด
5. **env/guard**: line-sender/one-off ต้อง fail-loud ถ้า BMS_FOLLOW_SECRET/ลิงก์ขาด (เลิกกลืน error) — ดู [[feedback_never_bypass_send_path]]

## Testing (completeness-first)
- enrichment: unit — งาน D0 เปิดในพื้นที่ (ทุกประเภท รวมนอกสาย) → เข้า queue ครบ ไม่ถูก cut; งานปิด/นอกพื้นที่ → ไม่เข้า
- **test-send เข้า LINE กัญจน์เอง 1 งานจริง → เปิดดู** ว่ามีชื่อ+ลิงก์ดูประกาศ+ลิงก์ติดตามครบ (บังคับก่อน broadcast — บทเรียน 2026-07-01)
- winner-poller: 3 ป้ายเฟสถูก (มี fixture PRELIM/W0/cancel เดิม)
- daily summary: recap นับถูก + รวมโน้ต due พรุ่งนี้
- shadow ก่อน: รันโหมด log อย่างเดียว 1 วัน ดูว่า "จะ enqueue กี่งาน/วัน" ยืนยัน quota ก่อน enforce

## Rollout
1. เคาะ quota (ก/ข/ค) ก่อน — ถ้า (ก) อัปเกรด LINE ก่อน
2. shadow 1 รอบ (log ปริมาณจริง) → ยืนยันตัวเลข
3. enforce + test-send ตัวเอง → broadcast
4. เก็บ 23:00 recap + ลบ seed

## Out of scope (→ phase-B / ทีหลัง)
- ปุ่มติ๊กหมวดบน Board B (อาคาร/ถนน/ชลประทาน/วัสดุ/อื่นๆ) + notes.categories
- ปรับความถี่ winner-poller (ถ้าอยากไวกว่า 6 ชม.)
- ปรับเวลา discovery 07/13/19 → 07/12/18 (ถ้าอยาก)
