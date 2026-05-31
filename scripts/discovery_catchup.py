"""
discovery_catchup.py — รัน discovery ทันทีถ้า "พลาด scheduled slot" (2026-05-31)

ใช้กรณี: เครื่อง harvest ปิดช่วง slot (07/13/19 ไทย) → token หมด → discovery รอบนั้นไม่ได้งาน
เมื่อเครื่องกลับมา + push token สด → เรียกตัวนี้ → ถ้าพบว่าพลาด slot → รัน discovery ทันที

เรียกจาก harvest_and_push (หลัง push token สำเร็จ). no-op ถ้า: ไม่มี token valid / ไม่พลาด slot
slot (UTC) = 00/06/12 = 07/13/19 ไทย. incremental ครอบคลุมการหางานใหม่อยู่แล้ว
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

DATA = os.environ.get("BMS_DATA_DIR", "/opt/bms/data")
HB_FILE = os.path.join(DATA, "last_discovery_run.json")
TOKEN_FILE = os.path.join(DATA, "token_state.json")
SLOT_HOURS_UTC = [0, 6, 12]   # = 07/13/19 ไทย (ตรงกับ bms-province-discovery.timer)
SLACK_SEC = 5 * 60            # margin กันรันซ้ำตอน slot เพิ่งผ่านพอดี


def _load(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def _iso_to_epoch(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def _most_recent_slot(now_dt: datetime) -> float:
    """epoch ของ scheduled slot ล่าสุดที่ผ่านมาแล้ว (วันนี้/เมื่อวาน)"""
    cands = []
    for d in (0, 1):
        day = now_dt - timedelta(days=d)
        for h in SLOT_HOURS_UTC:
            cands.append(day.replace(hour=h, minute=0, second=0, microsecond=0))
    passed = [c.timestamp() for c in cands if c.timestamp() <= now_dt.timestamp()]
    return max(passed) if passed else 0.0


def _discord(msg):
    try:
        from Sebastian_Discord_Notify import load_env, get_credentials, send
        load_env()
        t, ch = get_credentials()
        send(t, ch, msg)
    except Exception:
        pass


def main() -> int:
    now = time.time()
    now_dt = datetime.now(timezone.utc)

    # 1) ต้องมี token valid (เครื่องกลับมา push สดแล้ว)
    tok = _load(TOKEN_FILE)
    if not tok or float(tok.get("expires_at", 0)) <= now:
        print("catchup: ไม่มี token valid — skip")
        return 0

    # 2) พลาด slot ไหม? (last successful discovery < slot ล่าสุดที่ผ่านมา)
    hb = _load(HB_FILE)
    last_ok = _iso_to_epoch(hb.get("ts", "")) if (hb and hb.get("status") == "ok") else 0.0
    slot = _most_recent_slot(now_dt)
    if slot == 0 or last_ok >= slot - SLACK_SEC:
        print(f"catchup: ไม่พลาด slot (last_ok={int(now-last_ok)}s ago) — skip")
        return 0

    # 3) MISSED → รัน discovery ทันที (incremental)
    missed_dt = datetime.fromtimestamp(slot, timezone.utc)
    thai = (missed_dt + timedelta(hours=7)).strftime("%H:%M")
    print(f"catchup: 🔄 พลาด slot {thai} ไทย → รัน discovery ทันที")
    _discord(f"🔄 BMS catch-up: เครื่องกลับมา + พบว่าพลาด discovery รอบ {thai} ไทย → กำลังรันให้ทันที")

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "Sebastian_Province_Discovery.py")
    r = subprocess.run(["/opt/bms/venv/bin/python", script, "--worker", "--ingest"],
                       cwd="/opt/bms/app", env={**os.environ, "BMS_DATA_DIR": DATA})
    print(f"catchup: discovery exit={r.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
