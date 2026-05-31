# BMS Runbook — Dead-Man Alerts

หลักการ: **alert บอกอาการ (symptom) เท่านั้น — runbook นี้คือ hypotheses + วิธีแก้** (กัน confirmation bias)

---

## 🔴 TOKEN EXPIRED — หมดอายุ N นาที (TTL remaining: 0)
VPS token หมดอายุ → discovery ดึงงานใหม่ไม่ได้ (notification ที่ enqueue แล้วยังส่งได้)

**สาเหตุที่เป็นไปได้ (เรียงตามความน่าจะเป็น):**
1. **Refresh logic** — writer reuse token เก่าไม่ push สด (root cause 2026-05-31, fix: refresh_margin=22m + interval 15m). เช็ค `token_harvest_log.ndjson` ว่า refresh สำเร็จห่างกันเกิน TTL ไหม
2. Windows `BMS_TokenHarvest` task หยุด/disabled → `Get-ScheduledTaskInfo BMS_TokenHarvest`
3. push (scp) ไป VPS ล้มเหลว → เช็ค harvest log success แต่ VPS token เก่า = push fail
4. Chrome9222 ดับ / Turnstile challenge ค้าง → `curl localhost:9222/json/version`
5. เครื่อง Windows ดับ

**แก้ทันที:** `python scripts/harvest_and_push.py` (Windows) → เช็ค VPS token remaining

## 🔴 NO REFRESH — ไม่มี harvest refresh attempt N นาที
harvest ไม่ได้พยายาม refresh เลย (`last_refresh_attempt` เก่า)

**สาเหตุ:** เหมือนข้อ 2-5 ข้างบน (task หยุด / Chrome ดับ / เครื่องดับ). หมายเหตุ: ถ้า token ยัง valid อยู่ writer อาจ skip refresh (ไม่ update last_refresh_attempt) — หลัง fix 2026-05-31 (margin 22m) จะ refresh ทุกรอบ
**แก้:** เช็ค task state + รัน harvest_and_push มือ

## 🔴 TOKEN_STATE หาย/อ่านไม่ได้
`/opt/bms/data/token_state.json` หาย/corrupt
**แก้:** รัน harvest_and_push (สร้างใหม่) / เช็ค disk + permission

## 🟠 DISCOVERY STALE — ไม่มี discovery run N ชม.
heartbeat `last_discovery_run.json` เก่าเกิน 14 ชม. (เผื่อ overnight gap 12 ชม.)
**สาเหตุ:** `bms-province-discovery.timer` หยุด / discovery crash ก่อนเขียน heartbeat / rate-limit abort ทุกรอบ
**แก้:** `systemctl status bms-province-discovery.timer` + `journalctl -u bms-province-discovery.service`

## 🟠 DISCOVERY NO_DATA — รอบล่าสุดได้ 0 รายการ
discovery รันแต่ได้ 0 (heartbeat status=no_data)
**สาเหตุ:** rate-limit (eGP search endpoint) / token reject / API เปลี่ยน
**แก้:** เช็ค token valid + รัน discovery มือดู log; ถ้า rate-limit รอ window cleared (P1 graceful abort จะ heartbeat no_data)

---

## ⚡ Reconcile alert (จาก discovery full sweep)
"full sweep เจอ N งานใหม่ announceDate เก่า = incremental น่าจะพลาด"
**หมายความว่า:** ordering assumption ของ incremental อาจ drift → ตรวจ `Sebastian_Province_Discovery.py` stop logic + eGP sort order
