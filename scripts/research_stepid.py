"""
research_stepid.py — สำรวจ stepId catalog จาก eGP API

Phase 1: สุ่ม 50 jobs (15 กำลังประมูล + 15 ประมูลแล้ว + 10 ยกเลิก + 10 กำลังเตรียม)
         → probe getProjectDetail → เก็บ stepId/flowSeqno/projectStatus/announceType
Phase 1.5: Probe 5 Q7-9 gap jobs ที่ user สงสัย
Phase 2A: ลองหา document API endpoints (10 patterns)

Output: data/stepid_research.json
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
SEED = 42
random.seed(SEED)

OUT = Path(__file__).parent.parent / "data" / "stepid_research.json"


def log(m):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def sample_jobs():
    """สุ่ม jobs ตาม project_status quotas"""
    log("Reading all_jobs...")
    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    rows = ws.get_all_values()
    hdrs = rows[0]
    ps_i = hdrs.index("project_status")

    by_status = defaultdict(list)
    for r in rows[1:]:
        ps = r[ps_i] if ps_i < len(r) else ""
        if ps and r[0]:
            by_status[ps].append(r[0])

    log(f"all_jobs project_status distribution:")
    for s, jids in by_status.items():
        log(f"  {s!r}: {len(jids)}")

    quotas = {
        "กำลังประมูล": 15,
        "ประมูลแล้ว": 15,
        "ยกเลิก": 10,
        "กำลังเตรียม": 10,
    }
    sampled = {}
    for status, n in quotas.items():
        pool = by_status.get(status, [])
        take = random.sample(pool, min(n, len(pool))) if pool else []
        for jid in take:
            sampled[jid] = status
        log(f"  sampled {len(take)}/{n} from {status!r}")

    return sampled


def probe_detail(page, jid):
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            return await r.json();
        } catch(e) { return {error: e.toString()}; }
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
        "all_keys":      list(d.keys()),
    }


def probe_doc_endpoints(page, jid):
    """ลอง patterns ของ endpoint ที่อาจคืน document list"""
    candidates = [
        f"{BASE}/getProjectDocuments?projectId={jid}",
        f"{BASE}/getAnnouncementFiles?projectId={jid}",
        f"{BASE}/getAttachment?projectId={jid}",
        f"{BASE}/listFile?projectId={jid}",
        f"{BASE}/getProjectFile?projectId={jid}",
        f"{BASE}/getAnnouncementFile?projectId={jid}",
        f"{BASE}/getDocumentList?projectId={jid}",
        f"{BASE}/getFiles?projectId={jid}",
        f"{BASE}/getAllAnnouncement?projectId={jid}",
        f"{BASE}/getAnnouncement?projectId={jid}",
    ]
    js = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            const text = await r.text();
            try { return {status: r.status, body: JSON.parse(text)}; }
            catch { return {status: r.status, preview: text.slice(0, 200)}; }
        } catch(e) { return {error: e.toString()}; }
    }"""
    results = {}
    for url in candidates:
        ep = url.split("/")[-1].split("?")[0]
        res = page.evaluate(js, url)
        results[ep] = res
        time.sleep(0.5)
    return results


def main():
    log("=" * 60)
    log("stepId Research — Phase 1+1.5+2A")
    log("=" * 60)

    sampled = sample_jobs()
    log(f"Total sampled: {len(sampled)}")

    # Q7-9 gap jobs
    q79_jobs = {
        "69049365887": "should-be-active (user)",
        "69049011449": "should-be-active (user)",
        "69049235336": "should-be-active (user)",
        "69059074818": "OK in tor (still consulting)",
        "69059075123": "OK in tor (still consulting)",
    }
    # Add active jobs (deadline expired but still active)
    extra_active = {
        "69049234631": "active but yer-shong yesterday",
        "69049094319": "active but past deadline",
        "69049219653": "active but past deadline",
        "69049223058": "active but past deadline",
    }

    all_targets = {}
    for jid, status in sampled.items():
        all_targets[jid] = {"sample_group": status, "note": ""}
    for jid, note in q79_jobs.items():
        all_targets[jid] = {"sample_group": "q79_gap", "note": note}
    for jid, note in extra_active.items():
        all_targets[jid] = {"sample_group": "active_now", "note": note}

    log(f"\nTotal targets to probe: {len(all_targets)}")

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = browser.contexts[0].new_page()
        log("Loading process5...")
        page.goto("https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
                  wait_until="load", timeout=45000)
        time.sleep(5)

        results = {}
        for i, (jid, meta) in enumerate(all_targets.items(), 1):
            detail = probe_detail(page, jid)
            results[jid] = {**meta, "detail": detail}
            if detail:
                log(f"[{i}/{len(all_targets)}] {jid} ({meta['sample_group']}): step={detail['stepId']} seqno={detail['flowSeqno']} status={detail['projectStatus']} announce={detail['announceType']}")
            else:
                log(f"[{i}/{len(all_targets)}] {jid}: NO DATA")
            time.sleep(1.5)
            if i % 25 == 0:
                log(f"  ⏸  cooldown 30s")
                time.sleep(30)

        # Phase 2A: doc endpoint discovery on 3 jobs ที่ stepId ต่างกัน
        log("\n" + "=" * 60)
        log("Phase 2A: doc endpoint discovery")
        log("=" * 60)

        # Pick 3 jobs from different stages
        doc_probe_jids = [
            ("69059074818", "U03 - consulting"),
            ("69049234631", "S01 - active"),
            ("69039325763", "W03 - winner"),
        ]
        doc_results = {}
        for jid, label in doc_probe_jids:
            log(f"\nProbing {jid} ({label})...")
            doc_results[jid] = {"label": label, "endpoints": probe_doc_endpoints(page, jid)}
            for ep, res in doc_results[jid]["endpoints"].items():
                if isinstance(res, dict):
                    s = res.get("status", "?")
                    has_data = "body" in res
                    log(f"  {ep}: status={s} json={has_data}")

        page.close()

    # Save raw
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "samples": results,
        "doc_endpoint_probe": doc_results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nSaved → {OUT}")

    # Analyze
    log("\n" + "=" * 60)
    log("ANALYSIS: stepId catalog")
    log("=" * 60)

    by_step = defaultdict(list)
    for jid, info in results.items():
        d = info.get("detail")
        if not d:
            continue
        key = d.get("stepId", "")
        by_step[key].append({
            "jid": jid,
            "group": info["sample_group"],
            "seqno": d.get("flowSeqno"),
            "status": d.get("projectStatus"),
            "announce": d.get("announceType"),
            "flowId": d.get("flowId"),
        })

    for step in sorted(by_step.keys()):
        recs = by_step[step]
        seqnos = Counter(r["seqno"] for r in recs)
        statuses = Counter(r["status"] for r in recs)
        announces = Counter(r["announce"] for r in recs)
        flowIds = Counter(r["flowId"] for r in recs)
        groups = Counter(r["group"] for r in recs)
        log(f"\nstepId={step!r}  ({len(recs)} jobs)")
        log(f"  groups: {dict(groups)}")
        log(f"  flowSeqno: {dict(seqnos)}")
        log(f"  projectStatus: {dict(statuses)}")
        log(f"  announceType: {dict(announces)}")
        log(f"  flowId: {dict(flowIds)}")


if __name__ == "__main__":
    main()
