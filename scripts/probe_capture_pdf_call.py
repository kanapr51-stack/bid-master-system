"""
probe_capture_pdf_call.py — capture network call ตอนเปิดดูประกาศ PDF บน Chrome debug 9222
หา endpoint ที่ map projectId → templateId (deadline source)

วิธีใช้: เปิด Chrome debug (port 9222) ที่หน้า announcement → รันสคริปต์นี้ →
คลิกดูประกาศ 1 งาน (กดดู PDF) → สคริปต์จับ URL ที่เกี่ยว template/pdf/detail
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import requests, websocket

DEBUG = "http://127.0.0.1:9222"
KEYWORDS = ("template", "view-pdf", "pdf", "/detail", "announcement/", "dwnt", "getAnnounce", "document", "file")
DURATION = 120


def main():
    # หา target tab (หน้า announcement)
    tabs = requests.get(f"{DEBUG}/json", timeout=5).json()
    pages = [t for t in tabs if t.get("type") == "page" and "gprocurement" in t.get("url", "")]
    if not pages:
        print("❌ ไม่เจอ tab eGP — เปิดหน้า announcement ใน Chrome debug ก่อน"); return 1
    tab = pages[0]
    print(f"👀 ฟัง network ของ: {tab.get('title','')[:40]} ({tab['url'][:60]})")
    print(f"⏳ คลิกดูประกาศ 1 งาน (กดดู PDF) ภายใน {DURATION}s ...\n")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=DURATION, suppress_origin=True)
    mid = {"n": 0}
    def send(m, p=None):
        mid["n"] += 1; ws.send(json.dumps({"id": mid["n"], "method": m, "params": p or {}}))
    send("Network.enable")
    seen = set()
    deadline = time.time() + DURATION
    ws.settimeout(5)
    while time.time() < deadline:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        if msg.get("method") == "Network.requestWillBeSent":
            url = msg["params"]["request"]["url"]
            low = url.lower()
            if any(k in low for k in KEYWORDS) and url not in seen:
                seen.add(url)
                print(f"  🔗 {url[:160]}")
    ws.close()
    print(f"\n✅ จบ — จับได้ {len(seen)} URL ที่เกี่ยวเอกสาร/PDF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
