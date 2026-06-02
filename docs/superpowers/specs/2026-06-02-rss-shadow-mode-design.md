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
   ├─ incremental (07:00)      → ประทับเท่าที่เจอ
   └─ full sweep (19:30/20:30) → ประทับครบทั้งจังหวัด (safety net)
        ↓
Enrichment Worker:
   resolve location + match พื้นที่ (keyword + tambon)
   ├─ discovery_confirmed=1 → enqueue → ส่ง LINE  ✅
   └─ confirmed=0 (RSS-only) → audit เงียบ ไม่ส่ง
        ↓
Audit job: match พื้นที่ + confirmed=0 + RSS เจอ >24ชม → Discord เตือน "Discovery น่าจะพลาด"
```

## 5. Components (แก้ 4 จุด)

### 5.1 Schema migration
- `project_locations` + column `discovery_confirmed INTEGER NOT NULL DEFAULT 0`
- idempotent (ALTER TABLE … ADD COLUMN, ตรวจก่อนเพิ่ม เหมือน migration เดิม)

### 5.2 `Sebastian_Province_Discovery.py`
- หลัง scan แต่ละจังหวัด → `UPDATE project_locations SET discovery_confirmed=1 WHERE project_id IN (<project ที่เจอรอบนี้>)`
- ถ้า project ยังไม่มี row ใน project_locations (Discovery เจอก่อน RSS) → INSERT row (source='province_api', discovery_confirmed=1) — ใช้ pattern เดิมของ enrichment seed
- ทำทั้ง incremental และ full sweep

### 5.3 `Sebastian_Enrichment_Worker.py`
- เพิ่ม env `BMS_RSS_NOTIFY` (default `on` = พฤติกรรมเดิม)
- เมื่อ `BMS_RSS_NOTIFY=off`:
  - **Pass 1 (source=rss):** resolve + match ตามเดิม แต่ **enqueue เฉพาะ project ที่ `discovery_confirmed=1`**
  - งานที่ match แต่ `discovery_confirmed=0` → **ไม่ enqueue** (ปล่อยให้ audit job จับ) + log
  - **Pass 3 (source=province_api):** ไม่เปลี่ยน (งาน Discovery มี confirmed=1 อยู่แล้ว)
- เมื่อ `BMS_RSS_NOTIFY=on`: Pass 1 enqueue ตามเดิม (ไม่เช็ค confirmed)

### 5.4 Audit job (สคริปต์ใหม่ + systemd timer)
- scan `project_locations` ที่: match พื้นที่ (qualification ผ่าน) + `discovery_confirmed=0` + RSS first_seen เกิน 24 ชม
- ส่ง Discord: "⚠️ Discovery น่าจะพลาด N งานที่ RSS เจอ: [project_ids + ชื่อ]"
- timer วันละครั้ง (เช่น หลัง full sweep รอบดึก — 21:00 ไทย / 14:00 UTC)
- idempotent: ไม่เตือนซ้ำงานเดิม (เก็บ set ที่เตือนแล้ว หรือเตือนเฉพาะที่เพิ่งครบ 24ชม)

## 6. Edge cases
- **งานที่ส่ง LINE ไปแล้วก่อน deploy** → ไม่กระทบ (notification_queue เดิมคงอยู่, ไม่ re-enqueue)
- **`BMS_RSS_NOTIFY=on`** → กลับพฤติกรรมเดิมทันที (RSS ส่งได้) — reversible
- **Discovery เจอก่อน RSS** → confirmed=1 ตั้งแต่แรก → ส่งปกติ ไม่ต้องรอ
- **งานที่ RSS เจอ + Discovery ตามเจอใน <24ชม** → ไม่เตือน (ปกติ — แค่ latency รอ sweep)
- **Audit เตือนซ้ำ** → ต้องกันด้วย state (alerted set / เตือนเฉพาะ transition ครบ 24ชม)

## 7. Testing
- งาน RSS-only match + confirmed=0 → ไม่ enqueue + ขึ้น audit candidate
- Discovery ประทับตรา confirmed=1 → enqueue สำเร็จ
- งานที่ confirmed=0 เกิน 24ชม → Discord เตือน (ทดสอบด้วย mock timestamp)
- env `BMS_RSS_NOTIFY=on` → Pass 1 enqueue ตามเดิม (regression — RSS ยังส่งได้)
- schema migration idempotent (รัน 2 ครั้งไม่พัง)

## 8. Rollout
1. deploy 4 จุด + migration
2. ตั้ง `BMS_RSS_NOTIFY=off` บน VPS
3. สังเกต ~1 สัปดาห์ — เก็บสถิติ: Discovery enqueue กี่งาน, audit เตือนกี่ครั้ง
4. **เกณฑ์พิสูจน์ value:** audit **ไม่เตือนเลย** (หรือเตือนน้อยมากและอธิบายได้) = Discovery จับครบทุกงานที่ RSS เจอ
5. ถ้าพิสูจน์สำเร็จ → ตัดสินใจ (คง shadow เป็น safety net ถาวร / หรือพิจารณาปิด RSS ingest) — **อนาคต ไม่อยู่ใน scope นี้**

## 9. Scope
**Build ตอนนี้:** 4 components (schema + Discovery ประทับตรา + enqueue gate + audit job) + env toggle
**Defer (YAGNI):**
- ปิด RSS ingest ถาวร (รอผลพิสูจน์ก่อน)
- Auto-promote latency tuning (ใช้ 24ชม fixed ก่อน)
- Dashboard เปรียบเทียบ RSS vs Discovery (audit Discord พอสำหรับ beta)

## 10. Success Criteria
- user รับงานจาก Discovery path เท่านั้น (BMS_RSS_NOTIFY=off)
- งานที่ RSS เจอก่อน + Discovery ยืนยัน → ยังส่งถึง user (ไม่หาย — landmine แก้แล้ว)
- audit จับงานที่ Discovery พลาดได้จริง (ทดสอบด้วย mock)
- toggle กลับ on → RSS ส่งได้เหมือนเดิม (reversible)
