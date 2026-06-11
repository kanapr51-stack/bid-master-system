"""_probe_bidder_count_pilot.py — PILOT (ปลอดภัย): ดึงจำนวนผู้ยื่นซองต่องาน vs ช่วงราคา
เพื่อทดสอบสมมติฐาน "งานใหญ่คนยื่นน้อยลง (ชั้นผู้รับเหมาบีบ)". กัญจน์ 2026-06-11.

ความปลอดภัย (INC-001): throttle 2.5s/call, abort ถ้า fail 3 ครั้งติด, จำกัด ~15 งาน.
sample: ถนน FY2567-2568, stratified ตามช่วงราคา (ท้องถิ่น) + กรมทางหลวง 2-3 งาน.
output: data/bidder_count_pilot.json + ตาราง. read-only ต่อ production (ไม่เขียน DB หลัก).
"""
import sys, sqlite3, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci
from process5_http_client import get_procure_result

DB = Path(__file__).resolve().parent.parent / "data" / "winner_history.db"
CS = ci.COMPETITIVE_SET
ph = ",".join("?" * len(CS))
SLEEP = 2.5
MAX_CONSEC_FAIL = 4          # abort ถ้า fail ติดกัน (WAF tripwire) — สูงกว่า pilot กัน false abort
COOLDOWN_EVERY = 40          # พักยาวทุก N call
COOLDOWN_SEC = 20

# (label, where, budget_lo, budget_hi, จำนวนที่ดึง)
LOCAL = "(dept LIKE '%องค์การบริหารส่วน%' OR dept LIKE '%เทศบาล%')"
DOH = "dept LIKE '%ทางหลวง%'"
PLAN = [
    ("ท้องถิ่น 0.5-1ลบ", LOCAL, 0.5e6, 1e6, 22),
    ("ท้องถิ่น 1-2ลบ",   LOCAL, 1e6, 2e6, 22),
    ("ท้องถิ่น 2-3ลบ",   LOCAL, 2e6, 3e6, 22),
    ("ท้องถิ่น 3-5ลบ",   LOCAL, 3e6, 5e6, 22),
    ("ท้องถิ่น 5-7ลบ",   LOCAL, 5e6, 7e6, 18),
    ("ท้องถิ่น 7-10ลบ",  LOCAL, 7e6, 10e6, 18),
    ("กรมทางหลวง 1-5ลบ", DOH, 1e6, 5e6, 12),
    ("กรมทางหลวง 7-15ลบ", DOH, 7e6, 15e6, 12),
]


def pick_sample():
    c = sqlite3.connect(DB)
    out = []
    for label, where, lo, hi, k in PLAN:
        rows = c.execute(
            f"SELECT project_id, budget, discount_pct, dept FROM winner_history "
            f"WHERE work_type='ถนน' AND proc_type IN ({ph}) AND fiscal_year IN ('2567','2568') "
            f"AND project_id!='' AND budget>=? AND budget<? AND {where} "
            f"ORDER BY RANDOM() LIMIT ?", (*CS, lo, hi, k)).fetchall()
        for pid, bud, disc, dept in rows:
            out.append({"label": label, "project_id": pid, "budget": bud,
                        "cgd_discount": disc, "dept": dept})
    return out


def main():
    sample = pick_sample()
    print(f"PILOT: {len(sample)} งาน · throttle {SLEEP}s · abort หลัง fail {MAX_CONSEC_FAIL} ติด\n")
    results = []
    consec_fail = 0
    for i, s in enumerate(sample, 1):
        pid = s["project_id"]
        try:
            r = get_procure_result(pid)
        except Exception as e:
            r = {}
            print(f"  [{i}] {pid} EXC: {str(e)[:60]}")
        bidders = r.get("bidders") if r else None
        if not bidders:
            consec_fail += 1
            print(f"  [{i}] {pid} {s['budget']/1e6:.1f}ลบ {s['label']:18s} → ว่าง/fail ({consec_fail})")
            if consec_fail >= MAX_CONSEC_FAIL:
                print(f"\n⛔ ABORT — fail {MAX_CONSEC_FAIL} ครั้งติด (อาจโดน WAF) หยุดทันที")
                break
        else:
            consec_fail = 0
            tins = {b.get("receiveTin") or b.get("receiveNameTh") for b in bidders}
            n_bid = len(tins)
            s["n_bidders"] = n_bid
            results.append(s)
            print(f"  [{i}] {pid} {s['budget']/1e6:5.1f}ลบ {s['label']:18s} → ผู้ยื่น {n_bid} ราย (ลด {s['cgd_discount']}%)")
        if i < len(sample):
            time.sleep(SLEEP)
            if i % COOLDOWN_EVERY == 0:
                print(f"  ── cooldown {COOLDOWN_SEC}s (ผ่าน {i} call) ──")
                time.sleep(COOLDOWN_SEC)

    out = DB.parent / "bidder_count_expanded.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ saved {out} ({len(results)} สำเร็จ)")
    if results:
        from collections import defaultdict
        import statistics as st
        g = defaultdict(list)
        for r in results:
            g[r["label"]].append((r["n_bidders"], r["cgd_discount"]))
        print("\nสรุป จำนวนผู้ยื่น vs ช่วงราคา (median):")
        print(f"  {'ช่วง':20s} {'n':>3s} {'ผู้ยื่น med':>10s} {'ผู้ยื่น avg':>10s} {'ลด med':>8s}")
        for lab, v in g.items():
            bids = sorted(b for b, _ in v)
            discs = sorted(d for _, d in v if d is not None)
            print(f"  {lab:20s} {len(v):3d} {st.median(bids):10.0f} {st.mean(bids):10.1f} "
                  f"{(st.median(discs) if discs else 0):7.1f}%")


if __name__ == "__main__":
    main()
