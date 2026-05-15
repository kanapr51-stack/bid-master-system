"""
probe_bid_detail.py v3 — ลอง greenBook API ด้วย pageAnnounceType ต่างๆ
เป้าหมาย: หาข้อมูลวันยื่นซอง (deadline) ของ e-bidding กำลังประมูล
"""

import sys
import json
import time
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

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "probe"

# pageAnnounceType ต่างๆ ที่อาจมีรายละเอียดวันยื่นซอง
PAGE_TYPES = [
    "D0",   # ประกาศเชิญชวน
    "D1",   # ยกเลิกประกาศ
    "P0",   # ?
    "BOQ",  # ราคากลาง
    "IM",   # ?
    "B0",   # ?
    "S0",   # ?
    "R0",   # ?
    "T0",   # ?
    "C0",   # ?
    "W0",   # ผู้ชนะ
]

# additional endpoint candidates from Angular bundle aann09 / acrt23 / asln17 / etc.
SERVICE_BASES = [
    "/egp-atpj27-service/pb/a-egp-allt-project/announcement",
    "/egp-aann09-service/pb/a-aann/announcement",
    "/egp-aann09-service/pb/announcement",
    "/egp-aslc18-service/pb/a-slc/announcement",
]

DETAIL_ENDPOINTS = [
    "/getInviteDetail",      # ใบเชิญชวน
    "/getAnnouncementInfo",
    "/getProjectInfoDetail",
    "/getProcureProjectInfo",
    "/getAnnouncePrice",
    "/getProcureProjectPrice",
    "/getCalendar",
    "/getEventCalendar",
    "/getProcurePlanDetail",
]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch(page, url: str, extra_headers: dict = None) -> dict:
    headers = extra_headers or {}
    js = f"""async () => {{
        try {{
            const r = await fetch({json.dumps(url)}, {{
                credentials: 'include',
                headers: {json.dumps(headers)}
            }});
            const status = r.status;
            const text = await r.text();
            try {{ return {{status, body: JSON.parse(text)}}; }}
            catch(e) {{ return {{status, body_text: text.slice(0, 200)}}; }}
        }} catch(e) {{ return {{error: e.toString()}}; }}
    }}"""
    return page.evaluate(js)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ws = open_sheet(SPREADSHEET_ID, "active_bidding")
    rows = ws.get_all_records()
    pid = None
    for r in rows:
        p = str(r.get("job_id", "")).strip()
        if p:
            pid = p
            break
    if not pid:
        log("ไม่พบงานใน active_bidding")
        return

    log(f"ทดสอบกับ project_id: {pid}")

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

        log("โหลด process5 (session/Turnstile)...")
        page.goto(SEARCH_URL, wait_until="load", timeout=45000)
        time.sleep(6)
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                btn = page.query_selector("button:has-text('ค้นหา')")
                if btn and btn.is_enabled():
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(2)

        results = {}

        # 1) ทดลอง greenBook ทุก pageAnnounceType
        log(f"\n--- greenBook with various pageAnnounceType ---")
        for ptype in PAGE_TYPES:
            for mid in ("16", "19"):
                url = f"{API_BASE}/greenBook?mode=LINK&methodId={mid}&tempProjectId={pid}&pageAnnounceType={ptype}"
                res = fetch(page, url)
                status = res.get("status", "?")
                if status != 200:
                    continue
                body = res.get("body", {})
                rc = (body.get("response") or {}).get("responseCode", "?")
                d = body.get("data")
                if not d:
                    continue
                items = d.get("greenBookAnnouncementTypeLinkDto") if isinstance(d, dict) else None
                if items:
                    log(f"  greenBook ptype={ptype} mid={mid}: {len(items)} items")
                    results[f"greenBook_{ptype}_m{mid}"] = items[:5]

        # 2) ทดลอง endpoint อื่นๆ
        log(f"\n--- Custom endpoints ---")
        for base in SERVICE_BASES:
            for ep in DETAIL_ENDPOINTS:
                full_url = f"{PROCESS5_BASE}{base}{ep}?projectId={pid}"
                res = fetch(page, full_url)
                status = res.get("status", "?")
                if status not in (200, 401, 403):
                    continue
                body = res.get("body", {})
                if not isinstance(body, dict):
                    continue
                rc = (body.get("response") or {}).get("responseCode", "?")
                d = body.get("data")
                short = f"{base}{ep}".replace("/pb/a-egp-allt-project", "..")
                if d and rc == "0":
                    log(f"  ✅ {short}: keys={list(d.keys()) if isinstance(d, dict) else type(d).__name__}")
                    results[short] = d
                elif status == 200:
                    log(f"  {short}: 200 rc={rc}")

        # 3) ลอง pageAnnounceType อื่นๆ มี keyword ผ่าน wildcard
        log(f"\n--- greenBook ALL/null/empty ---")
        for ptype in ("", "ALL", "null"):
            url = f"{API_BASE}/greenBook?mode=LINK&methodId=16&tempProjectId={pid}&pageAnnounceType={ptype}"
            res = fetch(page, url)
            status = res.get("status", "?")
            if status == 200:
                body = res.get("body", {})
                d = body.get("data")
                if d:
                    items = d.get("greenBookAnnouncementTypeLinkDto") if isinstance(d, dict) else None
                    log(f"  ptype='{ptype}': data exists, items={len(items) if items else 0}, keys={list(d.keys()) if isinstance(d, dict) else '?'}")
                    if items:
                        results[f"greenBook_all_{ptype}"] = items

        # 4) ลอง getProjectInformation, getProject ต่างๆ
        log(f"\n--- getProject* endpoints ---")
        more_endpoints = [
            "/getProjectAll",
            "/getInformation",
            "/getEventList",
            "/getEventInfo",
            "/getProjectEvent",
            "/getAnnouncementSchedule",
            "/getProcureSchedule",
            "/getProcureDate",
            "/getProcureEvent",
            "/getProcureProposal",
            "/getProposalEnd",
            "/getProposalInfo",
            "/getDocSale",
            "/getDocSaleInfo",
            "/getSaleDocument",
            "/getReceiveDoc",
            "/getReceiveProposal",
            "/getProcureProcess",
            "/getProcessDate",
            "/getProjectAnnounceData",
            "/getProjectStatus",
            "/getAnnounceInvitation",
        ]
        for ep in more_endpoints:
            full_url = f"{API_BASE}{ep}?projectId={pid}"
            res = fetch(page, full_url)
            status = res.get("status", "?")
            if status == 200:
                body = res.get("body", {})
                rc = (body.get("response") or {}).get("responseCode", "?") if isinstance(body, dict) else "?"
                d = body.get("data") if isinstance(body, dict) else None
                if d:
                    log(f"  ✅ {ep}: rc={rc}, type={type(d).__name__}")
                    if isinstance(d, dict):
                        log(f"      keys={list(d.keys())[:20]}")
                    results[ep] = d
                else:
                    log(f"  {ep}: 200 (no data, rc={rc})")
            elif status != 404:
                log(f"  {ep}: {status}")

        # save
        out_path = OUTPUT_DIR / f"v3_probe_{pid}_{datetime.now().strftime('%H%M%S')}.json"
        out_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log(f"\nบันทึก: {out_path}")
        log(f"พบ endpoint ที่ตอบ 200 with data: {len(results)} รายการ")

        page.close()


if __name__ == "__main__":
    main()
