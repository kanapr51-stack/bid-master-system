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
# WAF/Turnstile challenge → slot ได้ no_data → ถ้าไม่ throttle catch-up จะ re-fire ทุก harvest cycle (15 นาที)
# = Discord spam + ยิง API ซ้ำตอน IP โดน challenge. ใช้ ts ของ heartbeat (เขียนทุกรอบ ทั้ง ok/no_data)
# เป็น "เพิ่ง attempt เมื่อไหร่" → ถ้าเพิ่งลองไม่นานให้ skip. ดู memory project_discovery_nodata_waf_turnstile
CATCHUP_RETRY_SEC = 20 * 60


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


# full sweep slots (UTC) per-province — ตรงกับ bms-province-discovery-full-{nkp,bkg}.timer
FULL_SLOTS_UTC = {"480000": [(0, 30), (12, 30)],   # นครพนม 07:30/19:30 ไทย
                  "380000": [(1, 30), (13, 30)]}   # บึงกาฬ 08:30/20:30 ไทย
PROV_NAME = {"480000": "นครพนม", "380000": "บึงกาฬ"}
COOLDOWN_FULL = 150   # วินาที — กัน rate limit ระหว่างรัน full sweep แต่ละจังหวัด


def _most_recent_slot_hm(now_dt: datetime, slots) -> float:
    """slot ล่าสุดที่ผ่านมาแล้ว (slots = [(hour, minute)] UTC)"""
    cands = []
    for d in (0, 1):
        day = now_dt - timedelta(days=d)
        for (h, m) in slots:
            cands.append(day.replace(hour=h, minute=m, second=0, microsecond=0))
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

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "Sebastian_Province_Discovery.py")
    PY = "/opt/bms/venv/bin/python"
    base_env = {**os.environ, "BMS_DATA_DIR": DATA}
    ran_heavy = False   # รัน job ที่ยิง API ไปแล้วไหม → cooldown ก่อนตัวถัดไป (กัน rate limit)

    # 2) discovery slot (incremental) — พลาดไหม?
    hb = _load(HB_FILE)
    last_ok = _iso_to_epoch(hb.get("ts", "")) if (hb and hb.get("status") == "ok") else 0.0
    last_attempt = _iso_to_epoch(hb.get("ts", "")) if hb else 0.0   # ts เขียนทุกรอบ (ok/no_data)
    slot = _most_recent_slot(now_dt)
    if slot != 0 and last_ok < slot - SLACK_SEC:
        # slot ยังไม่สำเร็จ — แต่ถ้าเพิ่ง attempt ไปไม่นาน (เช่น WAF challenge) อย่ารัน/แจ้งซ้ำถี่ๆ
        if last_attempt and (now - last_attempt) < CATCHUP_RETRY_SEC:
            print(f"catchup: slot ยังไม่สำเร็จ แต่เพิ่ง attempt {int(now-last_attempt)}s ที่แล้ว "
                  f"(<{CATCHUP_RETRY_SEC}s) — skip กัน spam/ซ้ำเติม WAF")
        else:
            thai = (datetime.fromtimestamp(slot, timezone.utc) + timedelta(hours=7)).strftime("%H:%M")
            retry_tag = " (retry)" if last_attempt else ""
            print(f"catchup: 🔄 พลาด discovery slot {thai} ไทย → รัน incremental{retry_tag}")
            _discord(f"🔄 BMS catch-up: discovery รอบ {thai} ไทย ยังไม่สำเร็จ → รันให้ทันที{retry_tag}")
            r = subprocess.run([PY, script, "--worker", "--ingest"], cwd="/opt/bms/app", env=base_env)
            print(f"catchup: discovery exit={r.returncode}")
            ran_heavy = True
    else:
        print(f"catchup: ไม่พลาด discovery slot (last_ok={int(now-last_ok)}s ago)")

    # 3) full sweep slots (per-province) — safety net catch-up (quiet retry)
    # full sweep จบ partial เพราะ rate limit = เรื่องปกติ (single-province paginate > budget/window).
    # ไม่ใช่ 'พลาด' → ไม่เด้ง Discord ตอน retry ปกติ. retry เงียบให้ครบ + throttle กัน spam.
    # alert เฉพาะกรณีเดียว: retry แล้ว 'ยัง partial ซ้ำ' = rate budget ตันจริง. ดู memory project_discovery_nodata_waf_turnstile
    def _read_marker(moi):
        fm = _load(os.path.join(DATA, f"last_fullsweep_{moi}.json"))
        ts = _iso_to_epoch(fm.get("ts", "")) if fm else 0.0
        partial = bool(fm.get("partial")) if fm else False
        return ts, partial

    for moi, slots in FULL_SLOTS_UTC.items():
        name = PROV_NAME.get(moi, moi)
        last_full, is_partial = _read_marker(moi)
        fslot = _most_recent_slot_hm(now_dt, slots)
        if fslot == 0:
            continue
        # slot สำเร็จครบแล้ว (complete marker) → ไม่ต้องทำอะไร
        if last_full >= fslot - SLACK_SEC and not is_partial:
            print(f"catchup: ไม่พลาด full sweep {name} (complete)")
            continue
        # throttle: เพิ่ง attempt slot นี้ไม่นาน (partial) → skip เงียบ กัน spam/ซ้ำเติม rate limit
        if last_full >= fslot - SLACK_SEC and is_partial and (now - last_full) < CATCHUP_RETRY_SEC:
            print(f"catchup: full sweep {name} เพิ่ง attempt {int(now-last_full)}s (partial) — skip throttle")
            continue
        # ต้องรัน: timer ยังไม่รัน slot นี้ หรือ partial เกิน retry window → retry 'เงียบ' (ไม่เด้ง 'พลาด')
        if ran_heavy:
            print(f"catchup: cooldown {COOLDOWN_FULL}s ก่อน full sweep (กัน rate limit)")
            time.sleep(COOLDOWN_FULL)
        thai = (datetime.fromtimestamp(fslot, timezone.utc) + timedelta(hours=7)).strftime("%H:%M")
        print(f"catchup: 🔄 full sweep {name} slot {thai} ยังไม่ครบ → retry เงียบ --full --moi {moi}")
        r = subprocess.run([PY, script, "--worker", "--ingest", "--full", "--moi", moi],
                           cwd="/opt/bms/app", env=base_env)
        print(f"catchup: full sweep {name} exit={r.returncode}")
        ran_heavy = True
        # recheck marker หลัง retry — ครบ=เงียบ / ยัง partial ซ้ำ=เด้ง alert (rate budget ตันจริง)
        ts2, partial2 = _read_marker(moi)
        if ts2 >= fslot - SLACK_SEC and not partial2:
            print(f"catchup: ✅ full sweep {name} ครบหลัง retry (เงียบ ไม่เด้ง)")
        else:
            _discord(f"⚠️ BMS: full sweep {name} รอบ {thai} ยัง partial หลัง retry "
                     f"(ชน rate limit ซ้ำ — ดู rate budget/pagination)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
