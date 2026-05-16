"""
fetch_bid_history.py — Phase B Migration

ดึงข้อมูล bidders ของทุกงานใน awarded_jobs จาก eGP getProcureResult
→ populate bid_history sheet (1 row = 1 bidder)
→ update awarded_jobs ใส่ deliver_day + num_bidders

Schema bid_history:
  job_id, bidder_name, bidder_tin, price_proposal, price_agree, result_flag,
  is_winner (priceAgree != null), is_sme (scoreTypeId="SME"),
  is_joint_venture, jv_partners, consider_desc, fetched_at

Usage:
    python scripts/fetch_bid_history.py [--limit N] [--jids id1,id2,...]
"""
import sys, json, time, argparse
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser
from Sebastian_Classifier import BID_HISTORY_HEADERS, AWARDED_JOBS_HEADERS

SS = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
BASE = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def fetch_procure_result(page, jid: str) -> dict:
    """ดึง procureResult ครบ — คืน {bidders: [...], announce_date, deliver_day, ...}"""
    js = """async (url) => { const r = await fetch(url, {credentials:'include'}); return await r.json(); }"""
    try:
        res = page.evaluate(js, f"{BASE}/getProcureResult?projectId={jid}")
        if not isinstance(res, dict):
            return {}
        d = res.get("data", {}) or {}
        arr = d.get("procureResultList", []) or []
        if not arr:
            return {"valid": False}

        # รวม bidders ทุก group
        all_bidders = []
        consider_desc = ""
        for group in arr:
            consider_desc = group.get("considerDesc", consider_desc)
            for item in group.get("procureResultDataResponse", []) or []:
                jv_list = item.get("jointVentureAndConsortiumsResponseList") or []
                jv_partners = ", ".join(
                    j.get("receiveNameTh", "") for j in jv_list if j.get("receiveNameTh")
                )
                all_bidders.append({
                    "bidder_name":     item.get("receiveNameTh", ""),
                    "bidder_tin":      item.get("receiveTin", ""),
                    "price_proposal":  item.get("priceProposal") or "",
                    "price_agree":     item.get("priceAgree") or "",
                    "result_flag":     item.get("resultFlag", ""),
                    "is_winner":       "TRUE" if item.get("priceAgree") is not None else "FALSE",
                    "is_sme":          "TRUE" if item.get("scoreTypeId") == "SME" else "FALSE",
                    "is_joint_venture": "TRUE" if jv_list else "FALSE",
                    "jv_partners":     jv_partners,
                    "consider_desc":   consider_desc,
                })

        return {
            "valid":         True,
            "bidders":       all_bidders,
            "announce_date": d.get("announceDate", ""),
            "report_date":   d.get("reportDate", ""),
            "deliver_day":   d.get("deliverDay", ""),
            "project_cost":  d.get("projectCost", ""),
        }
    except Exception as e:
        log(f"  err {jid}: {type(e).__name__}: {e}")
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max jobs to process (0 = all)")
    ap.add_argument("--jids", help="comma-separated job_ids")
    args = ap.parse_args()

    log("=" * 60)
    log("Phase B Migration — fetch bid_history for awarded jobs")
    log("=" * 60)

    # อ่าน awarded_jobs
    ws_aw = open_sheet(SS, "awarded_jobs")
    rows = ws_aw.get_all_values()
    hdrs = rows[0]
    log(f"awarded_jobs: {len(rows) - 1} rows, columns: {len(hdrs)}")

    # หา target jids
    if args.jids:
        target_jids = [j.strip() for j in args.jids.split(",") if j.strip()]
        log(f"  targeted: {len(target_jids)}")
    else:
        target_jids = [r[0] for r in rows[1:] if r and r[0]]
        log(f"  all awarded: {len(target_jids)}")
    if args.limit:
        target_jids = target_jids[:args.limit]
        log(f"  limited to: {len(target_jids)}")

    # อ่าน bid_history sheet ดู existing jids (ป้องกัน duplicate)
    ws_bh = open_sheet(SS, "bid_history")
    bh_rows = ws_bh.get_all_values()
    existing_jids = set()
    if len(bh_rows) > 1:
        for r in bh_rows[1:]:
            if r and r[0]:
                existing_jids.add(r[0])
    log(f"bid_history existing: {len(existing_jids)} unique jids")

    new_jids = [j for j in target_jids if j not in existing_jids]
    log(f"new to fetch: {len(new_jids)}")
    if not new_jids:
        log("ไม่มี jid ใหม่ — ครบแล้ว")
        return

    # ── Fetch from eGP ──
    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
                  wait_until="load", timeout=45000)
        time.sleep(5)

        now_iso = datetime.now().isoformat(timespec="seconds")
        all_bid_rows = []
        awarded_updates = []  # (jid, deliver_day, num_bidders)

        for i, jid in enumerate(new_jids, 1):
            info = fetch_procure_result(page, jid)
            if not info.get("valid"):
                if i % 10 == 0:
                    log(f"[{i}/{len(new_jids)}] {jid}: empty")
                continue

            bidders = info["bidders"]
            for b in bidders:
                all_bid_rows.append([
                    jid,
                    b["bidder_name"],
                    b["bidder_tin"],
                    str(b["price_proposal"]),
                    str(b["price_agree"]),
                    b["result_flag"],
                    b["is_winner"],
                    b["is_sme"],
                    b["is_joint_venture"],
                    b["jv_partners"],
                    b["consider_desc"],
                    now_iso,
                ])

            awarded_updates.append((jid, info.get("deliver_day", ""), len(bidders)))

            if i % 10 == 0:
                winners = sum(1 for b in bidders if b["is_winner"] == "TRUE")
                log(f"[{i:3}/{len(new_jids)}] {jid}: {len(bidders)} bidders, {winners} winner(s)")

            time.sleep(1.2)
            if i % 50 == 0:
                log(f"  ⏸ cooldown 30s")
                time.sleep(30)

        page.close()

    # ── Append to bid_history sheet ──
    if all_bid_rows:
        log(f"\nAppending {len(all_bid_rows)} bidder rows to bid_history...")
        BATCH = 500
        for i in range(0, len(all_bid_rows), BATCH):
            ws_bh.append_rows(all_bid_rows[i:i+BATCH], value_input_option="USER_ENTERED")
            log(f"  appended {min(i+BATCH, len(all_bid_rows))}/{len(all_bid_rows)}")

    # ── Update awarded_jobs — เพิ่ม deliver_day + num_bidders ──
    if awarded_updates:
        log(f"\nUpdate awarded_jobs ({len(awarded_updates)} rows)...")
        # หา column index
        try:
            dd_col = hdrs.index("deliver_day")
            nb_col = hdrs.index("num_bidders")
        except ValueError:
            log("  ⚠️  awarded_jobs ยังไม่มี deliver_day/num_bidders columns — skip update")
            return

        # หา row by jid
        jid_to_row = {r[0]: (i + 2) for i, r in enumerate(rows[1:]) if r and r[0]}
        batch = []
        for jid, dd, nb in awarded_updates:
            if jid in jid_to_row:
                rn = jid_to_row[jid]
                dd_letter = chr(ord("A") + dd_col)
                nb_letter = chr(ord("A") + nb_col)
                batch.append({"range": f"awarded_jobs!{dd_letter}{rn}", "values": [[str(dd)]]})
                batch.append({"range": f"awarded_jobs!{nb_letter}{rn}", "values": [[str(nb)]]})

        BATCH = 200
        for i in range(0, len(batch), BATCH):
            ws_aw.spreadsheet.values_batch_update(
                {"valueInputOption": "USER_ENTERED", "data": batch[i:i+BATCH]}
            )
        log(f"  updated {len(awarded_updates)} awarded rows")

    log(f"\n✅ Migration complete")
    log(f"  bidders added:    {len(all_bid_rows)}")
    log(f"  awarded updated:  {len(awarded_updates)}")


if __name__ == "__main__":
    main()
