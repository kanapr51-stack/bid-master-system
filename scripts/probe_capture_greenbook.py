"""
probe_capture_greenbook.py — capture greenBook call จริง (full URL + response body)
ตอน browser ดู INVITATION announcement → หา document linkage (templateId/pdfUrl)

ผ่าน UI ปกติ = ไม่ trip WAF (ต่างจาก brute sweep)
วิธีใช้: รัน → คุณกัญจน์คลิกประกวดราคา 1 งาน → ดูเอกสารประกาศ → จับ greenBook req+resp
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import requests, websocket

DEBUG = "http://127.0.0.1:9222"
WATCH = ("greenbook", "getprocurementdetail", "template", "view-pdf", "dwnt")
DURATION = 150


def main():
    tabs = requests.get(f"{DEBUG}/json", timeout=5).json()
    pages = [t for t in tabs if t.get("type") == "page" and "process5" in t.get("url", "")]
    if not pages:
        print("❌ ไม่เจอ process5 tab"); return 1
    tab = pages[0]
    print(f"👀 ฟัง: {tab.get('title','')[:30]}")
    print(f"⏳ คลิกประกวดราคา 1 งาน → ดูเอกสารประกาศ ภายใน {DURATION}s\n")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=DURATION, suppress_origin=True)
    n = [0]
    def send(m, p=None):
        n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p or {}})); return n[0]
    send("Network.enable")
    req = {}          # requestId → url
    body_reqs = {}    # msg id → url (รอ response body)
    deadline = time.time() + DURATION
    ws.settimeout(4)
    while time.time() < deadline:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        meth = msg.get("method")
        if meth == "Network.requestWillBeSent":
            url = msg["params"]["request"]["url"]
            if any(k in url.lower() for k in WATCH):
                rid = msg["params"]["requestId"]; req[rid] = url
                print(f"  🔗 REQ {url}")
        elif meth == "Network.loadingFinished":
            rid = msg["params"]["requestId"]
            if rid in req:
                mid = send("Network.getResponseBody", {"requestId": rid})
                body_reqs[mid] = req[rid]
        elif "result" in msg and msg.get("id") in body_reqs:
            url = body_reqs.pop(msg["id"])
            b = msg["result"].get("body", "")
            tag = "greenBook" if "greenbook" in url.lower() else url.split("/")[-1][:25]
            print(f"  📦 RESP [{tag}] {b[:400]}")
    ws.close()
    print("\n✅ จบ capture")
    return 0


if __name__ == "__main__":
    sys.exit(main())
