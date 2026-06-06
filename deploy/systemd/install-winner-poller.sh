#!/usr/bin/env bash
# ติดตั้ง bms-winner-poller timer — รันด้วย root: bash <ไฟล์นี้>
set -e
D=/opt/bms/app/deploy/systemd
cp "$D/bms-winner-poller.service" /etc/systemd/system/
cp "$D/bms-winner-poller.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bms-winner-poller.timer
echo "=== ✅ ติดตั้งเสร็จ ==="
systemctl is-enabled bms-winner-poller.timer
systemctl is-active  bms-winner-poller.timer
systemctl list-timers bms-winner-poller.timer --no-pager
