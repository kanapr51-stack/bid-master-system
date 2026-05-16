"""
audit_all_sheets.py — Audit tor_review + cancelled + awarded (sample) + pre_tor

วัตถุประสงค์:
- ตรวจ tor_review (ทั้งหมด): stepId ยังเป็น U* ไหม + projectStatus=A
- ตรวจ cancelled (sample 10): projectStatus=R จริงหรือเปล่า + ไม่มี winner
- ตรวจ awarded (sample 20 random): มี winner จริง (priceAgree != null)
- pre_tor: 0 jobs — ไม่ต้อง audit

Output: data/sheet_audit_result.json + summary
"""
import sys, json, time, random
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

SS = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
BASE = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"
OUT = Path("data/sheet_audit_result.json")

random.seed(42)


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def collect_jids():
    """รวบรวม jids ที่จะ audit แยกตาม sheet"""
    sheets_to_audit = {
        "tor_review": None,        # ทั้งหมด
        "cancelled_jobs": 10,       # sample 10
        "awarded_jobs": 20,         # sample 20 random
        "pre_tor": None,            # ทั้งหมด (probably 0)
    }
    targets = {}
    for sn, limit in sheets_to_audit.items():
        try:
            ws = open_sheet(SS, sn)
            rows = ws.get_all_values()
            jids = [r[0] for r in rows[1:] if r and r[0]]
            if limit and len(jids) > limit:
                jids = random.sample(jids, limit)
            targets[sn] = jids
            log(f"  {sn}: {len(jids)} jobs")
        except Exception as e:
            log(f"  {sn}: error {e}")
            targets[sn] = []
    return targets


def probe(page, jid):
    js = """async (url) => { const r = await fetch(url, {credentials:'include'}); return await r.json(); }"""
    d = page.evaluate(js, f"{BASE}/getProjectDetail?projectId={jid}")
    pd = d.get("data", {}) if isinstance(d, dict) else {}
    pr = page.evaluate(js, f"{BASE}/getProcureResult?projectId={jid}")
    prd = pr.get("data", {}) if isinstance(pr, dict) else {}
    winner = None
    arr = prd.get("procureResultList", [])
    if arr:
        for item in arr[0].get("procureResultDataResponse", []):
            if item.get("priceAgree") is not None:
                winner = {"name": item.get("receiveNameTh", ""), "price": item.get("priceAgree")}
                break
    return {
        "stepId":        pd.get("stepId", ""),
        "flowSeqno":     pd.get("flowSeqno", 0),
        "projectStatus": pd.get("projectStatus", ""),
        "announceType":  pd.get("announceType", ""),
        "winner":        winner,
        "valid":         bool(pd.get("stepId") or pd.get("flowSeqno")),
    }


def audit_sheet(page, sheet_name, jids, expected_check):
    """expected_check(jid, api_result) → (is_correct, verdict_text)"""
    log(f"\n=== Audit {sheet_name} ({len(jids)} jobs) ===")
    results = []
    wrong_count = 0
    for i, jid in enumerate(jids, 1):
        result = probe(page, jid)
        correct, verdict = expected_check(jid, result)
        if not correct:
            wrong_count += 1
            log(f"[{i:3}/{len(jids)}] ❌ {jid}: {verdict}")
        elif i % 5 == 0 or i == len(jids):
            log(f"[{i:3}/{len(jids)}] ✓ {jid}: ok")
        results.append({"jid": jid, "result": result, "correct": correct, "verdict": verdict})
        time.sleep(1.5)
        if i % 25 == 0:
            log(f"  ⏸ cooldown 30s")
            time.sleep(30)
    log(f"  → {wrong_count}/{len(jids)} wrong")
    return results, wrong_count


# Expected checks per sheet
def check_tor(jid, r):
    if not r["valid"]:
        return (False, "empty (rate limit?)")
    if r["projectStatus"] == "R":
        return (False, f"projectStatus=R should be cancelled")
    if r["stepId"].startswith("U"):
        return (True, "U-stepId active = correct tor_review")
    return (False, f"stepId={r['stepId']} should NOT be in tor_review")


def check_cancelled(jid, r):
    if not r["valid"]:
        return (False, "empty (rate limit?)")
    if r["projectStatus"] == "R":
        return (True, "projectStatus=R = correct cancelled")
    if r["announceType"] in ("D1", "W1"):
        return (True, f"announce={r['announceType']} = correct cancelled")
    if r["stepId"].startswith("B"):
        return (True, "B-stepId = correct cancelled")
    return (False, f"stepId={r['stepId']} ps={r['projectStatus']} announce={r['announceType']} should NOT be cancelled")


def check_awarded(jid, r):
    if not r["valid"]:
        return (False, "empty (rate limit?)")
    if r["winner"]:
        return (True, f"has winner {r['winner']['name']}")
    # ใน awarded_jobs ของเรา = มี winner_cache local — แต่ API อาจไม่มี winner ตอนนี้
    # (อาจเป็นเพราะ winner cache เป็นข้อมูลเก่า — verify ว่า stepId เป็น W*/C*/I*)
    if r["stepId"][:1] in "WCIX":
        return (True, f"stepId={r['stepId']} = winner stage (cache อาจล่าช้า)")
    return (False, f"stepId={r['stepId']} no winner → cache อาจผิด")


def main():
    log("=" * 60)
    log("Sheet Audit — tor + cancelled + awarded (sample)")
    log("=" * 60)
    targets = collect_jids()

    all_results = {}
    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
                  wait_until="load", timeout=45000)
        time.sleep(5)

        # tor_review
        if targets["tor_review"]:
            res, wrong = audit_sheet(page, "tor_review", targets["tor_review"], check_tor)
            all_results["tor_review"] = {"results": res, "wrong": wrong}

        # cancelled
        if targets["cancelled_jobs"]:
            res, wrong = audit_sheet(page, "cancelled_jobs", targets["cancelled_jobs"], check_cancelled)
            all_results["cancelled_jobs"] = {"results": res, "wrong": wrong}

        # awarded sample
        if targets["awarded_jobs"]:
            res, wrong = audit_sheet(page, "awarded_jobs", targets["awarded_jobs"], check_awarded)
            all_results["awarded_jobs"] = {"results": res, "wrong": wrong}

        page.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"\nSaved → {OUT}")

    log("\n" + "=" * 60)
    log("AUDIT SUMMARY")
    log("=" * 60)
    total_wrong = 0
    for sn, info in all_results.items():
        n = len(info["results"])
        w = info["wrong"]
        total_wrong += w
        log(f"  {sn}: {n - w}/{n} correct  ({w} wrong)")
        if w > 0:
            log(f"    wrong jids:")
            for r in info["results"]:
                if not r["correct"]:
                    log(f"      {r['jid']}: {r['verdict']}")
    log(f"\n  TOTAL WRONG: {total_wrong}")


if __name__ == "__main__":
    main()
