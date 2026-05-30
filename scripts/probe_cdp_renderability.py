"""
probe_cdp_renderability.py — Experiment 1+2: BrowserDeadlineProvider feasibility

ถาม: CDP render process3 announcement → extract deadline อัตโนมัติได้ไหม (Exp1 renderability)
      + invitation projects มี deadline เสมอไหม (Exp2 presence rate)

วิธี: เปิด Chrome debug 9222 (ที่ harvest token อยู่) → CDP navigate process3?pid=X →
      รอ render → ดึง document.body.innerText → หา deadline keyword
ผลลัพธ์ Exp1 = renderable? (ไม่ใช่ค่า deadline)  Exp2 = deadline_presence_rate
"""
import sys, os, json, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import requests, websocket
from token_service import TokenService, make_provider
import Sebastian_Province_Discovery as d

DEBUG = "http://127.0.0.1:9222"
P3 = ("https://process3.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch"
      "?pid={pid}&servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure")
DEADLINE_KW = ["ยื่นข้อเสนอ", "ยื่นซอง", "วันที่เสนอราคา", "กำหนดยื่น",
               "ปิดรับ", "เสนอราคา", "ขอรับเอกสาร", "ขายเอกสาร"]
RENDER_WAIT = 5.0   # รอ postback/JS หลัง load


def cdp_render(url: str, timeout: int = 30) -> str:
    """navigate tab ใหม่ → คืน document.body.innerText"""
    r = requests.put(f"{DEBUG}/json/new?{url}", timeout=10)
    tab = r.json(); tid = tab["id"]
    text = ""
    try:
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"],
                                         timeout=timeout, suppress_origin=True)
        mid = {"n": 0}
        def send(m, p=None):
            mid["n"] += 1
            ws.send(json.dumps({"id": mid["n"], "method": m, "params": p or {}}))
            return mid["n"]
        send("Page.enable")
        send("Page.navigate", {"url": url})
        # รอ load event
        deadline = time.time() + timeout
        loaded = False
        ws.settimeout(3)
        while time.time() < deadline and not loaded:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                continue
            if msg.get("method") == "Page.loadEventFired":
                loaded = True
        time.sleep(RENDER_WAIT)
        # ดึง innerText
        eid = send("Runtime.evaluate",
                   {"expression": "document.body ? document.body.innerText : ''",
                    "returnByValue": True})
        end = time.time() + 10
        ws.settimeout(3)
        while time.time() < end:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                continue
            if msg.get("id") == eid:
                text = (((msg.get("result") or {}).get("result") or {}).get("value")) or ""
                break
        ws.close()
    finally:
        try: requests.get(f"{DEBUG}/json/close/{tid}", timeout=5)
        except Exception: pass
    return text


def main():
    svc = TokenService(make_provider("chrome9222"), allow_refresh=False)
    tok = svc.get_valid_token()
    if not tok:
        print("❌ no token"); return 1
    items = d.fetch_page(tok, "480000", "2569", 1)
    # เลือก invitation stage (stepId M*/S*/Z* = ประกาศเชิญชวน/ยื่นซอง)
    invites = [it for it in items if str(it.get("stepId") or "")[:1] in ("M", "S", "Z")][:8]
    print(f"ทดสอบ {len(invites)} invitation projects (D0, stepId active)\n")
    found = 0
    for it in invites:
        pid = str(it["projectId"]); step = it.get("stepId")
        t0 = time.time()
        txt = cdp_render(P3.format(pid=pid))
        ms = int((time.time() - t0) * 1000)
        hits = [kw for kw in DEADLINE_KW if kw in txt]
        ok = len(txt) > 200
        dl = "✓" if hits else "✗"
        print(f"  pid={pid} step={step} | render={'✓' if ok else '✗'}({len(txt):>5}ch {ms}ms) | deadline {dl} {hits[:3]}")
        if hits: found += 1
        # ตัวอย่าง snippet รอบ keyword แรก (งานแรกที่เจอ)
        if hits and found == 1:
            i = txt.find(hits[0])
            snip = re.sub(r"\s+", " ", txt[max(0, i-30):i+90]).strip()
            print(f"     snippet: ...{snip}...")
    n = len(invites)
    print(f"\n📊 Exp1 renderability: {sum(1 for it in invites)} ทดสอบ")
    print(f"📊 Exp2 deadline_presence_rate: {found}/{n} = {found/n*100:.0f}%" if n else "no data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
