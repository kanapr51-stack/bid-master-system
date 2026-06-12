"""_research_z_formula.py — backtest หาสูตร Z (credibility blend ตำบล↔อำเภอ) จากข้อมูลจริง
ทฤษฎี: Bühlmann credibility Z=n/(n+K), K=EPV/VHM · Fay-Herriot small-area estimation.
รัน: python scripts/_research_z_formula.py
"""
import sqlite3, statistics as st
from collections import defaultdict, Counter

c = sqlite3.connect('data/winner_history.db'); c.row_factory = sqlite3.Row

def load(disc_lo=0):
    rows = c.execute("""SELECT province, district, subdistrict, winner, discount_pct
        FROM winner_history WHERE work_type='ถนน' AND method_group='แข่งขันราคา'
        AND price_valid=1 AND discount_pct BETWEEN ? AND 60
        AND subdistrict IS NOT NULL AND subdistrict!='' AND district IS NOT NULL AND district!=''""",
        (disc_lo,)).fetchall()
    # กรอง geocode เพี้ยน
    return [r for r in rows if 'LINESTRING' not in r['subdistrict'] and 'POINT' not in r['subdistrict']]

def mean(x): return sum(x)/len(x)

def buhlmann_K(data):
    """ประมาณ K = EPV/VHM แบบ Bühlmann (กลุ่ม=ตำบล)."""
    tb = defaultdict(list)
    for r in data:
        tb[(r['province'], r['district'], r['subdistrict'])].append(r['discount_pct'])
    groups = [v for v in tb.values() if len(v) >= 2]
    # EPV = ค่าเฉลี่ยความแปรปรวนภายในกลุ่ม
    epv = mean([st.variance(g) for g in groups])
    # VHM = ความแปรปรวนของค่าเฉลี่ยกลุ่ม − EPV/n_bar  (unbiased)
    means = [mean(g) for g in groups]
    n_bar = mean([len(g) for g in groups])
    vhm = st.variance(means) - epv / n_bar
    K = epv / vhm if vhm > 0 else float('inf')
    return epv, vhm, K, len(groups)

def eff_companies(winners):
    n = len(winners); cnt = Counter(winners)
    return 1.0 / sum((m/n)**2 for m in cnt.values())

def backtest(data, ks, use_eff=False):
    """leave-one-out: predict แต่ละงานด้วย Z-blend(ตำบล,อำเภอ). คืน {k: (MAE,RMSE,n)}."""
    by_tb = defaultdict(list); by_am = defaultdict(list)
    for i, r in enumerate(data):
        tk = (r['province'], r['district'], r['subdistrict'])
        ak = (r['province'], r['district'])
        by_tb[tk].append(i); by_am[ak].append(i)
    res = {k: [] for k in ks}; res['tambon'] = []; res['amphoe'] = []
    for i, r in enumerate(data):
        tk = (r['province'], r['district'], r['subdistrict']); ak = (r['province'], r['district'])
        t_others = [data[j]['discount_pct'] for j in by_tb[tk] if j != i]
        if len(t_others) < 1: continue
        # อำเภอ "นอกตำบล" = borrow แท้
        a_others = [data[j]['discount_pct'] for j in by_am[ak]
                    if data[j]['subdistrict'] != r['subdistrict']]
        if len(a_others) < 1: continue
        t_est, a_est = mean(t_others), mean(a_others)
        n_t = eff_companies([data[j]['winner'] for j in by_tb[tk] if j != i]) if use_eff else len(t_others)
        actual = r['discount_pct']
        for k in ks:
            Z = n_t/(n_t+k)
            res[k].append(abs(Z*t_est + (1-Z)*a_est - actual))
        res['tambon'].append(abs(t_est - actual))   # Z=1
        res['amphoe'].append(abs(a_est - actual))    # Z=0
    out = {}
    for key, errs in res.items():
        if errs:
            mae = mean(errs); rmse = (mean([e*e for e in errs]))**0.5
            out[key] = (mae, rmse, len(errs))
    return out

def report(label, data, use_eff=False):
    epv, vhm, K, ng = buhlmann_K(data)
    print(f"\n{'='*60}\n{label} — {len(data)} งาน, {ng} ตำบล(>=2)")
    print(f"  EPV(ภายใน)={epv:.1f}  VHM(ระหว่าง)={vhm:.1f}  → K(ทฤษฎี)={K:.2f}")
    ks = [0.5, 1, 1.5, 2, 3, 4, 5, 7, 10, 15, 25]
    r = backtest(data, ks, use_eff=use_eff)
    print(f"  backtest ({'eff-companies' if use_eff else 'raw n'}, n={r[ks[0]][2]} งาน):")
    print(f"    {'pure ตำบล':<14} MAE={r['tambon'][0]:.2f} RMSE={r['tambon'][1]:.2f}")
    best = min(ks, key=lambda k: r[k][1])
    for k in ks:
        star = ' ★ดีสุด' if k == best else ''
        flag = ' ←K ทฤษฎี' if abs(k-K) == min(abs(kk-K) for kk in ks) else ''
        print(f"    k={k:<5} Z-blend  MAE={r[k][0]:.2f} RMSE={r[k][1]:.2f}{star}{flag}")
    print(f"    {'pure อำเภอ':<14} MAE={r['amphoe'][0]:.2f} RMSE={r['amphoe'][1]:.2f}")
    print(f"  → k empirical ดีสุด={best} · K ทฤษฎี={K:.1f}")
    return K, best

ALL = load(0)
report("ALL ถนนแข่งขัน (disc 0-60) · raw n", ALL, use_eff=False)
report("ALL ถนนแข่งขัน (disc 0-60) · eff-companies", ALL, use_eff=True)

FLOOR = load(15)   # เฉพาะงานแข่งจริง (เหนือ contested floor) = ตรงกับที่ predictor ใช้
report("ถนนแข่งจริง (disc 15-60) · raw n", FLOOR, use_eff=False)
report("ถนนแข่งจริง (disc 15-60) · eff-companies", FLOOR, use_eff=True)

# target region
TGT = [r for r in ALL if r['province'] in ('นครพนม', 'บึงกาฬ')]
report("เฉพาะ นครพนม+บึงกาฬ (disc 0-60) · raw n", TGT, use_eff=False)
