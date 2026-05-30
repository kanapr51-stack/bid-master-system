"""
probe_capture_session_flow.py — B-2: จับ request sequence เต็ม (cross-tab) ตอน
process5 detail → คลิกดูประกาศ → process3 render

เป้าหมาย: หา minimal state transition ที่ทำให้ process3 ShowHTMLFile non-empty
(ตัวที่ตั้ง session/pid context) → ถ้า replicate ด้วย requests.Session ได้ = SessionDeadlineProvider

ใช้ CDP browser-level + Target.setAutoAttach(flatten) → จับทุก tab รวม process3 ที่เปิดใหม่
log: ทุก request (method, full URL, มี postData ไหม) + Set-Cookie + redirect
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import requests, websocket

DEBUG = "http://127.0.0.1:9222"
DURATION = 150
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "session_flow_capture.ndjson")
# โฟกัสเฉพาะ host ที่เกี่ยว (กรอง noise: analytics/cdn)
KEEP = ("process3.gprocurement", "process5.gprocurement", "egp2procmain")


def main():
    ver = requests.get(f"{DEBUG}/json/version", timeout=5).json()
    bws = ver["webSocketDebuggerUrl"]
    print(f"browser ws ok. ⏳ คลิก process5 detail → ดูประกาศ → process3 ภายใน {DURATION}s")
    print(f"   (จับ cross-tab — log → {os.path.abspath(OUT)})\n")
    ws = websocket.create_connection(bws, timeout=DURATION, suppress_origin=True,
                                     max_size=None)
    mid = [0]
    def send(method, params=None, sid=None):
        mid[0] += 1
        m = {"id": mid[0], "method": method, "params": params or {}}
        if sid:
            m["sessionId"] = sid
        ws.send(json.dumps(m))
        return mid[0]

    # auto-attach ทุก target (flatten → multiplex sessionId บน ws เดียว)
    send("Target.setAutoAttach",
         {"autoAttach": True, "flatten": True, "waitForDebuggerOnStart": False})
    send("Target.setDiscoverTargets", {"discover": True})

    events = []
    seq = 0
    deadline = time.time() + DURATION
    ws.settimeout(4)
    fout = open(OUT, "w", encoding="utf-8")
    while time.time() < deadline:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        method = msg.get("method")
        sid = msg.get("sessionId")
        # attach → enable Network บน session นั้น
        if method == "Target.attachedToTarget":
            s2 = msg["params"]["sessionId"]
            ti = msg["params"]["targetInfo"]
            send("Network.enable", {}, sid=s2)
            rec = {"ev": "attach", "url": ti.get("url", "")[:120], "type": ti.get("type")}
            print(f"  + attach {ti.get('type')} {ti.get('url','')[:70]}")
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
        elif method == "Network.requestWillBeSent":
            p = msg["params"]; req = p["request"]; url = req["url"]
            if not any(k in url for k in KEEP):
                continue
            seq += 1
            rec = {
                "ev": "req", "seq": seq, "sid": sid, "t": p.get("timestamp"),
                "method": req.get("method"), "url": url,
                "hasPost": bool(req.get("hasPostData") or req.get("postData")),
                "postData": (req.get("postData") or "")[:500],
                "redirectFrom": (p.get("redirectResponse") or {}).get("url"),
                "docURL": p.get("documentURL", "")[:120],
            }
            tag = "POST" if rec["method"] == "POST" else "GET "
            host = "P3" if "process3" in url or "egp2proc" in url else "P5"
            print(f"  [{seq:02d}] {host} {tag} {url[:110]}")
            if rec["postData"]:
                print(f"        post: {rec['postData'][:90]}")
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
        elif method == "Network.responseReceivedExtraInfo":
            hdrs = msg["params"].get("headers", {})
            sc = {k: v for k, v in hdrs.items() if k.lower() == "set-cookie"}
            if sc:
                rec = {"ev": "setcookie", "val": str(sc)[:200]}
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
    fout.close()
    ws.close()
    print(f"\n✅ จบ — บันทึก {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
