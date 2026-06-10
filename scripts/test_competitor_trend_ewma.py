"""test_competitor_trend_ewma.py — EWMA core: ewma/median/ewma_trend/recency_adjusted_pct."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import competitor_trend as ct

# ewma เรียงเก่า→ใหม่ (ตัวท้ายน้ำหนักมากสุด), α=0.3
assert ct.ewma([]) is None
assert abs(ct.ewma([30, 30, 30, 20]) - 27.0) < 0.01, ct.ewma([30, 30, 30, 20])   # 0.3*20+0.7*30
# ลู่เข้า: 30 แล้วตามด้วย 20 หลายครั้ง → เข้าใกล้ 20
assert ct.ewma([30, 20, 20, 20, 20, 20]) < 23, ct.ewma([30, 20, 20, 20, 20, 20])
assert ct.ewma([30]) == 30

# median
assert ct.median([10, 20, 30]) == 20
assert ct.median([10, 20]) == 15
assert ct.median([]) is None

# ewma_trend: n<MIN_N(3) → trend None + ewma=median
t = ct.ewma_trend([20, 30])
assert t["trend"] is None and t["n"] == 2 and t["ewma"] == t["median"], t
# recent สูงกว่า median → ↑ (ล่าสุดลดแรงขึ้น)
up = ct.ewma_trend([20, 20, 35])
assert up["trend"] == "↑", up                       # ewma 24.5 > median 20 + 2
# recent ต่ำกว่า → ↓
down = ct.ewma_trend([35, 35, 18])
assert down["trend"] == "↓", down
# ใกล้เคียง → →
flat = ct.ewma_trend([25, 24, 26])
assert flat["trend"] == "→", flat

# recency_adjusted_pct: n<MIN_N → ไม่ปรับ
assert ct.recency_adjusted_pct([20, 30], 10, 40) == (10, 40)
# recent ต่ำกว่า median → delta ลบ → เลื่อน range ลง (ลด% น้อยลง = ราคาสูงขึ้น)
p25b, p75b = ct.recency_adjusted_pct([30, 30, 30, 20, 20, 20], 25, 35)
assert p25b < 25 and p75b < 35 and abs((p75b - p25b) - 10) < 0.01, (p25b, p75b)   # คงความกว้าง 10
# damping: delta ถูก clamp ที่ CAP — series สุดโต่งไม่เลื่อนเกิน cap
p25c, p75c = ct.recency_adjusted_pct([50]*3 + [0]*3, 25, 35)   # ewma-median ห่างมาก
assert abs((p25c - 25)) <= ct.CAP + 0.001, (p25c, ct.CAP)

print("OK test_competitor_trend_ewma")
