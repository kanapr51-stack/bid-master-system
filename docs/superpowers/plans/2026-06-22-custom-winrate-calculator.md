# Custom Win% Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user on `/portal/job` type their own planned bid price and pick/type specific competitor companies, and get a calculated win% against those named competitors (not the generic N-bidders statistics already on the page).

**Architecture:** A new pure function in `cgd_intel.py` (`calc_custom_winrate`) reuses the scope `rows` and per-company stats already computed for `company_tables` — no new DB queries, no schema change. `portal_views.job_detail()` gains an optional `calc_params` argument that, when present, calls this function and attaches the result to the page data. A new `POST /portal/job/calc` route in `bms_api.py` parses the form and 303-redirects to the existing `GET /portal/job` route with the inputs encoded as query params (so the result is computed on GET, refresh-safe, no DB write needed for a one-off "what-if").

**Tech Stack:** Python, SQLite, FastAPI, plain HTML forms (no JavaScript — matches the rest of the portal).

## Global Constraints

- ไม่มี JavaScript ในหน้า portal เลย — ฟอร์มต้องเป็น plain HTML `<form method="post">` (จาก spec §3)
- ใช้ `MIN_GAMES_FOR_IQR = 3` (ค่าคงที่ที่มีอยู่แล้วใน `cgd_intel.py:66`) เป็นเกณฑ์ "มีประวัติพอ" — ไม่ใช้เลข 2 ที่เคยพิมพ์ผิดใน draft แรกของ spec
- สูตรทิศทางถูกต้อง (แก้ไว้ใน spec แล้ว): `win_pct_against` (คู่แข่งชนะเรา) = `round((1-CDF)*100)`; `overall_win_pct` = `product((100-win_pct_against_i)/100) * 100`
- ใส่ disclaimer "อิงจากสถิติตอนที่บริษัทนั้นชนะในอดีต ไม่ใช่ทุกครั้งที่เขายื่นซอง" ในหน้าผลลัพธ์เสมอ (จาก spec §5)
- ไม่แก้ schema/DB — ใช้ rows/company_tables ที่มีอยู่แล้วทั้งหมด (จาก spec §6)
- Backfill สกลนคร (residential fetch ของ N+164) รันอยู่เบื้องหลังคนละ process ไม่เกี่ยวกับงานนี้ — ห้ามไปแก้ไฟล์ `data/_backfill_home/*` หรือ `scripts/_backfill_home_*.py`

---

## Task 1: `cgd_intel.py` — expose `median` ใน company_tables blocks + expose scope rows

**Files:**
- Modify: `scripts/cgd_intel.py` (`_build_intel`, 4 จุดที่ append เข้า `company_tables` + จุด `return` สุดท้าย)
- Test: `scripts/test_cgd_intel.py`

**Interfaces:**
- Consumes: ตัวแปร local ที่มีอยู่แล้วในแต่ละ branch ของ `_build_intel()` — `tmed`/`amed`/`pmedn`/`fmed` (ค่า median ที่คำนวณไว้แล้วจาก `_scope_block()` แต่ไม่เคยถูกเก็บเข้า `company_tables`)
- Produces: `company_tables[i]["median"]` (float|None) ทุก block, และ `_build_intel()`'s return dict ได้ key ใหม่ `"scope_rows": used_rows` (list[dict] — แถวเดียวกับที่ใช้ทำนายราคา/company_tables ของ block ที่กว้างที่สุด/ล่าสุดที่ resolve ได้) ที่ Task 2 จะใช้ต่อ

- [ ] **Step 1: Write the failing test**

เปิด `scripts/test_cgd_intel.py` หา `test_build_intel_company_tables_and_winrate_table()` (มีอยู่แล้ว ดูจาก `_fixture_conn()`) แล้วเพิ่ม assertion ใหม่ต่อจาก assertion เดิมในฟังก์ชันนี้ (ก่อนบรรทัด `print("✅ _build_intel: company_tables + winrate_table keys present...")`):

```python
    assert "median" in blk, blk                            # N+168: ต้องมี median ระดับ block ด้วย (ไม่ใช่แค่ p25/p75)
    assert "scope_rows" in ctx and isinstance(ctx["scope_rows"], list) and ctx["scope_rows"], ctx.keys()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scripts && BMS_ENV=dev python test_cgd_intel.py`
Expected: `AssertionError` ที่บรรทัด `assert "median" in blk` (KeyError-style — key ไม่มี)

- [ ] **Step 3: Implement**

ใน `scripts/cgd_intel.py` แก้ทั้ง 4 จุดที่ `company_tables.append(...)` (อยู่ในฟังก์ชัน `_build_intel`) ให้เพิ่ม key `"median"`:

จุดที่ 1 (บล็อกตำบล):
```python
                company_tables.append({"label": f"🏘 ในตำบล{tambon}", "n": _n,
                                       "conf_tag": _conf_tag(_n, t25, t75), "p25": t25, "p75": t75,
                                       "median": tmed, "companies": t_cos})
```

จุดที่ 2 (บล็อกอำเภอ):
```python
                company_tables.append({"label": f"🏙 ในอำเภอ{amphoe}", "n": _n,
                                       "conf_tag": _conf_tag(_n, a25, a75), "p25": a25, "p75": a75,
                                       "median": amed, "companies": a_cos})
```

จุดที่ 3 (บล็อกจังหวัดเดี่ยว — เมื่อ `amphoe` เป็น None):
```python
        company_tables.append({"label": f"🏙 ใน{province}", "n": _n,
                               "conf_tag": _conf_tag(_n, p25, p75), "p25": p25, "p75": p75,
                               "median": pmedn, "companies": p_cos})
```

จุดที่ 4 (province fallback):
```python
            company_tables.append({"label": f"🗺 ทั้งจังหวัด{province} (ข้ามพื้นที่)", "n": _n,
                                   "conf_tag": _conf_tag(_n, f25, f75), "p25": f25, "p75": f75,
                                   "median": fmed, "companies": f_cos})
```

แก้ `return` statement สุดท้ายของ `_build_intel()` (อยู่ท้ายฟังก์ชัน ต่อจาก loop เติม `tin`):
```python
    return {"lines": lines, "prediction": pred, "tambon": tambon, "amphoe": amphoe,
            "explain": explain, "company_tables": company_tables, "winrate_table": winrate_table,
            "scope_rows": used_rows}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd scripts && BMS_ENV=dev python test_cgd_intel.py`
Expected: `ALL PASS (moi location disambiguation)` (ไม่มี traceback)

- [ ] **Step 5: Run broader regression (touches a hot function)**

Run: `cd scripts && BMS_ENV=dev python test_road_subtype.py && BMS_ENV=dev python test_water_subtype.py && BMS_ENV=dev python test_recency.py && BMS_ENV=dev python test_portal_views.py`
Expected: ทุกไฟล์ `ALL PASS`/`OK` (ฟังก์ชันที่แก้ถูกใช้จากหลายไฟล์ test)

- [ ] **Step 6: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_cgd_intel.py
git commit -m "feat(cgd_intel): expose median per company_tables block + scope_rows for custom winrate calc"
```

---

## Task 2: `cgd_intel.py` — `calc_custom_winrate()` core function

**Files:**
- Modify: `scripts/cgd_intel.py` (เพิ่มฟังก์ชันใหม่ — ไม่แก้ของเดิมอีกในไฟล์นี้)
- Test: `scripts/test_cgd_intel.py`

**Interfaces:**
- Consumes: `_company_stats_from_rows(rows, winner)` (มีอยู่แล้ว, `cgd_intel.py:402`), `MIN_GAMES_FOR_IQR` (`cgd_intel.py:66`), `portal_views._norm_name` (lazy import เหมือนจุดอื่นในไฟล์นี้)
- Produces: `calc_custom_winrate(rows, fallback_stats, my_price, budget, selected_names, extra_names) -> dict | None` ที่ Task 3 (`portal_views.job_detail`) จะเรียกใช้ตรงๆ. คืน `None` ถ้า input ไม่ถูกต้องหรือไม่มีคู่แข่งเลย. คืน dict รูปแบบ:
  ```python
  {"my_discount_pct": float, "overall_win_pct": int,
   "breakdown": [{"name": str, "win_pct_against": int, "median": float|None,
                  "p25": float|None, "p75": float|None, "has_history": bool}, ...]}
  ```

- [ ] **Step 1: Write the failing test**

เพิ่มในท้าย `scripts/test_cgd_intel.py` (ก่อน `if __name__ == "__main__":`):

```python
def _calc_fixture_rows():
    """rows เหมือนรูปแบบที่ _fetch_scope คืน — มี 2 บริษัท: A (ลดลึก, สม่ำเสมอ) B (ลดน้อย)."""
    rows = []
    for d in (10.0, 12.0, 11.0, 9.0):
        rows.append({"winner": "หจก.A", "discount_pct": d, "fiscal_year": "2568"})
    for d in (25.0, 27.0, 26.0, 24.0):
        rows.append({"winner": "หจก.B", "discount_pct": d, "fiscal_year": "2568"})
    return rows


def test_calc_custom_winrate_basic():
    rows = _calc_fixture_rows()
    fallback = {"median": 15.0, "p25": 10.0, "p75": 20.0}
    # budget 1,000,000 ราคาเรา 850,000 → ลด 15% — อยู่ระหว่าง A (median~10.5) กับ B (median~25.5)
    out = ci.calc_custom_winrate(rows, fallback, my_price=850000, budget=1000000,
                                 selected_names=["หจก.A"], extra_names=[])
    assert out is not None, out
    assert out["my_discount_pct"] == 15.0, out
    assert len(out["breakdown"]) == 1
    b = out["breakdown"][0]
    assert b["name"] == "หจก.A" and b["has_history"] is True, b
    assert b["median"] == 10.5, b   # _pct([9,10,11,12], 50) ของ A — ยืนยันด้วย python จริงก่อนเขียนแผน
    # เราลด 15% ลึกกว่า p75 ของ A (11.25) → extrapolate เกินช่วง → clamp 95% (เราชนะสูง) A ชนะเราโอกาสต่ำ
    assert b["win_pct_against"] < 30, b
    assert out["overall_win_pct"] > 70, out   # เราชนะ A สูง เพราะเราลดลึกกว่าเขามาก


def test_calc_custom_winrate_multi_competitor_multiplies():
    rows = _calc_fixture_rows()
    fallback = {"median": 15.0, "p25": 10.0, "p75": 20.0}
    one = ci.calc_custom_winrate(rows, fallback, 850000, 1000000, ["หจก.A"], [])
    two = ci.calc_custom_winrate(rows, fallback, 850000, 1000000, ["หจก.A", "หจก.B"], [])
    assert two is not None
    # เพิ่มคู่แข่งอีกราย (B ลดน้อยกว่าเรามาก → เราชนะ B สูงด้วย) แต่ overall ต้อง <= ตอนมีคู่แข่งรายเดียว
    # (คูณ probability เพิ่ม ยิ่งมีคนแข่งยิ่งชนะยากขึ้นหรือเท่าเดิม ไม่มากขึ้น)
    assert two["overall_win_pct"] <= one["overall_win_pct"], (one, two)


def test_calc_custom_winrate_unknown_company_uses_fallback():
    rows = _calc_fixture_rows()
    fallback = {"median": 15.0, "p25": 10.0, "p75": 20.0}
    out = ci.calc_custom_winrate(rows, fallback, 850000, 1000000, [], ["บริษัทไม่มีประวัติเลย"])
    assert out is not None
    b = out["breakdown"][0]
    assert b["has_history"] is False, b
    assert b["median"] == 15.0 and b["p25"] == 10.0 and b["p75"] == 20.0, b   # ใช้ fallback ตรงๆ


def test_calc_custom_winrate_dedupes_same_company():
    rows = _calc_fixture_rows()
    fallback = {"median": 15.0, "p25": 10.0, "p75": 20.0}
    # ติ๊ก "หจก.A" + พิมพ์ "หจก. เอ" ซ้ำชื่อเดิม (normalized ตรงกัน) → นับครั้งเดียว
    out = ci.calc_custom_winrate(rows, fallback, 850000, 1000000, ["หจก.A"], ["หจก.A"])
    assert out is not None
    assert len(out["breakdown"]) == 1, out["breakdown"]


def test_calc_custom_winrate_invalid_inputs():
    rows = _calc_fixture_rows()
    fallback = {"median": 15.0, "p25": 10.0, "p75": 20.0}
    assert ci.calc_custom_winrate(rows, fallback, 0, 1000000, ["หจก.A"], []) is None      # ราคา<=0
    assert ci.calc_custom_winrate(rows, fallback, "abc", 1000000, ["หจก.A"], []) is None  # parse ไม่ได้
    assert ci.calc_custom_winrate(rows, fallback, 850000, 1000000, [], []) is None         # ไม่มีคู่แข่งเลย
    assert ci.calc_custom_winrate(rows, fallback, 850000, 0, ["หจก.A"], []) is None        # budget<=0
    print("✅ calc_custom_winrate (basic/multi/fallback/dedupe/invalid)")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scripts && BMS_ENV=dev python -c "import cgd_intel as ci; ci.calc_custom_winrate"`
Expected: `AttributeError: module 'cgd_intel' has no attribute 'calc_custom_winrate'`

- [ ] **Step 3: Implement**

เพิ่มในท้าย `scripts/cgd_intel.py` (ต่อจากฟังก์ชัน `_resolve_tin` หรือจุดอื่นที่เหมาะสม — ไม่ต้องอยู่ตำแหน่งเจาะจง):

```python
def _cdf_3pt(p25, median, p75, x):
    """ประมาณ CDF(x) จาก 3 จุด (p25,.25)/(median,.50)/(p75,.75) แบบ piecewise-linear บนแกน%ลด.
    คืน fraction 0.0-1.0, clamp [0.05, 0.95] (กันมั่นใจเกินจริงจาก sample เล็ก). จุดซ้ำ (p25==median
    เช่น) ให้ y ของจุดหลังทับจุดก่อน (median/p75 สำคัญกว่า p25 เวลาขัดกัน)."""
    pts = {}
    for p, y in ((p25, 0.25), (median, 0.50), (p75, 0.75)):
        pts[p] = y
    xs = sorted(pts)
    if len(xs) == 1:
        return 0.95 if x > xs[0] else (0.05 if x < xs[0] else 0.50)
    ys = [pts[k] for k in xs]
    if x <= xs[0]:
        slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
        y = ys[0] + slope * (x - xs[0])
    elif x >= xs[-1]:
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        y = ys[-1] + slope * (x - xs[-1])
    else:
        y = ys[0]
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                y = ys[i] + (ys[i + 1] - ys[i]) * (x - xs[i]) / (xs[i + 1] - xs[i])
                break
    return max(0.05, min(0.95, y))


def _resolve_competitor_name(rows, typed_name, _norm_name):
    """หาชื่อ winner ที่ normalized ตรงกับ typed_name ใน rows (เทียบทุกแถว — rows ของ 1 งานไม่ใหญ่
    ไม่ต้องใช้ index). คืนชื่อดิบที่ตรงในรูปแบบเดียวกับ rows['winner'] หรือ None ถ้าไม่เจอ."""
    core = _norm_name(typed_name)
    if not core:
        return None
    for r in rows:
        w = r.get("winner")
        if w and _norm_name(w) == core:
            return w
    return None


def calc_custom_winrate(rows, fallback_stats, my_price, budget, selected_names, extra_names):
    """คำนวณโอกาสชนะเจาะจงคู่แข่ง — my_price ที่ผู้ใช้กรอกเอง vs รายชื่อคู่แข่งที่เลือก/พิมพ์เอง
    (N+168, กัญจน์ขอ 2026-06-22). rows: scope rows เดียวกับที่ทำ company_tables (จาก _build_intel
    ใน intel_context()['scope_rows']). fallback_stats: {"median","p25","p75"} ของ scope กว้างสุด
    (จาก company_tables block แรก/กว้างสุด) ใช้แทนบริษัทที่ไม่มีประวัติพอ (< MIN_GAMES_FOR_IQR เกม).
    คืน None ถ้าราคา/budget parse ไม่ได้หรือ<=0, หรือไม่มีคู่แข่งให้คำนวณเลย (หลัง dedupe)."""
    import portal_views as _pv
    try:
        budget_f = float(budget)
        price_f = float(my_price)
    except (TypeError, ValueError):
        return None
    if budget_f <= 0 or price_f <= 0:
        return None
    my_discount_pct = max(0.0, (budget_f - price_f) / budget_f * 100)
    raw_names = [n.strip() for n in (list(selected_names) + list(extra_names)) if n and str(n).strip()]
    seen_core, names = set(), []
    for n in raw_names:
        core = _pv._norm_name(n)
        if core and core not in seen_core:
            seen_core.add(core)
            names.append(n)
    if not names:
        return None
    breakdown = []
    overall = 1.0
    for typed in names:
        exact = _resolve_competitor_name(rows, typed, _pv._norm_name)
        stats = _company_stats_from_rows(rows, exact) if exact else None
        if stats and stats.get("p25") is not None and stats.get("p75") is not None \
                and stats.get("median") is not None:
            median, p25, p75, has_history = stats["median"], stats["p25"], stats["p75"], True
        else:
            median, p25, p75 = fallback_stats["median"], fallback_stats["p25"], fallback_stats["p75"]
            has_history = False
        cdf = _cdf_3pt(p25, median, p75, my_discount_pct)
        win_pct_against = round((1 - cdf) * 100)     # โอกาสคู่แข่งรายนี้ชนะเรา
        overall *= cdf                                # โอกาสเราชนะรายนี้ สะสมไว้
        breakdown.append({"name": typed, "win_pct_against": win_pct_against,
                          "median": median, "p25": p25, "p75": p75, "has_history": has_history})
    return {"my_discount_pct": round(my_discount_pct, 1), "overall_win_pct": round(overall * 100),
            "breakdown": breakdown}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd scripts && BMS_ENV=dev python test_cgd_intel.py`
Expected: `✅ calc_custom_winrate (basic/multi/fallback/dedupe/invalid)` แสดง + `ALL PASS (moi location disambiguation)` ท้ายไฟล์ (ต้องเพิ่มเรียก `test_calc_custom_winrate_basic()` ฯลฯ ใน `if __name__ == "__main__":` block ด้วย — ดู step 4b)

- [ ] **Step 4b: เพิ่มเรียก test ใหม่ใน `__main__` block**

หา `if __name__ == "__main__":` ท้ายไฟล์ `scripts/test_cgd_intel.py` เพิ่มก่อนบรรทัด `print("ALL PASS (moi location disambiguation)")`:
```python
    test_calc_custom_winrate_basic()
    test_calc_custom_winrate_multi_competitor_multiplies()
    test_calc_custom_winrate_unknown_company_uses_fallback()
    test_calc_custom_winrate_dedupes_same_company()
    test_calc_custom_winrate_invalid_inputs()
```

- [ ] **Step 5: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_cgd_intel.py
git commit -m "feat(cgd_intel): calc_custom_winrate — win% against named competitors at a custom price"
```

---

## Task 3: `portal_views.py` — wire `calc_custom_winrate` into `job_detail()`

**Files:**
- Modify: `scripts/portal_views.py` (`job_detail`)
- Test: `scripts/test_portal_views.py`

**Interfaces:**
- Consumes: `cgd_intel.calc_custom_winrate(rows, fallback_stats, my_price, budget, selected_names, extra_names)` (Task 2), `intel_ctx["scope_rows"]`/`intel_ctx["company_tables"]` (Task 1)
- Produces: `job_detail(conn, pid, calc_params=None) -> dict | None` — `calc_params` คือ `{"my_price": str, "selected_names": list[str], "extra_names": list[str]}` หรือ `None`. ผลลัพธ์ dict เดิมเพิ่ม key `"custom_calc"` (ผลจาก `calc_custom_winrate`, อาจเป็น `None`) ที่ Task 4 (`render_job_page`) จะใช้ต่อ

- [ ] **Step 1: Write the failing test**

เปิด `scripts/test_portal_views.py` เพิ่มต่อจาก `test_job_detail_dept_name_passthrough` (หรือกลุ่ม `job_detail_*` ที่มีอยู่):

```python
def test_job_detail_custom_calc():
    import cgd_intel as _ci
    orig_ctx = _ci.intel_context
    _ci.intel_context = lambda *a, **k: {
        "lines": [], "company_tables": [{"label": "x", "n": 5, "conf_tag": "🟢 มั่นใจ",
                                         "p25": 10.0, "p75": 20.0, "median": 15.0, "companies": []}],
        "winrate_table": None,
        "scope_rows": [{"winner": "หจก.A", "discount_pct": 12.0, "fiscal_year": "2568"}] * 3,
    }
    try:
        c = _seed()
        d = pv.job_detail(c, "69010000001",
                          calc_params={"my_price": "900000", "selected_names": ["หจก.A"], "extra_names": []})
        assert d["custom_calc"] is not None, d
        assert "overall_win_pct" in d["custom_calc"], d["custom_calc"]
        # ไม่ส่ง calc_params → ไม่คำนวณ ไม่พัง
        d2 = pv.job_detail(c, "69010000001")
        assert d2["custom_calc"] is None, d2
        # ส่ง calc_params แต่ scope_rows ไม่มี (intel_context คืน None) → graceful, ไม่ throw
        _ci.intel_context = lambda *a, **k: None
        d3 = pv.job_detail(c, "69010000001",
                          calc_params={"my_price": "900000", "selected_names": ["หจก.A"], "extra_names": []})
        assert d3["custom_calc"] is None, d3
    finally:
        _ci.intel_context = orig_ctx
    print("OK job_detail_custom_calc")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scripts && BMS_ENV=dev python test_portal_views.py`
Expected: `TypeError: job_detail() got an unexpected keyword argument 'calc_params'`

- [ ] **Step 3: Implement**

ใน `scripts/portal_views.py` แก้ signature ของ `job_detail`:
```python
def job_detail(conn, pid, calc_params=None):
```

หาบล็อก `try:`/`except Exception:` ที่เรียก `cgd_intel.intel_context(...)` (มี `intel_lines = None`, `company_tables = None`, `winrate_table = None` ก่อนหน้า) แก้เป็น:
```python
    intel_lines = None
    company_tables = None
    winrate_table = None
    custom_calc = None
    try:
        import cgd_intel
        intel_ctx = cgd_intel.intel_context(
            (ps["province"] if ps else "") or "", (ps["project_name"] if ps else "") or "",
            dept_name, pid, budget, conn)
        if intel_ctx:
            intel_lines = intel_ctx["lines"]
            company_tables = intel_ctx.get("company_tables")
            winrate_table = intel_ctx.get("winrate_table")
            if calc_params and intel_ctx.get("scope_rows") and company_tables:
                fallback = company_tables[0]
                custom_calc = cgd_intel.calc_custom_winrate(
                    intel_ctx["scope_rows"],
                    {"median": fallback.get("median"), "p25": fallback.get("p25"), "p75": fallback.get("p75")},
                    calc_params.get("my_price"), budget,
                    calc_params.get("selected_names") or [], calc_params.get("extra_names") or [])
    except Exception:
        intel_lines = None
```

หา `return` statement ท้ายฟังก์ชัน (มี `"intel_lines": intel_lines, "company_tables": company_tables, "winrate_table": winrate_table`) เพิ่ม key:
```python
    return {"job": {"project_id": pid, "name": (ps["project_name"] if ps else "") or pid,
                    "location": loc, "budget": budget, "deadline": deadline,
                    "pred_lo": pred_lo, "pred_hi": pred_hi}, "bidders": bidders,
            "intel_lines": intel_lines, "company_tables": company_tables,
            "winrate_table": winrate_table, "custom_calc": custom_calc}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd scripts && BMS_ENV=dev python test_portal_views.py`
Expected: `OK job_detail_custom_calc` แสดง + `OK test_portal_views` ท้ายไฟล์

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal_views): job_detail() accepts optional calc_params, wires calc_custom_winrate"
```

---

## Task 4: `portal_views.py` — render the form + result

**Files:**
- Modify: `scripts/portal_views.py` (`render_job_page`, `_CSS`, ฟังก์ชันใหม่ `_render_custom_calc_form`)
- Test: `scripts/test_portal_views.py`

**Interfaces:**
- Consumes: `data["company_tables"]`, `data["custom_calc"]` (Task 3), `data.get("calc_prefill")` (prefill values ส่งมาจาก route ตอน redirect กลับมา — ดู Task 5)
- Produces: `_render_custom_calc_form(company_tables, custom_calc, prefill, tok, pid) -> str` (HTML) ที่ `render_job_page` เรียกต่อจากตาราง winrate

- [ ] **Step 1: Write the failing test**

เพิ่มใน `scripts/test_portal_views.py` ต่อจาก `render_job_page_winrate_table_full_ladder`:

```python
# --- render_job_page: custom winrate calculator form + result (N+168) ---
data_calc = {"job": {"project_id": "P1", "name": "งานทดสอบ", "location": "", "budget": 1000000,
                     "deadline": None, "pred_lo": None, "pred_hi": None},
            "bidders": [], "intel_lines": [],
            "company_tables": [{"label": "🏘 ในตำบลโพนทอง", "n": 5, "conf_tag": "🟢 มั่นใจ",
                                "p25": 10.0, "p75": 20.0, "median": 15.0,
                                "companies": [{"name": "หจก.A", "tin": "111", "games": 5,
                                              "median": 14.0, "p25": 10.0, "p75": 18.0,
                                              "project_ids": ["R1"]}]}],
            "winrate_table": None, "custom_calc": None}
html_form = pv.render_job_page(data_calc, "tok", 0)
assert 'name="my_price"' in html_form, html_form
assert 'value="หจก.A"' in html_form and "ชนะ 5 งาน" in html_form, html_form   # checkbox มาจาก company_tables
assert 'name="extra_names"' in html_form, html_form                          # textarea เพิ่มชื่ออื่น
assert "คำนวณโอกาสชนะ" in html_form, html_form

data_calc["custom_calc"] = {"my_discount_pct": 15.0, "overall_win_pct": 62,
                            "breakdown": [{"name": "หจก.A", "win_pct_against": 74, "median": 14.0,
                                          "p25": 10.0, "p75": 18.0, "has_history": True}]}
html_result = pv.render_job_page(data_calc, "tok", 0)
assert "62%" in html_result and "74%" in html_result, html_result
assert "อิงจากสถิติตอนที่บริษัทนั้นชนะในอดีต" in html_result, html_result   # disclaimer ต้องมีเสมอ
print("OK render_job_page_custom_calc_form")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scripts && BMS_ENV=dev python test_portal_views.py`
Expected: `AssertionError` ที่ `assert 'name="my_price"' in html_form` (ฟอร์มยังไม่ถูก render)

- [ ] **Step 3: Implement**

เพิ่ม CSS ใหม่ใน `_CSS` (ต่อจากกลุ่ม `.itbl`/`.tblwrap` ที่มีอยู่ — แทรกก่อนวงเล็บปิด `)` ท้าย tuple):
```python
    ".calcform{margin:10px 0}"
    ".calcform label{display:block;font-size:13px;padding:4px 0;color:#444}"
    ".calcform textarea{width:100%;box-sizing:border-box;font-size:14px;padding:9px;"
    "border:1px solid #ddd;border-radius:8px;font-family:inherit;resize:vertical;margin:4px 0}"
    ".calcform input[type=number]{font-size:14px;padding:7px 9px;border:1px solid #ddd;"
    "border-radius:8px;width:160px}"
    ".calcform button{margin-top:8px;font-size:14px;padding:8px 14px;border:0;border-radius:8px;"
    "background:#1d72b4;color:#fff}"
    ".calcresult{background:#fff;border-radius:12px;padding:12px 14px;margin:10px 0;"
    "box-shadow:0 2px 8px rgba(0,0,0,.05)}"
    ".calcresult .big{font-size:20px;font-weight:700;color:#1d72b4;margin:0 0 8px}"
    ".calcresult .crow{display:flex;justify-content:space-between;gap:8px;font-size:13px;"
    "padding:4px 0;border-bottom:1px solid #f2f2f2}"
    ".calcresult .note{font-size:12px;color:#888;margin-top:8px}"
```

เพิ่มฟังก์ชันใหม่ก่อน `def render_job_page(...)`:
```python
def _render_custom_calc_form(company_tables, custom_calc, prefill, tok, pid):
    """ฟอร์มคำนวณโอกาสชนะเจาะจงคู่แข่ง (N+168) — checkbox จาก company_tables (dedupe ด้วยชื่อ
    normalized) + textarea พิมพ์ชื่อเพิ่ม + ราคาที่จะยื่น. ไม่มี JS — submit จริงไปหลังบ้าน."""
    prefill = prefill or {}
    seen, opts = set(), []
    for blk in company_tables or []:
        for cmp_ in blk.get("companies") or []:
            core = _norm_name(cmp_["name"])
            if core and core not in seen:
                seen.add(core)
                opts.append(cmp_)
    checked_names = set(prefill.get("selected_names") or [])
    out = ["<div class=\"bidhead\">🎯 คำนวณโอกาสชนะเจาะจงคู่แข่ง</div>",
           f"<form class=\"calcform\" method=\"post\" action=\"/portal/job/calc\">",
           f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">",
           f"<input type=\"hidden\" name=\"pid\" value=\"{_h.escape(str(pid))}\">"]
    for cmp_ in opts:
        nm = _h.escape(cmp_["name"])
        chk = " checked" if cmp_["name"] in checked_names else ""
        out.append(f"<label><input type=\"checkbox\" name=\"competitors\" value=\"{nm}\"{chk}> "
                   f"{nm} (ชนะ {cmp_['games']} งาน, ลดเฉลี่ย {cmp_['median']:.0f}%)</label>"
                   if cmp_.get("median") is not None else
                   f"<label><input type=\"checkbox\" name=\"competitors\" value=\"{nm}\"{chk}> {nm}</label>")
    extra_pf = _h.escape("\n".join(prefill.get("extra_names") or []))
    out.append(f"<label>หรือพิมพ์ชื่อบริษัทอื่นเพิ่ม (1 ชื่อ/บรรทัด):</label>"
               f"<textarea name=\"extra_names\" rows=\"2\">{extra_pf}</textarea>")
    price_pf = _h.escape(str(prefill.get("my_price") or ""))
    out.append(f"<label>ราคาที่จะยื่น (บาท):</label>"
               f"<input type=\"number\" name=\"my_price\" value=\"{price_pf}\" min=\"1\" step=\"1\">"
               f"<button type=\"submit\">คำนวณโอกาสชนะ</button></form>")
    if custom_calc:
        out.append(f"<div class=\"calcresult\"><div class=\"big\">🎯 โอกาสชนะของคุณรวม: "
                   f"{custom_calc['overall_win_pct']}%</div>"
                   f"<div class=\"meta\">ราคาของคุณ = ลด {custom_calc['my_discount_pct']}%</div>")
        for b in custom_calc["breakdown"]:
            hist_note = "" if b["has_history"] else " (ไม่มีประวัติเฉพาะบริษัทนี้ — ใช้ค่าเฉลี่ยพื้นที่แทน)"
            out.append(f"<div class=\"crow\"><span>{_h.escape(b['name'])}{hist_note}</span>"
                       f"<span>ชนะคุณ ~{b['win_pct_against']}%</span></div>")
        out.append("<div class=\"note\">*อิงจากสถิติตอนที่บริษัทนั้นชนะในอดีต ไม่ใช่ทุกครั้งที่เขายื่นซอง</div></div>")
    elif custom_calc is None and prefill.get("my_price"):
        out.append("<div class=\"msg\">เลือกคู่แข่งอย่างน้อย 1 บริษัท หรือกรอกราคาให้ถูกต้อง</div>")
    return "".join(out)
```

หา `if data.get("winrate_table"):` ใน `render_job_page` (ต่อด้วย `b.append(_render_winrate_table(data["winrate_table"]))`) เพิ่มต่อจากนั้น:
```python
    if data.get("winrate_table"):
        b.append(_render_winrate_table(data["winrate_table"]))
    if data.get("company_tables"):
        b.append(_render_custom_calc_form(data["company_tables"], data.get("custom_calc"),
                                          data.get("calc_prefill"), tok, j["project_id"]))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd scripts && BMS_ENV=dev python test_portal_views.py`
Expected: `OK render_job_page_custom_calc_form` แสดง + `OK test_portal_views` ท้ายไฟล์

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal_views): render custom winrate calculator form + result on /portal/job"
```

---

## Task 5: `bms_api.py` — wire the route

**Files:**
- Modify: `scripts/bms_api.py` (`portal_job_get`, เพิ่ม route ใหม่ `portal_job_calc_post`)

**Interfaces:**
- Consumes: `portal_views.job_detail(conn, pid, calc_params)` (Task 3), `portal_views.render_job_page(data, ...)` (เดิม, ไม่เปลี่ยน signature)
- Produces: `POST /portal/job/calc` (form submit) → 303 redirect ไป `GET /portal/job?...&calc_my_price=...&calc_competitors=...&calc_extra=...`. `GET /portal/job` รับ query params เหล่านี้เพิ่ม (optional, default ว่าง) แล้วส่งต่อเป็น `calc_params`/`calc_prefill`

- [ ] **Step 1: Implement (ไม่มี automated route test ในระบบนี้สำหรับ /portal/job — ตรวจด้วย manual verification ใน Step 2 เหมือน Task 6 ของแผนก่อนหน้า N+161)**

แก้ `portal_job_get` (`scripts/bms_api.py`, มี `@app.get("/portal/job")` นำหน้า):
```python
@app.get("/portal/job")
async def portal_job_get(t: str = "", pid: str = "", calc_my_price: str = "",
                         calc_competitors: str = "", calc_extra: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    calc_params = None
    calc_prefill = None
    if calc_my_price or calc_competitors or calc_extra:
        selected = [s for s in calc_competitors.split("\x1f") if s]
        extra = [s for s in calc_extra.split("\n") if s.strip()]
        calc_params = {"my_price": calc_my_price, "selected_names": selected, "extra_names": extra}
        calc_prefill = {"my_price": calc_my_price, "selected_names": selected, "extra_names": extra}
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        cid = cust["id"] if cust else None
        data = portal_views.job_detail(conn, pid, calc_params)
        if data and calc_prefill:
            data["calc_prefill"] = calc_prefill
        notes = portal_views.list_job_notes(conn, cid, pid) if cid else []
        overview = portal_views.get_job_overview(conn, cid, pid) if cid else ""
        starred = pid in portal_views.starred_project_ids(conn, cid)
    return HTMLResponse(portal_views.render_job_page(data, t, v[2], notes, overview, starred))
```

เพิ่ม route ใหม่ต่อจาก `portal_job_note_post` (มี `@app.post("/portal/job/note")` นำหน้า — แทรกหลัง `return RedirectResponse(...)` ของฟังก์ชันนั้น):
```python
@app.post("/portal/job/calc")
async def portal_job_calc_post(request: Request):
    from urllib.parse import parse_qs, quote
    form = parse_qs((await request.body()).decode("utf-8"))
    g = lambda k: (form.get(k) or [""])[0]
    gl = lambda k: form.get(k) or []
    t, pid = g("t"), g("pid")
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    competitors = "\x1f".join(gl("competitors"))   # \x1f กัน ',' ชนชื่อบริษัทที่มี comma จริง (ไม่ค่อยมีแต่กันไว้)
    extra = g("extra_names")
    price = g("my_price")
    url = (f"/portal/job?t={quote(t)}&pid={quote(pid)}&calc_my_price={quote(price)}"
          f"&calc_competitors={quote(competitors)}&calc_extra={quote(extra)}")
    return RedirectResponse(url, status_code=303)
```

- [ ] **Step 2: Manual verification**

Run: `python -c "import ast; ast.parse(open('scripts/bms_api.py', encoding='utf-8').read())"`
Expected: ไม่มี output (syntax valid)

Run regression ของไฟล์ test ที่เกี่ยวข้องกับ portal ทั้งหมดอีกรอบให้ชัวร์ว่าไม่กระทบ route เดิม:
```bash
cd scripts && BMS_ENV=dev python test_portal_views.py && BMS_ENV=dev python test_bms_follow.py
```
Expected: `OK test_portal_views` และ `OK test_bms_follow`

- [ ] **Step 3: Commit**

```bash
git add scripts/bms_api.py
git commit -m "feat(bms_api): wire POST /portal/job/calc + calc query params on GET /portal/job"
```

---

## Task 6: Full regression + Sophia sanity + deploy

**Files:** none modified — verification + deploy only

- [ ] **Step 1: Run every touched/related test file in one pass**

```bash
cd scripts && BMS_ENV=dev python test_cgd_intel.py && BMS_ENV=dev python test_portal_views.py && BMS_ENV=dev python test_road_subtype.py && BMS_ENV=dev python test_water_subtype.py && BMS_ENV=dev python test_recency.py && BMS_ENV=dev python test_bms_follow.py && BMS_ENV=dev python test_cgd_sync.py
```
Expected: ทุกไฟล์ผ่าน ไม่มี traceback

- [ ] **Step 2: Dispatch Sophia (sanity auditor) per CLAUDE.md protocol**

อธิบายให้ Sophia ตรวจ: ฟังก์ชันใหม่ `calc_custom_winrate` (math correctness ทิศทาง win_pct_against ถูกไหม — คู่แข่งลดลึกกว่าเรา = เขาชนะ), เช็คว่า route ใหม่ POST ไม่มี SQL injection (form values ผ่าน parameterized query ที่มีอยู่แล้วเท่านั้น ไม่ได้สร้าง SQL ใหม่), เช็คว่าไม่กระทบ /portal/job เดิม (กรณีไม่ส่ง calc params ต้อง behavior เหมือนเดิม 100%)

- [ ] **Step 3: Send Discord notification per CLAUDE.md protocol**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "✅ Custom Win% Calculator เสร็จ — กรอกราคา+คู่แข่งเองได้แล้วบน /portal/job. Sophia: <SAFE/STOP>")
```

- [ ] **Step 4: เพิ่ม progress_log.md entry ตาม format เดิม**

- [ ] **Step 5: Deploy VPS (git pull + restart bms-api) — รันได้เลยถ้า Sophia SAFE เพราะคุณกัญจน์อนุมัติให้ทำจนเสร็จแล้วในข้อความที่ขอ feature นี้ ("เริ่มทำจนเสร็จได้เลย เดี๋ยวฉันขอไปนอนพักผ่อนก่อนนะ") — backup DB ก่อน restart ตามปกติถ้า migration เกี่ยวข้อง (งานนี้ไม่มี schema change เลย จึงไม่ต้อง backup DB พิเศษ — แค่ restart `bms-api` ให้โหลดโค้ดใหม่)

---

## Self-Review Notes (completed during plan authoring)

- **Spec coverage:** §3 (UI/form, checkbox+textarea+price input, no-JS) → Task 4. §4.1 (discount conversion) → Task 2. §4.2 (per-company stats reuse + free-text resolve + fallback) → Task 2 (`_resolve_competitor_name` + fallback branch). §4.3 (CDF interpolation, clamp 5-95%) → Task 2 (`_cdf_3pt`) — **ทิศทางแก้แล้วก่อนเขียนแผน** (ดู commit `151626d` ที่แก้ spec). §4.4 (combine via independence, corrected formula) → Task 2 (`overall *= cdf` สะสมที่ถูกทิศ). §5 (disclaimer ข้อความ) → Task 4. §6 (data flow, ฟังก์ชัน/route ที่ต้องมี) → Task 1-5 ครบทุกแถวในตาราง. §7 (edge cases) → Task 2 test (invalid inputs, fallback, dedupe), Task 4 (ไม่มี company_tables → ไม่ render ฟอร์ม).
- **Placeholder scan:** ไม่มี "TBD"/"similar to Task N" — ทุก step มีโค้ดสมบูรณ์
- **Type/signature consistency:** `calc_custom_winrate()` signature เดียวกันทั้ง Task 2 (นิยาม) และ Task 3 (เรียกใช้). `job_detail(conn, pid, calc_params=None)` เดียวกันทั้ง Task 3 (นิยาม) และ Task 5 (เรียกใช้). `_render_custom_calc_form()` signature เดียวกันทั้ง Task 4 (นิยาม+เรียกใน `render_job_page`) — ไม่มีจุดไหนเรียกชื่อฟังก์ชันผิด
