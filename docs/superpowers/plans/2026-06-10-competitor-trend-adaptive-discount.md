# Competitor Trend — Recency-Weighted Adaptive Discount (Sub-2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ทำให้คาดราคา (prediction) ปรับตามผลจริงแบบ recency-weighted (EWMA, นุ่มนวล) + โชว์เทรนด์ส่วนลดต่อบริษัทแบบ recency ใน Round 2 — โดยรวมข้อมูล `cgd_winners` (ประวัติ) + `bid_results` (ที่เรา observe).

**Architecture:** โมดูลใหม่ `competitor_trend.py` = EWMA core + series builders (รวม 2 แหล่ง เรียงเวลา). consumer 2 จุด: `cgd_intel._build_intel` (เลื่อน percentile ตาม EWMA-delta ก่อนคาดราคา) + `cgd_intel.analyze_bidders` (เทรนด์ต่อบริษัทจาก EWMA).

**Tech Stack:** Python 3, sqlite3 (stdlib). test = standalone `python scripts\test_X.py` (exit 0 + print OK = ผ่าน). VPS ไม่มี sqlite3 CLI → sanity ใช้ `python3 -c`.

**Spec:** `docs/superpowers/specs/2026-06-10-competitor-trend-adaptive-discount-design.md`

**Environment notes:**
- test DB: `:memory:` หรือ env `BMS_DATA_DIR`+`BMS_DB_PATH` (ตาม convention `test_bms_follow.py`)
- ❌ Task 5 deploy: confirm กัญจน์ก่อน `git push` (CLAUDE.md)
- implementation log = N+113

---

### Task 1: `competitor_trend.py` — EWMA core (pure)

**Files:**
- Create: `scripts/competitor_trend.py`
- Test: `scripts/test_competitor_trend_ewma.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_competitor_trend_ewma.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_competitor_trend_ewma.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'competitor_trend'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/competitor_trend.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_competitor_trend_ewma.py`
Expected: `OK test_competitor_trend_ewma`

- [ ] **Step 5: Commit**

```bash
git add scripts/competitor_trend.py scripts/test_competitor_trend_ewma.py
git commit -m "feat(trend): competitor_trend EWMA core — ewma/ewma_trend/recency_adjusted_pct (Sub-2a)"
```
ต่อท้าย commit body: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 2: `competitor_trend.py` — series builders (cgd_winners + bid_results)

**Files:**
- Modify: `scripts/competitor_trend.py`
- Test: `scripts/test_competitor_trend_series.py`

`area_win_series` = ส่วนลด**ผู้ชนะ**ในพื้นที่ (สำหรับ prediction). `company_series` = ส่วนลด**ของบริษัท** (สำหรับเทรนด์). ทั้งคู่เรียง **เก่า→ใหม่** (cgd_winners.announce_date + bid_results.fetched_at). reuse constants จาก `cgd_intel`.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_competitor_trend_series.py`:

```python
"""test_competitor_trend_series.py — area_win_series + company_series (cgd_winners + bid_results)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import competitor_trend as ct

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        project_name TEXT, winner TEXT, win_price INTEGER, discount_pct REAL,
        announce_date TEXT, fiscal_year TEXT, proc_type TEXT, district TEXT, subdistrict TEXT)""")
    c.execute("""CREATE TABLE bid_results (project_id TEXT, bidder_name TEXT, bidder_tin TEXT,
        price_proposal TEXT, price_agree TEXT, is_winner INTEGER, result_flag TEXT, fetched_at TEXT,
        PRIMARY KEY(project_id, bidder_tin))""")
    c.execute("""CREATE TABLE projects_seen (project_id TEXT PRIMARY KEY, province TEXT, budget INTEGER)""")
    # cgd_winners: ถนนโพนทอง — หจก.X ชนะ 2 งาน (ลด 20 เก่า, 24 ใหม่), หจก.Y ลด 30
    w = [("w1", "ถนน คสล. โพนทอง", "หจก.X", 20.0, "2566-01-01", "บ้านแพง", "โพนทอง"),
         ("w2", "ถนน คสล. โพนทอง", "หจก.X", 24.0, "2567-06-01", "บ้านแพง", "โพนทอง"),
         ("w3", "ถนน คสล. โพนทอง", "หจก.Y", 30.0, "2567-01-01", "บ้านแพง", "โพนทอง")]
    for pid, nm, win, disc, ad, dist, sub in w:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,announce_date,fiscal_year,proc_type,district,subdistrict) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", nm, win, 100000, disc, ad, "256"+ad[3], EB, dist, sub))
    # bid_results: หจก.X เสนอราคางานใหม่ (price_proposal 700000 บน budget 1,000,000 = ลด 30) ล่าสุด
    c.execute("INSERT INTO projects_seen VALUES ('b1','นครพนม',1000000)")
    c.execute("INSERT INTO bid_results VALUES ('b1','หจก.X','T1','700000','700000',1,'P','2568-06-01')")
    c.commit(); return c


def test_area_win_series():
    c = _conn()
    s = ct.area_win_series(c, "นครพนม", ["ถนน"], subdistrict="โพนทอง", district="บ้านแพง")
    # winner discounts เรียงเวลา: w1(20,2566) w3(30,2567-01) w2(24,2567-06) b1(30,2568) → ตัวท้ายใหม่สุด
    assert s[-1] == 30.0, s                      # bid_results winner ล่าสุด
    assert s[0] == 20.0, s                       # cgd เก่าสุด
    assert len(s) == 4, s                        # 3 cgd winners + 1 bid_result winner
    print("✅ area_win_series (cgd_winners + bid_results winner, เรียงเวลา)")


def test_company_series():
    c = _conn()
    discs, scope = ct.company_series(c, "นครพนม", ["ถนน"], "หจก.X", subdistrict="โพนทอง", district="บ้านแพง")
    # หจก.X: cgd win 20(2566),24(2567) + bid_result เสนอ 30(2568) → เรียง [20,24,30]
    assert discs == [20.0, 24.0, 30.0], discs
    assert scope == "ตำบล", scope
    # บริษัทไม่มีในตำบล → fallback จังหวัด (Y มีแต่ในโพนทองด้วย — ใช้บริษัทใหม่)
    d2, sc2 = ct.company_series(c, "นครพนม", ["ถนน"], "หจก.ใหม่", subdistrict="โพนทอง", district="บ้านแพง")
    assert d2 == [] and sc2 == "", (d2, sc2)
    print("✅ company_series (cgd win + bid proposal, scope ตำบล→จังหวัด)")


if __name__ == "__main__":
    test_area_win_series()
    test_company_series()
    print("\n✅ ALL test_competitor_trend_series PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_competitor_trend_series.py`
Expected: FAIL — `AttributeError: module 'competitor_trend' has no attribute 'area_win_series'`

- [ ] **Step 3: Implement series builders**

Append to `scripts/competitor_trend.py`:

```python
import cgd_intel as ci


def _area_where(province, tokens, subdistrict, district, subtype):
    """ประกอบ WHERE + params สำหรับ cgd_winners (สอดคล้อง cgd_intel._fetch + announce_date)."""
    fy_ph = ",".join("?" for _ in ci.RECENT_FY)
    pt_ph = ",".join("?" for _ in ci.COMPETITIVE_SET)
    like = " OR ".join("project_name LIKE ?" for _ in tokens)
    where = ["province=?", "win_price>0", "discount_pct IS NOT NULL",
             f"fiscal_year IN ({fy_ph})", f"proc_type IN ({pt_ph})", f"({like})"]
    params = [province, *ci.RECENT_FY, *ci.COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    if subdistrict is not None:
        where.append("subdistrict=?"); params.append(subdistrict)
    if district is not None:
        where.append("district=?"); params.append(district)
    if subtype == "asphalt":
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in ci._ASPHALT_KW) + ")")
        params += [f"%{k}%" for k in ci._ASPHALT_KW]
    elif subtype == "concrete":
        where.append("(" + " OR ".join("project_name LIKE ?" for _ in ci._CONCRETE_KW) + ")")
        params += [f"%{k}%" for k in ci._CONCRETE_KW]
        where.append("NOT (" + " OR ".join("project_name LIKE ?" for _ in ci._ASPHALT_KW) + ")")
        params += [f"%{k}%" for k in ci._ASPHALT_KW]
    return " AND ".join(where), params


def _cgd_rows(conn, province, tokens, subdistrict, district, subtype, winner=None):
    """(announce_date, discount_pct, winner) จาก cgd_winners. winner!=None → filter บริษัท."""
    where, params = _area_where(province, tokens, subdistrict, district, subtype)
    if winner is not None:
        where += " AND winner=?"; params.append(winner)
    try:
        cur = conn.execute(f"SELECT announce_date, discount_pct, winner FROM cgd_winners WHERE {where}", params)
        return [(r[0] or "", r[1], r[2]) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def _bidresult_rows(conn, province, bidder=None, winner_only=False):
    """ส่วนลดจาก bid_results + budget (projects_seen, province scope). คืน [(fetched_at, disc)].
    bidder!=None → เฉพาะบริษัทนั้น (ใช้ price_proposal). winner_only → is_winner=1 (ใช้ price_agree)."""
    col = "price_agree" if winner_only else "price_proposal"
    where = ["ps.province=?", f"b.{col} IS NOT NULL", f"b.{col} != ''", "ps.budget>0"]
    params = [province]
    if winner_only:
        where.append("b.is_winner=1")
    if bidder is not None:
        where.append("b.bidder_name=?"); params.append(bidder)
    try:
        cur = conn.execute(
            f"SELECT b.fetched_at, b.{col}, ps.budget FROM bid_results b "
            f"JOIN projects_seen ps ON ps.project_id=b.project_id WHERE " + " AND ".join(where), params)
    except sqlite3.OperationalError:
        return []
    out = []
    for fa, price, budget in cur.fetchall():
        try:
            p, bud = float(price), float(budget or 0)
            if bud > 0 and p > 0:
                out.append((fa or "", (1 - p / bud) * 100.0))
        except (TypeError, ValueError):
            pass
    return out


def area_win_series(conn, province, tokens, subdistrict=None, district=None, subtype=None):
    """ส่วนลดผู้ชนะในพื้นที่ เรียงเก่า→ใหม่ (cgd_winners + bid_results winner). คืน list[float]."""
    rows = [(d, disc) for d, disc, _w in _cgd_rows(conn, province, tokens, subdistrict, district, subtype)
            if disc is not None]
    rows += _bidresult_rows(conn, province, winner_only=True)
    rows.sort(key=lambda x: x[0])
    return [disc for _d, disc in rows]


def company_series(conn, province, tokens, company, subdistrict=None, district=None, subtype=None):
    """ส่วนลดของบริษัท เรียงเก่า→ใหม่ (cgd_winners win + bid_results proposal). ตำบลก่อน→จังหวัด.
    คืน (list[float], scope) — scope ∈ {'ตำบล','นอกตำบล',''}."""
    def _series(sub, dist):
        rows = [(d, disc) for d, disc, _w in
                _cgd_rows(conn, province, tokens, sub, dist, subtype, winner=company) if disc is not None]
        rows += _bidresult_rows(conn, province, bidder=company)
        rows.sort(key=lambda x: x[0])
        return [disc for _d, disc in rows]
    if subdistrict is not None:
        s = _series(subdistrict, district)
        if s:
            return s, "ตำบล"
    s = _series(None, None)
    return (s, "นอกตำบล") if s else ([], "")
```

> หมายเหตุ: `company_series` รวม bid_results (province scope) ในทั้ง 2 ระดับ — bid_results sparse ตอนนี้ จึงแทบไม่กระทบ. tambon-scope ของ bid_results = approximate (มาจาก cgd_winners เป็นหลัก) ตาม spec.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_competitor_trend_series.py`
Expected: `✅ ALL test_competitor_trend_series PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/competitor_trend.py scripts/test_competitor_trend_series.py
git commit -m "feat(trend): area_win_series + company_series (cgd_winners + bid_results, เรียงเวลา)"
```
ต่อท้าย: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 3: prediction integration — recency-adjust percentile ใน `_build_intel`

**Files:**
- Modify: `scripts/cgd_intel.py` (`_build_intel` ~line 304-347)
- Test: `scripts/test_trend_prediction.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/test_trend_prediction.py`:

```python
"""test_trend_prediction.py — _build_intel ปรับ percentile ตาม recency (area_win_series)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        project_name TEXT, winner TEXT, win_price INTEGER, discount_pct REAL,
        announce_date TEXT, fiscal_year TEXT, proc_type TEXT, district TEXT, subdistrict TEXT)""")
    c.execute("""CREATE TABLE bid_results (project_id TEXT, bidder_name TEXT, bidder_tin TEXT,
        price_proposal TEXT, price_agree TEXT, is_winner INTEGER, result_flag TEXT, fetched_at TEXT,
        PRIMARY KEY(project_id, bidder_tin))""")
    c.execute("""CREATE TABLE projects_seen (project_id TEXT PRIMARY KEY, province TEXT, budget INTEGER)""")
    # งานเก่าลด ~30%, งานล่าสุด ๆ ลด ~20% (เทรนด์ลดน้อยลง = ราคาสูงขึ้น) — ในจังหวัด
    data = [(30, "2566-01-01"), (30, "2566-06-01"), (30, "2567-01-01"),
            (20, "2567-11-01"), (20, "2568-01-01"), (20, "2568-05-01")]
    for i, (disc, ad) in enumerate(data):
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,announce_date,fiscal_year,proc_type,district,subdistrict) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (f"p{i}", "นครพนม", "ก่อสร้างถนน คสล.", f"หจก.{i}", 100000, disc, ad,
                   "256"+ad[3], EB, "เมือง", "ในเมือง"))
    c.commit(); return c


def test_recency_shifts_prediction():
    c = _conn()
    # province-level (amphoe=None) — budget 1,000,000
    ctx = ci._build_intel(c, "นครพนม", ["ถนน"], "", None, 1000000)
    assert ctx and ctx["prediction"], ctx
    pred = ctx["prediction"]
    # flat percentile ของ [30,30,30,20,20,20] = p25 20, p75 30 → กรอบบนราคา = 1,000,000*(1-0.20)=800,000
    # recency (EWMA ~22.4 < median 25 → delta ~-2.6) เลื่อนลง → p25'<20 → กรอบบนราคา area_price_hi สูงขึ้น
    assert pred["area_price_hi"] > 800000, pred       # ปรับขึ้นเพราะล่าสุดลดน้อยลง
    print("✅ recency ปรับ prediction ขึ้นตามงานล่าสุด (ลดน้อยลง → ราคาสูงขึ้น)")


if __name__ == "__main__":
    test_recency_shifts_prediction()
    print("\n✅ ALL test_trend_prediction PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_trend_prediction.py`
Expected: FAIL — `area_price_hi` ยังเท่าค่า flat (800000) เพราะยังไม่ recency-adjust

- [ ] **Step 3: Implement integration ใน `_build_intel`**

ใน `scripts/cgd_intel.py` `_build_intel`:

**(a)** เปลี่ยนบรรทัด init (เดิม):
```python
    pp25 = pp75 = ptop = ptopm = None
    basis = ""
```
เป็น:
```python
    pp25 = pp75 = ptop = ptopm = None
    basis = ""
    basis_sub = basis_dist = None    # scope ที่ใช้คาดราคา (สำหรับ recency series)
```

**(b)** ในบล็อกตำบล เปลี่ยน (เดิม):
```python
                pp25, pp75, ptop, ptopm, basis = t25, t75, ttop, ttopm, "ตำบล"
```
เป็น:
```python
                pp25, pp75, ptop, ptopm, basis = t25, t75, ttop, ttopm, "ตำบล"
                basis_sub, basis_dist = tambon, amphoe
```

**(c)** ในบล็อกอำเภอ เปลี่ยน (เดิม):
```python
                    pp25, pp75, ptop, ptopm, basis = a25, a75, atop, atopm, "อำเภอ"
```
เป็น:
```python
                    pp25, pp75, ptop, ptopm, basis = a25, a75, atop, atopm, "อำเภอ"
                    basis_sub, basis_dist = None, amphoe
```

**(d)** ในบล็อกจังหวัด เปลี่ยน (เดิม):
```python
        pp25, pp75, ptop, ptopm, basis = p25, p75, ptopn, ptopmd, "จังหวัด"
```
เป็น:
```python
        pp25, pp75, ptop, ptopm, basis = p25, p75, ptopn, ptopmd, "จังหวัด"
        basis_sub, basis_dist = None, None
```

**(e)** ก่อนบรรทัด `pred = predict_winning_price(...)` (เดิม):
```python
    pred = predict_winning_price(budget, pp25, pp75, ptop, ptopm)
```
แทรก recency-adjust ข้างหน้า:
```python
    if pp25 is not None and pp75 is not None:
        import competitor_trend as _ct
        _series = _ct.area_win_series(conn, province, tokens, basis_sub, basis_dist, subtype)
        pp25, pp75 = _ct.recency_adjusted_pct(_series, pp25, pp75)
    pred = predict_winning_price(budget, pp25, pp75, ptop, ptopm)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts\test_trend_prediction.py`
Expected: `✅ ALL test_trend_prediction PASS`

- [ ] **Step 5: Regression**

Run: `python scripts\test_cgd_intel.py` (ตั้ง env ก่อน: `BMS_DATA_DIR=$(python -c "import tempfile;print(tempfile.mkdtemp())")`)
Expected: `ALL PASS` (intel เดิมไม่ regress — fixture เดิมไม่มี announce_date → recency ไม่ปรับเพราะ n อาจ <3 หรือ delta เล็ก; ถ้า test_build_intel assert ค่าคงที่แล้วพัง ให้ตรวจว่าคาดราคายังสมเหตุผล แล้วปรับ assert ของเราเองให้รับการ recency-shift)

- [ ] **Step 6: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_trend_prediction.py
git commit -m "feat(trend): _build_intel ปรับ percentile ตาม recency (area_win_series) ก่อนคาดราคา"
```
ต่อท้าย: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 4: Round 2 per-company trend — `analyze_bidders` ใช้ EWMA

**Files:**
- Modify: `scripts/cgd_intel.py` (`analyze_bidders` — ใช้ `company_series`+`ewma_trend` แทน `company_area_history`)
- Modify: `scripts/Sebastian_LINE_Sender.py` (`format_winner_detailed` — โชว์ ewma "ล่าสุด~X%")
- Test: `scripts/test_round2_analysis.py` (อัปเดต)

- [ ] **Step 1: อัปเดต test `test_round2_analysis.py`**

แก้ `test_analyze_bidders` ใน `scripts/test_round2_analysis.py` — เพิ่ม announce_date ใน seed + assert ewma field. แทนที่ฟังก์ชัน `_conn` ให้ cgd_winners มี `announce_date` column + ค่า, และเพิ่ม assert:

ใน `_conn`, เปลี่ยน CREATE TABLE cgd_winners ให้มี `announce_date TEXT` (ถ้ายังไม่มี) และ INSERT ใส่ announce_date. ใน `test_analyze_bidders` เพิ่มหลัง assert เดิม:
```python
    assert "ewma" in out[0]["hist"], out[0]            # มี ewma (recency)
    assert out[0]["hist"]["n"] == 2, out               # X ประวัติตำบล 2 ครั้ง (เดิม)
```
(ลบ assert ที่อิง median เดิมถ้ามี — ใช้ ewma/n แทน)

> ดู Task code ของ `_conn` เดิมใน `test_round2_analysis.py` (Sub-1) — เพิ่มเฉพาะ `announce_date` ใน schema + INSERT (ค่าเช่น '2567-01-01','2567-06-01' ให้ 2 งานของ หจก.X). ส่วนอื่นคงเดิม.

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts\test_round2_analysis.py`
Expected: FAIL — `out[0]["hist"]` ไม่มี key `ewma` (analyze_bidders ยังใช้ company_area_history)

- [ ] **Step 3: เปลี่ยน `analyze_bidders` ใช้ EWMA**

ใน `scripts/cgd_intel.py` `analyze_bidders` — เปลี่ยนส่วน per-bidder loop. แทนที่บล็อก (เดิม):
```python
        hist = company_area_history(conn, province, tokens, name, subdistrict, district)
        trend = None
        if hist["median"] is not None and disc is not None:
            trend = "↑" if disc > hist["median"] + 1 else "↓" if disc < hist["median"] - 1 else "→"
```
ด้วย:
```python
        import competitor_trend as _ct
        _discs, _scope = _ct.company_series(conn, province, tokens, name, subdistrict, district)
        _t = _ct.ewma_trend(_discs)
        hist = {"scope": _scope, "n": _t["n"], "median": _t["median"], "ewma": _t["ewma"]}
        trend = _t["trend"]
```

(ที่เหลือของ loop คงเดิม — `out.append({...})` ใช้ `hist` + `trend` เหมือนเดิม)

- [ ] **Step 4: อัปเดต `format_winner_detailed` โชว์ ewma**

ใน `scripts/Sebastian_LINE_Sender.py` `format_winner_detailed` — เปลี่ยนบรรทัดสร้าง `hist_s` (เดิม):
```python
            if h["n"] > 0:
                hist_s = f"{h['scope']}เคย~{h['median']:.0f}%({h['n']}ครั้ง) {b['trend'] or ''}"
            else:
                hist_s = "ไม่มีประวัติ"
```
เป็น (ใช้ ewma = ระดับล่าสุด recency-weighted):
```python
            if h["n"] > 0:
                _lv = h.get("ewma") if h.get("ewma") is not None else h["median"]
                hist_s = f"{h['scope']}ล่าสุด~{_lv:.0f}%({h['n']}ครั้ง){b['trend'] or ''}"
            else:
                hist_s = "ไม่มีประวัติ"
```

- [ ] **Step 5: Run tests**

Run: `python scripts\test_round2_analysis.py`
Expected: `✅ ALL test_round2_analysis PASS`
Run: `python scripts\test_format_winner_detailed.py` (ปรับ assert ถ้าอิงคำว่า "เคย~" → เปลี่ยนเป็น "ล่าสุด~"; หรือ test เดิมส่ง hist ที่มี ewma แล้ว — เพิ่ม `"ewma"` ใน analyzed fixture ของ test นั้นถ้าจำเป็น)
Expected: `OK test_format_winner_detailed`

- [ ] **Step 6: Commit**

```bash
git add scripts/cgd_intel.py scripts/Sebastian_LINE_Sender.py scripts/test_round2_analysis.py scripts/test_format_winner_detailed.py
git commit -m "feat(trend): Round 2 เทรนด์ต่อบริษัทแบบ EWMA recency (analyze_bidders + format ล่าสุด~%)"
```
ต่อท้าย: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 5: Local sanity + deploy + real-data check + docs

**Files:** none (verification) + progress/memory

- [ ] **Step 1: รัน test ทั้งชุด**

```bash
python scripts\test_competitor_trend_ewma.py
python scripts\test_competitor_trend_series.py
python scripts\test_trend_prediction.py
python scripts\test_round2_analysis.py
python scripts\test_format_winner_detailed.py
```
แล้ว regression (ตั้ง `BMS_DATA_DIR`):
```bash
python scripts\test_cgd_intel.py
python scripts\test_price_prediction.py
python scripts\test_compare_upper_bound.py
```
Expected: ทุกตัว OK/PASS

- [ ] **Step 2: confirm push (GATE)** — ถามกัญจน์ "deploy Sub-2a ได้ไหม" รอ OK

- [ ] **Step 3: Push + VPS pull**

```bash
git push origin main
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app && git pull --ff-only origin main 2>&1 | tail -3"
```

- [ ] **Step 4: Real-data sanity — flat vs adaptive + announce_date coverage**

```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c \"
import sys; sys.path.insert(0,'/opt/bms/app/scripts')
import competitor_trend as ct, sqlite3
from Sebastian_Customer_DB import get_connection
c=get_connection()
n=c.execute('SELECT COUNT(*) FROM cgd_winners WHERE announce_date IS NOT NULL AND announce_date != \\\"\\\"').fetchone()[0]
tot=c.execute('SELECT COUNT(*) FROM cgd_winners').fetchone()[0]
print(f'announce_date coverage: {n}/{tot} = {round(n*100/tot)}%')
s=ct.area_win_series(c,'นครพนม',['ถนน'],subtype='concrete')
print('series นครพนม ถนน concrete:', len(s), 'จุด · ล่าสุด 5:', [round(x,1) for x in s[-5:]])
print('ewma:', round(ct.ewma(s),1) if s else None, '· median:', round(ct.median(s),1) if s else None)
\""
```
Expected: เห็น coverage % (ถ้า < 50% → recency อ่อน, log ไว้เป็น followup) + series + ewma vs median (ดูว่าต่างกันสมเหตุผล)

- [ ] **Step 5: progress_log + memory + Discord**

- progress_log: `## งานที่ N+113: Competitor Trend recency-adaptive (Sub-2a) LIVE`
- memory: อัปเดต `project_event_centric_queue` หรือสร้าง `project_competitor_trend` (EWMA recency + bid_results learning) + MEMORY.md
- Discord: "✅ Sub-2a LIVE — คาดราคาปรับตามผลล่าสุดแบบ EWMA (นุ่มนวล) + เทรนด์ส่วนลดต่อบริษัทใน Round 2. Sub-2b/2c (ถ่วงผู้น่าจะยื่น/รายงานตลาด) ถัดไป"

```bash
git add progress_log.md
git commit -m "docs(progress): N+113 — Competitor Trend recency-adaptive (Sub-2a) LIVE"
```

---

## Self-Review

**Spec coverage:**
- EWMA core (α0.3, MIN_N, CAP, TREND_EPS) → Task 1 ✅
- series รวม cgd_winners + bid_results เรียงเวลา (area_win + company) → Task 2 ✅
- prediction ปรับ recency (recency_adjusted_pct ใน _build_intel) → Task 3 ✅
- Round 2 เทรนด์ต่อบริษัท EWMA → Task 4 ✅
- data semantics (area=winner, company=win+proposal) → Task 2 ✅
- edge cases (n<MIN_N ไม่ปรับ, budget=0 ข้าม, CAP damping, subtype) → Task 1/2 ✅
- deploy + real-data sanity (announce_date coverage) → Task 5 ✅

**Placeholder scan:** ไม่มี TBD. โค้ดครบทุก step. Task 4 Step 1 อ้าง `_conn` เดิมของ test_round2_analysis (Sub-1) — มีคำสั่งชัดให้เพิ่ม announce_date column+ค่า (ไม่ใช่ placeholder, เป็นการแก้ test ที่มีอยู่).

**Type consistency:** `ewma`/`median` คืน float|None. `ewma_trend` คืน `{ewma, median, n, trend}` — ใช้ตรงใน Task 4 (`_t["n"]`, `_t["ewma"]`, `_t["trend"]`). `recency_adjusted_pct` คืน `(p25, p75)` tuple — ใช้ใน Task 3. `area_win_series` คืน `list[float]`, `company_series` คืน `(list[float], scope)` — ตรงกับ Task 2 test + Task 3/4 callers. `hist` dict ใน analyze_bidders มี keys `{scope, n, median, ewma}` — `format_winner_detailed` (Task 4) อ่าน `h["scope"], h["n"], h.get("ewma"), h["median"]` ตรงกัน.

**ความเสี่ยง (ไม่ใช่ placeholder):** Task 3 regression — fixture เดิม test_cgd_intel ไม่มี announce_date → cgd_winners query `SELECT announce_date` คืน '' (null) ทุกแถว → sort เสถียร (เก่าสุด) → recency ยังคำนวณได้ (จาก discount อย่างเดียว ไม่พึ่ง date ที่ถูกต้อง). ถ้า n≥3 → อาจ shift เล็กน้อย → ถ้า assert เดิมพัง ปรับ assert (เป็น test เราเอง). Task 4 — `company_area_history` (Sub-1) คงไว้ (test_round2_analysis ยัง test มันตรงๆ) — analyze_bidders แค่เลิกใช้.
