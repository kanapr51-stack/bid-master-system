"""
research_stepid_v2.py — Comprehensive stepId catalog (Phase 4)

สุ่ม 300 jobs จาก all_jobs ครอบคลุม:
- ทุก project_status (กำลังประมูล/ประมูลแล้ว/ยกเลิก/กำลังเตรียม)
- กระจายตามช่วงเวลา (2025 vs 2026)
- งานทั้ง small + large budget

Probe getProjectDetail แล้วบันทึก raw + analyze stepId distribution
"""
import sys, json, time, random
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from playwright.sync_api import sync_playwright
from Sebastian_Scraper import connect_browser

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
BASE = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"
OUT = Path(__file__).parent.parent / "data" / "stepid_research_v2.json"

random.seed(42)


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def sample_diverse(n_per_status=75):
    """สุ่มหลากหลาย — n_per_status × 4 statuses = 300 jobs"""
    log("Reading all_jobs...")
    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    rows = ws.get_all_values()
    hdrs = rows[0]
    h_idx = {h: i for i, h in enumerate(hdrs)}

    by_status = defaultdict(list)
    for r in rows[1:]:
        jid = r[0]
        ps = r[h_idx.get("project_status", -1)] if h_idx.get("project_status", -1) < len(r) else ""
        pd = r[h_idx.get("publish_date", -1)] if h_idx.get("publish_date", -1) < len(r) else ""
        if jid and ps:
            by_status[ps].append((jid, pd))

    log("Distribution:")
    for s, jids in by_status.items():
        log(f"  {s!r}: {len(jids)}")

    sampled = {}
    for status in ["กำลังประมูล", "ประมูลแล้ว", "ยกเลิก", "กำลังเตรียม"]:
        pool = by_status.get(status, [])
        take = random.sample(pool, min(n_per_status, len(pool))) if pool else []
        for jid, pd in take:
            sampled[jid] = {"status": status, "publish_date": pd}
        log(f"  sampled {len(take)} from {status!r}")
    return sampled


def probe_detail(page, jid):
    js = """async (url) => {
        try { const r = await fetch(url, {credentials:'include'}); return await r.json(); }
        catch(e) { return {error: e.toString()}; }
    }"""
    res = page.evaluate(js, f"{BASE}/getProjectDetail?projectId={jid}")
    if not isinstance(res, dict):
        return None
    d = res.get("data", {}) or {}
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
    log("=" * 60)
    log("Comprehensive stepId Research v2 (300 jobs)")
    log("=" * 60)

    sampled = sample_diverse(n_per_status=75)
    total = len(sampled)
    log(f"\nTotal: {total} jobs to probe")

    results = {}
    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
                  wait_until="load", timeout=45000)
        time.sleep(5)

        for i, (jid, meta) in enumerate(sampled.items(), 1):
            d = probe_detail(page, jid)
            results[jid] = {**meta, "detail": d}
            if d:
                if i % 20 == 0 or d.get("stepId") not in {"M03","U03","S01","W01","W03","C01","I03","B03","Q01","Q03","Z01","Z03","C03"}:
                    log(f"[{i}/{total}] {jid}: step={d['stepId']} seqno={d['flowSeqno']} status={d['projectStatus']} announce={d['announceType']}")
            time.sleep(1.2)
            if i % 50 == 0:
                log(f"  ⏸ cooldown 30s")
                time.sleep(30)

        page.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "n_probed": total,
        "samples": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nSaved → {OUT}")

    # Analysis
    log("\n" + "=" * 60)
    log("ANALYSIS")
    log("=" * 60)

    by_step = defaultdict(list)
    invalid = 0
    for jid, info in results.items():
        d = info.get("detail")
        if not d or not d.get("stepId"):
            invalid += 1
            continue
        key = d["stepId"]
        by_step[key].append({
            "jid": jid,
            "scrape_status": info["status"],
            "publish_date": info["publish_date"],
            "seqno": d.get("flowSeqno"),
            "projectStatus": d.get("projectStatus"),
            "announceType": d.get("announceType"),
            "flowId": d.get("flowId"),
            "typeId": d.get("typeId"),
            "goodsId": d.get("goodsId"),
        })
    log(f"valid probes: {total - invalid}, invalid: {invalid}")
    log(f"unique stepIds: {len(by_step)}")
    log("\nstepId frequencies (sorted):")
    for step in sorted(by_step.keys(), key=lambda k: -len(by_step[k])):
        recs = by_step[step]
        seqnos = Counter(r["seqno"] for r in recs)
        statuses = Counter(r["projectStatus"] for r in recs)
        announces = Counter(r["announceType"] for r in recs)
        flowIds = Counter(r["flowId"] for r in recs)
        scrape_statuses = Counter(r["scrape_status"] for r in recs)
        log(f"\n{step!r} (n={len(recs)})")
        log(f"  flowSeqno: {dict(seqnos)}")
        log(f"  projectStatus: {dict(statuses)}")
        log(f"  announceType: {dict(announces)}")
        log(f"  flowId: {dict(flowIds)}")
        log(f"  scrape_status: {dict(scrape_statuses)}")
        if len(recs) <= 5:
            for r in recs:
                log(f"    {r['jid']} (publish {r['publish_date']})")

    log("\n" + "=" * 60)
    log("announceType cross-analysis")
    log("=" * 60)
    by_at = defaultdict(lambda: defaultdict(int))
    for jid, info in results.items():
        d = info.get("detail")
        if not d:
            continue
        at = d.get("announceType", "")
        ps = d.get("projectStatus", "")
        by_at[at][ps] += 1
    for at in sorted(by_at):
        log(f"announceType={at!r}: {dict(by_at[at])}")

    log("\n" + "=" * 60)
    log("flowId cross-analysis")
    log("=" * 60)
    by_fid = defaultdict(lambda: Counter())
    for jid, info in results.items():
        d = info.get("detail")
        if not d:
            continue
        fid = d.get("flowId", "")
        step = d.get("stepId", "")
        by_fid[fid][step] += 1
    for fid in sorted(by_fid):
        log(f"flowId={fid!r}: {dict(by_fid[fid])}")


if __name__ == "__main__":
    main()
