# CGD Winner Refresh Pipeline — Design Spec

**วันที่:** 2026-06-06 · **สถานะ:** approved (กัญจน์) → เขียน plan ต่อ

## Goal (1 ประโยค)
ดึงข้อมูลผู้ชนะ "ทุกงาน" จาก CGD Open Data (data.go.th) แบบ incremental บน **residential node** เพื่อ (1) keep `winner_history.db` ให้สด (ถึงปีปัจจุบัน 2569) สำหรับวิเคราะห์ + (2) sync subset เป้าหมายขึ้น VPS ป้อน competitive-intel ใน app

## Why
- "winner ทุกงาน real-time" ผ่าน eGP getProcureResult = **infeasible** (71K งาน × 2 call = ชน rate-limit/WAF). CGD = แหล่ง bulk ที่ถูกต้อง (open data, ไม่ติด rate-limit)
- ปัญหาปัจจุบัน: `winner_history.db` หยุดที่ **FY2568, ไม่มี FY2569 เลย** (resource ปีปัจจุบันไม่ได้อยู่ใน config + ไม่มี refresh)
- CGD โดน **403 จาก VPS** (datacenter IP block — เหมือน eGP WAF) → **ต้องรันจาก residential** (พิสูจน์แล้ว: local ผ่าน, VPS 403) → ตรง [[project_harvest_node_decision]]

## Non-goals (YAGNI)
- ❌ depth (ราคาคู่แข่งที่แพ้) — นั่นคือ Phase 2 เดิม (getProcureResult เฉพาะปักหมุด) แยกกัน
- ❌ ดึง 77 จังหวัดตอนนี้ (เริ่ม 2 จังหวัดเป้าหมาย แต่เขียนให้ขยายได้)
- ❌ ยัด winner_history.db เต็ม (2.6GB) ขึ้น VPS
- ❌ ซื้อ hardware ตอนนี้ (รันบนเครื่องบ้านก่อน; เลือกแล้วว่าอนาคต = **mini PC x86** ไม่ใช่ RPi เพราะ token harvest/browser พิสูจน์บน x86)

## Decisions (ล็อกจาก brainstorm)
| เรื่อง | ตัดสิน |
|---|---|
| Geographic | 2 จังหวัด (นครพนม+บึงกาฬ) ก่อน + code ขยาย 77 ได้ |
| Consumer | ทั้ง app (VPS subset) + วิเคราะห์ (full DB บน node) |
| Full DB อยู่ที่ไหน | บน residential node (analysis ที่นั่น, reuse analytics เดิม) |
| VPS ได้อะไร | subset เป้าหมาย (เบา) ป้อน competitive intel |
| Sync | **scp incremental** (pattern `harvest_and_push.py` — ไม่ git, กัน deploy-debt) |
| Cadence | รายวัน incremental (auto no-op ถ้า CGD ไม่มีใหม่) |
| Portability | **OS-agnostic core (Python ล้วน) + scheduler แยก** → ย้าย Windows→mini PC/RPi = เปลี่ยนแค่ cron |

---

## สถาปัตยกรรม
```
🏠 residential node (เครื่องบ้าน → อนาคต mini PC x86)   [residential IP = CGD ผ่าน]
   1. CGD incremental pull (รายวัน, cursor-based) → upsert winner_history.db (full)
   2. [วิเคราะห์ — มีอยู่แล้ว] work-type analytics + competitor profiles → Google Sheets (จะสดขึ้น)
   3. extract subset (นครพนม+บึงกาฬ) → scp → VPS
                                          ↓
🖥️ VPS: ตาราง cgd_winners (target subset) → competitive intel ใน LINE (future feature)
```

## Components (ไฟล์)
- `scripts/cgd_resource_catalog.py` (ใหม่) — หา/เก็บ rid ของแต่ละปี (รวม FY2569) ผ่าน CKAN `package_search`/`package_show`; แทน hardcode `CGD_CONTRACT_RIDS`. คืน rid ตามปี
- `scripts/cgd_winner_refresh.py` (ใหม่, OS-agnostic core) — pull incremental (cursor `cgd_discovery_cursor.json` เดิม) → upsert winner_history.db (dedup รหัสโครงการ); reuse `cgd_discovery._cgd_search`
- `scripts/cgd_sync_to_vps.py` (ใหม่) — extract subset เป้าหมาย → scp ไป VPS (delta เท่านั้น) → ฝั่ง VPS merge เข้าตาราง `cgd_winners`
- scheduler: **แยกจาก logic** — Windows = `harvest_task.bat` เพิ่ม 1 บรรทัด / mini PC,RPi = cron (เอกสารใน runbook)
- (VPS) migrate: ตาราง `cgd_winners` (project_id, winner, winning_price, announce_date, province, dept, fetched_at) — สำหรับ app

## Data flow + freshness
- pull: cursor เก็บ "ดึงถึงไหนแล้ว" → รอบถัดไปดึงเฉพาะใหม่ (CGD sort `_id desc`, หยุดเมื่อเจอ seen)
- freshness = จำกัดด้วย CGD publish lag → **วัดจริงตอน implement**: max(วันที่ประกาศ) vs วันนี้ + อ่าน metadata "ความถี่ปรับปรุง" ของ dataset (CKAN `package_show`)
- ถ้า CGD lag มาก → freshness ต่ำเป็นธรรมชาติ (ยอมรับ — เป็นข้อจำกัดแหล่งข้อมูล ไม่ใช่ระบบเรา)

## Error handling
- 403/network → log + retry รอบหน้า (ไม่ crash)
- scp fail → retry; VPS merge เป็น idempotent upsert (dedup project_id)
- field วันที่เป็น Thai text ("9-เม.ย.-67") → normalize ด้วย parser ที่มีใน winner_history_build เดิม

## Testing (TDD)
- `cgd_resource_catalog`: หา rid ปีได้ (mock CKAN response)
- `cgd_winner_refresh`: incremental cursor (รอบ 2 ดึงเฉพาะใหม่) + upsert dedup (unit, temp DB)
- subset extract: กรองเฉพาะ 2 จังหวัด (unit)
- VPS merge idempotent (unit)
- date normalize (Thai → ISO)

## Phasing
- **Phase 1:** resource catalog (หา FY2569) + cgd_winner_refresh (เติม 2569 เข้า winner_history.db บนเครื่องบ้าน) + วัด freshness จริง
- **Phase 2:** subset → VPS sync (`cgd_winners` table) — เปิดทางให้ feature competitive intel ใน app
- **Phase 3 (future):** ขยาย 77 จังหวัด + ย้ายลง mini PC (cron)

## Open item (ทำใน Phase 1)
- หา rid FY2569 จริง (CKAN package_search "egp" / "จัดซื้อจัดจ้าง" ปี 2569) — ยืนยันว่ามี dataset 2569 ไหม + โครง field ตรงกับปีเก่า
