# "ไม่มีคีย์เวิร์ด = เห็นทั้งจังหวัด" + รัน clear_keyword_seed จริง — Design Spec

**วันที่:** 2026-07-12 · **สถานะ:** approved โดยคุณกัญจน์ ("โอเค ลุยเลย")
**ที่มา:** กัญจน์เคยสั่ง "ตั้งค่าเป็นไม่มีคีย์เวิร์ด" แต่ `clear_keyword_seed --apply` ไม่เคยถูกรันบน prod
(ค้างจาก N+185) — ทั้ง 4 บัญชียังแบก seed 89 คำ (N+181) และโค้ด discover ปัจจุบัน
"ไม่มี keyword → คืนว่าง" ทำให้รันเคลียร์เฉยๆ ไม่ได้ (บอร์ดจะว่างทั้ง 4 บัญชี)

## 1. Semantic ใหม่ (board discovery เท่านั้น — LINE pipeline ไม่แตะ)

- **บัญชีไม่มีคีย์เวิร์ด (classes ว่าง/ไม่มี) = เห็นทุกงานในจังหวัดที่ subscribe**
  ยังกรอง: จังหวัด AND · negative keywords · ช่วงงบ (ถ้าตั้ง) · ตัด followed · deadline/TOR fresh เดิม
- บัญชีมีคีย์เวิร์ด → พฤติกรรมเดิมเป๊ะ (ต้องชนอย่างน้อย 1 คำ)
- การ์ดที่ match แบบไม่มีคำ → `matched_keywords=[]` (UI มี guard `length > 0` อยู่แล้ว ไม่โชว์ชิป)

## 2. Touchpoints

| ไฟล์ | แก้ |
|---|---|
| `scripts/discovery_match.py` | keyword gate: `if (user_keywords or []) and not hits: return False` — ลิสต์ว่าง = ไม่บังคับคำ |
| `scripts/bms_api.py` (discover ~1633) | `if not provinces or not keywords:` → `if not provinces:` |
| `scripts/test_discovery_match.py` + `test_portal_discover_api.py` | เคสใหม่: no-keyword customer เห็นทั้งจังหวัด + negative/budget ยังตัด |
| web | **ไม่แตะ** (chips guard แล้ว) → deploy VPS อย่างเดียว |

## 3. Ops หลัง deploy (ตาม Rollout ของ clear_keyword_seed.py)

1. backup DB บน VPS ก่อน (sqlite backup API — pattern N+195)
2. dry-run `clear_keyword_seed.py` → เห็นจำนวน 4 customer → `--apply`
3. verify: customers.notes classes ว่างทั้ง 4 + `/api/portal/discover` ของ Kan Kan คืนงาน non-empty
   (matched_keywords=[]) + งานหลากประเภทระดับจังหวัด

## 4. Success criteria

1. test เดิม + ใหม่เขียวหมด (test_discovery_match / test_portal_discover_api)
2. บัญชีมี keyword เดิม → ผลลัพธ์ discover เท่าเดิมเป๊ะ (regression ใน test เดิมครอบ)
3. หลัง apply: บอร์ดคุณกัญจน์โชว์งานทั้งจังหวัด · LINE pipeline ไม่เปลี่ยน (ไม่มีไฟล์ฝั่ง notify ถูกแตะ)
