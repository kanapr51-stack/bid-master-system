"""
refresh_active_jobs.py — รีเฟรชสถานะงาน active_bidding จาก eGP API สด

ปัญหา: ข้อมูลใน all_jobs frozen ตั้งแต่ migration → งานที่ผ่านไปนาน
อาจมี winner หรือเปลี่ยน flow status แล้ว แต่ระบบเรายังคิดว่า "กำลังประมูล"

วิธีแก้: ตรวจสอบสด 2 ทาง per job:
  1. getProcureResult → ถ้ามี winner → update awarded_jobs cache
  2. getProjectDetail (sumProject) → ถ้า flowName เปลี่ยน → update project_status + deadline

วิธีใช้:
    1. Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\\Temp\\ChromeDebug"
    2. python scripts/refresh_active_jobs.py [--jids id1,id2,...] [--all]
       - --jids: รีเฟรชเฉพาะ job_id ที่ระบุ
       - --all: รีเฟรชทุก row ใน active_bidding
       - default: รีเฟรช active_bidding ทั้งหมด
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from Sebastian_Scraper import FLOW_STATUS_MAP, connect_browser

DEBUG_PORT     = 9222
SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
PROCESS5_BASE  = "https://process5.gprocurement.go.th"
WINNER_CACHE   = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_iso_to_thai(date_str: str) -> str:
    if not date_str:
        return ""
    s = str(date_str)
    if "T" in s:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except Exception:
            return s[:10]
    return s


def fetch_winner_info(page, jid: str) -> dict:
    """
    ดึง winner จาก getProcureResult — ผู้ชนะคือ row ที่มี priceAgree != null

    Response shape:
      data.procureResultList[].procureResultDataResponse[]
        .receiveNameTh, .priceAgree (= ราคาตกลง = ผู้ชนะ), .priceProposal, .resultFlag
      data.announceDate = วันประกาศผู้ชนะ
    """
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            return await r.json();
        } catch(e) { return {error: e.toString()}; }
    }"""

    base = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement"

    try:
        body = page.evaluate(js, f"{base}/getProcureResult?projectId={jid}")
        if isinstance(body, dict):
            data = body.get("data", {}) or {}
            announce_date = parse_iso_to_thai(data.get("announceDate", ""))
            for group in data.get("procureResultList", []) or []:
                for item in group.get("procureResultDataResponse", []) or []:
                    if item.get("priceAgree") is not None:  # นี่คือผู้ชนะที่ตกลงราคาแล้ว
                        return {
                            "winner":         item.get("receiveNameTh", ""),
                            "winning_price":  str(item.get("priceAgree", "")),
                            "announce_date":  announce_date,
                        }
    except Exception as e:
        log(f"  getProcureResult err: {e}")

    return {}


def fetch_project_detail(page, jid: str, retry: bool = True) -> dict:
    """
    ดึงสถานะปัจจุบันจาก getProjectDetail
    flowSeqno guide:
      1-3 → 'กำลังเตรียม' (รับฟังคำวิจารณ์ / TOR)
      4   → 'กำลังประมูล' (เปิดให้ยื่นซองจริง)
      5+  → 'ประมูลแล้ว' (รอประกาศ / ประกาศแล้ว)

    Note: ถ้า API rate-limited จะคืน data partial (flowSeqno=0, stepId='')
    → ตรวจ valid_data ก่อน return — caller ต้องเช็ค .get("valid")
    """
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            return await r.json();
        } catch(e) { return {error: e.toString()}; }
    }"""

    url = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement/getProjectDetail?projectId={jid}"
    try:
        body = page.evaluate(js, url)
        if isinstance(body, dict):
            data = body.get("data", {}) or {}
            seqno  = data.get("flowSeqno", 0) or 0
            stepId = data.get("stepId", "")
            flowId = data.get("flowId", "")

            # Valid data = flowSeqno > 0 หรือ stepId มีค่า
            valid = bool(seqno > 0 or stepId or flowId)
            if not valid and retry:
                # Rate limit — รอ + retry 1 ครั้ง
                time.sleep(3)
                return fetch_project_detail(page, jid, retry=False)

            if seqno <= 3:
                status = "กำลังเตรียม"
            elif seqno == 4:
                status = "กำลังประมูล"
            else:
                status = "ประมูลแล้ว"
            return {
                "project_status":       status,
                "flow_seqno":           seqno,
                "step_id":              stepId,
                "flow_id":              flowId,
                "project_status_raw":   data.get("projectStatus", ""),  # A or R
                "announce_type":        data.get("announceType", ""),   # B0/D0/W0/D1/W1/BOQ/...
                "valid":                valid,
            }
    except Exception as e:
        log(f"  getProjectDetail err: {e}")
    return {"valid": False}


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--jids", help="comma-separated job_ids")
    ap.add_argument("--all",  action="store_true", help="refresh ทุก row ใน active_bidding")
    ap.add_argument("--expand", action="store_true", help="refresh active + tor_review + pending_award (default for cron)")
    args = ap.parse_args()

    log("=" * 60)
    log("Refresh Active Jobs — query eGP API สด")
    log("=" * 60)

    # ── เลือก jobs ที่จะรีเฟรช ──
    if args.jids:
        target_jids = [j.strip() for j in args.jids.split(",") if j.strip()]
        log(f"  targeted refresh: {len(target_jids)} jobs")
    elif args.expand:
        target_jids = []
        for sn in ("active_bidding", "tor_review", "pending_award"):
            try:
                ws = open_sheet(SPREADSHEET_ID, sn)
                rows = ws.get_all_values()
                jids = [r[0] for r in rows[1:] if r and r[0]]
                target_jids.extend(jids)
                log(f"  {sn}: +{len(jids)} jobs")
            except Exception as e:
                log(f"  {sn}: error {e}")
        # dedup
        target_jids = list(dict.fromkeys(target_jids))
        log(f"  expand mode: {len(target_jids)} unique jobs")
    else:
        ws_act = open_sheet(SPREADSHEET_ID, "active_bidding")
        rows = ws_act.get_all_values()
        target_jids = [r[0] for r in rows[1:] if r and r[0]]
        log(f"  full refresh: {len(target_jids)} active_bidding jobs")

    if not target_jids:
        log("ไม่มี jobs ที่จะรีเฟรช — เสร็จสิ้น")
        return

    # ── อ่าน all_jobs เพื่อหา row index + budget ──
    log("\nReading all_jobs...")
    ws_all = open_sheet(SPREADSHEET_ID, "all_jobs")
    all_values = ws_all.get_all_values()
    hdrs = all_values[0]
    h_idx = {h: i for i, h in enumerate(hdrs)}

    # job_id → (row_num, budget)
    row_map = {}
    for row_num, r in enumerate(all_values[1:], start=2):
        jid = r[0] if r else ""
        if jid in target_jids:
            budget = r[h_idx.get("budget", 7)] if h_idx.get("budget", -1) < len(r) else ""
            row_map[jid] = (row_num, budget)

    log(f"  matched {len(row_map)} jobs in all_jobs")

    cache = load_winner_cache()
    log(f"  winner cache: {len(cache)} entries")

    # ── เปิด Chrome + refresh ทีละ job ──
    log("\nเชื่อมต่อ Chrome...")
    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()

        log("  navigate ไป process5...")
        page.goto(f"{PROCESS5_BASE}/egp-agpc01-web/announcement", wait_until="load", timeout=45000)
        time.sleep(5)

        new_winners = 0
        status_updates = 0
        update_payload = []

        for i, jid in enumerate(target_jids, 1):
            if jid not in row_map:
                log(f"\n[{i}/{len(target_jids)}] {jid}: ไม่พบใน all_jobs — ข้าม")
                continue

            row_num, budget = row_map[jid]
            log(f"\n[{i}/{len(target_jids)}] {jid} (row {row_num})")

            # ── ดึง getProjectDetail ก่อน (ได้ stepId/projectStatus/announceType) ──
            detail = fetch_project_detail(page, jid)
            now_iso = datetime.now().isoformat(timespec="seconds")
            fields = {"last_seen_at": now_iso}

            if detail.get("valid"):
                stepId  = detail.get("step_id", "")
                ps_raw  = detail.get("project_status_raw", "")  # added below
                a_type  = detail.get("announce_type", "")       # added below
                seqno   = detail.get("flow_seqno", 0)
                # เก็บ 3 fields ใหม่
                fields["step_id"] = stepId
                fields["project_status_raw"] = ps_raw
                fields["announce_type"] = a_type
                # Derive project_status text
                new_status = detail.get("project_status", "")
                if new_status:
                    fields["project_status"] = new_status
                # Cancellation detection
                is_cancelled = (ps_raw == "R") or (a_type in ("D1", "W1"))
                if is_cancelled:
                    fields["project_status"] = "ยกเลิก"
                    log(f"  🚫 CANCELLED detected: ps_raw={ps_raw} announce={a_type} stepId={stepId}")
                else:
                    log(f"  flowSeqno={seqno} stepId={stepId} ps={ps_raw} announce={a_type} → {new_status!r}")
                status_updates += 1
            else:
                log(f"  ⚠️  empty data หลัง retry — keep current project_status")

            # ── ตรวจ winner (ถ้ามี — override status เป็น 'ประมูลแล้ว') ──
            # ทำหลัง project detail เพื่อให้ stepId/projectStatus_raw/announceType ติดมาด้วย
            if not detail.get("valid") or detail.get("project_status_raw") != "R":
                winfo = fetch_winner_info(page, jid)
                if winfo and winfo.get("winner"):
                    price = winfo.get("winning_price", "")
                    pct = calc_pct_discount(budget, price)
                    cache[jid] = {
                        "winner_name":  winfo["winner"],
                        "winner_price": str(price),
                        "discount_pct": pct,
                        "award_date":   winfo.get("announce_date", ""),
                    }
                    new_winners += 1
                    log(f"  ✅ WINNER: {winfo['winner']} | {price} | -{pct}%")
                    fields["project_status"] = "ประมูลแล้ว"

            update_payload.append({"row": row_num, "fields": fields})

            # Rate limit guard
            time.sleep(1.5)
            if i % 50 == 0:
                log(f"  ⏸  cooldown 30s หลังจาก {i} jobs (rate limit guard)...")
                time.sleep(30)

        page.close()

    # ── Apply updates to all_jobs ──
    if update_payload:
        log(f"\nApply {len(update_payload)} updates ลง all_jobs...")
        batch_data = []
        for u in update_payload:
            for field, val in u["fields"].items():
                if field in h_idx:
                    col = chr(ord("A") + h_idx[field])
                    batch_data.append({
                        "range": f"all_jobs!{col}{u['row']}",
                        "values": [[val]],
                    })
        BATCH = 200
        for i in range(0, len(batch_data), BATCH):
            chunk = batch_data[i:i+BATCH]
            ws_all.spreadsheet.values_batch_update(
                {"valueInputOption": "USER_ENTERED", "data": chunk}
            )
        log(f"  applied {len(batch_data)} cell updates")

    if new_winners:
        save_winner_cache(cache)
        log(f"\n+{new_winners} winners → cache (รวม {len(cache)})")

    # ── Re-classify ──
    if update_payload or new_winners:
        log("\nเรียก Classifier rebuild...")
        try:
            from Sebastian_Classifier import main as classifier_main
            classifier_main()
        except Exception as e:
            log(f"  ⚠️ Classifier error: {e}")

    log(f"\nสรุป:")
    log(f"  new winners: {new_winners}")
    log(f"  status/deadline updates: {status_updates}")
    log(f"  total updates applied: {len(update_payload)}")


if __name__ == "__main__":
    main()
