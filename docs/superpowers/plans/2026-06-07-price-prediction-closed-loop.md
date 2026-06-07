# Price Prediction + Closed-Loop Verify — Implementation Plan (SP1)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) หรือ subagent-driven-development. Steps ใช้ `- [ ]`.

**Goal:** Sebastian คาดช่วงราคาที่จะชนะตอน D0 (เก็บไว้) → เทียบราคาจริงตอน W0 → แจ้งผล (การ์ด + Discord real-time) + สะสม accuracy เพื่อสร้าง credibility

**Architecture:** เก็บ raw prediction ใน `price_predictions` (v122). predict จาก competitor stats ที่ intel มีอยู่ (reuse ผ่าน `intel_context`). closed-loop เสียบที่ `Sebastian_Winner_Poller` (มี winning_price อยู่แล้ว). การ์ด W0 อ่าน prediction มาโชว์เทียบ. ทุกอย่าง descriptive ("คาดการณ์") + graceful (พังไม่ทำ notification ล่ม).

**Tech Stack:** Python 3, sqlite3, reuse cgd_intel / Winner_Poller / Discord_Notify

**Spec:** `docs/superpowers/specs/2026-06-07-price-prediction-closed-loop-design.md`

**Checkpoints:** A=Prediction@D0 (T1-4) · B=Closed-loop@W0 (T5-7) · C=Production (T8) — หยุด review ทุก checkpoint

---

## File Structure
- `scripts/Sebastian_Customer_DB.py` — `_migrate_v122` (price_predictions) + helpers `save_prediction`/`get_prediction`/`update_prediction_actual`/`prediction_accuracy_summary`
- `scripts/cgd_intel.py` — refactor `intel_context()` (เผย stats) · `predict_winning_price()` · `predict_lines()`
- `scripts/Sebastian_LINE_Sender.py` — D0: append predict_lines + store (format_notification) · W0: บรรทัดเทียบใน `_winner_card_from_results`
- `scripts/Sebastian_Winner_Poller.py` — closed-loop: เทียบ winning_price vs prediction + update + Discord real-time
- tests: `test_cgd_intel.py`, `test_price_prediction.py` (new), `test_winner_poller.py`

---

## CHECKPOINT A — Prediction @ D0

### Task 1: migrate v122 — price_predictions + helpers

**Files:** `scripts/Sebastian_Customer_DB.py`, `scripts/test_price_prediction.py` (new)

- [ ] **Step 1: เขียน test** (`test_price_prediction.py`)
```python
import os, tempfile, sys; from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db; db.init_schema()


def test_prediction_crud():
    with db.get_connection() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(price_predictions)")]
    assert "project_id" in cols and "area_price_lo" in cols and "in_range" in cols, cols
    db.save_prediction({"project_id": "P1", "budget": 2000000, "area_disc_lo": 8, "area_disc_hi": 15,
                        "area_price_lo": 1700000, "area_price_hi": 1840000, "top_name": "หจก.A",
                        "top_disc": 11, "top_price": 1780000})
    db.save_prediction({"project_id": "P1", "budget": 999})   # idempotent — เก็บค่าแรก
    p = db.get_prediction("P1")
    assert p["budget"] == 2000000 and p["area_price_lo"] == 1700000, p
    db.update_prediction_actual("P1", actual_price=1750000, in_range=1, error_pct=3.0)
    p2 = db.get_prediction("P1")
    assert p2["actual_price"] == 1750000 and p2["in_range"] == 1, p2
    assert db.get_prediction("NOPE") is None
    print("✅ prediction CRUD + idempotent")


def test_accuracy_summary():
    for pid, inr, err in [("A", 1, 2.0), ("B", 1, 4.0), ("C", 0, 18.0)]:
        db.save_prediction({"project_id": pid, "budget": 1})
        db.update_prediction_actual(pid, actual_price=1, in_range=inr, error_pct=err)
    s = db.prediction_accuracy_summary()
    assert s["verified"] == 3 and s["in_range"] == 2, s
    assert s["in_range_pct"] == 66.7 and s["mean_error_pct"] == 8.0, s
    assert db.prediction_accuracy_summary_empty_ok() if False else True
    print("✅ accuracy summary")


if __name__ == "__main__":
    test_prediction_crud()
    test_accuracy_summary()
    print("ALL PASS price_prediction")
```
- [ ] **Step 2: รัน → FAIL** `python scripts/test_price_prediction.py` → no table / AttributeError save_prediction
- [ ] **Step 3: เพิ่ม `_migrate_v122` + เรียกใน init_schema** (หลัง `_migrate_v121()`)
```python
    _migrate_v121()
    _migrate_v122()
```
```python
def _migrate_v122():
    """price_predictions — เก็บคำทำนายราคาชนะตอน D0 → เทียบจริงตอน W0 (credibility engine).
    เก็บเฉพาะ raw + ผลเทียบ (in_range/error เป็นผลคำนวณตอน verify, เก็บเพื่อ aggregate). additive."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_predictions (
                project_id    TEXT PRIMARY KEY,
                budget        INTEGER,
                area_disc_lo  REAL, area_disc_hi REAL,
                area_price_lo INTEGER, area_price_hi INTEGER,
                top_name      TEXT, top_disc REAL, top_price INTEGER,
                predicted_at  TEXT,
                actual_price  INTEGER, in_range INTEGER, error_pct REAL, verified_at TEXT
            )""")
```
- [ ] **Step 4: เพิ่ม helpers** (ใกล้ save_project_location_raw)
```python
def save_prediction(p: dict) -> None:
    """เก็บคำทำนาย D0 (idempotent ตาม project_id — เก็บค่าแรกที่โชว์). p ต้องมี project_id."""
    cols = ("project_id", "budget", "area_disc_lo", "area_disc_hi", "area_price_lo",
            "area_price_hi", "top_name", "top_disc", "top_price")
    with get_connection() as conn:
        conn.execute(
            f"INSERT OR IGNORE INTO price_predictions ({','.join(cols)}, predicted_at) "
            f"VALUES ({','.join('?' for _ in cols)}, ?)",
            tuple(p.get(c) for c in cols) + (_now(),))


def get_prediction(project_id: str) -> dict | None:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT * FROM price_predictions WHERE project_id=?", (project_id,)).fetchone()
        return dict(r) if r else None


def update_prediction_actual(project_id: str, actual_price, in_range: int, error_pct: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_predictions SET actual_price=?, in_range=?, error_pct=?, verified_at=? "
            "WHERE project_id=?", (actual_price, in_range, error_pct, _now(), project_id))


def prediction_accuracy_summary() -> dict:
    """running credibility: in-range rate + mean error% จาก verified rows."""
    with get_connection() as conn:
        rows = conn.execute("SELECT in_range, error_pct FROM price_predictions "
                            "WHERE verified_at IS NOT NULL").fetchall()
    n = len(rows)
    inr = sum(1 for r in rows if r[0] == 1)
    errs = [r[1] for r in rows if r[1] is not None]
    return {
        "verified": n,
        "in_range": inr,
        "in_range_pct": round(inr * 100.0 / n, 1) if n else 0.0,
        "mean_error_pct": round(sum(errs) / len(errs), 1) if errs else 0.0,
    }
```
(ลบบรรทัด `prediction_accuracy_summary_empty_ok` ใน test — เป็น noise; ใช้ assert ปกติ)
- [ ] **Step 5: แก้ test step1** ลบบรรทัด `assert db.prediction_accuracy_summary_empty_ok()...` ออก, เพิ่ม `assert db.prediction_accuracy_summary()["verified"] >= 0` แทน
- [ ] **Step 6: รัน → PASS** `python scripts/test_price_prediction.py`
- [ ] **Step 7: Commit** `git add -A scripts/Sebastian_Customer_DB.py scripts/test_price_prediction.py && git commit -m "feat(db): v122 price_predictions + helpers (save/get/update/accuracy)"`

---

### Task 2: refactor cgd_intel — intel_context() (DRY enabler)

**Files:** `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: เขียน test** (เพิ่มใน test_cgd_intel.py) — intel_context เผย stats
```python
def test_intel_context():
    c = _fixture_conn()
    ctx = ci.intel_context("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", "", "", c)
    assert ctx is not None and ctx["lines"][0].startswith("💡 ราคาอ้างอิง"), ctx
    assert ctx["area_p25"] is not None and ctx["area_p75"] is not None, ctx
    assert ctx["top_name"] and ctx["top_median"] is not None, ctx
    # ไม่มี work-type → None
    assert ci.intel_context("นครพนม", "จัดซื้อรถยนต์", "", "", c) is None
    print("✅ intel_context")
```
- [ ] **Step 2: รัน → FAIL** `BMS_ENV=dev python scripts/test_cgd_intel.py` → AttributeError intel_context
- [ ] **Step 3: refactor** — แยก `intel_context()` ออกจาก `intel_lines()` ใน cgd_intel.py แทน intel_lines เดิมด้วย 2 ฟังก์ชัน:
```python
def intel_context(province: str, project_name: str, dept_name: str = "",
                  project_id: str = "", conn=None) -> dict | None:
    """resolve+select+stats ครั้งเดียว → คืน context (lines + stats สำหรับ price prediction reuse).
    None ถ้าไม่มี work-type/คู่แข่ง. ห่อ try/except — คืน None เมื่อ error."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return None
        own = conn is None
        if own:
            from Sebastian_Customer_DB import get_connection
            conn = get_connection()
        try:
            loc = resolve_location(project_id, project_name, dept_name, province, conn)
            rows, scope, _level = select_competitors(province, tokens, loc["tambon"], loc["amphoe"], conn)
            if not rows:
                return None
            counts = Counter(r["winner"] for r in rows if r.get("winner"))
            discs = [r["discount_pct"] for r in rows if r.get("discount_pct") is not None]
            area_p25, area_p75 = _pct(discs, 25), _pct(discs, 75)
            top3 = counts.most_common(SHOW_N)
            top_name = top3[0][0] if top3 else None
            top_stats = company_stats(top_name, tokens, conn) if top_name else {}
            # build competitor lines (เหมือน intel_lines เดิม)
            lines = [f"💡 ราคาอ้างอิง ({scope})", "🏆 คู่แข่งแถบนี้:"]
            for winner, _ in top3:
                cs = company_stats(winner, tokens, conn)
                nm = (winner or "?")[:28]
                if cs["p25"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}% "
                                 f"({cs['p25']:.0f}–{cs['p75']:.0f}%)")
                elif cs["median"] is not None:
                    lines.append(f"  • {nm} · {cs['games']} งาน · ลด {cs['median']:.0f}%")
                else:
                    lines.append(f"  • {nm} · {cs['games']} งาน")
            if area_p75:
                lines.append(f"📊 ภาพรวม: งานแบบนี้แถบนี้มักลด {area_p25:.0f}–{area_p75:.0f}% จากราคากลาง")
            else:
                lines.append(f"📊 ภาพรวม {len(rows)} งาน")
            lines.append(confidence_label(len(rows), area_p25, area_p75))
            return {"lines": lines, "scope": scope, "rows": rows,
                    "area_p25": area_p25, "area_p75": area_p75,
                    "top_name": top_name, "top_median": top_stats.get("median")}
        finally:
            if own:
                conn.close()
    except Exception:
        return None


def intel_lines(province: str, project_name: str, dept_name: str = "",
                project_id: str = "", conn=None) -> list:
    """บรรทัด 💡 competitor intel (back-compat wrapper). คืน [] ถ้าไม่มีข้อมูล."""
    ctx = intel_context(province, project_name, dept_name, project_id, conn)
    return ctx["lines"] if ctx else []
```
(ลบ body เดิมของ intel_lines ที่ทำ resolve+format ออก — ย้ายเข้า intel_context)
- [ ] **Step 4: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py` (test เดิม + test_intel_context ผ่านหมด — intel_lines wrapper คืนผลเดิม)
- [ ] **Step 5: Commit** `git add -A scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "refactor(intel): extract intel_context (เผย stats เพื่อ reuse price prediction)"`

---

### Task 3: predict_winning_price + predict_lines

**Files:** `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: เขียน test**
```python
def test_predict_winning_price():
    p = ci.predict_winning_price(2000000, 8.0, 15.0, "หจก.A", 11.0)
    assert p["area_price_lo"] == 1700000 and p["area_price_hi"] == 1840000, p   # 2M×(1-.15), ×(1-.08)
    assert p["top_price"] == 1780000, p
    assert ci.predict_winning_price(0, 8, 15, "x", 11) is None      # ไม่มี budget
    assert ci.predict_winning_price(2000000, None, None, None, None) is None  # ไม่มี stat
    print("✅ predict_winning_price")

def test_predict_lines():
    p = ci.predict_winning_price(2100000, 8.0, 15.0, "หจก.ศิรประภา", 11.0)
    lines = ci.predict_lines(p)
    assert any("คาดราคาที่จะชนะ" in l for l in lines), lines
    assert any("ลด 8–15%" in l for l in lines), lines           # % ก่อน
    assert any("ลบ." in l for l in lines), lines                # ราคา
    assert any("โปรดคำนวณต้นทุน" in l for l in lines), lines    # disclaimer
    print("✅ predict_lines")
```
- [ ] **Step 2: รัน → FAIL** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 3: เพิ่มใน cgd_intel.py**
```python
def predict_winning_price(budget, area_p25, area_p75, top_name=None, top_median=None) -> dict | None:
    """คาดช่วงราคาชนะ = ราคากลาง × (1 − ส่วนลด). ช่วงตลาด p25/p75 + เจ้าตัวเต็ง. None ถ้าข้อมูลไม่พอ."""
    if not budget or area_p25 is None or area_p75 is None:
        return None
    b = float(budget)
    return {
        "budget": b, "area_disc_lo": area_p25, "area_disc_hi": area_p75,
        "area_price_lo": round(b * (1 - area_p75 / 100)), "area_price_hi": round(b * (1 - area_p25 / 100)),
        "top_name": top_name, "top_disc": top_median,
        "top_price": round(b * (1 - top_median / 100)) if top_median is not None else None,
    }


def predict_lines(p: dict) -> list:
    """บรรทัด 💵 คาดราคา — โชว์ % (ที่มา) ก่อน → ราคา (ผล). framing คาดการณ์ ไม่ใช่คำสั่ง."""
    if not p:
        return []
    out = [f"💵 คาดราคาที่จะชนะ (ราคากลาง {p['budget']/1e6:.1f} ลบ.):",
           f"   • ตลาดแถบนี้ลด {p['area_disc_lo']:.0f}–{p['area_disc_hi']:.0f}% → "
           f"ชนะราว {p['area_price_lo']/1e6:.1f}–{p['area_price_hi']/1e6:.1f} ลบ."]
    if p.get("top_price") is not None:
        out.append(f"   • เจ้าตัวเต็ง ({(p['top_name'] or '?')[:20]}) มักลด ~{p['top_disc']:.0f}% → "
                   f"~{p['top_price']/1e6:.1f} ลบ.")
    out.append("   * ประเมินจากสถิติ โปรดคำนวณต้นทุนจริงประกอบ")
    return out
```
- [ ] **Step 4: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 5: Commit** `git add -A scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "feat(intel): predict_winning_price + predict_lines (โชว์ %→ราคา)"`

---

### Task 4: wire D0 — append predict_lines + store

**Files:** `scripts/Sebastian_LINE_Sender.py:257`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: เขียน test** (D0 path เก็บ prediction + การ์ดมีบรรทัดราคา) — เพิ่มใน test_cgd_intel.py
```python
def test_d0_predict_and_store():
    import Sebastian_Customer_DB as db
    c = _fixture_conn()
    # mock: ให้ format_notification ใช้ conn fixture ไม่ได้ → ทดสอบ helper ตรง
    ctx = ci.intel_context("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", "", "", c)
    pred = ci.predict_winning_price(2000000, ctx["area_p25"], ctx["area_p75"],
                                    ctx["top_name"], ctx["top_median"])
    assert pred and pred["area_price_lo"] > 0, pred
    assert ci.predict_lines(pred), "ควรมีบรรทัดราคา"
    print("✅ D0 predict integration (ctx→predict→lines)")
```
- [ ] **Step 2: รัน → PASS ทันที** (ทดสอบ integration ของ helper ที่มีแล้ว — ยืนยัน ctx→predict ทำงานคู่กัน) `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 3: แก้ wiring** `Sebastian_LINE_Sender.py` บล็อก followed_bid_open (บรรทัด ~257-265) — ใช้ intel_context + predict + store
```python
    if source_stage == "followed_bid_open":
        try:
            import cgd_intel
            ctx = cgd_intel.intel_context(province, project_name, dept_name, project_id)
            if ctx:
                lines.append("━━━━━━━━━━━━━")
                lines.extend(ctx["lines"])
                pred = cgd_intel.predict_winning_price(
                    budget, ctx["area_p25"], ctx["area_p75"], ctx["top_name"], ctx["top_median"])
                if pred:
                    lines.extend(cgd_intel.predict_lines(pred))
                    from Sebastian_Customer_DB import save_prediction
                    save_prediction({"project_id": project_id, **pred})   # idempotent
        except Exception:
            pass   # intel = value-add — ห้ามทำ D0 พัง
```
- [ ] **Step 4: รัน wiring test** (test_wiring_format_notification ใช้ mock intel_lines เดิม — ต้องปรับ mock เป็น intel_context) — แก้ test:
```python
    # (1) intel มีข้อมูล
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 TEST INTEL", "🏆 คู่แข่งแถบนี้:"],
                                          "area_p25": 8, "area_p75": 15, "top_name": "x", "top_median": 11}
    _ci.predict_winning_price = lambda *a, **k: None   # ปิด predict ใน test นี้
```
(แก้ทั้ง 3 เคสใน test_wiring ให้ stub `intel_context` แทน `intel_lines`; เคส throw → `intel_context` raise)
- [ ] **Step 5: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 6: Commit** `git add -A scripts/Sebastian_LINE_Sender.py scripts/test_cgd_intel.py && git commit -m "feat(intel): D0 การ์ดเพิ่มราคาคาด + เก็บ price_predictions (idempotent)"`

🛑 **CHECKPOINT A — หยุด review** (prediction@D0 เก็บ+โชว์ได้)

---

## CHECKPOINT B — Closed-loop @ W0

### Task 5: compare_prediction helper (verdict + update)

**Files:** `scripts/cgd_intel.py` (หรือ Customer_DB), `scripts/test_price_prediction.py`

- [ ] **Step 1: เขียน test**
```python
def test_compare_prediction():
    import cgd_intel as ci
    db.save_prediction({"project_id": "W1", "budget": 2000000, "area_disc_lo": 8, "area_disc_hi": 15,
                        "area_price_lo": 1700000, "area_price_hi": 1840000, "top_name": "A",
                        "top_disc": 11, "top_price": 1780000})
    v = ci.compare_prediction("W1", 1750000)   # ในช่วง 1.70-1.84
    assert v["in_range"] is True and v["error_pct"] <= 8, v   # mid=1.77M, err~1%
    p = db.get_prediction("W1")
    assert p["actual_price"] == 1750000 and p["in_range"] == 1, p
    # นอกช่วง
    db.save_prediction({"project_id": "W2", "budget": 2000000, "area_price_lo": 1700000, "area_price_hi": 1840000})
    v2 = ci.compare_prediction("W2", 1500000)
    assert v2["in_range"] is False, v2
    # ไม่มี prediction → None
    assert ci.compare_prediction("NOPE", 1) is None
    print("✅ compare_prediction")
```
- [ ] **Step 2: รัน → FAIL** `python scripts/test_price_prediction.py`
- [ ] **Step 3: เพิ่ม `compare_prediction` ใน cgd_intel.py**
```python
def compare_prediction(project_id: str, actual_price, conn=None) -> dict | None:
    """เทียบราคาจริง vs คำทำนาย → in_range + error% → update DB. None ถ้าไม่มี prediction/actual."""
    from Sebastian_Customer_DB import get_prediction, update_prediction_actual
    try:
        actual = float(actual_price)
    except (TypeError, ValueError):
        return None
    if not actual:
        return None
    p = get_prediction(project_id)
    if not p or p.get("area_price_lo") is None:
        return None
    lo, hi = p["area_price_lo"], p["area_price_hi"]
    in_range = lo <= actual <= hi
    mid = (lo + hi) / 2
    error_pct = round(abs(actual - mid) / actual * 100, 1)
    update_prediction_actual(project_id, round(actual), 1 if in_range else 0, error_pct)
    return {"in_range": in_range, "error_pct": error_pct,
            "area_price_lo": lo, "area_price_hi": hi, "actual": round(actual)}
```
- [ ] **Step 4: รัน → PASS** `python scripts/test_price_prediction.py`
- [ ] **Step 5: Commit** `git add -A scripts/cgd_intel.py scripts/test_price_prediction.py && git commit -m "feat(intel): compare_prediction (in-range + error% + update)"`

---

### Task 6: Winner_Poller closed-loop + Discord real-time

**Files:** `scripts/Sebastian_Winner_Poller.py`, `scripts/test_winner_poller.py`

- [ ] **Step 1: เขียน test** (poll_winners เรียก compare + ส่ง notify เมื่อมี prediction) — เพิ่มใน test_winner_poller.py
```python
def test_closed_loop_verify(monkeypatch=None):
    # fake store + resolve_result มี winning_price → poll_winners ต้องเรียก verify_hook
    calls = []
    def fake_verify(pid, price): calls.append((pid, price)); return {"in_range": True, "error_pct": 3.0}
    import Sebastian_Winner_Poller as wp
    class S:
        def get_active_follows(self): return [{"project_id":"P1","customer_id":1,"last_stage_notified":"D0","starred_at":"2026-06-01T00:00:00"}]
        def record_bid_results(self,*a): pass
        def enqueue_for_customer(self,*a,**k): pass
        def mark_stage_notified(self,*a): pass
        def close_follow(self,*a): pass
    import os; os.environ["BMS_PROVINCE_NOTIFY_MODE"]="preview"   # shadow (ไม่ต้อง DB enqueue)
    res = {"winner":"A","winning_price":"1,750,000","bidders":[{"bidder_tin":"1","is_winner":1}]}
    stats = wp.poll_winners(S(), lambda pid: res, log=lambda m: None, verify_hook=fake_verify)
    assert calls == [("P1", "1,750,000")], calls
    print("✅ closed-loop verify hook called")
```
- [ ] **Step 2: รัน → FAIL** `python scripts/test_winner_poller.py` → poll_winners ไม่มี verify_hook
- [ ] **Step 3: แก้ poll_winners เพิ่ม verify_hook + real-time Discord** (inject ได้เพื่อ test)
```python
def poll_winners(store, resolve_result, now=None, log=print, max_days=MAX_DAYS,
                 sleep_sec=0, verify_hook=None):
    ...
    if res.get("bidders") and res.get("winner"):
        store.record_bid_results(pid, res["bidders"])
        # closed-loop: เทียบราคาคาด vs จริง (ก่อน enqueue เพื่อให้การ์ดอ่าน prediction ที่ update แล้ว)
        if verify_hook is not None:
            try:
                verify_hook(pid, res.get("winning_price"))
            except Exception as e:
                log(f"  verify {pid} error: {e}")
        meta = names.get(pid, {})
        ...
```
ใน `main()`: ประกอบ verify_hook ที่เรียก compare_prediction + ส่ง Discord real-time
```python
    def verify_hook(pid, winning_price):
        import cgd_intel
        from Sebastian_Customer_DB import prediction_accuracy_summary
        v = cgd_intel.compare_prediction(pid, _parse_money(winning_price))
        if not v:
            return
        s = prediction_accuracy_summary()
        verdict = "✅ ตรง" if v["in_range"] else "❌ ไม่ตรง"
        msg = (f"🎯 ผลทำนาย {pid}\n"
               f"   คาด {v['area_price_lo']/1e6:.1f}–{v['area_price_hi']/1e6:.1f} / "
               f"จริง {v['actual']/1e6:.2f} ลบ. → {verdict} (คลาด {v['error_pct']:.0f}%)\n"
               f"   📊 สะสม: ตรง {s['in_range']}/{s['verified']} ({s['in_range_pct']}%) · "
               f"คลาดเฉลี่ย {s['mean_error_pct']}%")
        try:
            import sys; sys.path.insert(0, str(Path(__file__).parent))
            from Sebastian_Discord_Notify import load_env, get_credentials, send
            load_env(); tok, ch = get_credentials(); send(tok, ch, msg)
        except Exception as e:
            log(f"  discord verify fail: {e}")
    stats = poll_winners(store, get_procure_result, log=log, sleep_sec=POLL_SLEEP_SEC, verify_hook=verify_hook)
```
เพิ่ม helper `_parse_money(s)` (แปลง "1,750,000" → 1750000.0; คืน None ถ้าไม่ได้)
```python
def _parse_money(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
```
- [ ] **Step 4: รัน → PASS** `python scripts/test_winner_poller.py`
- [ ] **Step 5: Commit** `git add -A scripts/Sebastian_Winner_Poller.py scripts/test_winner_poller.py && git commit -m "feat(poller): closed-loop verify + Discord real-time (running accuracy)"`

---

### Task 7: การ์ด W0 — บรรทัดเทียบคาด vs จริง

**Files:** `scripts/Sebastian_LINE_Sender.py` (`_winner_card_from_results`), `scripts/test_winner_card.py`

- [ ] **Step 1: เขียน test** — winner card มีบรรทัดเทียบเมื่อมี prediction verified
```python
def test_winner_card_prediction_line():
    import Sebastian_Customer_DB as db
    db.save_prediction({"project_id":"WC1","budget":2000000,"area_price_lo":1700000,"area_price_hi":1840000})
    db.update_prediction_actual("WC1", 1750000, 1, 3.0)
    import Sebastian_LINE_Sender as ls
    item = {"project_id":"WC1","project_name":"ถนน","province":"นครพนม"}
    results = [{"bidder_name":"A","price_agree":"1750000","is_winner":1}]
    alt, flex = ls._winner_card_from_results(item, results)
    body = flex["body"]["contents"][1]["text"]
    assert "Sebastian คาด" in body and ("ตรง" in body), body
    print("✅ winner card prediction line")
```
- [ ] **Step 2: รัน → FAIL** `BMS_ENV=dev python scripts/test_winner_card.py`
- [ ] **Step 3: แก้ `_winner_card_from_results`** — อ่าน get_prediction(pid) ถ้า verified → เพิ่มบรรทัด
```python
    # (ในฟังก์ชัน _winner_card_from_results หลังประกอบ body หลัก)
    try:
        from Sebastian_Customer_DB import get_prediction
        p = get_prediction(item["project_id"])
        if p and p.get("verified_at") and p.get("area_price_lo") is not None:
            verdict = "✅ ตรง" if p.get("in_range") else "❌ ไม่ตรง"
            body_lines.append(f"🎯 Sebastian คาด {p['area_price_lo']/1e6:.1f}–{p['area_price_hi']/1e6:.1f} ลบ. "
                              f"→ {verdict} (คลาด {p.get('error_pct') or 0:.0f}%)")
    except Exception:
        pass
```
(ปรับชื่อ `body_lines` ให้ตรงกับตัวแปรจริงใน `_winner_card_from_results` — ตรวจตอน execute)
- [ ] **Step 4: รัน → PASS** `BMS_ENV=dev python scripts/test_winner_card.py`
- [ ] **Step 5: Commit** `git add -A scripts/Sebastian_LINE_Sender.py scripts/test_winner_card.py && git commit -m "feat(card): การ์ดผู้ชนะเพิ่มบรรทัดเทียบคาด vs จริง"`

🛑 **CHECKPOINT B — หยุด review** (closed-loop เทียบ+แจ้ง+การ์ดครบ)

---

## CHECKPOINT C — Production

### Task 8: deploy + verify

- [ ] **Step 1:** push + verify ls-remote
- [ ] **Step 2:** VPS pull --ff-only + backup `pre_priceprediction_$(date +%Y%m%d_%H%M%S).db`
- [ ] **Step 3: verify D0 prediction** — รัน format_notification (source_stage=followed_bid_open) กับงาน followed จริง 1 งาน → ดูการ์ดมีบรรทัด 💵 + price_predictions มี row
```bash
ssh ... "sudo -u bms BMS_DATA_DIR=/opt/bms/data BMS_ENV=prod /opt/bms/venv/bin/python -X utf8 -c \"
import sys; sys.path.insert(0,'/opt/bms/app/scripts'); import sqlite3, Sebastian_LINE_Sender as ls
c=sqlite3.connect('/opt/bms/data/bms_customers.db'); c.row_factory=sqlite3.Row
r=c.execute(\\\"SELECT project_id,province,project_name,dept_name,budget FROM projects_seen WHERE project_id IN (SELECT project_id FROM followed_jobs) LIMIT 1\\\").fetchone()
print(ls.format_notification(r['project_id'], province=r['province'], project_name=r['project_name'], dept_name=r['dept_name'] or '', budget=r['budget'] or 0, source_stage='followed_bid_open'))
print('--- prediction stored? ---')
import Sebastian_Customer_DB as db; print(db.get_prediction(r['project_id']))
\""
```
Expected: การ์ดมี "💵 คาดราคาที่จะชนะ" + get_prediction คืน row (ถ้างานนั้น match work-type + มี budget + competitor พอ)
- [ ] **Step 4: verify accuracy summary** `sudo -u bms ... python -c "import Sebastian_Customer_DB as db; print(db.prediction_accuracy_summary())"` → `{verified:0,...}` (ยังไม่มีงาน awarded — ปกติ)
- [ ] **Step 5:** update progress_log + memory + Discord
- [ ] **Step 6: note** closed-loop จะให้ผลจริงเมื่องาน followed เดินถึงประกาศผล (W0) — รอ Winner_Poller รอบถัดไปเจอผล

🛑 **CHECKPOINT C — review** (production verify)

---

## Self-Review
- **Spec coverage:** predict (T3) · การ์ด D0 %→ราคา (T3 predict_lines + T4 wire) · price_predictions (T1) · compare/closed-loop (T5) · Winner_Poller + Discord real-time (T6) · การ์ด W0 เทียบ (T7) · accuracy summary (T1) · reuse intel via intel_context (T2) · deploy (T8). SP2 calibrate = ไม่อยู่ใน plan นี้ ✅
- **Persist raw + ผลเทียบ:** price_predictions เก็บ prediction (raw) + actual/in_range/error (ผล verify, จำเป็นต่อ aggregate) — สอดคล้อง spec
- **Placeholder scan:** ไม่มี (โค้ดจริงทุก step; test step1 ของ T1 มีบรรทัด noise → ลบใน step5)
- **Type consistency:** save_prediction รับ dict (project_id+pred fields) · predict_winning_price คืน dict เดียวกับที่ save รับ (spread `**pred`) · compare_prediction อ่าน area_price_lo/hi · intel_context คืน area_p25/area_p75/top_name/top_median ใช้ตรงใน predict · _parse_money ใช้ใน verify_hook
- **⚠️ verify ตอน execute:** (a) ตัวแปร body ใน `_winner_card_from_results` ชื่อจริงอะไร (T7) (b) get_procure_result winning_price เป็น str มี comma → _parse_money รองรับ (c) test_wiring เดิม stub intel_lines → เปลี่ยนเป็น intel_context (T4 step4)
