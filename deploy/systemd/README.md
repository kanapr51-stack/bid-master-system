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

## Live timers อื่นบน VPS (ยังไม่ version-controlled)
bms-province-discovery (07/13/19) · bms-enrichment-worker (2 นาที) · bms-line-sender ·
bms-daily-digest (08:00) · bms-backup (03:00) · bms-rss-scraper / bms-rss-notifier (จะ RETIRE ใน P5)
