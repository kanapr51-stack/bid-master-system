"""_analyze_bidfield.py — characterize bid_results: winner-vs-2nd gap + clustering (2B evidence).
ดู pattern "เจ้าใหญ่ขาดลอย" บ่อยแค่ไหน. รัน: BMS_DATA_DIR=/opt/bms/data python scripts/_analyze_bidfield.py"""
import sqlite3, os, statistics
from collections import defaultdict

db = os.path.join(os.environ.get("BMS_DATA_DIR", "data"), "bms_customers.db")
c = sqlite3.connect(db)
rows = c.execute("SELECT project_id, bidder_name, price_proposal, price_agree, is_winner FROM bid_results").fetchall()

byp = defaultdict(list)
for pid, name, pp, pa, isw in rows:
    bid = None
    for x in (pp, pa):                      # sealed bid = proposal (winner ใช้ agree ถ้า proposal ว่าง)
        try:
            f = float(x)
            if f > 0:
                bid = f
                break
        except (TypeError, ValueError):
            pass
    if bid:
        byp[pid].append((bid, name or "", isw))


def pct(a, p):
    if not a:
        return None
    s = sorted(a)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    cc = min(f + 1, len(s) - 1)
    return s[f] + (s[cc] - s[f]) * (k - f)


gaps, ns, examples, cluster_cv = [], [], [], []
for pid, bids in byp.items():
    if len(bids) < 3:
        continue
    bids.sort()
    ns.append(len(bids))
    low, second = bids[0][0], bids[1][0]
    gap = (second - low) / second * 100 if second > 0 else 0
    gaps.append(gap)
    pack = [b[0] for b in bids[1:]]          # กลุ่มที่เหลือ (ไม่รวมผู้ชนะ)
    if len(pack) >= 2 and statistics.mean(pack) > 0:
        cluster_cv.append(statistics.pstdev(pack) / statistics.mean(pack) * 100)
    examples.append((gap, pid, len(bids), low, second, bids[0][1]))

print(f"=== bid_results field analysis ({db}) ===")
print(f"projects(n>=3 bidders): {len(gaps)}  |  avg bidders/job: {round(statistics.mean(ns),1) if ns else 0}")
if gaps:
    print(f"winner-vs-2nd gap%: median {pct(gaps,50):.1f}  p75 {pct(gaps,75):.1f}  p90 {pct(gaps,90):.1f}")
    print(f"landslide gap>10%: {sum(1 for g in gaps if g>10)}/{len(gaps)}  "
          f"({100*sum(1 for g in gaps if g>10)/len(gaps):.0f}%)")
    print(f"landslide gap>20%: {sum(1 for g in gaps if g>20)}/{len(gaps)}  "
          f"({100*sum(1 for g in gaps if g>20)/len(gaps):.0f}%)")
if cluster_cv:
    print(f"pack clustering CV% (เกาะกลุ่มแค่ไหน): median {pct(cluster_cv,50):.1f} "
          f"(ต่ำ=เกาะกลุ่มแน่น)")
print("--- top 10 landslide (ผู้ชนะขาดลอยจากที่ 2 มากสุด) ---")
for gap, pid, n, low, second, name in sorted(examples, reverse=True)[:10]:
    print(f"  gap {gap:5.1f}% | n={n:2} | ชนะ {low:>12,.0f} | ที่2 {second:>12,.0f} | {pid} | {name[:28]}")
