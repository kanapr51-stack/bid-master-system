# Tambon-Level Competitor Intel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) or subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** ยกระดับ competitive intel ในการ์ด D0 เป็นโปรไฟล์คู่แข่งรายบริษัทระดับท้องถิ่น (ตำบล→อำเภอ→จังหวัด) + ค่าความน่าเชื่อถือ

**Architecture:** ต่อยอด `scripts/cgd_intel.py`. เพิ่ม district+subdistrict ใน cgd_winners (v121+re-sync). resolve ตำบลงาน D0 จาก name/dept (ฟรี — ไม่เรียก API ใน notify path, บทเรียน INC-001). selection ไล่ระดับ + **derive อำเภอจาก cgd_winners** (`DISTINCT district WHERE subdistrict=ตำบล`; หลายอำเภอ=ambiguous→province). per-company stat คิดจากประวัติบริษัท (กลบ sparsity). competitive-set filter ทั้ง selection+stat.

**Tech Stack:** Python 3, sqlite3, pytest-less (assert scripts), job_matcher reuse

**Spec:** `docs/superpowers/specs/2026-06-07-tambon-competitor-intel-design.md`

---

## File Structure
- `scripts/Sebastian_Customer_DB.py` — เพิ่ม `_migrate_v121` (cgd_winners +district +subdistrict)
- `scripts/cgd_sync_to_vps.py` — extract/merge ส่ง district+subdistrict
- `scripts/cgd_intel.py` — เพิ่ม `resolve_tambon`/`_fetch`/`_fetch_winner`/`select_competitors`/`company_stats`/`confidence_label`; rewrite `intel_lines`; ลบ `query_similar`/`compute_stats` (เลิกใช้)
- `scripts/Sebastian_LINE_Sender.py` — wiring ส่ง `dept_name` เข้า `intel_lines`
- `scripts/test_cgd_intel.py`, `scripts/test_cgd_sync.py` — tests

**Config constants (cgd_intel.py):** `MIN_COMPETITORS=2`, `SHOW_N=3`, `MIN_GAMES_FOR_IQR=3`, `IQR_WIDE=20`

---

### Task 1: migrate v121 — cgd_winners +district +subdistrict

**Files:** Modify `scripts/Sebastian_Customer_DB.py` (init_schema call list + new fn), `scripts/test_cgd_sync.py`

- [ ] **Step 1: เพิ่ม assertion ใน test_cgd_sync.py** (หลัง `assert "project_id" in cols ...`)
```python
assert "district" in cols and "subdistrict" in cols, cols  # v121
```
- [ ] **Step 2: รัน → FAIL** `python scripts/test_cgd_sync.py` → AssertionError (ไม่มี district)
- [ ] **Step 3: เพิ่ม `_migrate_v121()` + เรียกใน init_schema** (หลัง `_migrate_v120()`)
```python
    _migrate_v120()
    _migrate_v121()
```
```python
def _migrate_v121():
    """cgd_winners +district +subdistrict — competitor intel ระดับตำบล/อำเภอ (winner_history
    มี district 100%, subdistrict 91%). additive ALTER (idempotent). ต้อง re-sync 617K หลัง migrate."""
    with get_connection() as conn:
        for col in ("district", "subdistrict"):
            try:
                conn.execute(f"ALTER TABLE cgd_winners ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # already exists
```
- [ ] **Step 4: รัน → PASS** `python scripts/test_cgd_sync.py`
- [ ] **Step 5: Commit** `git add -A scripts/Sebastian_Customer_DB.py scripts/test_cgd_sync.py && git commit -m "feat(db): migrate v121 — cgd_winners +district +subdistrict"`

---

### Task 2: cgd_sync — extract/merge ส่ง district+subdistrict

**Files:** Modify `scripts/cgd_sync_to_vps.py`, `scripts/test_cgd_sync.py`

- [ ] **Step 1: แก้ test fixture + assertion** ใน test_cgd_sync.py — แก้ INSERT winner_history ให้ใส่ district/subdistrict + assert ไหลผ่าน
```python
c.execute("INSERT INTO winner_history (project_id,province,district,subdistrict,winner,win_price,fiscal_year,proc_type) "
          "VALUES ('A1','นครพนม','บ้านแพง','โพนทอง','บ.B',500000,'2568','สอบราคา')")
```
แก้ assertion subset:
```python
assert subset[0]["district"] == "บ้านแพง" and subset[0]["subdistrict"] == "โพนทอง", subset[0]  # v121
```
- [ ] **Step 2: รัน → FAIL** `python scripts/test_cgd_sync.py` → KeyError 'district'
- [ ] **Step 3: แก้ cgd_sync_to_vps.py — 3 จุด**

`_MERGE_SQL` (เพิ่ม 2 col + 2 `?`):
```python
_MERGE_SQL = """INSERT OR REPLACE INTO cgd_winners
    (project_id, province, dept, project_name, winner, winner_tin, budget,
     win_price, discount_pct, announce_date, fiscal_year, proc_type, district, subdistrict, synced_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
```
`merge_winners` buf tuple (เพิ่มก่อน `now`):
```python
            buf.append((r["project_id"], r.get("province"), r.get("dept"), r.get("project_name"),
                        r.get("winner"), r.get("winner_tin"), r.get("budget"), r.get("win_price"),
                        r.get("discount_pct"), r.get("announce_date"), r.get("fiscal_year"),
                        r.get("proc_type"), r.get("district"), r.get("subdistrict"), now))
```
`extract_subset` SELECT:
```python
        f"SELECT project_id, province, dept, project_name, winner, winner_tin, budget, "
        f"win_price, discount_pct, announce_date, fiscal_year, proc_type, district, subdistrict "
        f"FROM winner_history WHERE province IN ({qs})", provinces)]
```
- [ ] **Step 4: รัน → PASS** `python scripts/test_cgd_sync.py`
- [ ] **Step 5: Commit** `git add -A scripts/cgd_sync_to_vps.py scripts/test_cgd_sync.py && git commit -m "feat(cgd): sync district+subdistrict (re-sync needed)"`

---

### Task 3: resolve_tambon + _fetch helper

**Files:** Modify `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: เขียน test** (เพิ่มใน test_cgd_intel.py — แทน _fixture_conn ให้มี district/subdistrict; ดู Task 4 สำหรับ fixture ใหม่; test นี้เน้น resolve_tambon)
```python
def test_resolve_tambon():
    # name: "ต.โพนทอง" → โพนทอง
    assert ci.resolve_tambon("ก่อสร้างถนน ต.โพนทอง", "") == "โพนทอง"
    # dept fallback: อบต.บ้านแพง → บ้านแพง
    assert ci.resolve_tambon("ก่อสร้างถนน", "องค์การบริหารส่วนตำบลบ้านแพง") == "บ้านแพง"
    # ไม่มี → ''
    assert ci.resolve_tambon("ก่อสร้างถนน", "") == ""
    print("✅ resolve_tambon")
```
- [ ] **Step 2: รัน → FAIL** `BMS_ENV=dev python scripts/test_cgd_intel.py` → AttributeError resolve_tambon
- [ ] **Step 3: เพิ่ม constants + resolve_tambon + _fetch ใน cgd_intel.py** (หลัง RECENT_FY)
```python
MIN_COMPETITORS = 2     # distinct winners ขั้นต่ำก่อนหยุด fallback
SHOW_N = 3              # จำนวนบริษัทที่โชว์
MIN_GAMES_FOR_IQR = 3   # ต่ำกว่านี้โชว์แค่ median
IQR_WIDE = 20           # p75-p25 เกินนี้ = ช่วงกว้าง (ลดความเชื่อมั่น)


def resolve_tambon(project_name: str, dept_name: str = "") -> str:
    """ตำบลของงาน D0 จาก name → dept (ฟรี ไม่เรียก API — บทเรียน INC-001: resolve API ใน
    notify path ทำ WAF block). resolve ไม่ได้ → '' (intel_lines degrade เป็นจังหวัด)."""
    try:
        import job_matcher as jm
        return jm.tambon_from_name(project_name) or jm.tambon_from_dept(dept_name)
    except Exception:
        return ""


def _fetch(conn, province: str, tokens: list, *, subdistrict=None, district=None) -> list:
    """ดึงงาน competitive ของ work-type (LIKE any token) ใน province + (เลือก subdistrict/district).
    คืน list[dict] (รวม district/subdistrict). graceful [] ถ้าไม่มี table/column."""
    fy_ph = ",".join("?" for _ in RECENT_FY)
    pt_ph = ",".join("?" for _ in COMPETITIVE_SET)
    like = " OR ".join("project_name LIKE ?" for _ in tokens)
    where = ["province=?", "win_price>0", f"fiscal_year IN ({fy_ph})",
             f"proc_type IN ({pt_ph})", f"({like})"]
    params = [province, *RECENT_FY, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    if subdistrict is not None:
        where.append("subdistrict=?"); params.append(subdistrict)
    if district is not None:
        where.append("district=?"); params.append(district)
    try:
        cur = conn.execute(
            "SELECT project_name, winner, win_price, discount_pct, district, subdistrict "
            "FROM cgd_winners WHERE " + " AND ".join(where), params)
        return [{"project_name": r[0], "winner": r[1], "win_price": r[2],
                 "discount_pct": r[3], "district": r[4], "subdistrict": r[5]}
                for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []
```
- [ ] **Step 4: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py` (test_resolve_tambon ผ่าน; tests เก่าอาจพังเพราะ fixture เก่า — แก้ใน Task 4)
- [ ] **Step 5: Commit** `git add -A scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "feat(intel): resolve_tambon (free) + _fetch location helper"`

---

### Task 4: select_competitors — ไล่ระดับ + derive อำเภอ + ambiguity

**Files:** Modify `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: แทน `_fixture_conn` ใน test_cgd_intel.py** (เพิ่ม district/subdistrict + งานหลายตำบล/อำเภอ)
```python
def _fixture_conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    rows = [
        # pid, prov, pname, winner, wp, disc, fy, proc, district, subdistrict
        ("R1","นครพนม","ถนน คสล. บ้านแพง","หจก.A",950000,5.0,"2567",EB,"บ้านแพง","โพนทอง"),
        ("R2","นครพนม","ถนนลาดยาง บ้านแพง","หจก.A",900000,8.0,"2567",EB,"บ้านแพง","โพนทอง"),
        ("R3","นครพนม","ถนน คสล.","หจก.B",800000,10.0,"2568",EB,"บ้านแพง","โพนทอง"),
        ("R4","นครพนม","ถนนเมือง","หจก.C",700000,12.0,"2567",EB,"เมืองนครพนม","ในเมือง"),
        ("R5","นครพนม","ถนนเฉพาะเจาะจง","หจก.D",1000000,0.0,"2567","เฉพาะเจาะจง","บ้านแพง","โพนทอง"),
    ]
    for pid,prov,pname,win,wp,disc,fy,proc,dist,sub in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid,prov,pname,win,wp,disc,fy,proc,dist,sub))
    c.commit(); return c
```
- [ ] **Step 2: เขียน test_select_competitors**
```python
def test_select_competitors():
    c = _fixture_conn(); tk = ["ถนน"]
    # tambon โพนทอง อ.บ้านแพง: winners A,B (≥MIN=2) → level tambon. R5 เฉพาะเจาะจงถูกตัด
    rows, scope, level = ci.select_competitors("นครพนม", tk, "โพนทอง", c)
    assert level == "tambon" and "ต.โพนทอง" in scope, (level, scope)
    assert {r["winner"] for r in rows} == {"หจก.A", "หจก.B"}, rows
    assert all(r["proc_type"] != "เฉพาะเจาะจง" for r in rows) if rows and "proc_type" in rows[0] else True
    # ตำบลที่ไม่มี → fallback province (level province)
    rows2, scope2, level2 = ci.select_competitors("นครพนม", tk, "ไม่มีตำบลนี้", c)
    assert level2 == "province" and {"หจก.A","หจก.B","หจก.C"} <= {r["winner"] for r in rows2}, (level2, rows2)
    # resolve ไม่ได้ (tambon='') → province
    assert ci.select_competitors("นครพนม", tk, "", c)[2] == "province"
    print("✅ select_competitors")
```
- [ ] **Step 3: รัน → FAIL** `BMS_ENV=dev python scripts/test_cgd_intel.py` → AttributeError select_competitors
- [ ] **Step 4: เพิ่ม `_distinct_winners` + `select_competitors`**
```python
def _distinct_winners(rows: list) -> int:
    return len({r["winner"] for r in rows if r.get("winner")})


def select_competitors(province: str, tokens: list, tambon: str, conn) -> tuple:
    """เลือกคู่แข่งไล่ระดับ ตำบล→อำเภอ→จังหวัด. คืน (rows, scope_label, level).
    อำเภอ derive จาก cgd_winners (DISTINCT district ของตำบล) — หลายอำเภอ=ambiguous→province.
    competitive-set ถูกกรองใน _fetch แล้ว (เฉพาะเจาะจงไม่หลุด)."""
    wt = tokens[0] if tokens else "งาน"
    if tambon:
        trows = _fetch(conn, province, tokens, subdistrict=tambon)
        districts = {r["district"] for r in trows if r.get("district")}
        if len(districts) == 1:
            d = next(iter(districts))
            if _distinct_winners(trows) >= MIN_COMPETITORS:
                return trows, f"งาน{wt} ต.{tambon} อ.{d}", "tambon"
            arows = _fetch(conn, province, tokens, district=d)   # widen → อำเภอ
            if _distinct_winners(arows) >= MIN_COMPETITORS:
                return arows, f"งาน{wt} อ.{d}", "amphoe"
        # ambiguous (หลายอำเภอ) / ไม่มี / ไม่พอ → province
    prows = _fetch(conn, province, tokens)
    if _distinct_winners(prows) >= 1:
        return prows, f"งาน{wt}ใน{province}", "province"
    return [], "", "province"
```
- [ ] **Step 5: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 6: Commit** `git add -A scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "feat(intel): select_competitors ไล่ระดับ ตำบล→อำเภอ→จังหวัด"`

---

### Task 5: company_stats + confidence_label

**Files:** Modify `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: เขียน tests**
```python
def test_company_stats():
    c = _fixture_conn(); tk = ["ถนน"]
    # หจก.A มี 2 งาน (disc 5,8) → games=2 < MIN_GAMES_FOR_IQR=3 → ไม่มี IQR, median=6.5
    s = ci.company_stats("หจก.A", tk, c)
    assert s["games"] == 2 and s["median"] == 6.5 and s["p25"] is None, s
    print("✅ company_stats")

def test_confidence_label():
    assert ci.confidence_label(40, 5, 10).startswith("🟢")
    assert ci.confidence_label(15, 5, 10).startswith("🟡")     # n<30
    assert ci.confidence_label(40, 5, 30).startswith("🟡")     # IQR กว้าง (25>20)
    assert ci.confidence_label(5, None, None).startswith("🔴") # n<10
    print("✅ confidence_label")
```
- [ ] **Step 2: รัน → FAIL** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 3: เพิ่ม `_fetch_winner` + `company_stats` + `confidence_label`**
```python
def _fetch_winner(conn, winner: str, tokens: list) -> list:
    """ส่วนลดของ winner รายนั้น (work-type เดียวกัน, competitive, recent FY). คือประวัติบริษัท
    (cgd_winners = subset target provinces อยู่แล้ว → ไม่ต้อง filter province)."""
    fy_ph = ",".join("?" for _ in RECENT_FY)
    pt_ph = ",".join("?" for _ in COMPETITIVE_SET)
    like = " OR ".join("project_name LIKE ?" for _ in tokens)
    params = [winner, *RECENT_FY, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
    try:
        cur = conn.execute(
            "SELECT discount_pct FROM cgd_winners WHERE winner=? AND win_price>0 "
            f"AND fiscal_year IN ({fy_ph}) AND proc_type IN ({pt_ph}) AND ({like})", params)
        return [r[0] for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def company_stats(winner: str, tokens: list, conn) -> dict:
    """median (+IQR ถ้า games≥MIN_GAMES_FOR_IQR) ส่วนลดจากประวัติบริษัท."""
    discs = [d for d in _fetch_winner(conn, winner, tokens) if d is not None]
    games = len(_fetch_winner(conn, winner, tokens))
    out = {"games": games, "median": _pct(discs, 50), "p25": None, "p75": None}
    if len(discs) >= MIN_GAMES_FOR_IQR:
        out["p25"], out["p75"] = _pct(discs, 25), _pct(discs, 75)
    return out


def confidence_label(area_n: int, p25, p75) -> str:
    """ป้ายความเชื่อมั่นทางสถิติ (จาก n + ความกว้าง IQR). คนละมิติกับ relevance (= header level)."""
    wide = p25 is not None and p75 is not None and (p75 - p25) > IQR_WIDE
    if area_n < 10:
        return "🔴 ข้อมูลน้อย — โปรดใช้วิจารณญาณ"
    if area_n < 30 or wide:
        return "🟡 เชื่อมั่นปานกลาง — ข้อมูลน้อย/ช่วงกว้าง (ดูเป็นแนวโน้ม ไม่ใช่ราคาตายตัว)"
    return "🟢 เชื่อถือได้ — ข้อมูลมากพอ"
```
> **หมายเหตุ:** `company_stats` เรียก `_fetch_winner` 2 ครั้ง (games + discs) — รับได้ (D0 volume ต่ำ, ≤3 บริษัท). ถ้าอยากเร็วรวมเป็น query เดียวภายหลังได้.
- [ ] **Step 4: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 5: Commit** `git add -A scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "feat(intel): company_stats (ประวัติบริษัท) + confidence_label"`

---

### Task 6: rewrite intel_lines (orchestrate + format) + ลบโค้ดเก่า

**Files:** Modify `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: แทน test_intel_lines + ลบ test เก่า (test_query_similar, test_compute_stats)**
```python
def test_intel_lines():
    c = _fixture_conn()
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", conn=c)
    assert out[0] == "💡 ราคาอ้างอิง (งานถนน ต.โพนทอง อ.บ้านแพง)", out[0]
    assert "🏆 คู่แข่งแถบนี้:" in out
    assert any("หจก.A" in l and "งาน" in l for l in out), out
    assert any(l.startswith("📊 ภาพรวม") for l in out), out
    assert any(l[0] in "🟢🟡🔴" for l in out), out
    # ชื่อไม่มี work-type → []
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", conn=c) == []
    # ไม่มีคู่แข่งในจังหวัด → []
    assert ci.intel_lines("เชียงใหม่", "ก่อสร้างถนน", conn=c) == []
    print("✅ intel_lines")
```
- [ ] **Step 2: รัน → FAIL** (intel_lines เก่ายังคืน format เดิม / เรียก query_similar)
- [ ] **Step 3: ลบ `query_similar`, `compute_stats` + แทน `intel_lines`** ใน cgd_intel.py
```python
def intel_lines(province: str, project_name: str, dept_name: str = "", conn=None) -> list:
    """บรรทัด 💡 competitor intel ระดับท้องถิ่นสำหรับการ์ด D0. คืน [] ถ้าไม่มีคู่แข่ง/error.
    พระเอก=โปรไฟล์คู่แข่งรายบริษัท (selection ไล่ระดับ ตำบล→อำเภอ→จังหวัด, stat จากประวัติบริษัท)
    + ภาพรวมเสริม + ป้ายความเชื่อมั่น. competitive-set กรองทั้ง selection+stat. ห่อ try/except."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return []
        own = conn is None
        if own:
            from Sebastian_Customer_DB import get_connection
            conn = get_connection()
        try:
            tambon = resolve_tambon(project_name, dept_name)
            rows, scope, _level = select_competitors(province, tokens, tambon, conn)
            if not rows:
                return []
            counts = Counter(r["winner"] for r in rows if r.get("winner"))
            lines = [f"💡 ราคาอ้างอิง ({scope})", "🏆 คู่แข่งแถบนี้:"]
            for winner, _ in counts.most_common(SHOW_N):
                cs = company_stats(winner, tokens, conn)
                nm = (winner or "?")[:28]
                if cs["p25"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}% "
                                 f"({cs['p25']:.0f}–{cs['p75']:.0f}%)")
                elif cs["median"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}%")
                else:
                    lines.append(f"  • {nm} · {cs['games']} งาน")
            discs = [r["discount_pct"] for r in rows if r.get("discount_pct") is not None]
            area_n = len(rows)
            p25, p75 = _pct(discs, 25), _pct(discs, 75)
            if p75:
                lines.append(f"📊 ภาพรวม {area_n} งาน · ลด {p25:.0f}–{p75:.0f}%")
            else:
                lines.append(f"📊 ภาพรวม {area_n} งาน")
            lines.append(confidence_label(area_n, p25, p75))
            return lines
        finally:
            if own:
                conn.close()
    except Exception:
        return []
```
- [ ] **Step 4: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py` (ครบทุก test รวม wiring)
- [ ] **Step 5: Commit** `git add -A scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "feat(intel): rewrite intel_lines → competitor-profile + confidence"`

---

### Task 7: wiring — ส่ง dept_name เข้า intel_lines

**Files:** Modify `scripts/Sebastian_LINE_Sender.py:260`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: ตรวจ test_wiring_format_notification** — มันใช้ `_ci.intel_lines = lambda *a, **k:` (รับ args ได้อยู่แล้ว) → ไม่ต้องแก้ test
- [ ] **Step 2: แก้ call site** `Sebastian_LINE_Sender.py` บรรทัด ~260
```python
            _il = cgd_intel.intel_lines(province, project_name, dept_name)
```
- [ ] **Step 3: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py` (test_wiring ผ่าน)
- [ ] **Step 4: Commit** `git add -A scripts/Sebastian_LINE_Sender.py && git commit -m "feat(intel): wire dept_name เข้า intel_lines (resolve ตำบล)"`

---

### Task 8: Deploy — re-sync 617K + verify (ops, ไม่ใช่ TDD)

**Files:** none (deploy)

- [ ] **Step 1: push** `git push origin main`
- [ ] **Step 2: VPS pull + backup ก่อน schema change**
```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cd /opt/bms/app && sudo -u bms git pull --ff-only && sudo -u bms cp /opt/bms/data/bms_customers.db /opt/bms/data/backups/bms_customers_pre_v121_$(date +%Y%m%d_%H%M%S).db"
```
- [ ] **Step 3: re-sync 617K (เครื่องบ้าน)** `python scripts/cgd_sync_to_vps.py --push`
Expected: `extract 617357 row ... ✅ merge 617357`
- [ ] **Step 4: Sanity check VPS** (rows เท่าเดิม + district/subdistrict populated + intel ตัวอย่าง)
```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "sudo -u bms BMS_DATA_DIR=/opt/bms/data BMS_ENV=prod /opt/bms/venv/bin/python -X utf8 -c \"
import sqlite3,sys; sys.path.insert(0,'/opt/bms/app/scripts')
c=sqlite3.connect('/opt/bms/data/bms_customers.db')
print('rows:', c.execute('SELECT COUNT(*) FROM cgd_winners').fetchone()[0])
print('district populated:', c.execute('SELECT COUNT(*) FROM cgd_winners WHERE district IS NOT NULL').fetchone()[0])
import cgd_intel as ci
for l in ci.intel_lines('นครพนม','ก่อสร้างถนน คสล. ต.โพนทอง', 'องค์การบริหารส่วนตำบลบ้านแพง'): print(l)
\""
```
Expected: rows=617357, district populated >560000, intel โชว์ competitor-profile + ป้ายสี
- [ ] **Step 5: update progress_log + memory + Discord**

---

## Self-Review
- **Spec coverage:** ✅ competitor-profile (T5,T6) · location hierarchy (T4) · derive amphoe+ambiguity (T4) · per-company stat broad (T5) · confidence label (T5) · competitive-set ทั้ง 2 จุด (_fetch + _fetch_winner) · schema+sync (T1,T2) · wiring (T7) · deploy (T8)
- **Refinement vs spec:** (1) amphoe derive จาก data ไม่ใช่ tambon_lookup (map ผิดเป็น province) (2) resolve ตำบล name+dept เท่านั้น ไม่เรียก API ใน notify path (INC-001) — ทั้ง 2 ทำให้ robust+ปลอดภัยกว่า, degrade graceful
- **Placeholder scan:** ไม่มี — ทุก step มีโค้ด/คำสั่งจริง
- **Type consistency:** rows dict keys (project_name/winner/win_price/discount_pct/district/subdistrict) สม่ำเสมอทุก task · company_stats คืน games/median/p25/p75 ใช้ตรงใน intel_lines · select_competitors คืน (rows,scope,level) ตรง
