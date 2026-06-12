# Price Prediction Audit View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** หน้า internal (auth) ให้กัญจน์ดูทุกการทำนายราคาที่ส่งไป + กางดูวิธีคิด+ข้อมูลดิบแบบแช่แข็ง ณ ตอนทำนาย

**Architecture:** เก็บ `explain_json` snapshot ใน `price_predictions` ตอนทำนาย (capture ที่ `_build_intel`), เสิร์ฟผ่าน 2 endpoint ใน `bms_api` (FastAPI) ป้องกันด้วย shared secret. หน้าเว็บ server-rendered ด้วยฟังก์ชันสร้าง HTML string (ตาม pattern `_portal_page_html` เดิม)

**Tech Stack:** Python, SQLite (`bms_customers.db`), FastAPI + HTMLResponse, pytest

**อ้างอิง spec:** `docs/superpowers/specs/2026-06-12-price-prediction-audit-view-design.md`

---

## File Structure

| ไฟล์ | รับผิดชอบ | แก้/สร้าง |
|---|---|---|
| `scripts/Sebastian_Customer_DB.py` | schema + `save_prediction` เก็บ `explain_json` | Modify |
| `scripts/cgd_intel.py` | `_build_explain()` ประกอบ snapshot + ผนวกใน `_build_intel` return | Modify |
| `scripts/Sebastian_LINE_Sender.py:299` · `scripts/repredict_followed.py:78` | wire explain เข้า `save_prediction` (fail-open) | Modify |
| `scripts/bms_api.py` | auth helper + `/audit` + `/audit/{id}` + HTML builders | Modify |
| `scripts/tests/test_audit_view.py` | unit tests | Create |

---

### Task 1: DB — เพิ่ม `explain_json` + `save_prediction` เก็บได้

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py` (schema `price_predictions` + `save_prediction` cols + migration)
- Test: `scripts/tests/test_audit_view.py`

- [ ] **Step 1: Write failing test** (temp DB, save พร้อม explain_json แล้วอ่านกลับ)

```python
# scripts/tests/test_audit_view.py
import json, os, importlib, sqlite3, tempfile, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def _fresh_db(monkeypatch_env):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    os.environ["BMS_DB_PATH"] = path
    import Sebastian_Customer_DB as db; importlib.reload(db)
    db.init_schema()
    return db, path

def test_save_prediction_stores_explain_json():
    db, _ = _fresh_db(None)
    explain = {"schema_version": 1, "scope": {"level": "tambon", "n": 12}}
    db.save_prediction({"project_id": "P1", "budget": 2500000,
                        "area_price_lo": 1700000, "area_price_hi": 1950000,
                        "explain_json": json.dumps(explain, ensure_ascii=False)})
    row = db.get_prediction("P1")
    assert json.loads(row["explain_json"])["scope"]["n"] == 12
```

- [ ] **Step 2: Run → FAIL**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_save_prediction_stores_explain_json -v`
Expected: FAIL (`explain_json` ไม่อยู่ใน cols / column ไม่มี → sqlite OperationalError หรือ KeyError)

- [ ] **Step 3: เพิ่ม column ใน schema** — ใน `CREATE TABLE price_predictions (...)` เพิ่มบรรทัดก่อน `)`:

```python
                actual_price  INTEGER, in_range INTEGER, error_pct REAL, verified_at TEXT,
                explain_json  TEXT
```

- [ ] **Step 4: เพิ่ม migration idempotent** (เผื่อ DB เก่า) — เพิ่มฟังก์ชันและเรียกใน `init_schema()`:

```python
def _migrate_explain_json():
    with get_connection() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(price_predictions)")]
        if "explain_json" not in cols:
            conn.execute("ALTER TABLE price_predictions ADD COLUMN explain_json TEXT")
```
(เรียก `_migrate_explain_json()` ต่อท้าย `init_schema()` ตาม pattern `_migrate_v121`)

- [ ] **Step 5: ให้ `save_prediction` รับ `explain_json`** — เพิ่มใน tuple `cols`:

```python
    cols = ("project_id", "budget", "area_disc_lo", "area_disc_hi", "area_price_lo",
            "area_price_hi", "area_disc_med", "area_price_med", "top_name", "top_disc",
            "top_price", "explain_json")
```
(โครงสร้าง upsert เดิมรองรับ — `upd` คำนวณจาก cols อยู่แล้ว, `p.get(c)` คืน None ถ้าไม่ส่ง)

- [ ] **Step 6: Run → PASS**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_save_prediction_stores_explain_json -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/Sebastian_Customer_DB.py scripts/tests/test_audit_view.py
git commit -m "feat(audit): price_predictions.explain_json column + save support"
```

---

### Task 2: `_build_explain()` ประกอบ snapshot ใน cgd_intel

**Files:**
- Modify: `scripts/cgd_intel.py` (เพิ่ม `_build_explain`, ผนวกใน `_build_intel` return)
- Test: `scripts/tests/test_audit_view.py`

- [ ] **Step 1: Write failing test** (pure helper — ไม่พึ่ง DB)

```python
def test_build_explain_shape():
    import cgd_intel as ci
    ex = ci._build_explain(
        inputs={"budget": 2500000, "project_name": "ถนน X", "province": "นครพนม",
                "tambon": "ก", "amphoe": "ข", "location_confidence": "HIGH"},
        classify={"subtype": "concrete_road", "market": "local", "work_kind": "new"},
        scope_level="ตำบล", n=12,
        analysis={"disc_lo": 0.22, "disc_med": 0.27, "disc_hi": 0.31,
                  "top_name": "หจก. ก", "top_disc": 0.28},
        raw_records=[{"project_name": "ถนน Y", "winner": "หจก. ก",
                      "win_price": 1980000, "discount": 0.26}],
        output={"price_lo": 1725000, "price_med": 1825000, "price_hi": 1950000})
    assert ex["schema_version"] == 1
    assert ex["scope"]["level"] == "ตำบล" and ex["scope"]["n"] == 12
    assert ex["classify"]["subtype"] == "concrete_road"
    assert ex["raw_records"][0]["winner"] == "หจก. ก"
    assert ex["output"]["price_med"] == 1825000
```

- [ ] **Step 2: Run → FAIL**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_build_explain_shape -v`
Expected: FAIL (`AttributeError: module 'cgd_intel' has no attribute '_build_explain'`)

- [ ] **Step 3: เพิ่มฟังก์ชัน** ใน `scripts/cgd_intel.py` (ก่อน `_build_intel`):

```python
def _build_explain(inputs, classify, scope_level, n, analysis, raw_records, output):
    """ประกอบ snapshot เหตุผล+ข้อมูลดิบ แช่แข็ง ณ ตอนทำนาย (audit). pure — ไม่แตะ DB."""
    return {
        "schema_version": 1,
        "inputs": inputs,
        "classify": classify,
        "scope": {"level": scope_level, "n": n},
        "analysis": analysis,
        "raw_records": raw_records or [],
        "formula": "ราคาคาด = budget × (1 − ส่วนลด), clamp floor",
        "output": output,
    }
```

- [ ] **Step 4: Run → PASS**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_build_explain_shape -v`
Expected: PASS

- [ ] **Step 5: ผนวก explain ใน `_build_intel` return** — แก้บรรทัดสุดท้าย (cgd_intel.py:~529) จาก:

```python
    return {"lines": lines, "prediction": pred, "tambon": tambon, "amphoe": amphoe}
```
เป็น (ประกอบจาก locals ที่คำนวณแล้ว — basis=scope level, basis_sub/basis_dist, pp25/pp75/pmed, ptop/ptopm, cf, budget, pred):

```python
    try:
        explain = _build_explain(
            inputs={"budget": budget, "project_name": " ".join(tokens) if tokens else "",
                    "province": province, "tambon": tambon, "amphoe": amphoe,
                    "location_confidence": None},
            classify={"subtype": cf.get("subtype"), "market": cf.get("market"),
                      "work_kind": cf.get("work_kind"), "nature": cf.get("nature")},
            scope_level=basis, n=(tn if basis == "ตำบล" else None),
            analysis={"disc_lo": pp25, "disc_hi": pp75, "disc_med": pmed,
                      "top_name": ptop, "top_disc": ptopm},
            raw_records=[{"project_name": r.get("project_name"), "winner": r.get("winner"),
                          "win_price": r.get("win_price"), "discount": r.get("discount")}
                         for r in (t_rows if basis == "ตำบล" else
                                   a_rows if basis == "อำเภอ" else p_rows)][:30],
            output={"price_lo": pred.get("lo") if pred else None,
                    "price_med": pred.get("med") if pred else None,
                    "price_hi": pred.get("hi") if pred else None})
    except Exception as e:
        log(f"  ⚠️ build_explain failed: {e}"); explain = None
    return {"lines": lines, "prediction": pred, "tambon": tambon, "amphoe": amphoe,
            "explain": explain}
```

> หมายเหตุ: ชื่อ local (`basis`, `t_rows`/`a_rows`/`p_rows`, `tn`, `pp25/pp75/pmed`, `ptop/ptopm`, `cf`, `pred`) มาจากโค้ดเดิมใน `_build_intel`. ถ้า field ใน `pred`/`r` ชื่อต่าง ให้ปรับ key ให้ตรงตอน implement (ดู `predict_winning_price` return + `_fetch_scope` row keys) — **ห้ามเดา ตรวจจริงก่อน**

- [ ] **Step 6: Run full test file → PASS** (regression)

Run: `python -m pytest scripts/tests/test_audit_view.py -v`
Expected: PASS ทั้งหมด

- [ ] **Step 7: Commit**

```bash
git add scripts/cgd_intel.py scripts/tests/test_audit_view.py
git commit -m "feat(audit): _build_explain snapshot ใน _build_intel (fail-open)"
```

---

### Task 3: Wire explain เข้า save_prediction (write path)

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py:299`, `scripts/repredict_followed.py:78`

- [ ] **Step 1: แก้ LINE_Sender** (บรรทัด 299) จาก:

```python
                save_prediction({"project_id": project_id, **intel_ctx["prediction"]})
```
เป็น:

```python
                _pp = {"project_id": project_id, **intel_ctx["prediction"]}
                _ex = intel_ctx.get("explain")
                if _ex is not None:
                    import json as _json
                    _pp["explain_json"] = _json.dumps(_ex, ensure_ascii=False)
                save_prediction(_pp)
```

- [ ] **Step 2: แก้ repredict_followed.py** (บรรทัด 78) — ทำแบบเดียวกัน: ดึง `ctx.get("explain")` → ใส่ `explain_json` ก่อน `save_prediction`

```python
            _pp = {"project_id": pid, **new}
            if ctx.get("explain") is not None:
                import json as _json
                _pp["explain_json"] = _json.dumps(ctx["explain"], ensure_ascii=False)
            save_prediction(_pp)
```
(`new` = prediction dict, `ctx` = ผลจาก `intel_context`. ตรวจชื่อตัวแปรจริงในไฟล์ก่อนแก้)

- [ ] **Step 3: Verify ไม่พัง import** (smoke)

Run: `python -c "import sys; sys.path.insert(0,'scripts'); import Sebastian_LINE_Sender, repredict_followed; print('import OK')"`
Expected: `import OK` (ถ้า error ที่ไม่เกี่ยว เช่น missing env ให้ดูว่าเป็น import-time จริงไหม)

- [ ] **Step 4: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/repredict_followed.py
git commit -m "feat(audit): wire explain_json เข้า save_prediction (fail-open)"
```

---

### Task 4: bms_api — auth + `/audit` list endpoint

**Files:**
- Modify: `scripts/bms_api.py` (auth helper + endpoint + list HTML)
- Test: `scripts/tests/test_audit_view.py`

- [ ] **Step 1: Write failing test** (FastAPI TestClient — auth)

```python
def test_audit_requires_key(monkeypatch):
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    import importlib, bms_api; importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    c = TestClient(bms_api.app)
    assert c.get("/audit").status_code == 401
    assert c.get("/audit?key=wrong").status_code == 401
    assert c.get("/audit?key=secret123").status_code == 200
```

- [ ] **Step 2: Run → FAIL**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_audit_requires_key -v`
Expected: FAIL (404 — endpoint ไม่มี)

- [ ] **Step 3: เพิ่ม auth helper + endpoint** ใน `scripts/bms_api.py`:

```python
import os
def _check_audit_key(key: str):
    expected = os.getenv("BMS_AUDIT_KEY", "")
    if not expected or key != expected:
        raise HTTPException(status_code=401, detail="unauthorized")

@app.get("/audit")
async def audit_list(key: str = ""):
    _check_audit_key(key)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT project_id, budget, area_price_lo, area_price_hi, predicted_at, "
            "actual_price, in_range, error_pct FROM price_predictions "
            "ORDER BY predicted_at DESC LIMIT 200").fetchall()
    return HTMLResponse(_audit_list_html([dict(r) for r in rows], key))
```

- [ ] **Step 4: เพิ่ม `_audit_list_html`** (string builder ตาม pattern เดิม):

```python
def _audit_list_html(rows: list, key: str) -> str:
    trs = ""
    for r in rows:
        if r["actual_price"] is None:
            stat = "⏳ รอผล"
        else:
            stat = ("✅ ใน range" if r["in_range"] else "❌ หลุด") + f" ({r['error_pct']}%)"
        trs += (f"<tr><td><a href='/audit/{r['project_id']}?key={key}'>{r['project_id']}</a></td>"
                f"<td>{r['area_price_lo']:,}–{r['area_price_hi']:,}</td>"
                f"<td>{r['predicted_at']}</td><td>{stat}</td></tr>")
    return ("<html><head><meta charset='utf-8'><title>Audit ราคา</title></head><body>"
            "<h2>การทำนายราคา (ล่าสุด 200)</h2><table border=1 cellpadding=6>"
            "<tr><th>งาน</th><th>ช่วงราคา</th><th>ทำนายเมื่อ</th><th>ผลจริง</th></tr>"
            f"{trs}</table></body></html>")
```

- [ ] **Step 5: Run → PASS**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_audit_requires_key -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/bms_api.py scripts/tests/test_audit_view.py
git commit -m "feat(audit): /audit list endpoint + shared-secret auth"
```

---

### Task 5: `/audit/{id}` detail — analysis + raw_records + closed-loop

**Files:**
- Modify: `scripts/bms_api.py` (endpoint + detail HTML)
- Test: `scripts/tests/test_audit_view.py`

- [ ] **Step 1: Write failing test** (seed prediction + explain → detail แสดงเนื้อหา)

```python
def test_audit_detail_renders_explain(monkeypatch):
    os.environ["BMS_AUDIT_KEY"] = "secret123"
    db, _ = _fresh_db(None)
    explain = {"schema_version": 1,
               "classify": {"subtype": "concrete_road", "market": "local"},
               "scope": {"level": "ตำบล", "n": 12},
               "analysis": {"disc_med": 0.27},
               "raw_records": [{"project_name": "ถนน Y", "winner": "หจก. ก",
                                "win_price": 1980000, "discount": 0.26}],
               "output": {"price_med": 1825000}}
    db.save_prediction({"project_id": "P9", "budget": 2500000,
                        "area_price_lo": 1700000, "area_price_hi": 1950000,
                        "explain_json": json.dumps(explain, ensure_ascii=False)})
    import importlib, bms_api; importlib.reload(bms_api)
    from fastapi.testclient import TestClient
    c = TestClient(bms_api.app)
    html = c.get("/audit/P9?key=secret123").text
    assert "concrete_road" in html and "หจก. ก" in html and "1,980,000" in html
```

- [ ] **Step 2: Run → FAIL**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_audit_detail_renders_explain -v`
Expected: FAIL (404)

- [ ] **Step 3: เพิ่ม detail endpoint + HTML** ใน `scripts/bms_api.py`:

```python
@app.get("/audit/{project_id}")
async def audit_detail(project_id: str, key: str = ""):
    _check_audit_key(key)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT * FROM price_predictions WHERE project_id=?",
                         (project_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="not found")
    return HTMLResponse(_audit_detail_html(dict(r)))

def _audit_detail_html(r: dict) -> str:
    import json as _json
    ex = _json.loads(r["explain_json"]) if r.get("explain_json") else None
    if not ex:
        body = "<p>ไม่มีข้อมูล explain (การทำนายเก่าก่อนเปิดฟีเจอร์)</p>"
    else:
        cls, sc, an = ex.get("classify", {}), ex.get("scope", {}), ex.get("analysis", {})
        recs = "".join(
            f"<tr><td>{x.get('project_name','')}</td><td>{x.get('winner','')}</td>"
            f"<td>{(x.get('win_price') or 0):,}</td><td>{x.get('discount','')}</td></tr>"
            for x in ex.get("raw_records", []))
        body = (f"<h3>วิธีคิด</h3><ul>"
                f"<li>ประเภท: {cls.get('subtype')} · ระบอบตลาด: {cls.get('market')}</li>"
                f"<li>scope: {sc.get('level')} (n={sc.get('n')})</li>"
                f"<li>ส่วนลดกลาง: {an.get('disc_med')} · คู่แข่ง top: {an.get('top_name')}</li>"
                f"<li>{ex.get('formula','')}</li></ul>"
                f"<h3>ข้อมูลดิบอ้างอิง ({len(ex.get('raw_records', []))} งาน)</h3>"
                f"<table border=1 cellpadding=6><tr><th>งาน</th><th>ผู้ชนะ</th>"
                f"<th>ราคาชนะ</th><th>%ลด</th></tr>{recs}</table>")
    if r.get("actual_price") is not None:
        cl = (f"<h3>คาด vs จริง</h3><p>คาด {r.get('area_price_med') or '-'} · "
              f"จริง {r['actual_price']:,} · error {r.get('error_pct')}% · "
              f"{'✅ ใน range' if r.get('in_range') else '❌ หลุด'}</p>")
    else:
        cl = "<h3>คาด vs จริง</h3><p>⏳ รอผลประมูล</p>"
    return (f"<html><head><meta charset='utf-8'><title>{r['project_id']}</title></head>"
            f"<body><h2>งาน {r['project_id']} — ช่วงราคา {r.get('area_price_lo') or 0:,}–"
            f"{r.get('area_price_hi') or 0:,}</h2>{body}{cl}</body></html>")
```

- [ ] **Step 4: Run → PASS**

Run: `python -m pytest scripts/tests/test_audit_view.py::test_audit_detail_renders_explain -v`
Expected: PASS

- [ ] **Step 5: Run full file** — `python -m pytest scripts/tests/test_audit_view.py -v` → PASS ทั้งหมด

- [ ] **Step 6: Commit**

```bash
git add scripts/bms_api.py scripts/tests/test_audit_view.py
git commit -m "feat(audit): /audit/{id} detail — analysis + raw records + closed-loop"
```

---

### Task 6: Sanity (Sophia) + เอกสาร env

**Files:**
- Modify: `.env.example` หรือ docs (ระบุ `BMS_AUDIT_KEY`)

- [ ] **Step 1: เพิ่ม `BMS_AUDIT_KEY` ใน `.env.example`** (ถ้ามีไฟล์) + บันทึกใน CLAUDE.md Quick Reference

- [ ] **Step 2: dispatch Sophia** — prompt: "เพิ่ง wire explain_json เข้า price_predictions (pricing/queue). ตรวจว่า (a) ตัวเลข output ใน explain ตรงกับ area_price_* ที่ส่งลูกค้า (b) save_prediction ไม่ทำ prediction เพี้ยน (c) ไม่มี test/fake (R1). ใช้ product DB"
- [ ] **Step 3: ถ้า Sophia = STOP → แก้ก่อน. SAFE → ผ่าน**

- [ ] **Step 4: Commit (ถ้ามี doc change)**

```bash
git add .env.example CLAUDE.md
git commit -m "docs(audit): BMS_AUDIT_KEY env + Sophia sanity ผ่าน"
```

---

## Deploy note (หลัง merge — ไม่อยู่ใน plan นี้)
- VPS: `init_schema()` รัน migration `explain_json` (additive, idempotent) + ตั้ง env `BMS_AUDIT_KEY` + restart bms_api
- explain เริ่มเก็บเฉพาะการทำนาย**ใหม่** (เก่าไม่มี = แสดง "ไม่มีข้อมูล explain")

## Self-Review (เทียบ spec)
- §4 explain_json → Task 1 (column) + Task 2 (build). §5 capture → Task 2+3. §6 API+auth → Task 4+5.
  §7 หน้าเว็บ → Task 4+5 HTML builders. §8 closed-loop → Task 5 detail. §10 acceptance → ครอบใน tasks + Task 6 Sophia ✅
- ⚠️ ความเสี่ยงเดียว: ชื่อ local/field ใน `_build_intel` (`pred.lo/med/hi`, row keys `win_price/discount`) — Task 2 Step 5 สั่งให้ **ตรวจจริงก่อน ห้ามเดา** (ป้องกัน type mismatch)
