# Scale TODO: API-First Tambon Resolution + Rate-Limit-Safe

**สถานะ:** 📐 PLAN + Phase 0 probe (กำลังทำ 2026-06-02) — IMPLEMENT = defer จนกว่า rate limit ชนจริง
**ตัดสินใจโดย:** กัญจน์ 2026-06-02 — เลือก "API ground truth ทุกงาน + แก้ rate limit ด้วย engineering" (ไม่ใช่ cheap-first/text-proxy ที่ Claude เสนอตอนแรก)

---

## 🎯 เป้าหมาย
หาตำบลจาก `getProcurementDetail` (ground truth, แม่นสุด) **ทุกงานที่ผ่าน gate** (keyword + จังหวัดเป้าหมาย + post-epoch) — แก้ rate limit ด้วยการ**คุมจังหวะยิง** (throttle/queue/cache) ยอมแลก latency เพื่อ accuracy 100% ไม่ลดคุณภาพด้วย text-proxy (ที่ผิด ~7% เช่น อบต.บ้านเอื้อง→งานจริงตำบลศรีสงคราม)

ระบบปัจจุบัน**เกือบเป็น API-first อยู่แล้ว** (resolve_tambon เรียก API ก่อนทุกงาน, dept = fallback) → แผนนี้ = เสริม rate-limit safety + caching ไม่ใช่ rewrite

---

## 🔬 Phase 0 — Probe Findings (2026-06-02, `scripts/probe_rate_limit.py`)
| Finding | ค่า |
|---|---|
| **คอขวดจริง = `generateToken`** (ไม่ใช่ getProcurementDetail!) | ชนที่ **~30 calls/รอบ** |
| getProcurementDetail (ตัว detail) | ยิงได้ ≥29 calls ไม่ชน — **ยังไม่เจอเพดาน** (สูงกว่า generateToken) |
| **generateToken cooldown** | **ฟื้นช้า >2 นาที** หลัง burst (น่าจะ penalty ยิงรัว) ⚠️ ชนแล้วแพง |
| **token reuse ข้าม project** | ❌ **ผูก project** — token ข้าม project 0/6 valid, control (token ตรง project) 3/3 valid |

**ทำไมคอขวดอยู่ที่ generateToken:** `tambon_from_api` / `_enrich` ต้อง mint AES token **per-project** (key = encrypt projectId) ทุกครั้ง → resolve N งานใหม่ = generateToken N ครั้ง → ชนที่ ~30

---

## 🧭 Design — สรุปจากผล probe (token ผูก project)
**token ใช้ข้ามไม่ได้ → cache 1 token แก้ไม่ได้ → generateToken เป็นเพดานจริง ~30 งานใหม่/รอบ + cooldown >2 นาที**
→ ทางแก้:
1. **Cache `moiName` per-project ลง DB** — resolve ครั้งเดียว/งาน, ไม่ mint token ซ้ำงานเดิม (ลด generateToken เฉพาะงานใหม่)
2. **Throttle ที่ generateToken** (ไม่ใช่ getProcurementDetail) — conservative เพราะ cooldown ยาว · shared ข้าม process
3. **Queue + priority** — resolve ~30 งานใหม่/รอบ, เกินนั้นเลื่อนรอบถัดไป (deadline ใกล้ก่อน)

> Capacity คร่าว: ~30 generate ต่อ ~window แล้ว cooldown >2 นาที → throughput ~ตามด้านล่าง ต้อง probe window/cooldown แม่นเพิ่มถ้าจะ implement (probe รอบนี้ recover-test ค้างเพราะ ssh hang ยังไม่ได้ค่า window เป๊ะ)

---

## 📐 Phase 1-3 (เมื่อถึงเวลา implement)
**Phase 1 — Capacity + Design**
- capacity check: งาน resolve/วัน vs generateToken capacity (~30/รอบ × รอบ/วัน) → beta พอ? scale เกิน?
- shared rate limiter (atomic counter ข้าม process: matcher/RSS enrich/scraper) ที่ generateToken — ตั้ง (limit − margin), conservative เพราะ cooldown ยาว
- cache moiName per-project ลง DB (ใช้ซ้ำ ไม่เรียก API ซ้ำ)
- ถ้าเกิน capacity → priority queue (deadline ใกล้/งานใหม่ ก่อน)

**Phase 2 — Implement (shadow first)**
- env flag `BMS_TAMBON_RESOLVE_MODE` (rollback ได้)
- shadow: log เทียบ decision เก่า/ใหม่ ก่อน enforce

**Phase 3 — Validate + Cutover**
- วัด: rate-limit hits (เป้า 0) · backlog depth · cache hit · latency
- ผ่านเกณฑ์ → flip · rollback = env flag

---

## ⚠️ Risks
| Risk | Mitigation |
|---|---|
| งาน/วัน > capacity (scale) | priority queue + capacity monitor + alert |
| generateToken ชน → cooldown ยาว >2 นาที | throttle conservative, **อย่าให้ชน** (reactive backoff แพงมาก) |
| API ใช้ไม่ได้ (generateToken ล่ม / moiName ว่าง 13%) | ⚠️ ต้องมี degraded fallback (dept/soft) แม้ "API 100%" |
| shared limiter race (multi-process) | atomic counter (DB txn/file lock) |

## ⏰ Timing
- Phase 0 (probe) + capacity check: ทำได้เลย (low-risk)
- Phase 1-3: **scale-todo** — beta 5 users ยังไม่ชน · หยิบทำเมื่อขยายจังหวัด/volume สูง

---

## ✅ Phase 2 Progress (2026-06-02 ข้ามคืน — scope A)
- **keyword-first shadow: DEPLOYED** (env `BMS_KEYWORD_FIRST_MODE=shadow` บน VPS)
  - `job_matcher.passes_keyword()` + worker pre-check ก่อน resolve deadline/tambon
  - **shadow validation (static, งานจริง 1077): skip 363 = 33% → ประหยัด ~726 API call (~33%)**
  - shadow = log เฉยๆ ไม่แตะ production decision
- **defer:** cache moiName (value ต่ำ — งานละ 1 resolve อยู่แล้ว) · shared rate limiter (ไม่ต้องจน enforce) · window probe (เสี่ยง hammer)
- **เหลือก่อน cutover:** review shadow log (เมื่อมีงานใหม่จาก discovery) → flip `BMS_KEYWORD_FIRST_MODE=enforce` → observe ว่า filtered_no_keyword ถูกต้อง (ไม่ตัดงานถนน target)
