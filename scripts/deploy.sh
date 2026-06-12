#!/usr/bin/env bash
# BMS VPS deploy — รันบน VPS เท่านั้น:  bash scripts/deploy.sh
# pull โค้ดใหม่ + migration (init_schema, ปลอดภัย) + restart bms-api
set -e

if [ ! -d /opt/bms/app ]; then
  echo "❌ สคริปต์นี้รันบน VPS เท่านั้น (ไม่เจอ /opt/bms/app)"; exit 1
fi
cd /opt/bms/app

echo "=== 1) git pull ==="
if ! git pull --ff-only; then
  echo "[!] pull ไม่ผ่าน — แก้สิทธิ์ .git (ใส่ password ถ้าถาม) แล้วลองใหม่"
  sudo chown -R bms:bms /opt/bms/app/.git
  git pull --ff-only
fi

echo "=== 2) migration (init_schema — ไม่รัน __main__) ==="
BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c \
  "import sys; sys.path.insert(0,'scripts'); from Sebastian_Customer_DB import init_schema; init_schema()"

echo "=== 3) restart bms-api ==="
sudo systemctl restart bms-api
sleep 2
echo -n "service bms-api: "; systemctl is-active bms-api

echo "=== ✅ deploy เสร็จ (worker timers จะใช้โค้ดใหม่รอบถัดไปเอง) ==="
