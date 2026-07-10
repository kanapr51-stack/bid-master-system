# -*- coding: utf-8 -*-
"""train_discount_band.py — เทรน LightGBM quantile (p50/p80) ทำนาย %ส่วนลดผู้ชนะ e-bidding
จาก winner_history + n_bidders (bid_results) → export model + meta ลง data/models/
สำหรับบรรทัด "ยื่นลด ≥X% → โอกาสชนะ ~Y%" บนหน้างาน Board B (ดู progress_log N+194/195).

หลักฐาน backtest 2026-07-10: calibration bid@p80 → ชนะจริง 80.7%, bid@p50 → 50.8%
(feature ชุด serve-time; worst-case dept ไม่ map → 82.2%/58.2% เพี้ยนทางระวังเกิน = ปลอดภัย)

วิธีเทรน: หา best_iter ด้วย time-tail valid 10% → refit ทั้งก้อนด้วย iter นั้น
Categorical = manual integer code (vocab แช่ใน meta — กัน train/serve skew, unseen → NaN=missing)

รัน: python -X utf8 scripts/train_discount_band.py  (ต้องมี data/winner_history.db +
     data/_backfill_home/vps_n_bidders.csv จาก export ล่าสุด)
"""
import json
import os
import sqlite3
import sys
from datetime import date

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, os.path.dirname(__file__))
from cgd_intel import agency_market

DB = 'data/winner_history.db'
NBID_CSV = 'data/_backfill_home/vps_n_bidders.csv'
OUT_DIR = 'data/models'
CAT_COLS = ('dept', 'province', 'work_type', 'agency')
NUM_COLS = ('log_budget', 'ym', 'mm', 'expected_n')
FEATS = list(NUM_COLS) + list(CAT_COLS)
MIN_N = 5
LOOKUP_LEVELS = (('dept', 'work_type', 'province'), ('dept', 'work_type'), ('dept',))
PARAMS = dict(learning_rate=0.05, num_leaves=63, min_child_samples=20,
              colsample_bytree=0.8, subsample=0.8, subsample_freq=1,
              verbose=-1, seed=42)


def load_dataset() -> pd.DataFrame:
    con = sqlite3.connect(DB)
    df = pd.read_sql_query("""
        SELECT project_id, budget, discount_pct, dept, province, work_type
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
    df = df[(df['discount_pct'] >= 0) & (df['discount_pct'] <= 70) & (df['budget'] > 0)]
    df['work_type'] = df['work_type'].fillna('UNKNOWN').replace('', 'UNKNOWN')
    df['agency'] = df['dept'].map(lambda d: agency_market(d) or 'central')
    df['log_budget'] = np.log10(df['budget'])
    return df.sort_values(['ym', 'project_id']).reset_index(drop=True)


def build_expected_n_lookup(df: pd.DataFrame) -> dict:
    """median จำนวนผู้ยื่นต่อ scope (hierarchical fallback) — key แบน 'a||b||c'."""
    has_n = df[df['n_bidders'].notna()]
    lookup = {}
    for keys in LOOKUP_LEVELS:
        g = has_n.groupby(list(keys))['n_bidders'].agg(['median', 'count'])
        g = g[g['count'] >= MIN_N]['median']
        level = {}
        for k, v in g.items():
            flat = '||'.join(k) if isinstance(k, tuple) else k
            level[flat] = float(v)
        lookup['|'.join(keys)] = level
    lookup['__global__'] = float(has_n['n_bidders'].median())
    return lookup


def apply_expected_n(df: pd.DataFrame, lookup: dict) -> pd.Series:
    def one(row):
        for keys in LOOKUP_LEVELS:
            flat = '||'.join(str(row[k]) for k in keys)
            v = lookup['|'.join(keys)].get(flat)
            if v is not None:
                return v
        return lookup['__global__']
    return df.apply(one, axis=1)


def encode_cats(df: pd.DataFrame, vocabs: dict) -> pd.DataFrame:
    """คืน df ที่ cat cols เป็น float code (unseen/ว่าง → NaN = missing สำหรับ LightGBM)."""
    out = df.copy()
    for c in CAT_COLS:
        code = {v: i for i, v in enumerate(vocabs[c])}
        out[c] = out[c].map(code).astype(float)
    return out


def train_quantile(X_all, y_all, alpha: float, v_cut: int) -> lgb.Booster:
    """หา best_iter ด้วย tail valid แล้ว refit ทั้งก้อน — ไม่ทิ้งข้อมูลล่าสุด."""
    probe = lgb.LGBMRegressor(objective='quantile', alpha=alpha, metric='quantile',
                              n_estimators=2000, **PARAMS)
    probe.fit(X_all.iloc[:v_cut], y_all[:v_cut],
              eval_set=[(X_all.iloc[v_cut:], y_all[v_cut:])],
              callbacks=[lgb.early_stopping(100, verbose=False)])
    best = probe.best_iteration_ or 200
    final = lgb.LGBMRegressor(objective='quantile', alpha=alpha, metric='quantile',
                              n_estimators=best, **PARAMS)
    final.fit(X_all, y_all, categorical_feature=[FEATS.index(c) for c in CAT_COLS])
    return final.booster_, best


def main():
    df = load_dataset()
    lookup = build_expected_n_lookup(df)
    df['expected_n'] = apply_expected_n(df, lookup)
    vocabs = {c: sorted(df[c].dropna().astype(str).unique().tolist()) for c in CAT_COLS}
    enc = encode_cats(df, vocabs)
    X, y = enc[FEATS], enc['discount_pct'].values
    v_cut = int(len(X) * 0.9)

    os.makedirs(OUT_DIR, exist_ok=True)
    version = f"band-{date.today().isoformat()}"
    iters = {}
    for alpha, name in ((0.5, 'p50'), (0.8, 'p80')):
        booster, best = train_quantile(X, y, alpha, v_cut)
        booster.save_model(os.path.join(OUT_DIR, f'discount_band_{name}.txt'))
        iters[name] = best
        print(f'{name}: best_iter={best} → saved discount_band_{name}.txt')

    meta = {
        'version': version,
        'feats': FEATS, 'cat_cols': list(CAT_COLS),
        'vocabs': vocabs,
        'expected_n_lookup': lookup,
        'lookup_levels': ['|'.join(k) for k in LOOKUP_LEVELS],
        'n_train': len(X), 'best_iters': iters,
        'calibration_backtest': {'win_at_p80': 0.807, 'win_at_p50': 0.508,
                                 'test_n': 5496, 'date': '2026-07-10'},
    }
    with open(os.path.join(OUT_DIR, 'discount_band_meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    sizes = {f: os.path.getsize(os.path.join(OUT_DIR, f)) // 1024
             for f in os.listdir(OUT_DIR)}
    print(f'meta saved | version={version} | n_train={len(X)} | sizes(KB)={sizes}')


if __name__ == '__main__':
    main()
