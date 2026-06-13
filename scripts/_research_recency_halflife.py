"""_research_recency_halflife.py — backtest หา half-life ของ recency weighting (L3).
ถ่วงน้ำหนัก precedent ตามอายุ: weight = 0.5^((ปีงาน − ปี precedent)/half_life).
เทียบกับ no-recency (เท่ากันหมด) + recent-3-ปี (แบบ RECENT_FY ปัจจุบัน).
no-lookahead: ใช้ precedent ปี ≤ ปีงานเป้าหมายเท่านั้น.
"""
import sqlite3
from collections import defaultdict

c = sqlite3.connect('C:/Bid-Master-System/data/winner_history.db'); c.row_factory = sqlite3.Row


def load(disc_lo=0):
    rows = c.execute("""SELECT province, district, subdistrict, discount_pct, fiscal_year
        FROM winner_history WHERE work_type='ถนน' AND method_group='แข่งขันราคา'
        AND price_valid=1 AND discount_pct BETWEEN ? AND 60
        AND district IS NOT NULL AND district!='' AND fiscal_year GLOB '25[0-9][0-9]'""", (disc_lo,)).fetchall()
    return rows


def mean(x): return sum(x) / len(x)
def rmse(e): return (sum(v * v for v in e) / len(e)) ** 0.5


def backtest(data, half_lives, level='amphoe'):
    by = defaultdict(list)
    for r in data:
        key = (r['province'], r['district']) if level == 'amphoe' else (r['province'], r['district'], r['subdistrict'])
        by[key].append((int(r['fiscal_year']), r['discount_pct']))
    res = {h: [] for h in half_lives}; res['no-recency'] = []; res['recent-3yr'] = []
    for jobs in by.values():
        for i, (Yj, dj) in enumerate(jobs):
            prec = [(Yi, di) for k, (Yi, di) in enumerate(jobs) if k != i and Yi <= Yj]
            if len(prec) < 3:
                continue
            for h in half_lives:
                ws = [0.5 ** ((Yj - Yi) / h) for Yi, di in prec]
                pred = sum(w * di for w, (Yi, di) in zip(ws, prec)) / sum(ws)
                res[h].append(abs(pred - dj))
            res['no-recency'].append(abs(mean([di for _, di in prec]) - dj))
            r3 = [di for Yi, di in prec if Yj - Yi < 3]
            if r3:
                res['recent-3yr'].append(abs(mean(r3) - dj))
    return {k: (mean(e), rmse(e), len(e)) for k, e in res.items() if e}


def report(label, data, level='amphoe'):
    hls = [0.5, 1, 1.5, 2, 3, 5, 10]
    r = backtest(data, hls, level)
    print(f"\n{'='*60}\n{label} ({level}, n={r[hls[0]][2]} ทำนาย)")
    print(f"  {'no-recency (เท่ากันหมด)':<26} MAE={r['no-recency'][0]:.2f} RMSE={r['no-recency'][1]:.2f}")
    if 'recent-3yr' in r:
        print(f"  {'recent-3yr only (ปัจจุบัน)':<26} MAE={r['recent-3yr'][0]:.2f} RMSE={r['recent-3yr'][1]:.2f}")
    best = min(hls, key=lambda h: r[h][1])
    for h in hls:
        star = ' ★ดีสุด' if h == best else ''
        print(f"  half-life={h:<4} ปี        MAE={r[h][0]:.2f} RMSE={r[h][1]:.2f}{star}")
    print(f"  → half-life ดีสุด = {best} ปี")


ALL = load(0)
report("ถนนแข่งขัน disc 0-60 — อำเภอ", ALL, 'amphoe')
FLOOR = load(15)
report("ถนนแข่งจริง disc 15-60 — อำเภอ", FLOOR, 'amphoe')
report("ถนนแข่งจริง disc 15-60 — ตำบล", FLOOR, 'tambon')
