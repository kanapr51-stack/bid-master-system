"""
harvest_existing_tab.py — เฉพาะกิจ (เน็ตเดินทาง/Turnstile แบบต้องคลิก)

ต่างจาก harvest_and_push: ตัวนั้นเปิด tab ใหม่ → โดน Turnstile challenge ซ้ำ
ตัวนี้ "เกาะ tab เดิม" ที่ผู้ใช้ผ่าน Turnstile ด้วยมือแล้ว (มี cf_clearance)
→ Network.enable → Page.reload → จับ X-Announcement-Token / cfturnstile token
→ ป้อนเข้า TokenService (ManualProvider) เขียน token_state.json
→ reuse push_to_vps + trigger_catchup จาก harvest_and_push

ถ้า reload แล้วยังไม่ได้ token ภายใน ~30s → สคริปต์จะบอกให้กดปุ่ม "ค้นหา" บนหน้า
(การค้นหายิง /announcement API พร้อม header X-Announcement-Token แน่นอน)
"""

import os
import sys
import json
import base64
import requests
import websocket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from token_service import TokenService, ManualProvider, TOKEN_PREFIX
from harvest_and_push import push_to_vps, trigger_catchup, _log

DEBUG = "http://localhost:9222"
TIMEOUT = 300


def find_announce_tab():
    tabs = requests.get(f"{DEBUG}/json", timeout=5).json()
    for t in tabs:
        if t.get("type") == "page" and "announcement" in t.get("url", ""):
            return t
    return None


def harvest_existing() -> str | None:
    tab = find_announce_tab()
    if not tab:
        _log("❌ ไม่เจอ tab announcement ที่เปิดอยู่")
        return None
    _log(f"เกาะ tab เดิม: {tab.get('url','')[:70]}")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"],
                                     timeout=TIMEOUT, suppress_origin=True)
    box = {"token": None}
    mid = {"n": 0}

    def send(method, params=None):
        mid["n"] += 1
        ws.send(json.dumps({"id": mid["n"], "method": method, "params": params or {}}))

    send("Network.enable")
    send("Page.enable")
    # listen-only: ไม่แตะหน้า (clearance ผ่านแล้ว) — รอผู้ใช้กด "ค้นหา"
    # request ค้นหายิง X-Announcement-Token header → ดักตรงนั้น

    import time
    deadline = time.time() + TIMEOUT
    pending = {}
    ws.settimeout(5)
    _log("👂 listen-only กำลังรอ — กดปุ่ม 'ค้นหา' บนหน้า eGP ได้เลย")
    while time.time() < deadline and not box["token"]:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        m = msg.get("method")
        if m == "Network.requestWillBeSent":
            req = msg["params"]["request"]
            for k, v in req.get("headers", {}).items():
                if k.lower() == "x-announcement-token" and v:
                    box["token"] = v
                    break
            if "cfturnstile/validate" in req.get("url", ""):
                pending[msg["params"]["requestId"]] = True
        elif m == "Network.loadingFinished":
            rid = msg["params"]["requestId"]
            if rid in pending:
                send("Network.getResponseBody", {"requestId": rid})
        elif "result" in msg and "body" in msg.get("result", {}):
            try:
                body = msg["result"]["body"]
                if msg["result"].get("base64Encoded"):
                    body = base64.b64decode(body).decode("utf-8", "replace")
                data = json.loads(body).get("data")
                if data and TOKEN_PREFIX in base64.b64decode(data).decode("utf-8", "replace"):
                    box["token"] = data
            except Exception:
                pass
    ws.close()
    return box["token"]


def main() -> int:
    token = harvest_existing()
    if not token:
        _log("❌ ยังจับ token ไม่ได้ (timeout)")
        return 1
    _log(f"🔑 จับ token ได้ ({token[:24]}...)")
    # ป้อนผ่าน ManualProvider → TokenService เขียน state ฟอร์แมตเดียวกับ chrome9222
    svc = TokenService(ManualProvider(token=token), allow_refresh=True)
    valid = svc.get_valid_token()
    h = svc.health()
    if not valid:
        _log(f"❌ token ใช้ไม่ได้ (state={h['state']}) — อาจ parse expiry ไม่ผ่าน")
        return 2
    _log(f"✅ token valid (เหลือ {h['remaining_sec']}s)")
    if push_to_vps(svc.state_path):
        trigger_catchup()
        return 0
    return 3


if __name__ == "__main__":
    sys.exit(main())
