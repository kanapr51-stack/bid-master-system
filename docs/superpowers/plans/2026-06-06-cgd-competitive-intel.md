# CGD Competitive Intel ใน D0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) หรือ superpowers:executing-plans. Steps ใช้ checkbox (`- [ ]`).

**Goal:** แนบ "ราคาอ้างอิงจากผู้ชนะงานคล้ายในพื้นที่" (จาก `cgd_winners`) เข้าการ์ดแจ้งเปิดประมูล D0 — descriptive ไม่ prescriptive

**Architecture:** โมดูลใหม่ `scripts/cgd_intel.py` (query+stat+format แยก domain) + wiring 1 จุดใน `Sebastian_LINE_Sender.format_notification` (ห่อ try/except — intel = value-add). ใช้ median/p25/p75 (ทน outlier), similar = ≥2 token (fallback ≥1), min_count=10 (ไม่ถึง→omit).

**Tech Stack:** Python (sqlite3, statistics manual percentile, json). reuse `config/matching_preferences.json["keywords"]` + `Sebastian_Customer_DB.get_connection`.

**Spec:** `docs/superpowers/specs/2026-06-06-cgd-competitive-intel-design.md`

**Runtime:** test `BMS_ENV=dev python scripts/test_cgd_intel.py` (เครื่องไหนก็ได้ — inject conn). production query รันบน VPS (`cgd_winners` อยู่ที่ bms_customers.db บน VPS).

---

## File Structure
- `scripts/cgd_intel.py` (ใหม่) — `match_keywords` · `query_similar` · `compute_stats` · `intel_lines` · `_pct` helper
- `scripts/test_cgd_intel.py` (ใหม่) — unit tests (inject conn + fixture, ไม่ยิง DB จริง)
- `scripts/Sebastian_LINE_Sender.py` (แก้ `format_notification` ~บรรทัด 256) — wiring + wiring test

---

## Task 1: `match_keywords` — work-type tokens ในชื่องาน

**Files:** Create `scripts/cgd_intel.py` · Create `scripts/test_cgd_intel.py`

- [ ] **Step 1: Write failing test**
```python
"""test_cgd_intel.py — competitive intel (query cgd_winners → stats → LINE lines)."""
import sys, sqlite3; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci

def test_match_keywords():
    kws = ["ถนน", "คสล", "อาคาร"]
    assert ci.match_keywords("ก่อสร้างถนน คสล. บ้านแพง", keywords=kws) == ["ถนน", "คสล"]
    assert ci.match_keywords("จัดซื้อรถยนต์", keywords=kws) == []
    assert ci.match_keywords("", keywords=kws) == []
    # default โหลด config จริง — งานถนนต้องเจอ token
    assert "ถนน" in ci.match_keywords("ปรับปรุงถนนลาดยาง")
    print("✅ match_keywords")

if __name__ == "__main__":
    test_match_keywords()
    print("ALL PASS (Task 1)")
```

- [ ] **Step 2: Run → FAIL** — `python scripts/test_cgd_intel.py` → `ModuleNotFoundError: cgd_intel`

- [ ] **Step 3: Implement** (สร้าง `scripts/cgd_intel.py`)
```python
"""cgd_intel.py — competitive intel จาก cgd_winners: ผู้ชนะงานคล้ายในพื้นที่ + ราคา/ส่วนลด.
descriptive เท่านั้น (ตลาดเป็นยังไง) ไม่ prescriptive (ไม่บอกราคาที่ควรยื่น).
ใช้แนบการ์ด D0 (source_stage=followed_bid_open). intel = value-add — ห้ามทำ notification พัง."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_KW_PATH = Path(__file__).parent.parent / "config" / "matching_preferences.json"


def _load_keywords() -> list:
    return json.load(open(_KW_PATH, encoding="utf-8")).get("keywords", [])


def match_keywords(project_name: str, keywords: list = None) -> list:
    """คืน work-type tokens ที่ปรากฏในชื่องาน (vocab เดียวกับ job_matcher). ไม่ซ้ำ."""
    kws = keywords if keywords is not None else _load_keywords()
    name = project_name or ""
    out = []
    for kw in kws:
        if kw and kw in name and kw not in out:
            out.append(kw)
    return out
```

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `git commit -m "feat(intel): match_keywords work-type tokens (Task 1)"`

---

## Task 2: `query_similar` — ดึงงานคล้ายจาก cgd_winners (province + overlap)

**Files:** Modify `scripts/cgd_intel.py` · `scripts/test_cgd_intel.py`

- [ ] **Step 1: Write failing test** (เพิ่มใน test_cgd_intel.py)
```python
def _fixture_conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT, synced_at TEXT)""")
    rows = [
        ("R1","นครพนม","ก่อสร้างถนน คสล. บ้านแพง","หจก.A",1000000,950000,5.0),  # ถนน+คสล overlap2
        ("R2","นครพนม","ซ่อมถนนลูกรัง","หจก.B",800000,760000,5.0),               # ถนน overlap1
        ("R3","บึงกาฬ","ก่อสร้างถนน คสล.","หจก.C",1000000,900000,10.0),          # คนละจังหวัด
        ("R4","นครพนม","ก่อสร้างถนน คสล.","หจก.D",1000000,0,None),               # win_price=0 ตัด
    ]
    for pid, prov, pname, win, bud, wp, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,budget,"
                  "win_price,discount_pct) VALUES (?,?,?,?,?,?,?)",
                  (pid, prov, pname, win, bud, wp, disc))
    c.commit(); return c

def test_query_similar():
    c = _fixture_conn(); tk = ["ถนน", "คสล"]
    r2 = ci.query_similar("นครพนม", tk, min_overlap=2, conn=c)
    assert [x["project_name"] for x in r2] == ["ก่อสร้างถนน คสล. บ้านแพง"], r2
    r1 = ci.query_similar("นครพนม", tk, min_overlap=1, conn=c)
    assert len(r1) == 2, r1   # R1+R2 (R3 คนละจังหวัด, R4 win_price=0)
    assert ci.query_similar("", tk, 1, conn=c) == []
    # graceful: ไม่มี table cgd_winners → []
    empty = sqlite3.connect(":memory:")
    assert ci.query_similar("นครพนม", tk, 1, conn=empty) == []
    print("✅ query_similar")
```
เพิ่มใน `__main__`: `test_query_similar()`

- [ ] **Step 2: Run → FAIL** — `AttributeError: module 'cgd_intel' has no attribute 'query_similar'`

- [ ] **Step 3: Implement** (เพิ่มใน cgd_intel.py)
```python
def query_similar(province: str, tokens: list, min_overlap: int, conn=None) -> list:
    """งานใน cgd_winners ที่ province ตรง + ชื่อมี ≥ min_overlap ของ tokens + win_price>0.
    candidate fetch = LIKE ANY token (ใช้ idx province) → filter overlap ใน Python.
    conn inject ได้ (test); default = Sebastian_Customer_DB.get_connection()."""
    if not province or not tokens:
        return []
    own = conn is None
    if own:
        from Sebastian_Customer_DB import get_connection
        conn = get_connection()
    try:
        like = " OR ".join("project_name LIKE ?" for _ in tokens)
        params = [province] + [f"%{t}%" for t in tokens]
        try:
            cur = conn.execute(
                f"SELECT project_name, winner, win_price, discount_pct FROM cgd_winners "
                f"WHERE province=? AND win_price>0 AND ({like})", params)
            fetched = cur.fetchall()
        except sqlite3.OperationalError:
            return []   # ไม่มี table cgd_winners → graceful
        out = []
        for row in fetched:
            pname, winner, win_price, disc = row[0], row[1], row[2], row[3]
            if sum(1 for t in tokens if t in (pname or "")) >= min_overlap:
                out.append({"project_name": pname, "winner": winner,
                            "win_price": win_price, "discount_pct": disc})
        return out
    finally:
        if own:
            conn.close()
```

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `feat(intel): query_similar province+overlap filter (Task 2)`

---

## Task 3: `compute_stats` — median/p25/p75 + price range + top winners

**Files:** Modify `scripts/cgd_intel.py` · `scripts/test_cgd_intel.py`

- [ ] **Step 1: Write failing test**
```python
def test_compute_stats():
    rows = [{"win_price": p, "discount_pct": d, "winner": w} for p, d, w in [
        (1_000_000, 2.0, "หจก.A"), (1_200_000, 3.0, "หจก.A"), (1_500_000, 4.0, "หจก.A"),
        (2_000_000, 5.0, "หจก.B"), (3_000_000, 20.0, "หจก.B"), (1_100_000, 4.0, "หจก.C")]]
    s = ci.compute_stats(rows)
    assert s["count"] == 6
    assert s["discount_median"] == 4.0, s["discount_median"]   # median ของ [2,3,4,4,5,20]
    assert s["discount_p25"] == 3.25 and s["discount_p75"] == 4.75, (s["discount_p25"], s["discount_p75"])
    assert s["top_winners"][0] == ("หจก.A", 3), s["top_winners"]
    assert s["price_lo"] is not None and s["price_hi"] >= s["price_lo"]
    # discount ทั้งหมด null → median/p25/p75 = None
    s2 = ci.compute_stats([{"win_price": 100, "discount_pct": None, "winner": "X"}])
    assert s2["discount_median"] is None and s2["discount_p25"] is None
    print("✅ compute_stats")
```
เพิ่มใน `__main__`: `test_compute_stats()`

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement** (เพิ่มใน cgd_intel.py)
```python
def _pct(values: list, p: float):
    """percentile แบบ linear interpolation (deterministic). values ไม่ต้อง sort มาก่อน."""
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(v) - 1)
    if f == c:
        return v[f]
    return v[f] + (v[c] - v[f]) * (k - f)


def compute_stats(rows: list) -> dict:
    """สถิติตลาด: count, ส่วนลด median/p25/p75, ช่วงราคาชนะ p10/p90, ผู้ชนะบ่อย top3+count."""
    discs = [r["discount_pct"] for r in rows if r.get("discount_pct") is not None]
    prices = [r["win_price"] for r in rows if r.get("win_price")]
    winners = Counter(r["winner"] for r in rows if r.get("winner"))
    return {
        "count": len(rows),
        "discount_median": _pct(discs, 50),
        "discount_p25": _pct(discs, 25),
        "discount_p75": _pct(discs, 75),
        "price_lo": _pct(prices, 10),
        "price_hi": _pct(prices, 90),
        "top_winners": winners.most_common(3),
    }
```
> หมายเหตุ: median ของ [2,3,4,4,5,20] (n=6) = (v[2]+v[3])/2 interpolate ที่ k=2.5 → 4.0. p25 ที่ k=1.25 → 3+0.25=3.25. p75 ที่ k=3.75 → 4+0.75=4.75.

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `feat(intel): compute_stats median/p25/p75+price+winners (Task 3)`

---

## Task 4: `intel_lines` — orchestrate strict→relax→silence + format

**Files:** Modify `scripts/cgd_intel.py` · `scripts/test_cgd_intel.py`

- [ ] **Step 1: Write failing test**
```python
def test_intel_lines():
    c = _fixture_conn()   # มีงานนครพนมแค่ 2 (R1,R2) → < min_count
    # ต่ำกว่า threshold → []
    assert ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล.", min_count=10, conn=c) == []
    # ชื่อไม่มี work-type → []
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", min_count=1, conn=c) == []
    # min_count=1 → ได้ section (ทดสอบ format)
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล.", min_count=1, conn=c)
    assert out[0] == "💡 ราคาอ้างอิง (งานถนนในนครพนม)", out[0]
    assert any(l.startswith("📊 จาก 1 งาน") for l in out)        # ≥2-overlap = R1 เดี่ยว
    assert any("ส่วนลดที่พบบ่อย" in l for l in out)
    assert any(l.strip().startswith("• หจก.A (1)") for l in out)
    # fallback: ≥2 ได้ 1 (<3) → relax ≥1 ได้ 2
    out2 = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล.", min_count=2, conn=c)
    assert any(l.startswith("📊 จาก 2 งาน") for l in out2), out2
    print("✅ intel_lines")
```
เพิ่มใน `__main__`: `test_intel_lines()`

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement** (เพิ่มใน cgd_intel.py)
```python
def intel_lines(province: str, project_name: str, min_count: int = 10, conn=None) -> list:
    """บรรทัด 💡 competitive intel สำหรับแนบการ์ด D0. คืน [] ถ้าข้อมูลไม่พอ/error.
    strict (≥2 token) → relax (≥1) → silence (<min_count). ห่อ try/except — ห้าม throw."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return []
        if len(tokens) >= 2:
            rows = query_similar(province, tokens, 2, conn=conn)
            if len(rows) < min_count:
                rows = query_similar(province, tokens, 1, conn=conn)   # widen
        else:
            rows = query_similar(province, tokens, 1, conn=conn)
        if len(rows) < min_count:
            return []
        s = compute_stats(rows)
        lines = [f"💡 ราคาอ้างอิง (งาน{tokens[0]}ใน{province})",
                 f"📊 จาก {s['count']} งานย้อนหลัง"]
        if s["discount_p25"] is not None:
            lines.append(f"📉 ส่วนลดที่พบบ่อย {s['discount_p25']:.0f}–{s['discount_p75']:.0f}%")
        if s["price_lo"] is not None:
            lines.append(f"💵 ช่วงราคาชนะ {s['price_lo']/1e6:.1f}–{s['price_hi']/1e6:.1f} ลบ.")
        if s["top_winners"]:
            lines.append("🏆 ผู้ชนะบ่อย:")
            for nm, cnt in s["top_winners"]:
                lines.append(f"  • {(nm or '?')[:32]} ({cnt})")
        return lines
    except Exception:
        return []
```

- [ ] **Step 4: Run → PASS** (`python scripts/test_cgd_intel.py` → ALL PASS) · **Step 5: Commit** `feat(intel): intel_lines orchestrate strict→relax→silence (Task 4)`

---

## Task 5: Wiring เข้า `format_notification` (D0 card)

**Files:** Modify `scripts/Sebastian_LINE_Sender.py` (`format_notification`, ก่อนบรรทัด `lines.append(f"\n🔑 {project_id}")` ≈ บรรทัด 256) · `scripts/test_cgd_intel.py`

- [ ] **Step 1: Write failing test** (เพิ่มใน test_cgd_intel.py — monkeypatch intel_lines)
```python
def test_wiring_format_notification():
    import Sebastian_LINE_Sender as ls
    import cgd_intel as _ci
    orig = _ci.intel_lines
    # (1) intel มีข้อมูล → แทรกใน card + divider
    _ci.intel_lines = lambda *a, **k: ["💡 TEST INTEL", "📊 จาก 99 งานย้อนหลัง"]
    txt = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                 source_stage="followed_bid_open")
    assert "💡 TEST INTEL" in txt and "🔑 P1" in txt and "━" in txt, txt
    # (2) intel throw → card ยังออก (value-add ห้ามพัง)
    _ci.intel_lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    txt2 = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="followed_bid_open")
    assert "🔑 P1" in txt2 and "💡" not in txt2, txt2
    # (3) source_stage อื่น → ไม่แตะ intel
    _ci.intel_lines = lambda *a, **k: ["💡 SHOULD NOT APPEAR"]
    txt3 = ls.format_notification("P2", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="api_enriched")
    assert "💡" not in txt3, txt3
    _ci.intel_lines = orig
    print("✅ wiring format_notification")
```
เพิ่มใน `__main__`: `test_wiring_format_notification()`

- [ ] **Step 2: Run → FAIL** (intel ไม่ถูกแทรก — assert "💡 TEST INTEL" fail)

- [ ] **Step 3: Implement** — แก้ `scripts/Sebastian_LINE_Sender.py`, แทรก block ก่อนบรรทัด `lines.append(f"\n🔑 {project_id}")`:
```python
    if source_stage == "followed_bid_open":
        try:
            import cgd_intel
            _il = cgd_intel.intel_lines(province, project_name)
            if _il:
                lines.append("━━━━━━━━━━━━━")
                lines.extend(_il)
        except Exception:
            pass   # intel = value-add — ห้ามทำ D0 notification พัง
```

- [ ] **Step 4: Run → PASS** · **Step 5: Commit** `feat(intel): wire competitive intel เข้า D0 card (Task 5)`

---

## Definition of Done
- [ ] `cgd_intel.py` 4 ฟังก์ชัน + `_pct` (test เขียวทั้งหมดใน `test_cgd_intel.py`)
- [ ] D0 card (`followed_bid_open`) แนบ intel เมื่อ match ≥10 งาน ; ไม่พอ/error → ไม่แนบ (card ปกติ)
- [ ] descriptive only (ไม่มีบรรทัดแนะนำราคาที่ควรยื่น)
- [ ] intel throw → notification ยังส่ง (graceful)

## Deploy (หลัง test เขียว)
`git push origin main` → VPS `cd /opt/bms/app && git pull --ff-only` (cgd_winners มีอยู่แล้วจาก Phase 2). ไม่มี migration. line-sender จะใช้ทันทีรอบ D0 ถัดไป.

## Manual verify บน VPS (optional)
```
sudo -u bms BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "import sys;sys.path.insert(0,'/opt/bms/app/scripts');import cgd_intel;print('\n'.join(cgd_intel.intel_lines('นครพนม','ก่อสร้างถนน คสล.')))"
```

## Rollback
ลบ block wiring ใน `format_notification` (intel แยกโมดูล — flow อื่นไม่กระทบ). `cgd_intel.py` ลบได้อิสระ.
