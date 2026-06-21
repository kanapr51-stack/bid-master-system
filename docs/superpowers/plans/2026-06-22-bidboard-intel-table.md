# Bid Board Intel Table (N=1..max win% + full company list + area portfolio) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-column win%-by-bidders table with a full N=1..max ladder, show ALL competitor companies (not just top 3) as clickable links to `/portal/company`, and surface jobs-in-this-area on the company page when navigated from a job.

**Architecture:** Extend `bid_field.py`'s centering math to produce every N from 1 to the true historical max (hardcoding N=1 win%=100 as a special case), have `field_and_winrate()` return the raw grid dict instead of pre-rendered text. Extend `cgd_intel.py`'s `_scope_block()` to return an unlimited `companies` list (instead of a capped text bullet), resolve each company name to a `bidder_tin` via a new `_resolve_tin()` helper, and assemble two new structured keys (`company_tables`, `winrate_table`) on `_build_intel()`'s return dict — `intel_context()` passes them through unchanged (it's a pure wrapper). Render real HTML `<table>` elements for these two structured pieces in `portal_views.py` (the existing text-line rendering path stays for everything else), add an `area_ids`-based exact-match lookup (`area_portfolio()`) for the company page's "jobs in this area" section, and wire `area_ids`/`area_label` query params through `bms_api.py`.

**Tech Stack:** Python 3, sqlite3, FastAPI (bms_api.py), no new dependencies.

## Global Constraints

- N=1 win% is always hardcoded to 100 (alone = no competitor = certain win) — never derived from the `tf**(k/k_mid)*100` formula.
- `ns` ladder = `[1] + range(2, max(sizes)+1)` — no artificial cap, extends to the true historical max N observed in that scope.
- Company list is unlimited (remove `SHOW_N=3` cap) — every company that won ≥1 job in the scope's `rows` appears, sorted by win-count descending.
- Company names that fail tin resolution render as plain grey non-clickable text (`<span class="notin">`), never as a broken/empty link.
- `_resolve_tin()` never throws — any DB error (including "no such table") returns `None`.
- `_scope_block()` stays pure (no `conn` param, no DB access) — tin resolution happens in `_build_intel()`, which already has `conn`.
- Area-highlight on `/portal/company` uses an exact `project_id IN (...)` match against the caller-supplied `area_ids` — no fuzzy/new area-parsing logic (per existing deferral in `docs/superpowers/specs/2026-06-20-portal-job-company-detail-design.md` §11).
- `winrate_lines()` stays intact (back-compat / still unit-tested) — `field_and_winrate()` simply stops calling it internally.
- Existing text-line rendering (`intel_lines`) stays for everything except the two structured sections — no full `intel_context()` refactor.

---

## File Structure

| File | Change |
|---|---|
| `scripts/bid_field.py` | `_center_stats()` ladder N=1..max; `_evaluate_winrate()` hardcode N=1→100; `field_and_winrate()` returns grid dict instead of text |
| `scripts/cgd_intel.py` | `_scope_block()` returns unlimited `companies` list (8th tuple element) instead of capped bullet text; new `_resolve_tin()` helper; `_build_intel()` assembles `company_tables`/`winrate_table` + calls `bid_field.winrate_lines()` itself for the text fallback |
| `scripts/portal_views.py` | `job_detail()` passes through 2 new keys; `render_job_page()` renders 2 new HTML tables; new `area_portfolio()`; `render_company_page()` gets an area-highlight section |
| `scripts/bms_api.py` | `/portal/company` route gains `area_ids`/`area_label` query params, wires `area_portfolio()` in |
| `scripts/test_bid_field.py`, `scripts/test_center_monitor.py`, `scripts/test_winrate_grid.py` | update for new ladder + new `field_and_winrate()` return shape |
| `scripts/test_cgd_intel.py`, `scripts/test_recency.py` | update `_scope_block()` unpacking (8 elements) + company assertions move to structured `companies` |
| `scripts/test_portal_views.py` | new tests for `area_portfolio()`, new HTML table rendering |

---

## Task 1: `bid_field.py` — N=1..max ladder + N=1 hardcoded 100% + grid-returning `field_and_winrate()`

**Files:**
- Modify: `scripts/bid_field.py:54-71` (`_center_stats`), `:147` (`_evaluate_winrate` row-building), `:358-360` (`field_and_winrate` tail)
- Test: `scripts/test_center_monitor.py:14-38`, `scripts/test_winrate_grid.py` (multiple), `scripts/test_bid_field.py` (no changes needed — only touches index `[1]`)

**Interfaces:**
- Consumes: nothing new
- Produces: `_center_stats(auctions)["ns"]` = `[1, 2, 3, ..., max(sizes)]`; `field_and_winrate(...)` returns `(grid: dict|None, field_lines: list, conf)` where `grid` is the same dict `winrate_grid()`/`_evaluate_winrate()` already produces (keys: `ns`, `rows`, `n_mean`, `n_sd`, `n_auctions`, `n_bids`, `ess`, `k_mid`, `budget`) — used by `cgd_intel.py` Task 2/3.

- [ ] **Step 1: Update failing tests for the new ladder in `_center_stats`**

Edit `scripts/test_center_monitor.py` lines 14-30:

```python
def test_center_stats_uniform():
    # 4 งาน ผู้ยื่น 4 เท่ากันหมด → mean=4 sd=0 ns=[1,2,3,4] k_mid=4
    st = bf._center_stats([auc(4) for _ in range(4)])
    assert st["n"] == 4, st
    assert abs(st["n_mean"] - 4.0) < 1e-9, st
    assert st["ns"] == [1, 2, 3, 4], st
    assert st["k_mid"] == 4, st
    print("✅ _center_stats uniform")


def test_center_stats_spread():
    # ผู้ยื่น [3,4,5] → mean=4 var=1 sd=1 ns=[1,2,3,4,5] k_mid=4
    st = bf._center_stats([auc(3), auc(4), auc(5)])
    assert abs(st["n_mean"] - 4.0) < 1e-9, st
    assert st["ns"] == [1, 2, 3, 4, 5], st
    assert st["k_mid"] == 4, st
    print("✅ _center_stats spread")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_center_monitor.py`
Expected: `AssertionError` on `st["ns"] == [1, 2, 3, 4]` (old code produces `[4]`)

- [ ] **Step 3: Implement the new ladder in `_center_stats`**

Replace `scripts/bid_field.py:54-71`:

```python
def _center_stats(auctions) -> dict:
    """centering math (สกัดจาก _evaluate_winrate): mean/sd จำนวนผู้ยื่น → ns (1..max จริง) + k_mid.
    auctions = [[(name,disc,is_winner[,fy])]] · auction <2 ผู้ยื่นถูกตัด.
    ว่าง → {n:0, n_mean:0, n_sd:0, ns:[], k_mid:None}."""
    sizes = [len(a) for a in auctions if len(a) >= 2]
    n = len(sizes)
    if n == 0:
        return {"n": 0, "n_mean": 0.0, "n_sd": 0.0, "ns": [], "k_mid": None}
    n_mean = sum(sizes) / n
    var = sum((s - n_mean) ** 2 for s in sizes) / (n - 1) if n > 1 else 0.0
    n_sd = math.sqrt(var)
    ns = [1] + list(range(2, max(sizes) + 1))     # ladder เต็ม N=1..max ที่เคยเกิดจริง (เดิม 3 จุด mean±SD)
    k_mid = min(max(2, round(n_mean)), max(sizes))
    return {"n": n, "n_mean": n_mean, "n_sd": n_sd, "ns": ns, "k_mid": k_mid}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/test_center_monitor.py`
Expected: `ALL PASS` (or all 3 `test_center_stats_*` print lines, plus the rest of the file's existing tests since `_log_center_breadcrumb` reads `ns`/`k_mid` but only logs `k_mid` — unaffected)

- [ ] **Step 5: Write the failing test for N=1 hardcoded to 100%**

Add to `scripts/test_winrate_grid.py` (after `test_grid_invert_columns`, before `test_grid_gate`):

```python
def test_grid_n1_always_100():
    # ผู้ยื่น 1 คนใน auction ใดก็ตาม → ns ต้องมี 1 รวม และ win% ของคอลัมน์ k=1 ต้อง=100 เสมอ (ไม่ใช่จากสูตร)
    sizes = [1, 2, 3, 4, 5]
    auctions = [[(f"b{j}", j * 1.7, j == 0) for j in range(s)] for s in sizes]
    # auction ขนาด 1 ถูกตัดออกจาก _center_stats (len>=2) แต่ ns ต้องยังมี N=1 เป็นจุดเริ่มเสมอ
    g = bf.winrate_grid(auctions, 1000000)
    assert g is not None, g
    assert g["ns"][0] == 1, g["ns"]
    for _price, ws in g["rows"]:
        assert ws[0] == 100, ws   # คอลัมน์ N=1 = ชนะแน่นอน ทุกราคา
    print("✅ grid: N=1 win%=100 เสมอ (ไม่ผ่านสูตร)")
```

- [ ] **Step 6: Run to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: `AssertionError` on `ws[0] == 100` (old formula yields something close to but not exactly 100, or a different value depending on `tf`/`k_mid`)

- [ ] **Step 7: Implement N=1 hardcode in `_evaluate_winrate`**

In `scripts/bid_field.py`, replace line 147:

```python
        rows.append((price, [round(tf ** (k / k_mid) * 100) for k in ns]))
```

with:

```python
        rows.append((price, [100 if k == 1 else round(tf ** (k / k_mid) * 100) for k in ns]))
```

- [ ] **Step 8: Run to verify it passes**

Run: `python scripts/test_winrate_grid.py`
Expected: `✅ grid: N=1 win%=100 เสมอ (ไม่ผ่านสูตร)` printed, no assertion errors

- [ ] **Step 9: Write failing tests for `field_and_winrate()` returning a grid dict instead of text**

Edit `scripts/test_winrate_grid.py` — update the 3 call sites that unpack `field_and_winrate()`'s first element as `wl` (rendered text) to expect a `grid` dict instead:

Replace lines 91-98 (`test_field_and_winrate_endtoend`):

```python
    with db.get_connection() as conn:
        grid, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                              district="เมือง", scope_label=" (อ.เมือง)", basis="อำเภอ")
    assert conf is None, conf                                # ไม่ผ่อน scope → 🟢 local
    assert grid is not None and grid["ns"][0] == 1, grid      # grid dict (ไม่ใช่ text แล้ว)
    assert grid["n_auctions"] == 6 and grid["n_bids"] == 24, grid  # 6 งาน × 4 ผู้ยื่น = 24
    assert isinstance(fl, list), fl                          # 2B block (อาจ [] ถ้าไม่มี leader) — ไม่ error
    print("✅ field_and_winrate end-to-end (อ่านรอบเดียว → 2 บล็อก)")
```

Replace lines 133-136 (`test_gate_fallback_to_old_card`):

```python
    with db.get_connection() as conn:
        grid, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                              district="ไม่มี", basis="อำเภอ")
    assert grid is None and fl == [] and conf is None, (grid, fl, conf)
    print("✅ gate: scope บาง → (None,[]) → การ์ดเดิม")
```

Replace lines 160-166 (`test_ladder_relax_to_amphoe`):

```python
    with db.get_connection() as conn:
        grid, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                              basis="ตำบล", project_ids=tambon_ids,
                                              cf={}, amphoe="นาทม")
    assert conf is not None and conf[0] == "🟡", conf        # ผ่อนไปอำเภอ
    assert grid is not None, grid                            # grid ขึ้น (เดิมไม่ขึ้น)
    print("✅ ladder: ตำบลบาง → ผ่อนอำเภอ 🟡 + grid ขึ้น")
```

Also update `scripts/test_center_monitor.py` line 106 (variable rename only, no assertion change needed since it doesn't inspect `wl` content):

```python
        grid, fl, conf = bf2.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                               basis="ตำบล", project_ids=["L0", "L1"],
                                               cf={}, amphoe="นาทม")
```

- [ ] **Step 10: Run to verify it fails**

Run: `python scripts/test_winrate_grid.py`
Expected: `AssertionError` (old code returns rendered text list for the first element, not a dict — `grid["ns"]` raises `TypeError: list indices must be integers`)

- [ ] **Step 11: Implement `field_and_winrate()` returning the grid**

In `scripts/bid_field.py`, replace lines 358-360:

```python
    wl = winrate_lines(grid, conf, price_basis=basis) if grid else []
    fl = field_lines(analyze_field(local_auc), budget, scope_label)
    return wl, fl, conf
```

with:

```python
    fl = field_lines(analyze_field(local_auc), budget, scope_label)
    return grid, fl, conf
```

Also update the docstring at line 332 (`field_and_winrate`'s docstring) — replace:

```python
    จน gate ผ่าน. คืน (winrate_lines, field_lines[2B], conf). conf=None(🟢)/('🟡','อำเภอ')/('🟠','จังหวัด').
```

with:

```python
    จน gate ผ่าน. คืน (grid|None, field_lines[2B], conf). conf=None(🟢)/('🟡','อำเภอ')/('🟠','จังหวัด').
    grid = dict จาก _evaluate_winrate (ns/rows/n_mean/n_sd/n_auctions/n_bids/ess/k_mid/budget) — caller render เอง.
```

- [ ] **Step 12: Run to verify it passes**

Run: `python scripts/test_winrate_grid.py && python scripts/test_center_monitor.py && python scripts/test_bid_field.py`
Expected: `ALL PASS` for all three files (no other call sites of `field_and_winrate()` exist outside these test files and `cgd_intel.py`, which is updated in Task 3)

- [ ] **Step 13: Commit**

```bash
git add scripts/bid_field.py scripts/test_center_monitor.py scripts/test_winrate_grid.py
git commit -m "feat(bid_field): extend win% ladder to N=1..max, hardcode N=1=100%, return raw grid"
```

---

## Task 2: `cgd_intel.py` — `_scope_block()` unlimited company list

**Files:**
- Modify: `scripts/cgd_intel.py:64-71` (remove `SHOW_N`), `:425-452` (`_scope_block`)
- Test: `scripts/test_cgd_intel.py:332-342`, `scripts/test_recency.py:25-31`

**Interfaces:**
- Consumes: `_company_stats_from_rows(rows, winner)` (unchanged, `cgd_intel.py:403-412`)
- Produces: `_scope_block(rows, label, now_year=None)` returns an 8-tuple `(lines, p25, p75, n, top_name, top_median, med, companies)` where `companies` is `list[dict]` with keys `name, games, median, p25, p75, project_ids` (no `tin` — that's added by `_build_intel()` in Task 3), sorted by win-count descending, unlimited length.

- [ ] **Step 1: Write the failing test**

Replace `scripts/test_cgd_intel.py:332-342` (`test_scope_stats`):

```python
def test_scope_stats():
    c = _fixture_conn(); tk = ["ถนน"]
    rows = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง")  # A,A,B (R5 เฉพาะเจาะจงตัด)
    s = ci._company_stats_from_rows(rows, "หจก.A")   # 2 งาน disc 5,8 → median 6.5, ไม่มี IQR
    assert s["games"] == 2 and s["median"] == 6.5 and s["p25"] is None, s
    assert ci._company_stats_from_rows(rows, "หจก.D")["games"] == 0   # ไม่อยู่ใน scope
    lines, p25, p75, n, top, topm, med, companies = ci._scope_block(rows, "🏘 ในตำบลโพนทอง")
    assert n == 3 and lines[0].startswith("🏘 ในตำบลโพนทอง — 3 งาน"), (n, lines[0])
    assert not any("หจก.A" in l for l in lines), "bullet รายบริษัทย้ายไป companies (ไม่ใช่ lines แล้ว)"
    names = [cmp["name"] for cmp in companies]
    assert "หจก.A" in names and "หจก.B" in names, companies   # ครบทุกบริษัท (ไม่จำกัด 3 แล้ว)
    a = next(cmp for cmp in companies if cmp["name"] == "หจก.A")
    assert a["games"] == 2 and a["median"] == 6.5, a
    assert a["project_ids"] and set(a["project_ids"]) == {"R1", "R2"}, a
    assert med is not None, med   # median ของ scope (สำหรับ 'ปกติ' ในคาดราคา)
    print("✅ scope stats + block (scope-local, full company list)")
```

Replace `scripts/test_recency.py:29` (`test_scope_block_recency`):

```python
def test_scope_block_recency():
    """scope ที่มีข้อมูลเก่า-ดุ (2562, 40%) + สด-อนุรักษ์ (2568, 25%) → median เอนของสด (~25)."""
    rows = [{"discount_pct": 40.0, "winner": "หจก.เก่า", "fiscal_year": "2562", "subdistrict": "x", "district": "y"},
            {"discount_pct": 25.0, "winner": "หจก.สด", "fiscal_year": "2568", "subdistrict": "x", "district": "y"}]
    _l, p25, p75, n, _t, _tm, med, _cos = ci._scope_block(rows, "🏘 ทดสอบ", now_year=2569)
    assert med is not None and med <= 30, f"ของเก่าควรจาง median เอน 25 ไม่ใช่ 32.5; ได้ {med}"
    print(f"✅ _scope_block recency (median={med} เอนของสด)")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_cgd_intel.py`
Expected: `ValueError: not enough values to unpack (expected 8, got 7)` on the `_scope_block()` call

- [ ] **Step 3: Implement the unlimited company list in `_scope_block`**

In `scripts/cgd_intel.py`, remove the `SHOW_N = 3` line from the constants block (line 66):

```python
MIN_COMPETITORS = 2     # distinct winners ขั้นต่ำก่อนหยุด fallback
PROVINCE_FALLBACK_MIN = 3   # อำเภอไม่มี precedent → คาดจากจังหวัดได้ถ้า distinct winners ≥ นี้ (หยาบกว่า local จึงตั้งสูงกว่า)
MIN_GAMES_FOR_IQR = 3   # ต่ำกว่านี้โชว์แค่ median
```

Replace `scripts/cgd_intel.py:425-452` (`_scope_block`):

```python
def _scope_block(rows: list, label: str, now_year=None) -> tuple:
    """บล็อกคู่แข่ง 1 scope (ตำบล/อำเภอ/จังหวัด). สถิติทุกตัว scope-local จาก rows.
    p25/p75/median ถ่วงน้ำหนักความสด (L3 recency, half-life 1 ปี) — งานเก่าจาง.
    companies = ทุกบริษัทที่ชนะใน rows (ไม่จำกัด — เดิม SHOW_N=3) เรียงจำนวนงานชนะมาก→น้อย, ไม่มี tin
    (tin resolve โดย _build_intel ซึ่งมี conn).
    คืน (lines, p25, p75, n, top_name, top_median, median, companies)."""
    counts = Counter(r["winner"] for r in rows if r.get("winner"))
    dw = [(r["discount_pct"], recency_weight(r.get("fiscal_year"), now_year))
          for r in rows if r.get("discount_pct") is not None]
    discs = [d for d, _ in dw]; wts = [w for _, w in dw]
    p25, p75 = _wpct(discs, wts, 25), _wpct(discs, wts, 75)
    med = _wpct(discs, wts, 50)
    n = len(rows)
    ranked = counts.most_common()                  # ทุกบริษัท ไม่จำกัด (เดิม most_common(SHOW_N))
    top_name = ranked[0][0] if ranked else None
    top_median = _company_stats_from_rows(rows, top_name)["median"] if top_name else None
    lines = [f"{label} — {n} งาน {_conf_tag(n, p25, p75)}"]
    companies = []
    for w, _wins in ranked:
        cs = _company_stats_from_rows(rows, w)
        pids = [r["project_id"] for r in rows if r.get("winner") == w and r.get("project_id")]
        companies.append({"name": w or "?", "games": cs["games"], "median": cs["median"],
                          "p25": cs["p25"], "p75": cs["p75"], "project_ids": pids})
    if p75:
        lines.append(f"  📊 ส่วนลด {p25:.0f}–{p75:.0f}%")
    return lines, p25, p75, n, top_name, top_median, med, companies
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/test_cgd_intel.py && python scripts/test_recency.py`
Expected: `ALL PASS` — note `test_intel_lines` (in `test_cgd_intel.py`) currently asserts `any("• หจก." in l for l in out)`, which will now fail since bullet lines are removed; this is fixed in Task 3 Step 1 (it needs `_build_intel`'s new `company_tables` to verify against, not just `intel_lines()`'s text). If it fails here, that is expected — proceed to Task 3.

- [ ] **Step 5: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_cgd_intel.py scripts/test_recency.py
git commit -m "feat(cgd_intel): _scope_block returns unlimited company list instead of top-3 bullet text"
```

---

## Task 3: `cgd_intel.py` — `_resolve_tin()` + `_build_intel()` assembles `company_tables`/`winrate_table`

**Files:**
- Modify: `scripts/cgd_intel.py:500-627` (`_build_intel`, all 4 `_scope_block()` call sites + the `bid_field` integration block + return dict)
- Create (new function in same file): `_resolve_tin(conn, name)`
- Test: `scripts/test_cgd_intel.py` (new tests + fix `test_intel_lines`)

**Interfaces:**
- Consumes: `bid_field.field_and_winrate(...)` now returns `(grid: dict|None, field_lines, conf)` (Task 1); `bid_field.winrate_lines(grid, conf, price_basis)` (unchanged signature, Task 1 kept it intact); `portal_views._norm_name(s)`, `portal_views._prefilter_key(name)` (unchanged, `portal_views.py:155-169`)
- Produces: `_build_intel(...)` return dict gains two new keys: `"company_tables": list[dict]` (each `{label, n, conf_tag, p25, p75, companies: [{name, tin, project_ids, games, median, p25, p75}]}`) and `"winrate_table": dict|None` (the raw grid dict plus `conf` and `price_basis` keys merged in). `intel_context()` is unchanged (pure pass-through) — these keys flow through automatically.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_cgd_intel.py` (after `test_scope_stats`, before `test_confidence_label`):

```python
def _tin_fixture_conn():
    """conn แยกจาก _fixture_conn — มี bid_results สำหรับ _resolve_tin."""
    c = _fixture_conn()
    c.execute("""CREATE TABLE bid_results (project_id TEXT, bidder_name TEXT, bidder_tin TEXT)""")
    c.execute("INSERT INTO bid_results VALUES ('R1','หจก.A','1234567890123')")
    c.commit()
    return c


def test_resolve_tin():
    c = _tin_fixture_conn()
    assert ci._resolve_tin(c, "หจก.A") == "1234567890123"
    assert ci._resolve_tin(c, "หจก.ไม่มีตัวนี้") is None
    assert ci._resolve_tin(c, "") is None
    # ไม่มีตาราง bid_results → graceful None (ไม่ throw)
    c2 = _fixture_conn()
    assert ci._resolve_tin(c2, "หจก.A") is None
    print("✅ _resolve_tin (match / no-match / no-table graceful)")


def test_build_intel_company_tables_and_winrate_table():
    c = _fixture_conn()
    ctx = ci.intel_context("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", conn=c)
    assert ctx is not None, ctx
    assert "company_tables" in ctx and "winrate_table" in ctx, ctx
    assert ctx["company_tables"], "ต้องมีอย่างน้อย 1 บล็อก (ตำบลโพนทอง มีคู่แข่ง)"
    blk = ctx["company_tables"][0]
    assert set(blk.keys()) >= {"label", "n", "conf_tag", "p25", "p75", "companies"}, blk
    names = [cmp["name"] for cmp in blk["companies"]]
    assert "หจก.A" in names and "หจก.B" in names, names    # ครบทุกบริษัท ไม่จำกัด 3
    for cmp in blk["companies"]:
        assert "tin" in cmp, cmp                            # key มีเสมอ (None ถ้า resolve ไม่ได้ — ไม่มี bid_results ในนี้)
        assert cmp["tin"] is None, cmp                       # _fixture_conn ไม่มี bid_results → resolve ไม่ได้เสมอ graceful
    print("✅ _build_intel: company_tables + winrate_table keys present, full company list, tin graceful-None")


def test_intel_lines_no_longer_has_company_bullets():
    """N+161: bullet รายบริษัทย้ายไป company_tables — intel_lines() (text, LINE) ไม่มี '• ' บริษัทแล้ว."""
    c = _fixture_conn()
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", conn=c)
    assert out and out[0].startswith("💡 ราคาอ้างอิง (งานถนน"), out
    assert not any("• หจก." in l for l in out), "bullet รายบริษัทต้องไม่อยู่ใน lines text แล้ว"
    assert any("ส่วนลด" in l for l in out), out
    print("✅ intel_lines: ไม่มี company bullet text แล้ว (ย้ายไป company_tables)")
```

Also fix the now-broken assertion in the existing `test_intel_lines` (`scripts/cgd_intel.py` test file, around line 353-359) — remove the obsolete bullet-text assertion:

```python
def test_intel_lines():
    c = _fixture_conn()   # ไม่มี project_locations → resolve degrade province (graceful)
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", conn=c)
    assert out and out[0].startswith("💡 ราคาอ้างอิง (งานถนน"), out
    assert any("ส่วนลด" in l for l in out), out
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", conn=c) == []
```

(Removed the `assert any("• หจก." in l for l in out), out` line — that assertion tested the now-removed bullet text.)

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_cgd_intel.py`
Expected: `AttributeError: module 'cgd_intel' has no attribute '_resolve_tin'`

- [ ] **Step 3: Implement `_resolve_tin()` and update `_build_intel()`**

Add this new function to `scripts/cgd_intel.py` directly after `_conf_tag` (after line 422, before `_scope_block`):

```python
def _resolve_tin(conn, name):
    """หา bidder_tin จาก bid_results ด้วยชื่อ (cgd_winners ไม่มี tin ที่เชื่อถือได้ — N+157 winner_tin เพี้ยน ~99%).
    normalized exact match (ตัด prefix นิติบุคคล, ใช้ helper จาก portal_views) + LIKE prefilter ด้วยคำยาวสุด.
    None ถ้าไม่เจอ/ชื่อสั้นเกิน/error (รวม 'ไม่มีตาราง bid_results') — ห้าม throw."""
    try:
        import portal_views as _pv
        core = _pv._norm_name(name)
        key = _pv._prefilter_key(name)
        if not core or not key:
            return None
        cand = conn.execute(
            "SELECT bidder_name, bidder_tin FROM bid_results WHERE bidder_name LIKE ?",
            (f"%{key}%",)).fetchall()
        for row in cand:
            bname, tin = row[0], row[1]
            if tin and _pv._norm_name(bname) == core:
                return tin
        return None
    except Exception:
        _log.debug("_resolve_tin failed for name=%r", name, exc_info=True)
        return None
```

Now update all 4 `_scope_block()` call sites in `_build_intel()` to unpack 8 elements, and assemble `company_tables`. Replace `scripts/cgd_intel.py:511-516` (the initializer block) — add `company_tables = []`:

```python
    blocks = []
    company_tables = []              # N+161: บล็อกบริษัทแบบ structured (เต็มลิสต์ + tin) ต่อ scope ที่มีคู่แข่ง
    pp25 = pp75 = ptop = ptopm = pmed = None
    basis = ""
    used_rows = []                   # reference rows ของ scope ที่ใช้คาดราคา (สำหรับ explain snapshot)
    basis_sub = basis_dist = None    # scope ที่ใช้คาดราคา (สำหรับ recency series)
    basis_old = False                # คาดราคาอิงข้อมูลย้อนเกิน 3 ปี (พื้นที่งานน้อย) → ติดป้าย
    tag = " (งานแข่งจริง)" if contested_only else ""
```

Replace line 526 (tambon block):

```python
                tl, t25, t75, t_n, ttop, ttopm, tmed, t_cos = _scope_block(t_rows, f"🏘 ในตำบล{tambon}")
                blocks += tl
                company_tables.append({"label": f"🏘 ในตำบล{tambon}", "n": t_n,
                                       "conf_tag": _conf_tag(t_n, t25, t75), "p25": t25, "p75": t75,
                                       "companies": t_cos})
```

Replace line 536 (amphoe-dual block):

```python
                al, a25, a75, a_n, atop, atopm, amed, a_cos = _scope_block(a_rows, f"🏙 ในอำเภอ{amphoe}")
                blocks += al
                company_tables.append({"label": f"🏙 ในอำเภอ{amphoe}", "n": a_n,
                                       "conf_tag": _conf_tag(a_n, a25, a75), "p25": a25, "p75": a75,
                                       "companies": a_cos})
```

Replace line 558 (province-only block):

```python
        pl, p25, p75, p_n, ptopn, ptopmd, pmedn, p_cos = _scope_block(p_rows, f"🏙 ใน{province}")
        blocks += pl
        company_tables.append({"label": f"🏙 ใน{province}", "n": p_n,
                               "conf_tag": _conf_tag(p_n, p25, p75), "p25": p25, "p75": p75,
                               "companies": p_cos})
```

Replace line 569 (province-fallback block):

```python
            fl, f25, f75, f_n, ftop, ftopm, fmed, f_cos = _scope_block(pf_rows, f"🗺 ทั้งจังหวัด{province} (ข้ามพื้นที่)")
            blocks += fl
            company_tables.append({"label": f"🗺 ทั้งจังหวัด{province} (ข้ามพื้นที่)", "n": f_n,
                                   "conf_tag": _conf_tag(f_n, f25, f75), "p25": f25, "p75": f75,
                                   "companies": f_cos})
```

Now replace the `bid_field` integration block at `scripts/cgd_intel.py:586-606`:

```python
    winrate_table = None
    if pred:
        import bid_field as _bf                       # 2B เจ้าตลาด + B′ ตาราง win% (population เดียวกับราคา)
        _ids = [r["project_id"] for r in used_rows if r.get("project_id")]
        _lbl = (f" (ต.{tambon})" if basis == "ตำบล"
                else f" (อ.{amphoe})" if basis == "อำเภอ"
                else f" (ต.{tambon}+อ.{amphoe})" if basis.startswith("ตำบล+")
                else f" (ใน{province})")
        _grid, _fl, _conf = _bf.field_and_winrate(conn, province, tokens, budget,
                                                   scope_label=_lbl, basis=basis, project_ids=_ids,
                                                   cf=cf, amphoe=amphoe)
        _wl = _bf.winrate_lines(_grid, _conf, price_basis=basis) if _grid else []
        if _grid:
            winrate_table = {**_grid, "conf": _conf, "price_basis": basis}
        if _wl and _conf is None:                      # 🟢 local → ตารางแทน a/b/c (consistent ทุกอย่าง local)
            lines += [""] + _wl
        elif _wl:                                      # 🟡/🟠 assisted → คงราคา local + ตารางต่อท้าย (price sacred)
            lines += [""] + predict_lines(pred, basis, contested=contested_only)
            lines += [""] + _wl
        else:                                          # ไม่มี grid → การ์ดเดิม (graceful)
            lines += [""] + predict_lines(pred, basis, contested=contested_only)
        if basis_old:
            lines.append("📜 รวมข้อมูลเก่ากว่า 3 ปี (พื้นที่นี้งานน้อย) — ใช้เป็นแนวโน้ม")
        if _fl:                                        # บล็อกเจ้าตลาด 2B (ต่อท้าย)
            lines += [""] + _fl
```

Now add tin-resolution and the new keys to the final return — replace `scripts/cgd_intel.py:625-626`:

```python
    _tin_cache = {}
    for ct in company_tables:
        for cmp in ct["companies"]:
            if cmp["name"] not in _tin_cache:
                _tin_cache[cmp["name"]] = _resolve_tin(conn, cmp["name"])
            cmp["tin"] = _tin_cache[cmp["name"]]
    return {"lines": lines, "prediction": pred, "tambon": tambon, "amphoe": amphoe,
            "explain": explain, "company_tables": company_tables, "winrate_table": winrate_table}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/test_cgd_intel.py && python scripts/test_recency.py`
Expected: `ALL PASS` for both files

- [ ] **Step 5: Run the full existing test suite for regressions**

Run: `python scripts/test_bid_field.py && python scripts/test_center_monitor.py && python scripts/test_winrate_grid.py && python scripts/test_cgd_intel.py && python scripts/test_recency.py`
Expected: `ALL PASS` / all `✅` lines, no `AssertionError`/`Traceback`

- [ ] **Step 6: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_cgd_intel.py
git commit -m "feat(cgd_intel): assemble company_tables + winrate_table on _build_intel, resolve company tin"
```

---

## Task 4: `portal_views.py` — pass through new keys + render HTML tables on `/portal/job`

**Files:**
- Modify: `scripts/portal_views.py:80-89` (`job_detail`), `:411-414` (`render_job_page`'s intel_lines loop), `:262-320` (`_CSS`)
- Test: `scripts/test_portal_views.py` (new)

**Interfaces:**
- Consumes: `cgd_intel.intel_context(...)` dict now has `company_tables`/`winrate_table` keys (Task 3)
- Produces: `job_detail(conn, pid)`'s returned dict gains `company_tables: list|None` and `winrate_table: dict|None`; `render_job_page(data, token, exp, notes=None, overview="", starred=False)` (signature unchanged) renders 2 new `<table>` blocks when those keys are truthy

- [ ] **Step 1: Write the failing test**

Check whether `scripts/test_portal_views.py` exists first:

Run: `ls scripts/test_portal_views.py`

If it does not exist, create it with this content. If it exists, append these functions to it (read the existing file first to match its `_conn()`/fixture helper naming, then adapt the snippet below to reuse it instead of duplicating).

```python
"""test_portal_views.py — job_detail/render_job_page company_tables + winrate_table HTML (N+161)."""
import os, sys, tempfile
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def test_render_job_page_company_table_with_tin_link():
    data = {"job": {"project_id": "P1", "name": "งานทดสอบ", "location": "", "budget": 0,
                    "deadline": None, "pred_lo": None, "pred_hi": None},
            "bidders": [], "intel_lines": ["💡 ราคาอ้างอิง (งานถนน ต.โพนทอง)"],
            "company_tables": [{"label": "🏘 ในตำบลโพนทอง", "n": 5, "conf_tag": "🟢", "p25": 10.0, "p75": 20.0,
                                "companies": [
                                    {"name": "หจก.A", "tin": "111", "games": 3, "median": 12.0,
                                     "p25": 10.0, "p75": 15.0, "project_ids": ["R1", "R2"]},
                                    {"name": "หจก.ไม่มีtin", "tin": None, "games": 1, "median": None,
                                     "p25": None, "p75": None, "project_ids": ["R3"]}]}],
            "winrate_table": None}
    html = pv.render_job_page(data, "tok", 0)
    assert "หจก.A" in html and "หจก.ไม่มีtin" in html, html
    assert "/portal/company?t=tok&tin=111" in html, html               # tin resolve ได้ → ลิงก์
    assert "area_ids=R1%2CR2" in html or "area_ids=R1,R2" in html, html  # project_ids ติดไปด้วย
    assert 'class="notin"' in html, "ชื่อ resolve ไม่ได้ต้องเป็น grey ไม่คลิก"
    print("✅ render_job_page: company table (tin link + notin grey)")


def test_render_job_page_winrate_table_full_ladder():
    data = {"job": {"project_id": "P1", "name": "งานทดสอบ", "location": "", "budget": 0,
                    "deadline": None, "pred_lo": None, "pred_hi": None},
            "bidders": [], "intel_lines": [], "company_tables": [],
            "winrate_table": {"ns": [1, 2, 3, 4], "rows": [(1400000, [100, 78, 68, 59])],
                              "n_mean": 3.0, "n_sd": 1.0, "n_auctions": 10, "n_bids": 30,
                              "ess": 12.0, "k_mid": 3, "budget": 2000000, "conf": None, "price_basis": "ตำบล"}}
    html = pv.render_job_page(data, "tok", 0)
    assert "1ราย" in html and "4ราย" in html, html        # ladder เต็ม N=1..4 (ไม่ใช่ 3 จุดเดิม)
    assert "100%" in html, html                            # N=1 = 100% เสมอ
    print("✅ render_job_page: winrate table full N=1..max ladder")


test_render_job_page_company_table_with_tin_link()
test_render_job_page_winrate_table_full_ladder()
print("ALL PASS portal_views (company/winrate tables)")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_portal_views.py`
Expected: `KeyError: 'company_tables'` or the `assert` on `"หจก.A" in html` fails (current `render_job_page` only renders `intel_lines` as escaped text, no table)

- [ ] **Step 3: Pass through the new keys in `job_detail()`**

In `scripts/portal_views.py`, replace lines 80-89:

```python
    intel_lines = None
    company_tables = None
    winrate_table = None
    try:
        import cgd_intel
        intel_ctx = cgd_intel.intel_context(
            (ps["province"] if ps else "") or "", (ps["project_name"] if ps else "") or "",
            dept_name, pid, budget, conn)
        if intel_ctx:
            intel_lines = intel_ctx["lines"]
            company_tables = intel_ctx.get("company_tables")
            winrate_table = intel_ctx.get("winrate_table")
    except Exception:
        intel_lines = None
```

And update the final `return` at lines 124-127:

```python
    return {"job": {"project_id": pid, "name": (ps["project_name"] if ps else "") or pid,
                    "location": loc, "budget": budget, "deadline": deadline,
                    "pred_lo": pred_lo, "pred_hi": pred_hi}, "bidders": bidders,
            "intel_lines": intel_lines, "company_tables": company_tables,
            "winrate_table": winrate_table}
```

- [ ] **Step 4: Add CSS for the 2 new tables**

In `scripts/portal_views.py`, add to the `_CSS` tuple (right before the closing `)` at line 319, after the `.star{...}` line):

```python
    ".star{font-size:20px;text-decoration:none;margin-left:8px;vertical-align:middle}"
    ".itbl{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0}"
    ".itbl th,.itbl td{padding:5px 7px;text-align:right;border-bottom:1px solid #eee;white-space:nowrap}"
    ".itbl th:first-child,.itbl td:first-child{text-align:left}"
    ".itbl th{color:#888;font-weight:600;background:#fafbfc}"
    ".itbl a{color:#1d72b4;text-decoration:none}"
    ".itbl .notin{color:#999}"
    ".tblwrap{overflow-x:auto;margin:8px 0;-webkit-overflow-scrolling:touch}"
)
```

(Note: this is a continuation of the existing `_CSS` tuple — keep it as one string concatenated by adjacent string literals, matching the existing style. Place this new chunk as the last element before the closing `)`.)

- [ ] **Step 5: Render the 2 tables in `render_job_page()`**

In `scripts/portal_views.py`, replace lines 411-414:

```python
    if data.get("intel_lines"):
        b.append("<div class=\"bidhead\">📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่</div>")
        for line in data["intel_lines"]:
            b.append(f"<div class=\"meta\">{_h.escape(line)}</div>")
    if data.get("company_tables"):
        b.append(_render_company_tables(data["company_tables"], tok))
    if data.get("winrate_table"):
        b.append(_render_winrate_table(data["winrate_table"]))
```

Add these 2 new render helpers right before `def render_job_page(` (i.e. right after `_render_overview`, before line 388):

```python
def _render_company_tables(tables, tok):
    """ตารางบริษัทคู่แข่งแบบเต็ม (ไม่จำกัด 3) ต่อ scope — ชื่อ resolve tin ได้ = ลิงก์ /portal/company, ไม่ได้ = grey."""
    out = []
    for blk in tables:
        if not blk.get("companies"):
            continue
        out.append(f"<div class=\"bidhead\">🏢 คู่แข่ง {_h.escape(blk['label'])} "
                   f"({blk['n']} งาน {blk['conf_tag']})</div>")
        out.append("<div class=\"tblwrap\"><table class=\"itbl\"><tr><th>บริษัท</th>"
                   "<th>งาน</th><th>ลด%</th></tr>")
        for cmp_ in blk["companies"]:
            nm = _h.escape(cmp_["name"])
            disc = f"{cmp_['median']:.0f}%" if cmp_.get("median") is not None else "—"
            if cmp_.get("tin"):
                ids = ",".join(str(p) for p in (cmp_.get("project_ids") or []))
                href = (f"/portal/company?t={tok}&tin={_h.escape(cmp_['tin'])}"
                       f"&area_ids={_h.escape(ids)}&area_label={_h.escape(blk['label'])}")
                name_html = f"<a href=\"{href}\">{nm}</a>"
            else:
                name_html = f"<span class=\"notin\">{nm}</span>"
            out.append(f"<tr><td>{name_html}</td><td>{cmp_['games']}</td><td>{disc}</td></tr>")
        out.append("</table></div>")
    return "".join(out)


def _render_winrate_table(wt):
    """ตารางโอกาสชนะตามจำนวนผู้ยื่น N=1..max เต็ม (เดิม 3 คอลัมน์ mean±SD)."""
    ns, rows = wt["ns"], wt["rows"]
    out = [f"<div class=\"bidhead\">💵 โอกาสชนะตามจำนวนผู้ยื่น (งบ {wt['budget']:,.0f})</div>",
           "<div class=\"tblwrap\"><table class=\"itbl\"><tr><th>ราคายื่น</th>"
           + "".join(f"<th>{k} ราย</th>" for k in ns) + "</tr>"]
    for price, ws in rows:
        out.append(f"<tr><td>{price:,.0f}</td>" + "".join(f"<td>{w}%</td>" for w in ws) + "</tr>")
    out.append("</table></div>")
    sd_txt = f" (±{round(wt['n_sd'])})" if len(ns) > 1 else ""
    out.append(f"<div class=\"meta\">📊 สนามนี้เฉลี่ย {round(wt['n_mean'])} ผู้ยื่น{sd_txt} "
              f"· จาก {wt['n_auctions']} งาน · {wt['n_bids']} ราย</div>")
    if wt.get("conf"):
        emoji, scope_word = wt["conf"]
        out.append(f"<div class=\"meta\">{emoji} โอกาส% อิง{scope_word} (พื้นที่นี้ข้อมูลบาง)</div>")
    return "".join(out)
```

- [ ] **Step 6: Run to verify it passes**

Run: `python scripts/test_portal_views.py`
Expected: `ALL PASS portal_views (company/winrate tables)`

- [ ] **Step 7: Run existing portal test for regressions**

Run: `python scripts/test_bms_follow.py`
Expected: `OK test_bms_follow` (unaffected — `render_job_page` signature unchanged, new sections only render when the new keys are present)

- [ ] **Step 8: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal_views): render full company table + N=1..max winrate table on /portal/job"
```

---

## Task 5: `portal_views.py` — `area_portfolio()` + area-highlight section on `/portal/company`

**Files:**
- Modify: `scripts/portal_views.py:574-627` (`render_company_page`)
- Create (new function in same file): `area_portfolio(conn, name, project_ids)`
- Test: `scripts/test_portal_views.py` (append)

**Interfaces:**
- Consumes: `_to_float`, `_discount`, `_year_th` (unchanged, `portal_views.py:42-59`)
- Produces: `area_portfolio(conn, name, project_ids)` returns `None` if `project_ids` is empty or no exact match found, else `{"label_count": int, "jobs": [{"project_id", "name", "price", "discount", "is_winner"}]}` (jobs restricted to `project_ids` where `winner == name` in `cgd_winners`); `render_company_page(data, token, from_pid, exp, h2h=None, won=None, area=None, area_label="")` (2 new optional kwargs appended at the end — existing callers unaffected since they're optional)

- [ ] **Step 1: Write the failing test**

Append to `scripts/test_portal_views.py` (before the final `print("ALL PASS...")` line — move that print to the very end after these new test calls):

```python
def _area_conn():
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, project_name TEXT,
        winner TEXT, win_price INTEGER, budget INTEGER)""")
    c.executemany("INSERT INTO cgd_winners VALUES (?,?,?,?,?)", [
        ("R1", "ถนน ต.โพนทอง", "หจก.A", 900000, 1000000),
        ("R2", "ถนน ต.โพนทอง", "หจก.A", 850000, 1000000),
        ("R3", "ถนน อ.อื่น", "หจก.A", 700000, 1000000),     # นอก area_ids → ไม่ติด
        ("R4", "ถนน ต.โพนทอง", "หจก.B", 600000, 1000000)])  # คนละบริษัท → ไม่ติด
    c.commit()
    return c


def test_area_portfolio_exact_match_only():
    c = _area_conn()
    out = pv.area_portfolio(c, "หจก.A", ["R1", "R2", "R3"])
    assert out is not None and len(out["jobs"]) == 2, out      # R3 winner≠หจก.A เลยตัด, R4 ไม่อยู่ใน id list
    ids = {j["project_id"] for j in out["jobs"]}
    assert ids == {"R1", "R2"}, ids
    assert pv.area_portfolio(c, "หจก.A", []) is None, "ว่าง → None"
    assert pv.area_portfolio(c, "หจก.ไม่มี", ["R1"]) is None, "ไม่เจอ → None"
    print("✅ area_portfolio: exact project_id match, no fuzzy area logic")


def test_render_company_page_area_section_above_timeline():
    data = {"name": "หจก.A", "tin": "111", "is_sme": False, "total_bids": 2, "wins": 2,
            "win_rate": 100.0, "provinces": ["นครพนม"],
            "discount_hist": [{"lo": 0, "hi": 5, "count": 0}],
            "discount_avg": 12.0, "by_year": [{"year": 2568, "bids": 2, "wins": 2, "jobs": []}]}
    area = {"label_count": 2, "jobs": [{"project_id": "R1", "name": "ถนน ต.โพนทอง",
                                        "price": 900000, "discount": 10.0, "is_winner": True}]}
    html = pv.render_company_page(data, "tok", "", 0, area=area, area_label="🏘 ในตำบลโพนทอง")
    assert "📍 ผลงานในพื้นที่นี้" in html, html
    pos_area = html.index("📍 ผลงานในพื้นที่นี้")
    pos_timeline = html.index("ปี 2568")
    assert pos_area < pos_timeline, "area section ต้องอยู่ก่อน timeline แยกรายปี"
    print("✅ render_company_page: area section ก่อน timeline")


test_area_portfolio_exact_match_only()
test_render_company_page_area_section_above_timeline()
print("ALL PASS portal_views (company/winrate/area tables)")
```

Remove the now-duplicate earlier `print("ALL PASS portal_views (company/winrate tables)")` call from Task 4 Step 1 so there is only one final print statement at the bottom of the file.

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/test_portal_views.py`
Expected: `AttributeError: module 'portal_views' has no attribute 'area_portfolio'`

- [ ] **Step 3: Implement `area_portfolio()` and the area section in `render_company_page()`**

Add this new function to `scripts/portal_views.py` directly after `company_profile()` (after line 259, before the `_CSS` block):

```python
def area_portfolio(conn, name, project_ids):
    """ผลงานของ name เฉพาะใน project_ids (exact match — id มาจาก cgd_intel scope query เดิม,
    ไม่ใช่ fuzzy area parsing ใหม่ — bid_results มีพิกัดน้อยเกิน ~7/1084, deferred ใน spec 2026-06-20 §11).
    None ถ้า project_ids ว่าง หรือไม่เจองานของ name ใน id ชุดนั้น."""
    ids = [p for p in (project_ids or []) if p]
    if not ids:
        return None
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT project_id, project_name, win_price, budget FROM cgd_winners "
        f"WHERE project_id IN ({placeholders}) AND winner=?", (*ids, name)).fetchall()
    if not rows:
        return None
    jobs = []
    for r in rows:
        price = _to_float(r["win_price"])
        jobs.append({"project_id": r["project_id"], "name": r["project_name"] or r["project_id"],
                    "price": price, "discount": _discount(price, _to_float(r["budget"]) or 0),
                    "is_winner": True})
    return {"label_count": len(jobs), "jobs": jobs}
```

Now update `render_company_page()`'s signature and insert the area section. Replace `scripts/portal_views.py:574` (the `def` line):

```python
def render_company_page(data, token, from_pid, exp, h2h=None, won=None, area=None, area_label=""):
```

Replace lines 612-615 (right after the `won` section, before `# timeline แยกรายปี`):

```python
    # 🏆 ผลงานที่ชนะทุกวิธีจัดซื้อ (cgd_winners) — หลังกราฟ, โชว์เฉพาะมีข้อมูล
    if won:
        b.append(_render_won(won, data["tin"], tok, from_pid))
    # 📍 ผลงานในพื้นที่นี้ — เฉพาะเมื่อเข้ามาจากลิงก์ scope (area_ids) ก่อน timeline แยกรายปี (decision: ชูพื้นที่นี้ก่อน)
    if area:
        b.append(f"<div class=\"chart\"><div class=\"ct\">📍 ผลงานในพื้นที่นี้"
                 f"{(' — ' + _h.escape(area_label)) if area_label else ''} ({area['label_count']} งาน)</div>")
        for j in area["jobs"]:
            disc = f"ส่วนลด {j['discount']:.1f}%" if j["discount"] is not None else "—"
            link = f"/portal/job?t={tok}&pid={_h.escape(str(j['project_id']))}"
            b.append(f"<div class=\"jrow\"><a class=\"jn\" href=\"{link}\">✅ {_h.escape(j['name'])}</a>"
                     f"<span class=\"jp\">{_baht(j['price'])}<br><small>{disc}</small></span></div>")
        b.append("</div>")
    # timeline แยกรายปี
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/test_portal_views.py`
Expected: `ALL PASS portal_views (company/winrate/area tables)`

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal_views): area_portfolio exact-match section above timeline on /portal/company"
```

---

## Task 6: `bms_api.py` — wire `area_ids`/`area_label` through `/portal/company`

**Files:**
- Modify: `scripts/bms_api.py:1058-1071` (`portal_company_get`)
- Test: manual route check (no existing automated test file covers this route directly — `test_bms_follow.py` only tests `_follow_status`/`_follow_page_html`; verified by Step 2 below)

**Interfaces:**
- Consumes: `portal_views.area_portfolio(conn, name, project_ids)` (Task 5), `portal_views.render_company_page(data, token, from_pid, exp, h2h, won, area, area_label)` (Task 5)
- Produces: `GET /portal/company?t=...&tin=...&area_ids=R1,R2&area_label=...` renders the area section

- [ ] **Step 1: Implement the route change**

Replace `scripts/bms_api.py:1058-1071`:

```python
@app.get("/portal/company")
async def portal_company_get(t: str = "", tin: str = "", from_: str = Query("", alias="from"),
                             proc: str = "all", area_ids: str = "", area_label: str = ""):
    v = follow_token.verify_token(t)
    if not v:
        return HTMLResponse(_follow_page_html(t, "invalid", {}, "", 0))
    with get_conn() as conn:
        data = portal_views.company_profile(conn, tin)
        cust = conn.execute("SELECT company_tin FROM customers WHERE line_user_id=?", (v[0],)).fetchone()
        our_tin = (cust["company_tin"] if cust and "company_tin" in cust.keys() else None) or None
        h2h = portal_views.head_to_head(conn, our_tin, tin) if our_tin else None
        # cgd_winners join ด้วยชื่อ (winner_tin source เพี้ยน ~99% — N+157) → ใช้ชื่อจาก profile
        won = portal_views.won_portfolio(conn, data["name"], proc) if data else None
        area = None
        if data and area_ids:
            ids = [p.strip() for p in area_ids.split(",") if p.strip()]
            area = portal_views.area_portfolio(conn, data["name"], ids)
    return HTMLResponse(portal_views.render_company_page(data, t, from_, v[2], h2h, won, area, area_label))
```

- [ ] **Step 2: Manual verification (no dedicated route test in this codebase's test suite)**

Run: `python -c "import ast; ast.parse(open('scripts/bms_api.py', encoding='utf-8').read())"`
Expected: no output (syntax valid)

Run the existing full portal-adjacent test to confirm nothing else broke:
Run: `python scripts/test_bms_follow.py`
Expected: `OK test_bms_follow`

- [ ] **Step 3: Commit**

```bash
git add scripts/bms_api.py
git commit -m "feat(bms_api): wire area_ids/area_label query params into /portal/company"
```

---

## Task 7: Full regression pass + sanity check + deploy notes

**Files:** none modified — verification only

- [ ] **Step 1: Run every touched test file in one pass**

Run:
```bash
python scripts/test_bid_field.py && python scripts/test_center_monitor.py && python scripts/test_winrate_grid.py && python scripts/test_cgd_intel.py && python scripts/test_recency.py && python scripts/test_portal_views.py && python scripts/test_bms_follow.py
```
Expected: every file prints its `ALL PASS`/`OK`, no tracebacks

- [ ] **Step 2: Dispatch Sophia (sanity auditor) per CLAUDE.md protocol**

Since this changes pricing/winrate/company-resolution logic that touches `cgd_winners`/`bid_results`, dispatch the `sophia` agent with a description of exactly what changed (the 4 files, the N=1..max ladder, the unlimited company list, the tin-resolution lookup, the area_ids exact-match) and wait for `SAFE`/`STOP` verdict before considering the branch done.

- [ ] **Step 3: Send Discord notification per CLAUDE.md protocol**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "✅ Bid Board intel table redesign เสร็จ — N=1..max win% ladder + company list ไม่จำกัด + คลิกดูประวัติพื้นที่ผ่าน /portal/company. Sophia: <SAFE/STOP>")
```

- [ ] **Step 4: Add a `progress_log.md` entry per CLAUDE.md protocol**

Append an entry following the existing format in `progress_log.md` (สถานะ ✅ เสร็จ, root cause/สิ่งที่ทำ, fix/ผล with concrete numbers e.g. test counts, followup = deploy to VPS).

- [ ] **Step 5: Deployment note (do NOT execute without explicit user confirmation — VPS is shared infra)**

Files to scp to VPS: `bid_field.py`, `cgd_intel.py`, `portal_views.py`, `bms_api.py`. Restart the `bms-api` systemd service. Verify against a real job with full intel via the deployed `/portal/job` URL. This step requires user confirmation before execution (touches shared infra per the "Executing actions with care" policy) — present it as a question rather than running it.

---

## Self-Review Notes (completed during plan authoring)

- **Spec coverage:** §4.1 (N=1..max + N=1=100% hardcode) → Task 1. §4.2 (`field_and_winrate` returns grid) → Task 1. §5.1 (`_scope_block` unlimited + `_resolve_tin`) → Task 2 + Task 3. §5.2 (`company_tables`/`winrate_table` on `_build_intel`) → Task 3. §6.1 (`job_detail` passthrough) → Task 4. §6.2 (`render_job_page` new tables) → Task 4. §6.3 (`area_portfolio` + `/portal/company` area section + route params) → Task 5 + Task 6. §7 edge cases (empty/short names → Task 3's `_resolve_tin` None-checks; duplicate companies across dual blocks not deduped → intentionally left as-is, matches spec; stale area_ids → `area_portfolio` returns `None` gracefully when no rows match; failed gate → no table → `winrate_table=None` short-circuits in `render_job_page`; single-N-column / very-wide N → no cap, `overflow-x:auto` via `.tblwrap`) → Task 4/5. §8 testing plan → each task's Step 1.
- **Placeholder scan:** no "TBD"/"similar to Task N" — every step has complete code. Task 6 Step 2 explicitly notes no dedicated automated route test exists for `/portal/company` in this codebase (verified by reading `test_bms_follow.py` in full) rather than inventing a fake test file reference.
- **Type/signature consistency:** `_scope_block()` 8-tuple shape is identical across Task 2 (definition) and Task 3 (all 4 call sites). `field_and_winrate()`'s `(grid, field_lines, conf)` shape is identical across Task 1 (definition + its own tests) and Task 3 (the one production call site). `render_company_page()`'s 2 new trailing optional kwargs (`area=None, area_label=""`) don't break the Task 6 call site (positional args unchanged, new ones appended) or the existing `bms_api.py` call before Task 6 runs.
