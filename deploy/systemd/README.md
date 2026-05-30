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

## bms-province-discovery-full (P3 safety net + reconcile — 2026-05-31)
**Daily** FULL re-paginate (00:30 UTC=07:30 ไทย) — ground truth กัน incremental พลาด + reconcile.
discovery ปกติ (07/13/19) = incremental (หยุดเมื่อรู้หมด 2 หน้าติดกัน = margin กัน ties, ~95-98% req น้อยลง);
full sweep = paginate ครบ TimeoutStartSec=1800 + **reconciliation**: ถ้าเจองานใหม่ announceDate เก่ากว่า 2 วัน
= incremental น่าจะพลาด → Discord alert (พิสูจน์ ordering assumption ด้วย evidence ทุกวัน).
หลัง 2-4 สัปดาห์พลาด 0 → ผ่อนกลับ weekly ได้. ใส่ --full บังคับ full ด้วยมือได้
```
scp deploy/systemd/bms-province-discovery-full.* root@VPS:/etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bms-province-discovery-full.timer
```

## Live timers อื่นบน VPS (ยังไม่ version-controlled)
bms-province-discovery (07/13/19, incremental) · bms-enrichment-worker (2 นาที) · bms-line-sender ·
bms-daily-digest (08:00 UTC=15:00 ไทย) · bms-backup (03:00) · bms-rss-scraper / bms-rss-notifier (จะ RETIRE ใน P5)
