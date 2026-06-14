# Conditional Win-Rate (งาน B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** แทนป้าย win% ตายตัว 75/50/25 บนการ์ด D0 ด้วยตาราง win% 3 ระดับที่ self-calibrate จาก full-field (2A) ตามจำนวนผู้ยื่น.

**Architecture:** เพิ่ม pure function `winrate_grid` + renderer `winrate_lines` ใน `scripts/bid_field.py` (โมดูล 2B เดิม). ประเมิน F_bid (CDF discount ผู้ยื่นรายเดียว) + n stats (mean±SD ผู้ยื่น/auction) → win% = `F_bid(disc)^k`. เชื่อมเข้า `cgd_intel.predict()` ผ่าน helper `field_and_winrate` ที่อ่าน `_field_auctions` **รอบเดียว** ป้อนทั้ง 2B (เจ้าตลาด) และ B (ตาราง). gating: scope บาง → fallback การ์ดเดิม.

**Tech Stack:** Python 3, sqlite3, ไม่มี dependency ใหม่ (ใช้ `math` ใน stdlib). test = assert-style script (รูปแบบ `test_bid_field.py`), รันตรง `python scripts/test_*.py`.

**Spec:** `docs/superpowers/specs/2026-06-15-conditional-winrate-b-design.md`

---

## File Structure

- **Modify** `scripts/bid_field.py` — เพิ่ม `winrate_grid`, `winrate_lines`, `field_and_winrate` (+ const `MIN_AUCTIONS` มีอยู่แล้ว reuse)
- **Modify** `scripts/cgd_intel.py:583-597` — เปลี่ยนจุดต่อบล็อก 💵 + เจ้าตลาด ให้อ่าน field รอบเดียว + ตาราง B แทน a/b/c เมื่อมี grid
- **Create** `scripts/test_winrate_grid.py` — unit tests `winrate_grid`/`winrate_lines`/`field_and_winrate`
- **ไม่แตะ** `predict_lines` (fallback เดิม), `test_winrate.py`, `analyze_field`/`field_lines` (2B)

---

## Task 1: `winrate_grid` — pure function คำนวณตาราง win%

**Files:**
- Modify: `scripts/bid_field.py` (เพิ่มหลัง `_median`, ก่อน `analyze_field`)
- Test: `scripts/test_winrate_grid.py` (create)

- [ ] **Step 1: เขียน failing test (math + columns + gate + counts)**

สร้าง `scripts/test_winrate_grid.py`:

```python
"""test_winrate_grid.py — งาน B: conditional win-rate (F_bid^k) + ตาราง 3 ระดับ."""
import os, sys, tempfile
os.environ.setdefault("BMS_DATA_DIR", tempfile.mkdtemp())   # กัน import แตะ prod DB
os.environ.setdefault("BMS_ENV", "dev")
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf

def auc(*discs):
    """auction จาก list ของ disc — รายแรกเป็น winner (disc สูงสุดไม่จำเป็นต้องใช่ ในการคำนวณ grid ไม่สน winner)."""
    return [(f"b{i}", d, i == 0) for i, d in enumerate(discs)]

def test_grid_math():
    # 5 auctions × 4 bidders (n คงที่=4 → SD=0 → 1 คอลัมน์ k=4)
    # pooled disc: 10 ตัวที่ 10%, 10 ตัวที่ 30% → F_bid(30)=20/20=1.0 · F_bid(10)=10/20=0.5
    auctions = [auc(30, 30, 10, 10) for _ in range(5)]   # 5×(สอง 30, สอง 10)
    g = bf.winrate_grid(auctions, [700000, 900000, None], 1000000)
    assert g is not None, g
    assert g["ns"] == [4], g["ns"]                        # SD=0 → dedupe เหลือ k=4
    assert g["n_auctions"] == 5 and g["n_bids"] == 20, g
    rows = dict((p, w) for p, w in g["rows"])
    # 700000 → disc 30 → F=1.0 → 1.0^4=100% · 900000 → disc 10 → F=0.5 → 0.5^4=6.25%→6%
    assert rows[700000] == [100], rows
    assert rows[900000] == [6], rows
    print("✅ grid math (F_bid^k) ถูกต้อง")

def test_grid_columns_and_monotonic():
    # ขนาดสนาม [2,4,4,4,6] → mean=4, sample-SD=√2≈1.41 → คอลัมน์ [round(2.59),4,round(5.41)]=[3,4,5]
    sizes = [2, 4, 4, 4, 6]
    # ให้ disc กระจาย 0..(size-1)*?  ใช้ค่าเดียวกันทุก auction เพื่อ F_bid อยู่ (0,1) ที่ราคาทดสอบ
    auctions = []
    for s in sizes:
        auctions.append(auc(*[5 + 2 * j for j in range(s)]))   # disc 5,7,9,... ต่อ auction
    # price 900000 → disc 10% → F_bid(10)=14/20=0.7 (อยู่ใน (0,1) → k มีผลจริง)
    g = bf.winrate_grid(auctions, [900000, None, None], 1000000)
    assert g["ns"] == [3, 4, 5], g["ns"]
    ws = g["rows"][0][1]
    assert len(ws) == 3, ws
    assert ws[0] > ws[1] > ws[2], ("คู่แข่งเยอะ → win% ลด (strict)", ws)   # 34>24>17
    print("✅ คอลัมน์ mean±SD + monotonic (k↑→%↓)")

def test_grid_rows_monotonic():
    # ราคาต่ำ (disc สูง) → win% สูงกว่าราคาสูง (disc ต่ำ) ในคอลัมน์เดียวกัน
    auctions = [auc(30, 20, 10, 25) for _ in range(5)]    # n=4 คงที่
    g = bf.winrate_grid(auctions, [700000, 800000, 900000], 1000000)  # disc 30/20/10
    w_lo = g["rows"][0][1][0]   # 700000 (disc 30)
    w_hi = g["rows"][2][1][0]   # 900000 (disc 10)
    assert w_lo > w_hi, ("ราคาต่ำต้องชนะมากกว่า", w_lo, w_hi)
    print("✅ ราคาต่ำ → win% สูงกว่า (rows monotonic)")

def test_grid_gate():
    auctions = [auc(20, 10) for _ in range(4)]            # n_auctions=4 < MIN_AUCTIONS(5)
    assert bf.winrate_grid(auctions, [800000], 1000000) is None, "gate <5 → None"
    assert bf.winrate_grid([], [800000], 1000000) is None, "ว่าง → None"
    # ไม่มี budget / prices ว่าง → None
    assert bf.winrate_grid([auc(20, 10) for _ in range(5)], [], 1000000) is None, "ไม่มี price → None"
    assert bf.winrate_grid([auc(20, 10) for _ in range(5)], [800000], 0) is None, "ไม่มี budget → None"
    print("✅ gating (น้อย/ว่าง/ไม่มี budget → None)")

test_grid_math()
test_grid_columns_and_monotonic()
test_grid_rows_monotonic()
test_grid_gate()
print("ALL PASS winrate_grid (part 1)")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL — `AttributeError: module 'bid_field' has no attribute 'winrate_grid'`

- [ ] **Step 3: เขียน `winrate_grid` (minimal)**

ใน `scripts/bid_field.py` — เพิ่ม `import math` บนสุด (แก้ `import sqlite3, sys, os` → `import sqlite3, sys, os, math`) แล้วเพิ่มฟังก์ชันหลัง `_median` (บรรทัด ~21):

```python
def _cdf(sorted_bids, x):
    """F_bid(x) = สัดส่วน bid ≤ x (empirical CDF). sorted_bids เรียงแล้ว."""
    import bisect
    return bisect.bisect_right(sorted_bids, x) / len(sorted_bids)


def winrate_grid(auctions, prices, budget):
    """ตาราง win% conditional ตามจำนวนผู้ยื่น. win% = F_bid(disc)^k.
    auctions = [[(name,disc,is_winner)]] · prices = [lo,med,hi] (None ตัด) · budget = งบงานปัจจุบัน.
    คืน {ns, rows, n_mean, n_sd, n_auctions, n_bids, budget} หรือ None ถ้า gate ไม่ผ่าน."""
    auctions = [a for a in auctions if len(a) >= 2]
    n_auctions = len(auctions)
    try:
        bud = float(budget)
    except (TypeError, ValueError):
        bud = 0
    ps = [p for p in (prices or []) if p is not None]
    if n_auctions < MIN_AUCTIONS or bud <= 0 or not ps:
        return None
    bids = sorted(d for a in auctions for (_n, d, _w) in a)
    if not bids:
        return None
    sizes = [len(a) for a in auctions]
    n_mean = sum(sizes) / n_auctions
    var = sum((s - n_mean) ** 2 for s in sizes) / (n_auctions - 1)   # sample variance
    n_sd = math.sqrt(var)
    raw = [round(n_mean - n_sd), round(n_mean), round(n_mean + n_sd)]
    ns = []
    for k in raw:                                  # clamp ≥2 + dedupe รักษาลำดับ
        k = max(2, k)
        if k not in ns:
            ns.append(k)
    rows = []
    for p in ps:
        disc = (bud - p) / bud * 100.0
        f = _cdf(bids, disc)
        rows.append((p, [round(f ** k * 100) for k in ns]))
    return {"ns": ns, "rows": rows, "n_mean": n_mean, "n_sd": n_sd,
            "n_auctions": n_auctions, "n_bids": len(bids), "budget": bud}
```

- [ ] **Step 4: รัน test ให้ pass**

Run: `python scripts/test_winrate_grid.py`
Expected: PASS — `ALL PASS winrate_grid (part 1)`

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): งาน B — winrate_grid (F_bid^k conditional ตามจำนวนผู้ยื่น)"
```

---

## Task 2: `winrate_lines` — render ตาราง

**Files:**
- Modify: `scripts/bid_field.py` (เพิ่มหลัง `winrate_grid`)
- Test: `scripts/test_winrate_grid.py` (เพิ่ม test)

- [ ] **Step 1: เขียน failing test**

เพิ่มใน `scripts/test_winrate_grid.py` ก่อนบรรทัด `print("ALL PASS ...")` สุดท้าย:

```python
def test_winrate_lines_render():
    grid = {"ns": [4, 6, 8],
            "rows": [(1400000, [78, 68, 59]), (1600000, [55, 42, 32]), (1800000, [28, 18, 11])],
            "n_mean": 6.0, "n_sd": 2.0, "n_auctions": 18, "n_bids": 107, "budget": 2000000}
    lines = bf.winrate_lines(grid, "อำเภอ")
    txt = "\n".join(lines)
    assert "โอกาสชนะตามจำนวนผู้ยื่น" in txt, txt
    assert "งบ 2,000,000" in txt, txt
    assert "4ราย" in txt and "6ราย" in txt and "8ราย" in txt, txt
    assert "1,400,000" in txt and "78%" in txt, txt
    assert "เฉลี่ย 6 ผู้ยื่น" in txt and "(±2)" in txt and "อิงอำเภอ" in txt, txt
    assert "📈 สถิติจาก 18 งาน · 107 ผู้ยื่น" in txt, txt        # sample size (กัญจน์ขอ)
    assert bf.winrate_lines(None, "อำเภอ") == [], "None → []"
    print("✅ winrate_lines render + sample size")

test_winrate_lines_render()
```

แก้บรรทัดสุดท้าย `print("ALL PASS winrate_grid (part 1)")` → `print("ALL PASS winrate_grid")` และย้าย `test_winrate_lines_render()` ให้รันก่อน print นั้น.

- [ ] **Step 2: รัน test ให้ fail**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL — `AttributeError: ... 'winrate_lines'`

- [ ] **Step 3: เขียน `winrate_lines`**

ใน `scripts/bid_field.py` หลัง `winrate_grid`:

```python
def winrate_lines(grid, basis="") -> list:
    """render ตาราง win% (pure). [] ถ้า grid None.
    คอลัมน์ = จำนวนผู้ยื่น (mean±SD) · แถว = ราคา a/b/c · footer = ค่าเฉลี่ย + sample size."""
    if not grid:
        return []
    ns, rows = grid["ns"], grid["rows"]
    lines = [f"💵 แนะนำราคายื่น (งบ {grid['budget']:,.0f}) — โอกาสชนะตามจำนวนผู้ยื่น"]
    lines.append("   ผู้ยื่น →   " + "  ".join(f"{k}ราย".rjust(6) for k in ns))
    for price, ws in rows:
        cells = "  ".join(f"{w}%".rjust(6) for w in ws)
        lines.append(f"   {price:>10,.0f}  {cells}")
    sd_txt = f" (±{round(grid['n_sd'])})" if len(ns) > 1 else ""
    lines.append(f"   📊 สนามนี้เฉลี่ย {round(grid['n_mean'])} ผู้ยื่น{sd_txt} · อิง{basis}")
    lines.append(f"   📈 สถิติจาก {grid['n_auctions']} งาน · {grid['n_bids']} ผู้ยื่น")
    lines.append("   * ยิ่งผู้ยื่นเยอะ โอกาสยิ่งต่ำ")
    return lines
```

- [ ] **Step 4: รัน test ให้ pass**

Run: `python scripts/test_winrate_grid.py`
Expected: PASS — `ALL PASS winrate_grid`

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): งาน B — winrate_lines render ตาราง + sample size"
```

---

## Task 3: `field_and_winrate` + เชื่อม `predict()`

**Files:**
- Modify: `scripts/bid_field.py` (เพิ่มหลัง `field_block`)
- Modify: `scripts/cgd_intel.py:583-597`
- Test: `scripts/test_winrate_grid.py` (เพิ่ม end-to-end test)

- [ ] **Step 1: เขียน failing test (end-to-end จาก DB — อ่านรอบเดียว ป้อน 2 บล็อก)**

เพิ่มใน `scripts/test_winrate_grid.py` (ก่อน print สุดท้าย):

```python
def test_field_and_winrate_endtoend():
    import tempfile
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import importlib, Sebastian_Customer_DB as db
    importlib.reload(db)
    db.init_schema()
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        for i in range(6):                                   # 6 auctions ≥ MIN_AUCTIONS
            conn.execute("INSERT OR REPLACE INTO cgd_winners "
                         "(project_id, province, proc_type, project_name, budget) VALUES (?,?,?,?,?)",
                         (f"W{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                          "ก่อสร้างถนน อ.เมือง", 1000000))
    for i in range(6):
        s.record_bid_results(f"W{i}", [
            {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "850000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "900000"}])
    with db.get_connection() as conn:
        wl, fl = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                      [700000, 850000, 900000], district="เมือง",
                                      scope_label=" (อ.เมือง)", basis="อำเภอ")
    wtxt = "\n".join(wl)
    assert "โอกาสชนะตามจำนวนผู้ยื่น" in wtxt, wtxt           # B table โผล่
    assert "📈 สถิติจาก 6 งาน · 18 ผู้ยื่น" in wtxt, wtxt     # 6 งาน × 3 ผู้ยื่น = 18
    assert isinstance(fl, list), fl                          # 2B block (อาจ [] ถ้าไม่มี leader) — ไม่ error
    print("✅ field_and_winrate end-to-end (อ่านรอบเดียว → 2 บล็อก)")

test_field_and_winrate_endtoend()
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL — `AttributeError: ... 'field_and_winrate'`

- [ ] **Step 3: เขียน `field_and_winrate` (อ่าน `_field_auctions` รอบเดียว)**

ใน `scripts/bid_field.py` หลัง `field_block`:

```python
def field_and_winrate(conn, province, tokens, budget, prices,
                      subdistrict=None, district=None, scope_label="", basis=""):
    """อ่าน _field_auctions รอบเดียว → คืน (winrate_lines [B], field_lines [2B เจ้าตลาด]).
    graceful: คืน ([],[]) ถ้า scope ว่าง. จุดเชื่อม predictor — กัน query ซ้ำ."""
    auctions = _field_auctions(conn, province, tokens, subdistrict, district)
    wl = winrate_lines(winrate_grid(auctions, prices, budget), basis)
    fl = field_lines(analyze_field(auctions), budget, scope_label)
    return wl, fl
```

- [ ] **Step 4: รัน test ให้ pass**

Run: `python scripts/test_winrate_grid.py`
Expected: PASS — `ALL PASS winrate_grid`

- [ ] **Step 5: เชื่อมเข้า `predict()` — แทนบล็อก 583-597**

ใน `scripts/cgd_intel.py` แทนที่บล็อกเดิม (บรรทัด 583-597):

```python
    pred = predict_winning_price(budget, pp25, pp75, ptop, ptopm, area_median=pmed)
    if pred:
        import bid_field as _bf                       # 2B เจ้าตลาด + B ตาราง win% — อ่าน field รอบเดียว
        prices = [pred.get("area_price_lo"), pred.get("area_price_med"), pred.get("area_price_hi")]
        scopes = ([(tambon, None, f" (ต.{tambon})")] if tambon else []) + \
                 ([(None, amphoe, f" (อ.{amphoe})")] if amphoe else [])
        _wl, _fl = [], []
        for _sub, _dist, _lbl in scopes:              # ตำบลก่อน → อำเภอ → เจอ data ที่ระดับไหนใช้ระดับนั้น
            _wl, _fl = _bf.field_and_winrate(conn, province, tokens, budget, prices,
                                             subdistrict=_sub, district=_dist,
                                             scope_label=_lbl, basis=basis)
            if _wl or _fl:
                break
        if _wl:                                        # มี grid → ตาราง B แทนป้าย a/b/c เดิม
            lines += [""] + _wl
        else:                                          # ไม่มี → การ์ดเดิม (fallback graceful)
            lines += [""] + predict_lines(pred, basis, contested=contested_only)
        if basis_old:
            lines.append("📜 รวมข้อมูลเก่ากว่า 3 ปี (พื้นที่นี้งานน้อย) — ใช้เป็นแนวโน้ม")
        if _fl:                                        # บล็อกเจ้าตลาด 2B (ต่อท้าย)
            lines += [""] + _fl
```

- [ ] **Step 6: รัน py_compile + test ทั้งหมด (backward-compat)**

Run:
```bash
python -m py_compile scripts/cgd_intel.py scripts/bid_field.py
BMS_ENV=dev python scripts/test_winrate_grid.py
BMS_ENV=dev python scripts/test_winrate.py
BMS_ENV=dev python scripts/test_bid_field.py
```
Expected: ทุกไฟล์ผ่าน — `ALL PASS winrate_grid` · `ALL PASS (winrate headline)` · `ALL PASS bid_field`
(บน Windows ถ้า `BMS_ENV=dev x` ไม่ทำงาน ใช้ `$env:BMS_ENV='dev'; python ...` ทีละบรรทัด)

- [ ] **Step 7: Commit**

```bash
git add scripts/bid_field.py scripts/cgd_intel.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): งาน B — เชื่อม predict() ตาราง win% แทน a/b/c (อ่าน field รอบเดียว 2B+B)"
```

---

## Task 4: Verification — smoke จริง + backward-compat

**Files:** ไม่แก้โค้ด — รัน verify อย่างเดียว

- [ ] **Step 1: ยืนยัน test เดิมไม่พังจาก integration**

Run:
```bash
$env:BMS_ENV='dev'; python scripts/test_winrate.py
$env:BMS_ENV='dev'; python scripts/test_bid_field.py
$env:BMS_ENV='dev'; python scripts/test_competitor_trend_series.py
```
Expected: ทุกไฟล์ `ALL PASS` (predict_lines เดิมยัง fallback ได้, การ์ดไม่พัง)

- [ ] **Step 2: ยืนยัน gating — scope บางต้องเห็นการ์ดเดิม (ไม่ใช่ตาราง)**

เพิ่ม assert ใน `test_winrate_grid.py` (หรือรัน inline) ว่า scope ที่ bid_results ว่าง → `field_and_winrate` คืน `([], [])` → predict() ใช้ `predict_lines` เดิม:

```python
def test_gate_fallback_to_old_card():
    import tempfile, importlib, Sebastian_Customer_DB as db
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp(); importlib.reload(db); db.init_schema()
    with db.get_connection() as conn:
        wl, fl = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                      [700000, 800000, 900000], district="ไม่มี", basis="อำเภอ")
    assert wl == [] and fl == [], (wl, fl)               # ว่าง → predict() จะ fallback การ์ดเดิม
    print("✅ gate: scope บาง → ([],[]) → การ์ดเดิม")

test_gate_fallback_to_old_card()
```
Run: `$env:BMS_ENV='dev'; python scripts/test_winrate_grid.py` → PASS

- [ ] **Step 3: บันทึก progress_log + Discord**

- เพิ่ม entry `## งานที่ N+132: งาน B conditional win-rate — code DONE (รอ deploy)` ใน `progress_log.md` (status, สิ่งที่ทำ, followup = deploy VPS + ดูการ์ดจริง)
- Discord: `📝 งาน B (conditional win-rate ตาราง 3 ระดับ) code+test เสร็จ รอ deploy VPS`

- [ ] **Step 4: Commit progress_log**

```bash
git add progress_log.md
git commit -m "docs(progress): N+132 งาน B conditional win-rate — code DONE (รอ deploy)"
```

- [ ] **Step 5: Followup (ไม่อยู่ใน session นี้ — ต้องกัญจน์รัน VPS)**

หลัง backfill 2A เสร็จ + deploy:
```bash
cd /opt/bms/app && git pull && bash scripts/deploy.sh
BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python scripts/_show_card.py
```
ดู: scope ที่ full-field ≥5 → เห็นตาราง 3 คอลัมน์ + บรรทัด 📈 สถิติ · scope บาง → การ์ดเดิม

---

## Self-Review

**Spec coverage:**
- §4 กลไก (F_bid, n stats, columns, F^k) → Task 1 ✅
- §6 winrate_grid dict (ns/rows/n_mean/n_sd/n_auctions/n_bids) → Task 1 ✅ (+budget สำหรับ render)
- §7 output ตาราง + 📈 sample size → Task 2 ✅
- §5+§6 อ่าน _field_auctions รอบเดียว ป้อน 2B+B → Task 3 `field_and_winrate` ✅
- §6 integration (a) ไม่แตะ predict_lines, ตาราง B แทน a/b/c → Task 3 Step 5 ✅
- §8 gating fallback การ์ดเดิม → Task 1 (None) + Task 4 Step 2 ✅
- §9 test 1-7 → Task 1-3 tests (math/columns/monotonic/gate/counts/render/sample-size) ✅
- §11 DoD (test ผ่าน, py_compile, smoke, อ่านรอบเดียว) → Task 3 Step 6 + Task 4 ✅

**Placeholder scan:** ไม่มี TBD/TODO — ทุก step มี code/command จริง.

**Type consistency:** `winrate_grid` คืน dict keys {ns, rows, n_mean, n_sd, n_auctions, n_bids, budget} ใช้ตรงกันใน `winrate_lines` (อ่าน budget/ns/rows/n_mean/n_sd/n_auctions/n_bids) และ test. `field_and_winrate(conn, province, tokens, budget, prices, subdistrict, district, scope_label, basis)` ตรงกันทั้ง def + call ใน predict() + test. `_cdf(sorted_bids, x)` ใช้ใน winrate_grid เท่านั้น.

**หมายเหตุ consistency (spec test #4 ≈50%):** validate ผ่าน `test_grid_math` (assert ค่า exact `F^k`) ซึ่งคุมสูตรเดียวกับ property — property ≈50% เป็นผลของสูตรที่ test บังคับค่าตรงแล้ว.
