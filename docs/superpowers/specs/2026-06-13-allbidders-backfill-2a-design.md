# All-Bidders Backfill Engine (2A) — Design

**วันที่:** 2026-06-13
**สถานะ:** design (รอ implement)
**Sub-project ของ:** เฟส 2 (all-bidders ใน predictor). 2A = evidence layer; 2B = dominant-detection predictor (brainstorm ภายหลังเมื่อมีข้อมูล)

---

## 1. Goal

เติม `bid_results` ด้วย **full-bidder list ของงานที่จบแล้ว** (ผู้ยื่นทุกราย ไม่ใช่แค่ผู้ชนะ) สำหรับงานแข่งจริงในจังหวัดเป้าหมาย ย้อนหลัง ~3 ปีงบ — เพื่อให้ predictor (2B) มี evidence เรื่องการเกาะกลุ่มของผู้ยื่น + ระยะห่างผู้ชนะ-ที่สอง (pattern "ขาดลอย")

**Non-goal (→ 2B):** budget COALESCE ใน read path, dominant-detection, clustering metric, scenario-conditional pricing, field-floor. 2A เป็น **writer ล้วน** — เอาข้อมูลเข้า ไม่แตะ predictor

## 2. Motivation / Evidence

Probe จริง (`getProcureResult('67129346506')`, e-bidding ก่อสร้างถนน นครพนม FY67): คืน **46 ผู้ยื่น** ครบสนาม — winner ลง ~1.66M (disc 39%) แต่ loser เกาะกลุ่ม 2.38–2.86M (disc ~0–17%) = ขาดลอย ~20%. ยืนยันว่า API คืน full field สำหรับงานเก่า และ pattern ที่ต้องการมีจริงในข้อมูล

ปัจจุบัน `winner_history.db` (617K งาน) / `cgd_winners` มีแต่**ผู้ชนะ** ไม่มีผู้แพ้ → ต้อง backfill ผ่าน eGP `getProcureResult`

## 3. Scope (อนุมัติแล้ว)

| มิติ | ค่า |
|---|---|
| จังหวัด | นครพนม, บึงกาฬ |
| proc_type | `COMPETITIVE_SET` = e-bidding, ประกวดราคาด้วยวิธีการทางอิเล็กทรอนิกส์, สอบราคา, คัดเลือก |
| ปีงบ | 2567, 2568, 2569 |
| เงื่อนไข | `win_price > 0` |
| ประมาณการ | ~3-4K งาน → ~3-4K API calls ≈ 2-3 ชม. unattended |
| run location | VPS (eGP เข้าได้ — winner_sweep ทำอยู่แล้ว) |
| job source | `cgd_winners` (อยู่บน VPS, มี project_id+province+budget+proc_type+fiscal_year+win_price ครบ) |

## 4. Architecture (Approach A — VPS-side, source = cgd_winners)

```
cgd_winners (candidate ids)
   │  selector: province∈target ∧ proc_type∈COMPETITIVE_SET ∧ fy∈RECENT ∧ win_price>0
   │            ∧ project_id ∉ bid_results ∧ project_id ∉ backfill_seen.json   (resume)
   ▼
loop (sequential, rate-limited):
   get_procure_result(pid)  ── flowSeqno=0 → retry 3s ×3 → cooldown
   │  bidders[]  (อาจว่าง → mark seen, ข้าม)
   ▼
record_bid_results(pid, bidders)   # 1b helper, name-fallback, idempotent
   ▼
bid_results  (+ ทุก ~50 งาน: เขียน backfill_seen.json + log progress)
```

ทุกตารางอยู่ใน `bms_customers.db` เดียว (single-DB, ไม่ต้อง ATTACH/sync)

### Components

1. **`select_candidates(conn, provinces, fy, limit=None)`** — คืน list[project_id] จาก `cgd_winners` ตาม filter, ตัดที่มีใน `bid_results` แล้ว + ที่อยู่ใน seen-set. `COMPETITIVE_SET` import จาก `cgd_intel` (sync กับ predictor). **FY รับจาก CLI** (default = scope §3 = 2567,2568,2569) — *ไม่* ผูกกับ `cgd_intel.RECENT_FY` ซึ่งปัจจุบัน=`(2566,2567,2568)` ต่างจาก scope (2569 ใหม่กว่า). หมายเหตุ: predictor (2B) อ่านเฉพาะ RECENT_FY — งาน FY2569 ที่ backfill จะยังไม่ถูกอ่านจน RECENT_FY อัปเดต (2B concern)
2. **Fetcher** — `get_procure_result(pid)` (process5_http_client). Rate-limit reuse winner_sweep: `time.sleep(1.5)` ต่องาน + cooldown 30s ทุก 50 งาน + detect rate-limit (flowSeqno=0/stepId='') → retry 3s ×3
3. **Writer** — `SubscriptionStore().record_bid_results(pid, bidders)` (idempotent INSERT OR REPLACE บน project_id+key)
4. **Checkpoint** — `data/backfill_seen.json` = set ของ project_id ที่ประมวลผลแล้ว (รวมที่ได้ 0 bidder) เขียนทุก 50 งาน + ตอนจบ. resume = อ่าน seen + skip
5. **Runner CLI** — `scripts/backfill_bidders.py`: `--provinces นครพนม,บึงกาฬ --fy 2567,2568,2569 --limit N --dry-run`. รันบน VPS ผ่าน nohup/systemd (กัญจน์ kick off)

## 5. Data flow & idempotency

- 1 call ต่องาน (ไม่เพิ่ม API budget ต่องาน)
- รันซ้ำปลอดภัย: `bid_results` INSERT OR REPLACE + selector skip already-done → resume หลัง crash/rate-limit ไม่เริ่มศูนย์
- งาน 0-bidder (เช่น cancelled / เฉพาะเจาะจงหลุด filter) → mark seen ไม่ดึงซ้ำ

## 6. Error handling (fail-open)

| เหตุการณ์ | การจัดการ |
|---|---|
| งานเดียว fetch พัง/timeout/exception | log + ข้าม + mark seen — run ไม่ล้ม |
| rate-limit (flowSeqno=0) | retry 3s ×3 → ยัง = cooldown 30s แล้วไปต่อ |
| 0 bidder | mark seen, ข้าม |
| crash กลางคัน | resume จาก seen-set (ไม่เริ่มศูนย์) |

## 7. Testing (TDD)

ไฟล์ใหม่ `scripts/test_backfill_bidders.py` (รัน `BMS_ENV=dev PYTHONIOENCODING=utf-8 python ...`):

1. **selector filter+dedup** — mock `cgd_winners`+`bid_results`: คืนเฉพาะ province/proc_type/fy ในเกณฑ์ ∧ ตัด project_id ที่มีใน bid_results แล้ว
2. **resume skip** — seen-set มี P1 → รอบถัดไปไม่คืน P1
3. **fetch loop fail-open** — mock `get_procure_result` โยน exception 1 งาน → run ไม่ล้ม, งานอื่นเขียนครบ, นับ success ถูก
4. **0-bidder skip** — mock คืน `{"bidders": []}` → mark seen, ไม่ write
5. **idempotent** — รัน 2 รอบบนงานเดิม → row ไม่ซ้ำ (อิง record_bid_results เดิม)

## 8. Verification (post-run, manual บน VPS)

1. ก่อนรัน: นับ candidate — `SELECT COUNT(*) FROM cgd_winners WHERE <filter>` ยืนยัน ~3-4K (ถ้า cgd_winners บน VPS ไม่ครบ → ดู §10 risk)
2. หลังรัน: `SELECT COUNT(DISTINCT project_id) FROM bid_results` โตขึ้นเท่าจำนวน candidate (± งาน 0-bidder)
3. sample 1 งานที่รู้ผล (เช่น 67129346506) → `get_bid_results(pid)` มี ~46 ราย, ราคาตรง probe
4. spot-check: มี loser (`is_winner=0`) จริง ไม่ใช่แค่ winner

## 9. Out of scope (→ 2B หรือภายหลัง)

- read-side budget COALESCE จาก cgd_winners ใน `_bidresult_rows` (2B ต้องการตอนคำนวณ field discount)
- dominant-detection / clustering / winner-2nd gap metric
- scenario-conditional win-price (เจ้าใหญ่มา/ไม่มา)
- ขยาย scope จังหวัด/ปีงบ

## 10. Risks & open items

- **R1: cgd_winners บน VPS อาจไม่ครบ target rows** (เป็น synced subset). Mitigation: §8.1 นับ candidate ก่อนรัน; ถ้าน้อยกว่าคาดมาก → fallback ใช้ `winner_history.db` (ต้อง copy ไป VPS หรือรัน home + sync = Approach B). **ต้อง verify ก่อน implement runner**
- **R2: getProcureResult บางงานเก่าอาจ archived/ไม่คืน bidder** — fail-open จัดการ (mark seen, ข้าม); วัดจริงตอน run (% 0-bidder)
- **R3: rate-limit window ของ getProcureResult** อาจต่างจาก winner_sweep ที่รันพร้อม pipeline อื่น — backfill รันเดี่ยว น่าจะ headroom มากกว่า; เริ่มด้วย `--limit 100` probe ก่อน full run
