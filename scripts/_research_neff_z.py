"""_research_neff_z.py — backtest: Z ควรใช้ n ดิบ หรือ n_eff (recency-weighted) ?
n_eff = ผลรวมน้ำหนักความสดของงานในตำบล. สมมติฐาน: ตำบล all-old → n_eff≈0 → Z≈0 → อำเภอล้วน.
no-lookahead. k=3 (จาก Z research). half-life=1.
"""
import sqlite3
from collections import defaultdict

c = sqlite3.connect('C:/Bid-Master-System/data/winner_history.db'); c.row_factory = sqlite3.Row
K = 3


def load(disc_lo=15):
    rows = c.execute("""SELECT province, district, subdistrict, discount_pct, fiscal_year
        FROM winner_history WHERE work_type='ถนน' AND method_group='แข่งขันราคา'
        AND price_valid=1 AND discount_pct BETWEEN ? AND 60
        AND subdistrict IS NOT NULL AND subdistrict!='' AND district IS NOT NULL AND district!=''
        AND fiscal_year GLOB '25[0-9][0-9]'""", (disc_lo,)).fetchall()
    return [r for r in rows if 'LINESTRING' not in r['subdistrict'] and 'POINT' not in r['subdistrict']]


def recw(age, hl=1): return 1.0 if age <= 0 else 0.5 ** (age / hl)
def mean(x): return sum(x) / len(x)
def rmse(e): return (sum(v * v for v in e) / len(e)) ** 0.5


def backtest(data):
    by_am = defaultdict(list)
    for r in data:
        by_am[(r['province'], r['district'])].append((int(r['fiscal_year']), r['discount_pct'], r['subdistrict']))
    res = {'raw n': [], 'n_eff': [], 'pure ตำบล': [], 'pure อำเภอ': []}
    stale = {'raw n': [], 'n_eff': []}
    fresh = {'raw n': [], 'n_eff': []}
    for jobs in by_am.values():
        for i, (Yj, dj, tbj) in enumerate(jobs):
            tp = [(Yi, di) for k2, (Yi, di, tb) in enumerate(jobs) if k2 != i and tb == tbj and Yi <= Yj]
            ap = [(Yi, di) for k2, (Yi, di, tb) in enumerate(jobs) if k2 != i and tb != tbj and Yi <= Yj]
            if not tp or len(ap) < 2:
                continue
            def west(p):
                ws = [recw(Yj - Yi) for Yi, _ in p]; return sum(w * d for w, (_, d) in zip(ws, p)) / sum(ws)
            t_est, a_est = west(tp), west(ap)
            n_raw = len(tp)
            n_eff = sum(recw(Yj - Yi) for Yi, _ in tp)
            Zr, Ze = n_raw / (n_raw + K), n_eff / (n_eff + K)
            er = abs(Zr * t_est + (1 - Zr) * a_est - dj)
            ee = abs(Ze * t_est + (1 - Ze) * a_est - dj)
            res['raw n'].append(er); res['n_eff'].append(ee)
            res['pure ตำบล'].append(abs(t_est - dj)); res['pure อำเภอ'].append(abs(a_est - dj))
            if Yj - max(Yi for Yi, _ in tp) >= 3:    # ตำบล stale (งานใหม่สุดเก่า ≥3 ปี)
                stale['raw n'].append(er); stale['n_eff'].append(ee)
            else:
                fresh['raw n'].append(er); fresh['n_eff'].append(ee)
    return res, stale, fresh


for lo, lbl in [(15, 'แข่งจริง 15-60'), (0, 'ทั้งหมด 0-60')]:
    res, stale, fresh = backtest(load(lo))
    print(f"\n{'='*58}\n{lbl} (n={len(res['raw n'])} ทำนาย)")
    for k, e in res.items():
        print(f"  {k:<12} MAE={mean(e):.2f}  RMSE={rmse(e):.2f}")
    print(f"  --- ตำบล STALE ({len(stale['raw n'])} เคส, ที่ n_eff ควรช่วย) ---")
    for k in ('raw n', 'n_eff'):
        if stale[k]: print(f"  {k:<12} MAE={mean(stale[k]):.2f}  RMSE={rmse(stale[k]):.2f}")
    print(f"  --- ตำบล FRESH ({len(fresh['raw n'])} เคส, ไม่ควรต่าง) ---")
    for k in ('raw n', 'n_eff'):
        if fresh[k]: print(f"  {k:<12} MAE={mean(fresh[k]):.2f}  RMSE={rmse(fresh[k]):.2f}")
