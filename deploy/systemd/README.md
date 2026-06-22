# BMS systemd units (VPS)

Units รันบน VPS (Vultr SG) `/etc/systemd/system/`, User=bms, EnvironmentFile=/opt/bms/app/.env

เก็บไว้ใน git เพื่อ reproducibility (ปัจจุบันมีเฉพาะ dead-man switch — units อื่นยังอยู่บน VPS เท่านั้น, ทยอยเพิ่มภายหลัง)

## bms-deadman (P1 Dead-Man Switch — 2026-05-30)
ตรวจสุขภาพระบบ live ทุก 15 นาที เปลี่ยน silent failure → observable (Discord alert):
- TOKEN_EXPIRED / HARVEST_STALE (token pipeline พัง) = CRITICAL
- DISCOVERY_STALE / DISCOVERY_NODATA = WARN
- cooldown 60 นาที/issue (กัน spam), exit 0 เสมอ

deploy:
```
scp deploy/systemd/bms-deadman.* root@VPS:/etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bms-deadman.timer
```

## bms-province-discovery-full-{nkp,bkg} (P3 safety net + reconcile)
**Daily** FULL re-paginate per-province (ground truth กัน incremental พลาด + reconcile):
- `full-nkp` (--moi 480000 นครพนม): 00:30 + 12:30 UTC = 07:30 + 19:30 ไทย
- `full-bkg` (--moi 380000 บึงกาฬ): 01:30 + 13:30 UTC = 08:30 + 20:30 ไทย

discovery ปกติ (07/13/19) = incremental (หยุดเมื่อรู้หมด 2 หน้าติดกัน, ~95-98% req น้อยลง);
full sweep = paginate ครบ + reconciliation (เจองานใหม่ announceDate เก่า >2วัน = incremental พลาด → Discord alert).
**แยกต่อจังหวัด** (ไม่ทำพร้อมกัน) เพื่อกัน rate-limit (2 จว.×~66หน้า > limit).
```
scp deploy/systemd/bms-province-discovery-full-nkp.* deploy/systemd/bms-province-discovery-full-bkg.* root@VPS:/etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bms-province-discovery-full-nkp.timer bms-province-discovery-full-bkg.timer
```
> ~~bms-province-discovery-full~~ (รวม 2 จว. รอบเดียว) = **RETIRED 2026-06-02** → แยกเป็น nkp/bkg ข้างบน (กัน rate-limit). ลบ unit แล้ว

## Live timers อื่นบน VPS (ยังไม่ version-controlled)
bms-province-discovery (07/13/19, incremental) · bms-enrichment-worker (2 นาที) · bms-line-sender ·
bms-daily-digest (08:00 UTC=15:00 ไทย) · bms-backup (03:00) · bms-rss-scraper / bms-rss-notifier (จะ RETIRE ใน P5)

## bms-winner-poller (⭐ Phase 2 — ประกาศผู้ชนะ + competitive intel)
**ทุก 6 ชม.** (00,06,12,18:15 UTC) — poll getProcureResult ของงานที่ติดตาม (B0/D0) ที่ยังไม่ได้ผู้ชนะ
→ มีผล: แจ้งผู้ชนะ+คู่แข่ง+ราคา (source_stage=followed_winner, line-sender render) + เก็บ bid_results
→ ไม่มีผล >60 วัน: ปิด (กัน loop). rate-limit: poll เฉพาะงานติดตาม (น้อย) + cooldown 3s
```
scp deploy/systemd/bms-winner-poller.* root@VPS:/etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bms-winner-poller.timer
```

## bms-backfill-bidders (เก็บผู้ยื่นซองครบของ "ทุกงาน" ไม่ใช่แค่งานติดตาม — N+162)
**รายวัน** (02:00 UTC = 09:00 ไทย, หลัง full-bkg) — `backfill_bidders.py` ไม่มี arg: provinces=นครพนม,บึงกาฬ
+ fy=`current_fy()-1,current_fy()` (คำนวณจากวันนี้ — ไม่ตายตัวเหมือนเดิม กันค้างปีงบเก่าหลัง 1 ต.ค.)
+ `project_id NOT IN bid_results` กันดึงซ้ำ → volume จริงเล็กมาก (~2-5 งาน/วัน หลัง backfill ประวัติ 12K เสร็จ 2026-06-22)
→ ไม่จำกัดแค่งานที่มีลูกค้าติดตาม (ต่างจาก bms-winner-poller) — ปิดช่องว่าง "งานไม่มีคนติดตาม = ไม่เก็บ bid_results"
```
scp deploy/systemd/bms-backfill-bidders.* root@VPS:/etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bms-backfill-bidders.timer
```
