# D0 Notification → Bid Board Job Link — Design

**Date:** 2026-06-21
**Status:** Approved by กัญจน์ 2026-06-21

## Problem

การ์ดงานใหม่ (D0) ที่ส่งทาง LINE ตอนนี้ฝังบล็อกวิเคราะห์ราคา+คู่แข่งที่ชนะบ่อย+ตาราง win% (`cgd_intel.intel_context()["lines"]`) เป็น text ยาวอยู่ในข้อความ — อ่านยากบนมือถือ และจำกัดความละเอียดด้วยพื้นที่ของ LINE message. กัญจน์ต้องการย้ายบล็อกนี้ไปแสดงในหน้า job detail ของ BMS Bid Board แทน (`/portal/job`) แล้วเหลือแค่ลิงก์สั้นๆใน LINE — อ่านง่ายขึ้น และเปิดทางให้ใส่รายละเอียดเชิงลึกเพิ่มได้ในเว็บ (ไม่ติด constraint ความยาวแบบ LINE).

หน้า `/portal/job` (`scripts/portal_views.py::job_detail`/`render_job_page`) ปัจจุบันแสดงแค่**ผู้ยื่นจริงของงานนี้** (จาก `bid_results`, มีข้อมูลเฉพาะหลังประมูลจบ) — ไม่มีส่วนแสดง intel เชิงทำนาย/ประวัติศาสตร์แบบที่ `cgd_intel` คำนวณเลย ต้องเพิ่ม section ใหม่ ไม่ใช่แค่ลิงก์ไปหน้าที่มีอยู่.

## Scope

เฉพาะการ์ด D0 ("พบงานเปิดกำหนดยื่นซองใหม่") — `format_notification(announce_type="D0")` เท่านั้น. ไม่แตะ format ของ PRELIM/W0 cards (ใช้ข้อมูลผู้ยื่นจริงอยู่แล้ว คนละ data source).

## ฝั่ง LINE (`scripts/Sebastian_LINE_Sender.py`)

### `format_notification()`

- ลบส่วน build `intel_ctx["lines"]` เข้า message body (บรรทัด `━━━━━━━━━━━━━` + เนื้อหาวิเคราะห์ทั้งหมด — ปัจจุบันอยู่ราวบรรทัด 292-306)
- คงการเรียก `cgd_intel.intel_context(...)` ไว้เหมือนเดิมทุกอย่าง — ยังต้องใช้ `tambon`/`amphoe` ทำบรรทัด 📍 และ `prediction` สำหรับ `save_prediction()` closed-loop tracking (ห้ามแตะ — เป็น bookkeeping คนละเรื่องกับการแสดงผล)
- เพิ่ม parameter ใหม่ `line_user_id: str = ""`
- ถ้า `intel_ctx` ไม่ None และมีทั้ง `line_user_id` กับ `project_id` → เพิ่ม 1 บรรทัดท้ายข้อความ (แทนที่บล็อกเดิม):

  ```
  🔍 ดูวิเคราะห์ราคา+คู่แข่งบน Bid Board: {link}
  ```

- ถ้า `intel_ctx` เป็น None (ไม่มีข้อมูลย้อนหลังพอ) หรือไม่มี `line_user_id`/`project_id` → ไม่มีบรรทัดนี้เลย (เหมือนพฤติกรรมปัจจุบันที่ omit ทั้งบล็อกตอนไม่มีข้อมูล)
- ไม่มีสรุปเลขย่อ (ราคา/จำนวนคู่แข่ง) เหลืออยู่ใน LINE — ลิงก์เปล่าล้วนๆตามที่กัญจน์ยืนยัน

### `build_job_link(line_user_id: str, project_id: str) -> str`

ฟังก์ชันใหม่ มิเรอร์ `build_follow_link()` ที่มีอยู่แล้ว (บรรทัด 338-345) ทุกอย่าง ต่างกันแค่ path ปลายทาง:

```python
def build_job_link(line_user_id: str, project_id: str) -> str:
    """ลิงก์ไปหน้า job detail บน Bid Board (signed token, ต่อคน-ต่องาน). คืน '' ถ้า make_token พลาด (ห้ามทำ D0 พัง)."""
    try:
        return PUBLIC_BASE_URL.rstrip("/") + "/portal/job?t=" + \
            follow_token.make_token(line_user_id, project_id) + "&pid=" + project_id
    except Exception as e:
        print(f"[build_job_link] follow_token error (ส่งต่อไม่มีลิงก์): {e}", file=sys.stderr)
        return ""
```

อายุ token เท่า default ของ `make_token` (120 วัน) — เหมือนลิงก์ follow เดิม ไม่ต้องคิด TTL ใหม่.

### Call sites

- จุดหลัก (~บรรทัด 835 ใน `Sebastian_LINE_Sender.py`) — มี `item["line_user_id"]` และ `item["project_id"]` อยู่ในสโคปอยู่แล้ว ส่งผ่านตรงๆได้
- `scripts/_resend_today_onboarding.py:75`, `scripts/resend_d0_jobs.py:66`, `scripts/_show_card.py:20` — สคริปต์ resend/preview/test ที่ไม่ใช่ทาง critical. ถ้าไม่ส่ง `line_user_id` เข้าไป (default `""`) → ไม่มีลิงก์ ไม่ error. ไม่บังคับแก้ทั้ง 3 จุดนี้ในรอบนี้ ยกเว้นแก้ง่ายและไม่เสี่ยง.

## ฝั่ง Portal (`scripts/portal_views.py`)

### `job_detail(conn, pid)`

- ใช้ `province`, `project_name`, `dept_name`, `budget` ที่ฟังก์ชันนี้ดึงอยู่แล้ว (ใช้ทำ header ส่วนอื่น) เรียก `cgd_intel.intel_context(province, project_name, dept_name, pid, budget, conn)` — ใช้ conn เดียวกัน ไม่เปิด connection ใหม่
- ห่อ try/except (ตามแพทเทิร์นเดิมของไฟล์ — ส่วนเสริมต้องไม่ทำหน้าเว็บพัง): ถ้า exception หรือคืน `None` → `data["intel_lines"] = None`
- แนบผลสำเร็จเป็น `data["intel_lines"] = intel_ctx["lines"]` — ใช้ text เดิมจาก `cgd_intel` ตรงๆ ไม่ parse/restructure ใหม่ เพราะเนื้อหานี้ผ่านการพิสูจน์ใช้งานจริงมาแล้วจาก LINE
- **ไม่เรียก** `save_prediction()` ในเส้นทางนี้ — closed-loop prediction logging เกิดแค่ครั้งเดียวตอน dispatch notification เท่านั้น (ใน `Sebastian_LINE_Sender.py`) ไม่ใช่ทุกครั้งที่มีคนเปิดหน้าเว็บซ้ำ

### `render_job_page(data, ...)`

- เพิ่ม section ใหม่ หัวข้อ `📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่` วางต่อจากบล็อกราคาคาด (`pred_lo`/`pred_hi`) ก่อนรายชื่อผู้ยื่นจริง — แยกชัดว่าเป็นข้อมูลเชิงทำนาย/ประวัติศาสตร์ คนละชุดกับผู้ยื่นจริงของงานนี้ (ที่อยู่ด้านล่าง)
- render แต่ละบรรทัดใน `data["intel_lines"]` เป็น `<div>` แยกบรรทัด (reuse CSS class ที่มีอยู่ในไฟล์นี้แล้ว — ไม่สร้าง class/framework ใหม่)
- ถ้า `data["intel_lines"]` เป็น `None` → ไม่ render section นี้เลย (เคสงานที่ไม่มีข้อมูลย้อนหลังพอ)

### Route `/portal/job` (`scripts/bms_api.py:1037-1049`)

ไม่ต้องแก้ — รับ `data` จาก `job_detail()` ส่งตรงไปยัง `render_job_page()` อยู่แล้ว, การเปลี่ยนแปลงทั้งหมดอยู่ใน `data` dict และ template ฝั่ง `portal_views.py`.

## Testing

- `format_notification()` tests ที่มีอยู่แล้ว — แก้ assertion ที่เคยเช็คเนื้อหา intel block ในข้อความ → เช็คว่ามีบรรทัดลิงก์ปรากฏ (เมื่อมี `line_user_id`+`project_id`+`intel_ctx`) และไม่มีบรรทัดลิงก์ (เมื่อขาดอย่างใดอย่างหนึ่ง)
- เพิ่ม unit test ให้ `build_job_link()` มิเรอร์ test ของ `build_follow_link()` ที่มีอยู่แล้ว (token gen สำเร็จ → URL ถูกรูปแบบ, gen พลาด → คืน `""`)
- `test_portal_views.py` — เพิ่มเคส `job_detail()` คืน `intel_lines` (list) เมื่อ `cgd_intel` resolve ได้, คืน `None` เมื่อ resolve ไม่ได้/error
- `render_job_page()` — เพิ่มเคสเช็คว่า HTML มี section "📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่" เมื่อมี `intel_lines`, และไม่มี section นี้เมื่อ `intel_lines` เป็น `None`

## Rollout

- ไม่มี DB migration (ไม่กระทบ schema) — แก้แค่ formatting (LINE) + data-fetch/template (portal)
- ต้อง deploy LINE sender กับ portal **พร้อมกันเป็นชุดเดียว** — ถ้า deploy แยก ลิงก์ใน LINE ที่ส่งออกไปแล้วจะพัง (ปลายทาง `/portal/job` ที่ยังไม่มี section ใหม่ก็ไม่พัง แต่ก็ยังไม่สมบูรณ์ — เพื่อความปลอดภัยให้ deploy คู่กัน)
- ไม่กระทบ data layer (notification_queue/winner/pricing dedup) — เป็น presentation layer ล้วน ไม่จำเป็นต้องให้ Sophia ตรวจ แต่ต้องรัน test suite ที่มีอยู่ + ที่เพิ่มใหม่ให้ผ่านก่อน commit

## Out of Scope

- PRELIM (Round 1) / W0 (winner) notification cards — ใช้ข้อมูลผู้ยื่นจริงอยู่แล้ว ไม่มีบล็อก `cgd_intel` ให้ย้าย
- การ restructure ภายในของ `cgd_intel.intel_context()` ให้คืน structured data แทน text lines — เนื้อหาเดิมพิสูจน์แล้วว่าใช้งานได้ดี และการแก้ logic การคำนวณราคา/win% (price-sacred, B′ grid) มีความเสี่ยงสูงเกินสโคปงานนี้
- การแก้ไข 3 call site รอง (`_resend_today_onboarding.py`, `resend_d0_jobs.py`, `_show_card.py`) ให้ส่ง `line_user_id` ครบ — เป็น nice-to-have ไม่บังคับ
