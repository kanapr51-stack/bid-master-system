# Auto-Competitor Win-Rate (Board B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เครื่องคำนวณโอกาสชนะบนหน้า `/portal/job/[pid]` ทำนายรายชื่อคู่แข่งที่น่าจะมายื่นให้อัตโนมัติ (p_attend ต่อบริษัท) แล้วถ่วงเข้าโมเดล Gates เดิม — ผู้ใช้ใส่แค่ราคา ยังติ๊กออก/เพิ่มชื่อได้

**Architecture:** ฟังก์ชันใหม่ `attendance_probs()` ใน `bid_field.py` นับความถี่การโผล่ (recency-weighted) จาก `_field_auctions` ladder เดิม (🟢 local → 🟡 อำเภอ → 🟠 จังหวัด). `calc_custom_winrate` รับ `attend_probs` ถ่วงเป็น `P_eff = 1 − p_attend×(1−P_beat)` ก่อนเข้า `gates_winrate` เดิม. `_build_intel` แนบผลทำนายใน key `predicted_attendees`. `portal_views` render กลุ่ม pre-ticked + breakdown "โอกาสมา X%".

**Tech Stack:** Python (engine, no framework), SQLite, script-style tests (`python scripts/test_*.py` — assert + print, ไม่ใช่ pytest)

**Spec:** `docs/superpowers/specs/2026-07-11-auto-competitor-winrate-design.md`

## Global Constraints

- **Invariant:** `attend_probs` ที่ทุกค่า = 1.0 (หรือไม่ส่ง) → ผลลัพธ์เท่าโมเดลเดิมทุกหลัก
- **แตะแค่ 3 ไฟล์ engine:** `scripts/bid_field.py`, `scripts/cgd_intel.py`, `scripts/portal_views.py` — **ห้ามแตะ** `bms_api.py`, `dashboard/web`
- ทุกทางใหม่ต้อง graceful/fail-open: attendance พัง → ฟอร์มแบบเดิม ห้ามทำการ์ดพัง
- threshold แสดงผล `p_attend ≥ 0.15`, cap 10 บริษัท, clamp [0.05, 0.95]
- ฟอร์ม no-JS เดิม (POST `/portal/job/calc` → redirect) — ไม่เพิ่ม URL param ใหม่
- UI copy ภาษาไทยตาม spec §4 (คัดลอก string ตามแผนนี้เป๊ะ)
- test isolation: `os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()` **ก่อน** import Sebastian_Customer_DB (pattern เดียวกับ `test_cgd_intel.py:3`)
- commit เล็กต่อ task, ห้าม `--no-verify`, ห้าม push (รอกัญจน์ confirm)

---

### Task 1: `attendance_probs()` ใน bid_field.py

**Files:**
- Modify: `scripts/bid_field.py` (ต่อท้ายไฟล์, หลัง `p_beat` บรรทัด ~429)
- Create: `scripts/test_attendance.py`

**Interfaces:**
- Consumes: `_field_auctions`, `_scope_ids`, `_CONF`, `MIN_AUCTIONS`, `recency_weight` (มีอยู่แล้วใน bid_field.py), `portal_views._norm_name`
- Produces: `attendance_probs(conn, province, tokens, project_ids=None, cf=None, amphoe=None, threshold=0.15, cap=10) -> dict | None`
  - คืน `{"probs": {display_name: float}, "conf": None | ("🟡","อำเภอ") | ("🟠","จังหวัด"), "n_auctions": int}` หรือ `None`

- [ ] **Step 1: เขียน failing tests**

สร้าง `scripts/test_attendance.py`:

```python
"""test_attendance.py — attendance_probs (N+196 auto-competitor): โอกาสบริษัทมายื่นต่อสนาม
recency-weighted appearance share + ladder 🟢→🟡→🟠 + threshold/cap/clamp."""
import os, sys, tempfile; from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()   # isolate จาก prod ก่อน import DB
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("BMS_FOLLOW_SECRET", "test-secret-attendance")
import bid_field as bf

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _db():
    import Sebastian_Customer_DB as db
    db.init_schema()
    return db


def _seed_field(db, province, prefix, name_tmpl, n_auctions, bidders_fn, fy="2569", budget=1000000):
    """seed cgd_winners + bid_results: auction ละ 1 แถว winner + bidders จาก bidders_fn(i)."""
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id,province,proc_type,project_name,budget,fiscal_year,winner,win_price,"
            "discount_pct,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(f"{prefix}{i}", province, EB, name_tmpl.format(i), budget,
              fy if not callable(fy) else fy(i), "หจก.ประจำ", 850000, 15.0, "นาทม", "นาทม")
             for i in range(n_auctions)])
    for i in range(n_auctions):
        s.record_bid_results(f"{prefix}{i}", bidders_fn(i))


NAME_NATHOM = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย{0} องค์การบริหารส่วนตำบลนาทม อำเภอนาทม จังหวัดนครพนม"


def _seed_basic(db):
    """8 auctions ปีปัจจุบัน: หจก.ประจำ 8/8, หจก.ครึ่งเดียว 4/8, หจก.ขาจรi 1/8"""
    def bidders(i):
        b = [{"receiveNameTh": "หจก.ประจำ", "receiveTin": "1", "priceProposal": "850000"},
             {"receiveNameTh": f"หจก.ขาจร{i}", "receiveTin": str(100 + i), "priceProposal": "900000"}]
        if i < 4:
            b.append({"receiveNameTh": "หจก.ครึ่งเดียว", "receiveTin": "2", "priceProposal": "880000"})
        return b
    _seed_field(db, "นครพนม", "A", NAME_NATHOM, 8, bidders)


def test_attendance_basic_threshold_clamp():
    db = _db(); _seed_basic(db)
    with db.get_connection() as conn:
        out = bf.attendance_probs(conn, "นครพนม", ["ถนน"])
    assert out is not None, out
    assert out["conf"] is None and out["n_auctions"] == 8, out
    assert out["probs"]["หจก.ประจำ"] == 0.95, out          # 8/8=1.0 → clamp 0.95
    assert out["probs"]["หจก.ครึ่งเดียว"] == 0.5, out       # 4/8
    assert all("ขาจร" not in k for k in out["probs"]), out  # 1/8=0.125 < 0.15 → ตัด
    print("✅ attendance basic + threshold + clamp")


def test_attendance_recency_weighting():
    """งานเก่า (2565, w=0.0625) แทบไม่นับ: หจก.เก่า โผล่ 3/8 ดิบ (0.375 ถ้าไม่ถ่วง)
    แต่ถ่วงแล้ว = 3×0.0625/(5+3×0.0625) ≈ 0.036 → ต้องไม่ติดลิสต์"""
    db = _db()
    NAME = "ก่อสร้างถนนลาดยาง สาย{0} ตำบลไชยบุรี อำเภอท่าอุเทน จังหวัดมุกดาหาร"
    def bidders(i):
        if i < 5:   # ปีปัจจุบัน
            return [{"receiveNameTh": "หจก.สด", "receiveTin": "1", "priceProposal": "850000"},
                    {"receiveNameTh": "หจก.สดสอง", "receiveTin": "2", "priceProposal": "900000"}]
        return [{"receiveNameTh": "หจก.เก่า", "receiveTin": "3", "priceProposal": "850000"},
                {"receiveNameTh": "หจก.เก่าสอง", "receiveTin": "4", "priceProposal": "900000"}]
    _seed_field(db, "มุกดาหาร", "R", NAME, 8, bidders, fy=lambda i: "2569" if i < 5 else "2565")
    with db.get_connection() as conn:
        out = bf.attendance_probs(conn, "มุกดาหาร", ["ถนน"])
    assert out is not None, out
    assert out["probs"]["หจก.สด"] == 0.95, out              # 5/5.1875=0.964 → clamp
    assert "หจก.เก่า" not in out["probs"], out               # recency ฆ่าข้อมูลเก่า
    print("✅ attendance recency weighting")


def test_attendance_gate_and_ladder():
    db = _db()
    # จังหวัดที่มีแค่ 3 auctions → ไม่พอ (MIN_AUCTIONS=5) → None
    NAME_BK = "ก่อสร้างถนนคอนกรีต สาย{0} ตำบลบึงโขงหลง อำเภอบึงโขงหลง จังหวัดบึงกาฬ"
    _seed_field(db, "บึงกาฬ", "T", NAME_BK, 3,
                lambda i: [{"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "850000"},
                           {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "900000"}])
    _seed_basic(db)   # นครพนม 8 auctions (อ.นาทม)
    with db.get_connection() as conn:
        assert bf.attendance_probs(conn, "บึงกาฬ", ["ถนน"]) is None
        # local (project_ids) แค่ 2 → ผ่อนไปอำเภอ (🟡) เจอ 8 งานของ อ.นาทม
        out = bf.attendance_probs(conn, "นครพนม", ["ถนน"], project_ids=["A0", "A1"],
                                  cf={}, amphoe="นาทม")
    assert out is not None and out["conf"] == ("🟡", "อำเภอ"), out
    assert out["probs"]["หจก.ประจำ"] == 0.95, out
    print("✅ attendance MIN_AUCTIONS gate + ladder อำเภอ")


def test_attendance_cap10():
    db = _db()
    NAME = "ก่อสร้างถนนคอนกรีต สาย{0} ตำบลธาตุเชิงชุม อำเภอเมืองสกลนคร จังหวัดสกลนคร"
    _seed_field(db, "สกลนคร", "C", NAME, 6,
                lambda i: [{"receiveNameTh": f"บริษัท แคป{j} จำกัด", "receiveTin": str(j),
                            "priceProposal": "880000"} for j in range(12)])
    with db.get_connection() as conn:
        out = bf.attendance_probs(conn, "สกลนคร", ["ถนน"])
    assert out is not None and len(out["probs"]) == 10, out   # 12 เจ้า p=0.95 หมด → cap 10
    print("✅ attendance cap 10")


def test_attendance_graceful_bad_conn():
    import sqlite3
    empty = sqlite3.connect(":memory:")   # ไม่มีตารางเลย → ต้อง None ไม่ throw
    assert bf.attendance_probs(empty, "นครพนม", ["ถนน"]) is None
    print("✅ attendance graceful (no tables)")


if __name__ == "__main__":
    test_attendance_basic_threshold_clamp()
    test_attendance_recency_weighting()
    test_attendance_gate_and_ladder()
    test_attendance_cap10()
    test_attendance_graceful_bad_conn()
    print("ALL PASS (attendance)")
```

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_attendance.py`
Expected: `AttributeError: module 'bid_field' has no attribute 'attendance_probs'`

- [ ] **Step 3: implement `attendance_probs`**

ต่อท้าย `scripts/bid_field.py` (หลัง `p_beat`):

```python
def attendance_probs(conn, province, tokens, project_ids=None, cf=None, amphoe=None,
                     threshold=0.15, cap=10):
    """โอกาสบริษัทมายื่นสนามนี้ (auto-competitor N+196). ladder เดิมแบบ field_and_winrate:
    price-scope (🟢) → อำเภอ (🟡) → จังหวัด (🟠) — ใช้ชั้นแรกที่ competitive auctions ≥ MIN_AUCTIONS.
    p = Σw(auctions ที่บริษัทโผล่)/Σw(ทั้งหมด), w = recency_weight(fy ของ auction), นับ 1 ครั้ง/บริษัท/auction.
    clamp [0.05,0.95] · แสดงเฉพาะ p ≥ threshold เรียงมาก→น้อย cap ราย. คืน
    {"probs": {ชื่อ: p}, "conf": None|('🟡','อำเภอ')|('🟠','จังหวัด'), "n_auctions": n} · None ถ้าทุกชั้นบาง/error."""
    import portal_views as _pv
    try:
        if project_ids is not None:
            attempts = [_field_auctions(conn, province, tokens, project_ids=project_ids)]
        else:
            attempts = [_field_auctions(conn, province, tokens)]
        if amphoe and cf is not None:
            attempts.append(_field_auctions(conn, province, tokens,
                            project_ids=_scope_ids(conn, province, tokens, cf, district=amphoe)))
            attempts.append(_field_auctions(conn, province, tokens,
                            project_ids=_scope_ids(conn, province, tokens, cf)))
        for i, auc in enumerate(attempts):
            auc = [a for a in auc if len(a) >= 2]        # สนามแข่งจริง (เกณฑ์เดียวกับ winrate)
            if len(auc) < MIN_AUCTIONS:
                continue
            total_w, appear_w, disp = 0.0, defaultdict(float), {}
            for a in auc:
                fy = next((b[3] for b in a if len(b) > 3 and b[3]), None)
                w = recency_weight(fy)
                total_w += w
                seen = set()
                for b in a:
                    core = _pv._norm_name(b[0])
                    if not core or core in seen:
                        continue
                    seen.add(core)
                    appear_w[core] += w
                    disp.setdefault(core, b[0])
            if total_w <= 0:
                continue
            ranked = []
            for core, aw in appear_w.items():
                p = max(0.05, min(0.95, aw / total_w))
                if p >= threshold:
                    ranked.append((disp[core], round(p, 2)))
            if not ranked:
                continue
            ranked.sort(key=lambda kv: -kv[1])
            return {"probs": dict(ranked[:cap]), "conf": _CONF.get(i), "n_auctions": len(auc)}
        return None
    except Exception:                                     # fail-open — ห้ามทำการ์ด/ฟอร์มพัง
        _log.warning("attendance_probs failed", exc_info=True)
        return None
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `python scripts/test_attendance.py`
Expected: `ALL PASS (attendance)` (5 ✅)

- [ ] **Step 5: regression เดิมของ bid_field**

Run: `python scripts/test_winrate_grid.py`
Expected: pass เหมือนเดิม (ไม่ได้แตะฟังก์ชันเดิม)

- [ ] **Step 6: Commit**

```bash
git add scripts/bid_field.py scripts/test_attendance.py
git commit -m "feat(pricing): attendance_probs — โอกาสคู่แข่งมายื่นต่อสนาม (N+196 auto-competitor)"
```

---

### Task 2: `calc_custom_winrate` รับ `attend_probs` (effective-P)

**Files:**
- Modify: `scripts/cgd_intel.py:867-911` (`calc_custom_winrate`)
- Test: `scripts/test_cgd_intel.py` (ต่อท้าย section calc + เพิ่มใน `__main__`)

**Interfaces:**
- Consumes: `bid_field.p_beat`, `bid_field.gates_winrate`, `portal_views._norm_name` (เดิม)
- Produces: `calc_custom_winrate(..., attend_probs: dict[str, float] | None = None)` — param ใหม่ keyword ตัวสุดท้าย, default `None` = พฤติกรรมเดิม 100%. breakdown row เพิ่ม key `"attend_pct": int | None`

- [ ] **Step 1: เขียน failing test** — ต่อท้าย `scripts/test_cgd_intel.py` (หลัง `test_calc_custom_winrate_dedupe_and_invalid`):

```python
def test_calc_custom_winrate_attend_weighting():
    """N+196: attend_probs ถ่วง P_eff = 1−p_attend×(1−P). attend=1.0 → invariant เท่าเดิมเป๊ะ."""
    db = _seed_calc_db()
    args = ("นครพนม", ["ถนน"], "ก่อสร้างถนนคอนกรีตเสริมเหล็ก องค์การบริหารส่วนตำบลนาทม",
            "องค์การบริหารส่วนตำบลนาทม", "นาทม", 700000, 1000000, ["หจก.ลึก"], [])
    with db.get_connection() as conn:
        base = ci.calc_custom_winrate(conn, *args)
        full = ci.calc_custom_winrate(conn, *args, attend_probs={"หจก.ลึก": 1.0})
        low = ci.calc_custom_winrate(conn, *args, attend_probs={"หจก.ลึก": 0.2})
    assert base["breakdown"][0]["attend_pct"] is None, base           # ไม่ส่ง map → มาแน่ (เดิม)
    assert full["overall_win_pct"] == base["overall_win_pct"], (full, base)   # invariant
    assert full["breakdown"][0]["attend_pct"] == 100, full
    assert low["overall_win_pct"] > base["overall_win_pct"], (low, base)      # นานๆ มาที → กดน้อยลง
    assert low["breakdown"][0]["attend_pct"] == 20, low
    # conditional "ถ้ามา ชนะเรา" ไม่เปลี่ยนตาม attend (แสดงแยกกัน)
    assert low["breakdown"][0]["win_pct_against"] == base["breakdown"][0]["win_pct_against"], low
    print("✅ calc_custom_winrate attend weighting (invariant + low-attend)")
```

และเพิ่ม `test_calc_custom_winrate_attend_weighting()` ใน `__main__` ต่อจาก `test_calc_custom_winrate_dedupe_and_invalid()`

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_cgd_intel.py`
Expected: `TypeError: calc_custom_winrate() got an unexpected keyword argument 'attend_probs'`

- [ ] **Step 3: implement** — แก้ `calc_custom_winrate` (`cgd_intel.py:867`):

signature: `... selected_names, extra_names, attend_probs=None):`
docstring เพิ่มบรรทัด: `attend_probs {ชื่อ: p_attend} → ถ่วง P_eff = 1−p_attend×(1−P) ก่อนรวม Gates (N+196); None/ชื่อนอก map = มาแน่ 1.0 (เดิมเป๊ะ).`

หลังบรรทัด `if not names: return None` เพิ่ม:

```python
    amap = {}
    for k, v in (attend_probs or {}).items():
        core = _pv._norm_name(k)
        if core:
            amap[core] = v
```

ใน loop `for nm in names:` แทนที่ 2 บรรทัดเดิม (`probs.append(p)` และ `breakdown.append({...})`) ด้วย:

```python
        pa = amap.get(_pv._norm_name(nm))
        probs.append(1.0 - pa * (1.0 - p) if pa is not None else p)
        breakdown.append({"name": nm, "win_pct_against": round((1 - p) * 100),
                          "attend_pct": round(pa * 100) if pa is not None else None,
                          "source": source, "has_history": has_history})
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `python scripts/test_cgd_intel.py`
Expected: ทุกข้อเดิมผ่าน + `✅ calc_custom_winrate attend weighting` + `ALL PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_cgd_intel.py
git commit -m "feat(pricing): calc_custom_winrate รับ attend_probs — P_eff ถ่วงโอกาสมา ก่อน Gates (N+196)"
```

---

### Task 3: `_build_intel` แนบ `predicted_attendees`

**Files:**
- Modify: `scripts/cgd_intel.py:665-667` (return ของ `_build_intel`)
- Test: `scripts/test_attendance.py` (ต่อท้าย)

**Interfaces:**
- Consumes: `bid_field.attendance_probs` (Task 1)
- Produces: dict จาก `intel_context`/`_build_intel` มี key ใหม่ `"predicted_attendees": dict | None` (รูปเดียวกับผลของ `attendance_probs`)

- [ ] **Step 1: เขียน failing test** — ต่อท้าย `scripts/test_attendance.py` (ก่อน `__main__`):

```python
def test_build_intel_predicted_attendees():
    """_build_intel แนบ predicted_attendees จากสนามเดียวกับที่คาดราคา (used_rows)."""
    db = _db(); _seed_basic(db)
    import cgd_intel as ci
    with db.get_connection() as conn:
        ctx = ci._build_intel(conn, "นครพนม", ["ถนน"], "นาทม", "นาทม", 1000000)
    assert ctx is not None, "seed อ.นาทม ต้องประกอบ intel ได้"
    pa = ctx.get("predicted_attendees")
    assert pa and pa["probs"].get("หจก.ประจำ") == 0.95, pa
    assert all("ขาจร" not in k for k in pa["probs"]), pa
    print("✅ _build_intel แนบ predicted_attendees")
```

เพิ่ม `test_build_intel_predicted_attendees()` ใน `__main__` ก่อนบรรทัด `ALL PASS`

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_attendance.py`
Expected: assert fail — `pa` เป็น `None` (key ยังไม่มี)

- [ ] **Step 3: implement** — ใน `_build_intel` ก่อน `return` สุดท้าย (`cgd_intel.py:665`) เพิ่ม:

```python
    predicted = None
    try:                                       # N+196: ทำนายคู่แข่งจาก population เดียวกับราคา
        import bid_field as _bfa
        _att_ids = [r["project_id"] for r in used_rows if r.get("project_id")]
        predicted = _bfa.attendance_probs(conn, province, tokens, project_ids=_att_ids,
                                          cf=cf, amphoe=amphoe)
    except Exception:
        _log.warning("attendance_probs wiring failed", exc_info=True)
```

และเติม `"predicted_attendees": predicted` เข้า dict ที่ return (ต่อจาก `"scope_rows": used_rows`)

- [ ] **Step 4: รันให้ผ่าน**

Run: `python scripts/test_attendance.py` แล้ว `python scripts/test_cgd_intel.py`
Expected: ALL PASS ทั้งคู่ (ของเดิมใน test_cgd_intel ไม่ assert key ครบ ไม่พังจาก key ใหม่)

- [ ] **Step 5: Commit**

```bash
git add scripts/cgd_intel.py scripts/test_attendance.py
git commit -m "feat(pricing): _build_intel แนบ predicted_attendees (สนามเดียวกับคาดราคา)"
```

---

### Task 4: portal_views — wiring + ฟอร์ม auto-predict

**Files:**
- Modify: `scripts/portal_views.py:62-160` (`job_detail`), `:532-576` (`_render_custom_calc_form`), `:609-613` (call site ใน `render_job_page`)
- Test: `scripts/test_portal_views.py` (แก้ `fake_calc` + เพิ่ม tests)

**Interfaces:**
- Consumes: `intel_ctx["predicted_attendees"]` (Task 3), `calc_custom_winrate(..., attend_probs=)` (Task 2), breakdown key `attend_pct`
- Produces: `_render_custom_calc_form(company_tables, custom_calc, prefill, tok, pid, predicted=None)`; dict จาก `job_detail` มี key `"predicted_attendees"`
- **Prefill sentinel:** `prefill is None` = GET แรก (pre-tick ตามทำนาย) · dict (แม้ selected ว่าง) = หลัง submit (เคารพผู้ใช้)

- [ ] **Step 1: แก้ test เดิม + เพิ่ม failing tests**

ใน `scripts/test_portal_views.py` แก้ `fake_calc` (บรรทัด ~280) ให้รับ param ใหม่ + capture:

```python
    def fake_calc(conn, province, tokens, project_name, dept_name, district,
                  my_price, budget, selected_names, extra_names, attend_probs=None):
        captured.update(province=province, tokens=tokens, district=district,
                        my_price=my_price, selected=selected_names, attend=attend_probs)
        return {"my_discount_pct": 10.0, "overall_win_pct": 55, "breakdown": []}
```

ใน mock `intel_context` ของ test เดียวกัน (บรรทัด ~272) เพิ่ม key:
`"predicted_attendees": {"probs": {"หจก.A": 0.7}, "conf": None, "n_auctions": 8},`

และเพิ่ม assert ใน `test_job_detail_custom_calc` หลัง assert `captured["selected"]`:

```python
    assert captured["attend"] == {"หจก.A": 0.7}, captured
    assert d["predicted_attendees"]["probs"] == {"หจก.A": 0.7}, d
```

เพิ่ม test ใหม่ต่อท้ายไฟล์ (สไตล์ script-level เดียวกับไฟล์):

```python
# --- _render_custom_calc_form: auto-predict (N+196) ---
def test_render_calc_form_auto_predict():
    ct = [{"label": "x", "companies": [
        {"name": "หจก.เอ", "games": 3, "median": 12.0},
        {"name": "หจก.บี", "games": 2, "median": 8.0}]}]
    pred = {"probs": {"หจก.เอ": 0.8}, "conf": None, "n_auctions": 8}
    # GET แรก (prefill=None) → กลุ่มทำนาย pre-tick, กลุ่มรองไม่ tick
    h = pv._render_custom_calc_form(ct, None, None, "TOK", "P1", pred)
    assert "ระบบเดาคู่แข่งให้" in h, h
    assert "โอกาสมา ~80%" in h, h
    assert 'value="หจก.เอ" checked' in h, h
    assert 'value="หจก.บี" checked' not in h and 'value="หจก.บี"' in h, h
    assert "เจ้าอื่นในพื้นที่" in h, h
    # หลัง submit ติ๊กออกหมด → ไม่ re-tick
    h2 = pv._render_custom_calc_form(ct, None, {"my_price": "900000", "selected_names": [],
                                                "extra_names": []}, "TOK", "P1", pred)
    assert 'value="หจก.เอ" checked' not in h2, h2
    # ทำนายไม่ได้ → header เดิม + note fallback
    h3 = pv._render_custom_calc_form(ct, None, None, "TOK", "P1", None)
    assert "ระบบเดารายชื่อไม่ได้" in h3 and "คำนวณโอกาสชนะเจาะจงคู่แข่ง" in h3, h3
    assert "checked" not in h3, h3
    # conf 🟡 → ป้ายบอก scope
    h4 = pv._render_custom_calc_form(ct, None, None, "TOK", "P1",
                                     {"probs": {"หจก.เอ": 0.8}, "conf": ("🟡", "อำเภอ"), "n_auctions": 6})
    assert "🟡 คำทำนายอิงข้อมูลอำเภอ" in h4, h4
    # ทำนายชื่อที่ไม่อยู่ใน company_tables (มาจาก bid_results ผู้แพ้) → render ได้ ไม่พัง
    h5 = pv._render_custom_calc_form(ct, None, None, "TOK", "P1",
                                     {"probs": {"หจก.นอกลิสต์": 0.6}, "conf": None, "n_auctions": 8})
    assert 'value="หจก.นอกลิสต์" checked' in h5, h5
    # breakdown แสดง "โอกาสมา X% · ถ้ามา ชนะคุณ ~Y%" / ไม่มี attend → conditional อย่างเดียว
    cc = {"overall_win_pct": 62, "my_discount_pct": 12.0, "breakdown": [
        {"name": "หจก.เอ", "win_pct_against": 55, "attend_pct": 80, "source": "", "has_history": True},
        {"name": "หจก.ซี", "win_pct_against": 30, "attend_pct": None, "source": "สนามทั่วไป", "has_history": False}]}
    h6 = pv._render_custom_calc_form(ct, cc, {"my_price": "880000", "selected_names": ["หจก.เอ"],
                                              "extra_names": ["หจก.ซี"]}, "TOK", "P1", pred)
    assert "โอกาสชนะของคุณรวม: 62%" in h6, h6
    assert "โอกาสมา 80% · ถ้ามา ชนะคุณ ~55%" in h6, h6
    assert "ถ้ามา ชนะคุณ ~30%" in h6 and "โอกาสมา 80% · ถ้ามา ชนะคุณ ~30%" not in h6, h6
    print("OK render_calc_form_auto_predict")

test_render_calc_form_auto_predict()
```

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_portal_views.py`
Expected: fail ที่ assert `captured["attend"]` (job_detail ยังไม่ส่ง) หรือ `TypeError` ที่ `_render_custom_calc_form` รับ 6 args

- [ ] **Step 3: implement portal_views**

**(a) `job_detail`** — บรรทัด ~83 เพิ่ม `predicted_attendees = None` (ข้างๆ `custom_calc = None`). ในบล็อก `if intel_ctx:` (~บรรทัด 89) เพิ่ม `predicted_attendees = intel_ctx.get("predicted_attendees")` และแก้ call `calc_custom_winrate` เพิ่ม arg keyword ท้ายสุด:

```python
                    calc_params.get("selected_names") or [], calc_params.get("extra_names") or [],
                    attend_probs=(predicted_attendees or {}).get("probs"))
```

ใน dict ที่ `job_detail` return (หา `"company_tables": company_tables` ใน return statement ตอนท้ายฟังก์ชัน) เพิ่ม `"predicted_attendees": predicted_attendees,`

**(b) `_render_custom_calc_form`** — แทนที่ทั้งฟังก์ชัน (บรรทัด 532-576):

```python
def _render_custom_calc_form(company_tables, custom_calc, prefill, tok, pid, predicted=None):
    """ฟอร์มคำนวณโอกาสชนะเจาะจงคู่แข่ง (N+168, auto-predict N+196) — กลุ่ม "คาดว่าจะมายื่น"
    pre-tick จาก attendance_probs + กลุ่มรองจาก company_tables + textarea + ราคา. ไม่มี JS.
    prefill=None = GET แรก (pre-tick ตามทำนาย) · dict = หลัง submit (เคารพติ๊กของผู้ใช้)."""
    initial = prefill is None
    prefill = prefill or {}
    pred_probs = (predicted or {}).get("probs") or {}
    seen, opts = set(), []
    for blk in company_tables or []:
        for cmp_ in blk.get("companies") or []:
            core = _norm_name(cmp_["name"])
            if core and core not in seen:
                seen.add(core)
                opts.append(cmp_)
    opt_by_core = {_norm_name(c["name"]): c for c in opts}
    pred_items = sorted(pred_probs.items(), key=lambda kv: -kv[1])
    pred_cores = {_norm_name(n) for n, _p in pred_items}
    checked_names = (set(n for n, _p in pred_items) if initial
                     else set(prefill.get("selected_names") or []))
    header = "🎯 โอกาสชนะ (ระบบเดาคู่แข่งให้)" if pred_items else "🎯 คำนวณโอกาสชนะเจาะจงคู่แข่ง"
    out = [f"<div class=\"bidhead\">{header}</div>",
           "<form class=\"calcform\" method=\"post\" action=\"/portal/job/calc\">",
           f"<input type=\"hidden\" name=\"t\" value=\"{tok}\">",
           f"<input type=\"hidden\" name=\"pid\" value=\"{_h.escape(str(pid))}\">"]

    def _cb(name, label_extra):
        nm = _h.escape(name)
        chk = " checked" if name in checked_names else ""
        return (f"<label><input type=\"checkbox\" name=\"competitors\" value=\"{nm}\"{chk}> "
                f"{nm}{label_extra}</label>")

    def _hist(cmp_):
        if cmp_ and cmp_.get("median") is not None:
            return f" (ชนะ {cmp_['games']} งาน, ลดเฉลี่ย {cmp_['median']:.0f}%)"
        return ""

    if pred_items:
        out.append("<div class=\"meta\">คาดว่าจะมายื่น (ติ๊กออกได้ถ้ารู้ว่าไม่มา):</div>")
        for name, p in pred_items:
            out.append(_cb(name, f" — โอกาสมา ~{round(p * 100)}%" + _hist(opt_by_core.get(_norm_name(name)))))
        if (predicted or {}).get("conf"):
            emoji, scope_word = predicted["conf"]
            out.append(f"<div class=\"meta\">{emoji} คำทำนายอิงข้อมูล{scope_word} (พื้นที่นี้ข้อมูลบาง)</div>")
        out.append("<div class=\"meta\">เจ้าอื่นในพื้นที่ (นานๆ มาที — ติ๊กเพิ่มได้ = มาแน่):</div>")
    else:
        out.append("<div class=\"meta\">ข้อมูลสนามนี้ยังบาง — ระบบเดารายชื่อไม่ได้ เลือกเองได้ด้านล่าง</div>")
    for cmp_ in opts:
        if _norm_name(cmp_["name"]) in pred_cores:
            continue
        out.append(_cb(cmp_["name"], _hist(cmp_)))
    extra_pf = _h.escape("\n".join(prefill.get("extra_names") or []))
    out.append("<label>หรือพิมพ์ชื่อบริษัทอื่นเพิ่ม (1 ชื่อ/บรรทัด · ถือว่ามาแน่):</label>"
               f"<textarea name=\"extra_names\" rows=\"2\">{extra_pf}</textarea>")
    price_pf = _h.escape(str(prefill.get("my_price") or ""))
    out.append("<label>ราคาที่จะยื่น (บาท):</label>"
               f"<input type=\"number\" name=\"my_price\" value=\"{price_pf}\" min=\"1\" step=\"1\">"
               "<button type=\"submit\">คำนวณโอกาสชนะ</button></form>")
    if custom_calc:
        out.append(f"<div class=\"calcresult\"><div class=\"big\">🎯 โอกาสชนะของคุณรวม: "
                   f"{custom_calc['overall_win_pct']}%</div>"
                   f"<div class=\"meta\">ราคาของคุณ = ลด {custom_calc['my_discount_pct']}%</div>")
        for b in custom_calc["breakdown"]:
            src = b.get("source") or ""
            src_note = f" ({src})" if src else ""
            att = b.get("attend_pct")
            att_txt = f"โอกาสมา {att}% · " if att is not None else ""
            out.append(f"<div class=\"crow\"><span>{_h.escape(b['name'])}{src_note}</span>"
                       f"<span>{att_txt}ถ้ามา ชนะคุณ ~{b['win_pct_against']}%</span></div>")
        out.append("<div class=\"note\">*โอกาสมา = ความถี่ที่บริษัทโผล่ในสนามแบบนี้ · โอกาสชนะประเมินจาก"
                   "นิสัยการยื่นราคาในงานประเภท+หน่วยงานแบบเดียวกัน (โมเดล Gates) — เป็นการประมาณ ไม่ใช่การรับประกัน</div></div>")
    elif custom_calc is None and prefill.get("my_price"):
        out.append("<div class=\"msg\">เลือกคู่แข่งอย่างน้อย 1 บริษัท หรือกรอกราคาให้ถูกต้อง</div>")
    return "".join(out)
```

หมายเหตุ breakdown เดิม (`ชนะคุณ ~X%`) เปลี่ยน copy เป็น `ถ้ามา ชนะคุณ ~X%` — ตรวจว่าไม่มี test เดิม assert copy เก่า (grep `ชนะคุณ` ใน test_portal_views.py ก่อน ถ้ามีให้อัปเดตตาม)

**(c) call site ใน `render_job_page`** (บรรทัด ~611):

```python
    if data.get("company_tables"):
        b.append(_render_custom_calc_form(data["company_tables"], data.get("custom_calc"),
                                          data.get("calc_prefill"), tok, j["project_id"],
                                          data.get("predicted_attendees")))
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `python scripts/test_portal_views.py`
Expected: ทุก OK เดิม + `OK render_calc_form_auto_predict`

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): ฟอร์มโอกาสชนะเดาคู่แข่งอัตโนมัติ — pre-tick + โอกาสมา% + fallback (N+196)"
```

---

### Task 5: Regression เต็ม + verify งานจริง + บันทึก

**Files:**
- Modify: `progress_log.md` (อัปเดต entry N+196)

- [ ] **Step 1: รัน test ทุกไฟล์ที่เกี่ยว**

```bash
python scripts/test_attendance.py && python scripts/test_cgd_intel.py && \
python scripts/test_winrate.py && python scripts/test_winrate_grid.py && \
python scripts/test_portal_views.py && python scripts/test_portal_page.py && \
python scripts/test_portal_jobs.py
```
Expected: ALL PASS ทุกไฟล์

- [ ] **Step 2: verify งานจริงกับ DB local** — หา pid จริงที่เคยส่ง LINE แล้วลองทั้ง flow:

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
import Sebastian_Customer_DB as db, portal_views as pv
with db.get_connection() as conn:
    pids = [r[0] for r in conn.execute(
        'SELECT DISTINCT project_id FROM notification_queue ORDER BY id DESC LIMIT 5')]
    for pid in pids:
        d = pv.job_detail(conn, pid)
        pa = (d or {}).get('predicted_attendees')
        print(pid, '→', None if not pa else (pa['conf'], pa['n_auctions'], list(pa['probs'].items())[:5]))
"
```
เกณฑ์ผ่าน (spec §7.5): อย่างน้อย 1 งานได้รายชื่อ non-empty, p สมเหตุผล (Σp ≈ n_mean ของสนาม ±50%), งานที่ข้อมูลบางได้ `None` (fallback) โดยไม่ throw — ถ้าได้ None หมดทั้ง 5 งาน ให้ลอง pid จากงานถนนนครพนม/บึงกาฬที่มี winrate_table

- [ ] **Step 3: Sophia sanity audit** (per CLAUDE.md) — dispatch Sophia: "N+196 เพิ่ม attendance_probs + attend_probs ใน calc + ฟอร์ม portal — read-only ตรวจว่าไม่มี write path ใหม่ลง DB, test ไม่แตะ prod DB (BMS_DATA_DIR temp), invariant attend=1.0 = เดิม" → รอ verdict SAFE

- [ ] **Step 4: อัปเดต progress_log.md** — entry N+196 เปลี่ยนสถานะเป็น ✅ + ผล verify + commit hashes แล้ว commit:

```bash
git add progress_log.md
git commit -m "docs(progress): N+196 auto-competitor winrate เสร็จ — tests เขียว + verify งานจริง"
```

- [ ] **Step 5: Discord แจ้งเสร็จ + รอ confirm deploy** — ส่ง "✅ N+196 เดาคู่แข่งอัตโนมัติบน Board B เสร็จ (local) — รอ confirm deploy VPS" · **ห้าม push จนกัญจน์ยืนยัน** (VPS deploy: pull → restart bms-api — ไม่มี migration/dependency ใหม่ · Vercel ไม่ต้อง deploy)

---

## Self-Review Notes

- Spec coverage: §2 โมเดล→Task 2 · §3 attendance→Task 1 · §4 UX/prefill→Task 4 · §5 fallback→Task 1(gate)+4(note) · §6 touchpoints ตรง · §7 criteria→Task 1-5 (invariant=Task 2 test, render=Task 4 test, งานจริง=Task 5)
- Type consistency: `attendance_probs` คืน `{"probs","conf","n_auctions"}` ใช้ตรงกันใน Task 3 (แนบทั้ง dict), Task 4 (`.get("probs")`, `.get("conf")`)
- ชื่อ param `attend_probs` (calc) vs `predicted` (render) — คนละชั้น: calc รับ map ชื่อ→p, render รับ dict เต็ม
