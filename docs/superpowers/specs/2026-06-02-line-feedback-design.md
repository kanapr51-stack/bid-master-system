# Spec: ระบบ Feedback ปุ่มกดใน LINE

**วันที่:** 2026-06-02
**สถานะ:** Design approved (กัญจน์ 2026-06-02)
**เป้าหมาย North-Star:** พิสูจน์ value — user เจองานที่ไม่เคยเห็น + นำไปทำต่อ

---

## 1. เป้าหมาย
ให้ user (พ่อแม่/ครอบครัว 5 คน) กด feedback บนงานที่ส่งทาง LINE ได้ — เก็บ signal เพื่อ:
1. **วัด value** (North-Star) — กี่งานที่ user "สนใจ/น่าติดตาม"
2. **ปรับ matching** — งานที่ "ไม่เกี่ยวข้องเลย" = matching ผิด → กัญจน์ปรับ config

## 2. ปุ่ม 3 แบบ (postback) + ความหมาย
| ปุ่ม | action (DB) | ความหมาย | เอาไปใช้ |
|---|---|---|---|
| 👍 **สนใจ/น่าติดตาม** | `interested` | งานใช่ + พื้นที่ใช่ + งบคุ้ม | **value (North-Star)** + เผื่อ future portal ติดดาว |
| 🤔 **เกี่ยวข้องแต่ไม่น่าสนใจ** | `relevant_low` | matching ถูก แต่ดูงบแล้วไม่คุ้ม/ขาดทุน | **business signal** (budget pref) — **ไม่แตะ matching** |
| 👎 **ไม่เกี่ยวข้องเลย** | `irrelevant` | พื้นที่/ประเภทงานผิด | **matching ผิด** → กัญจน์ดู → ปรับ config |

**หลักการสำคัญ (จาก insight กัญจน์):** เฉพาะ 👎 เท่านั้นที่บอกว่า matching ผิด — 🤔 คือ business judgment (ระบบส่งถูกแล้ว) ห้ามเอา 🤔 ไปปรับ matching (จะตัดงานที่ส่งถูกทิ้ง)

## 3. Data Flow
```
LINE_Sender ส่งงาน (flex message + 3 ปุ่ม postback, แนบ project_id)
   ↓ user กดปุ่ม
bms_api /webhook/line → postback handler
   ↓
feedback table (เก็บ: customer_id, project_id, action, created_at)
   ↓
reply "บันทึกแล้ว ขอบคุณครับ 🎩"
   ↓
Daily Digest → สรุปให้กัญจน์ (👍 value / 👎 matching ผิด + project)
   ↓ manual
กัญจน์ดู 👎 → ตัดสินปรับ config เอง
```

## 4. Mockup (LINE message)
```
🏗️ ก่อสร้างถนน คสล. ต.โพธิ์หมากแข้ง
💰 4.5 ล้านบาท · ⏳ ยื่นซอง 8 มิ.ย.
📎 [ดูเอกสาร]
─────────────────
[👍 สนใจ/น่าติดตาม] [🤔 เกี่ยวข้องแต่ไม่น่าสนใจ] [👎 ไม่เกี่ยวข้องเลย]
```

## 5. Components ที่แตะ
| ไฟล์ | แก้อะไร |
|---|---|
| `Sebastian_LINE_Sender.py` | เปลี่ยน text → **flex message** + 3 ปุ่ม postback (postback data = `fb:<action>:<project_id>`) |
| `bms_api.py` (webhook `/webhook/line`) | เพิ่ม **postback event handler** → parse `fb:...` → เขียน feedback table + reply ขอบคุณ |
| `feedback` table | **มีอยู่แล้ว** (customer_id, project_id, action, raw_text, created_at) — ใช้ได้เลย |
| `Sebastian_Daily_Digest.py` | เพิ่ม section สรุป feedback (👍/🤔/👎 count + 👎 project list ให้กัญจน์ดู) |

## 6. Error Handling
- **กดซ้ำ/เปลี่ยนใจ:** เก็บ feedback ล่าสุด 1 รายการ/customer/project (upsert — กดใหม่ทับเก่า)
- **project_id ไม่ match delivery_log:** ยังเก็บได้ (feedback table ไม่ FK บังคับ) — แต่ flag ใน report
- **webhook error:** log + reply graceful, ไม่ crash (best-effort เหมือน onboarding webhook เดิม)
- **postback data ผิดรูปแบบ:** ignore (log)

## 7. Testing
- ส่ง flex message + ปุ่ม → user กด → webhook รับ postback → feedback row เขียนถูก (action + project + customer)
- reply ขอบคุณกลับ
- กดซ้ำ → ทับ (1 row/customer/project)
- digest สรุป feedback ถูก

## 8. Scope
**Build ตอนนี้:** 3 ปุ่ม postback + webhook handler + เก็บ feedback + รายงาน digest/Discord
**Defer (YAGNI):**
- Portal "ติดดาวงาน" — 👍 → saved jobs (feedback table มี data รองรับแล้ว, portal ดึงทีหลัง)
- Auto-tune matching จาก 👎 (volume ต่ำ 5 users → manual ก่อน)
- Budget filter จาก 🤔 (เก็บ signal ไว้ก่อน)

## 9. Success Criteria
- user กดปุ่มได้จริง → feedback เก็บถูก
- กัญจน์เห็นสรุป feedback ในรายงาน
- **North-Star:** มี 👍 ≥ 1 = "user เจองานที่น่าติดตาม" (พิสูจน์ value เริ่มขยับ)
