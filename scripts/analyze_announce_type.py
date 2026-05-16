"""
analyze_announce_type.py — วิเคราะห์ announceType + flowId mapping จาก research data

Output: ทำตารางที่อธิบาย announceType แต่ละค่า + flowId family
"""
import sys, json
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

INPUT_V1 = Path("data/stepid_research.json")
INPUT_V2 = Path("data/stepid_research_v2.json")


def load_all():
    """Merge samples from v1 + v2"""
    all_samples = {}
    for f in [INPUT_V1, INPUT_V2]:
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            for jid, info in data.get("samples", {}).items():
                if info.get("detail") and info["detail"].get("stepId"):
                    all_samples[jid] = info
    return all_samples


def main():
    samples = load_all()
    print(f"Total valid samples: {len(samples)}")
    print()

    # announceType cross-tab with stepId + projectStatus
    print("=" * 60)
    print("announceType × stepId × projectStatus")
    print("=" * 60)
    breakdown = defaultdict(lambda: defaultdict(Counter))
    for info in samples.values():
        d = info["detail"]
        at = d.get("announceType", "")
        step = d.get("stepId", "")
        status = d.get("projectStatus", "")
        breakdown[at][step][status] += 1

    for at in sorted(breakdown.keys()):
        total = sum(sum(s.values()) for s in breakdown[at].values())
        print(f"\nannounceType={at!r} (total={total})")
        for step in sorted(breakdown[at]):
            statuses = breakdown[at][step]
            statuses_str = ", ".join(f"{s}={c}" for s, c in statuses.items())
            print(f"  stepId={step}: {statuses_str}")

    # flowId × stepId
    print()
    print("=" * 60)
    print("flowId → stepId family")
    print("=" * 60)
    flow_step = defaultdict(Counter)
    for info in samples.values():
        d = info["detail"]
        fid = d.get("flowId", "")
        step = d.get("stepId", "")
        flow_step[fid][step] += 1

    flow_meaning = {
        "0":  "Cancelled (B family)",
        "1":  "TOR drafting / consultation (M, U)",
        "7":  "Winner announcement (W)",
        "9":  "Implementation (I)",
        "10": "Quote/early prep (Q)",
        "13": "X family (unknown)",
        "15": "Contract (C)",
        "16": "Submission/bidding (S, Z, E)",
    }
    for fid in sorted(flow_step.keys(), key=lambda x: int(x) if x.isdigit() else 999):
        steps = flow_step[fid]
        total = sum(steps.values())
        meaning = flow_meaning.get(fid, "❓ unknown")
        print(f"\nflowId={fid!r} (n={total}) — {meaning}")
        for s, c in steps.most_common():
            print(f"  {s}: {c}")

    # stepId by status (overall view)
    print()
    print("=" * 60)
    print("stepId master summary")
    print("=" * 60)
    by_step = defaultdict(list)
    for jid, info in samples.items():
        d = info["detail"]
        by_step[d["stepId"]].append(info)

    print(f"{'stepId':<8} {'count':<6} {'flowSeqno':<10} {'projectStatus':<15} {'announceType':<15} {'flowId':<8}")
    for step in sorted(by_step.keys()):
        recs = by_step[step]
        seqnos = Counter(r["detail"]["flowSeqno"] for r in recs)
        statuses = Counter(r["detail"]["projectStatus"] for r in recs)
        announces = Counter(r["detail"]["announceType"] for r in recs)
        flowIds = Counter(r["detail"]["flowId"] for r in recs)
        print(f"{step:<8} {len(recs):<6} {str(dict(seqnos))[:10]:<10} {str(dict(statuses))[:15]:<15} {str(dict(announces))[:15]:<15} {str(dict(flowIds))[:8]:<8}")


if __name__ == "__main__":
    main()
