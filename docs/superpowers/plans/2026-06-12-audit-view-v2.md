# Audit View v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่มในหน้า /audit: ชื่องาน + stage + ราคา PRELIM(เบื้องต้น) + หมวด/ประเภท/ระบอบตลาด

**Architecture:** prelim เก็บใน 4 คอลัมน์ใหม่ (แยกจาก official), capture ที่ prelim notification path. Display: list join projects_seen(name)+followed_jobs(stage); detail เพิ่มบล็อกหมวดงาน(จาก explain.classify)+บล็อก PRELIM. Label maps เป็น pure helper.

**Tech Stack:** SQLite, FastAPI HTMLResponse, plain-script tests (`python scripts/test_audit_view.py`)

**อ้างอิง spec:** `docs/superpowers/specs/2026-06-12-audit-view-v2-design.md`

---

## File Structure

| ไฟล์ | รับผิดชอบ | แก้ |
|---|---|---|
| `scripts/Sebastian_Customer_DB.py` | migration v127 (prelim cols) + `update_prediction_prelim()` | Modify |
| `scripts/Sebastian_LINE_Sender.py` (~674) | capture prelim → save (fail-open) | Modify |
| `scripts/bms_api.py` | label helpers + list(name+stage) + detail(หมวดงาน+PRELIM block) | Modify |
| `scripts/test_audit_view.py` | tests | Modify |

---

### Task 1: prelim columns + update_prediction_prelim

**Files:** Modify `scripts/Sebastian_Customer_DB.py` · Test `scripts/test_audit_view.py`

- [ ] **Step 1: failing test** (append ก่อน `if __name__`)

```python
def test_prelim_does_not_touch_official():
    db = _fresh_db()
    db.save_prediction({"project_id": "PP", "budget": 2000000,
                        "area_price_lo": 1600000, "area_price_hi": 1800000})
    db.update_prediction_actual("PP", actual_price=1720000, in_range=1, error_pct=1.2)
    db.update_prediction_prelim("PP", prelim_price=1650000, in_range=0, error_pct=-8.3)
    r = db.get_prediction("PP")
    assert r["prelim_price"] == 1650000 and r["prelim_in_range"] == 0
    assert r["prelim_error_pct"] == -8.3 and r["prelim_at"]
    # official ต้องไม่ถูกแตะ
    assert r["actual_price"] == 1720000 and r["in_range"] == 1 and r["error_pct"] == 1.2
    print("✅ prelim แยกจาก official")
```
แล้วเพิ่มชื่อ test ใน `__main__` runner

- [ ] **Step 2: run → FAIL**

Run: `python scripts/test_audit_view.py`
Expected: FAIL (`update_prediction_prelim` ไม่มี / column ไม่มี)

- [ ] **Step 3: migration v127** — ใน `init_schema()` เพิ่ม `_migrate_v127()` ต่อจาก `_migrate_v126()`:

```python
    _migrate_v126()
    _migrate_v127()
```
และฟังก์ชัน (วางใกล้ `_migrate_v126`):

```python
def _migrate_v127():
    """price_predictions +prelim_* — เก็บราคาต่ำสุดเบื้องต้น (PRELIM, ยังไม่ทางการ) แยกจาก official
    actual. additive idempotent."""
    with get_connection() as conn:
        for col, typ in (("prelim_price", "INTEGER"), ("prelim_in_range", "INTEGER"),
                         ("prelim_error_pct", "REAL"), ("prelim_at", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE price_predictions ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass
```

- [ ] **Step 4: เพิ่ม `update_prediction_prelim`** (วางใกล้ `update_prediction_actual`):

```python
def update_prediction_prelim(project_id: str, prelim_price, in_range: int, error_pct) -> None:
    """เก็บราคา PRELIM (เบื้องต้น ยังไม่ทางการ) — เขียนเฉพาะ prelim_* ไม่แตะ official."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_predictions SET prelim_price=?, prelim_in_range=?, prelim_error_pct=?, "
            "prelim_at=? WHERE project_id=?",
            (prelim_price, in_range, error_pct, _now(), project_id))
```

- [ ] **Step 5: run → PASS** — `python scripts/test_audit_view.py` (test เดิม 6 ตัว + ใหม่ ผ่านหมด)

- [ ] **Step 6: commit**

```bash
git add scripts/Sebastian_Customer_DB.py scripts/test_audit_view.py
git commit -m "feat(audit-v2): prelim columns + update_prediction_prelim (แยกจาก official)"
```

---

### Task 2: capture prelim ที่ prelim notification path

**Files:** Modify `scripts/Sebastian_LINE_Sender.py` (~674)

- [ ] **Step 1: แก้ prelim path** — หลังบรรทัด `cmp = _ci.compare_prediction_provisional(...)`:

หาบรรทัด:
```python
        cmp = _ci.compare_prediction_provisional(pid, pr.get("lowest_price")) if pr.get("has_price") else None
```
เพิ่มต่อท้าย (ก่อนบรรทัด `pname = ...`):
```python
        if cmp is not None and pr.get("lowest_price"):
            try:
                from Sebastian_Customer_DB import update_prediction_prelim
                update_prediction_prelim(pid, round(float(pr["lowest_price"])),
                                         1 if cmp.get("held") else 0, cmp.get("error_pct"))
            except Exception:
                pass
```

- [ ] **Step 2: verify compile + import**

Run: `python -m py_compile scripts/Sebastian_LINE_Sender.py && echo OK`
Expected: `OK`

- [ ] **Step 3: commit**

```bash
git add scripts/Sebastian_LINE_Sender.py
git commit -m "feat(audit-v2): capture prelim price ตอน prelim notification (fail-open)"
```

---

### Task 3: label helpers (pure) ใน bms_api

**Files:** Modify `scripts/bms_api.py` · Test `scripts/test_audit_view.py`

- [ ] **Step 1: failing test**

```python
def test_label_helpers():
    import bms_api as a
    assert a._stage_label("PRELIM").startswith("🟡")
    assert a._stage_label("W0").endswith("ประกาศผู้ชนะ") or "ผู้ชนะ" in a._stage_label("W0")
    assert a._stage_label("ZZZ") == "—" or a._stage_label("ZZZ") == "ZZZ"
    assert a._most_advanced_stage(["D0", "W0", "PRELIM"]) == "W0"
    assert a._most_advanced_stage([]) == ""
    assert a._work_kind_label("new") == "สร้างใหม่"
    assert a._market_label("local") == "ท้องถิ่น (อปท.)"
    assert a._subtype_label("concrete_road") == "ถนนคอนกรีต"
    assert a._subtype_label(None) == "—"
    print("✅ label helpers")
```
เพิ่มใน `__main__` runner. (ต้อง reload bms_api ใน test นี้: `import bms_api,importlib; importlib.reload(bms_api)` — แต่ helper เป็น module-level ไม่พึ่ง DB จึง import ตรงได้)

- [ ] **Step 2: run → FAIL** (`_stage_label` ไม่มี)

- [ ] **Step 3: เพิ่ม helpers** ใน `scripts/bms_api.py` (ก่อน `_audit_list_html`):

```python
_STAGE = {"B0": "🟣 รับฟังคำวิจารณ์", "D0": "🔵 ประกาศ/ยื่นซอง",
          "PRELIM": "🟡 ราคาเบื้องต้น", "W0": "🟢 ประกาศผู้ชนะ"}
_STAGE_RANK = {"B0": 1, "D0": 2, "PRELIM": 3, "W0": 4}
_WORK_KIND = {"new": "สร้างใหม่", "reno": "ปรับปรุง/ซ่อม"}
_MARKET = {"local": "ท้องถิ่น (อปท.)", "provincial": "อบจ.", "central": "ส่วนกลาง (กรม)"}
_SUBTYPE = {"concrete_road": "ถนนคอนกรีต", "asphalt_road": "ถนนแอสฟัลต์",
            "water_dredge": "ขุดลอก", "water_structure": "ฝาย/โครงสร้างน้ำ"}

def _stage_label(s): return _STAGE.get(s or "", s or "—")
def _work_kind_label(s): return _WORK_KIND.get(s or "", "—")
def _market_label(s): return _MARKET.get(s or "", "—")
def _subtype_label(s): return _SUBTYPE.get(s or "", "—")

def _most_advanced_stage(stages: list) -> str:
    best, best_rank = "", 0
    for s in stages:
        r = _STAGE_RANK.get(s or "", 0)
        if r > best_rank:
            best, best_rank = s, r
    return best
```

- [ ] **Step 4: run → PASS**

- [ ] **Step 5: commit**

```bash
git add scripts/bms_api.py scripts/test_audit_view.py
git commit -m "feat(audit-v2): label helpers (stage/work_kind/market/subtype → ไทย)"
```

---

### Task 4: List — ชื่องาน + stage

**Files:** Modify `scripts/bms_api.py` (`audit_list` + `_audit_list_html`) · Test `scripts/test_audit_view.py`

- [ ] **Step 1: failing test** (seed prediction + projects_seen + followed_jobs)

```python
def test_audit_list_shows_name_and_stage():
    db = _fresh_db()
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    db.save_prediction({"project_id": "PL", "budget": 2000000,
                        "area_price_lo": 1600000, "area_price_hi": 1800000})
    with db.get_connection() as conn:
        conn.execute("INSERT INTO projects_seen(project_id,project_name,first_seen_at) VALUES(?,?,?)",
                     ("PL", "ก่อสร้างถนนทดสอบ", "2026-06-12"))
        conn.execute("INSERT INTO followed_jobs(customer_id,project_id,starred_at,last_stage_notified,status)"
                     " VALUES(1,'PL','2026-06-12','PRELIM','active')")
        conn.execute("INSERT INTO followed_jobs(customer_id,project_id,starred_at,last_stage_notified,status)"
                     " VALUES(2,'PL','2026-06-12','D0','active')")
    import bms_api, importlib; importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    html = TestClient(bms_api.app).get("/audit?key=secret123").text
    assert "ก่อสร้างถนนทดสอบ" in html, "ต้องมีชื่องาน"
    assert "ราคาเบื้องต้น" in html, "stage ต้องเป็น PRELIM (ก้าวหน้าสุดจาก 2 customer)"
    print("✅ list แสดงชื่องาน + stage")
```
เพิ่มใน `__main__` runner

- [ ] **Step 2: run → FAIL** (ยังไม่มีชื่อ/stage ใน list)

- [ ] **Step 3: แก้ `audit_list`** — query เพิ่ม name + stage. แทน body เดิมของ `audit_list`:

```python
@app.get("/audit")
async def audit_list(key: str = ""):
    _check_audit_key(key)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        preds = conn.execute(
            "SELECT pp.project_id, pp.area_price_lo, pp.area_price_hi, pp.predicted_at, "
            "pp.actual_price, pp.in_range, pp.error_pct, ps.project_name "
            "FROM price_predictions pp LEFT JOIN projects_seen ps ON ps.project_id=pp.project_id "
            "ORDER BY pp.predicted_at DESC LIMIT 200").fetchall()
        rows = [dict(r) for r in preds]
        for r in rows:
            stages = [x[0] for x in conn.execute(
                "SELECT last_stage_notified FROM followed_jobs WHERE project_id=?",
                (r["project_id"],)).fetchall()]
            r["stage"] = _most_advanced_stage([s for s in stages if s])
    return HTMLResponse(_audit_list_html(rows, key))
```

- [ ] **Step 4: แก้ `_audit_list_html`** — เพิ่มคอลัมน์ชื่องาน + stage:

```python
def _audit_list_html(rows: list, key: str) -> str:
    trs = ""
    for r in rows:
        lo, hi = r.get("area_price_lo") or 0, r.get("area_price_hi") or 0
        if r.get("actual_price") is None:
            stat = "⏳ รอผล"
        else:
            stat = ("✅ ในกรอบ" if r.get("in_range") else "❌ หลุด") + f" ({r.get('error_pct')}%)"
        name = r.get("project_name") or "(ไม่มีชื่อ)"
        trs += (f"<tr><td><a href='/audit/{r['project_id']}?key={key}'>{name}</a>"
                f"<br><small>{r['project_id']}</small></td>"
                f"<td>{_stage_label(r.get('stage'))}</td>"
                f"<td>{lo:,}–{hi:,}</td><td>{stat}</td></tr>")
    return ("<html><head><meta charset='utf-8'><title>Audit ราคา</title>"
            "<style>body{font-family:sans-serif;padding:16px}table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:6px}small{color:#888}</style></head><body>"
            "<h2>การทำนายราคา (ล่าสุด 200)</h2><table>"
            "<tr><th>งาน</th><th>สถานะ</th><th>ช่วงราคาคาด</th><th>ผลจริง(ทางการ)</th></tr>"
            f"{trs}</table></body></html>")
```

- [ ] **Step 5: run → PASS**

- [ ] **Step 6: commit**

```bash
git add scripts/bms_api.py scripts/test_audit_view.py
git commit -m "feat(audit-v2): list แสดงชื่องาน + stage (join projects_seen/followed_jobs)"
```

---

### Task 5: Detail — บล็อกหมวดงาน + บล็อก PRELIM

**Files:** Modify `scripts/bms_api.py` (`_audit_detail_html`) · Test `scripts/test_audit_view.py`

- [ ] **Step 1: failing test**

```python
def test_audit_detail_category_and_prelim():
    db = _fresh_db()
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    explain = {"schema_version": 1,
               "inputs": {"work_type": "ถนน"},
               "classify": {"subtype": "concrete_road", "market": "local", "work_kind": "new"},
               "scope": {"level": "ตำบล", "n": 4}, "analysis": {"disc_med": 0.27},
               "raw_records": [], "output": {"price_med": 1700000}}
    db.save_prediction({"project_id": "PD", "budget": 2000000,
                        "area_price_lo": 1600000, "area_price_hi": 1800000,
                        "area_price_med": 1700000,
                        "explain_json": json.dumps(explain, ensure_ascii=False)})
    db.update_prediction_prelim("PD", prelim_price=1650000, in_range=1, error_pct=-2.9)
    import bms_api, importlib; importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    html = TestClient(bms_api.app).get("/audit/PD?key=secret123").text
    assert "ถนนคอนกรีต" in html and "สร้างใหม่" in html and "ท้องถิ่น (อปท.)" in html, "บล็อกหมวดงาน"
    assert "ราคาเบื้องต้น (ยังไม่ทางการ)" in html and "1,650,000" in html, "บล็อก PRELIM"
    print("✅ detail หมวดงาน + PRELIM")
```
เพิ่มใน `__main__` runner

- [ ] **Step 2: run → FAIL**

- [ ] **Step 3: แก้ `_audit_detail_html`** — เพิ่มบล็อกหมวดงาน (จาก classify) + บล็อก PRELIM ก่อนบล็อก official. แทนทั้งฟังก์ชันด้วย:

```python
def _audit_detail_html(r: dict) -> str:
    ex = json.loads(r["explain_json"]) if r.get("explain_json") else None
    cat = ""
    if ex:
        cls, inp = ex.get("classify", {}), ex.get("inputs", {})
        cat = (f"<h3>หมวดงาน</h3><ul>"
               f"<li>หมวดงาน: {inp.get('work_type') or '—'}</li>"
               f"<li>หมวดย่อย: {_subtype_label(cls.get('subtype'))}</li>"
               f"<li>ประเภท: {_work_kind_label(cls.get('work_kind'))}</li>"
               f"<li>ระบอบตลาด: {_market_label(cls.get('market'))}</li></ul>")
    if not ex:
        body = "<p>ไม่มีข้อมูล explain (การทำนายเก่าก่อนเปิดฟีเจอร์)</p>"
    else:
        sc, an = ex.get("scope", {}), ex.get("analysis", {})
        recs = "".join(
            f"<tr><td>{x.get('project_name','')}</td><td>{x.get('winner','')}</td>"
            f"<td>{(x.get('win_price') or 0):,}</td><td>{x.get('discount','')}</td></tr>"
            for x in ex.get("raw_records", []))
        body = (f"<h3>วิธีคิด</h3><ul>"
                f"<li>scope: {sc.get('level')} (n={sc.get('n')})</li>"
                f"<li>ส่วนลดกลาง: {an.get('disc_med')} · คู่แข่ง top: {an.get('top_name')}</li>"
                f"<li>{ex.get('formula','')}</li></ul>"
                f"<h3>ข้อมูลดิบอ้างอิง ({len(ex.get('raw_records', []))} งาน)</h3>"
                f"<table><tr><th>งาน</th><th>ผู้ชนะ</th><th>ราคาชนะ</th><th>%ลด</th></tr>"
                f"{recs}</table>")
    # บล็อก PRELIM (เบื้องต้น) — แสดงเฉพาะถ้ามี
    if r.get("prelim_price") is not None:
        pl = (f"<h3>🟡 ราคาเบื้องต้น (ยังไม่ทางการ)</h3>"
              f"<p>เบื้องต้น {r['prelim_price']:,} · คาด {r.get('area_price_med') or '-'} · "
              f"ต่าง {r.get('prelim_error_pct')}% · "
              f"{'✅ ในกรอบ' if r.get('prelim_in_range') else '❌ หลุด'} "
              f"<i>(ยังไม่ทางการ)</i></p>")
    else:
        pl = ""
    # บล็อก official (W0)
    if r.get("actual_price") is not None:
        cl = (f"<h3>🟢 คาด vs จริง (ทางการ W0)</h3><p>คาด {r.get('area_price_med') or '-'} · "
              f"จริง {r['actual_price']:,} · error {r.get('error_pct')}% · "
              f"{'✅ ในกรอบ' if r.get('in_range') else '❌ หลุด'}</p>")
    else:
        cl = "<h3>🟢 คาด vs จริง (ทางการ W0)</h3><p>⏳ รอผลประมูล</p>"
    lo, hi = r.get("area_price_lo") or 0, r.get("area_price_hi") or 0
    name = r.get("project_name") or r["project_id"]
    return ("<html><head><meta charset='utf-8'>"
            f"<title>{r['project_id']}</title>"
            "<style>body{font-family:sans-serif;padding:16px}table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:6px}</style></head><body>"
            f"<p><a href='/audit?key={r.get('_key','')}'>← กลับ</a></p>"
            f"<h2>{name}</h2><p><small>{r['project_id']}</small> — ช่วงราคา {lo:,}–{hi:,}</p>"
            f"{cat}{body}{pl}{cl}</body></html>")
```

- [ ] **Step 4: แก้ `audit_detail`** — join projects_seen เพื่อได้ project_name. แทน query:

```python
        row = conn.execute(
            "SELECT pp.*, ps.project_name FROM price_predictions pp "
            "LEFT JOIN projects_seen ps ON ps.project_id=pp.project_id "
            "WHERE pp.project_id=?", (project_id,)).fetchone()
```

- [ ] **Step 5: run → PASS** (`python scripts/test_audit_view.py` ทุกตัว)

- [ ] **Step 6: commit**

```bash
git add scripts/bms_api.py scripts/test_audit_view.py
git commit -m "feat(audit-v2): detail บล็อกหมวดงาน + บล็อก PRELIM แยกจาก official"
```

---

### Task 6: full regression + deploy note

- [ ] **Step 1: รัน test ทั้งหมด** — `python scripts/test_audit_view.py` → ALL PASS · `python scripts/test_price_prediction.py` → ALL PASS
- [ ] **Step 2: dispatch Sophia** (หลัง deploy มีข้อมูลจริง) — ตรวจ prelim_* ไม่ทำให้ official/explain เพี้ยน + ราคาตรงที่ส่ง
- [ ] **Step 3:** ไม่มี commit เพิ่ม (ถ้า test ผ่านหมด)

---

## Deploy note (หลัง merge)
- VPS: `git pull` → `init_schema()` (migration v127) → restart bms-api
- prelim เริ่มเก็บงานใหม่ที่ถึง PRELIM หลัง deploy · stage/name แสดงทันที (อ่านจาก table เดิม)

## Self-Review (เทียบ spec)
- §3 prelim cols → Task1 · §4 capture → Task2 · §5 list name+stage → Task3(helper)+Task4 · §6 detail หมวดงาน+PRELIM → Task3+Task5 · §7 labels → Task3 · §9 acceptance → ครอบใน tasks
- invariant (prelim ไม่แตะ official) → Task1 test · label None ไม่ crash → Task3 test
- ⚠️ ตรวจจริงตอน implement: `cmp` keys (`held`/`error_pct`) จาก `_compare_core`, projects_seen NOT NULL cols (first_seen_at?) ตอน seed test
