# Spec: RSS Shadow Mode

**วันที่:** 2026-06-02
**สถานะ:** Design approved (กัญจน์ 2026-06-02)
**เป้าหมาย:** พิสูจน์ value ของ Discovery — ส่ง user เฉพาะงานที่ Discovery/full sweep ยืนยัน, ใช้ RSS เป็น shadow audit คอยจับผิดว่า Discovery พลาดงานไหม

---

## 1. เป้าหมาย & หลักการ
- **user รับงานเฉพาะที่ Discovery+full sweep ยืนยัน** (pure shadow — ไม่ส่งจาก RSS โดยตรง)
- **RSS ยัง ingest + resolve + match เงียบๆ** เป็น ground truth คอยจับผิด Discovery
- **ไม่ตาบอด:** ถ้า Discovery พลาดงานที่ RSS เจอ → audit เตือนทันที → ดึงกลับได้
- หลักการ: **"Observe before optimize"** — วัดก่อนตัด RSS ถาวร
- **Reversible 100%:** env toggle กลับเป็นพฤติกรรมเดิมได้ทันที

## 2. Design decisions (จาก brainstorming)
| ประเด็น | ตัดสินใจ |
|---|---|
| งานที่ RSS เจอก่อน Discovery | **รอ Discovery ยืนยันก่อนค่อยส่ง** (pure shadow) |
| Alert threshold | **24 ชม** (ครบ 1 รอบ full sweep + margin, false alarm ต่ำ) |
| กลไก claim | **Approach A — Discovery ประทับตรา** `discovery_confirmed` |
| ประทับตรา | **ทั้ง incremental + full sweep** (full sweep = safety net ครบทั้งจังหวัด) |
| Rollout | สังเกต **~1 สัปดาห์** → audit ไม่เตือน = พิสูจน์ value สำเร็จ |

## 3. Landmine ที่ต้องระวัง (เหตุผลของ design นี้)
`record_project_seen` ใช้ `INSERT OR IGNORE` → `projects_seen.source` = **ใครเจอก่อน** RSS เป็น real-time จึงเจอก่อนเกือบทุกงาน → `source='rss'` ถาวร แม้ Discovery จะเจอภายหลัง (dedup ทิ้ง)

→ **ถ้าปิด Pass 1 (RSS enqueue) ดื้อๆ งานที่ RSS เจอก่อน (≈ ทั้งหมด) จะไม่ถูกส่งเลย** เพราะ Discovery ไม่เคย "claim" มัน

→ จึงต้องมีกลไกให้ Discovery ประทับตรา `discovery_confirmed=1` กับงานที่มันเห็น (รวมงานที่ RSS เจอก่อน) แยกจาก `source` (เก็บ provenance บริสุทธิ์)

## 4. Architecture
```
RSS Notifier  → project_locations (source=rss, discovery_confirmed=0)
Discovery     → ประทับ discovery_confirmed=1 ให้ทุก project ที่ scan เจอ
   ├─ incremental (07:00 / 13:00 / 19:00)  → ประทับเท่าที่เจอ
   └─ full sweep ครบทั้งจังหวัด (safety net) — นครพนม 07:30+19:30 · บึงกาฬ 08:30+20:30
        → จบแต่ละรอบ ส่ง Discord report ย่อย (4 ครั้ง/วัน)
        ↓
Enrichment Worker:
   resolve location + match พื้นที่ (keyword + tambon)
   ├─ discovery_confirmed=1 → enqueue → ส่ง LINE  ✅
   └─ confirmed=0 (RSS-only) → audit เงียบ ไม่ส่ง
        ↓
Audit รายวัน (21:00): รายงานเสมอ — Discovery ส่งกี่งาน + งานที่ RSS เจอแต่ Discovery พลาด >24ชม
```

## 5. Components (แก้ 5 จุด)

### 5.1 Schema migration
- `project_locations` + column `discovery_confirmed INTEGER NOT NULL DEFAULT 0`
- idempotent (ALTER TABLE … ADD COLUMN, ตรวจก่อนเพิ่ม เหมือน migration เดิม)

### 5.2 `Sebastian_Province_Discovery.py`
- หลัง scan แต่ละจังหวัด → `UPDATE project_locations SET discovery_confirmed=1 WHERE project_id IN (<project ที่เจอรอบนี้>)`
- ถ้า project ยังไม่มี row ใน project_locations (Discovery เจอก่อน RSS) → INSERT row (source='province_api', discovery_confirmed=1) — ใช้ pattern เดิมของ enrichment seed
- ทำทั้ง incremental (07:00/13:00/19:00) และ full sweep (4 รอบ)
- **จบแต่ละ full sweep → ส่ง Discord report ย่อย** (scan เจอ X / ประทับตรา Y / RSS เห็นแต่ Discovery ยังไม่เจอ Z) — รายงานเสมอไม่ว่าเจอ gap หรือไม่. 4 รอบ/วัน (นครพนม 07:30+19:30 · บึงกาฬ 08:30+20:30)

### 5.3 `Sebastian_Enrichment_Worker.py`
- เพิ่ม env `BMS_RSS_NOTIFY` (default `on` = พฤติกรรมเดิม)
- เมื่อ `BMS_RSS_NOTIFY=off`:
  - **Pass 1 (source=rss):** resolve + match ตามเดิม แต่ **enqueue เฉพาะ project ที่ `discovery_confirmed=1`**
  - งานที่ match แต่ `discovery_confirmed=0` → **ไม่ enqueue** (ปล่อยให้ audit job จับ) + log
  - **Pass 3 (source=province_api):** ไม่เปลี่ยน (งาน Discovery มี confirmed=1 อยู่แล้ว)
- เมื่อ `BMS_RSS_NOTIFY=on`: Pass 1 enqueue ตามเดิม (ไม่เช็ค confirmed)

### 5.4 Audit job รายวัน (สคริปต์ใหม่ + systemd timer)
- timer วันละครั้ง — **21:00 ไทย (14:00 UTC)** หลัง full sweep รอบเย็นจบครบ
- **รายงานเสมอ** (ไม่ว่าสำเร็จหรือพบ gap) — heartbeat ว่า audit ยังทำงาน:
  ```
  📊 RSS Shadow Audit รายวัน
  • Discovery ส่ง user วันนี้: A งาน
  • Shadow backlog (RSS target, confirmed=0): N งาน  ← leading indicator
      อายุ: 0-6ชม X · 6-12ชม Y · 12-24ชม Z · >24ชม B
  • confirmed rate: C% (confirmed=1 / RSS target resolved)
  • RSS เห็นแต่ Discovery พลาด >24ชม: B งาน
  • สถานะ: ✅ Discovery จับครบ  /  ⚠️ พบ gap B งาน [project list]
  ```
- เกณฑ์ gap (lagging): `project_locations` match พื้นที่ + `discovery_confirmed=0` + RSS first_seen เกิน 24 ชม
- **Leading indicators (ChatGPT review 2026-06-03):** lagging audit (>24ชม) รู้ช้าเกินถ้า Discovery regression (token/rate-limit/incremental bug) — เพิ่ม 3 ตัวเห็นเร็วกว่า:
  1. **shadow backlog size** = count(RSS target + confirmed=0 + age<24ชม) — ถ้าโตผิดปกติ = Discovery กำลังพลาด เห็นก่อนครบ 24ชม
  2. **age distribution** (0-6/6-12/12-24/>24ชม) — ดู trend ก่อน alert (ไม่ binary)
  3. **confirmed rate** = confirmed=1 / RSS-target-resolved — สุขภาพรวมของ claim
- idempotent: gap ที่เคยเตือนแล้วยังคงนับใน "สถานะ" แต่ไม่สแปม (รายงานรวมวันละครั้งอยู่แล้ว)

### 5.5 Per-sweep report (ใน `Sebastian_Province_Discovery.py`)
- จบแต่ละ full sweep → ส่ง Discord report ย่อย **รายงานเสมอ** (4 ครั้ง/วัน):
  ```
  🔍 Full sweep บึงกาฬ จบ (20:30)
  • scan เจอ: 347 งาน
  • ประทับตรา Discovery: 347 (ใหม่ 2)
  • RSS เห็นแต่ Discovery ยังไม่เจอ: 0 งาน ✅
  ```
- ใช้ `_discord()` ที่มีอยู่แล้วใน Province_Discovery
- รวม Discord ช่วง shadow = **5/วัน** (4 per-sweep + 1 daily audit) — verbose แต่เหมาะช่วงพิสูจน์ value (dev channel). ลด per-sweep ออกได้หลังพิสูจน์เสร็จ

## 6. Edge cases
- **งานที่ส่ง LINE ไปแล้วก่อน deploy** → ไม่กระทบ (notification_queue เดิมคงอยู่, ไม่ re-enqueue)
- **`BMS_RSS_NOTIFY=on`** → กลับพฤติกรรมเดิมทันที (RSS ส่งได้) — reversible
- **Discovery เจอก่อน RSS** → confirmed=1 ตั้งแต่แรก → ส่งปกติ ไม่ต้องรอ
- **งานที่ RSS เจอ + Discovery ตามเจอใน <24ชม** → ไม่เตือน (ปกติ — แค่ latency รอ sweep)
- **Audit เตือนซ้ำ** → ต้องกันด้วย state (alerted set / เตือนเฉพาะ transition ครบ 24ชม)

## 7. Testing
- งาน RSS-only match + confirmed=0 → ไม่ enqueue + ขึ้น audit candidate
- Discovery ประทับตรา confirmed=1 → enqueue สำเร็จ
- งานที่ confirmed=0 เกิน 24ชม → audit รายวันรายงาน gap (ทดสอบด้วย mock timestamp)
- per-sweep report ส่ง Discord จบทุก full sweep (รายงานเสมอ แม้ gap=0)
- env `BMS_RSS_NOTIFY=on` → Pass 1 enqueue ตามเดิม (regression — RSS ยังส่งได้)
- schema migration idempotent (รัน 2 ครั้งไม่พัง)

## 8. Rollout — evidence-based gate (ChatGPT review 2026-06-03)
**Decision (Co-Architect approved 2026-06-03): flip gate ก็ต่อเมื่อ metric สนับสนุน — ห้ามเดา**

1. deploy 5 จุด + migration — **gate ยัง `on`** (ไม่เปลี่ยนพฤติกรรม user)
2. **48h dry-run** (gate ยัง on): Discovery ประทับตราเดินปกติ + audit เก็บ metric — ยังไม่ตัดงาน
3. **เกณฑ์ flip (confirmed-rate gate):** วัดหลัง 48h
   - confirmed rate **≥ ~99%** + backlog age ไม่มี >24ชม ค้าง → **flip `off` ได้** (มั่นใจ Discovery claim ครบ)
   - confirmed rate **ต่ำ (เช่น ~80%)** หรือมี >24ชม ค้าง → **ห้าม flip** — มี gap ใหญ่ ต้องสืบก่อน
4. flip `BMS_RSS_NOTIFY=off` → สังเกตต่อ ~1 สัปดาห์ (audit รายวัน + leading metrics)
5. **เกณฑ์พิสูจน์ value:** audit gap = 0 ต่อเนื่อง + confirmed rate สูง = Discovery จับครบ
6. ถ้าพิสูจน์สำเร็จ → P4 ตัดสินใจ demote RSS (คง shadow safety net / ปิด ingest) — อนาคต ไม่อยู่ใน scope นี้

**Rollout philosophy:** เปลี่ยนจาก "รอเวลาแล้ว flip" → "flip เมื่อหลักฐาน (confirmed rate) สนับสนุน" — observe before optimize

## 9. Scope
**Build ตอนนี้:** 5 components (schema + Discovery ประทับตรา + enqueue gate + audit รายวัน + per-sweep report) + env toggle
**Defer (YAGNI):**
- ปิด RSS ingest ถาวร (รอผลพิสูจน์ก่อน)
- Auto-promote latency tuning (ใช้ 24ชม fixed ก่อน)
- Dashboard เปรียบเทียบ RSS vs Discovery (audit Discord พอสำหรับ beta)

## 10. Success Criteria
- user รับงานจาก Discovery path เท่านั้น (BMS_RSS_NOTIFY=off)
- งานที่ RSS เจอก่อน + Discovery ยืนยัน → ยังส่งถึง user (ไม่หาย — landmine แก้แล้ว)
- audit จับงานที่ Discovery พลาดได้จริง (ทดสอบด้วย mock)
- toggle กลับ on → RSS ส่งได้เหมือนเดิม (reversible)
