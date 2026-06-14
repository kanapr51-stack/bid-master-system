"""_verify_2b.py — diagnostic: landslide_rate + top winners ต่อ scope (tuning 2B threshold). debug ชั่วคราว.
รัน: BMS_DATA_DIR=/opt/bms/data python scripts/_verify_2b.py"""
import os, sys
os.environ.setdefault("BMS_DATA_DIR", "/opt/bms/data")
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf
from collections import defaultdict
from Sebastian_Customer_DB import get_connection

SCOPES = [("นครพนม", ["ถนน"]), ("นครพนม", ["อาคาร"]), ("นครพนม", ["ก่อสร้าง"]),
          ("บึงกาฬ", ["ถนน"]), ("บึงกาฬ", ["ก่อสร้าง"])]

with get_connection() as conn:
    for prov, tok in SCOPES:
        auctions = [a for a in bf._field_auctions(conn, prov, tok) if len(a) >= 2]
        n = len(auctions)
        if not n:
            print(f"=== {prov} {tok} === n=0\n")
            continue
        gaps, appear, wins, wgap = [], defaultdict(int), defaultdict(int), defaultdict(list)
        for a in auctions:
            wi = bf._winner_idx(a)
            wname, wdisc, _ = a[wi]
            others = [d for j, (_n, d, _w) in enumerate(a) if j != wi]
            gap = wdisc - (max(others) if others else wdisc)
            gaps.append(gap)
            seen = set()
            for nm, _d, _w in a:
                if nm and nm not in seen:
                    appear[nm] += 1
                    seen.add(nm)
            if wname:
                wins[wname] += 1
                wgap[wname].append(gap)
        ls = sum(1 for g in gaps if g > bf.LANDSLIDE_GAP)
        fr = bf.analyze_field([a for a in auctions])
        print(f"=== {prov} {tok} === n={n} landslide={ls/n*100:.0f}% "
              f"(gate Tier2={bf.LANDSLIDE_RATE*100:.0f}%) → tier={fr['tier']}")
        for nm, ap in sorted(appear.items(), key=lambda x: -wins[x[0]])[:3]:
            wg = bf._median(wgap[nm]) if wgap[nm] else None
            wgs = f"{wg:.0f}" if wg is not None else "-"
            print(f"   {nm[:26]:26} ลง{ap:2} ชนะ{wins[nm]:2} (win {wins[nm]/ap*100:3.0f}%) gapmed {wgs}")
        print()
