"""
Sebastian_Winner_Checker.py — ดึงชื่อบริษัทผู้ชนะประมูล (post 2026-05-15 redesign)

อ่าน all_jobs (e-bidding + project_status='ประมูลแล้ว' + ไม่อยู่ใน winner_cache)
→ เรียก eGP API → merge ลง data/winner_cache_bootstrap.json
→ auto-trigger Sebastian_Classifier rebuild

วิธีใช้:
    1. Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\\Temp\\ChromeDebug"
    2. python Sebastian_Winner_Checker.py
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
WINNER_CACHE   = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_date(date_str: str) -> str:
    if date_str and "T" in str(date_str):
        try:
            from datetime import datetime as dt
            return dt.fromisoformat(str(date_str).replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except Exception:
            pass
    return str(date_str)


def fetch_winner_info(page, project_id: str) -> dict:
    """2-tier: getContractAvailable → fallback getProcureResult"""
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            return await r.json();
        } catch(e) { return {error: e.toString()}; }
    }"""

    base = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement"

    # 1) getContractAvailable
    try:
        body = page.evaluate(js, f"{base}/getContractAvailable?projectId={project_id}")
        if isinstance(body, dict):
            data = body.get("data", {})
            arr = data.get("contractAvailableResponse") or []
            if arr:
                first = arr[0]
                name  = first.get("corporateName") or ""
                price = first.get("contractPrice") or first.get("contractAmount") or ""
                cdate = first.get("contractDate") or first.get("noticeAnnounceDate") or ""
                if name:
                    return {"winner": name, "winning_price": str(price), "announce_date": parse_date(cdate)}
    except Exception as e:
        log(f"  getContractAvailable err: {type(e).__name__}: {e}")

    # 2) fallback: getProcureResult
    try:
        body = page.evaluate(js, f"{base}/getProcureResult?projectId={project_id}")
        if isinstance(body, dict):
            data = body.get("data", {})
            arr = data.get("procureResultDataResponse") or []
            for item in arr:
                flag = (item.get("processFlag") or "").upper()
                if flag in ("P", "W", "A"):
                    name  = item.get("receiveNameTh") or ""
                    price = item.get("priceAgree") or item.get("priceProposal") or ""
                    adate = item.get("noticeAnnounceDate") or item.get("auctionDate") or ""
                    if name:
                        return {"winner": name, "winning_price": str(price), "announce_date": parse_date(adate)}
    except Exception as e:
        log(f"  getProcureResult err: {type(e).__name__}: {e}")

    return {}


def connect_browser(p):
    for attempt in range(3):
        try:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUG_PORT}", timeout=5000
            )
            return browser
        except Exception as e:
            log(f"  รอ Chrome... ({attempt+1}/3): {type(e).__name__}")
            time.sleep(2)
    raise RuntimeError("เชื่อมต่อ Chrome ไม่ได้")


def ensure_on_process5(page):
    if "process5.gprocurement.go.th" not in page.url:
        log("  navigate ไป process5...")
        page.goto(f"{PROCESS5_BASE}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(5)


def calc_pct_discount(budget_str, price_str: str) -> str:
    try:
        budget = float(str(budget_str).replace(",", "").strip())
        price  = float(str(price_str).replace(",", "").strip())
        if budget > 0:
            return f"{((budget - price) / budget) * 100:.2f}"
    except (ValueError, TypeError):
        pass
    return ""


def load_winner_cache() -> dict:
    if WINNER_CACHE.exists():
        return json.loads(WINNER_CACHE.read_text(encoding="utf-8"))
    return {}


def save_winner_cache(cache: dict):
    WINNER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    WINNER_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    log("=" * 60)
    log("Sebastian Winner Checker — all_jobs source")
    log("=" * 60)

    cache = load_winner_cache()
    log(f"  winner cache: {len(cache)} entries")

    log("\nReading all_jobs...")
    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    rows = ws.get_all_records()
    log(f"  {len(rows)} jobs")

    # งานที่ต้องตรวจ: e-bidding + ประมูลแล้ว + ยังไม่มี winner cache
    pending = [
        r for r in rows
        if str(r.get("procurement_type", "")).strip() == "e-bidding"
        and str(r.get("project_status", "")).strip() == "ประมูลแล้ว"
        and str(r.get("job_id", "")).strip() not in cache
    ]
    log(f"  pending winner check: {len(pending)} jobs")

    if not pending:
        log("ไม่มีงานใหม่ — เสร็จสิ้น")
        return

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        ensure_on_process5(page)

        new_count = 0
        for i, row in enumerate(pending, 1):
            jid    = str(row.get("job_id", ""))
            title  = str(row.get("title", ""))[:60]
            budget = row.get("budget", "")
            log(f"\n[{i}/{len(pending)}] {jid}: {title}")

            info = fetch_winner_info(page, jid)
            if info and info.get("winner"):
                price = info.get("winning_price", "")
                pct = calc_pct_discount(budget, price)
                cache[jid] = {
                    "winner_name":  info["winner"],
                    "winner_price": str(price),
                    "discount_pct": pct,
                    "award_date":   info.get("announce_date", ""),
                }
                new_count += 1
                log(f"  ✅ {info['winner']} | {price} | -{pct}%")
            else:
                log(f"  ❌ ไม่พบข้อมูลผู้ชนะ")

            time.sleep(1)

        page.close()

    if new_count:
        save_winner_cache(cache)
        log(f"\nเพิ่ม {new_count} winners → cache (รวม {len(cache)})")

        log("\nเรียก Classifier rebuild awarded_jobs...")
        try:
            from Sebastian_Classifier import main as classifier_main
            classifier_main()
        except Exception as e:
            log(f"  ⚠️ Classifier error: {e} — รันมือได้: python scripts/Sebastian_Classifier.py")
    else:
        log("\nไม่มี winner ใหม่ — ข้าม Classifier rebuild")

    log("\nเสร็จสิ้น")


if __name__ == "__main__":
    main()
