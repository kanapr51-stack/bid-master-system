# Follow-link (signed-token, stateful toggle) — Design

**วันที่:** 2026-06-08
**สถานะ:** approved (กัญจน์ 2026-06-08)
**เกี่ยวข้อง:** N+108 (DECISION LIFF→token), `project_event_centric_queue`, `project_client_surface_decision`

---

## Context

ข้อความแจ้งเตือน D0 ปัจจุบันใช้ quick-reply button ⭐ (N+107) สำหรับ "ติดตามงาน" — แต่ LINE
แสดง quick-reply เฉพาะข้อความล่าสุด ฉะนั้นเมื่อหลายงาน D0 เด้งพร้อมกัน ปุ่ม ⭐ ของงานก่อนหน้า
หายไป กดติดตามไม่ได้ (follow-timing gap)

N+108 ตัดสินใจแก้ด้วยลิงก์ในเนื้อข้อความ (เลื่อนกดของเก่าได้ไม่หาย) เดิมวางแผนใช้ LIFF แต่ทบทวน
แล้วพบว่า **ไม่จำเป็นต้องใช้ LIFF**: bot เป็นคนส่งข้อความเอง จึงรู้ userId อยู่แล้ว → ฝัง userId
ลงใน **signed token** ในลิงก์ได้เลย ไม่ต้องสร้าง LINE Login channel / โหลด LIFF SDK / ขอ consent

LIFF ยังอยู่ในแผนระยะยาว (Web Portal เต็มรูปแบบ `project_client_surface_decision`) แต่สำหรับ
ปุ่มติดตามปุ่มเดียวตอนนี้ token link เพียงพอ (KISS/YAGNI)

## เป้าหมาย

ในแต่ละข้อความ D0 มีลิงก์ของงานนั้นโดยเฉพาะ → แตะ → หน้าเว็บใน LINE → ปุ่มยืนยัน → backend
บันทึก `userId ↔ projectId` ลง `followed_jobs` หน้าเว็บ **สะท้อนสถานะจริง** (toggle):

- ยังไม่ติดตาม → ปุ่ม **[⭐ ติดตามงานนี้]**
- ติดตามอยู่แล้ว (เช่นเคยกดตอน B0) → "✅ งานนี้ติดตามอยู่แล้ว" + ปุ่ม **[ยกเลิกการติดตาม]**

## Non-goals

- ไม่ทำ LIFF / LINE Login channel (defer จนทำ Web Portal เต็ม)
- ไม่ทำ template engine — HTML เป็น inline string
- ไม่แตะ logic การ resolve intel / deadline / matching

---

## สถานะ infra (ยืนยันแล้ว 2026-06-08)

| รายการ | ค่า |
|---|---|
| HTTPS domain | `https://api.butler-bms.com` (Let's Encrypt + Certbot auto-renew) |
| nginx | `bms-api` site → proxy `127.0.0.1:8000` |
| FastAPI | `scripts/bms_api.py` (systemd `bms-api.service`, active) |
| /health | live: `{"ok":true,"db":true}` |
| ลิงก์ follow | `https://api.butler-bms.com/follow?t=<token>` |

---

## Architecture

### Flow

```
D0 match → Sender มินต์ token(userId+projectId) → แทรกลิงก์ในข้อความ (รายคน)
   ↓ user แตะ
GET /follow?t=… → verify → lookup customer + followed_jobs(cust,proj)
   ├─ ยังไม่ตาม      → การ์ดรายละเอียดงาน + ปุ่ม [⭐ ติดตามงานนี้]
   └─ ตามอยู่แล้ว     → "✅ งานนี้ติดตามอยู่แล้ว" + ปุ่ม [ยกเลิกการติดตาม]
   ↓ กดปุ่ม (POST form: t + action)
POST /follow → verify → _record_follow / _record_unfollow → re-render หน้าเดิม (สลับปุ่ม)
```

### Unit 1 — `scripts/follow_token.py` (ไฟล์ใหม่, dependency-free)

ตัวมินต์/ตรวจ token แบบ stateless HMAC ไม่เก็บ DB

- `make_token(user_id, project_id=None, ttl_days=120) -> str`
  payload = `{"u": user_id, "p": project_id, "e": <epoch หมดอายุ>}`
  (`p=None` = portal token ระดับ user — เผื่อ Phase 2; follow-link จะส่ง project_id เสมอ)
  token = `base64url(json(payload)) + "." + base64url(hmac_sha256(secret, payload_b64))`
- `verify_token(t) -> (user_id, project_id) | None`
  - แยก `.` → ตรวจ sig ด้วย `hmac.compare_digest` → reject ถ้าไม่ตรง
  - ตรวจ `e` > now → reject ถ้าหมดอายุ
  - คืน `(u, p)`
- secret = env **`BMS_FOLLOW_SECRET`** (sender มินต์ + api verify อยู่บน VPS เดียวกัน แชร์ env)
- ใช้ `base64.urlsafe_b64encode` (ไม่มีอักขระต้อง URL-escape)

**ทำไม:** อยู่ได้เองในไฟล์เดียว ทดสอบ unit แยกได้ (มินต์→verify roundtrip) ไม่พึ่ง state/DB

### Unit 2 — `scripts/bms_api.py` (เพิ่ม 2 endpoint + 1 ฟังก์ชัน)

| ส่วน | รายละเอียด |
|---|---|
| `GET /follow` (query `t`) | verify_token → ถ้า None: หน้า error "ลิงก์ไม่ถูกต้อง/หมดอายุ" · lookup customer by line_user_id → ถ้าไม่เจอ: หน้า "กรุณาเพิ่มเพื่อน Sebastian ก่อน" · lookup followed_jobs(cust,proj).status → render HTML toggle |
| `POST /follow` (form `t`, `action` ∈ follow/unfollow) | verify_token → ถ้า None: 400 · `action=follow` → `_record_follow` · `action=unfollow` → `_record_unfollow` · re-render หน้า (สถานะใหม่) |
| `_record_unfollow(user_id, project_id)` ใหม่ | `UPDATE followed_jobs SET status='unfollowed' WHERE customer_id=? AND project_id=?` (lookup cust จาก line_user_id เหมือน `_record_follow`) |

- HTML: inline string, มือถือ-first, ปุ่มใหญ่แตะง่าย, ภาษาไทย — reuse `_project_detail()` +
  `_follow_deadline()` แสดงชื่องาน/จังหวัด/งบ/⏰ deadline
- ใช้ `HTMLResponse` จาก `fastapi.responses`
- ปุ่ม = `<form method="post" action="/follow">` + hidden `t` + hidden `action` → กัน prefetch
  auto-follow (side-effect เป็น POST เท่านั้น)

### Unit 3 — `scripts/Sebastian_LINE_Sender.py` (send site ~665-670)

- เลิกสร้าง `qr` (เอา quick-reply ออกตามมติ) → ส่ง `quick_reply=None`
- ต่อบรรทัดท้าย text **รายคน** (หลัง `format_notification` คืนค่า):
  ```
  ⭐ ติดตามงานนี้:
  https://api.butler-bms.com/follow?t=<make_token(line_user_id, project_id)>
  ```
- `format_notification` ไม่แตะ (text ยัง recipient-agnostic — ลิงก์ต่อนอกฟังก์ชันเพราะต้องใช้
  line_user_id เฉพาะคน)
- `_quick_reply_items` เก็บโค้ดไว้ (ไม่ลบ) เผื่ออนาคต แต่ไม่เรียกใช้
- base URL = env (เช่น `BMS_PUBLIC_BASE_URL`, default `https://api.butler-bms.com`)

---

## Data

`followed_jobs` (มีอยู่แล้ว): `(customer_id, project_id, starred_at, starred_stage,
last_stage_notified, status)` · UNIQUE(customer_id, project_id)

- follow → `status='active'` (เดิม, ON CONFLICT upsert)
- unfollow → `status='unfollowed'`

⚠️ **ต้องเช็กก่อน commit:** `job_followups.py` + `Sebastian_Winner_Poller.py` filter
`status='active'` หรือไม่ — ถ้าใช่ unfollow จะหยุดแจ้ง B0→D0→W0 ของงานนั้นถูกต้อง ถ้า downstream
ไม่ได้ filter status ต้องเพิ่ม

## Security / trust model

- token = **bearer**: ใครถือลิงก์ = follow/unfollow แทน user คนนั้นได้ — ยอมรับได้เพราะลิงก์ส่ง
  เข้า LINE chat ส่วนตัวเท่านั้น (โมเดลเดียวกับ action link ใน email)
- HMAC: กันปลอม userId/projectId เป็นคนอื่น
- exp 120 วัน: กันลิงก์เก่ารั่วถูกใช้ภายหลัง
- POST-only side-effect: กัน LINE/ไคลเอนต์ prefetch ลิงก์แล้ว auto-follow โดยไม่ตั้งใจ
- `BMS_FOLLOW_SECRET` ห้าม commit (อยู่ใน env บน VPS เท่านั้น)

## Error handling

| กรณี | ผล |
|---|---|
| token sig ผิด / หมดอายุ | GET → หน้า "ลิงก์ไม่ถูกต้องหรือหมดอายุ" · POST → 400 |
| ไม่เจอ customer (ยังไม่ add bot) | หน้า "กรุณาเพิ่มเพื่อน Sebastian ก่อนติดตามงาน" |
| ไม่เจอ project ใน projects_seen | แสดงเท่าที่มี (project_id เป็น fallback ชื่อ — เหมือน `_project_detail`) |
| make_token error ตอนส่ง | log + ส่งข้อความไม่มีลิงก์ (ห้ามทำ D0 notification พัง — pattern เดียวกับ intel) |

## Testing / Sanity check (ตาม CLAUDE.md)

1. **Unit token:** มินต์ → verify คืน (user, pid) ตรง · แก้ token 1 อักขระ → reject · exp อดีต → reject
2. **Idempotent:** follow→unfollow→follow ซ้ำ → followed_jobs คง 1 row/(cust,proj), status ถูกต้อง
3. **Downstream filter:** ยืนยัน job_followups/Winner_Poller filter status='active' (ดู section Data)
4. **End-to-end:** ส่ง D0 ทดสอบหา self → แตะลิงก์จริงบนมือถือ → กดติดตาม → re-tap เห็นปุ่มยกเลิก →
   กดยกเลิก → followed_jobs.status='unfollowed'

## Future work: Web Portal (Phase 2 — spec แยก)

กัญจน์ยืนยัน 2026-06-08: Portal ส่วนตัวเป็น feature ถัดไป (ทำ follow-link นี้ให้จบก่อน เป็นรากฐาน
identity) Portal = หน้าแสดง "งานทั้งหมดที่ฉันติดตาม" + lifecycle + ผู้ชนะ/คู่แข่ง/ราคา (จาก
`bid_results`) + คาดราคา vs จริง + **โน้ตส่วนตัวต่องาน** (ตาราง/คอลัมน์ใหม่) ตรงกับ
`project_client_surface_decision` (LINE + Web Portal)

**Forward-compat ที่ต้องเผื่อใน spec นี้:** ออกแบบ `make_token` ให้รองรับ token ระดับ user
ในอนาคต — projectId เป็น optional (payload ไม่มี `p` = portal token ระดับ user, อายุยาวกว่า)
เพื่อ Phase 2 reuse `verify_token` เดิมได้โดยไม่ต้องรื้อ ส่วน dashboard/notes/bid_results view
เก็บไว้ Phase 2 (ไม่ทำตอนนี้)

## Deployment notes

- ตั้ง env `BMS_FOLLOW_SECRET` (สุ่ม) บน VPS — ทั้ง `bms-api.service` + `bms-line-sender` service
- restart `bms-api.service` หลัง deploy โค้ดใหม่
- ไม่ต้องแตะ nginx/cert (ใช้ domain เดิม)
