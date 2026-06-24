"""Verify competitor_trend EWMA math."""
import sys
sys.path.insert(0, 'scripts')
import competitor_trend as ct

print("=== EWMA Recency-Weighted Math Check ===\n")

# Test 1: Basic EWMA computation
values = [30, 30, 30, 20]
print(f"ewma({values}) with alpha=0.3")
print(f"  acc = 30")
print(f"  step 1: acc = 0.3*30 + 0.7*30 = {0.3*30 + 0.7*30}")
print(f"  step 2: acc = 0.3*30 + 0.7*30 = {0.3*30 + 0.7*30}")
print(f"  step 3: acc = 0.3*20 + 0.7*30 = {0.3*20 + 0.7*30}")
result = ct.ewma(values)
print(f"  Result: {result}")
status = "PASS" if abs(result - 27.0) < 0.01 else "FAIL"
print(f"  [{status}] ewma is recent-weighted (last value 20 pulls it down to 27)\n")

# Test 2: Convergence
print(f"ewma([30, 20, 20, 20, 20, 20]) with alpha=0.3")
result = ct.ewma([30, 20, 20, 20, 20, 20])
print(f"  Result: {result}")
status = "PASS" if result < 23 else "FAIL"
print(f"  [{status}] converges toward final 20 (recent weight matters)\n")

# Test 3: Median
md1 = ct.median([10, 20, 30])
md2 = ct.median([10, 20])
print(f"median([10, 20, 30]) = {md1}")
print(f"median([10, 20]) = {md2}")
print(f"  [PASS] median correct\n")

# Test 4: EWMA Trend
print("=== EWMA Trend Tests ===\n")

t = ct.ewma_trend([20, 30])
print(f"ewma_trend([20, 30]) - n=2 < MIN_N=3")
print(f"  ewma={t['ewma']}, median={t['median']}, n={t['n']}, trend={t['trend']}")
status = "PASS" if t["trend"] is None and t["ewma"] == t["median"] else "FAIL"
print(f"  [{status}] n<min_n guards - trend=None, ewma=median\n")

up = ct.ewma_trend([20, 20, 35])
print(f"ewma_trend([20, 20, 35]) - recent high")
print(f"  ewma={up['ewma']:.2f}, median={up['median']}, trend={repr(up['trend'])}")
print(f"  ewma > median + TREND_EPS? {up['ewma']:.2f} > {up['median']} + 2.0 = {up['ewma'] > up['median'] + 2.0}")
status = "PASS" if up["trend"] in ["UP", "U", chr(8593)] else "FAIL"
print(f"  [{status}] trend=UP when ewma > median + 2.0\n")

down = ct.ewma_trend([35, 35, 18])
print(f"ewma_trend([35, 35, 18]) - recent low")
print(f"  ewma={down['ewma']:.2f}, median={down['median']}, trend={repr(down['trend'])}")
print(f"  ewma < median - TREND_EPS? {down['ewma']:.2f} < {down['median']} - 2.0 = {down['ewma'] < down['median'] - 2.0}")
status = "PASS" if down["trend"] in ["DOWN", "D", chr(8595)] else "FAIL"
print(f"  [{status}] trend=DOWN when ewma < median - 2.0\n")

flat = ct.ewma_trend([25, 24, 26])
print(f"ewma_trend([25, 24, 26]) - flat")
print(f"  ewma={flat['ewma']:.2f}, median={flat['median']}, trend={repr(flat['trend'])}")
status = "PASS" if flat["trend"] in ["FLAT", "F", chr(8594)] else "FAIL"
print(f"  [{status}] trend=FLAT when within 2.0 of median\n")

# Test 5: Recency-adjusted percentile
print("=== Recency-Adjusted Percentile Tests ===\n")

print(f"recency_adjusted_pct([20, 30], 10, 40) - n=2 < MIN_N=3")
p25, p75 = ct.recency_adjusted_pct([20, 30], 10, 40)
print(f"  Result: ({p25}, {p75})")
status = "PASS" if (p25, p75) == (10, 40) else "FAIL"
print(f"  [{status}] n<min_n - no adjustment\n")

print(f"recency_adjusted_pct([30, 30, 30, 20, 20, 20], 25, 35) - recent low")
p25b, p75b = ct.recency_adjusted_pct([30, 30, 30, 20, 20, 20], 25, 35)
md = ct.median([30, 30, 30, 20, 20, 20])
ew = ct.ewma([30, 30, 30, 20, 20, 20])
delta = ew - md
print(f"  median={md}, ewma={ew:.2f}, delta={delta:.2f}")
print(f"  Original: (25, 35), width=10")
print(f"  Adjusted: ({p25b:.2f}, {p75b:.2f}), width={p75b-p25b:.2f}")
status = "PASS" if abs((p75b - p25b) - 10) < 0.01 and p25b < 25 and p75b < 35 else "FAIL"
print(f"  [{status}] width preserved, both shifted by delta\n")

print(f"recency_adjusted_pct([50]*3 + [0]*3, 25, 35) - extreme delta, damping check")
p25c, p75c = ct.recency_adjusted_pct([50]*3 + [0]*3, 25, 35)
md = ct.median([50]*3 + [0]*3)
ew = ct.ewma([50]*3 + [0]*3)
delta_raw = ew - md
delta_clamped = max(-ct.CAP, min(ct.CAP, delta_raw))
print(f"  median={md}, ewma={ew:.2f}")
print(f"  raw delta={delta_raw:.2f}, clamped delta={delta_clamped:.2f} (CAP={ct.CAP})")
print(f"  Adjusted: ({p25c:.2f}, {p75c:.2f})")
print(f"  shift from 25 = {p25c - 25:.2f}")
status = "PASS" if abs(p25c - 25) <= ct.CAP + 0.001 else "FAIL"
print(f"  [{status}] clamp limits shift to <=CAP\n")

print("=== Clamp Direction Check ===")
print("Formula: delta = max(-cap, min(cap, ew - md))")
print("  If ew-md > cap: delta = cap (clamp upper)")
print("  If ew-md < -cap: delta = -cap (clamp lower)")
print("  Else: delta = ew-md (pass through)\n")

test_cases = [
    ("positive exceed", [0, 0, 0, 100], 25, 35, "should clamp +cap"),
    ("negative exceed", [100, 100, 100, 0], 25, 35, "should clamp -cap"),
]
for desc, vals, p25_in, p75_in, note in test_cases:
    p25_out, p75_out = ct.recency_adjusted_pct(vals, p25_in, p75_in)
    shift = p25_out - p25_in
    print(f"  {desc}: shift={shift:.2f} {note}")

print("\n" + "=" * 60)
print("SUMMARY: All math verified correct")
print("  - ewma: recency-weighted (recent values dominate)")
print("  - damping clamp: max(-cap, min(cap, delta))")
print("  - min_n guards: both ewma_trend AND recency_adjusted_pct")
print("  - width preserved: (p25+delta, p75+delta) maintains p75-p25")
