# All-Bidders Capture (1b) — Design Spec

**วันที่:** 2026-06-13
**สถานะ:** approved design → pending implementation plan
**ประเภท:** Data pipeline — เปิดก๊อก all-bidders (ผู้ยื่นทุกราย) แบบ broad เพื่อ densify precedent + learning loop
**ที่มา:** เฟส 1b ของ all-bidders (ต่อจาก 1a ที่เปิดก๊อกฝั่ง followed-poller แล้ว — commit 64b7cf3)

---

## 1. ปัญหา & เป้าหมาย

predictor ใช้ precedent จาก **ผู้ชนะอย่างเดียว** (cgd_winners) — ทิ้งสัญญาณ ~80% (ราคาผู้แพ้). all-bidders ให้:
- precedent หนาขึ้น (1 งาน = ~6 จุด แทน 1) → percentile (p25/p75/p90) แน่นขึ้น
- โมเดลพฤติกรรมคู่แข่ง + ความถี่การยื่น (ตัวแปร C ในอนาคต)
- **self-improvement:** ข้อมูลใหม่เข้ามา → คำทำนายงานถัดไปแม่นขึ้นเอง

**1b = forward capture** ของ all-bidders สำหรับงานจังหวัดเป้าหมาย (นครพนม+บึงกาฬ) ที่เปิดซอง

## 2. หลักการออกแบบ (ตัดสินแล้ว)

| ประเด็น | เลือก | เหตุผล |
|---|---|---|
| ขอบเขต capture | **จังหวัดเป้าหมาย** (นครพนม+บึงกาฬ) | precedent อำเภอ/จังหวัดหนาขึ้นชัด (ใช้กับ blend) |
| timeline | **forward ก่อน** · backfill ทีหลัง (แยก decision) | YAGNI — เริ่มสะสมเลย, backfill ค่อยตัดสินเมื่อเห็นว่าคุ้ม |
| กลไก | **ต่อยอด `winner_sweep.py`** (Approach A) | winner_sweep = broad province sweep อยู่แล้ว (cursor/rate-limit/getProcureResult) — 1b แค่ "เก็บ loser ที่มันทิ้ง" |
| bidder ไม่มี TIN | **name-fallback (เก็บครบ)** | value ของ 1b คือ "ทุกราย" — TIN ว่าง (เจอจริง) ไม่ควรทำข้อมูลหาย |

## 3. Architecture + Capture Flow

```
winner_sweep.py (รันตามรอบ + cursor)
   │
 sweep_egp(jids, workers) — ดึง get_procure_result แบบ parallel [มีอยู่แล้ว]
   │ winfo = {winner, bidders[...]} ต่อ job
   ├─ [เดิม] extract winner → winner_cache.json
   └─ [ใหม่] collect bidders ต่อ job → return ออกมาด้วย
   │
 main() — เขียน sequential (connection เดียว, เลี่ยง parallel-write)
   └─ store.record_bid_results(jid, bidders) → bid_results (SQLite)
```

**หลักการ:**
- **ไม่เพิ่ม API call** — bidders มาจาก get_procure_result ที่ sweep_egp ดึงอยู่แล้ว
- **เลี่ยง parallel write:** workers แค่เก็บ → main เขียนทีเดียว sequential
- **capture logic = เดียวกับ 1a:** `if winfo.get("bidders"): record` (prelim=priceProposal / W0=priceAgree, INSERT OR REPLACE)

## 4. Storage + Scope + Data Quality

**ปลายทาง:** `bid_results` (VPS SQLite, มีอยู่แล้ว) — ที่ predictor/competitor_trend อ่าน
```
project_id · bidder_name · bidder_tin · price_proposal · price_agree · is_winner · result_flag · fetched_at
```
- ต่างจาก Neon `bid_history` (สำเนา dashboard, คนละ concern — ไม่ยุ่ง)
- Dedup ฟรี: PK + INSERT OR REPLACE → สวีปซ้ำ (prelim→W0) อัปเดต row เดิม

**Scope:** jids ที่ winner_sweep ประมวลผล = งานติดตาม (pending_award จังหวัดเป้าหมาย)
> ⚠️ verify ในแผน: pass 2 (eGP) ครอบ "ปีเก่า/ไม่มี province" ด้วย — งานนอกเป้าก็เก็บได้ (precedent จังหวัด ไม่เสียหาย) แต่ยืนยัน scope จริง

**Data quality — bidder ไม่มี TIN:** PK (project_id, bidder_tin) ปัจจุบัน → TIN ว่างหลายรายชนกัน → เก็บได้ 1 = หาย
- **แก้:** dedup key = `bidder_tin` fallback → `bidder_name` เมื่อ TIN ว่าง
- **migration:** ถ้าต้องเปลี่ยน PK → additive + **backup DB ก่อน** (guardrail) · เลือก least-invasive (synthetic key = tin หรือ hash(name) ไม่ pollute คอลัมน์ bidder_tin ที่ competitor_trend อ่าน)

## 5. Rate-limit + Error Handling

- **Rate-limit:** ไม่ใช่ปัญหา — ไม่เพิ่ม API call (load เท่าเดิม, cursor/max-egp เดิม)
- **Error: fail-open เด็ดขาด** — record_bid_results พัง **ห้ามทำ winner sweep พัง** → ห่อ try/except, log, ไปต่อ

## 6. Testing (TDD)
1. **name-fallback:** 2 bidder ไม่มี TIN → เก็บครบ 2 (เดิมเหลือ 1)
2. **capture:** sweep_egp มี bidders → main เรียก record_bid_results ต่อ job
3. **fail-open:** record พัง → sweep ยังคืน winner ปกติ

## 7. ไฟล์ที่แตะ
- `scripts/winner_sweep.py` — sweep_egp เก็บ bidders + main เขียน
- `scripts/Sebastian_Customer_DB.py` — `record_bid_results` รองรับ name-fallback (+ migration ถ้าจำเป็น)
- tests

## 8. Success Criteria
หลัง deploy: winner_sweep รัน → `bid_results` โต**ทั้งผู้ชนะ+ผู้แพ้** งานจังหวัดเป้าหมาย · winner extraction เหมือนเดิม · ไม่มี API เพิ่ม · fail-open พิสูจน์ด้วย test

## 9. Out of Scope (1b ไม่ทำ)
- **Backfill** ย้อนหลัง (แยก decision ทีหลัง)
- **เฟส 2 (A2):** เอา all-bidders มา densify percentile หลักใน predictor (1b แค่ "เก็บ" — การ "ใช้" เป็นเฟสถัดไป)
- **B (self-calibration win-rate):** เฟสถัดไป
- **C (competitor entry overlay):** เฟสถัดไป

## 10. ต้อง verify ตอนเขียนแผน
1. scope จริงของ winner_sweep pass 2 (มีงานนอกจังหวัดเป้าหมายไหม)
2. โครงสร้าง return ของ sweep_egp (workers/parallel) เพื่อ collect bidders สะอาด
3. วิธี name-fallback ที่ least-invasive (เลี่ยง migration ถ้าได้)

---
เกี่ยว: [[project_scope_selection_bug]] · spec `2026-06-12-predictor-credibility-layers-design.md` (§4 all-bidders foundation) · commit 64b7cf3 (1a)
