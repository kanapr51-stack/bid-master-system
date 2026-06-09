"""_probe_capture_prelim_summary.py — RE: ดัก network ของหน้า "สรุปข้อมูลการเสนอราคาเบื้องต้น"
(egp-agpc01-web) — v2: โหลดหน้า + กดปุ่ม "ดูข้อมูล" ของ row สรุปราคา → จับ endpoint ที่ fetch PDF/data.

connect Chrome debug 9222 (เครื่องกัญจน์, session จริง). READ-ONLY (เปิด+กดดูเท่านั้น ไม่ submit).
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import process5_http_client as p
from playwright.sync_api import sync_playwright

PID = sys.argv[1] if len(sys.argv) > 1 else "69059075454"
URL = ("https://process5.gprocurement.go.th/egp-agpc01-web/announcement/procurement/"
       + p._encrypt_data({"projectId": PID}))
KW = ("price", "Price", "winner", "receiveName", "priceProposal", "priceAgree", "740",
      "resultFlag", "template", "buildName", "bidder", "procureResult", "AndReceive", "view-pdf")

captured = []


def log_resp(resp, tag=""):
    u = resp.url
    if "process5.gprocurement.go.th" not in u:
        return
    if any(x in u for x in (".js", ".css", ".woff", ".png", ".svg", ".ico")):
        return
    if "-web/" in u and "-service" not in u:
        return
    entry = {"tag": tag, "url": u, "status": resp.status, "method": resp.request.method, "body": ""}
    try:
        ct = resp.headers.get("content-type", "")
        if "json" in ct or "text" in ct:
            entry["body"] = resp.text()[:1500]
    except Exception:
        pass
    captured.append(entry)


def main():
    print(f"URL: {URL}\n")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        ctx.on("response", lambda r: log_resp(r, "ctx"))     # จับทุก page รวม popup
        page = ctx.new_page()
        try:
            page.goto(URL, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"goto note: {type(e).__name__}: {e}")
        time.sleep(3)

        # หาปุ่ม "ดูข้อมูล" ทั้งหมด + ข้อความ row เพื่อระบุ row สรุปราคา
        try:
            btns = page.get_by_text("ดูข้อมูล")
            n = btns.count()
            print(f"พบปุ่ม 'ดูข้อมูล' {n} ปุ่ม")
        except Exception as e:
            print("find ดูข้อมูล err:", e); n = 0

        # คลิกทีละปุ่ม (แต่ละปุ่ม = แต่ละ announcement) — จับ network หลังคลิก
        before = len(captured)
        for i in range(n):
            try:
                captured.append({"tag": f"--- click ดูข้อมูล #{i} ---", "url": "", "status": "", "method": "", "body": ""})
                with ctx.expect_page(timeout=6000) as pop_info:
                    page.get_by_text("ดูข้อมูล").nth(i).click(timeout=5000)
                pop = pop_info.value
                time.sleep(3)
                print(f"  คลิก #{i} → เปิด {pop.url[:80]}")
                try:
                    pop.close()
                except Exception:
                    pass
            except Exception as e:
                # ไม่เปิด tab ใหม่ → อาจ fetch inline; รอ network
                time.sleep(2)
                print(f"  คลิก #{i}: {type(e).__name__} (อาจ fetch inline)")
        time.sleep(2)
        page.close()

    print(f"\n=== captured {len(captured)} entries ===\n")
    for e in captured:
        if e["url"] == "":
            print(e["tag"]); continue
        hit = [k for k in KW if k in (e["body"] or "") or k in e["url"]]
        flag = "  ⭐HIT" if hit else ""
        print(f"[{e['status']}] {e['method']} {e['url'][:110]}{flag}")
        if hit:
            print(f"    kw={hit}\n    body={e['body'][:700]}\n")
    out = Path(__file__).parent.parent / "data" / "probe" / f"prelim_capture_{PID}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
