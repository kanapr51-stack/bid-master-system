"""
harvest_and_push.py — Windows single-writer: harvest X-Announcement-Token → push VPS

รันบนเครื่อง residential (Windows) ทุก ~25 นาที (Task Scheduler)
- ensure Chrome debug port 9222 (launch ถ้ายังไม่เปิด — reuse ถ้าเปิดอยู่)
- TokenService(chrome9222).get_valid_token()  (refresh เชิงรุกเมื่อ EXPIRING)
- ถ้าได้ token valid → scp data/token_state.json → VPS:/opt/bms/data/token_state.json
- VPS รัน discovery เป็น read-only worker (allow_refresh=False) อ่าน token นี้

ทำไมต้องบน Windows: Cloudflare Turnstile ผ่านง่ายบน residential IP + browser จริง
(VPS/datacenter เสี่ยง challenge — ดู memory/project_province_search_api.md)

Env (override ได้):
  VPS_HOST   = root@45.76.156.166
  VPS_KEY    = ~/.ssh/bms_vps
  REMOTE_TOKEN = /opt/bms/data/token_state.json
  CHROME_PATH = (auto-detect)
"""

import os
import sys
import time
import shutil
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from token_service import TokenService, make_provider, _data_dir

DEBUG_PORT = 9222
DEBUG_URL = f"http://127.0.0.1:{DEBUG_PORT}/json/version"
ANNOUNCE_URL = ("https://process5.gprocurement.go.th/egp-agpc01-web/"
                "announcement?advancedSearch=true")
PROFILE_DIR = os.environ.get("CHROME_DEBUG_PROFILE", "C:/chrome_debug_profile")

VPS_HOST = os.environ.get("VPS_HOST", "root@45.76.156.166")
VPS_KEY = os.path.expanduser(os.environ.get("VPS_KEY", "~/.ssh/bms_vps"))
REMOTE_TOKEN = os.environ.get("REMOTE_TOKEN", "/opt/bms/data/token_state.json")

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _log(msg: str):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}")


def _chrome_exe() -> str:
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("ไม่เจอ chrome.exe — ตั้ง env CHROME_PATH")


def _port_up() -> bool:
    import requests
    try:
        return requests.get(DEBUG_URL, timeout=2).ok
    except Exception:
        return False


def ensure_chrome() -> bool:
    """เปิด Chrome debug ถ้ายังไม่เปิด — reuse instance เดิม (กัน spawn ซ้ำ)"""
    if _port_up():
        _log("Chrome debug 9222 เปิดอยู่แล้ว — reuse")
        return True
    _log("Chrome debug ยังไม่เปิด — launching...")
    exe = _chrome_exe()
    subprocess.Popen(
        [exe, f"--remote-debugging-port={DEBUG_PORT}",
         f"--user-data-dir={PROFILE_DIR}", ANNOUNCE_URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    for i in range(20):       # รอ boot สูงสุด 20s
        time.sleep(1)
        if _port_up():
            _log(f"Chrome debug พร้อม ({i+1}s) — รอ page โหลด Turnstile อีก 6s")
            time.sleep(6)
            return True
    _log("❌ Chrome debug ไม่ขึ้นใน 20s")
    return False


def push_to_vps(state_path: str) -> bool:
    if not shutil.which("scp"):
        _log("❌ ไม่เจอ scp ใน PATH")
        return False
    cmd = ["scp", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ConnectTimeout=15", state_path, f"{VPS_HOST}:{REMOTE_TOKEN}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        _log(f"✅ push token → {VPS_HOST}:{REMOTE_TOKEN}")
        return True
    _log(f"❌ scp ล้มเหลว (rc={r.returncode}): {r.stderr.strip()[:200]}")
    return False


def main() -> int:
    if not ensure_chrome():
        return 1
    # refresh เชิงรุก: refresh_margin สูง (22 นาที) → push token สดเกือบเต็ม TTL ทุกรอบ
    # กัน gap "token เหลือ 5 นาที ถูก reuse แล้วหมดก่อนรอบถัดไป" (root cause 2026-05-31)
    # คู่กับ harvest interval 15 นาที (task) → VPS token สดเสมอ + รอด 1 harvest fail
    svc = TokenService(make_provider("chrome9222"), allow_refresh=True,
                       refresh_margin=22 * 60)
    token = svc.get_valid_token()
    h = svc.health()
    if not token:
        _log(f"❌ harvest ล้มเหลว (state={h['state']}, err={h.get('last_error')})")
        return 2
    _log(f"🔑 token OK (state={h['state']}, เหลือ {h['remaining_sec']}s, "
         f"refresh={h['refresh_count']}/fail={h['refresh_failures']})")
    ok = push_to_vps(svc.state_path)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
