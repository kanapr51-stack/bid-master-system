# Portal Phase 2a — Read-Only Followed-Jobs Dashboard — Design

**วันที่:** 2026-06-10
**สถานะ:** approved design (รอ user review spec → writing-plans)

## Problem / Goal

ตอนนี้ลูกค้าเห็นงานที่ติดตามได้เฉพาะจากข้อความ LINE ที่เด้งมาทีละครั้ง — ไม่มีที่ "ดูรวมทั้งหมด" ว่ากำลังติดตามอะไรอยู่ + สถานะถึงไหน. follow-link (N+110) วางราก `follow_token` (`p=None` = portal-token ต่อ user) ไว้แล้ว. Portal 2a = **เว็บหน้าเดียว read-only** ที่ user เปิดดู **งานที่ติดตามทั้งหมด** + lifecycle + คาดราคา + ผู้ชนะ/คู่แข่ง.

**คุณค่า:** client surface ที่เราเลือก (LINE + Web Portal) — ที่เดียวที่เห็นภาพรวมงานติดตาม → ตัดสินใจ/ติดตามต่อได้ดีขึ้น (North-Star "user นำไปทำต่อ").

## Scope / Out of scope
- ✅ **2a (นี้):** หน้าเดียว server-rendered, การ์ดต่องาน inline, จัดกลุ่มตาม stage, read-only. แสดง active + closed (ปิด=เห็นผล). 1 route + 1 LINE command.
- ⏳ **2b (defer):** โน้ตต่องาน (write path + ตารางใหม่) · unfollow จาก portal · per-job detail page.
- ❌ ไม่ทำ: framework/SPA/LIFF (ใช้ server-rendered HTML เดิม ตาม ethos ship-simple) · auth ซับซ้อน (token bearer พอสำหรับ MVP เหมือน follow-link).

## Architecture

ต่อยอด `bms_api.py` (FastAPI) + `follow_token` เดิม. ทั้งหมด server-rendered HTML (เหมือน `_follow_page_html`).

```
LINE: user พิมพ์ "งานของฉัน"
   │
   ▼ /webhook/line (bms_api) — text keyword → reply portal link
   │   _portal_link(user_id) = BASE_URL + /portal?t= + follow_token.make_token(user_id, None)
   ▼
GET /portal?t=<portal_token>
   ├─ verify_token → user_id (project_id ไม่สน — token ไหนของ user ก็เปิด portal ได้)
   ├─ _portal_jobs(user_id) → followed_jobs + join data → จัดกลุ่ม stage
   └─ _portal_page_html(groups) → HTML มือถือ-first
```

## Components (bms_api.py)

### 1. `_portal_jobs(user_id) -> dict`
- หา customer จาก `line_user_id`. ไม่เจอ → `None` (→ หน้า no_customer).
- query `followed_jobs WHERE customer_id=? AND status IN ('active','closed')` (ซ่อน `'unfollowed'` = user เอาออกเอง).
- ต่องาน รวม data: `projects_seen` (announce_type=stage ปัจจุบัน, project_name, province, budget, dept_name) · `project_locations` (deadline) · `price_predictions` (area_price_lo/hi) · `bid_results` (winner+competitors ถ้ามี).
- **derive stage group** (3 กลุ่ม):
  - `won` (🏆 ประกาศผลแล้ว) = มี winner ใน bid_results **หรือ** announce_type ขึ้นต้น 'W'
  - `bidding` (🔵 กำลังประมูล) = announce_type 'D0' และยังไม่มี winner
  - `pre` (⭐ รับฟังความเห็น/เตรียม) = อื่น ๆ (B*)
- คืน `{"won": [...], "bidding": [...], "pre": [...]}` — แต่ละ job = dict {project_id, name, location, deadline, pred_lo, pred_hi, winner, winner_price, winner_disc, competitors[]}

### 2. `_portal_page_html(groups, exp_epoch) -> str`
- HTML มือถือ-first (reuse head/style จาก `_follow_page_html` — DRY: แยก `_html_head()`/`_html_foot()` ถ้าจำเป็น).
- หัว "🗂 งานที่คุณติดตาม (N)". กลุ่มเรียง: bidding → pre → won (กำลังลุ้นอยู่บนสุด).
- การ์ดต่องาน: ชื่อ · 📍 ต./อ. · lifecycle dots (●━━●━━○ + ป้าย stage ปัจจุบัน) · ตามกลุ่ม:
  - bidding: ⏰ ยื่นซอง {deadline} · 💵 คาด {lo}–{hi}
  - won: 🏆 {winner} · {price} (ลด {disc}%) · 👥 คู่แข่ง {top}
  - pre: "⭐ รับฟังความเห็น (ยังไม่เปิดประมูล)"
- ว่าง (ไม่มีงาน) → "ยังไม่มีงานที่ติดตาม — กดดาว ⭐ ในข้อความแจ้งเตือนเพื่อเริ่มติดตาม"
- escape ทุก dynamic field (html.escape) — ป้องกัน XSS (ชื่องาน/บริษัทจาก eGP)

### 3. `GET /portal` route
```
v = follow_token.verify_token(t)
if not v: → HTMLResponse(_follow_page_html(t,"invalid",{},"",v[2] if v else 0))   # reuse invalid page
user_id = v[0]
jobs = _portal_jobs(user_id)
if jobs is None: → HTMLResponse(_follow_page_html(t,"no_customer",{},"",exp))
return HTMLResponse(_portal_page_html(jobs, v[2]))
```
- read-only, GET, side-effect-free (สอดคล้อง follow GET).

### 4. Webhook keyword → portal link (`/webhook/line`)
- ใน handler ของ text message: ถ้า text strip ∈ {"งานของฉัน","portal","พอร์ทัล","งานที่ติดตาม"} → reply ลิงก์ portal.
- reply ผ่าน LINE reply API: `POST https://api.line.me/v2/bot/message/reply` {replyToken, messages:[{type:text, text:"🗂 ดูงานที่ติดตามทั้งหมด:\n"+link}]} ด้วย `LINE_CHANNEL_ACCESS_TOKEN` (env).
- `_portal_link(user_id)` = `PUBLIC_BASE_URL + "/portal?t=" + follow_token.make_token(user_id, None)`.
- ⚠️ implementer ตรวจ webhook เดิมว่า reply ยังไง (มี postback handler อยู่แล้ว) + signature verify — เพิ่ม text branch ไม่ทับ postback.

### 5. env
- `bms_api.py` เพิ่ม `PUBLIC_BASE_URL = os.getenv("BMS_PUBLIC_BASE_URL", "https://api.butler-bms.com")` (ถ้ายังไม่มี — sender มีแล้ว, .env ตั้งแล้วตอน N+110).

## Data flow / lifecycle dots
- stage ปัจจุบัน = `projects_seen.announce_type` (advance โดย discovery: B<D<W). dots map: B0→`●○○`, D0→`●●○`, won→`●●●`.
- deadline จาก `project_locations.deadline` (resolve PDF, N+110). ไม่มี → ข้ามบรรทัด ⏰.
- prediction จาก `price_predictions` (recency-adjusted แล้ว N+113). ไม่มี → ข้าม 💵.
- winner/competitors จาก `bid_results` (Winner_Poller). dedupe ชื่อ (เหมือน `_winner_card_from_results`). โชว์ top 3 คู่แข่ง.

## Edge cases
| กรณี | จัดการ |
|---|---|
| token invalid/expired | หน้า invalid (reuse _follow_page_html "invalid") |
| user ไม่มีใน customers | หน้า no_customer |
| ไม่มีงานติดตาม | empty state |
| followed_jobs.status='unfollowed' | ซ่อน (user เอาออกเอง) |
| projects_seen row หาย | ข้ามงานนั้น (graceful) |
| ไม่มี deadline/prediction/winner | ข้ามบรรทัดนั้น (การ์ดยังแสดง) |

## Testing (TDD)
- `_portal_jobs`: seed customers + followed_jobs (active+closed+unfollowed) + projects_seen (B0/D0/W0) + bid_results → ยืนยันจัดกลุ่ม won/bidding/pre ถูก, ซ่อน unfollowed, winner/competitors ถูก
- `_portal_page_html`: render 3 กลุ่ม → มีชื่องาน, ป้าย stage, winner card; empty → empty state; escape `<script>`
- `GET /portal`: import-sanity route ลงทะเบียน + verify_token p=None ผ่าน (ตรวจ runtime ด้วย curl ใน deploy)
- webhook keyword: unit ยาก (ต้อง FastAPI runtime + LINE) → ตรวจ `_portal_link` มินต์ token verify ได้ + e2e curl/manual หลัง deploy
- regression: test_bms_follow, test_follow_token เดิมผ่าน

## Deploy
push → VPS pull → restart bms-api (route ใหม่ — daemon ต้อง reload). ⚠️ gate confirm push. e2e: curl /portal?t=<portal token จริง> เห็นรายการ + พิมพ์ "งานของฉัน" ใน LINE จริง (กัญจน์) ได้ลิงก์.
