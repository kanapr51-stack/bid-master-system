# Plan: Harvest Token Decoupling (ADR-004) — ตัด discovery จาก "PC บ้าน + เน็ต residential เดียว"

**วันที่:** 2026-06-17 · **สถานะ:** draft (autonomous คืนกัญจน์นอน) — รอกัญจน์ review + ตัดสิน
**ที่มา:** incident N+143 — discovery ล่มตอนเดินทาง (เครื่องบ้านปิด + เน็ตเดินทาง harvest ไม่ได้)
**เกี่ยว:** [[project_harvest_network_trust]] · [[project_incident_control_plane]] (ADR-003) · [[project_harvest_node_decision]] · [[project_deploy_debt]] · [[project_discovery_nodata_waf_turnstile]] (JA3 fix)

## ปัญหา

`harvest_and_push.py` รันบน Windows บ้าน ทุก ~25 นาที: Chrome9222 เปิด SPA eGP → ดึง
`X-Announcement-Token` → scp ขึ้น VPS. VPS discovery อ่าน token แบบ read-only.
**single point of failure = "PC เปิดตลอด + เน็ต residential ที่ Cloudflare ไว้ใจ ที่เดียว"**:
- เครื่องปิด / เดินทาง / เน็ตเปลี่ยน → harvest หยุด → discovery ตายเงียบ (N+143)
- **กัญจน์จะย้ายหอ** → เน็ตหอใหม่อาจไม่ residential-trusted → เสี่ยงตันถาวร (ไม่ใช่แค่ชั่วคราว)

## 🔑 Key unknown (ต้อง probe ก่อนเลือกทาง — อย่า assume)

`harvest_and_push.py:10-11` เขียนว่า *"VPS/datacenter เสี่ยง challenge"* — แต่เป็น assumption **ก่อน**
JA3 fix ([[project_discovery_nodata_waf_turnstile]], commit 5997fdf ทำให้ VPS discovery search ผ่าน
0 challenge). คำถามที่ยังไม่มีคำตอบ:

> **VPS (datacenter IP) ดึง blessed `X-Announcement-Token` จาก SPA ได้ไหม?**
> (discovery *search* VPS ทำได้แล้ว — แต่ token harvest เป็นคนละ flow: ต้องให้ SPA วิ่ง path
> `cfturnstile/validate` ที่มี token ไม่ใช่ `bypasscloudflare`)

ถ้า **ได้** → ไม่ต้องซื้ออะไรเลย (Option 0, ฟรี). ถ้า **ไม่ได้** → ต้องผ่าน residential path (Option A/B).
N+143 พิสูจน์แค่ว่า *laptop บนเน็ตเดินทาง* ทำไม่ได้ — **ยังไม่เคย test VPS โดยตรง**.

## Options

| | ทาง | decouple location? | cost/effort | ความเสี่ยง |
|---|---|---|---|---|
| **0** | VPS harvest เอง (headless Chrome + JA3) | ✅ เต็ม | ฟรี (ถ้าได้) | datacenter IP อาจ → bypasscloudflare (no token) |
| **A** | Residential proxy ให้ VPS ยิง harvest ผ่าน | ✅ เต็ม | ~$/เดือน (เช่า proxy) | proxy ต้องให้ path validate จริง (probe ก่อนสมัครยาว) |
| **B** | RPi ที่บ้าน (harvest node ถาวร) | ⚠️ บางส่วน | ซื้อ RPi ครั้งเดียว | **ยังผูกเน็ตที่เสียบ** (หอใหม่ไม่ residential = ตันเหมือนเดิม) |
| **C** | คงเดิม + WakeToRun PC | ❌ | ฟรี | ไม่แก้เดินทาง/ย้ายหอ — แค่กันฝาพับ ([[project_harvest_modern_standby]]) |

**สังเกต:** Option B (RPi) ที่เคยเป็น candidate ([[project_harvest_node_decision]]) **แก้ N+143 ไม่ตรงจุด** —
ปมจริงคือ "ผูก network-trust" ไม่ใช่ "ผูก device". RPi ในหอที่เน็ตไม่ residential = ตันเท่าเดิม.
ทางที่ decouple จริง = **0 (ฟรี) หรือ A (proxy)** เพราะตัด dependency เรื่อง*ประเภทเน็ต*

## Recommended sequence (probe-first, ถูก→แพง)

1. **PROBE 1 (ฟรี, ก่อนอื่น):** รัน headless Chrome บน VPS เปิด SPA → ดู response เป็น
   `cfturnstile/validate` (มี token) หรือ `bypasscloudflare` (ไม่มี). ใช้ `harvest_fresh_browser.py`
   (diagnostic ที่สร้างไว้แล้ว) พอร์ตไปรันบน VPS. **ได้ → Option 0 → จบ (port harvest logic ไป VPS, เลิก scp).**
2. **ถ้า PROBE 1 ตัน → PROBE 2:** เช่า residential proxy รายวัน (trial) → VPS ยิง harvest ผ่าน proxy →
   ดูว่าได้ path validate ไหม. **ได้ → Option A** (สมัครรายเดือน + route เฉพาะ harvest call ผ่าน proxy).
3. **ถ้าทั้งคู่ตัน → fallback Option C ชั่วคราว** (WakeToRun + ยอมรับ gap ตอนเดินทาง) จนหา proxy ที่เวิร์ก
4. **ทุกกรณี: เพิ่ม alert** — `harvest_stale > 60m` ส่ง Discord (deadman มีบางส่วนแล้ว — ดู [[project_incident_control_plane]] P1)

## Success criteria
- PROBE 1/2 = verifiable: log response path (`validate` vs `bypasscloudflare`) + token มี/ไม่มี จริง
- target สุดท้าย: เครื่องบ้านปิด/เดินทาง/ย้ายหอ → discovery **ไม่ล่ม** (harvest ไม่ผูก PC+residential เดียว)
- ไม่ regression: VPS discovery search เดิม (read-only token) ยังทำงาน

## ขอบเขต (ไม่ทำในรอบนี้)
- ❌ ไม่ซื้อ RPi (probe พิสูจน์ก่อนว่าจำเป็น — N+143 ชี้ว่า RPi ไม่ตรงปม)
- ❌ ไม่ implement ตอนนี้ — รอกัญจน์เลือก + รัน PROBE 1 บน VPS (ต้อง SSH)
- PROBE ต้องทำตอนกลับเน็ตบ้าน + discovery heal แล้ว (ไม่ชน recovery)
