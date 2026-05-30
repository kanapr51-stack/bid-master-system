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

## bms-province-discovery-full (P3 safety net — 2026-05-31)
Weekly FULL re-paginate (Sun 00:30 UTC) กัน incremental discovery พลาดงาน.
discovery ปกติ (07/13/19) = incremental (หยุดเมื่อเจอหน้าที่รู้แล้ว, ~98% req น้อยลง);
full sweep = paginate ครบ TimeoutStartSec=1800. ใส่ --full บังคับ full ด้วยมือได้
```
scp deploy/systemd/bms-province-discovery-full.* root@VPS:/etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bms-province-discovery-full.timer
```

## Live timers อื่นบน VPS (ยังไม่ version-controlled)
bms-province-discovery (07/13/19, incremental) · bms-enrichment-worker (2 นาที) · bms-line-sender ·
bms-daily-digest (08:00 UTC=15:00 ไทย) · bms-backup (03:00) · bms-rss-scraper / bms-rss-notifier (จะ RETIRE ใน P5)
