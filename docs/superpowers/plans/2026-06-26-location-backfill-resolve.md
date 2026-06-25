# Location Backfill + Forward Resolve — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / subagent-driven-development. Steps use checkbox tracking.

**Goal:** เติม `moi_name` (ตำบล) + พิกัดให้งาน province_api ที่ค้าง NULL (1,117 งาน) ผ่าน worker pass เดียวที่กวาดทั้งของเก่าและงานใหม่

**Architecture:** เพิ่ม pass `resolve_missing_locations()` ใน enrichment worker — selector จับ `source='province_api' AND moi_name IS NULL` → `get_procurement_detail` → save ตำบล/อำเภอ/พิกัด, fallback `tambon_from_dept`. batch เล็ก rate-disciplined, เสียบหลัง cooldown gate (INC-001). self-healing: งานใหม่ที่ moi ว่างถูกเก็บรอบถัดไปเอง.

**Tech Stack:** Python, SQLite, plain-assert test scripts (รันตรง ไม่ใช่ pytest)

## Global Constraints
- spec: `docs/superpowers/specs/2026-06-26-location-backfill-resolve-design.md`
- reuse (ห้ามเขียนซ้ำ): `save_project_location_raw(pid, district_moi_id, moi_name, latitude, longitude)` (Customer_DB:88, ไม่แตะ status), `tambon_from_dept(dept_name)->str` (job_matcher:135), `get_procurement_detail(pid)->dict` (process5_http_client), `_now()`/`_now_plus(min)`/`get_connection()`/`RETRY_DELAY_MIN=30` (worker)
- `get_procurement_detail` คืน keys: `valid, moi_name, district_moi_id, latitude, longitude`
- batch=`BMS_LOCFILL_BATCH` default 8 · stop หลัง `LOCFILL_MAX_ATTEMPTS=3` · sleep 1.5s/งาน
- ห้ามแตะ `enrichment_status` (province_api ='failed' placeholder — สถานะจริงใน qualification_status)
- ห้ามชน RSS pass (RSS เลือก `enrichment_status='pending'`; province_api='failed' จึงไม่ชน) — ใช้ `enrichment_attempts` เป็น locfill counter ได้

---

## Task 1: `resolve_missing_locations()` core + tests

**Files:**
- Modify: `scripts/Sebastian_Enrichment_Worker.py` (เพิ่ม constants + `_bump_locfill_retry` + `resolve_missing_locations`)
- Test: `scripts/test_resolve_missing_locations.py` (สร้างใหม่)

**Interfaces — Produces:**
- `resolve_missing_locations(log, resolve_detail=None, sleep_sec=1.5) -> int` (คืนจำนวนที่เติม moi สำเร็จ)
- `_bump_locfill_retry(project_id: str) -> None`
- consts `LOCFILL_BATCH`, `LOCFILL_MAX_ATTEMPTS=3`

- [ ] **Step 1: เขียน test ที่ fail**

สร้าง `scripts/test_resolve_missing_locations.py`:
```python
"""test_resolve_missing_locations.py — locfill pass: เติม moi จาก detail/dept, retry, selector."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_ENV"] = "dev"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import Sebastian_Enrichment_Worker as w

def seed(pid, moi=None, attempts=0, source="province_api", dept="", retry=None):
    with db.get_connection() as c:
        c.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name,dept_name) "
                  "VALUES (?,?,?,?,?,?,?)", (pid,"D0","นครพนม","province_api","2026-06-01","งาน "+pid,dept))
        c.execute("INSERT INTO project_locations (project_id,province_name,moi_name,source,enrichment_status,need_location,enrichment_attempts,next_retry_at,created_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (pid,"นครพนม",moi,source,"failed",0,attempts,retry,"2026-06-01"))

def moi_of(pid):
    with db.get_connection() as c:
        r=c.execute("SELECT moi_name,district_moi_id,latitude,enrichment_attempts FROM project_locations WHERE project_id=?",(pid,)).fetchone()
    return r  # (moi, district, lat, attempts)

# งานทั้งหมด
seed("A")  # มี moi จาก detail
seed("B", dept="องค์การบริหารส่วนตำบลโพนแพง")  # detail ไม่มี moi → dept fallback
seed("C", dept="แขวงทางหลวงนครพนม")  # ไม่มีทั้งคู่ → attempt+1
seed("D", attempts=3)  # เกิน max → ไม่แตะ
seed("E", moi="มีแล้ว")  # moi เต็ม → ข้าม
seed("F", source="rss")  # RSS → ข้าม

def fake_detail(pid):
    if pid=="A": return {"valid":True,"moi_name":"นาทม","district_moi_id":"481100","latitude":"17.85","longitude":"104.02"}
    if pid=="D": return {"valid":True,"moi_name":"ไม่ควรเซฟ","district_moi_id":"x","latitude":"","longitude":""}
    return {"valid":False}  # B,C (และ F/E ไม่ถูกเรียกอยู่แล้ว)

n = w.resolve_missing_locations(lambda m: None, resolve_detail=fake_detail, sleep_sec=0)

# A: detail moi
a=moi_of("A"); assert a[0]=="นาทม" and a[1]=="481100" and a[2]=="17.85", a
# B: dept fallback
assert moi_of("B")[0]=="โพนแพง", moi_of("B")
# C: ไม่ได้ → attempt+1, moi ยัง NULL
cc=moi_of("C"); assert cc[0] is None and cc[3]==1, cc
# D: เกิน max → ไม่ถูกประมวลผล (moi ยัง NULL, attempts ยัง 3)
dd=moi_of("D"); assert dd[0] is None and dd[3]==3, dd
# E: moi เต็ม → ไม่เปลี่ยน
assert moi_of("E")[0]=="มีแล้ว"
# F: RSS → ไม่แตะ
assert moi_of("F")[0] is None
# คืนจำนวน resolve สำเร็จ = A,B = 2
assert n==2, n
print("✅ ALL PASS test_resolve_missing_locations")
```

- [ ] **Step 2: รัน test ดูว่า fail**

Run: `python scripts/test_resolve_missing_locations.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'resolve_missing_locations'`

- [ ] **Step 3: implement**

ใน `scripts/Sebastian_Enrichment_Worker.py` หลังบล็อก constants (ใกล้บรรทัด 46 `PROVINCE_QUAL_BATCH`) เพิ่ม:
```python
LOCFILL_BATCH        = int(os.environ.get("BMS_LOCFILL_BATCH", "8"))  # location backfill/resolve
LOCFILL_MAX_ATTEMPTS = 3
```
แล้วเพิ่ม 2 ฟังก์ชัน (วางใกล้ `qualify_province_api`, ก่อน `def main`):
```python
def _bump_locfill_retry(project_id: str) -> None:
    """locfill: เพิ่ม attempt + ตั้ง backoff (ไม่แตะ enrichment_status)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_locations SET enrichment_attempts=enrichment_attempts+1, next_retry_at=? "
            "WHERE project_id=?", (_now_plus(RETRY_DELAY_MIN), project_id))


def resolve_missing_locations(log, resolve_detail=None, sleep_sec: float = 1.5) -> int:
    """เติม moi_name (ตำบล)+พิกัด ให้งาน province_api ที่ค้าง NULL (backfill + งานใหม่, self-healing).
    resolve_detail(pid)->dict = get_procurement_detail (inject ได้เพื่อ test). คืนจำนวนที่เติมสำเร็จ."""
    if resolve_detail is None:
        from process5_http_client import get_procurement_detail
        resolve_detail = get_procurement_detail
    import job_matcher as jm
    now = _now()
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute("""
            SELECT pl.project_id, ps.dept_name
            FROM project_locations pl
            LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE pl.source='province_api' AND pl.moi_name IS NULL
              AND pl.enrichment_attempts < ?
              AND (pl.next_retry_at IS NULL OR pl.next_retry_at <= ?)
            ORDER BY pl.enrichment_attempts ASC, pl.created_at ASC
            LIMIT ?
        """, (LOCFILL_MAX_ATTEMPTS, now, LOCFILL_BATCH)).fetchall()]
    resolved = 0
    for r in rows:
        pid = r["project_id"]
        try:
            d = resolve_detail(pid) or {}
        except Exception as e:
            log(f"  locfill {pid} error: {type(e).__name__}: {e}")
            _bump_locfill_retry(pid)
            if sleep_sec:
                time.sleep(sleep_sec)
            continue
        moi = (d.get("moi_name") or "").strip() if d.get("valid") else ""
        if moi:
            save_project_location_raw(pid, d.get("district_moi_id") or "", moi,
                                      d.get("latitude") or "", d.get("longitude") or "")
            resolved += 1
            log(f"  📍 locfill {pid} → ต.{moi} (coord={bool(d.get('latitude'))})")
        else:
            tb = jm.tambon_from_dept(r.get("dept_name") or "")
            if tb:
                save_project_location_raw(pid, "", tb, "", "")
                resolved += 1
                log(f"  📍 locfill {pid} → ต.{tb} (dept fallback)")
            else:
                _bump_locfill_retry(pid)
        if sleep_sec:
            time.sleep(sleep_sec)
    return resolved
```
ตรวจ import ที่หัวไฟล์มี `time`, `save_project_location_raw`, `_now`, `_now_plus`, `get_connection`, `RETRY_DELAY_MIN` แล้ว (worker ใช้อยู่). ถ้า `time` ยังไม่ import ให้เพิ่ม `import time`.

- [ ] **Step 4: รัน test ดูว่า pass**

Run: `python scripts/test_resolve_missing_locations.py`
Expected: `✅ ALL PASS test_resolve_missing_locations`

- [ ] **Step 5: commit**

```bash
git add scripts/Sebastian_Enrichment_Worker.py scripts/test_resolve_missing_locations.py
git commit -m "feat(enrich): resolve_missing_locations — เติมตำบล/พิกัด province_api (backfill+forward) — Task 1/2"
```

---

## Task 2: เสียบเข้า `main()` หลัง cooldown gate

**Files:**
- Modify: `scripts/Sebastian_Enrichment_Worker.py` (`main()` หลังบล็อก cooldown check บรรทัด ~597-602)

**Interfaces — Consumes:** `resolve_missing_locations(log)` (Task 1)

- [ ] **Step 1: เพิ่มการเรียกใน main()**

ใน `main()` หลังบล็อก:
```python
    in_cd, until = _resolve_in_cooldown()
    if in_cd:
        log(f"Cooldown set by Pass 3 (until {until}) — skip RSS passes")
        _write_resolve_heartbeat("skip_cooldown_pass3", resolved_ok=qual_ok, in_cooldown=True)
        log("=== Enrichment Worker done (cooldown set) ===")
        return
```
(บรรทัด ~597-602 — จุดนี้รับประกันว่า **ไม่ cooldown** แล้ว = เคารพ gate INC-001) เพิ่มต่อทันที:
```python
    # Location backfill/resolve (province_api ที่ moi ว่าง) — rate-disciplined, หลัง cooldown gate
    try:
        nfill = resolve_missing_locations(log)
        if nfill:
            log(f"Location resolve: เติมตำบล/พิกัด {nfill} งาน")
    except Exception as e:
        log(f"Location resolve ERROR: {type(e).__name__}: {e}")
```

- [ ] **Step 2: ตรวจ syntax + ลำดับ (วางหลัง cooldown early-return จริง)**

Run: `python -c "import py_compile; py_compile.compile('scripts/Sebastian_Enrichment_Worker.py', doraise=True); print('ok')"`
Expected: `ok`
ตรวจด้วยตา: บล็อกใหม่อยู่ **หลัง** `return` ของ cooldown check (บรรทัด ~602) และ **ก่อน** `# Take batch of pending items` (บรรทัด ~604)

- [ ] **Step 3: รัน test เดิมซ้ำ (ยังเขียว)**

Run: `python scripts/test_resolve_missing_locations.py`
Expected: `✅ ALL PASS`

- [ ] **Step 4: commit**

```bash
git add scripts/Sebastian_Enrichment_Worker.py
git commit -m "feat(enrich): เสียบ location resolve เข้า worker main หลัง cooldown gate — Task 2/2"
```

---

## Deploy + verify (หลัง 2 task ผ่าน + Sophia SAFE)
1. push → VPS `bash scripts/deploy.sh` (ff-pull + restart bms-api; worker timer ใช้โค้ดใหม่รอบถัดไป)
2. รัน test บน venv prod: `BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python scripts/test_resolve_missing_locations.py`
3. ดู worker log รอบถัดไป: เห็น `📍 locfill ... → ต.X`
4. ตรวจ drain: `SELECT COUNT(*) FROM project_locations WHERE source='province_api' AND moi_name IS NULL` ลดลงเรื่อยๆ
5. board: `69069203920` แสดง "ต.นาทม จ.นครพนม"

## Self-review
- spec coverage: Task 1 = resolve+fallback+retry+selector (ครบ 6 test cases ในตาราง spec ยกเว้น cooldown ซึ่งเป็น placement-level → Task 2 step 2 ตรวจด้วยตา) · Task 2 = wiring+cooldown gate via placement
- placeholder: ไม่มี
- type consistency: `resolve_missing_locations(log, resolve_detail, sleep_sec)` ตรงกันทั้ง 2 task; `save_project_location_raw` signature ตรง Customer_DB:88
