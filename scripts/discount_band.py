# -*- coding: utf-8 -*-
"""discount_band.py — แถบส่วนลด ML: "ยื่นลด ≥X% → โอกาสชนะ ~Y%" จาก LightGBM quantile.
โมเดล/meta อยู่ data/models/ (เทรนด้วย train_discount_band.py — calibration backtest
2026-07-10: bid@p80 → ชนะจริง 80.7%, bid@p50 → 50.8% บนงานทดสอบ 5,496 งาน).

fail-open ทุกทาง: ไม่มี lightgbm / ไม่มีไฟล์โมเดล / field ขาด / exception → คืน None
(หน้า portal แสดงเหมือนเดิม ไม่มีบรรทัดนี้) — ห้าม raise ใส่ caller.

dept mapping (eGP ชื่อสาขา ≠ CGD ชื่อกรมแม่): exact → longest-prefix → unseen (NaN=missing).
Backtest worst-case dept ไม่ map: 82.2%/58.2% — เพี้ยนทาง "ระวังเกิน" ปลอดภัยต่อคำเคลม.
"""
import json
import logging
import math
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

_log = logging.getLogger(__name__)

MODELS_DIR = os.environ.get(
    "BMS_MODELS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models"))

_STATE = {"loaded": False, "p50": None, "p80": None, "meta": None}


def _load():
    """โหลดโมเดล+meta ครั้งเดียว (module cache). โหลดไม่ได้ → แช่ None (ไม่ retry ทุก call)."""
    if _STATE["loaded"]:
        return
    _STATE["loaded"] = True
    try:
        import lightgbm as lgb
        with open(os.path.join(MODELS_DIR, "discount_band_meta.json"), encoding="utf-8") as f:
            _STATE["meta"] = json.load(f)
        _STATE["p50"] = lgb.Booster(model_file=os.path.join(MODELS_DIR, "discount_band_p50.txt"))
        _STATE["p80"] = lgb.Booster(model_file=os.path.join(MODELS_DIR, "discount_band_p80.txt"))
    except Exception as e:  # lightgbm ไม่มี / ไฟล์ขาด / corrupt — fail-open
        _log.warning("discount_band load failed (feature off): %s", e)
        _STATE["p50"] = _STATE["p80"] = _STATE["meta"] = None


def _map_dept(dept_name: str, vocab: list) -> str | None:
    """map ชื่อหน่วยงาน eGP → vocab เทรน (CGD): exact → longest prefix → None."""
    if not dept_name:
        return None
    if dept_name in vocab:
        return dept_name
    pref = [v for v in vocab if dept_name.startswith(v)]
    return max(pref, key=len) if pref else None


def _expected_n(meta: dict, dept, work_type, province) -> float:
    vals = {"dept": dept, "work_type": work_type, "province": province}
    for lvl in meta["lookup_levels"]:
        keys = lvl.split("|")
        if any(vals[k] is None for k in keys):
            continue
        v = meta["expected_n_lookup"][lvl].get("||".join(str(vals[k]) for k in keys))
        if v is not None:
            return v
    return meta["expected_n_lookup"]["__global__"]


def _code(value, vocab: list) -> float:
    try:
        return float(vocab.index(value))
    except ValueError:
        return math.nan


def predict_band(project_name: str, budget, dept_name: str = "",
                 province: str = "", project_id: str = "") -> dict | None:
    """คืน {disc_p50, disc_p80, price_p50, price_p80, version} หรือ None (fail-open).
    disc = %ส่วนลดจาก budget · price = budget*(1-disc/100) — ความหมาย: ยื่น ≤ price_pXX
    → โอกาสชนะ ~XX% อิงสถิติงานลักษณะเดียวกัน (calibrated backtest)."""
    try:
        budget = float(budget or 0)
        if budget <= 0 or not project_name:
            return None
        _load()
        meta = _STATE["meta"]
        if meta is None:
            return None
        from work_type_classifier import classify_work_type
        from cgd_intel import agency_market

        pid = str(project_id or "")
        if len(pid) >= 4 and pid[:4].isdigit():
            yy, mm = int(pid[:2]), int(pid[2:4])
            if not (1 <= mm <= 12):
                yy, mm = None, None
        else:
            yy, mm = None, None
        if yy is None:  # ไม่มี pid ที่ parse ได้ → ใช้เดือนปัจจุบัน (พ.ศ. 2 หลัก)
            today = date.today()
            yy, mm = (today.year + 543) % 100, today.month
        ym = yy * 12 + mm

        vocabs = meta["vocabs"]
        prov = province if province in vocabs["province"] else None
        if prov is None:   # นอก 4 จังหวัดที่มีข้อมูลเทรน — อย่าเดานอกเขต
            return None
        dept = _map_dept(dept_name or "", vocabs["dept"])
        work_type = classify_work_type(project_name)["primary"]
        agency = agency_market(dept_name) or "central"
        exp_n = _expected_n(meta, dept, work_type, prov)

        row = []
        for f in meta["feats"]:
            if f == "log_budget":
                row.append(math.log10(budget))
            elif f == "ym":
                row.append(float(ym))
            elif f == "mm":
                row.append(float(mm))
            elif f == "expected_n":
                row.append(float(exp_n))
            elif f == "dept":
                row.append(_code(dept, vocabs["dept"]) if dept else math.nan)
            elif f == "province":
                row.append(_code(prov, vocabs["province"]) if prov else math.nan)
            elif f == "work_type":
                row.append(_code(work_type, vocabs["work_type"]))
            elif f == "agency":
                row.append(_code(agency, vocabs["agency"]))
            else:
                row.append(math.nan)

        import numpy as np
        X = np.array([row], dtype=float)
        d50 = float(_STATE["p50"].predict(X)[0])
        d80 = float(_STATE["p80"].predict(X)[0])
        d50 = round(min(max(d50, 0.0), 70.0), 1)
        d80 = round(min(max(d80, d50), 70.0), 1)   # กัน quantile crossing (คนละโมเดล)
        return {   # ราคาคิดจาก % ที่ปัดแล้ว — เลขบนการ์ดต้องสอดคล้องกันเอง
            "disc_p50": d50, "disc_p80": d80,
            "price_p50": int(budget * (1 - d50 / 100)),
            "price_p80": int(budget * (1 - d80 / 100)),
            "version": meta["version"],
        }
    except Exception as e:
        _log.warning("predict_band failed (fail-open): %s", e)
        return None
