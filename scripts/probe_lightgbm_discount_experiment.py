# -*- coding: utf-8 -*-
"""
Probe: LightGBM ทำนาย %ส่วนลด (discount_pct) งาน e-bidding จาก winner_history
Offline backtest เท่านั้น — ไม่แตะ pipeline จริง

เกณฑ์ตัดสิน (ตั้งไว้ก่อนรัน):
  LightGBM MAE <= 0.90 * hierarchical-median-baseline MAE บน test set (time split)
  ไม่ผ่าน = พับ

Output: data/lightgbm_discount_experiment.json + ตารางสรุปทาง stdout
"""
import json
import sqlite3
import sys

import numpy as np
import pandas as pd
import lightgbm as lgb

DB = 'data/winner_history.db'
OUT = 'data/lightgbm_discount_experiment.json'
TARGET_PROVINCES = {'นครพนม', 'บึงกาฬ'}

# ---------- load ----------
con = sqlite3.connect(DB)
df = pd.read_sql_query("""
    SELECT project_id, budget, mid_price, win_price, discount_pct,
           dept, province, district, work_type, fiscal_year
    FROM winner_history
    WHERE proc_type LIKE '%e-bidding%' AND price_valid=1 AND discount_pct IS NOT NULL
""", con)
con.close()
n_raw = len(df)

# ---------- clean ----------
# เวลาเอาจาก project_id prefix: YYMM (พ.ศ. 2 หลัก + เดือน)
df['yy'] = pd.to_numeric(df['project_id'].str[:2], errors='coerce')
df['mm'] = pd.to_numeric(df['project_id'].str[2:4], errors='coerce')
df = df[(df['yy'] >= 55) & (df['yy'] <= 70) & (df['mm'] >= 1) & (df['mm'] <= 12)]
df['ym'] = df['yy'] * 12 + df['mm']  # time index รายเดือน

df = df[(df['discount_pct'] >= 0) & (df['discount_pct'] <= 70)]
df = df[(df['budget'] > 0) & (df['mid_price'] > 0)]
df['work_type'] = df['work_type'].fillna('UNKNOWN').replace('', 'UNKNOWN')
df['district'] = df['district'].fillna('UNKNOWN').replace('', 'UNKNOWN')
n_clean = len(df)

# ---------- time split: เทรนอดีต 80% / ทดสอบอนาคต 20% ----------
df = df.sort_values(['ym', 'project_id']).reset_index(drop=True)
cut = int(len(df) * 0.8)
cut_ym = df['ym'].iloc[cut]
train = df[df['ym'] < cut_ym].copy()
test = df[df['ym'] >= cut_ym].copy()

y_tr, y_te = train['discount_pct'].values, test['discount_pct'].values

# ---------- baseline 0: global median ----------
g_med = float(np.median(y_tr))
pred_b0 = np.full(len(test), g_med)

# ---------- baseline 1: hierarchical group median (train only) ----------
MIN_N = 5
levels = [
    ['dept', 'work_type', 'province'],
    ['dept', 'work_type'],
    ['dept'],
]
maps = []
for keys in levels:
    g = train.groupby(keys)['discount_pct'].agg(['median', 'count'])
    g = g[g['count'] >= MIN_N]['median']
    maps.append((keys, g))

def hier_predict(row):
    for keys, m in maps:
        k = tuple(row[k] for k in keys) if len(keys) > 1 else row[keys[0]]
        if k in m.index:
            return m.loc[k]
    return g_med

pred_b1 = test.apply(hier_predict, axis=1).values

# ---------- LightGBM ----------
FEATS = ['log_budget', 'mid_ratio', 'ym', 'mm', 'dept', 'province', 'district', 'work_type']
CATS = ['dept', 'province', 'district', 'work_type']

for d in (train, test):
    d['log_budget'] = np.log10(d['budget'])
    d['mid_ratio'] = d['mid_price'] / d['budget']
    for c in CATS:
        d[c] = d[c].astype('category')
# ให้ test ใช้ category space เดียวกับ train
for c in CATS:
    test[c] = test[c].cat.set_categories(train[c].cat.categories)

# valid = ท้ายสุดของ train 10% (ตามเวลา) สำหรับ early stopping
v_cut = int(len(train) * 0.9)
X_tr, X_v = train[FEATS].iloc[:v_cut], train[FEATS].iloc[v_cut:]
yy_tr, yy_v = y_tr[:v_cut], y_tr[v_cut:]

params = dict(
    objective='regression_l1', metric='mae', learning_rate=0.05,
    num_leaves=63, min_child_samples=20, n_estimators=2000,
    colsample_bytree=0.8, subsample=0.8, subsample_freq=1,
    verbose=-1, seed=42,
)
model = lgb.LGBMRegressor(**params)
model.fit(X_tr, yy_tr, eval_set=[(X_v, yy_v)],
          callbacks=[lgb.early_stopping(100, verbose=False)])
pred_lgb = model.predict(test[FEATS])

# quantile models p20 / p80 (ช่วงราคาที่ควรยื่น)
q_preds = {}
for alpha in (0.2, 0.8):
    qm = lgb.LGBMRegressor(**{**params, 'objective': 'quantile', 'alpha': alpha, 'metric': 'quantile'})
    qm.fit(X_tr, yy_tr, eval_set=[(X_v, yy_v)],
           callbacks=[lgb.early_stopping(100, verbose=False)])
    q_preds[alpha] = qm.predict(test[FEATS])

# ---------- metrics ----------
def mae(y, p): return float(np.mean(np.abs(y - p)))
def medae(y, p): return float(np.median(np.abs(y - p)))

is_target = test['province'].astype(str).isin(TARGET_PROVINCES).values
results = {}
for name, pred in [('global_median', pred_b0), ('hier_median', pred_b1), ('lightgbm', pred_lgb)]:
    results[name] = {
        'mae_all': mae(y_te, pred), 'medae_all': medae(y_te, pred),
        'mae_target_prov': mae(y_te[is_target], pred[is_target]),
        'medae_target_prov': medae(y_te[is_target], pred[is_target]),
    }

cov = float(np.mean((y_te >= q_preds[0.2]) & (y_te <= q_preds[0.8])))
width = float(np.mean(q_preds[0.8] - q_preds[0.2]))

verdict_ratio = results['lightgbm']['mae_all'] / results['hier_median']['mae_all']
verdict = 'PASS' if verdict_ratio <= 0.90 else 'FAIL'

fi = sorted(zip(FEATS, model.feature_importances_.tolist()), key=lambda x: -x[1])

out = {
    'n_raw': n_raw, 'n_clean': n_clean,
    'n_train': len(train), 'n_test': len(test),
    'test_from_ym': int(cut_ym), 'n_test_target_prov': int(is_target.sum()),
    'best_iteration': model.best_iteration_,
    'results': results,
    'quantile_p20_p80_coverage': cov, 'quantile_band_width_pct': width,
    'feature_importance': fi,
    'criteria': 'lgb_mae <= 0.90 * hier_median_mae',
    'ratio': verdict_ratio, 'verdict': verdict,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# ---------- report ----------
print(f'rows raw={n_raw} clean={n_clean} train={len(train)} test={len(test)} '
      f'(test เริ่ม ym={cut_ym} ~ พ.ศ.{cut_ym//12} เดือน {cut_ym%12 or 12})')
print(f'test ใน นครพนม/บึงกาฬ: {is_target.sum()}')
print()
print(f'{"วิธี":<16}{"MAE":>8}{"MedAE":>8}{"MAE(2จว.)":>12}{"MedAE(2จว.)":>12}')
for name in ('global_median', 'hier_median', 'lightgbm'):
    r = results[name]
    print(f'{name:<16}{r["mae_all"]:>8.2f}{r["medae_all"]:>8.2f}'
          f'{r["mae_target_prov"]:>12.2f}{r["medae_target_prov"]:>12.2f}')
print()
print(f'quantile band p20-p80: coverage={cov:.1%} (เป้า ~60%), กว้างเฉลี่ย {width:.1f} จุด%')
print(f'feature importance: {fi}')
print(f'\nVERDICT: {verdict} (lgb/hier ratio = {verdict_ratio:.3f}, เกณฑ์ <= 0.90)')
print(f'saved -> {OUT}')
