"""competitor_trend.py — recency-weighted (EWMA) discount trend จาก cgd_winners + bid_results.
ใช้ปรับ prediction (area, recency-adjusted percentile) + เทรนด์ส่วนลดต่อบริษัท (Round 2).
ดู docs/superpowers/specs/2026-06-10-competitor-trend-adaptive-discount-design.md"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ALPHA = 0.3        # EWMA recency weight (ปานกลาง — ล่าสุดมากสุด แต่ไม่ไล่ noise)
MIN_N = 3          # < นี้ → ไม่ปรับ/ไม่โชว์เทรนด์ (data น้อย)
CAP = 8.0          # damping: เลื่อน percentile ได้ ≤ CAP จุด/รอบ (กัน 1 ฟลุ๊คดันแรง)
TREND_EPS = 2.0    # เกณฑ์ ↑/↓


def ewma(values, alpha=ALPHA):
    """recency-weighted average. values เรียง เก่า→ใหม่ (ตัวท้ายน้ำหนักมากสุด). None ถ้าว่าง."""
    if not values:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return acc


def median(values):
    """มัธยฐาน. None ถ้าว่าง."""
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def ewma_trend(values, alpha=ALPHA, min_n=MIN_N):
    """คืน {ewma, median, n, trend}. trend ∈ {↑,↓,→,None}. n<min_n → ewma=median, trend=None."""
    n = len(values)
    md = median(values)
    if n < min_n:
        return {"ewma": md, "median": md, "n": n, "trend": None}
    ew = ewma(values, alpha)
    if ew > md + TREND_EPS:
        tr = "↑"
    elif ew < md - TREND_EPS:
        tr = "↓"
    else:
        tr = "→"
    return {"ewma": ew, "median": md, "n": n, "trend": tr}


def recency_adjusted_pct(values, p25, p75, alpha=ALPHA, min_n=MIN_N, cap=CAP):
    """เลื่อน (p25,p75) ตาม EWMA-median delta (damped ≤cap, คงความกว้าง). n<min_n → ไม่ปรับ."""
    if len(values) < min_n or p25 is None or p75 is None:
        return p25, p75
    md = median(values)
    ew = ewma(values, alpha)
    delta = max(-cap, min(cap, ew - md))
    return p25 + delta, p75 + delta
