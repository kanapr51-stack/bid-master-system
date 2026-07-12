# หน้า "ตั้งค่า" แทนระบบบริษัท — Design Spec

**วันที่:** 2026-07-12 · **สถานะ:** approved โดยคุณกัญจน์ ("โอเค ลุยเลย")
**Requirement:** แถบ "บริษัท" → "ตั้งค่า" + ถอดระบบบริษัท (เพิ่มขั้นตอนเกินจำเป็น) +
การ์ดพื้นที่ครอบคลุมกดแล้วเจอหน้าบริษัทที่ยังไม่ตั้งค่า ใช้ไม่ได้

## 1. หน้าใหม่ `/portal/settings` (web-only)

3 ส่วนแบน ไม่มีชั้นบริษัท:
1. 📍 พื้นที่ครอบคลุม — chips จังหวัดจาก `customer.provinces` (subscription จริง, N+198.1)
   **read-only** + note "ต้องการเปลี่ยนพื้นที่ แจ้ง Sebastian ได้เลยครับ"
2. 🏷️ คำค้น — chips เพิ่ม/ลบ; ว่าง = note "ไม่ตั้งคำค้น = เห็นงานทุกประเภททั้งจังหวัด"
3. 💰 ช่วงงบ — งบต่ำสุด/สูงสุด (บาท + hint ล้านบาท ตาม FilterEditor เดิม); 0/ว่าง = ไม่จำกัด

**Data shape (หลังบ้านไม่แตะ):** เซฟผ่าน POST `/api/portal/save` เดิม — merge เข้า notes ทั้งก้อน:
- คำค้น+งบ ว่างหมด → `classes: []`
- มีค่า → single hidden class `{id:'settings', name:'ตั้งค่า', keywords:[...], defaultKeywords:[],
  budgetMinBaht?, budgetMaxBaht?, geo:{mode:'province', provinces:[], districts:[], tambons:[], gps:null, radiusKm:30}, color:'#B8893A'}`
- engine `_classes_from_notes` อ่านต่อได้ทันที (keywords/budget) — matching ไม่เปลี่ยน

## 2. จุดที่แก้ตาม

| ไฟล์ | แก้ |
|---|---|
| `_shell.tsx:67` | nav → `{href:'/portal/settings', label:'ตั้งค่า', GearIcon}` |
| `world/_client.tsx` | ตัดการ์ด "บริษัทของฉัน"; การ์ดพื้นที่/Keywords + ปุ่ม "ไปตั้งค่า" (discovery empty) href → `/portal/settings` |
| `classes/page.tsx` | แทนทั้งไฟล์ด้วย `redirect('/portal/settings')` (กันลิงก์เก่า) |
| `classes/_client.tsx` | **ลบทิ้ง** (ไม่มีใครอื่น import — ตรวจแล้ว) |
| `company-stats/_client.tsx` | ปุ่มแก้ตั้งค่า → `/portal/settings` + copy "ตั้งค่า" |

## 3. Out of scope

- แก้จังหวัดเอง (read-only รอบนี้ — ขับ LINE จริง) · multi-company / เอกสารต่อบริษัท / SME ต่อบริษัท
  (ทุกบัญชี classes ว่างอยู่แล้วจาก N+198 — ไม่มี data สูญ) · SME/MIT/เวลาแจ้งเตือนอยู่หน้าโปรไฟล์เดิม

## 4. Success criteria

1. tsc ผ่าน · Vercel READY
2. `/portal/settings`: โชว์ 2 จังหวัดจริง · เพิ่มคำค้น+เซฟ → notes.classes[0].keywords มีค่า →
   การ์ด Keywords บน world นับถูก + discovery กลับมากรองด้วยคำ · ลบคำหมด+เซฟ → classes ว่าง = ทั้งจังหวัด
3. `/portal/classes` เด้งไป settings · แถบล่างเป็น "ตั้งค่า"
