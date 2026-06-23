# Custom Win% Calculator — Gates Model Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** แก้ bug "โอกาสชนะ 0%" ใน Custom Win% Calculator โดยเปลี่ยนเครื่องยนต์คำนวณเป็น Gates model + per-company all-bids distribution (กรอง subtype+agency เป็นชั้น).

**Architecture:** เพิ่ม pure helpers (`gates_winrate`, `p_beat`) + DB-reading helpers (`_pooled_dist`, `_company_bid_dist`) ใน `bid_field.py` → rewrite `calc_custom_winrate` ใน `cgd_intel.py` ให้ orchestrate helpers เหล่านี้ → ปรับ call site + render ใน `portal_views.py`. ไม่แตะ schema/route.

**Tech Stack:** Python 3, sqlite3, ระบบ test เป็น plain-function + `assert` + `print("✅...")` (ไม่ใช่ pytest), seed DB ผ่าน `Sebastian_Customer_DB`.

## Global Constraints

- ภาษาไทยใน comment/docstring/ข้อความผู้ใช้ (ตาม codebase เดิม)
- ทุกฟังก์ชันที่อ่าน DB ต้อง **graceful** — `sqlite3.DatabaseError` → คืนค่าว่าง/None ไม่ throw (ห้ามทำหน้า `/portal/job` พัง)
- รัน test: `python scripts/test_bid_field.py` / `python scripts/test_cgd_intel.py` / `python scripts/test_portal_views.py` (รันไฟล์ตรงๆ — assert ทำงานตอน import)
- คงสไตล์ test เดิม: ฟังก์ชัน + assert + `print("✅ ...")`, เรียกที่ module level
- clamp `Pᵢ` ∈ [0.05, 0.95] เสมอ · ตัด outlier discount นอก `[0, DISC_MAX=60]`
- gate เลือกชั้น = **จำนวนแถวดิบ** (`MIN_OWN_BIDS=5`) ไม่ใช่ effective sample (ดู spec §4.2 design decision — ห้ามเปลี่ยนเป็น ESS)
- Discord notify ตอน commit (ตาม CLAUDE.md): `scripts/Sebastian_Discord_Notify.py`
- หลังแต่ละ task ที่แก้ logic → ส่ง Sophia sanity ก่อนไป task ถัดไป (CLAUDE.md)

---

### Task 1: Pure math helpers — `gates_winrate` + `p_beat`

**Files:**
- Modify: `scripts/bid_field.py` (เพิ่มฟังก์ชันใหม่ + constant `MIN_OWN_BIDS`)
- Test: `scripts/test_bid_field.py` (เพิ่ม test ต่อท้าย)

**Interfaces:**
- Produces:
  - `gates_winrate(probs: list[float]) -> float | None` — Gates combine `1/(1+Σ(1-Pi)/Pi)`. ตัด `None` ออกก่อน. ว่าง → `None`.
  - `p_beat(dist: list[tuple[float,float]], my_discount: float) -> float | None` — สัดส่วนถ่วงน้ำหนักของ bids ที่ `discount < my_discount`, clamp [0.05,0.95]. `dist=[(discount,weight)]`. น้ำหนักรวม≤0 → `None`.
  - constant `MIN_OWN_BIDS = 5`

- [ ] **Step 1: เขียน test ที่ fail**

เพิ่มต่อท้าย `scripts/test_bid_field.py`:

```python
def test_gates_winrate():
    # fair-share property: ทุกคน P=0.5 → 1/(N+1)
    assert abs(bf.gates_winrate([0.5, 0.5, 0.5]) - 0.25) < 1e-9, bf.gates_winrate([0.5,0.5,0.5])
    # รายเดียว → P เอง
    assert abs(bf.gates_winrate([0.9]) - 0.9) < 1e-9, bf.gates_winrate([0.9])
    # ไม่ดิ่งศูนย์เท่า Friedman: 11 ราย @0.5 → Gates=1/12≈0.083 >> Friedman 0.5^11≈0.00049
    g = bf.gates_winrate([0.5] * 11)
    assert abs(g - 1/12) < 1e-9 and g > 0.5**11 * 100, g
    # ว่าง / None ล้วน → None
    assert bf.gates_winrate([]) is None
    assert bf.gates_winrate([None, None]) is None
    # ตัด None ทิ้งก่อนคิด
    assert abs(bf.gates_winrate([0.9, None]) - 0.9) < 1e-9, bf.gates_winrate([0.9, None])
    print("✅ gates_winrate (fair-share / single / no-collapse / empty)")

def test_p_beat():
    # ลด 30% → ชนะคนที่ลด 10,20 (2/3) ไม่ชนะคนลด 40
    d = [(10.0, 1.0), (20.0, 1.0), (40.0, 1.0)]
    assert abs(bf.p_beat(d, 30.0) - 2/3) < 1e-9, bf.p_beat(d, 30.0)
    # clamp สูง: ลดลึกกว่าทุกคน → 1.0 → 0.95
    assert bf.p_beat([(10.0,1.0),(20.0,1.0)], 50.0) == 0.95
    # clamp ต่ำ: ลดตื้นกว่าทุกคน → 0 → 0.05
    assert bf.p_beat([(40.0,1.0),(50.0,1.0)], 10.0) == 0.05
    # weight สำคัญ: bid ใหม่ (40, w=1.0) ถ่วงหนักกว่า bid เก่า (10, w=0.25) → P ต่ำ
    assert abs(bf.p_beat([(10.0,0.25),(40.0,1.0)], 30.0) - 0.2) < 1e-9, bf.p_beat([(10.0,0.25),(40.0,1.0)],30.0)
    # ว่าง / น้ำหนัก 0 → None
    assert bf.p_beat([], 30.0) is None
    assert bf.p_beat([(10.0, 0.0)], 30.0) is None
    print("✅ p_beat (fraction / clamp / weighted / empty)")

test_gates_winrate()
test_p_beat()
```

- [ ] **Step 2: รัน test ให้เห็นว่า fail**

Run: `python scripts/test_bid_field.py`
Expected: FAIL — `AttributeError: module 'bid_field' has no attribute 'gates_winrate'`

- [ ] **Step 3: เพิ่ม constant + ฟังก์ชันใน `scripts/bid_field.py`**

เพิ่ม `MIN_OWN_BIDS` ใต้บรรทัด `MIN_N_AUCTIONS = 3` (ราวบรรทัด 17):

```python
MIN_OWN_BIDS = 5       # จำนวนแถวดิบขั้นต่ำต่อชั้น ก่อนเชื่อประวัติบริษัทเอง (gate นับดิบ ไม่ใช่ ESS — spec §4.2)
```

เพิ่มฟังก์ชันต่อท้ายไฟล์ (หลัง `field_and_winrate`):

```python
def gates_winrate(probs):
    """Gates (1967) combine: P_win = 1/(1+Σ(1−Pi)/Pi). แก้ Friedman collapse (∏Pi → 0 เมื่อคนเยอะ).
    probs=[Pi] (โอกาสเราชนะคู่แข่งแต่ละราย, ควร clamp (0,1) มาแล้ว). ตัด None ทิ้ง. ว่าง → None."""
    ps = [p for p in probs if p is not None]
    if not ps:
        return None
    s = sum((1.0 - p) / p for p in ps)
    return 1.0 / (1.0 + s)


def p_beat(dist, my_discount):
    """โอกาสเราชนะคู่แข่ง 1 ราย = สัดส่วนถ่วงน้ำหนักของ bids ที่ลด 'ตื้นกว่า' เรา (ราคาเขาสูงกว่า = เราชนะ).
    dist=[(discount, weight)]. clamp [0.05,0.95] (กันมั่นใจเกินจริง). น้ำหนักรวม≤0 → None."""
    tot = sum(w for _d, w in dist)
    if tot <= 0:
        return None
    below = sum(w for d, w in dist if d < my_discount)
    return max(0.05, min(0.95, below / tot))
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `python scripts/test_bid_field.py`
Expected: PASS — เห็น `✅ gates_winrate ...` และ `✅ p_beat ...` (test เดิมทั้งหมดต้องยัง pass)

- [ ] **Step 5: Commit**

```bash
git add scripts/bid_field.py scripts/test_bid_field.py
git commit -m "feat(bid_field): add gates_winrate + p_beat pure helpers (Gates model)"
```

---

### Task 2: DB distribution helpers — `_pooled_dist` + `_company_bid_dist`

**Files:**
- Modify: `scripts/bid_field.py` (เพิ่ม import + 2 ฟังก์ชัน)
- Test: `scripts/test_bid_field.py`

**Interfaces:**
- Consumes: `recency_weight`, `COMPETITIVE_SET`, `road_subtype`, `water_subtype`, `agency_market` (จาก `cgd_intel`); `_field_auctions`, `DISC_MAX`, `MIN_OWN_BIDS` (ในไฟล์เดียวกัน); `portal_views._norm_name` (lazy import)
- Produces:
  - `_pooled_dist(conn, province, tokens, subdistrict=None, district=None) -> list[tuple[float,float]]` — แบน `[(discount, weight)]` ของสนาม. graceful `[]`.
  - `_company_bid_dist(conn, name, this_subtype, this_market, min_bids=MIN_OWN_BIDS) -> tuple[list|None, str]` — เลือก distribution ของบริษัทแบบชั้น. คืน `(dist, label)` หรือ `(None, "pooled")`.

- [ ] **Step 1: ขยาย import ใน `scripts/bid_field.py`**

แก้บรรทัด 8 จาก:
```python
from cgd_intel import COMPETITIVE_SET, recency_weight
```
เป็น:
```python
from cgd_intel import COMPETITIVE_SET, recency_weight, road_subtype, water_subtype, agency_market
```

- [ ] **Step 2: เขียน test ที่ fail**

เพิ่มต่อท้าย `scripts/test_bid_field.py`:

```python
def test_pooled_and_company_dist():
    import Sebastian_Customer_DB as db
    db.init_schema()
    s = db.SubscriptionStore()
    # ชื่องาน encode subtype(concrete) + agency: local=อบต. / central=กรมทางหลวงชนบท
    LOCAL = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย{0} องค์การบริหารส่วนตำบลนาทม อำเภอนาทม จังหวัดนครพนม"
    CENTRAL = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย{0} กรมทางหลวงชนบท จังหวัดนครพนม"
    rows = []
    for i in range(6):   # 6 งาน concrete+local (อบต.)
        rows.append((f"L{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", LOCAL.format(i), 1000000, "2568"))
    for i in range(4):   # 4 งาน concrete+central (กรม) — agency ต่าง
        rows.append((f"C{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", CENTRAL.format(i), 1000000, "2568"))
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners (project_id,province,proc_type,project_name,budget,fiscal_year) "
            "VALUES (?,?,?,?,?,?)", rows)
    # หจก.ครบ: ยื่นครบ 6 local → ผ่านชั้น1 (subtype+agency). ลด 20% (800k/1M)
    for i in range(6):
        s.record_bid_results(f"L{i}", [{"receiveNameTh": "หจก.ครบ", "receiveTin": "1", "priceProposal": "800000"}])
    # หจก.ตก: ยื่น 3 local + 4 central → local=3(<5 ตกชั้น1) แต่ concrete รวม 7 → ผ่านชั้น2 (subtype)
    for i in range(3):
        s.record_bid_results(f"L{i}", [{"receiveNameTh": "หจก.ตก", "receiveTin": "2", "priceProposal": "850000"}])
    for i in range(4):
        s.record_bid_results(f"C{i}", [{"receiveNameTh": "หจก.ตก", "receiveTin": "2", "priceProposal": "850000"}])
    with db.get_connection() as conn:
        # pooled: สนามถนน นครพนม → ต้องมี bids
        pooled = bf._pooled_dist(conn, "นครพนม", ["ถนน"])
        assert len(pooled) > 0 and all(len(t) == 2 for t in pooled), pooled
        # หจก.ครบ → ชั้น 1 (subtype+agency), label มีจำนวน
        dist1, lab1 = bf._company_bid_dist(conn, "หจก.ครบ", "concrete", "local")
        assert dist1 is not None and "หน่วยงาน" in lab1, (lab1, len(dist1 or []))
        assert len(dist1) == 6, dist1
        # หจก.ตก → concrete+local=3 <5 → ตกมาชั้น 2 (subtype only) = 7
        dist2, lab2 = bf._company_bid_dist(conn, "หจก.ตก", "concrete", "local")
        assert dist2 is not None and len(dist2) == 7, (lab2, len(dist2 or []))
        assert "ประเภทงาน" in lab2, lab2
        # ไม่มีประวัติ → (None, 'pooled')
        d3, lab3 = bf._company_bid_dist(conn, "หจก.ไม่มีเลย", "concrete", "local")
        assert d3 is None and lab3 == "pooled", (d3, lab3)
    print("✅ _pooled_dist + _company_bid_dist (layered raw-count gate)")

test_pooled_and_company_dist()
```

- [ ] **Step 3: รัน test ให้เห็นว่า fail**

Run: `python scripts/test_bid_field.py`
Expected: FAIL — `AttributeError: ... '_pooled_dist'`

- [ ] **Step 4: เพิ่ม 2 ฟังก์ชันใน `scripts/bid_field.py`** (ต่อจาก Task 1)

```python
def _pooled_dist(conn, province, tokens, subdistrict=None, district=None):
    """สนามทั่วไป — แบน _field_auctions เป็น [(discount, recency_weight)]. graceful []."""
    auc = _field_auctions(conn, province, tokens, subdistrict=subdistrict, district=district)
    return [(bid[1], recency_weight(bid[3] if len(bid) > 3 else None)) for a in auc for bid in a]


def _company_bid_dist(conn, name, this_subtype, this_market, min_bids=MIN_OWN_BIDS):
    """ประวัติยื่นจริงของบริษัท (all-bids) เลือกชั้นเจาะจงสุดที่จำนวนดิบ ≥ min_bids:
    ชั้น1 subtype+agency → ชั้น2 subtype → ชั้น3 ทุกงาน. ทุกชั้นบาง → (None,'pooled').
    gate = จำนวนดิบ (spec §4.2 — recency ใช้ในการคิด P เท่านั้น ไม่ใช่เกณฑ์ตกชั้น)."""
    import portal_views as _pv
    core = _pv._norm_name(name)
    if not core:
        return None, "pooled"
    pt = ",".join("?" for _ in COMPETITIVE_SET)
    sql = ("SELECT b.price_proposal, cw.budget, cw.project_name, cw.fiscal_year "
           "FROM bid_results b JOIN cgd_winners cw ON cw.project_id=b.project_id "
           f"WHERE b.normalized_name=? AND cw.proc_type IN ({pt}) "
           "AND cw.budget>0 AND CAST(b.price_proposal AS REAL)>0")
    try:
        rows = conn.execute(sql, (core, *COMPETITIVE_SET)).fetchall()
    except sqlite3.DatabaseError:
        return None, "pooled"
    tagged = []                                    # (discount, weight, subtype, market)
    for pp, budget, pname, fy in rows:
        try:
            bid = float(pp); bud = float(budget)
        except (TypeError, ValueError):
            continue
        if bid <= 0 or bud <= 0:
            continue
        disc = (bud - bid) / bud * 100.0
        if disc < 0 or disc > DISC_MAX:
            continue
        st = road_subtype(pname) or water_subtype(pname)
        tagged.append((disc, recency_weight(fy), st, agency_market(pname)))
    layers = []                                    # (label, predicate) เรียงเจาะจง→กว้าง
    if this_subtype and this_market:
        layers.append(("ตรงงาน+หน่วยงาน", lambda st, mk: st == this_subtype and mk == this_market))
    if this_subtype:
        layers.append(("ตรงประเภทงาน", lambda st, mk: st == this_subtype))
    if this_market and not this_subtype:
        layers.append(("ตรงหน่วยงาน", lambda st, mk: mk == this_market))
    layers.append(("ทุกประเภทงาน", lambda st, mk: True))
    for label, pred in layers:
        d = [(disc, w) for disc, w, st, mk in tagged if pred(st, mk)]
        if len(d) >= min_bids:
            return d, f"{label} {len(d)} ครั้ง"
    return None, "pooled"
```

- [ ] **Step 5: รัน test ให้ผ่าน**

Run: `python scripts/test_bid_field.py`
Expected: PASS — `✅ _pooled_dist + _company_bid_dist ...` (test เดิมทั้งหมดยัง pass)

- [ ] **Step 6: Sophia sanity + Commit**

ส่ง Sophia ตรวจ (แก้ bid_field อ่าน DB) — prompt: "เพิ่ม `_pooled_dist`/`_company_bid_dist` ใน bid_field.py (per-company all-bids layered). ตรวจ query ถูก scope/proc_type, ไม่มี silent error". รอ verdict SAFE.

```bash
git add scripts/bid_field.py scripts/test_bid_field.py
git commit -m "feat(bid_field): add _pooled_dist + layered _company_bid_dist (per-company all-bids)"
```

---

### Task 3: Rewrite `calc_custom_winrate` (Gates orchestration)

**Files:**
- Modify: `scripts/cgd_intel.py` — rewrite `calc_custom_winrate` (บรรทัด ~906-947)
- Test: `scripts/test_cgd_intel.py` — แทน test `calc_custom_winrate` เดิม (บรรทัด ~459-513)

**Interfaces:**
- Consumes: `bid_field._pooled_dist`, `bid_field._company_bid_dist`, `bid_field.p_beat`, `bid_field.gates_winrate` (Task 1-2); `road_subtype`, `water_subtype`, `agency_market` (ไฟล์เดียวกัน); `portal_views._norm_name`
- Produces: `calc_custom_winrate(conn, province, tokens, project_name, dept_name, district, my_price, budget, selected_names, extra_names) -> dict | None`
  คืน `{"my_discount_pct": float, "overall_win_pct": int, "breakdown": [{"name": str, "win_pct_against": int, "source": str, "has_history": bool}]}` หรือ `None`

- [ ] **Step 0: แยก DB ของ test_cgd_intel.py ออกจาก prod (สำคัญ — กัน seed ลง bms_customers.db จริง)**

`test_cgd_intel.py` ปัจจุบันไม่ตั้ง `BMS_DATA_DIR` → `Sebastian_Customer_DB` จะชี้ `data/bms_customers.db` จริง. แก้บรรทัด 2-4 (top imports) ให้ตั้ง temp dir **ก่อน** import ใดๆ ที่อาจ load `Sebastian_Customer_DB`:

แทน:
```python
import os, sys, sqlite3, csv; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("BMS_FOLLOW_SECRET", "test-secret-cgd-intel")
```
ด้วย:
```python
import os, sys, sqlite3, csv, tempfile; from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()   # isolate Sebastian_Customer_DB ออกจาก prod (seed ลง temp)
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("BMS_FOLLOW_SECRET", "test-secret-cgd-intel")
```

- [ ] **Step 1: แทน test เดิมใน `scripts/test_cgd_intel.py`**

ลบ `_calc_fixture_rows` + test 5 ตัว (`test_calc_custom_winrate_*`, บรรทัด ~450-513) แล้วใส่แทน (หมายเหตุ: ใช้ `db.get_connection()` ตัวเดียวกันทั้ง seed และเรียก calc — conn เดียว DB เดียว):

```python
def _seed_calc_db():
    """seed สนามถนนคอนกรีต อบต.นครพนม + คู่แข่ง 1 รายมีประวัติลดลึก (หจก.ลึก)."""
    import Sebastian_Customer_DB as db
    db.init_schema()
    s = db.SubscriptionStore()
    LOCAL = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย{0} องค์การบริหารส่วนตำบลนาทม อำเภอนาทม จังหวัดนครพนม"
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners (project_id,province,proc_type,project_name,budget,fiscal_year) "
            "VALUES (?,?,?,?,?,?)",
            [(f"K{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", LOCAL.format(i), 1000000, "2568")
             for i in range(8)])
    # สนาม: หลายบริษัทลดตื้น ~10-15% (เป็น pooled baseline)
    for i in range(8):
        s.record_bid_results(f"K{i}", [
            {"receiveNameTh": f"หจก.สนาม{i}", "receiveTin": str(100+i), "priceProposal": "880000"},
            {"receiveNameTh": "หจก.ลึก", "receiveTin": "9", "priceProposal": "650000"}])  # ลึก ลด 35%
    return db

def test_calc_custom_winrate_known_deep_competitor():
    db = _seed_calc_db()
    with db.get_connection() as conn:
        # เราลด 30% (700k/1M). คู่แข่ง 'หจก.ลึก' ลด 35% บ่อย → เขามักชนะเรา → P(เราชนะ) ต่ำ
        out = ci.calc_custom_winrate(conn, "นครพนม", ["ถนน"],
                                     "ก่อสร้างถนนคอนกรีตเสริมเหล็ก องค์การบริหารส่วนตำบลนาทม",
                                     "องค์การบริหารส่วนตำบลนาทม",
                                     "นาทม", my_price=700000, budget=1000000,
                                     selected_names=["หจก.ลึก"], extra_names=[])
    assert out is not None, out
    assert out["my_discount_pct"] == 30.0, out
    b = out["breakdown"][0]
    assert b["name"] == "หจก.ลึก" and b["has_history"] is True, b
    assert b["win_pct_against"] > 50, b          # หจก.ลึก ลดลึกกว่าเรา → เขาชนะเราเกินครึ่ง
    print("✅ calc_custom_winrate known deep competitor")

def test_calc_custom_winrate_gates_no_collapse():
    """regression bug 0%: คู่แข่งไม่รู้จัก 11 ราย (pooled) + เราลดลึก → overall ต้อง >0 (Gates ไม่ดิ่งศูนย์)."""
    db = _seed_calc_db()
    extras = [f"บริษัทไม่รู้จัก {i}" for i in range(11)]
    with db.get_connection() as conn:
        out = ci.calc_custom_winrate(conn, "นครพนม", ["ถนน"],
                                     "ก่อสร้างถนนคอนกรีตเสริมเหล็ก องค์การบริหารส่วนตำบลนาทม",
                                     "องค์การบริหารส่วนตำบลนาทม",
                                     "นาทม", my_price=650000, budget=1000000,   # ลด 35% (ลึก)
                                     selected_names=[], extra_names=extras)
    assert out is not None, out
    assert len(out["breakdown"]) == 11 and all(not b["has_history"] for b in out["breakdown"]), out
    # Gates: 11 ราย pooled ที่เราลดลึก → ต้องไม่ใช่ 0 และไม่เกิน 100
    assert 0 < out["overall_win_pct"] <= 100, out["overall_win_pct"]
    # ทุกรายใช้ source = สนามทั่วไป
    assert all(b["source"] == "สนามทั่วไป" for b in out["breakdown"]), out
    print("✅ calc_custom_winrate Gates no-collapse (regression bug 0%)")

def test_calc_custom_winrate_dedupe_and_invalid():
    db = _seed_calc_db()
    with db.get_connection() as conn:
        # ติ๊ก + พิมพ์ชื่อเดียวกัน → นับครั้งเดียว
        out = ci.calc_custom_winrate(conn, "นครพนม", ["ถนน"], "ถนนคอนกรีต อบต.", "อบต.",
                                     "นาทม", 700000, 1000000, ["หจก.ลึก"], ["หจก.ลึก"])
        assert out is not None and len(out["breakdown"]) == 1, out
        # invalid inputs → None
        assert ci.calc_custom_winrate(conn, "นครพนม", ["ถนน"], "x", "y", "นาทม", 0, 1000000, ["หจก.ลึก"], []) is None
        assert ci.calc_custom_winrate(conn, "นครพนม", ["ถนน"], "x", "y", "นาทม", "abc", 1000000, ["หจก.ลึก"], []) is None
        assert ci.calc_custom_winrate(conn, "นครพนม", ["ถนน"], "x", "y", "นาทม", 700000, 1000000, [], []) is None
        assert ci.calc_custom_winrate(conn, "นครพนม", ["ถนน"], "x", "y", "นาทม", 700000, 0, ["หจก.ลึก"], []) is None
    print("✅ calc_custom_winrate dedupe + invalid")

test_calc_custom_winrate_known_deep_competitor()
test_calc_custom_winrate_gates_no_collapse()
test_calc_custom_winrate_dedupe_and_invalid()
```

แก้ runner block ท้ายไฟล์ (บรรทัด ~542-546) — เปลี่ยนชื่อ test 5 ตัวเดิมเป็น 3 ตัวใหม่นี้ (ถ้ามี).

- [ ] **Step 2: รัน test ให้เห็นว่า fail**

Run: `python scripts/test_cgd_intel.py`
Expected: FAIL — `TypeError` (signature เก่ารับ args ไม่ตรง) หรือ assert fail

- [ ] **Step 3: Rewrite `calc_custom_winrate` ใน `scripts/cgd_intel.py`**

แทนทั้งฟังก์ชัน (บรรทัด ~906-947) ด้วย:

```python
def calc_custom_winrate(conn, province, tokens, project_name, dept_name, district,
                        my_price, budget, selected_names, extra_names):
    """คำนวณโอกาสชนะเจาะจงคู่แข่ง (rebuild 2026-06-23, Gates model).
    Pᵢ = โอกาสเราชนะคู่แข่ง i (จากประวัติยื่นจริงรายบริษัท กรอง subtype+agency เป็นชั้น,
    ไม่มีประวัติ → สนามทั่วไป). รวมด้วย Gates 1/(1+Σ(1-Pi)/Pi) แทนการคูณ (กัน collapse).
    คืน None ถ้าราคา/budget ไม่ถูกต้อง หรือไม่มีคู่แข่ง/ไม่มีข้อมูลเลย. ดู spec 2026-06-23-winrate-calc-gates-model."""
    import portal_views as _pv
    import bid_field as _bf
    try:
        budget_f = float(budget)
        price_f = float(my_price)
    except (TypeError, ValueError):
        return None
    if budget_f <= 0 or price_f <= 0:
        return None
    my_discount_pct = max(0.0, (budget_f - price_f) / budget_f * 100)
    raw = [n.strip() for n in (list(selected_names) + list(extra_names)) if n and str(n).strip()]
    seen, names = set(), []
    for n in raw:
        core = _pv._norm_name(n)
        if core and core not in seen:
            seen.add(core)
            names.append(n)
    if not names:
        return None
    this_subtype = road_subtype(project_name) or water_subtype(project_name)
    this_market = agency_market(dept_name)
    pooled = _bf._pooled_dist(conn, province, tokens, district=district)
    breakdown, probs = [], []
    for nm in names:
        dist, source = _bf._company_bid_dist(conn, nm, this_subtype, this_market)
        has_history = dist is not None
        if dist is None:
            dist, source = pooled, "สนามทั่วไป"
        p = _bf.p_beat(dist, my_discount_pct)
        if p is None:
            continue                                # ไม่มีข้อมูลแม้แต่ pooled → ข้ามราย
        probs.append(p)
        breakdown.append({"name": nm, "win_pct_against": round((1 - p) * 100),
                          "source": source, "has_history": has_history})
    if not probs:
        return None
    p_win = _bf.gates_winrate(probs)
    return {"my_discount_pct": round(my_discount_pct, 1),
            "overall_win_pct": round(p_win * 100), "breakdown": breakdown}
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `python scripts/test_cgd_intel.py`
Expected: PASS — เห็น `✅ calc_custom_winrate known deep competitor` / `... Gates no-collapse ...` / `... dedupe + invalid`

- [ ] **Step 5: Sophia sanity + Commit**

ส่ง Sophia — prompt: "Rewrite calc_custom_winrate เป็น Gates model + per-company all-bids. ตรวจว่า regression (คู่แข่งเยอะ → overall ไม่เป็น 0), invalid inputs คืน None, ไม่มี silent error". รอ SAFE.

```bash
git add scripts/cgd_intel.py scripts/test_cgd_intel.py
git commit -m "feat(cgd_intel): rewrite calc_custom_winrate with Gates model + per-company all-bids"
```

---

### Task 4: Wire portal_views (call site + render) + manual smoke

**Files:**
- Modify: `scripts/portal_views.py` — call site ใน `job_detail` (บรรทัด ~93-99) + `_render_custom_calc_form` result block (บรรทัด ~532-541)
- Test: `scripts/test_portal_views.py` — `test_job_detail_custom_calc` (บรรทัด ~268) + render test (บรรทัด ~360)

**Interfaces:**
- Consumes: `cgd_intel.calc_custom_winrate` (signature ใหม่จาก Task 3), `cgd_intel.match_keywords`, `intel_ctx["amphoe"]`
- Produces: `data["custom_calc"]` มี breakdown fields `{name, win_pct_against, source, has_history}` (render ใช้ `source` แทน note เดิม)

- [ ] **Step 1: แก้ call site ใน `job_detail` (`scripts/portal_views.py` บรรทัด ~93-99)**

แทน block:
```python
            if calc_params and intel_ctx.get("scope_rows") and company_tables:
                fallback = company_tables[0]
                custom_calc = cgd_intel.calc_custom_winrate(
                    intel_ctx["scope_rows"],
                    {"median": fallback.get("median"), "p25": fallback.get("p25"), "p75": fallback.get("p75")},
                    calc_params.get("my_price"), budget,
                    calc_params.get("selected_names") or [], calc_params.get("extra_names") or [])
```
ด้วย:
```python
            if calc_params and company_tables:
                custom_calc = cgd_intel.calc_custom_winrate(
                    conn, (ps["province"] if ps else "") or "",
                    cgd_intel.match_keywords((ps["project_name"] if ps else "") or ""),
                    (ps["project_name"] if ps else "") or "", dept_name,
                    intel_ctx.get("amphoe"),
                    calc_params.get("my_price"), budget,
                    calc_params.get("selected_names") or [], calc_params.get("extra_names") or [])
```

- [ ] **Step 2: แก้ render result block ใน `_render_custom_calc_form` (บรรทัด ~532-541)**

แทน block `if custom_calc:` (ถึงก่อน `elif`) ด้วย:
```python
    if custom_calc:
        out.append(f"<div class=\"calcresult\"><div class=\"big\">🎯 โอกาสชนะของคุณรวม: "
                   f"{custom_calc['overall_win_pct']}%</div>"
                   f"<div class=\"meta\">ราคาของคุณ = ลด {custom_calc['my_discount_pct']}%</div>")
        for b in custom_calc["breakdown"]:
            src = b.get("source") or ""
            src_note = f" ({src})" if src else ""
            out.append(f"<div class=\"crow\"><span>{_h.escape(b['name'])}{src_note}</span>"
                       f"<span>ชนะคุณ ~{b['win_pct_against']}%</span></div>")
        out.append("<div class=\"note\">*โอกาส% ประเมินจากนิสัยการยื่นราคาของคู่แข่งในงานประเภท+หน่วยงาน"
                   "แบบเดียวกัน (โมเดล Gates) — เป็นการประมาณ ไม่ใช่การรับประกัน</div></div>")
```

- [ ] **Step 3: แก้ test ใน `scripts/test_portal_views.py`**

(3a) `test_job_detail_custom_calc` (บรรทัด ~268): นี่เป็น **wiring test** — ตรวจว่า `job_detail` ส่ง args ถูกตัวให้ `calc_custom_winrate` แล้วแนบผลเข้า `data["custom_calc"]`. **ห้าม** seed Sebastian DB จริง เพราะ `job_detail` รัน calc บน conn in-memory `c` (จาก `_seed()`) ไม่ใช่ไฟล์ DB — mismatch. ใช้ monkeypatch `calc_custom_winrate` แทน. การคิดเลขจริง end-to-end ครอบคลุมแล้วใน Task 3. แทนฟังก์ชันด้วย:
```python
def test_job_detail_custom_calc():
    orig_ctx = cgd_intel.intel_context
    orig_calc = cgd_intel.calc_custom_winrate
    cgd_intel.intel_context = lambda *a, **k: {
        "lines": [], "amphoe": "นาทม",
        "company_tables": [{"label": "x", "n": 5, "conf_tag": "🟢 มั่นใจ",
                            "p25": 10.0, "p75": 20.0, "median": 15.0,
                            "companies": [{"name": "หจก.A", "tin": "1", "games": 3, "median": 12.0,
                                           "p25": 10.0, "p75": 15.0, "project_ids": ["K0"]}]}],
        "winrate_table": None, "scope_rows": [], }
    captured = {}
    def fake_calc(conn, province, tokens, project_name, dept_name, district,
                  my_price, budget, selected_names, extra_names):
        captured.update(province=province, tokens=tokens, district=district,
                        my_price=my_price, selected=selected_names)
        return {"my_discount_pct": 10.0, "overall_win_pct": 55, "breakdown": []}
    cgd_intel.calc_custom_winrate = fake_calc
    try:
        c = _seed()
        d = pv.job_detail(c, "69010000001",
                          calc_params={"my_price": "900000", "selected_names": ["หจก.A"], "extra_names": []})
        assert d["custom_calc"] == {"my_discount_pct": 10.0, "overall_win_pct": 55, "breakdown": []}, d
        # job_detail ส่ง args ถูก: district จาก intel_ctx amphoe, my_price/selected จาก calc_params
        assert captured["district"] == "นาทม" and captured["my_price"] == "900000", captured
        assert captured["selected"] == ["หจก.A"], captured
        # ไม่ส่ง calc_params → ไม่เรียก calc, custom_calc None
        d2 = pv.job_detail(c, "69010000001")
        assert d2["custom_calc"] is None, d2
        # intel_context None → graceful, ไม่ throw
        cgd_intel.intel_context = lambda *a, **k: None
        d3 = pv.job_detail(c, "69010000001",
                          calc_params={"my_price": "900000", "selected_names": ["หจก.A"], "extra_names": []})
        assert d3["custom_calc"] is None, d3
    finally:
        cgd_intel.intel_context = orig_ctx
        cgd_intel.calc_custom_winrate = orig_calc
    print("OK job_detail_custom_calc")
```

(3b) render test (บรรทัด ~360-366): แทน `data_calc["custom_calc"]` mock + assert ให้ตรง breakdown ใหม่:
```python
data_calc["custom_calc"] = {"my_discount_pct": 15.0, "overall_win_pct": 62,
                            "breakdown": [{"name": "หจก.A", "win_pct_against": 30,
                                           "source": "ตรงงาน+หน่วยงาน 12 ครั้ง", "has_history": True}]}
html_calc = pv.render_job_page(data_calc, "tok", 0)
assert "โอกาสชนะของคุณรวม: 62%" in html_calc, html_calc
assert "หจก.A" in html_calc and "ชนะคุณ ~30%" in html_calc, html_calc
assert "ตรงงาน+หน่วยงาน 12 ครั้ง" in html_calc, html_calc
assert "โมเดล Gates" in html_calc, html_calc
print("OK render_job_page_custom_calc_form")
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `python scripts/test_portal_views.py`
Expected: PASS — `OK job_detail_custom_calc` + `OK render_job_page_custom_calc_form` (test อื่นยัง pass)

- [ ] **Step 5: รัน test ทั้ง 3 ไฟล์ + Sophia sanity**

Run:
```bash
python scripts/test_bid_field.py && python scripts/test_cgd_intel.py && python scripts/test_portal_views.py
```
Expected: ทุกไฟล์ PASS

ส่ง Sophia — prompt: "Wire calc_custom_winrate ใหม่เข้า portal_views (call site + render). ตรวจ end-to-end job_detail ไม่พัง, render ออก field ครบ". รอ SAFE.

- [ ] **Step 6: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal_views): wire Gates calc_custom_winrate (call site + render + disclaimer)"
```

- [ ] **Step 7: Manual smoke บน VPS (verification — ไม่ใช่ code)**

หลัง merge+deploy: เปิด `/portal/job?...&pid=69059453079` กรอกราคา 1,145,000 + ติ๊กคู่แข่งจริง → ยืนยัน overall **ไม่ใช่ 0%** (คาด ~5-10%) และ breakdown โชว์ source ต่อราย. เทียบเลขกับ spec §3 (Gates 7.5%).

---

## Self-Review

**1. Spec coverage:**
- §2 Gates formula → Task 1 `gates_winrate` ✓
- §4.1 my_discount → Task 3 ✓
- §4.2 layered subtype+agency, raw-count gate → Task 2 `_company_bid_dist` ✓
- §4.3 pooled fallback → Task 2 `_pooled_dist` ✓
- §4.4 p_beat clamp → Task 1 `p_beat` ✓
- §4.5 Gates combine, M unknowns บวกตรงๆ → Task 3 (loop ใส่ทุก p เข้า probs) ✓
- §5 components (5 ฟังก์ชัน + signature ใหม่) → Task 1-4 ✓
- §6 edge cases (ไม่มีคู่แข่ง/price invalid/ประวัติบาง/pooled ว่าง/dedupe) → Task 3 test + logic ✓
- §7 disclaimer Gates → Task 4 render ✓
- §8 testing (gates fair-share, no-collapse regression, layer selection, render) → Task 1-4 tests ✓

**2. Placeholder scan:** ไม่มี TBD/TODO — ทุก step มีโค้ดจริง ✓

**3. Type consistency:**
- `_company_bid_dist` คืน `(dist, label)` ใช้ตรงกันใน Task 3 (`dist, source = ...`) ✓
- breakdown fields `{name, win_pct_against, source, has_history}` ตรงกัน Task 3 (สร้าง) ↔ Task 4 (render `b['win_pct_against']`, `b.get('source')`) ✓
- `gates_winrate`/`p_beat`/`_pooled_dist` signature ตรงกัน Task 1-2 (สร้าง) ↔ Task 3 (เรียก `_bf.gates_winrate(probs)`, `_bf.p_beat(dist, my_discount_pct)`, `_bf._pooled_dist(conn, province, tokens, district=district)`) ✓
- `calc_custom_winrate` signature ใหม่ตรงกัน Task 3 (def) ↔ Task 4 call site ✓
