# Portal Polish B — ไทม์ไลน์งานที่สร้างเอง (รางรถไฟ) + โน้ต

**วันที่:** 2026-06-20
**สถานะ:** design approved (กัญจน์ยืนยัน "เขียน spec แล้วลุยได้เลย")

---

## 1. เป้าหมาย

ในหน้า `/portal/job` (รายละเอียดงาน) เพิ่มส่วน **"ไทม์ไลน์ของฉัน"** ที่ผู้ใช้ **สร้างรายการเองได้ง่ายๆ** — แต่ละรายการ = วันที่ + สิ่งที่จะทำ (เช่น "21 ม.ค. โทรหาช่าง", "22 ม.ค. โทรถามรายละเอียด") แล้วระบบเรียงตามวันที่ แสดงเป็น **รางรถไฟ** (จุด + เส้นแนวตั้ง). เพิ่ม/แก้/ลบ รายการได้. เป็นของแต่ละ user ต่อแต่ละงาน.

**ไม่ใช่** timeline อัตโนมัติจาก lifecycle ระบบ — เป็นแผนงานที่ user จดเอง.

## 2. Success criteria (verifiable)

1. POST add (วันที่+ข้อความ) → กลับมาหน้า job เห็นรายการใหม่บนราง เรียงตาม `entry_date`
2. หลาย entry เรียงจากวันที่เก่า→ใหม่ (asc)
3. POST edit (เปลี่ยนวันที่/ข้อความของ entry ตัวเอง) → ค่าอัปเดต
4. POST delete → entry หาย
5. **Ownership:** edit/delete ของ entry ที่ `customer_id` ไม่ตรง → ไม่มีผล (no-op)
6. token ปลอม/หมดอายุ → หน้า invalid (เหมือน route อื่น); ไม่มี customer → ไม่ crash (ส่วน timeline ว่าง)
7. ข้อความ escape (ทดสอบ `<script>` ไม่หลุด)
8. ไม่มี JavaScript (form POST ล้วน; date ใช้ `<input type="date">` native)

## 3. Schema (ผ่าน `Sebastian_Customer_DB.init_schema()`)

```sql
CREATE TABLE IF NOT EXISTS job_notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER NOT NULL,
    project_id   TEXT NOT NULL,
    entry_date   TEXT NOT NULL,      -- 'YYYY-MM-DD' วันที่ user เลือก (ใช้เรียงราง)
    note         TEXT NOT NULL,      -- สิ่งที่จะทำ
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
```
- เพิ่มใน `init_schema()` (CREATE TABLE IF NOT EXISTS). apply บน VPS ด้วย `init_schema()` (Migration No-Seed — ห้ามรัน script มั่ว)
- หลาย entry ต่อ (customer, project) ได้

## 4. Data layer (`scripts/portal_views.py`) — รับ `conn` เป็น argument (กัน import bms_api)

- `list_job_notes(conn, customer_id, pid) -> list[dict]`
  คืน `[{"id","entry_date","note"}]` เรียง `entry_date ASC, id ASC`. ไม่มี customer/ไม่มี note → `[]`
- `add_job_note(conn, customer_id, pid, entry_date, note) -> None`
  INSERT (`created_at=updated_at=now ISO TH`). ข้ามถ้า `note` ว่างหรือ `entry_date` ไม่ใช่ 'YYYY-MM-DD'
- `edit_job_note(conn, customer_id, note_id, entry_date, note) -> None`
  `UPDATE ... SET entry_date=?, note=?, updated_at=? WHERE id=? AND customer_id=?` (ownership). ข้ามถ้า note ว่าง/date ผิด
- `delete_job_note(conn, customer_id, note_id) -> None`
  `DELETE WHERE id=? AND customer_id=?`
- helper `_valid_date(s) -> bool` (parse 'YYYY-MM-DD' ได้)

## 5. Render (`render_job_page` ใน portal_views — เพิ่มพารามิเตอร์)

`render_job_page(data, token, exp, notes=None) -> str` (notes = list จาก `list_job_notes`; `None`/`[]` = ยังไม่มี)

ต่อท้ายส่วนผู้ยื่น เพิ่ม section:
- หัวข้อ "🚂 ไทม์ไลน์ของฉัน"
- **ฟอร์มเพิ่ม** (บนสุด): `<form method="post" action="/portal/job/note">` hidden `t`,`pid`,`action=add` + `<input type="date" name="entry_date" required>` + `<input type="text" name="note" placeholder="สิ่งที่จะทำ เช่น โทรหาช่าง" required>` + ปุ่ม "➕ เพิ่ม"
- **ราง** (`.rail`): แต่ละ entry (`.rstation`) = จุด (CSS `::before`) + เส้นแนวตั้ง + วันที่ (ไทย) + ข้อความ + ฟอร์มแก้ (date+text prefilled, action=edit, hidden note_id) + ฟอร์มลบ (action=delete, hidden note_id). escape ทุก field
- ถ้า notes ว่าง → "ยังไม่มีรายการ — เพิ่มด้านบนได้เลย"

CSS rail (เพิ่มใน `_CSS`): เส้นแนวตั้ง (border-left) + จุดวงกลม + จัด date/text/ปุ่ม. ไม่มี JS.

## 6. Routes (`scripts/bms_api.py`)

- **แก้ `portal_job_get(t, pid)`:** หลัง verify token → resolve `customer_id` จาก `v[0]` (`SELECT id FROM customers WHERE line_user_id=?`, อาจ `None`) → `notes = portal_views.list_job_notes(conn, customer_id, pid)` (ถ้า customer_id) → `render_job_page(data, t, v[2], notes)`
- **route ใหม่ POST `/portal/job/note`:** อ่าน form (`t, pid, action, note_id, entry_date, note`) → `verify_token(t)`; invalid → `_follow_page_html invalid` → resolve customer_id; ถ้ามี → dispatch `add/edit/delete` ผ่าน portal_views → **`RedirectResponse("/portal/job?t=<t>&pid=<pid>", status_code=303)`**
  - parse form แบบเดียวกับ `follow_post` (`parse_qs` ของ body)
  - customer None → ข้าม write, redirect กลับเฉยๆ

## 7. Edge cases

- note ว่าง / entry_date ไม่ใช่ YYYY-MM-DD → ข้าม (ไม่ INSERT/UPDATE)
- note_id ไม่ใช่ของ customer → WHERE customer_id กัน (no-op)
- customer None (token ไม่ผูกลูกค้า) → timeline ว่าง, write ข้าม
- ข้อความมี `<`/`"` → escape (ทั้งใน text content และ value attribute ของ input)
- entry_date แสดงผลเป็นไทย (reuse `_fmt_date_th`)

## 8. การทดสอบ

- `test_portal_notes.py` (seed sqlite in-memory + job_notes table):
  - add → list คืน 1; add อีกวันก่อนหน้า → list เรียง asc ถูก
  - edit ของตัวเอง → ค่าเปลี่ยน; edit ของ customer อื่น (id เดียวกันแต่ customer ต่าง) → ไม่เปลี่ยน
  - delete ของตัวเอง → หาย; delete ของคนอื่น → ยังอยู่
  - add note ว่าง / date ผิด → ไม่เพิ่ม
  - render_job_page(notes=[...]) → มีหัวข้อ "ไทม์ไลน์", ฟอร์มเพิ่ม, รางมี entry + วันไทย, escape `<script>` ไม่หลุด; notes ว่าง → "ยังไม่มีรายการ"
- `test_portal_routes.py` (เพิ่ม): POST add → 303 + ตามไปเห็น note; POST delete → หาย
- ไม่มี JS → ไม่ต้อง node --check

## 9. Deploy

- scp 3 ไฟล์: `Sebastian_Customer_DB.py` + `portal_views.py` + `bms_api.py`
- รัน `init_schema()` บน VPS (สร้าง job_notes) — `sudo -u bms ... python -c "...init_schema()"`
- restart bms-api + verify import + hash == HEAD
- e2e: POST add ผ่าน handler จริงบน VPS (หรือ insert ทดสอบ + render) → เห็นบนราง
- **Discord:** แจ้ง schema change (`job_notes` เพิ่ม) ตาม protocol

## 10. ออกนอกขอบเขต (ไม่ทำใน B)

- ไม่ merge lifecycle อัตโนมัติจากระบบ (notification_queue) ลงราง — ผู้ใช้สร้างเองล้วน
- ไม่มี reminder/แจ้งเตือนตามวันที่ (แค่บันทึก+แสดง) — เผื่ออนาคต
