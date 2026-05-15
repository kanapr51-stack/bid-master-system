"""
probe_raw_fields.py — dump raw API fields จาก search + greenBook + getAnnouncementInfo
เพื่อหาว่า field deadline/วันยื่นซอง อยู่ที่ไหน
"""
import sys, json, time, re
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

DEBUG_PORT     = 9222
SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
PROCESS5_BASE  = "https://process5.gprocurement.go.th"
API_BASE       = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement"
SEARCH_URL     = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
OUTPUT_DIR     = Path(__file__).parent.parent / "data" / "probe"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_js(page, url):
    js = f"""async () => {{
        try {{
            const r = await fetch({json.dumps(url)}, {{credentials:'include'}});
            const t = await r.text();
            try {{ return {{status:r.status, body:JSON.parse(t)}}; }}
            catch(e) {{ return {{status:r.status, text:t.slice(0,500)}}; }}
        }} catch(e) {{ return {{error:e.toString()}}; }}
    }}"""
    return page.evaluate(js)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ดึง job_ids จาก active_bidding
    ws = open_sheet(SPREADSHEET_ID, "active_bidding")
    rows = ws.get_all_records()
    pids = [str(r.get("job_id","")).strip() for r in rows if r.get("job_id")][:5]
    log(f"job_ids: {pids}")

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}", timeout=5000)
        context = browser.contexts[0]
        page = context.new_page()

        # โหลดหน้าหลัก + รอ Turnstile
        log("โหลด search page...")
        page.goto(SEARCH_URL, wait_until="load", timeout=45000)
        time.sleep(8)
        deadline_t = time.time() + 25
        while time.time() < deadline_t:
            try:
                btn = page.query_selector("button:has-text('ค้นหา')")
                if btn and btn.is_enabled():
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(2)
        log("session พร้อม")

        # 1) ดัก raw search API response — search "นครพนม" แล้วบันทึก ALL fields ของ item แรก
        log("\n--- 1. Capture raw search API item fields ---")
        raw_items = []
        captured_url = []

        def on_req(req):
            url = req.url
            if "egp-atpj27-service" in url and "announcement" in url and "sumProject" not in url:
                captured_url.append(url)

        page.on("request", on_req)
        try:
            search_input = page.locator("input[placeholder*='ค้น'], input[type='search'], input[formcontrolname]").first
            search_input.fill("นครพนม")
            with page.expect_response(
                lambda r: "egp-atpj27-service" in r.url and "announcement" in r.url and "sumProject" not in r.url,
                timeout=20000
            ) as resp_info:
                page.locator("button:has-text('ค้นหา')").first.click()
            body = resp_info.value.json()
            items = body.get("data", {}).get("data", [])
            if items:
                raw_items = items[:3]
                log(f"  ได้ {len(items)} items, ดู ALL fields ของ item[0]:")
                for k, v in items[0].items():
                    log(f"    {k!r:35} = {str(v)[:80]}")
                results["search_item_fields"] = {k: str(v) for k, v in items[0].items()}
        except Exception as e:
            log(f"  search error: {e}")
        page.remove_listener("request", on_req)

        # 2) greenBook D0 → ดู B0 seqNo แล้ว getAnnouncementInfo
        log("\n--- 2. greenBook D0 → getAnnouncementInfo ---")
        for pid in pids[:2]:
            # ดึง greenBook D0 ก่อน
            gb_url = f"{API_BASE}/greenBook?mode=LINK&methodId=16&tempProjectId={pid}&pageAnnounceType=D0"
            gb_res = fetch_js(page, gb_url)
            gb_body = gb_res.get("body", {})
            gb_data = gb_body.get("data", {}) if isinstance(gb_body, dict) else {}
            gb_items = gb_data.get("greenBookAnnouncementTypeLinkDto", []) if isinstance(gb_data, dict) else []
            log(f"  job {pid}: greenBook D0 items={len(gb_items)}")

            # ลอง getAnnouncementInfo ด้วยทุก seqNo/announceType ที่เจอ
            tried = set()
            for item in gb_items:
                ann_type = item.get("announceType","")
                seq_no   = item.get("seqNo", "")
                template = item.get("templateType","")
                key = (ann_type, seq_no, template)
                if key in tried:
                    continue
                tried.add(key)

                for ep in ["/getAnnouncementInfo", "/getInviteDetail"]:
                    for param_set in [
                        f"projectId={pid}&methodId=16&announceType={ann_type}&seqNo={seq_no}",
                        f"tempProjectId={pid}&methodId=16&announceType={ann_type}&seqNo={seq_no}",
                        f"projectId={pid}&methodId=16&pageAnnounceType=D0&announceType={ann_type}&seqNo={seq_no}",
                        f"projectId={pid}&methodId=16&templateType={template}&seqNo={seq_no}",
                    ]:
                        url = f"{API_BASE}{ep}?{param_set}"
                        res = fetch_js(page, url)
                        body = res.get("body", {})
                        if not isinstance(body, dict):
                            continue
                        rc   = (body.get("response") or {}).get("responseCode","?")
                        data = body.get("data")
                        if data:
                            log(f"  ✅ {ep}?{param_set[:60]}")
                            log(f"     rc={rc}, type={type(data).__name__}")
                            if isinstance(data, dict):
                                for k, v in data.items():
                                    log(f"     {k!r:40} = {str(v)[:80]}")
                            results[f"{pid}_{ep}_{ann_type}_{seq_no}"] = data
                        elif rc == "0":
                            log(f"  rc=0 nodata: {ep[-30:]}?{param_set[:50]}")

        # 3) ลอง aann09 service endpoints
        log("\n--- 3. aann09 service ---")
        aann_base = f"{PROCESS5_BASE}/egp-aann09-service/pb/a-aann/announcement"
        for pid in pids[:2]:
            for ep in ["/getInviteDetail", "/getAnnouncementInfo", "/getAnnounceDetail",
                       "/getAnnounceInvitation", "/getProjectAnnounceData"]:
                for params in [
                    f"projectId={pid}&methodId=16",
                    f"tempProjectId={pid}&methodId=16",
                    f"projectId={pid}",
                ]:
                    url = f"{aann_base}{ep}?{params}"
                    res = fetch_js(page, url)
                    body = res.get("body", {})
                    st = res.get("status","?")
                    if isinstance(body, dict) and body.get("data"):
                        rc = (body.get("response") or {}).get("responseCode","?")
                        data = body.get("data")
                        log(f"  ✅ aann09{ep}?{params[:50]}: rc={rc}")
                        if isinstance(data, dict):
                            for k, v in list(data.items())[:20]:
                                log(f"     {k!r:40} = {str(v)[:80]}")
                        results[f"aann09_{pid}_{ep}"] = data
                        break

        page.close()

    out_path = OUTPUT_DIR / f"raw_fields_{datetime.now().strftime('%H%M%S')}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"\nบันทึก: {out_path}")
    log(f"พบ {len(results)} endpoints ที่มีข้อมูล")


if __name__ == "__main__":
    main()
