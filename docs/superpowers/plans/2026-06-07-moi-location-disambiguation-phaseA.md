# MOI/พิกัด Location Disambiguation — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) หรือ subagent-driven-development. Steps ใช้ `- [ ]`.

**Goal:** intel ระบุ (ตำบล, อำเภอ) ของงาน D0 แม่นด้วย lat/lng reverse-geocode (Phase A) → query cgd_winners ตรงพื้นที่ ไม่ degrade จังหวัด เมื่อตำบลซ้ำอำเภอ

**Architecture:** หยุดทิ้ง location จาก getProcurementDetail (capture district_moi_id+moi_name+lat/lng แก้ swap ลง project_locations, 0 API เพิ่ม) → `resolve_location` runtime-compute (geo→tambon→dept→province) + confidence + trace (ไม่ persist derived) → select_competitors รับ amphoe → backfill งาน active

**Tech Stack:** Python 3, sqlite3, csv/haversine (stdlib), reuse job_matcher/process5_http_client

**Spec:** `docs/superpowers/specs/2026-06-07-moi-location-disambiguation-design.md` (Phase A เท่านั้น; MOI decode = Phase B)

---

## File Structure
- `scripts/geo_reverse.py` (**new**) — reverse_geocode + amphoes_of_tambon (โหลด thai_geo_raw ครั้งเดียว)
- `scripts/cgd_intel.py` — `resolve_location` (new), `select_competitors` รับ `amphoe`, `intel_lines` ส่ง project_id
- `scripts/Sebastian_Enrichment_Worker.py:397` — capture location (get_procurement_detail + persist raw swapped)
- `scripts/Sebastian_Customer_DB.py` — helper `save_project_location_raw` (UPDATE raw fields)
- `scripts/Sebastian_LINE_Sender.py:260` — wire project_id
- `scripts/backfill_location.py` (**new**) — backfill งาน active เปิดอยู่
- `scripts/test_geo_reverse.py` (**new**), `scripts/test_cgd_intel.py` — tests

---

### Task 1: geo_reverse.py — reverse_geocode + amphoes_of_tambon

**Files:** Create `scripts/geo_reverse.py`, `scripts/test_geo_reverse.py`

- [ ] **Step 1: เขียน test** (`test_geo_reverse.py`) — หาแถวโพนทองจริงจาก csv แล้ว assert
```python
import sys, csv; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import geo_reverse as gr

_CSV = Path(__file__).parent.parent / "data" / "thai_geo_raw.csv"

def _find(prov, amphoe, tambon):
    with open(_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["province"]==prov and r["district"]==amphoe and r["subdistrict"]==tambon:
                return float(r["latitude"]), float(r["longitude"])
    return None

def test_reverse_geocode_disambiguates_tambon():
    bp = _find("นครพนม", "บ้านแพง", "โพนทอง")
    rn = _find("นครพนม", "เรณูนคร", "โพนทอง")
    assert bp and rn, (bp, rn)   # ทั้งสองโพนทองมีจริงใน geo
    p, a, t, d = gr.reverse_geocode(bp[0], bp[1])
    assert a == "บ้านแพง" and d < 1.0, (a, d)
    p2, a2, t2, d2 = gr.reverse_geocode(rn[0], rn[1])
    assert a2 == "เรณูนคร", a2
    print("✅ reverse_geocode")

def test_reverse_geocode_bad_input():
    assert gr.reverse_geocode("", "") is None
    assert gr.reverse_geocode(None, 100.0) is None
    print("✅ reverse_geocode bad input")

def test_amphoes_of_tambon():
    as = gr.amphoes_of_tambon("นครพนม", "โพนทอง")
    assert "บ้านแพง" in as and "เรณูนคร" in as and len(as) >= 2, as   # ซ้ำ
    assert gr.amphoes_of_tambon("นครพนม", "ไม่มีตำบลนี้") == []
    print("✅ amphoes_of_tambon")

if __name__ == "__main__":
    test_reverse_geocode_disambiguates_tambon()
    test_reverse_geocode_bad_input()
    test_amphoes_of_tambon()
    print("ALL PASS geo_reverse")
```
- [ ] **Step 2: รัน → FAIL** `python scripts/test_geo_reverse.py` → ModuleNotFoundError geo_reverse
- [ ] **Step 3: เขียน `geo_reverse.py`**
```python
"""geo_reverse.py — reverse-geocode พิกัด → (จังหวัด,อำเภอ,ตำบล) จาก thai_geo_raw.csv (self-contained).
ใช้แยกอำเภอเมื่อตำบลซ้ำ (intel ระดับท้องถิ่น). thai_geo_raw lat/lng ถูกต้อง (กทม. lat=13.75)."""
import csv
import math
from pathlib import Path

_CSV = Path(__file__).parent.parent / "data" / "thai_geo_raw.csv"
_POINTS = None   # list[(lat, lng, province, district, subdistrict)]


def _load():
    global _POINTS
    if _POINTS is None:
        pts = []
        with open(_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    pts.append((float(r["latitude"]), float(r["longitude"]),
                                r["province"], r["district"], r["subdistrict"]))
                except (ValueError, KeyError):
                    continue
        _POINTS = pts
    return _POINTS


def _haversine(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def reverse_geocode(lat, lng):
    """(province, amphoe, tambon, distance_km) ของ subdistrict centroid ใกล้สุด. None ถ้าพิกัดใช้ไม่ได้."""
    try:
        lat = float(lat); lng = float(lng)
    except (TypeError, ValueError):
        return None
    if not lat or not lng:
        return None
    best = None
    for plat, plng, prov, dist, sub in _load():
        d = _haversine(lat, lng, plat, plng)
        if best is None or d < best[3]:
            best = (prov, dist, sub, d)
    return best


def amphoes_of_tambon(province, tambon):
    """list อำเภอ (distinct) ที่มีตำบลชื่อนี้ในจังหวัด — ใช้เช็ค ambiguity. [] ถ้าไม่มี."""
    out = []
    for _lat, _lng, prov, dist, sub in _load():
        if prov == province and sub == tambon and dist not in out:
            out.append(dist)
    return out
```
- [ ] **Step 4: รัน → PASS** `python scripts/test_geo_reverse.py`
- [ ] **Step 5: Commit** `git add scripts/geo_reverse.py scripts/test_geo_reverse.py && git commit -m "feat(geo): reverse_geocode + amphoes_of_tambon (thai_geo_raw, self-contained)"`

---

### Task 2: capture location helper (Customer_DB) + persist ที่ enrichment worker

**Files:** Modify `scripts/Sebastian_Customer_DB.py` (helper), `scripts/Sebastian_Enrichment_Worker.py:393-400`, `scripts/test_cgd_sync.py` (helper test)

- [ ] **Step 1: เขียน test** (เพิ่มท้าย `test_cgd_sync.py` ก่อน print สุดท้าย) — helper persist raw + swap
```python
# v: save_project_location_raw — persist raw location (swap lat/lng จาก API)
with db.get_connection() as cc:
    cc.execute("INSERT OR IGNORE INTO project_locations (project_id, location_confidence, enrichment_status, created_at) "
               "VALUES ('LOC1','unknown','pending','2026-06-07')")
db.save_project_location_raw("LOC1", district_moi_id="480400", moi_name="โพนทอง",
                             api_latitude="104.2", api_longitude="17.9")  # API swap: lat field=lng
with db.get_connection() as cc:
    r = cc.execute("SELECT district_moi_id, moi_name, latitude, longitude FROM project_locations WHERE project_id='LOC1'").fetchone()
assert r[0]=="480400" and r[1]=="โพนทอง", r
assert r[2]=="17.9" and r[3]=="104.2", r  # เก็บแล้ว latitude=real lat (17.9), longitude=real lng (104.2)
print("✅ save_project_location_raw (swap)")
```
- [ ] **Step 2: รัน → FAIL** `python scripts/test_cgd_sync.py` → AttributeError save_project_location_raw
- [ ] **Step 3: เพิ่ม helper ใน `Sebastian_Customer_DB.py`** (ใกล้ get_connection/ฟังก์ชัน util)
```python
def save_project_location_raw(project_id: str, district_moi_id: str = "", moi_name: str = "",
                              api_latitude: str = "", api_longitude: str = "") -> None:
    """persist raw location จาก getProcurementDetail (Phase A). แก้ swap: eGP field 'latitude'
    เก็บค่า longitude จริง → สลับเก็บให้ latitude=lat จริง. ไม่แตะ qualification/enrichment_status.
    เก็บเฉพาะ raw — amphoe/confidence เป็น runtime-compute (ไม่ persist)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_locations SET district_moi_id=?, moi_name=?, latitude=?, longitude=? "
            "WHERE project_id=?",
            (district_moi_id or "", moi_name or "",
             str(api_longitude or ""), str(api_latitude or ""), project_id))  # SWAP
```
- [ ] **Step 4: รัน → PASS** `python scripts/test_cgd_sync.py`
- [ ] **Step 5: แก้ enrichment worker** `Sebastian_Enrichment_Worker.py` บรรทัด 396-399 (จาก `jm.resolve_tambon` → capture เต็ม, API call เท่าเดิม)
```python
            if jm is not None and mmode != "off":
                from process5_http_client import get_procurement_detail
                _d = get_procurement_detail(pid)
                tb = (_d.get("moi_name") or "") or jm.tambon_from_dept(c.get("dept_name") or "")
                if _d.get("valid"):
                    save_project_location_raw(pid, _d.get("district_moi_id") or "",
                                              _d.get("moi_name") or "",
                                              _d.get("latitude") or "", _d.get("longitude") or "")
                decision, mdet = jm.match_job(c.get("project_name") or "", c["province"], tb,
                                              c.get("dept_name") or "", cfg=mcfg)
```
(ตรวจ import `save_project_location_raw` มีใน scope — มาจาก Sebastian_Customer_DB ที่ worker import อยู่แล้ว; ถ้าไม่ เพิ่ม `from Sebastian_Customer_DB import save_project_location_raw`)
- [ ] **Step 6: sanity import** `BMS_ENV=dev python -c "import sys; sys.path.insert(0,'scripts'); import Sebastian_Enrichment_Worker"` → ไม่ error
- [ ] **Step 7: Commit** `git add scripts/Sebastian_Customer_DB.py scripts/Sebastian_Enrichment_Worker.py scripts/test_cgd_sync.py && git commit -m "feat(loc): capture district_moi_id+moi_name+lat/lng (swap fix) ตอน resolve (0 API เพิ่ม)"`

---

### Task 3: cgd_intel.resolve_location — runtime chain + confidence + trace

**Files:** Modify `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: เขียน test** (เพิ่มใน test_cgd_intel.py; fixture project_locations ใน :memory:)
```python
def _loc_conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE project_locations (project_id TEXT PRIMARY KEY,
        district_moi_id TEXT, moi_name TEXT, latitude TEXT, longitude TEXT)""")
    return c

def test_resolve_location_geo():
    import csv
    from pathlib import Path
    csvp = Path(__file__).parent.parent / "data" / "thai_geo_raw.csv"
    bp = None
    for r in csv.DictReader(open(csvp, encoding="utf-8")):
        if r["province"]=="นครพนม" and r["district"]=="บ้านแพง" and r["subdistrict"]=="โพนทอง":
            bp = (r["latitude"], r["longitude"]); break
    assert bp, "fixture"
    c = _loc_conn()
    # เก็บแบบ corrected (latitude=lat จริง) → resolve ชั้น geo
    c.execute("INSERT INTO project_locations VALUES ('P1','','โพนทอง',?,?)", (bp[0], bp[1]))
    out = ci.resolve_location("P1", "ก่อสร้างถนน", "", c)
    assert out["amphoe"] == "บ้านแพง" and out["source"] == "geo", out
    assert out["location_confidence"] in ("HIGH","MEDIUM"), out
    assert any("geo" in t for t in out["resolution_trace"]), out
    print("✅ resolve_location geo")

def test_resolve_location_fallbacks():
    c = _loc_conn()
    # ไม่มี row → ตำบลไม่ซ้ำ (ใช้ geo unique) หรือ dept หรือ province
    # ต.บ้านแพง (ชื่อตำบล=อำเภอ) unique → ชั้น tambon
    out = ci.resolve_location("PX", "ก่อสร้างถนน ต.หนองซน", "", c)
    assert out["source"] in ("tambon","province"), out   # หนองซน อาจ unique
    # ไม่มีอะไรเลย → province (amphoe None, LOW)
    out2 = ci.resolve_location("PY", "จัดซื้อรถ", "", c)
    assert out2["amphoe"] is None and out2["location_confidence"]=="LOW", out2
    print("✅ resolve_location fallbacks")
```
- [ ] **Step 2: รัน → FAIL** `BMS_ENV=dev python scripts/test_cgd_intel.py` → AttributeError resolve_location
- [ ] **Step 3: เพิ่ม `resolve_location` ใน cgd_intel.py** (หลัง resolve_tambon)
```python
def resolve_location(project_id: str, project_name: str, dept_name: str, conn) -> dict:
    """runtime-compute (ไม่ persist) ตำบล+อำเภอ แม่น→หยาบ: [moi=phaseB] → geo(lat/lng) →
    unique-tambon → dept → province. คืน tambon/amphoe/location_confidence/source/resolution_trace."""
    import geo_reverse
    import job_matcher as jm
    trace = ["moi: deferred (phaseB)"]
    moi_name = lat = lng = ""
    if project_id:
        try:
            r = conn.execute("SELECT moi_name, latitude, longitude FROM project_locations "
                             "WHERE project_id=?", (project_id,)).fetchone()
            if r:
                moi_name, lat, lng = (r[0] or ""), (r[1] or ""), (r[2] or "")
        except sqlite3.OperationalError:
            pass
    name_tb = ""
    try:
        name_tb = jm.tambon_from_name(project_name) or ""
    except Exception:
        pass
    tb = moi_name or name_tb
    province_guess = None
    # ชั้น 2: geo (lat/lng corrected ตอน capture แล้ว)
    geo = geo_reverse.reverse_geocode(lat, lng) if (lat and lng) else None
    if geo:
        prov, amphoe, gtb, dist = geo
        conf = "HIGH" if dist < 0.5 else "MEDIUM" if dist < 2 else "LOW"
        trace.append(f"geo: {amphoe} dist={dist*1000:.0f}m → {conf}")
        return {"tambon": tb or gtb, "amphoe": amphoe, "location_confidence": conf,
                "source": "geo", "resolution_trace": trace}
    trace.append("geo: no latlng")
    # ชั้น 3: unique tambon
    if tb:
        amphoes = geo_reverse.amphoes_of_tambon(_province_of(project_name, dept_name) or "", tb)
        # province ไม่ทราบที่ resolve นี้ — ใช้เช็ค ambiguity ข้ามจังหวัดไม่ได้; ส่ง province ผ่าน caller แทน
    return _resolve_fallback(tb, dept_name, trace)
```
> หมายเหตุ: resolve_location **ต้องรู้ province** เพื่อ amphoes_of_tambon — เพิ่ม arg `province`. แก้ signature เป็น `resolve_location(project_id, project_name, dept_name, province, conn)` และ test/caller ส่ง province. (เขียนเต็มใน step นี้:)
```python
def resolve_location(project_id: str, project_name: str, dept_name: str, province: str, conn) -> dict:
    import geo_reverse
    import job_matcher as jm
    trace = ["moi: deferred (phaseB)"]
    moi_name = lat = lng = ""
    if project_id:
        try:
            r = conn.execute("SELECT moi_name, latitude, longitude FROM project_locations WHERE project_id=?",
                             (project_id,)).fetchone()
            if r:
                moi_name, lat, lng = (r[0] or ""), (r[1] or ""), (r[2] or "")
        except sqlite3.OperationalError:
            pass
    try:
        name_tb = jm.tambon_from_name(project_name) or ""
    except Exception:
        name_tb = ""
    tb = moi_name or name_tb
    geo = geo_reverse.reverse_geocode(lat, lng) if (lat and lng) else None
    if geo:
        _prov, amphoe, gtb, dist = geo
        conf = "HIGH" if dist < 0.5 else "MEDIUM" if dist < 2 else "LOW"
        trace.append(f"geo: {amphoe} dist={dist*1000:.0f}m → {conf}")
        return {"tambon": tb or gtb, "amphoe": amphoe, "location_confidence": conf,
                "source": "geo", "resolution_trace": trace}
    trace.append("geo: no latlng")
    if tb:                                              # ชั้น 3 unique tambon
        amphoes = geo_reverse.amphoes_of_tambon(province, tb)
        if len(amphoes) == 1:
            trace.append(f"tambon: {tb} unique → {amphoes[0]}")
            return {"tambon": tb, "amphoe": amphoes[0], "location_confidence": "HIGH",
                    "source": "tambon", "resolution_trace": trace}
        trace.append(f"tambon: {tb} ambiguous({len(amphoes)})")
    try:                                               # ชั้น 4 dept
        dtb = jm.tambon_from_dept(dept_name) or ""
    except Exception:
        dtb = ""
    if dtb:
        damphoes = geo_reverse.amphoes_of_tambon(province, dtb)
        if len(damphoes) == 1:
            trace.append(f"dept: {dtb} → {damphoes[0]}")
            return {"tambon": tb or dtb, "amphoe": damphoes[0], "location_confidence": "MEDIUM",
                    "source": "dept", "resolution_trace": trace}
        trace.append(f"dept: {dtb} ambiguous/none")
    trace.append("province degrade")                    # ชั้น 5
    return {"tambon": tb, "amphoe": None, "location_confidence": "LOW",
            "source": "province", "resolution_trace": trace}
```
(ลบ pseudo `_province_of`/`_resolve_fallback` ในร่างแรกออก — ใช้เวอร์ชันเต็มด้านบนที่รับ province)
- [ ] **Step 4: แก้ test ให้ส่ง province** — ใน test_resolve_location_geo: `ci.resolve_location("P1","ก่อสร้างถนน","","นครพนม",c)` · fallbacks เช่นกันเติม `"นครพนม"`
- [ ] **Step 5: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 6: Commit** `git add scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "feat(intel): resolve_location runtime chain (geo→tambon→dept→province) + confidence + trace"`

---

### Task 4: select_competitors รับ amphoe + intel_lines ใช้ resolve_location

**Files:** Modify `scripts/cgd_intel.py`, `scripts/test_cgd_intel.py`

- [ ] **Step 1: แก้ test_select_competitors + test_intel_lines** ให้ใช้ amphoe param
```python
def test_select_competitors():
    c = _fixture_conn(); tk = ["ถนน"]
    # ระบุ amphoe ตรง → tambon level (subdistrict+district)
    rows, scope, level = ci.select_competitors("นครพนม", tk, "โพนทอง", "บ้านแพง", c)
    assert level == "tambon" and "ต.โพนทอง" in scope and "บ้านแพง" in scope, (level, scope)
    assert {r["winner"] for r in rows} == {"หจก.A", "หจก.B"}, rows
    # amphoe=None → province
    assert ci.select_competitors("นครพนม", tk, "", None, c)[2] == "province"
    # จังหวัดไม่มีงาน → []
    assert ci.select_competitors("เชียงใหม่", tk, "", None, c)[0] == []
    print("✅ select_competitors")
```
(test_intel_lines: ใช้ fixture เดิม + ต้องมี project_locations? intel_lines เรียก resolve_location ซึ่งอ่าน project_locations — fixture conn ไม่มี table นั้น → resolve คืน province (OperationalError→ข้าม) → intel ยังทำงานระดับจังหวัด. ปรับ assert header รับได้ทั้ง ต./จังหวัด:)
```python
def test_intel_lines():
    c = _fixture_conn()
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", conn=c)
    assert out and out[0].startswith("💡 ราคาอ้างอิง (งานถนน"), out[0]
    assert "🏆 คู่แข่งแถบนี้:" in out and any("หจก." in l for l in out), out
    assert any(l.startswith("📊 ภาพรวม") for l in out) and any(l[0] in "🟢🟡🔴" for l in out), out
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", conn=c) == []
    assert ci.intel_lines("เชียงใหม่", "ก่อสร้างถนน", conn=c) == []
    print("✅ intel_lines")
```
- [ ] **Step 2: รัน → FAIL** `BMS_ENV=dev python scripts/test_cgd_intel.py` (select_competitors signature เก่า / intel_lines signature)
- [ ] **Step 3: แก้ `select_competitors` รับ amphoe** (แทนของเดิมที่ derive)
```python
def select_competitors(province: str, tokens: list, tambon: str, amphoe, conn) -> tuple:
    """เลือกคู่แข่ง: ถ้ามี amphoe → tambon level (subdistrict+district) → fallback อำเภอ → จังหวัด.
    ไม่มี amphoe → จังหวัด. คืน (rows, scope_label, level). competitive-set กรองใน _fetch."""
    wt = tokens[0] if tokens else "งาน"
    if amphoe and tambon:
        trows = _fetch(conn, province, tokens, subdistrict=tambon, district=amphoe)
        if _distinct_winners(trows) >= 1:
            return trows, f"งาน{wt} ต.{tambon} อ.{amphoe}", "tambon"
    if amphoe:
        arows = _fetch(conn, province, tokens, district=amphoe)
        if _distinct_winners(arows) >= MIN_COMPETITORS:
            return arows, f"งาน{wt} อ.{amphoe}", "amphoe"
    prows = _fetch(conn, province, tokens)
    if _distinct_winners(prows) >= 1:
        return prows, f"งาน{wt}ใน{province}", "province"
    return [], "", "province"
```
- [ ] **Step 4: แก้ `intel_lines` ใช้ resolve_location** (แทน resolve_tambon เดิม)
```python
def intel_lines(province: str, project_name: str, dept_name: str = "",
                project_id: str = "", conn=None) -> list:
    """💡 competitor intel ระดับท้องถิ่นสำหรับ D0. resolve (ตำบล,อำเภอ) runtime → select → format.
    competitive-set ทั้ง selection+stat. ห่อ try/except — ห้าม throw."""
    try:
        tokens = match_keywords(project_name)
        if not tokens:
            return []
        own = conn is None
        if own:
            from Sebastian_Customer_DB import get_connection
            conn = get_connection()
        try:
            loc = resolve_location(project_id, project_name, dept_name, province, conn)
            rows, scope, _level = select_competitors(province, tokens, loc["tambon"], loc["amphoe"], conn)
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
            area_n = len(rows); p25, p75 = _pct(discs, 25), _pct(discs, 75)
            lines.append(f"📊 ภาพรวม {area_n} งาน · ลด {p25:.0f}–{p75:.0f}%" if p75
                         else f"📊 ภาพรวม {area_n} งาน")
            lines.append(confidence_label(area_n, p25, p75))
            return lines
        finally:
            if own:
                conn.close()
    except Exception:
        return []
```
(ลบ `resolve_tambon` เดิมถ้าไม่มีที่ใช้แล้ว — เช็ค: ไม่มี caller อื่น → ลบได้)
- [ ] **Step 5: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py`
- [ ] **Step 6: Commit** `git add scripts/cgd_intel.py scripts/test_cgd_intel.py && git commit -m "feat(intel): select_competitors(amphoe) + intel_lines ใช้ resolve_location"`

---

### Task 5: wire project_id ที่ format_notification

**Files:** Modify `scripts/Sebastian_LINE_Sender.py:260`

- [ ] **Step 1: แก้ call site**
```python
            _il = cgd_intel.intel_lines(province, project_name, dept_name, project_id)
```
- [ ] **Step 2: รัน → PASS** `BMS_ENV=dev python scripts/test_cgd_intel.py` (test_wiring ใช้ lambda *a,**k รับได้)
- [ ] **Step 3: Commit** `git add scripts/Sebastian_LINE_Sender.py && git commit -m "feat(intel): wire project_id เข้า intel_lines (resolve_location)"`

---

### Task 6: backfill_location.py — งาน active เปิดอยู่

**Files:** Create `scripts/backfill_location.py`

- [ ] **Step 1: เขียนสคริปต์** (ไม่มี unit test — ops script; มี --dry-run + sanity)
```python
"""backfill_location.py — เติม raw location (district_moi_id/moi_name/lat-lng) ให้งานเป้าหมายที่
ยังเปิด + ยังไม่มี location. low-rate (INC-001). รันบนเครื่องที่ยิง API ได้. --dry-run ดูก่อน."""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import get_connection, save_project_location_raw
from process5_http_client import get_procurement_detail

SLEEP = 2.5   # INC-001 throughput envelope

def candidates(conn):
    return conn.execute("""
        SELECT pl.project_id FROM project_locations pl
        WHERE (pl.district_moi_id IS NULL OR pl.district_moi_id='')
          AND (pl.latitude IS NULL OR pl.latitude='')
          AND pl.qualification_status IN ('enqueued','suppressed_preview')
        LIMIT ?""", ((conn.execute("SELECT 999").fetchone()[0]),)).fetchall()

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT project_id FROM project_locations
            WHERE (district_moi_id IS NULL OR district_moi_id='')
              AND (latitude IS NULL OR latitude='')
            LIMIT ?""", (a.limit,)).fetchall()
    ids = [r[0] for r in rows]
    print(f"candidates: {len(ids)} (limit {a.limit})")
    if a.dry_run:
        print(ids[:20]); return 0
    ok = 0
    for i, pid in enumerate(ids):
        try:
            d = get_procurement_detail(pid)
            if d.get("valid") and (d.get("district_moi_id") or d.get("latitude")):
                save_project_location_raw(pid, d.get("district_moi_id") or "", d.get("moi_name") or "",
                                          d.get("latitude") or "", d.get("longitude") or "")
                ok += 1
                print(f"  [{i+1}/{len(ids)}] OK {pid} moi={d.get('moi_name')}")
        except Exception as e:
            print(f"  [{i+1}/{len(ids)}] ERR {pid}: {e}")
        time.sleep(SLEEP)
    print(f"✅ backfilled {ok}/{len(ids)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```
(หมายเหตุ: ตัด helper `candidates()` ที่ซ้ำออก — ใช้ query ใน main เท่านั้น)
- [ ] **Step 2: --dry-run บน VPS** (งานจริง) — ดู candidate count ก่อนยิงจริง
Run (VPS): `sudo -u bms BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python /opt/bms/app/scripts/backfill_location.py --dry-run --limit 50`
Expected: list project_id ที่ตามอยู่ (followed 4 + active)
- [ ] **Step 3: Commit** `git add scripts/backfill_location.py && git commit -m "feat(loc): backfill_location งาน active (low-rate, --dry-run)"`

---

### Task 7: Deploy + verify (ops)

- [ ] **Step 1:** `git push origin main` (เช็คด้วย ls-remote เผื่อ client timeout)
- [ ] **Step 2: VPS pull + backup** `ssh ... "cd /opt/bms/app && sudo -u bms git pull --ff-only && sudo -u bms cp /opt/bms/data/bms_customers.db /opt/bms/data/backups/pre_moidisambig_$(date +%Y%m%d_%H%M%S).db"`
- [ ] **Step 3: backfill จริง** (VPS, low-rate) `sudo -u bms ... backfill_location.py --limit 30` → ดู ok count
- [ ] **Step 4: Sanity** — intel ของงาน followed โชว์ระดับตำบล/อำเภอ (header "ต.X อ.Y") + trace ใน log
```bash
ssh ... "sudo -u bms BMS_DATA_DIR=/opt/bms/data BMS_ENV=prod /opt/bms/venv/bin/python -X utf8 -c \"
import sys; sys.path.insert(0,'/opt/bms/app/scripts'); import sqlite3, cgd_intel as ci
c=sqlite3.connect('/opt/bms/data/bms_customers.db')
# งาน followed ที่ backfill แล้ว
for pid, in c.execute('SELECT project_id FROM followed_jobs LIMIT 4'):
    r=c.execute('SELECT province_snapshot, project_name_snapshot, dept_name_snapshot FROM notification_queue WHERE project_id=? LIMIT 1',(pid,)).fetchone()
    if r:
        loc=ci.resolve_location(pid, r[1] or '', r[2] or '', r[0] or '', c)
        print(pid, '→', loc['source'], loc['amphoe'], loc['location_confidence'], loc['resolution_trace'])
\""
```
Expected: source=geo/tambon, amphoe ระบุได้ (ไม่ None) สำหรับงานที่ backfill สำเร็จ
- [ ] **Step 5:** update progress_log + memory + Discord

---

## Self-Review
- **Spec coverage:** capture+swap (T2) · resolve chain geo/tambon/dept/province + trace + confidence runtime (T3) · select(amphoe) (T4) · wire (T5) · backfill (T6) · reverse_geocode helper (T1) · deploy (T7). MOI ชั้น1/TIS = Phase B (ไม่อยู่ใน plan นี้ ตาม design) ✅
- **Persist raw only:** save_project_location_raw เขียนแค่ district_moi_id/moi_name/lat/lng; amphoe/confidence/trace = runtime ใน resolve_location ✅
- **Placeholder scan:** ไม่มี (โค้ดจริงทุก step; ร่างแรกของ resolve_location ที่มี pseudo ถูกแทนด้วยเวอร์ชันเต็มใน Task3 step3)
- **Type consistency:** resolve_location คืน dict {tambon,amphoe,location_confidence,source,resolution_trace} ใช้ตรงใน intel_lines · select_competitors(province,tokens,tambon,amphoe,conn) ตรงทุก caller/test · save_project_location_raw signature ตรง T2/T6 · reverse_geocode คืน (prov,amphoe,tambon,dist) ตรง
- **⚠️ verify ตอน execute:** (a) thai_geo_raw มี โพนทอง ทั้งบ้านแพง+เรณูนคร จริง (Task1 test จะ fail ทันทีถ้าไม่มี) (b) project_locations มี column qualification_status (backfill query) — เช็คก่อน หรือใช้ enrichment_status แทน
