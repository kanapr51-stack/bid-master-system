"""
probe_deadline_api.py — เปิดหน้า announcement detail จริงๆ แล้วดัก API calls
เพื่อหาว่า endpoint ไหนส่ง deadline (วันยื่นซอง) กลับมา
"""
import sys, json, time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

DEBUG_PORT     = 9222
SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
PROCESS5_BASE  = "https://process5.gprocurement.go.th"
SEARCH_URL     = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
OUTPUT_DIR     = Path(__file__).parent.parent / "data" / "probe"

DATE_KEYWORDS = [
    "date", "Date", "deadline", "Deadline", "end", "End",
    "close", "Close", "submit", "Submit", "receive", "Receive",
    "proposal", "Proposal", "due", "Due", "expire", "Expire",
    "วัน", "ยื่น", "ปิด", "สิ้นสุด",
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def has_date_key(obj, path=""):
    """ค้นหา key ที่น่าจะเป็น date ใน nested dict/list"""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{path}.{k}" if path else k
            if any(kw in k for kw in DATE_KEYWORDS):
                results.append((full_key, v))
            results.extend(has_date_key(v, full_key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:3]):
            results.extend(has_date_key(item, f"{path}[{i}]"))
    return results


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ดึง job_id จาก active_bidding
    ws = open_sheet(SPREADSHEET_ID, "active_bidding")
    rows = ws.get_all_records()
    pids = []
    for r in rows:
        pid = str(r.get("job_id", "")).strip()
        if pid:
            pids.append(pid)
        if len(pids) >= 3:
            break

    if not pids:
        log("ไม่พบ job ใน active_bidding")
        return

    log(f"ทดสอบกับ {len(pids)} jobs: {pids}")

    captured = {}   # url → body ของทุก API call ที่ดักได้

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUG_PORT}", timeout=5000
            )
        except Exception as e:
            log(f"เชื่อม Chrome ไม่ได้: {e}")
            return

        context = browser.contexts[0]
        page = context.new_page()

        # ดัก response ทุกตัวที่มาจาก process5
        def on_response(resp):
            url = resp.url
            if "process5.gprocurement" not in url:
                return
            # ข้าม assets, fonts, images
            if any(x in url for x in [".js", ".css", ".png", ".ico", "cfturnstile", "app-ver", "app-hidden"]):
                return
            try:
                body = resp.json()
                if not isinstance(body, dict):
                    return
                data = body.get("data")
                rc   = (body.get("response") or {}).get("responseCode", "?")
                date_hits = has_date_key(data) if data else []
                if date_hits:
                    log(f"  ✅ DATE FOUND in {url.split('process5.gprocurement.go.th')[1][:80]}")
                    for key, val in date_hits[:5]:
                        log(f"      {key} = {val}")
                    captured[url] = {"rc": rc, "date_keys": date_hits, "data_preview": str(data)[:500]}
                elif data and rc == "0":
                    short = url.split('process5.gprocurement.go.th')[1][:80]
                    log(f"  (data, rc=0) {short}")
            except Exception:
                pass

        page.on("response", on_response)

        # โหลดหน้าหลักก่อน (ให้ session/Turnstile พร้อม)
        log("โหลดหน้า search (รอ Turnstile)...")
        page.goto(SEARCH_URL, wait_until="load", timeout=45000)
        time.sleep(8)

        # รอปุ่มค้นหา
        deadline_t = time.time() + 25
        while time.time() < deadline_t:
            try:
                btn = page.query_selector("button:has-text('ค้นหา')")
                if btn and btn.is_enabled():
                    break
            except Exception:
                pass
            time.sleep(1)

        # ทดสอบแต่ละ job — navigate ไปหน้า detail โดยตรง
        for pid in pids:
            log(f"\n=== probe job {pid} ===")
            detail_url = f"{SEARCH_URL}?tempProjectId={pid}&methodId=16&pageAnnounceType=D0"
            try:
                page.goto(detail_url, wait_until="networkidle", timeout=30000)
                time.sleep(4)
            except Exception as e:
                log(f"  goto error: {e}")

            # ลอง fetch API ที่น่าสนใจโดยตรงด้วย
            for ep, params in [
                ("/egp-atpj27-service/pb/a-egp-allt-project/announcement/getInviteDetail",
                 f"projectId={pid}&methodId=16"),
                ("/egp-atpj27-service/pb/a-egp-allt-project/announcement/getInviteDetail",
                 f"tempProjectId={pid}&methodId=16"),
                ("/egp-aann09-service/pb/a-aann/announcement/getInviteDetail",
                 f"projectId={pid}&methodId=16"),
                ("/egp-aann09-service/pb/a-aann/announcement/getAnnounceDetail",
                 f"projectId={pid}&methodId=16"),
                ("/egp-atpj27-service/pb/a-egp-allt-project/announcement/getAnnouncementInfo",
                 f"projectId={pid}&methodId=16&announceType=B0&seqNo=1"),
                ("/egp-atpj27-service/pb/a-egp-allt-project/announcement/getAnnouncementInfo",
                 f"tempProjectId={pid}&methodId=16&pageAnnounceType=D0"),
                ("/egp-atpj27-service/pb/a-egp-allt-project/announcement/getAnnouncementInfo",
                 f"projectId={pid}"),
                ("/egp-aann09-service/pb/a-aann/announcement/getAnnouncementInfo",
                 f"projectId={pid}&methodId=16"),
            ]:
                url = f"{PROCESS5_BASE}{ep}?{params}"
                js = f"""async () => {{
                    try {{
                        const r = await fetch({json.dumps(url)}, {{credentials:'include'}});
                        const t = await r.text();
                        try {{ return {{status:r.status, body:JSON.parse(t)}}; }}
                        catch(e) {{ return {{status:r.status, text:t.slice(0,300)}}; }}
                    }} catch(e) {{ return {{error:e.toString()}}; }}
                }}"""
                res = page.evaluate(js)
                st = res.get("status", "?")
                body = res.get("body", {})
                if isinstance(body, dict) and body.get("data"):
                    rc = (body.get("response") or {}).get("responseCode", "?")
                    date_hits = has_date_key(body["data"])
                    short_ep = ep.split("/pb/")[1] if "/pb/" in ep else ep
                    if date_hits:
                        log(f"  ✅✅ {short_ep}?{params[:40]}")
                        for dkey, dval in date_hits[:8]:
                            log(f"      {dkey} = {dval}")
                        captured[url] = {"rc": rc, "date_keys": [(k, str(v)) for k,v in date_hits], "data": body["data"]}
                    elif rc == "0":
                        log(f"  data rc=0 (no dates): {short_ep}")
                elif st == 200:
                    log(f"  {st} (no data): {ep[-40:]}")

        page.close()

    out_path = OUTPUT_DIR / f"deadline_probe_{datetime.now().strftime('%H%M%S')}.json"
    out_path.write_text(json.dumps(captured, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"\nบันทึก: {out_path}")
    log(f"พบ endpoint ที่มีวันที่: {len(captured)} รายการ")

    # สรุปผล
    if captured:
        log("\n=== สรุป Endpoint ที่มีวันที่ ===")
        for url, info in captured.items():
            log(f"  {url.split('process5.gprocurement.go.th')[1][:100]}")
            for k, v in (info.get("date_keys") or [])[:5]:
                log(f"    {k} = {v}")
    else:
        log("\n❌ ไม่พบ endpoint ที่มีวันที่เลย — ต้อง parse จาก document HTML/PDF")


if __name__ == "__main__":
    main()
