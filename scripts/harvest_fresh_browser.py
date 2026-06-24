"""
harvest_fresh_browser.py — เฉพาะกิจเน็ตเดินทาง (robust)

ปัญหาเดิม: เกาะ page target id เดียว → พอ Turnstile ผ่าน หน้า navigate →
target id เปลี่ยน → ws พัง → หลุด validate token

แก้: เกาะระดับ BROWSER ws + auto-attach ทุก target (flatten) → รอด navigation
+ launch Chrome ด้วย profile เปล่า → บังคับ Turnstile challenge สด (คลิก checkbox ได้)

flow:
  1. kill debug chrome เดิม
  2. launch chrome --remote-debugging-port=9222 --user-data-dir=<fresh> + announce page
  3. browser ws → Target.setAutoAttach flatten → Network.enable ทุก session
  4. ดัก X-Announcement-Token header / cfturnstile validate token (ข้าม navigation ได้)
  5. ป้อน ManualProvider → TokenService เขียน state → push VPS + catchup
"""

import os
import sys
import json
import time
import base64
import subprocess
import requests
import websocket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from token_service import TokenService, ManualProvider, TOKEN_PREFIX
from harvest_and_push import push_to_vps, trigger_catchup, _log, _chrome_exe

PORT = 9222
ANNOUNCE = ("https://process5.gprocurement.go.th/egp-agpc01-web/"
            "announcement?advancedSearch=true")
# profile เปล่าใหม่ทุกครั้ง (timestamped) → ไม่มี cf_clearance ค้าง → Turnstile validate สดแน่
FRESH_PROFILE = f"C:/chrome_debug_fresh_{int(time.time())}"
LISTEN_SEC = int(os.environ.get("HARVEST_LISTEN_SEC", "300"))


def kill_debug_chrome():
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
             "Where-Object { $_.CommandLine -match 'remote-debugging-port=9222' } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            capture_output=True, text=True, timeout=20)
        time.sleep(2)
    except Exception as e:
        _log(f"kill chrome warn: {e}")


def launch_fresh():
    exe = _chrome_exe()
    subprocess.Popen(
        [exe, f"--remote-debugging-port={PORT}",
         f"--user-data-dir={FRESH_PROFILE}",
         "--no-first-run", "--no-default-browser-check",
         "--disable-fre", "--ash-no-nudges", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(25):
        time.sleep(1)
        try:
            if requests.get(f"http://127.0.0.1:{PORT}/json/version", timeout=2).ok:
                return True
        except Exception:
            pass
    return False


def harvest_browser_level() -> str | None:
    ver = requests.get(f"http://127.0.0.1:{PORT}/json/version", timeout=5).json()
    bws = ver["webSocketDebuggerUrl"]
    ws = websocket.create_connection(bws, timeout=LISTEN_SEC, suppress_origin=True,
                                     max_size=None)
    box = {"token": None}
    mid = {"n": 0}

    def send(method, params=None, session=None):
        mid["n"] += 1
        msg = {"id": mid["n"], "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        ws.send(json.dumps(msg))

    # auto-attach ทุก target + waitForDebuggerOnStart=True → tab ใหม่ "หยุดรอ"
    # จน Network.enable เสร็จก่อนค่อยปล่อยวิ่ง → ไม่พลาด validate ที่ยิงวินาทีแรก
    send("Target.setAutoAttach",
         {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})
    send("Target.setDiscoverTargets", {"discover": True})
    time.sleep(1)
    if os.environ.get("HARVEST_LISTEN_ONLY") == "1":
        # เกาะ tab eGP ที่เปิดอยู่ (ไม่เปิดใหม่) → Network.enable ทุก page ปัจจุบัน
        for t in requests.get(f"http://127.0.0.1:{PORT}/json", timeout=5).json():
            if t.get("type") == "page" and "egp-agpc01" in t.get("url", ""):
                send("Target.attachToTarget", {"targetId": t["id"], "flatten": True})
    else:
        # เปิด tab eGP เอง "หลัง" arm listener → target จะ pause รอ Network.enable
        send("Target.createTarget", {"url": ANNOUNCE})

    def looks_like_token(s: str) -> bool:
        """token = base64 ของ 'EGP-ANNOUNCEMENT-KEY...:TS:HMAC'"""
        try:
            return bool(s) and TOKEN_PREFIX in base64.b64decode(s).decode("utf-8", "replace")
        except Exception:
            return False

    pending = {}                 # (session, requestId) → url : รอ response body
    seen_api = set()             # diagnostic: egp-atpj27 endpoints ที่เห็น
    deadline = time.time() + LISTEN_SEC
    ws.settimeout(5)
    _log("👂 browser-level attach แล้ว — คลิก Turnstile checkbox บนหน้า eGP ได้เลย")
    while time.time() < deadline and not box["token"]:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        m = msg.get("method")
        sess = msg.get("sessionId")
        if m == "Target.attachedToTarget":
            s = msg["params"]["sessionId"]
            send("Network.enable", session=s)        # เปิด Network ก่อน
            send("Page.enable", session=s)
            send("Runtime.runIfWaitingForDebugger", session=s)   # ปล่อย target ที่ pause
        elif m == "Network.requestWillBeSent":
            req = msg["params"]["request"]
            url = req.get("url", "")
            if "egp-atpj27" in url:
                seen_api.add(url.split("?")[0].split("/")[-1])
            for k, v in req.get("headers", {}).items():
                if k.lower() == "x-announcement-token" and v:
                    box["token"] = v
                    _log(f"🔑 จาก header X-Announcement-Token ({url.split('/')[-1][:30]})")
                    break
            # ดักทุก cfturnstile* (validate / bypasscloudflare / ฯลฯ) ไม่ fix ชื่อ
            if "cfturnstile" in url:
                pending[(sess, msg["params"]["requestId"])] = url
        elif m == "Network.responseReceived":
            url = msg["params"]["response"].get("url", "")
            if "cfturnstile" in url or "/announcement" in url:
                pending[(sess, msg["params"]["requestId"])] = url
        elif m == "Network.loadingFinished":
            key = (sess, msg["params"]["requestId"])
            if key in pending:
                send("Network.getResponseBody",
                     {"requestId": msg["params"]["requestId"]}, session=sess)
        elif "result" in msg and "body" in msg.get("result", {}):
            try:
                body = msg["result"]["body"]
                if msg["result"].get("base64Encoded"):
                    body = base64.b64decode(body).decode("utf-8", "replace")
                # ลอง .data ก่อน (รูปแบบมาตรฐาน) แล้ว fallback scan ทั้ง body
                cand = None
                try:
                    cand = json.loads(body).get("data")
                except Exception:
                    pass
                if looks_like_token(cand):
                    box["token"] = cand
                    _log("🔑 จาก response .data")
                else:
                    # brute: หา substring ที่ decode แล้วมี prefix
                    import re
                    for tok in re.findall(r'[A-Za-z0-9+/=%]{120,}', body):
                        if looks_like_token(tok):
                            box["token"] = tok
                            _log("🔑 จาก response (brute scan)")
                            break
            except Exception:
                pass
    ws.close()
    if seen_api:
        _log(f"🔎 egp-atpj27 endpoints ที่เห็น: {sorted(seen_api)}")
    return box["token"]


def main() -> int:
    listen_only = os.environ.get("HARVEST_LISTEN_ONLY") == "1"
    if listen_only:
        _log("listen-only: เกาะ Chrome ที่เปิดอยู่ (ไม่ปิด/เปิดใหม่) — รอ user กดค้นหา")
    else:
        _log("ปิด debug chrome เดิม + เปิด profile เปล่า...")
        kill_debug_chrome()
        if not launch_fresh():
            _log("❌ launch chrome ไม่ขึ้น")
            return 1
        _log("Chrome พร้อม (profile เปล่า) — Turnstile challenge สดควรโผล่")
    token = harvest_browser_level()
    if not token:
        _log("❌ ยังจับ token ไม่ได้ (timeout)")
        return 2
    _log(f"🔑 จับ token ได้ ({token[:24]}...)")
    svc = TokenService(ManualProvider(token=token), allow_refresh=True)
    if not svc.get_valid_token():
        _log(f"❌ token parse expiry ไม่ผ่าน (state={svc.health()['state']})")
        return 3
    _log(f"✅ token valid (เหลือ {svc.health()['remaining_sec']}s)")
    if push_to_vps(svc.state_path):
        trigger_catchup()
        return 0
    return 4


if __name__ == "__main__":
    sys.exit(main())
