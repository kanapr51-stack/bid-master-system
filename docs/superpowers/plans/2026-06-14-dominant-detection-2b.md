# Dominant-Detection Predictor (2B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** สร้าง `scripts/bid_field.py` ตรวจ "เจ้าใหญ่ขาดลอย" จาก full-field bids (2A) แล้วเสนอ 2 ฉากทัศน์ (เจ้าใหญ่มา/ไม่มา) ต่อท้ายการ์ด D0 — graceful gate (auto-activate เมื่อข้อมูลพอ)

**Architecture:** โมดูลใหม่ pure-function `bid_field.py`: `_field_auctions` (read bid_results JOIN cgd_winners budget) → `analyze_field` (tiered detection) → `field_lines` (baht). `field_block` รวบ 3 ขั้น เรียกจาก `cgd_intel._build_intel` ต่อท้าย `predict_lines`. ไม่แก้ headline a/b/c เดิม

**Tech Stack:** Python, sqlite3, assert-style test (รัน `BMS_ENV=dev PYTHONIOENCODING=utf-8 python <file>`)

**Spec:** `docs/superpowers/specs/2026-06-14-dominant-detection-2b-design.md`

---

## File Structure

- Create: `scripts/bid_field.py` — `_median`, `_winner_idx`, `analyze_field`, `_short`, `field_lines`, `_field_auctions`, `field_block` (~120 บรรทัด, 1 ความรับผิดชอบ = field analysis)
- Create: `scripts/test_bid_field.py` — TDD tests
- Modify: `scripts/cgd_intel.py:585-587` — เรียก `field_block` ต่อท้าย predict_lines

**Data shapes:**
- auction = `list[(bidder_name: str, disc_pct: float, is_winner: bool)]`
- `analyze_field` คืน `{"tier": 0|1|2, "n_auctions": int, "pack_disc_med": float|None, "dominant": {"name","show_rate","win_disc_med","win_gap_med"}|None, "landslide_gap_med": float|None}`

---

### Task 1: analyze_field — tiered detection (core algorithm)

**Files:**
- Create: `scripts/bid_field.py`
- Create: `scripts/test_bid_field.py`

- [ ] **Step 1: เขียน failing test** สร้าง `scripts/test_bid_field.py`

```python
"""test_bid_field.py — dominant-detection: analyze_field / field_lines / _field_auctions."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf

def mk(winner, wdisc, others):
    """auction: ผู้ชนะ + others=[(name,disc)]."""
    return [(winner, wdisc, True)] + [(n, d, False) for n, d in others]

def test_tier1_named_dominant():
    auctions = [
        mk("X", 40, [("A", 20), ("B", 19), ("C", 21)]),
        mk("X", 38, [("A", 20), ("B", 18)]),
        mk("X", 42, [("D", 22), ("B", 20)]),
        mk("X", 39, [("A", 21), ("C", 19)]),
        mk("A", 23, [("B", 21), ("C", 22)]),     # X ไม่มา
    ]
    fr = bf.analyze_field(auctions)
    assert fr["tier"] == 1, fr
    assert fr["dominant"]["name"] == "X", fr
    assert abs(fr["dominant"]["show_rate"] - 0.8) < 1e-9, fr   # X ลง 4/5
    assert fr["dominant"]["win_gap_med"] > 10, fr
    print("✅ tier1 named dominant")

def test_tier2_structural():
    auctions = [
        mk("W1", 40, [("A", 20), ("B", 19)]),
        mk("W2", 38, [("C", 20), ("D", 18)]),
        mk("W3", 42, [("E", 22), ("F", 20)]),
        mk("A", 22, [("B", 21)]),                # tight
        mk("C", 23, [("D", 22)]),                # tight
    ]
    fr = bf.analyze_field(auctions)
    assert fr["tier"] == 2, fr                    # landslide เยอะ แต่ไม่มีเจ้าเด่น
    assert fr["landslide_gap_med"] == 20, fr
    print("✅ tier2 structural")

def test_tier0_tight_and_gate():
    tight = [mk(f"W{i}", 22, [("A", 21), ("B", 20)]) for i in range(5)]
    assert bf.analyze_field(tight)["tier"] == 0, "สนามสูสี → tier0"
    assert bf.analyze_field(tight[:4])["tier"] == 0, "n<MIN_AUCTIONS → gate tier0"
    print("✅ tier0 tight + gate น้อย")

test_tier1_named_dominant()
test_tier2_structural()
test_tier0_tight_and_gate()
print("ALL PASS bid_field")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'bid_field'`

- [ ] **Step 3: สร้าง `scripts/bid_field.py`** (constants + `_median` + `_winner_idx` + `analyze_field`)

```python
"""bid_field.py — ตรวจ "เจ้าใหญ่ขาดลอย" จาก full-field bids (2B). เสนอ 2 ฉากทัศน์ในการ์ด D0.
graceful gate (โชว์เฉพาะ scope ที่ข้อมูลพอ+มีโครงสร้างขาดลอย). ดู spec 2026-06-14-dominant-detection-2b."""
import sqlite3, sys, os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from cgd_intel import COMPETITIVE_SET

MIN_AUCTIONS = 5       # scope ต้องมี ≥ นี้ ถึงวิเคราะห์
MIN_APPEAR = 3         # บริษัทปรากฏ ≥ นี้ ถึง "ระบุชื่อ"
WIN_FRACTION = 0.5     # ชนะ ≥ ครึ่งที่ลง
LANDSLIDE_GAP = 10.0   # percentage points (ผู้ชนะขาดที่2)
LANDSLIDE_RATE = 0.30  # Tier2: ≥30% ของ auctions เป็น landslide
DISC_MAX = 60.0        # ตัด outlier disc (unit-price เพี้ยน)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _winner_idx(auction):
    """index ผู้ชนะ: is_winner ก่อน, fallback disc สูงสุด."""
    for i, (_n, _d, w) in enumerate(auction):
        if w:
            return i
    return max(range(len(auction)), key=lambda i: auction[i][1])


def analyze_field(auctions: list) -> dict:
    """tiered detection. auctions = [ [(name, disc_pct, is_winner)] ]. คืน dict (ดู File Structure)."""
    auctions = [a for a in auctions if len(a) >= 2]
    n = len(auctions)
    base = {"tier": 0, "n_auctions": n, "pack_disc_med": None,
            "dominant": None, "landslide_gap_med": None}
    if n < MIN_AUCTIONS:
        return base
    pack_discs, gaps = [], []
    appear, wins = defaultdict(int), defaultdict(int)
    win_disc, win_gap = defaultdict(list), defaultdict(list)
    for a in auctions:
        wi = _winner_idx(a)
        wname, wdisc, _ = a[wi]
        others = [d for j, (_n, d, _w) in enumerate(a) if j != wi]
        pack_discs += others
        second = max(others) if others else wdisc
        gap = wdisc - second
        gaps.append(gap)
        seen = set()
        for (nm, _d, _w) in a:
            if nm and nm not in seen:        # นับ 1 บริษัท/auction
                appear[nm] += 1
                seen.add(nm)
        if wname:
            wins[wname] += 1
            win_disc[wname].append(wdisc)
            win_gap[wname].append(gap)
    base["pack_disc_med"] = _median(pack_discs)
    landslide = [g for g in gaps if g > LANDSLIDE_GAP]
    # Tier 1: named dominant
    cands = []
    for name, ap in appear.items():
        if ap >= MIN_APPEAR and wins[name] / ap >= WIN_FRACTION:
            wg = _median(win_gap[name])
            if wg is not None and wg > LANDSLIDE_GAP:
                cands.append((ap, name, wg))
    if cands:
        cands.sort(reverse=True)             # appear มากสุดก่อน
        ap, name, wg = cands[0]
        base["tier"] = 1
        base["dominant"] = {"name": name, "show_rate": ap / n,
                            "win_disc_med": _median(win_disc[name]), "win_gap_med": wg}
        return base
    # Tier 2: structural landslide
    if len(landslide) / n >= LANDSLIDE_RATE:
        base["tier"] = 2
        base["landslide_gap_med"] = _median(landslide)
    return base
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: PASS — `✅ tier1 named dominant` / `✅ tier2 structural` / `✅ tier0 tight + gate น้อย`

- [ ] **Step 5: commit**

```bash
git add scripts/bid_field.py scripts/test_bid_field.py
git commit -m "feat(bid_field): 2B analyze_field — tiered dominant detection"
```

---

### Task 2: field_lines — baht rendering

**Files:**
- Modify: `scripts/bid_field.py`
- Modify: `scripts/test_bid_field.py`

- [ ] **Step 1: เพิ่ม failing test** ต่อท้าย `scripts/test_bid_field.py` (ก่อน `print("ALL PASS bid_field")`)

```python
def test_field_lines():
    # tier1: budget 1,000,000 · win_disc 40 → 600,000 · pack 20 → 800,000
    fr1 = {"tier": 1, "pack_disc_med": 20.0,
           "dominant": {"name": "ห้างหุ้นส่วนจำกัด เอ็กซ์", "show_rate": 0.8,
                        "win_disc_med": 40.0, "win_gap_med": 22.0}}
    lines = bf.field_lines(fr1, 1_000_000); txt = "\n".join(lines)
    assert "เจ้าใหญ่" in txt and "หจก. เอ็กซ์" in txt, txt   # ย่อชื่อ
    assert "600,000" in txt and "800,000" in txt, txt        # baht 2 ฉากทัศน์
    assert "80%" in txt, txt                                  # show-rate
    # tier0 / ข้อมูลน้อย → []
    assert bf.field_lines({"tier": 0, "pack_disc_med": None}, 1_000_000) == []
    assert bf.field_lines(None, 1_000_000) == []
    assert bf.field_lines(fr1, 0) == []                       # ไม่มี budget
    # tier2
    fr2 = {"tier": 2, "pack_disc_med": 20.0, "landslide_gap_med": 18.0, "dominant": None}
    l2 = "\n".join(bf.field_lines(fr2, 1_000_000))
    assert "ขาดลอย" in l2 and "800,000" in l2, l2
    print("✅ field_lines baht (tier1/2/0)")

test_field_lines()
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: FAIL — `AttributeError: module 'bid_field' has no attribute 'field_lines'`

- [ ] **Step 3: เพิ่ม `_short` + `field_lines`** ใน `scripts/bid_field.py` (หลัง `analyze_field`)

```python
def _short(name):
    """ย่อชื่อ: ห้างหุ้นส่วนจำกัด→หจก. · บริษัท→บ."""
    return name.replace("ห้างหุ้นส่วนจำกัด", "หจก.").replace("บริษัท", "บ.").strip()


def field_lines(fr: dict, budget_now) -> list:
    """บรรทัดการ์ดเจ้าใหญ่ (baht ตาม budget งานปัจจุบัน). [] ถ้า tier0/ข้อมูลน้อย/ไม่มี budget."""
    if not fr or fr.get("tier", 0) == 0 or fr.get("pack_disc_med") is None or not budget_now:
        return []
    b = float(budget_now)

    def price(disc):
        return round(b * (1 - disc / 100.0))

    pack = price(fr["pack_disc_med"])
    if fr["tier"] == 1:
        d = fr["dominant"]
        nm = _short(d["name"])
        sr = d["show_rate"] * 100
        win = price(d["win_disc_med"])
        risk = (f"   ⚠️ {nm} มาบ่อย ({sr:.0f}%) — ยื่นตื้นมีความเสี่ยง" if d["show_rate"] >= 0.5
                else f"   {nm} ลงไม่บ่อย ({sr:.0f}%) — มีโอกาสยื่นตื้น")
        return [
            f"🏆 สนามนี้มีเจ้าใหญ่: {nm} (ลง ~{sr:.0f}% ของงาน · ชนะขาดลอยเฉลี่ย {d['win_gap_med']:.0f}%)",
            f"   • ถ้า {nm} มา → ต้องยื่นต่ำกว่า ~{win:,.0f} (ระดับเจ้าใหญ่) ถึงแซง (กำไรบาง)",
            f"   • ถ้าไม่มา → กลุ่มที่เหลืออยู่ ~{pack:,.0f} → ยื่นต่ำกว่ากลุ่มนิดเดียวก็ชนะ (กำไรงาม)",
            risk,
        ]
    return [    # tier 2
        f"🏆 สนามนี้ผู้ชนะมักขาดลอย ~{fr['landslide_gap_med']:.0f}% (ไม่มีเจ้าเด่นชัด)",
        f"   • กลุ่มหลักอยู่ ~{pack:,.0f} → ถ้าคู่แข่งดุไม่มา ยื่นต่ำกว่ากลุ่มก็ชนะ",
    ]
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: PASS — `✅ field_lines baht (tier1/2/0)`

- [ ] **Step 5: commit**

```bash
git add scripts/bid_field.py scripts/test_bid_field.py
git commit -m "feat(bid_field): 2B field_lines — baht 2-scenario card (tier1/2)"
```

---

### Task 3: _field_auctions — DB read + disc + outlier + group

**Files:**
- Modify: `scripts/bid_field.py`
- Modify: `scripts/test_bid_field.py`

- [ ] **Step 1: เพิ่ม failing test** ต่อท้าย `scripts/test_bid_field.py` (ก่อน `print("ALL PASS bid_field")`)

```python
def test_field_auctions_read():
    import Sebastian_Customer_DB as db
    db.init_schema()
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners (project_id, province, proc_type, project_name, budget) "
            "VALUES (?,?,?,?,?)",
            [("J1", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน ต.นาทม", 1000000),
             ("J2", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน ต.นาทม", 2000000),
             ("JX", "ขอนแก่น", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน", 1000000)])  # นอก scope
    s = db.SubscriptionStore()
    # J1: winner ลด 30% (700k) + loser ลด 10% (900k) + outlier ลด 95% (50k → ตัด)
    s.record_bid_results("J1", [
        {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
        {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "900000"},
        {"receiveNameTh": "หจก.outlier", "receiveTin": "3", "priceProposal": "50000"}])
    s.record_bid_results("J2", [
        {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "1600000", "priceAgree": "1600000"},
        {"receiveNameTh": "หจก.ค", "receiveTin": "4", "priceProposal": "1800000"}])
    s.record_bid_results("JX", [
        {"receiveNameTh": "หจก.z", "receiveTin": "9", "priceProposal": "500000", "priceAgree": "500000"}])
    with db.get_connection() as conn:
        auctions = bf._field_auctions(conn, "นครพนม", ["ถนน"], subdistrict="นาทม")
    assert len(auctions) == 2, auctions                  # J1,J2 (JX นอกจังหวัด ตัด)
    j1 = next(a for a in auctions if any(abs(d - 30.0) < 1e-9 for _n, d, _w in a))  # J1 มี disc 30
    discs = sorted(d for _n, d, _w in j1)
    assert discs == [10.0, 30.0], discs                  # (1-700k/1M)=30, (1-900k/1M)=10 · outlier 95% ตัด
    assert any(w for _n, _d, w in j1), "มี winner flag"
    print("✅ _field_auctions read + disc + outlier filter")

test_field_auctions_read()
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: FAIL — `AttributeError: module 'bid_field' has no attribute '_field_auctions'`

- [ ] **Step 3: เพิ่ม `_field_auctions`** ใน `scripts/bid_field.py` (หลัง `field_lines`)

```python
def _field_auctions(conn, province, tokens, subdistrict=None, district=None) -> list:
    """full-field auctions ของ scope จาก bid_results JOIN cgd_winners(budget).
    คืน [ [(bidder_name, disc_pct, is_winner)] ] · ตัด outlier disc นอก [0,DISC_MAX] · graceful []."""
    pt = ",".join("?" for _ in COMPETITIVE_SET)
    like = " OR ".join("cw.project_name LIKE ?" for _ in tokens)
    where = ["cw.province=?", f"cw.proc_type IN ({pt})", f"({like})", "cw.budget>0"]
    params = [province, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    if subdistrict is not None:                  # geocode column เพี้ยน → match จากชื่องาน (เหมือน competitor_trend)
        where.append("(cw.project_name LIKE ? OR cw.project_name LIKE ?)")
        params += [f"%ตำบล{subdistrict}%", f"%ต.{subdistrict}%"]
    if district is not None:
        where.append("(cw.project_name LIKE ? OR cw.project_name LIKE ?)")
        params += [f"%อำเภอ{district}%", f"%อ.{district}%"]
    sql = ("SELECT b.project_id, b.bidder_name, b.price_proposal, b.price_agree, b.is_winner, cw.budget "
           "FROM bid_results b JOIN cgd_winners cw ON cw.project_id=b.project_id "
           "WHERE " + " AND ".join(where))
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    byp = defaultdict(list)
    for pid, name, pp, pa, isw, budget in rows:
        bid = None
        for x in (pp, pa):                        # sealed bid = proposal (winner ใช้ agree ถ้า proposal ว่าง)
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
        if disc < 0 or disc > DISC_MAX:           # ตัด outlier (unit-price เพี้ยน)
            continue
        byp[pid].append((name or "", disc, bool(isw)))
    return list(byp.values())
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: PASS — `✅ _field_auctions read + disc + outlier filter`

- [ ] **Step 5: commit**

```bash
git add scripts/bid_field.py scripts/test_bid_field.py
git commit -m "feat(bid_field): 2B _field_auctions — read+disc+outlier filter (graceful)"
```

---

### Task 4: field_block + integrate _build_intel

**Files:**
- Modify: `scripts/bid_field.py`
- Modify: `scripts/cgd_intel.py:585-587`
- Modify: `scripts/test_bid_field.py`

- [ ] **Step 1: เพิ่ม failing test** ต่อท้าย `scripts/test_bid_field.py` (ก่อน `print("ALL PASS bid_field")`)

```python
def test_field_block_endtoend_and_gate():
    import Sebastian_Customer_DB as db
    db.init_schema()
    s = db.SubscriptionStore()
    # gate: bid_results ว่าง → field_block = [] (ปลอดภัยกับ _build_intel เดิม)
    with db.get_connection() as conn:
        assert bf.field_block(conn, "สกลนคร", ["ถนน"], 1000000) == [], "scope ว่าง → []"
    # tier1 end-to-end: 5 auction เจ้าใหญ่ Y ลง 4 ชนะขาดลอย
    with db.get_connection() as conn:
        for i in range(5):
            conn.execute("INSERT OR REPLACE INTO cgd_winners (project_id, province, proc_type, project_name, budget) "
                         "VALUES (?,?,?,?,?)",
                         (f"F{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน", 1000000))
    for i in range(4):  # Y ชนะ 4 งาน ลด 40% ขาดกลุ่มที่ลด 20%
        s.record_bid_results(f"F{i}", [
            {"receiveNameTh": "หจก.วาย", "receiveTin": "1", "priceProposal": "600000", "priceAgree": "600000"},
            {"receiveNameTh": "หจก.พ", "receiveTin": "2", "priceProposal": "800000"},
            {"receiveNameTh": "หจก.ม", "receiveTin": "3", "priceProposal": "810000"}])
    s.record_bid_results("F4", [   # Y ไม่มา
        {"receiveNameTh": "หจก.พ", "receiveTin": "2", "priceProposal": "780000", "priceAgree": "780000"},
        {"receiveNameTh": "หจก.ม", "receiveTin": "3", "priceProposal": "800000"}])
    with db.get_connection() as conn:
        block = bf.field_block(conn, "นครพนม", ["ถนน"], 1000000)
    txt = "\n".join(block)
    assert "เจ้าใหญ่" in txt and "วาย" in txt, txt
    print("✅ field_block end-to-end + gate")

test_field_block_endtoend_and_gate()
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: FAIL — `AttributeError: module 'bid_field' has no attribute 'field_block'`

- [ ] **Step 3: เพิ่ม `field_block`** ใน `scripts/bid_field.py` (ท้ายไฟล์)

```python
def field_block(conn, province, tokens, budget_now, subdistrict=None, district=None) -> list:
    """read → analyze → lines. [] ถ้าไม่เข้าเงื่อนไข (graceful). จุดเชื่อม predictor."""
    auctions = _field_auctions(conn, province, tokens, subdistrict, district)
    return field_lines(analyze_field(auctions), budget_now)
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_field.py`
Expected: PASS — `✅ field_block end-to-end + gate` + `ALL PASS bid_field`

- [ ] **Step 5: เชื่อมเข้า `_build_intel`** — แก้ `scripts/cgd_intel.py` แทนบล็อก predict_lines (บรรทัด ~584-587)

แทน:
```python
    if pred:
        lines += [""] + predict_lines(pred, basis, contested=contested_only)
        if basis_old:                             # อิงข้อมูลเก่ากว่า 3 ปี — แจ้งให้ผู้ใช้รู้
            lines.append("📜 รวมข้อมูลเก่ากว่า 3 ปี (พื้นที่นี้งานน้อย) — ใช้เป็นแนวโน้ม")
```
ด้วย:
```python
    if pred:
        lines += [""] + predict_lines(pred, basis, contested=contested_only)
        if basis_old:                             # อิงข้อมูลเก่ากว่า 3 ปี — แจ้งให้ผู้ใช้รู้
            lines.append("📜 รวมข้อมูลเก่ากว่า 3 ปี (พื้นที่นี้งานน้อย) — ใช้เป็นแนวโน้ม")
        import bid_field as _bf                    # 2B: บล็อกเจ้าใหญ่ขาดลอย (graceful — [] ถ้าข้อมูลไม่พอ)
        _fb = _bf.field_block(conn, province, tokens, budget, basis_sub, basis_dist)
        if _fb:
            lines += [""] + _fb
```

- [ ] **Step 5b: regression — predictor เดิมไม่พัง** (bid_results ว่าง → ไม่มีบล็อกเพิ่ม)

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_cgd_intel.py`
Expected: PASS (ครบทุก `✅` เดิม — field_block คืน [] เพราะ bid_results ว่างใน test เหล่านี้)

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_winrate.py`
Expected: PASS

- [ ] **Step 6: commit**

```bash
git add scripts/bid_field.py scripts/test_bid_field.py scripts/cgd_intel.py
git commit -m "feat(2B): field_block + เชื่อมเจ้าใหญ่ขาดลอยเข้า _build_intel (graceful)"
```

---

### Task 5: Deploy + post-trickle tune (manual — กัญจน์)

- [ ] **Step 1: push + deploy**

```bash
git push origin main
# บน VPS:
cd /opt/bms/app && bash scripts/deploy.sh
```
(ปลอดภัย: graceful gate → บล็อกเจ้าใหญ่โผล่เฉพาะ scope ที่ bid_results พอ; scope อื่นการ์ดเหมือนเดิม)

- [ ] **Step 2: หลัง 2A trickle ครบ — validate + tune threshold** (pass สั้นๆ, ไม่บล็อก deploy)

ดู scope จริงที่ติด Tier 1/2 สมเหตุผลไหม + ปรับ const ใน `bid_field.py` (MIN_APPEAR/LANDSLIDE_GAP/...) ถ้าจำเป็น เทียบกับ `_analyze_bidfield.py` (ภาพรวม gap distribution)

---

## Self-Review

**Spec coverage:**
- §4 architecture (bid_field.py module) → Task 1-4 ✅
- §5 data read (_field_auctions + budget COALESCE จาก cgd_winners + outlier) → Task 3 ✅
- §6 algorithm (tiered, thresholds, dominant/pack/landslide, median) → Task 1 ✅
- §7 output (field_lines baht tier1/2/0) → Task 2 ✅
- §8 integration (_build_intel ต่อ predict_lines) → Task 4 step 5 ✅
- §9 gating (graceful, [] เมื่อข้อมูลน้อย) → Task 1 gate + Task 4 gate test ✅
- §10 testing (7 เคส) → tier1/2/0+gate (T1) · field_lines (T2) · read+outlier (T3) · end-to-end+gate (T4) ครบ ✅
- §11 out-of-scope (headline a/b/c, self-calibrate, predict เจ้าใหญ่มา) → ไม่มีใน plan ✅

**Placeholder scan:** ไม่มี TBD/TODO — ทุก step มีโค้ด+คำสั่งจริง ✅

**Type consistency:**
- `analyze_field(auctions) -> dict{tier,n_auctions,pack_disc_med,dominant,landslide_gap_med}` — field_lines อ่าน key ตรง (T1↔T2) ✅
- `dominant = {name, show_rate, win_disc_med, win_gap_med}` — field_lines อ่าน 4 key ตรง ✅
- `_field_auctions(conn, province, tokens, subdistrict, district) -> [[(name,disc,is_winner)]]` — analyze_field consume รูปเดียวกัน (T3↔T1) ✅
- `field_block(conn, province, tokens, budget_now, subdistrict, district)` — _build_intel เรียกด้วย (conn, province, tokens, budget, basis_sub, basis_dist) ตรงตำแหน่ง (T4) ✅
- `record_bid_results`, `cgd_winners` schema (project_id/province/proc_type/project_name/budget) — ตรงกับที่ 1b/2A ใช้ ✅
- `COMPETITIVE_SET` import จาก cgd_intel — ใช้ใน _field_auctions placeholder/params ตรงจำนวน ✅
