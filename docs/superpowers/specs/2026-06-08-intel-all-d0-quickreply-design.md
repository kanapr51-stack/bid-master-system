# Intel + Plain-text + Quick-Reply บนทุกงาน D0 ที่ match — Design Spec

**วันที่:** 2026-06-08 · **สถานะ:** APPROVED (brainstorm กับกัญจน์) · ต่อยอด scope-local/dual-block output

## เป้าหมาย
ให้ **ทุกงานที่ตรงเกณฑ์ (พื้นที่/ประเภท) + เปิดให้ยื่นซองแล้ว (D0)** แสดง intel (คู่แข่ง+ราคาคาด) **ทันที ไม่ว่าจะกดติดตามหรือยัง** + มีปุ่มลอย (quick-reply) ให้กดติดตามได้จากข้อความ text

**Gap ที่แก้ (กัญจน์จับได้):** ปัจจุบัน intel ขึ้นเฉพาะ `followed_bid_open` (ติดตามตั้งแต่ B0 แล้วเลื่อนเป็น D0). ถ้า **กดสนใจตอน D0 เลย** → `last_stage_notified=D0` → `bid_open_followups` (ต้องการ B*) ไม่ทริก → **ไม่ได้ intel เลย**

## หลักการ
- intel = ช่วยตัดสินใจตอนจะยื่น → ควรเห็นทุกงาน D0 ที่เกี่ยว ไม่ผูกกับ timing การติดตาม
- text ธรรมดากดปุ่มในตัวไม่ได้ → ใช้ **quick-reply** (ปุ่มลอยใต้ข้อความ) สำหรับติดตาม/ไม่เกี่ยว

## Gate
**`announce_type == "D0"`** → ส่ง plain text + intel + quick-reply
- B0 (province_tor_review = ร่าง TOR) → flex เดิม ไม่แตะ
- W0 (followed_winner = ผู้ชนะ) → การ์ดผู้ชนะเดิม ไม่แตะ

## ข้อความ (plain text)
หัวข้อตาม stage:
- `followed_bid_open` (ติดตามแล้ว) → "⭐ งานที่ติดตามกำหนดวันยื่นซองแล้ว!"
- D0 อื่น (ยังไม่ติดตาม: province_qualified/soft/api_enriched) → **"🔔 พบงานเปิดกำหนดวันยื่นซองใหม่"**

body เดิม: 📍 ต./อ./จ. · 💰 ราคากลาง · 🏢 · ⏰ ยื่นซอง · 💡 intel dual-block + คาดราคา · 🔑 id
(intel ว่าง = ไม่มีคู่แข่ง → ข้าม block intel แต่ยังส่งข้อมูลพื้นฐาน + ปุ่ม)

## Quick-Reply chips (ต่อคน — สร้างใน send path)
- **⭐ ติดตาม** (postback `star:<pid>`) — เฉพาะลูกค้าที่**ยังไม่ติดตาม**งานนี้ (เช็ค `is_following`)
- **❌ ไม่เกี่ยว** (postback `fb:irrelevant:<pid>`) — ทุกคน
- (FB_ACTIONS ปัจจุบัน = star + irrelevant เท่านั้น — feedback 3-ทางเอาออกแล้ว · webhook รองรับ postback ทั้งคู่อยู่แล้ว)

## Components
- `send_line_push(token, uid, text, quick_reply=None)` — เพิ่ม `quickReply` ใน LINE payload (list of postback items). ไม่ส่ง quick_reply = เหมือนเดิม
- `is_following(customer_id, project_id) -> bool` (Customer_DB) — query followed_jobs status='active'
- `_quick_reply_items(...)` helper ใน LINE_Sender — ประกอบ chips (⭐ ถ้ายังไม่ตาม + ❌)
- `format_notification` — intel block + 📍 ต./อ. สำหรับ `announce_type=="D0"` ทุก stage (ไม่ใช่แค่ followed_bid_open). หัวข้อแยก followed vs ใหม่
- send path — `if announce_type=="D0": send_line_push(text, qr) else: flex เดิม`

## Edge / Safety
- intel ว่าง → ส่ง text พื้นฐาน + chips (graceful)
- ลูกค้าติดตามงานนี้แล้ว → ไม่โชว์ ⭐ (โชว์แค่ ❌)
- non-D0 → flex เดิม ไม่กระทบ
- intel/quick-reply พัง → try/except, notification ยังส่ง
- ปริมาณ: D0 ที่ match/วันไม่เยอะ (matcher กรอง tambon แล้ว) — load รับได้

## Testing (TDD)
1. `is_following`: ตาม/ไม่ตาม/ปิดแล้ว
2. `_quick_reply_items`: ยังไม่ตาม→[⭐,❌] · ตามแล้ว→[❌]
3. `send_line_push` quick_reply: payload มี quickReply ถูก format · ไม่ส่ง=ไม่มี key
4. `format_notification`: D0 ไม่ followed → หัวข้อ "🔔 พบงานเปิดกำหนดวันยื่นซองใหม่" + มี intel · followed → "⭐..." + intel · B0 → ไม่มี intel
5. send path: D0 → send_line_push + qr (mock) · non-D0 → flex
6. graceful: intel ว่าง → ยังส่ง

## Rollback
revert gate (กลับ followed_bid_open เท่านั้น) + send_line_push quick_reply param (optional ถอยได้). additive
