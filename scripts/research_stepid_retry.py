"""Retry failed jobs จาก stepid_research_v2.json — delay 3s + cooldown 60s/20jobs"""
import sys, json, time
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

BASE = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"
INPUT = Path(__file__).parent.parent / "data" / "stepid_research_v2.json"
OUT = INPUT  # update in place


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def probe(page, jid):
    js = """async (url) => {
        try { const r = await fetch(url, {credentials:'include'}); return await r.json(); }
        catch(e) { return {error: e.toString()}; }
    }"""
    res = page.evaluate(js, f"{BASE}/getProjectDetail?projectId={jid}")
    if not isinstance(res, dict):
        return None
    d = res.get("data", {}) or {}
    if not d.get("stepId") and not d.get("flowSeqno"):
        return None  # invalid
    return {
        "flowSeqno":     d.get("flowSeqno"),
        "stepId":        d.get("stepId", ""),
        "flowId":        d.get("flowId", ""),
        "projectStatus": d.get("projectStatus", ""),
        "announceType":  d.get("announceType", ""),
        "typeId":        d.get("typeId", ""),
        "goodsId":       d.get("goodsId", ""),
        "isSect7":       d.get("isSect7"),
    }


def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    samples = data["samples"]
    failed = [(jid, info) for jid, info in samples.items() if not info.get("detail") or not info["detail"].get("stepId")]
    log(f"Retry {len(failed)} failed jobs (delay 3s, cooldown 60s/20)")

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
                  wait_until="load", timeout=45000)
        time.sleep(5)

        recovered = 0
        new_stepids = set()
        for i, (jid, info) in enumerate(failed, 1):
            d = probe(page, jid)
            if d:
                samples[jid]["detail"] = d
                recovered += 1
                stepid = d.get("stepId")
                if stepid:
                    new_stepids.add(stepid)
                if i % 10 == 0 or stepid not in {"M03","U03","U06","S01","W01","W03","C01","C03","I03","B03","Q01","Q03","Z01","Z03","E03","X01","X03"}:
                    log(f"[{i}/{len(failed)}] {jid}: step={d['stepId']} seqno={d['flowSeqno']}")
            time.sleep(3.0)
            if i % 20 == 0:
                log(f"  ⏸ cooldown 60s ({recovered} recovered)")
                time.sleep(60)

        page.close()

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nRecovered {recovered}/{len(failed)} → saved to {OUT.name}")

    # Re-analyze
    by_step = defaultdict(list)
    invalid = 0
    for jid, info in samples.items():
        d = info.get("detail")
        if not d or not d.get("stepId"):
            invalid += 1
            continue
        by_step[d["stepId"]].append({
            "jid": jid,
            "scrape_status": info["status"],
            "seqno": d.get("flowSeqno"),
            "projectStatus": d.get("projectStatus"),
            "announceType": d.get("announceType"),
            "flowId": d.get("flowId"),
        })

    log(f"\nFinal valid: {len(samples) - invalid}/{len(samples)}, invalid: {invalid}")
    log(f"Total unique stepIds: {len(by_step)}")
    log("\nstepId summary (sorted by freq):")
    for step in sorted(by_step.keys(), key=lambda k: -len(by_step[k])):
        recs = by_step[step]
        seqnos = Counter(r["seqno"] for r in recs)
        statuses = Counter(r["projectStatus"] for r in recs)
        announces = Counter(r["announceType"] for r in recs)
        flowIds = Counter(r["flowId"] for r in recs)
        log(f"\n{step!r} (n={len(recs)})")
        log(f"  flowSeqno: {dict(seqnos)}")
        log(f"  projectStatus: {dict(statuses)}")
        log(f"  announceType: {dict(announces)}")
        log(f"  flowId: {dict(flowIds)}")


if __name__ == "__main__":
    main()
