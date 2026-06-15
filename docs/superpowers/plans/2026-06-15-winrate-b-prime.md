# Win-Rate B′ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ทำให้ตาราง win% ขึ้นในพื้นที่ข้อมูลบาง (ผ่อน scope ladder) + ถ่วงปี (recency) + center คอลัมน์ด้วยจำนวนผู้ยื่น local — โดยไม่แตะคุณภาพราคาหลัก (price sacred).

**Architecture:** `bid_field.py` มี `_evaluate_winrate` (gate+ESS+weighted quantile+local-n centering, source-of-truth เดียว) ห่อด้วย `winrate_grid` (คง contract dict|None). `field_and_winrate` กลายเป็น orchestrator: ลอง F_bid scope จาก price scope → ผ่อน อำเภอ→จังหวัด (ผ่าน `_fetch_scope` คง cf) จน gate ผ่าน, คืน `(wl, fl, conf)`. `cgd_intel.predict()` render: 🟢 แทน a/b/c · 🟡🟠 คง a/b/c + ตารางต่อท้าย.

**Tech Stack:** Python 3, SQLite, assert-style tests (no pytest), `recency_weight` (cgd_intel, half-life 1ปี).

---

## File Structure

- **Modify** `scripts/bid_field.py` — เพิ่ม `_weighted_quantile`/`_evaluate_winrate`, constants, ปรับ `_field_auctions` (4-tuple +fiscal_year), `winrate_grid`/`winrate_lines`/`field_and_winrate`, fix consumers `analyze_field`/`_winner_idx`.
- **Modify** `scripts/cgd_intel.py` — integration ~586-601 (replace vs append by conf + cf/amphoe args).
- **Modify** `scripts/test_winrate_grid.py` — ขยาย tests (recency/ESS/local-n/ladder/assisted/fail_reason) + อัปเดต tests ที่ signature เปลี่ยน.

**Constants** (เพิ่มหัวไฟล์ `bid_field.py` ใกล้ `MIN_AUCTIONS`):
- `ESS_FLOOR = 6` — effective sample (weighted) ขั้นต่ำ (bootstrap; ขยับ 8/10 เมื่อ backfill โต — B″)
- `MIN_N_AUCTIONS = 3` — auctions ขั้นต่ำของ local scope ที่จะเชื่อ n centering (review: 2 → variance ไร้ความหมาย)

---

## Task 1: `_weighted_quantile` + logger + recency import

**Files:**
- Modify: `scripts/bid_field.py` (imports + ใหม่หลัง `_quantile`)
- Test: `scripts/test_winrate_grid.py`

- [ ] **Step 1: Write the failing test** (เพิ่มในไฟล์ test, ก่อนบรรทัด `test_grid_invert_targets()` ที่เรียกล่าง)

```python
def test_weighted_quantile():
    pairs = [(0.0, 1.0), (10.0, 1.0), (20.0, 1.0), (30.0, 1.0)]   # น้ำหนักเท่ากัน
    q50 = bf._weighted_quantile(pairs, 0.5)
    assert 10.0 <= q50 <= 20.0, q50                               # กลาง ๆ
    assert bf._weighted_quantile(pairs, 0.0) == 0.0               # ต่ำสุด
    assert bf._weighted_quantile(pairs, 1.0) == 30.0              # สูงสุด
    heavy_high = [(0.0, 0.1), (30.0, 10.0)]                       # ถ่วงค่าสูง
    assert bf._weighted_quantile(heavy_high, 0.5) > 25.0, "น้ำหนักเอียงสูง → median สูง"
    print("✅ _weighted_quantile (Hazen weighted)")
```

และเพิ่ม `test_weighted_quantile()` ในบล็อกเรียกล่างสุด (ก่อน `print("ALL PASS...")`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL `AttributeError: module 'bid_field' has no attribute '_weighted_quantile'`

- [ ] **Step 3: Implement** — แก้ import บนสุด + เพิ่มฟังก์ชัน

แก้บรรทัด import (`scripts/bid_field.py:4-8`):
```python
import sqlite3, sys, os, math, logging
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from cgd_intel import COMPETITIVE_SET, recency_weight

_log = logging.getLogger(__name__)
```

เพิ่มหลัง `_quantile` (หลัง `bid_field.py:35`):
```python
def _weighted_quantile(pairs, q):
    """ค่าที่ cumulative-weight quantile q (0..1) — Hazen plotting position บนน้ำหนักสะสม.
    pairs = [(value, weight)] · weight>0. น้ำหนักเท่ากัน → ใกล้ median ปกติ. ว่าง → 0."""
    sp = sorted(pairs)
    if not sp:
        return 0.0
    total = sum(w for _v, w in sp)
    if total <= 0:
        return sp[0][0]
    pts, cum = [], 0.0
    for v, w in sp:
        pts.append(((cum + w / 2.0) / total, v))    # Hazen: กึ่งกลางช่วงน้ำหนัก
        cum += w
    if q <= pts[0][0]:
        return pts[0][1]
    if q >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        p0, v0 = pts[i - 1]
        p1, v1 = pts[i]
        if q <= p1:
            frac = (q - p0) / (p1 - p0) if p1 > p0 else 0.0
            return v0 + frac * (v1 - v0)
    return pts[-1][1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_winrate_grid.py`
Expected: `✅ _weighted_quantile` + `ALL PASS winrate_grid`

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): B′ _weighted_quantile + recency import (knob 2 รากฐาน)"
```

---

## Task 2: `_field_auctions` → 4-tuple (+fiscal_year) + fix consumers

**Files:**
- Modify: `scripts/bid_field.py` (`_field_auctions`, `analyze_field`, `_winner_idx`)
- Test: `scripts/test_winrate_grid.py`

- [ ] **Step 1: Write the failing test**

```python
def test_field_auctions_fiscal_year():
    """_field_auctions คืน 4-tuple (name, disc, is_winner, fiscal_year)."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO cgd_winners "
                     "(project_id, province, proc_type, project_name, budget, fiscal_year) "
                     "VALUES (?,?,?,?,?,?)",
                     ("F1", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน", 1000000, 2568))
    s.record_bid_results("F1", [
        {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
        {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "850000"}])
    with db.get_connection() as conn:
        au = bf._field_auctions(conn, "นครพนม", ["ถนน"])
    assert au and len(au[0][0]) == 4, au                          # 4-tuple
    assert au[0][0][3] == 2568, au[0][0]                          # fiscal_year ตัวที่ 4
    # 2B ยังทำงาน (รับ 4-tuple ไม่พัง)
    fr = bf.analyze_field(au)
    assert isinstance(fr, dict) and "tier" in fr, fr
    print("✅ _field_auctions 4-tuple + analyze_field รับได้")
```

เพิ่มเรียกในบล็อกล่าง.

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL — `len(au[0][0]) == 4` ไม่จริง (ยัง 3-tuple)

- [ ] **Step 3: Implement** — 3 จุด

(a) `_field_auctions` SQL + unpack (`bid_field.py:190-217`): เพิ่ม `cw.fiscal_year`:
```python
    sql = ("SELECT b.project_id, b.bidder_name, b.price_proposal, b.price_agree, b.is_winner, "
           "cw.budget, cw.fiscal_year "
           "FROM bid_results b JOIN cgd_winners cw ON cw.project_id=b.project_id "
           "WHERE " + " AND ".join(where))
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.DatabaseError:
        return []
    byp = defaultdict(list)
    for pid, name, pp, pa, isw, budget, fy in rows:
        bid = None
        for x in (pp, pa):
            try:
                f = float(x)
                if f > 0:
                    bid = f
                    break
            except (TypeError, ValueError):
                pass
        try:
            bud = float(budget)
        except (TypeError, ValueError):
            bud = 0
        if not bid or bud <= 0:
            continue
        disc = (bud - bid) / bud * 100.0
        if disc < 0 or disc > DISC_MAX:
            continue
        byp[pid].append((name or "", disc, bool(isw), fy))
    return list(byp.values())
```

(b) `_winner_idx` (`bid_field.py:100-105`) — รับ tuple ยาวกว่า 3:
```python
def _winner_idx(auction):
    """index ผู้ชนะ: is_winner ก่อน, fallback disc สูงสุด."""
    for i, t in enumerate(auction):
        if t[2]:
            return i
    return max(range(len(auction)), key=lambda i: auction[i][1])
```

(c) `analyze_field` loop unpack (`bid_field.py:118-128`) — `for (nm, _d, _w) in a:` → tolerate 4-tuple, และ `wname, wdisc, _ = a[wi]`:
```python
    for a in auctions:
        wi = _winner_idx(a)
        wname, wdisc = a[wi][0], a[wi][1]
        seen = set()
        for t in a:
            nm = t[0]
            if nm and nm not in seen:
                appear[nm] += 1
                seen.add(nm)
        if wname:
            wins[wname] += 1
            win_disc[wname].append(wdisc)
```

- [ ] **Step 4: Run tests** (ทั้ง winrate + bid_field เดิม)

Run: `python scripts/test_winrate_grid.py && python scripts/test_bid_field.py`
Expected: ทั้งคู่ PASS (`✅ _field_auctions 4-tuple` + test_bid_field เดิมไม่พัง)

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): B′ _field_auctions 4-tuple (+fiscal_year) + fix 2B consumers รับ 4-tuple"
```

---

## Task 3: `_evaluate_winrate` (ESS gate + recency quantile + local-n + fail_reason)

**Files:**
- Modify: `scripts/bid_field.py` (เพิ่ม constants + `_evaluate_winrate` + ปรับ `winrate_grid` เป็น wrapper)
- Test: `scripts/test_winrate_grid.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_eval_fail_reasons():
    base = [[(f"b{j}", j * 2.0, j == 0, 2569) for j in range(4)] for _ in range(5)]   # 5×4, disc 0/2/4/6
    assert bf._evaluate_winrate(base[:4], 1000000)["fail_reason"] == "AUCTIONS"        # <5 auctions
    assert bf._evaluate_winrate(base, 0)["fail_reason"] == "BUDGET"
    narrow = [[(f"b{j}", 20.0, j == 0, 2569) for j in range(4)] for _ in range(5)]     # disc เท่ากัน
    assert bf._evaluate_winrate(narrow, 1000000)["fail_reason"] == "PRICE_COLLAPSE"
    ok = bf._evaluate_winrate(base, 1000000)
    assert ok["ok"] and ok["fail_reason"] == "OK" and ok["ess"] >= 6, ok
    print("✅ _evaluate_winrate fail_reason (AUCTIONS/BUDGET/PRICE_COLLAPSE/OK)")

def test_eval_ess_gate_recency():
    # 5 auctions แต่ส่วนใหญ่เก่ามาก (2562) → ESS ต่ำ → gate ESS fail
    old = [[(f"b{j}", j * 3.0, j == 0, 2562) for j in range(2)] for _ in range(5)]     # 10 bids เก่า → w≈0.008
    r = bf._evaluate_winrate(old, 1000000)
    assert r["fail_reason"] == "ESS", r                      # ESS < 6 (เก่าจาง)
    print("✅ ESS gate (งานเก่าจาง → ESS fail)")

def test_eval_local_n_centering():
    # F-scope กว้าง n~8 (สนามใหญ่), local_auctions แคบ n~4 → center ตาม local
    big = [[(f"b{j}", j * 1.3, j == 0, 2569) for j in range(8)] for _ in range(5)]     # n=8
    local = [[(f"b{j}", j * 1.3, j == 0, 2569) for j in range(4)] for _ in range(4)]   # n=4, 4 auctions ≥3
    g = bf._evaluate_winrate(big, 1000000, local_auctions=local)
    assert g["ok"] and g["ns"][len(g["ns"]) // 2] == 4, g["ns"]    # center=4 (local) ไม่ใช่ 8
    # local น้อยกว่า MIN_N_AUCTIONS(3) → fallback ใช้ F-scope n
    g2 = bf._evaluate_winrate(big, 1000000, local_auctions=local[:2])
    assert g2["ns"][len(g2["ns"]) // 2] == 8, g2["ns"]            # center=8 (F-scope) เพราะ local<3
    print("✅ local-n centering + fallback เมื่อ local<MIN_N_AUCTIONS")
```

เพิ่มเรียกในบล็อกล่าง. **อัปเดต `test_grid_gate`** ให้ใช้ 4-tuple-agnostic (มันใช้ 3-tuple ผ่าน inline — ยังผ่านเพราะ fy=None→w=1, ESS=20). ไม่ต้องแก้ test_grid_gate.

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL `module 'bid_field' has no attribute '_evaluate_winrate'`

- [ ] **Step 3: Implement** — เพิ่ม constants + `_evaluate_winrate` + แทน `winrate_grid`

เพิ่ม constants ใกล้ `bid_field.py:10-13`:
```python
ESS_FLOOR = 6          # effective sample (weighted) ขั้นต่ำ — bootstrap (ขยับ 8/10 เมื่อ backfill โต = B″)
MIN_N_AUCTIONS = 3     # local auctions ขั้นต่ำที่จะเชื่อ n centering (2 → variance ไร้ความหมาย)
```

แทน `winrate_grid` ทั้งฟังก์ชัน (`bid_field.py:38-79`) ด้วย `_evaluate_winrate` + wrapper:
```python
def _evaluate_winrate(auctions, budget, local_auctions=None, targets=(75, 50, 25)):
    """source-of-truth: gate + ESS + weighted quantile + local-n centering.
    คืน dict เสมอ — ok=True พร้อม grid fields, หรือ ok=False พร้อม fail_reason
    (AUCTIONS/ESS/BOTH/BUDGET/PRICE_COLLAPSE). auctions/local_auctions = [[(name,disc,is_winner[,fy])]].
    local_auctions = scope แคบสุด (≥MIN_N_AUCTIONS) สำหรับ center คอลัมน์ (None → ใช้ auctions)."""
    auctions = [a for a in auctions if len(a) >= 2]
    n_auctions = len(auctions)
    try:
        bud = float(budget)
    except (TypeError, ValueError):
        bud = 0
    if bud <= 0:
        return {"ok": False, "fail_reason": "BUDGET", "ess": 0.0}
    pairs = []                                          # (disc, recency_weight)
    for a in auctions:
        for bid in a:
            fy = bid[3] if len(bid) > 3 else None
            pairs.append((bid[1], recency_weight(fy)))
    ess = 0.0
    if pairs:
        sw = sum(w for _d, w in pairs)
        sw2 = sum(w * w for _d, w in pairs)
        ess = (sw * sw) / sw2 if sw2 > 0 else 0.0
    fail = []
    if n_auctions < MIN_AUCTIONS:
        fail.append("AUCTIONS")
    if ess < ESS_FLOOR:
        fail.append("ESS")
    if fail:
        reason = "BOTH" if len(fail) == 2 else fail[0]
        return {"ok": False, "fail_reason": reason, "ess": ess}
    # n centering: ใช้ local ถ้าหนาพอ ไม่งั้น F-scope
    src = [a for a in (local_auctions or []) if len(a) >= 2]
    if len(src) < MIN_N_AUCTIONS:
        src = auctions
    sizes = [len(a) for a in src]
    n_mean = sum(sizes) / len(sizes)
    var = sum((s - n_mean) ** 2 for s in sizes) / (len(sizes) - 1) if len(sizes) > 1 else 0.0
    n_sd = math.sqrt(var)
    raw = [round(n_mean - n_sd), round(n_mean), round(n_mean + n_sd)]
    ns = []
    for k in raw:
        k = max(2, k)
        if k not in ns:
            ns.append(k)
    k_mid = ns[len(ns) // 2]
    rows, seen_price = [], set()
    for t in targets:
        tf = t / 100.0
        disc = _weighted_quantile(pairs, tf ** (1.0 / k_mid))    # ราคา = inverse weighted-CDF
        price = round(bud * (1 - disc / 100.0))
        if price in seen_price:
            continue
        seen_price.add(price)
        rows.append((price, [round(tf ** (k / k_mid) * 100) for k in ns]))
    if len(rows) < 2:
        return {"ok": False, "fail_reason": "PRICE_COLLAPSE", "ess": ess}
    rows.sort()
    return {"ok": True, "fail_reason": "OK", "ns": ns, "rows": rows,
            "n_mean": n_mean, "n_sd": n_sd, "n_auctions": n_auctions,
            "n_bids": len(pairs), "ess": ess, "k_mid": k_mid, "budget": bud}


def winrate_grid(auctions, budget, local_auctions=None, targets=(75, 50, 25)):
    """ตาราง win% conditional (B′). wrapper ของ _evaluate_winrate — คง contract dict|None.
    None เมื่อ gate ไม่ผ่าน (ดู fail_reason ใน _evaluate_winrate)."""
    g = _evaluate_winrate(auctions, budget, local_auctions, targets)
    return g if g.get("ok") else None
```

> หมายเหตุ: `test_grid_gate` ตรวจ `narrow` (disc เท่ากัน 20.0, 5×4=20 bids) → ESS=20≥6 ผ่าน gate แต่ราคายุบ → PRICE_COLLAPSE → `winrate_grid` คืน None. assertion เดิม (`is None`) ยังจริง.

- [ ] **Step 4: Run tests**

Run: `python scripts/test_winrate_grid.py`
Expected: ทุกเคสใหม่ + เก่า PASS (`✅ _evaluate_winrate...`, `✅ ESS gate`, `✅ local-n centering`, `ALL PASS`)

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): B′ _evaluate_winrate — ESS gate + recency quantile + local-n centering + fail_reason"
```

---

## Task 4: `winrate_lines` — conf tag + assisted disclaimer

**Files:**
- Modify: `scripts/bid_field.py` (`winrate_lines`)
- Test: `scripts/test_winrate_grid.py` (เขียนทับ `test_winrate_lines_render` + เพิ่ม assisted test)

- [ ] **Step 1: Write/replace the failing test** — แทน `test_winrate_lines_render` เดิมทั้งฟังก์ชัน:

```python
def test_winrate_lines_render():
    grid = {"ns": [4, 6, 8],
            "rows": [(1400000, [78, 68, 59]), (1600000, [55, 42, 32]), (1800000, [28, 18, 11])],
            "n_mean": 6.0, "n_sd": 2.0, "n_auctions": 18, "n_bids": 107,
            "ess": 40.0, "k_mid": 6, "budget": 2000000}
    lines = bf.winrate_lines(grid)                       # 🟢 local (conf=None)
    txt = "\n".join(lines)
    assert "โอกาสชนะตามจำนวนผู้ยื่น" in txt and "งบ 2,000,000" in txt, txt
    assert "4ราย" in txt and "1,400,000" in txt and "78%" in txt, txt
    assert "เฉลี่ย 6 ผู้ยื่น" in txt and "(±2)" in txt, txt
    assert "📈 จาก 18 งานที่มีข้อมูลผู้ยื่นครบ · 107 ราย" in txt, txt
    assert "⚠️" not in txt, "🟢 local ไม่มี disclaimer"
    assert bf.winrate_lines(None) == [], "None → []"
    print("✅ winrate_lines render (🟢 local)")

def test_winrate_lines_assisted():
    grid = {"ns": [3, 5, 7], "rows": [(1100000, [85, 75, 66]), (1200000, [36, 25, 16])],
            "n_mean": 5.0, "n_sd": 2.0, "n_auctions": 9, "n_bids": 41,
            "ess": 12.0, "k_mid": 5, "budget": 2000000}
    lines = bf.winrate_lines(grid, conf=("🟡", "อำเภอ"), price_basis="ตำบล")
    txt = "\n".join(lines)
    assert "🟡 โอกาส% อิงอำเภอ" in txt, txt
    assert "⚠️ ราคาด้านบนยังอิงตำบล" in txt, txt          # disclaimer เน้น (review R2)
    assert 'โอกาสชนะ%' in txt, txt
    print("✅ winrate_lines assisted (🟡 + disclaimer ราคา local)")
```

เพิ่มเรียก `test_winrate_lines_assisted()` ในบล็อกล่าง.

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL — `winrate_lines() got unexpected keyword 'conf'` หรือ assertion 🟢 disclaimer

- [ ] **Step 3: Implement** — แทน `winrate_lines` ทั้งฟังก์ชัน (`bid_field.py:82-97`):

```python
def winrate_lines(grid, conf=None, price_basis=""):
    """render ตาราง win% (pure). [] ถ้า grid None.
    conf=None → 🟢 local (ไม่มี disclaimer). conf=(emoji, scope_word) → assisted:
    เพิ่มป้าย scope + ⚠️ ย้ำว่าราคาด้านบนยังอิง price_basis (กันเข้าใจผิดว่าราคาตาราง=ราคาแนะนำ)."""
    if not grid:
        return []
    ns, rows = grid["ns"], grid["rows"]
    lines = [f"💵 โอกาสชนะตามจำนวนผู้ยื่น (งบ {grid['budget']:,.0f})"]
    lines.append("   ผู้ยื่น →   " + "  ".join(f"{k}ราย".rjust(6) for k in ns))
    for price, ws in rows:
        cells = "  ".join(f"{w}%".rjust(6) for w in ws)
        lines.append(f"   {price:>10,.0f}  {cells}")
    sd_txt = f" (±{round(grid['n_sd'])})" if len(ns) > 1 else ""
    lines.append(f"   📊 สนามนี้เฉลี่ย {round(grid['n_mean'])} ผู้ยื่น{sd_txt}")
    lines.append(f"   📈 จาก {grid['n_auctions']} งานที่มีข้อมูลผู้ยื่นครบ · {grid['n_bids']} ราย")
    if conf:
        emoji, scope_word = conf
        lines.append(f"   {emoji} โอกาส% อิง{scope_word} (พื้นที่นี้ข้อมูลบาง)")
        if price_basis:
            lines.append(f"   ⚠️ ราคาด้านบนยังอิง{price_basis} — ตารางนี้บอกเฉพาะ \"โอกาสชนะ%\"")
    lines.append("   * คอลัมน์ตรงค่าเฉลี่ย = เป้า 75/50/25 · ยิ่งผู้ยื่นเยอะ โอกาสยิ่งต่ำ")
    return lines
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_winrate_grid.py`
Expected: `✅ winrate_lines render (🟢 local)` + `✅ winrate_lines assisted` + `ALL PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): B′ winrate_lines conf tag 🟢🟡🟠 + assisted disclaimer (ราคา local sacred)"
```

---

## Task 5: `field_and_winrate` ladder orchestration + `_scope_ids`

**Files:**
- Modify: `scripts/bid_field.py` (เพิ่ม `_scope_ids`, `_CONF`, แทน `field_and_winrate`)
- Test: `scripts/test_winrate_grid.py` (อัปเดต 2 test ที่ unpack 2-tuple → 3-tuple + เพิ่ม ladder test)

- [ ] **Step 1: Write the failing tests** — อัปเดต `test_field_and_winrate_endtoend` และ `test_gate_fallback_to_old_card` ให้ unpack 3 ค่า, เพิ่ม ladder test:

ใน `test_field_and_winrate_endtoend` เปลี่ยนบรรทัด unpack:
```python
        wl, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                            district="เมือง", scope_label=" (อ.เมือง)", basis="อำเภอ")
```
และเพิ่ม assert ท้าย (ก่อน print):
```python
    assert conf is None, conf                                # ไม่ผ่อน scope → 🟢 local
```

ใน `test_gate_fallback_to_old_card` เปลี่ยน unpack:
```python
        wl, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                            district="ไม่มี", basis="อำเภอ")
    assert wl == [] and fl == [] and conf is None, (wl, fl, conf)
```

เพิ่ม ladder test ใหม่:
```python
def test_ladder_relax_to_amphoe():
    """local (ตำบล) full-field < MIN_AUCTIONS → ผ่อนไปอำเภอ → conf 🟡 + ตารางขึ้น."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    s = db.SubscriptionStore()
    bids = [{"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "780000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "860000"}]
    with db.get_connection() as conn:
        for i in range(6):                                   # 6 งานในอำเภอ (พอ), แต่ตำบลมีแค่ 2
            tb = "ตำบลโพธิ์" if i < 2 else f"ตำบลอื่น{i}"
            conn.execute("INSERT OR REPLACE INTO cgd_winners "
                         "(project_id, province, proc_type, project_name, budget, fiscal_year) VALUES (?,?,?,?,?,?)",
                         (f"L{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                          f"ก่อสร้างถนน {tb} อำเภอนาทม", 1000000, 2569))
    for i in range(6):
        s.record_bid_results(f"L{i}", bids)
    tambon_ids = ["L0", "L1"]                                # ตำบล = 2 auctions (<5)
    with db.get_connection() as conn:
        wl, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                            basis="ตำบล", project_ids=tambon_ids,
                                            cf={}, amphoe="นาทม")
    assert conf is not None and conf[0] == "🟡", conf        # ผ่อนไปอำเภอ
    assert any("โอกาสชนะตามจำนวนผู้ยื่น" in x for x in wl), wl    # ตารางขึ้น (เดิมไม่ขึ้น)
    assert any("ราคาด้านบนยังอิงตำบล" in x for x in wl), wl       # disclaimer
    print("✅ ladder: ตำบลบาง → ผ่อนอำเภอ 🟡 + ตารางขึ้น")
```

เพิ่มเรียก `test_ladder_relax_to_amphoe()` ในบล็อกล่าง.

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL — `field_and_winrate` คืน 2 ค่า (unpack 3 พัง) / ไม่มี `cf`/`amphoe` kwarg

- [ ] **Step 3: Implement** — แทน `field_and_winrate` (`bid_field.py:221-229`) + เพิ่ม helper/constant ก่อนหน้า:

```python
_CONF = {0: None, 1: ("🟡", "อำเภอ"), 2: ("🟠", "จังหวัด")}   # ระยะผ่อนจาก price scope


def _scope_ids(conn, province, tokens, cf, subdistrict=None, district=None):
    """project_ids ของ scope (คง cf จัดเต็มผ่าน _fetch_scope). [] ถ้าว่าง/error."""
    try:
        from cgd_intel import _fetch_scope
        rows, _old = _fetch_scope(conn, province, tokens,
                                  subdistrict=subdistrict, district=district, **(cf or {}))
        return [r["project_id"] for r in rows if r.get("project_id")]
    except Exception:
        return []


def field_and_winrate(conn, province, tokens, budget, subdistrict=None, district=None,
                      scope_label="", basis="", project_ids=None, cf=None, amphoe=None):
    """orchestrator: อ่าน price-scope auctions → ลองทำตาราง → ผ่อน ladder (อำเภอ→จังหวัด)
    จน gate ผ่าน. คืน (winrate_lines, field_lines[2B], conf). conf=None(🟢)/('🟡','อำเภอ')/('🟠','จังหวัด').
    n centering = price-scope auctions (local) เสมอ. 2B (field_lines) อิง price-scope."""
    if project_ids is not None:
        local_auc = _field_auctions(conn, province, tokens, project_ids=project_ids)
    else:
        local_auc = _field_auctions(conn, province, tokens, subdistrict, district)
    attempts = [local_auc]                                  # 0 = price scope (🟢)
    if amphoe and cf is not None:                           # ผ่อนได้เฉพาะตอนรู้ amphoe + cf
        attempts.append(_field_auctions(conn, province, tokens,
                        project_ids=_scope_ids(conn, province, tokens, cf, district=amphoe)))
        attempts.append(_field_auctions(conn, province, tokens,
                        project_ids=_scope_ids(conn, province, tokens, cf)))
    grid, conf, reason = None, None, "OK"
    for i, auc_ in enumerate(attempts):
        ev = _evaluate_winrate(auc_, budget, local_auctions=local_auc)
        reason = ev["fail_reason"]
        if ev.get("ok"):
            grid, conf = ev, _CONF.get(i)
            break
    _log.info("winrate basis=%s conf=%s ess=%.1f k_local=%s fail_reason=%s",
              basis, ("local" if conf is None else conf[1]) if grid else "none",
              grid["ess"] if grid else 0.0, grid["k_mid"] if grid else None, reason)
    wl = winrate_lines(grid, conf, price_basis=basis) if grid else []
    fl = field_lines(analyze_field(local_auc), budget, scope_label)
    return wl, fl, conf
```

- [ ] **Step 4: Run tests**

Run: `python scripts/test_winrate_grid.py`
Expected: `✅ ladder: ตำบลบาง → ผ่อนอำเภอ 🟡` + endtoend (conf None) + fallback + `ALL PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): B′ field_and_winrate ladder (ผ่อน price→อำเภอ→จังหวัด) + conf tag + breadcrumb log"
```

---

## Task 6: `cgd_intel.predict()` integration — replace vs append by conf

**Files:**
- Modify: `scripts/cgd_intel.py` (~586-597)
- Test: `scripts/test_cgd_intel.py` (รันยืนยันไม่ regress) + smoke ใน Task 7

- [ ] **Step 1: Write the failing test** — เพิ่มใน `scripts/test_winrate_grid.py` (integration ระดับ predict ผ่าน intel):

```python
def test_predict_assisted_keeps_local_price():
    """🟡 assisted: ตาราง win% ต่อท้าย + บล็อกราคา a/b/c local ยังอยู่ (ไม่ถูกแทน)."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    import cgd_intel as ci
    importlib.reload(ci)
    import bid_field as bf2
    importlib.reload(bf2)
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        for i in range(8):                                   # อำเภอหนา, ตำบลบาง
            tb = "โพธิ์หมากแข้ง" if i < 2 else f"อื่น{i}"
            conn.execute("INSERT OR REPLACE INTO cgd_winners (project_id, province, dept, proc_type, "
                         "project_name, winner, budget, win_price, discount_pct, fiscal_year) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (f"A{i}", "บึงกาฬ", "อบต.ทดสอบ", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                          f"ก่อสร้างถนน คสล. ตำบล{tb} อำเภอบึงโขงหลง", "หจก.ผู้ชนะ",
                          1000000, 820000, 18.0, 2569))
        s2 = db.SubscriptionStore()
    for i in range(8):
        s.record_bid_results(f"A{i}", [
            {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "780000", "priceAgree": "780000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "840000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "900000"}])
    with db.get_connection() as conn:
        ctx = ci.intel_context("บึงกาฬ", "ก่อสร้างถนน คสล. ตำบลโพธิ์หมากแข้ง อำเภอบึงโขงหลง",
                               dept_name="อบต.ทดสอบ", project_id="X1", budget=1000000, conn=conn)
    assert ctx and ctx.get("lines"), ctx
    txt = "\n".join(ctx["lines"])
    # ถ้าโผล่ตาราง assisted → ต้องมีทั้งบล็อกราคา (💡 ราคาอ้างอิง) และ disclaimer
    if "🟡" in txt or "🟠" in txt:
        assert "ราคาอ้างอิง" in txt, "assisted: ต้องคงบล็อกราคา local"
        assert "ราคาด้านบนยังอิง" in txt, txt
    print("✅ predict assisted คงราคา local (หรือ 🟢/no-table graceful)")
```

> เคสนี้ tolerant (if assisted → ตรวจ): กัน flakiness จาก resolve_location. แกนคือ "ถ้า assisted ห้ามทิ้งบล็อกราคา".

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: FAIL — ปัจจุบัน predict แทน a/b/c ด้วยตารางเสมอเมื่อ `_wl` (ไม่คงราคา) → ถ้า assisted จะไม่มี "ราคาอ้างอิง"

- [ ] **Step 3: Implement** — แก้ integration block (`cgd_intel.py:586-597`):

```python
        import bid_field as _bf                       # 2B เจ้าตลาด + B′ ตาราง win% (population เดียวกับราคา)
        _ids = [r["project_id"] for r in used_rows if r.get("project_id")]
        _lbl = (f" (ต.{tambon})" if basis == "ตำบล"
                else f" (อ.{amphoe})" if basis == "อำเภอ"
                else f" (ต.{tambon}+อ.{amphoe})" if basis.startswith("ตำบล+")
                else f" (ใน{province})")
        _wl, _fl, _conf = _bf.field_and_winrate(conn, province, tokens, budget,
                                                scope_label=_lbl, basis=basis, project_ids=_ids,
                                                cf=cf, amphoe=amphoe)
        if _wl and _conf is None:                      # 🟢 local → ตารางแทน a/b/c (consistent ทุกอย่าง local)
            lines += [""] + _wl
        elif _wl:                                      # 🟡/🟠 assisted → คงราคา local + ตารางต่อท้าย (price sacred)
            lines += [""] + predict_lines(pred, basis, contested=contested_only)
            lines += [""] + _wl
        else:                                          # ไม่มี grid → การ์ดเดิม (graceful)
            lines += [""] + predict_lines(pred, basis, contested=contested_only)
```

- [ ] **Step 4: Run tests**

Run: `python scripts/test_winrate_grid.py && python scripts/test_cgd_intel.py`
Expected: ทั้งคู่ PASS (`✅ predict assisted คงราคา local` + test_cgd_intel เดิมไม่ regress)

- [ ] **Step 5: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_winrate_grid.py
git commit -m "feat(winrate): B′ integration — 🟢 ตารางแทน a/b/c · 🟡🟠 คงราคา local + ตารางต่อท้าย (price sacred)"
```

---

## Task 7: Full suite + py_compile + verification

**Files:** ไม่มีไฟล์ใหม่ — รัน verification ตาม Definition of Done

- [ ] **Step 1: py_compile**

Run: `python -m py_compile scripts/bid_field.py scripts/cgd_intel.py scripts/test_winrate_grid.py`
Expected: no output (ผ่าน)

- [ ] **Step 2: รัน test suite ที่เกี่ยวทั้งหมด**

Run:
```bash
python scripts/test_winrate_grid.py && python scripts/test_bid_field.py && python scripts/test_cgd_intel.py && python scripts/test_winrate.py && python scripts/test_recency.py
```
Expected: ทุกไฟล์จบด้วย ALL PASS / ✅ ไม่มี AssertionError

- [ ] **Step 3: Dispatch Sophia sanity audit** (ตาม CLAUDE.md — แก้ pipeline/script ก่อน commit รวบ)

ส่ง prompt ให้ agent `sophia`: "แก้ bid_field.py (winrate B′: ladder+recency+local-n) + cgd_intel integration. ตรวจ winrate_grid/field_and_winrate ไม่ทำ predict() พัง, ราคา local ไม่ถูกบังตอน assisted, ไม่มี duplicate/silent error. คืน SAFE/STOP."
รอ verdict. STOP → แก้ก่อนไปต่อ.

- [ ] **Step 4: Update progress_log.md**

เพิ่ม entry `## งานที่ N+137: Win-Rate B′ — ladder+recency+local-n — DONE` (สถานะ, สิ่งที่ทำ, test ผ่านกี่ไฟล์, รอ deploy VPS).

- [ ] **Step 5: Final commit + Discord notify**

```bash
git add progress_log.md
git commit -m "docs(progress): N+137 Win-Rate B′ DONE (ladder+recency+local-n, 7 tests ผ่าน, รอ deploy)"
```
ส่ง Discord: "✅ Win-Rate B′ เสร็จ — ตารางขึ้นในพื้นที่ข้อมูลบาง (ladder) + ถ่วงปี + center n local · price sacred · รอกัญจน์ deploy VPS"

---

## Self-Review (เทียบ spec)

**Spec coverage:**
- Knob 1 scope ladder → Task 5 ✓ · Knob 2 recency CDF+ESS → Task 1+3 ✓ · Knob 3 local-n → Task 3 ✓
- F ก้อนเดียว (center=target) → Task 3 (`tf**(k/k_mid)`, k_mid จาก local) ✓
- price sacred (assisted คง a/b/c) → Task 6 ✓ · confidence tag 🟢🟡🟠 → Task 4+5 ✓
- assisted disclaimer (R2) → Task 4 ✓ · MIN_N_AUCTIONS=3 (R1) → Task 3 ✓ · fail_reason log (R3) → Task 3+5 ✓
- 4-tuple ไม่ทำ 2B พัง → Task 2 ✓ · breadcrumb log → Task 5 ✓
- Tests #1-10 ใน spec §11 → Task 1-6 ครอบ ✓ · DoD verifiable → Task 7 ✓

**Type consistency:** `_evaluate_winrate` คืน dict (ok/fail_reason/...) · `winrate_grid`→dict|None · `winrate_lines(grid, conf, price_basis)` · `field_and_winrate(...)→(wl,fl,conf)` · `conf`=None|(emoji,word) ใช้ตรงกันทุก task ✓

**Placeholder scan:** ไม่มี TBD/TODO — โค้ดครบทุก step ✓
