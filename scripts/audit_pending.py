"""Audit ทุก row ใน pending_award — ดูว่ามีตัวไหนควรย้ายไปชีตอื่น (winner / cancelled)"""
import sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

SS = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
BASE = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"


def main():
    ws = open_sheet(SS, "pending_award")
    rows = ws.get_all_values()
    hdrs = rows[0]
    jid_i = hdrs.index("job_id")
    dl_i  = hdrs.index("deadline")
    si_i  = hdrs.index("step_id")

    jids = [(r[jid_i], r[dl_i], r[si_i]) for r in rows[1:] if r and r[jid_i]]
    print(f"pending_award: {len(jids)} jobs to audit\n")

    js = """async (url) => { const r = await fetch(url, {credentials:'include'}); return await r.json(); }"""

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
                  wait_until="load", timeout=45000)
        time.sleep(5)

        verdicts = {"keep_pending": [], "should_be_awarded": [], "should_be_cancelled": [],
                    "should_be_active": [], "api_empty": []}

        for i, (jid, dl, step) in enumerate(jids, 1):
            d = page.evaluate(js, f"{BASE}/getProjectDetail?projectId={jid}")
            pd = d.get("data", {}) if isinstance(d, dict) else {}
            new_step = pd.get("stepId", "")
            ps = pd.get("projectStatus", "")
            at = pd.get("announceType", "")
            seqno = pd.get("flowSeqno", 0)

            # Check for winner
            pr = page.evaluate(js, f"{BASE}/getProcureResult?projectId={jid}")
            prd = pr.get("data", {}) if isinstance(pr, dict) else {}
            arr = prd.get("procureResultList", [])
            has_winner = False
            winner_name = ""
            winner_price = ""
            if arr:
                for item in arr[0].get("procureResultDataResponse", []):
                    if item.get("priceAgree") is not None:
                        has_winner = True
                        winner_name = item.get("receiveNameTh", "")
                        winner_price = item.get("priceAgree")
                        break

            verdict = ""
            if not new_step and seqno == 0:
                verdicts["api_empty"].append(jid)
                verdict = "EMPTY (API rate limit?)"
            elif ps == "R" or at in ("D1", "W1"):
                verdicts["should_be_cancelled"].append(jid)
                verdict = "🚫 should be CANCELLED"
            elif has_winner:
                verdicts["should_be_awarded"].append((jid, winner_name, winner_price))
                verdict = f"🏆 should be AWARDED: {winner_name} @ {winner_price:,}"
            elif new_step and new_step[0] in "MSZ":
                # stepId ยัง active — เช็คว่า deadline (เดิม) ผ่านไหม
                from datetime import date
                from Sebastian_Classifier import parse_thai_date
                dl_parsed = parse_thai_date(dl)
                if dl_parsed is None or dl_parsed < date.today():
                    verdicts["keep_pending"].append(jid)
                    verdict = f"✓ keep pending (stepId {new_step} active, deadline passed)"
                else:
                    verdicts["should_be_active"].append(jid)
                    verdict = f"⬆️ should be ACTIVE (stepId {new_step}, deadline NOT passed yet)"
            elif new_step and new_step[0] in "WCI":
                verdicts["keep_pending"].append(jid)
                verdict = f"✓ keep pending (stepId {new_step}, no winner cache yet)"
            else:
                verdicts["keep_pending"].append(jid)
                verdict = f"? keep pending (stepId {new_step})"

            print(f"[{i:2}/{len(jids)}] {jid}: step={new_step} ps={ps} announce={at} seqno={seqno} → {verdict}")
            time.sleep(1.5)
            if i % 10 == 0:
                print(f"  ⏸ cooldown 30s")
                time.sleep(30)

        page.close()

    print("\n" + "=" * 60)
    print("AUDIT SUMMARY")
    print("=" * 60)
    print(f"✓ keep pending:          {len(verdicts['keep_pending'])}")
    print(f"🏆 should be awarded:     {len(verdicts['should_be_awarded'])}")
    print(f"🚫 should be cancelled:   {len(verdicts['should_be_cancelled'])}")
    print(f"⬆️ should be active:      {len(verdicts['should_be_active'])}")
    print(f"? API empty:             {len(verdicts['api_empty'])}")
    if verdicts['should_be_awarded']:
        print(f"\nAwarded winners found:")
        for jid, name, price in verdicts['should_be_awarded']:
            print(f"  {jid}: {name} @ {price:,}")
    if verdicts['should_be_cancelled']:
        print(f"\nCancelled: {verdicts['should_be_cancelled']}")
    if verdicts['should_be_active']:
        print(f"\nShould be active: {verdicts['should_be_active']}")
    if verdicts['api_empty']:
        print(f"\nEmpty (retry?): {verdicts['api_empty']}")


if __name__ == "__main__":
    main()
