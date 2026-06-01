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
| **token reuse ข้าม project** | ⏳ _รอ probe เสร็จ — จะเติม (ตัวชี้ขาด feasibility)_ |

**ทำไมคอขวดอยู่ที่ generateToken:** `tambon_from_api` / `_enrich` ต้อง mint AES token **per-project** (key = encrypt projectId) ทุกครั้ง → resolve N งานใหม่ = generateToken N ครั้ง → ชนที่ ~30

---

## 🧭 Design ขึ้นกับผล token-reuse
- **ถ้า token ใช้ข้าม project ได้** → cache 1 token (30 นาที) ใช้ทุกงาน → generateToken แทบไม่ถูกเรียก → **คอขวดหาย "API 100%" ทำได้สบาย** ✅
- **ถ้า token ผูก project** → generateToken เป็นเพดานจริง ~30 งาน/รอบ → ต้อง throttle ที่ **generateToken** (ไม่ใช่ getProcurementDetail) + conservative มาก (cooldown ยาว)

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
