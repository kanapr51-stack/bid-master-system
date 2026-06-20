# Portal Interest Star (⭐ ที่สนใจ) — Design

**Date:** 2026-06-21
**Status:** Approved by กัญจน์ 2026-06-21

## Problem

ใน BMS Bid Board (`/portal`) ตอนนี้มี ⭐ อยู่แล้ว 1 ความหมาย — กดในข้อความ LINE เพื่อ**เริ่มติดตามงาน** (เข้า `followed_jobs`). กัญจน์ต้องการ **จุดสนใจพิเศษอีกชั้น** ภายในกลุ่มงานที่ติดตามอยู่แล้ว เพื่อกรองดูเฉพาะงานที่สนใจที่สุด — คนละความหมายกับ ⭐ เดิม ห้ามสับสนกัน.

## Data Model

ตารางใหม่ `job_stars` — **ไม่ใช่คอลัมน์ใหม่ใน `followed_jobs`**:

```sql
CREATE TABLE IF NOT EXISTS job_stars (
    customer_id INTEGER NOT NULL,
    project_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (customer_id, project_id)
)
```

เหตุผลแยกตาราง: `followed_jobs.starred_at` มีความหมาย "วันที่เริ่มติดตาม" อยู่แล้ว (⭐ เดิมจาก LINE postback `star:<project_id>`). ถ้าฝาก flag ใหม่ในตารางเดียวกันชื่อใกล้กัน จะงงเองตอนแก้ทีหลังว่า star ไหนคือ star ไหน. แยกตารางชัดกว่า ต้นทุนแค่ join เพิ่ม 1 จุด.

Migration เพิ่มใน `Sebastian_Customer_DB.py` (`_migrate_vX` ใหม่ + bump schema version).

## Toggle Mechanism

ไม่มี JS/fetch ในระบบนี้เลย — ทุกอย่างเป็น server-rendered link ล้วน. Toggle ก็เช่นกัน:

- Route ใหม่: `GET /portal/star_toggle?t=<token>&pid=<project_id>&back=board|job`
- ตรวจ token (`follow_token.verify_token`) → หา `customer_id` จาก `line_user_id` → ถ้ามีแถวใน `job_stars` อยู่แล้วลบ, ถ้าไม่มีก็ insert (`created_at` = now TH tz)
- `back` validate ต้องเป็น `"board"` หรือ `"job"` เท่านั้น (ไม่ใช่ open redirect — ไม่รับ URL ใดๆจาก query ตรงๆ)
- 302 redirect: `back=board` → `/portal?t=<t>` · `back=job` → `/portal/job?t=<t>&pid=<pid>`
- กดดาว = หน้า reload เห็นสถานะใหม่ทันที ไม่ต้องเขียน client-state sync

ไม่ guard ว่า `project_id` ต้องอยู่ใน `followed_jobs` ของ customer นั้นก่อนถึง star ได้ (YAGNI) — ปุ่มโชว์เฉพาะหน้าที่เห็นงานอยู่แล้ว, ข้อมูลเป็นของ customer คนนั้นเองอยู่แล้ว เสี่ยงต่ำ.

## UI Changes

### Bid Board card (`scripts/bms_api.py::_portal_page_html`, `_card`)

โครงสร้างการ์ดปัจจุบันคือ `<a class="job joblink">` ห่อทั้งใบ — ใส่ `<a>` ดาวซ้อนข้างในไม่ได้ (nested `<a>` ผิด HTML). เปลี่ยนเป็น:

```
<div class="job">
  <a class="star" href="/portal/star_toggle?t=..&pid=..&back=board">⭐|☆</a>
  <a class="joblink" href="/portal/job?t=..&pid=..">
    ...เนื้อการ์ดเดิมทั้งหมด...
  </a>
</div>
```

`data-starred="1|0"` อยู่บน `.job` div (ใช้กับ JS filter ด้านล่าง) — มาจาก DB ตรงทุกครั้งที่โหลดหน้า ไม่มี state ค้าง.

### Job detail page (`scripts/portal_views.py::render_job_page`)

ปุ่มดาวเดียวกัน ต่อจาก header ชื่องาน (หลัง `<div class="h">🏗️ ...</div>`) — `href` ใช้ `back=job&pid=...`.

### Filter chip "⭐ ที่สนใจ"

Toggle อิสระ **ไม่รวมกับ** กลุ่ม single-select เดิม (ทั้งหมด/ยื่นซอง/สรุปราคา/ประชาวิจารณ์/ผู้ชนะ). JS เดิม (`_portal_page_html` script tag) เพิ่มตัวแปร `starOnly` (bool, toggle เมื่อคลิกชิปดาว) แล้ว AND เข้ากับเงื่อนไข filter ที่มีอยู่ (search text + stage `sel`):

```js
var hit = (!s || text-match) && (sel==='all'||sel===k) && (!starOnly || card.dataset.starred==='1');
```

## Data Flow ใหม่ที่ต้องเพิ่ม

1. `portal_views.py` ต้อง expose helper อ่าน starred project_id set ของ customer คนหนึ่ง เช่น `starred_project_ids(conn, customer_id) -> set[str]`
2. `bms_api.py::_portal_jobs` — หลัง build `groups` dict แล้ว ใส่ `job["starred"] = pid in starred_set` ให้ทุก job
3. `_portal_jobs` ต้อง pass `cid` (customer_id) ไปด้วย เพื่อให้ `_portal_page_html` สร้างลิงก์ toggle ได้ (หรือคำนวณ set นี้ตั้งแต่ตอนเรียก `_portal_jobs` แล้วส่งต่อ — รายละเอียดเป็น implementation detail)
4. `portal_job_get` (route `/portal/job`) ต้อง query `job_stars` ด้วยเพื่อรู้สถานะดาวของ job เดียวที่กำลังดู แล้วส่งเข้า `render_job_page`

## Testing / Sanity

- `scripts/test_portal_stars.py` (แพทเทิร์นเดียวกับ `test_portal_notes.py`) ครอบคลุม:
  - toggle ครั้งที่ 1 = insert, toggle ครั้งที่ 2 = delete (กลับสถานะเดิม)
  - customer คนละคน star งานเดียวกันไม่กระทบกัน (cross-customer isolation)
  - ไม่มี duplicate (customer_id, project_id) — PK กันอยู่แล้วระดับ DB
- Sophia sanity audit ก่อน commit (ตาม CLAUDE.md Sanity Check Protocol) — เน้น SQL injection (parameterized), XSS escaping, customer-scoping, `back` param ไม่เป็น open-redirect vector
- Manual: เปิด `/portal` จริง กดดาว 2-3 งาน เช็คชิป "⭐ ที่สนใจ" กรองถูก, ดาวคงสถานะข้าม reload, กดจากหน้า job detail ก็ทำงานเหมือนกัน

## Out of Scope

- ไม่มี sort/reorder ตามดาว (แค่ filter)
- ไม่มี limit จำนวนดาวสูงสุด
- ไม่กระทบ ⭐ เดิมใน LINE flex message (`star:<project_id>` postback) หรือ `followed_jobs.starred_at` เลย — คนละระบบ
