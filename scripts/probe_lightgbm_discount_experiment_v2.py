# -*- coding: utf-8 -*-
"""
Probe v2: LightGBM ทำนาย %ส่วนลด + feature จำนวนผู้ยื่น (จาก bid_results VPS)
ต่อจาก v1 (FAIL ratio 0.929) — เพิ่มสิ่งที่ v1 ขาด: ความเข้มการแข่งขัน

เกณฑ์เดิม: lgb MAE <= 0.90 * hier-median MAE บน test (time split)
2 variant:
  - ceiling:    n_bidders จริง (leak — รู้หลังเปิดซอง) = เพดานความแม่นถ้ารู้การแข่งขัน
  - deployable: expected_n จากประวัติ train (dept×work_type×province → dept×work_type → dept)

Output: data/lightgbm_discount_experiment_v2.json
"""
import json
import sqlite3

import numpy as np
import pandas as pd
import lightgbm as lgb

DB = 'data/winner_history.db'
NBID_CSV = 'data/_backfill_home/vps_n_bidders.csv'
OUT = 'data/lightgbm_discount_experiment_v2.json'
TARGET_PROVINCES = {'นครพนม', 'บึงกาฬ'}

# ---------- load (เหมือน v1) ----------
con = sqlite3.connect(DB)
df = pd.read_sql_query("""
    SELECT project_id, budget, mid_price, win_price, discount_pct,
           dept, province, district, work_type, fiscal_year
    FROM winner_history
    WHERE proc_type LIKE '%e-bidding%' AND price_valid=1 AND discount_pct IS NOT NULL
""", con)
con.close()

nb = pd.read_csv(NBID_CSV, dtype={'project_id': str})
df = df.merge(nb, on='project_id', how='left')

df['yy'] = pd.to_numeric(df['project_id'].str[:2], errors='coerce')
df['mm'] = pd.to_numeric(df['project_id'].str[2:4], errors='coerce')
df = df[(df['yy'] >= 55) & (df['yy'] <= 70) & (df['mm'] >= 1) & (df['mm'] <= 12)]
df['ym'] = df['yy'] * 12 + df['mm']
df = df[(df['discount_pct'] >= 0) & (df['discount_pct'] <= 70)]
df = df[(df['budget'] > 0) & (df['mid_price'] > 0)]
df['work_type'] = df['work_type'].fillna('UNKNOWN').replace('', 'UNKNOWN')
df['district'] = df['district'].fillna('UNKNOWN').replace('', 'UNKNOWN')

n_total = len(df)
n_with_nb = int(df['n_bidders'].notna().sum())

# ---------- time split เหมือน v1 ----------
df = df.sort_values(['ym', 'project_id']).reset_index(drop=True)
cut = int(len(df) * 0.8)
cut_ym = df['ym'].iloc[cut]
train = df[df['ym'] < cut_ym].copy()
test = df[df['ym'] >= cut_ym].copy()
y_tr, y_te = train['discount_pct'].values, test['discount_pct'].values

# ---------- baseline hier median (เหมือน v1) ----------
g_med = float(np.median(y_tr))
MIN_N = 5
levels = [['dept', 'work_type', 'province'], ['dept', 'work_type'], ['dept']]
maps = []
for keys in levels:
    g = train.groupby(keys)['discount_pct'].agg(['median', 'count'])
    maps.append((keys, g[g['count'] >= MIN_N]['median']))

def hier_predict(row):
    for keys, m in maps:
        k = tuple(row[k] for k in keys) if len(keys) > 1 else row[keys[0]]
        if k in m.index:
            return m.loc[k]
    return g_med

pred_b1 = test.apply(hier_predict, axis=1).values

# ---------- expected_n (deployable — จาก train เท่านั้น) ----------
nmaps = []
tr_nb = train[train['n_bidders'].notna()]
for keys in levels:
    g = tr_nb.groupby(keys)['n_bidders'].agg(['median', 'count'])
    nmaps.append((keys, g[g['count'] >= MIN_N]['median']))
n_global = float(tr_nb['n_bidders'].median())

def expected_n(row):
    for keys, m in nmaps:
        k = tuple(row[k] for k in keys) if len(keys) > 1 else row[keys[0]]
        if k in m.index:
            return m.loc[k]
    return n_global

for d in (train, test):
    d['expected_n'] = d.apply(expected_n, axis=1)
    d['log_budget'] = np.log10(d['budget'])
    d['mid_ratio'] = d['mid_price'] / d['budget']

CATS = ['dept', 'province', 'district', 'work_type']
for c in CATS:
    train[c] = train[c].astype('category')
    test[c] = test[c].astype('category').cat.set_categories(train[c].cat.categories)

BASE_FEATS = ['log_budget', 'mid_ratio', 'ym', 'mm', 'dept', 'province', 'district', 'work_type']
params = dict(
    objective='regression_l1', metric='mae', learning_rate=0.05,
    num_leaves=63, min_child_samples=20, n_estimators=2000,
    colsample_bytree=0.8, subsample=0.8, subsample_freq=1,
    verbose=-1, seed=42,
)

v_cut = int(len(train) * 0.9)

def fit_predict(feats):
    X_tr, X_v = train[feats].iloc[:v_cut], train[feats].iloc[v_cut:]
    m = lgb.LGBMRegressor(**params)
    m.fit(X_tr, y_tr[:v_cut], eval_set=[(X_v, y_tr[v_cut:])],
          callbacks=[lgb.early_stopping(100, verbose=False)])
    return m, m.predict(test[feats])

model_v1, pred_v1 = fit_predict(BASE_FEATS)                       # reproduce v1
model_dep, pred_dep = fit_predict(BASE_FEATS + ['expected_n'])    # deployable
model_ceil, pred_ceil = fit_predict(BASE_FEATS + ['n_bidders'])   # ceiling (leak)

# ---------- metrics ----------
def mae(y, p): return float(np.mean(np.abs(y - p)))
def medae(y, p): return float(np.median(np.abs(y - p)))

is_target = test['province'].astype(str).isin(TARGET_PROVINCES).values
results = {}
for name, pred in [('hier_median', pred_b1), ('lgb_v1', pred_v1),
                   ('lgb_deployable', pred_dep), ('lgb_ceiling', pred_ceil)]:
    results[name] = {
        'mae_all': mae(y_te, pred), 'medae_all': medae(y_te, pred),
        'mae_target_prov': mae(y_te[is_target], pred[is_target]),
    }

ratio_dep = results['lgb_deployable']['mae_all'] / results['hier_median']['mae_all']
ratio_ceil = results['lgb_ceiling']['mae_all'] / results['hier_median']['mae_all']
verdict = 'PASS' if ratio_dep <= 0.90 else 'FAIL'

fi_dep = sorted(zip(BASE_FEATS + ['expected_n'], model_dep.feature_importances_.tolist()), key=lambda x: -x[1])
fi_ceil = sorted(zip(BASE_FEATS + ['n_bidders'], model_ceil.feature_importances_.tolist()), key=lambda x: -x[1])

out = {
    'n_rows': n_total, 'n_with_n_bidders': n_with_nb,
    'n_train': len(train), 'n_test': len(test), 'test_from_ym': int(cut_ym),
    'results': results,
    'ratio_deployable': ratio_dep, 'ratio_ceiling': ratio_ceil,
    'criteria': 'lgb_deployable_mae <= 0.90 * hier_median_mae',
    'verdict': verdict,
    'fi_deployable': fi_dep, 'fi_ceiling': fi_ceil,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f'rows={n_total} (มี n_bidders {n_with_nb} = {n_with_nb/n_total:.1%}) train={len(train)} test={len(test)}')
print()
print(f'{"วิธี":<18}{"MAE":>8}{"MedAE":>8}{"MAE(2จว.)":>12}')
for name in ('hier_median', 'lgb_v1', 'lgb_deployable', 'lgb_ceiling'):
    r = results[name]
    print(f'{name:<18}{r["mae_all"]:>8.2f}{r["medae_all"]:>8.2f}{r["mae_target_prov"]:>12.2f}')
print()
print(f'ratio deployable={ratio_dep:.3f} | ceiling={ratio_ceil:.3f} (เกณฑ์ <= 0.90)')
print(f'FI deployable: {fi_dep[:5]}')
print(f'FI ceiling:    {fi_ceil[:5]}')
print(f'\nVERDICT (deployable): {verdict}')
print(f'saved -> {OUT}')
