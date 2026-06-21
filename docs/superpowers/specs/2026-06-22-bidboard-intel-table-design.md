# Bid Board — ตาราง win% เต็ม N + รายชื่อผู้รับเหมาคลิกได้

**วันที่:** 2026-06-22
**สถานะ:** design approved (รอ user review spec — แต่คุณกัญจน์สั่งให้ทำต่อจนเสร็จโดยไม่รอ)
**ขอบเขต:** ส่วนแสดงผลทำนายราคาในหน้า `/portal/job` (engine: `cgd_intel.py` + `bid_field.py`, เพิ่ม area-highlight ในหน้า `/portal/company` ที่มีอยู่แล้ว)

---

## 1. เป้าหมาย

ปัจจุบันหน้า `/portal/job` แสดงบล็อกวิเคราะห์ราคาเป็น **plain text lines** (escape แล้ว dump เป็น `<div>`) มี 2 ข้อจำกัดที่คุณกัญจน์อยากแก้:

1. **ตาราง win% ตามจำนวนผู้ยื่น** (`bid_field.winrate_lines`) โชว์แค่ 3 คอลัมน์ (mean−SD/mean/mean+SD ของจำนวนผู้ยื่นในอดีต) — อยากให้ไล่เต็ม N=1,2,3...จนถึง max ที่เคยเกิดจริงในสนามนี้ เพราะเว็บไม่มีข้อจำกัดความยาวข้อความเหมือน LINE
2. **รายชื่อบริษัทคู่แข่ง** (`cgd_intel._scope_block`) โชว์แค่ Top 3 ต่อ scope — อยากเห็นทุกบริษัทที่เอามาคำนวณ และกดชื่อแล้วไปดูประวัติบริษัทได้ (หน้า `/portal/company` มีอยู่แล้วจาก spec 2026-06-20)

**ข้อเข้าใจผิดที่แก้ไปแล้วก่อน brainstorm:** การทำนายราคาไม่ได้ใช้ mean±SD — ใช้ percentile (p25/p75/median) ถ่วงน้ำหนักความสดของส่วนลด% ในประวัติ. mean±SD ใช้แค่จุดเดียวคือ "เลือกว่าจะโชว์ตาราง win% ที่ N เท่าไหร่" (ใน `_center_stats`) — เป็นเรื่องการแสดงผล ไม่ใช่ตัวทำนายราคา

## 2. Success criteria (verifiable)

1. หน้า `/portal/job` ของงานที่มี grid ผ่าน gate (`MIN_AUCTIONS=5`, `ESS_FLOOR=6`) แสดงตาราง win% เป็น HTML `<table>` จริง คอลัมน์ N ไล่ตั้งแต่ 1 ถึง max ที่เคยเกิดในสนามนี้ (ไม่ตัด ไม่ cap)
2. แต่ละ scope block (ตำบล/อำเภอ) แสดงบริษัททุกตัวที่มี winner ใน `rows` ของ scope นั้น (ไม่จำกัด 3) เรียงจำนวนงานชนะมาก→น้อยเหมือนเดิม
3. บริษัทที่ resolve tin ได้ (มี record ใน `bid_results`) → ชื่อเป็นลิงก์ไป `/portal/company?...&tin=<tin>` ที่ใช้งานได้จริง; resolve ไม่ได้ → ชื่อเป็น text เทาไม่มีลิงก์ (ไม่ throw, ไม่ทำให้ตารางพัง)
4. กดลิงก์จากตาราง intel → หน้า `/portal/company` แสดง section "📍 ผลงานในพื้นที่นี้" ก่อน "📂 ผลงานทั้งหมด" เดิม โดยรายการในพื้นที่ตรงกับ `project_id` ที่มาจาก scope query เดียวกับที่ทำนายราคา (ไม่ใช่ fuzzy area-match ใหม่)
5. งานที่ grid/company list ไม่ผ่าน gate → ไม่มี error, fallback เหมือนเดิม (ไม่มีตาราง = ไม่แสดง section นั้น)
6. unit test ใหม่ใน `test_bid_field.py`, `test_cgd_intel.py`, `test_portal_views.py` PASS; Sophia SAFE ก่อน commit สุดท้าย

## 3. สถาปัตยกรรมที่เลือก (และทำไมไม่เลือกอย่างอื่น)

**ปัญหาหลัก:** `intel_lines` ปัจจุบันเป็น `list[str]` ที่ render เป็น `<div>` escape-แล้ว — ใส่ `<a>` ลิงก์จริงในนั้นไม่ได้ (escape ทับหมด) และ build `<table>` จาก string ดิบมันเปราะ

**ตัดสินใจ:** เปลี่ยนเฉพาะ 2 ส่วนที่ต้องการ table/ลิงก์ (รายชื่อบริษัท + win% grid) ให้เป็น **structured data** (`dict`/`list`) แทนข้อความ แล้วให้ `render_job_page()` (`portal_views.py`) เป็นคน build HTML เอง ส่วนอื่น (header scope, ป้ายความเชื่อมั่น, ราคาแนะนำ a/b/c, เจ้าตลาด 2B) **ไม่แตะ** ยังเป็น text lines เดิม — surgical change ตามที่ task ต้องการจริง ไม่ refactor ทั้งไฟล์

ทางเลือกที่ไม่เลือก: เปลี่ยน `intel_context()` ทั้งหมดเป็น fully-structured (ทุก field เป็น object) — ปฏิเสธเพราะเกินขอบเขตที่ขอ (ส่วนอื่นทำงานดีอยู่แล้ว ไม่มีเหตุต้องแตะ)

## 4. การเปลี่ยน `bid_field.py`

### 4.1 `_center_stats()` — ขยาย ns เป็นเต็ม range

ปัจจุบัน (`bid_field.py:54-71`) คำนวณ `n_mean`/`n_sd` แล้วเลือกแค่ 3 จุด `[mean-sd, mean, mean+sd]`. เปลี่ยนเป็น:

```python
ns = [1] + list(range(2, max(sizes) + 1))   # 1 พ่วงพิเศษ + 2..max จริงที่เคยเกิดใน scope นี้
```

(`sizes` เองยังกรอง `len(a)>=2` เหมือนเดิม — auction ที่มีผู้ยื่นแค่ 1 ไม่เคยถูกนับเป็น "การแข่ง" ในประวัติ ดังนั้น `max(sizes)` ไม่มีทางเป็น 1; **N=1 ใส่เองเสมอเป็นคอลัมน์แรกของตาราง** ไม่ใช่ค่าที่ derive จากประวัติ)

`k_mid` (ค่าอ้างอิงกลางสำหรับคำนวณ disc ที่ target win%) **ยังคงเป็น `round(n_mean)`** (ไม่ใช่ `ns[len(ns)//2]` แบบเดิม — ของเดิมใช้ตำแหน่งกลางของ list 3 ช่อง ซึ่งบังเอิญ≈mean; ตอนนี้ list ยาวขึ้นเป็น 1,2..max ตำแหน่งกลางไม่ใช่ mean แล้ว ต้องคำนวณ `round(n_mean)` ตรงๆ และ clamp ให้อยู่ใน `[2, max(sizes)]` — `n_mean` มาจาก `sizes` ที่ ≥2 อยู่แล้วจึงไม่หลุด range จริง)

**N=1 คือกรณีพิเศษ ไม่ผ่านสูตร `tf ** (N/k_mid) * 100`:** ยื่นคนเดียว = ไม่มีคู่แข่งให้แข่ง ชนะแน่นอน (สมมติราคาอยู่ในงบ) → win% ของคอลัมน์ N=1 **fix เป็น 100 ทุกแถวราคา** ไม่คำนวณจากสูตร (สูตรเดิมไม่ได้ลบตัวเองออกจาก N อยู่แล้วเป็น approximation ที่ยอมรับได้ตั้งแต่ N=2 ขึ้นไป แต่ที่ N=1 มันความหมายชัดเจนระดับ "นิยาม" ไม่ใช่ประมาณ จึง hardcode ให้ตรงความจริง)

หมายเหตุสูตรเดิมที่ N≥2 (ไม่เปลี่ยน, เป็น characteristic ที่รู้อยู่แล้วไม่ใช่บั๊กใหม่): `win%(N) = tf ** (N/k_mid) * 100` เป็น approximation (ไม่ได้ลบผู้ยื่นเองออกจาก N ตอนคิดโอกาสเป็นผู้ชนะสูงสุด) — ของเดิมเป็นแบบนี้อยู่แล้วตั้งแต่ตาราง 3 คอลัมน์ ไม่ใช่ปัญหาใหม่จากการขยาย range จึงไม่แก้ในงานนี้

**จุดที่ต้อง hardcode N=1:** อยู่ใน `_evaluate_winrate()` (`bid_field.py:147`) ที่ build `rows`:
```python
rows.append((price, [round(tf ** (k / k_mid) * 100) for k in ns]))
```
เปลี่ยนเป็น:
```python
rows.append((price, [100 if k == 1 else round(tf ** (k / k_mid) * 100) for k in ns]))
```

### 4.2 `field_and_winrate()` — คืน grid ดิบแทน text

ปัจจุบัน (`bid_field.py:329-354`) เรียก `winrate_lines()` แปลงเป็น text ก่อนคืนเป็น `_wl`. เปลี่ยนให้คืน **`grid` dict ดิบ** (ผลจาก `_evaluate_winrate`, มี `ns`/`rows`/`n_mean`/`n_sd`/`n_auctions`/`n_bids`/`k_mid`/`budget`) แทน — caller (`cgd_intel.py`) เป็นคนตัดสินใจว่าจะ render เป็น text (ไม่มี caller ไหนใช้แบบนี้ในโปรดักชันแล้ว เพราะ LINE ไม่โชว์ intel block อีกต่อไป) หรือ structured table (web — กรณีนี้)

`winrate_lines()` function **เก็บไว้เหมือนเดิม ไม่ลบ** — `test_bid_field.py`/`test_winrate_grid.py`/`_validate_winrate_tambon.py` ยังเรียกมันตรงๆ ได้ (pure function ของ grid, ไม่ผ่าน `field_and_winrate` แล้ว)

Signature ใหม่: `field_and_winrate(...) -> (grid: dict|None, field_lines: list, conf)` (เดิมตำแหน่งแรกคือ `winrate_lines text: list`)

## 5. การเปลี่ยน `cgd_intel.py`

### 5.1 `_scope_block()` — โชว์ทุกบริษัท + แนบ tin

`counts.most_common(SHOW_N)` (บรรทัด 436) → `counts.most_common()` (ไม่จำกัด) ลบค่าคงที่ `SHOW_N` (ไม่ใช้แล้ว)

**เอาบรรทัด bullet รายบริษัทออกจาก `lines`** (ของเดิมบรรทัด 440-449 ที่ append `f"  • {nm} · {cs['games']} งาน..."`) — ย้ายไปเป็น structured field แทน เพื่อไม่ให้ซ้ำซ้อนกับตารางใหม่ `lines` ของ `_scope_block` เหลือแค่ header (`"{label} — {n} งาน {conf_tag}"`) + บรรทัดสรุป p25-p75

`_scope_block()` คืนค่าเพิ่ม 1 ตัว: `companies: list[dict]` แต่ละตัว `{"name": str, "tin": str|None, "project_ids": [str,...], "games": int, "median": float|None, "p25": float|None, "p75": float|None}` — `project_ids` มาจาก `rows` ที่ `winner == name` ในตอนวนลูปอยู่แล้ว (เก็บเพิ่มตอนวน ไม่ queryใหม่)

`tin` resolve ผ่านฟังก์ชันใหม่ `_resolve_tin(conn, name) -> str|None` ใน `cgd_intel.py`:
```python
def _resolve_tin(conn, name):
    """หา bidder_tin จาก bid_results ที่ชื่อ normalized ตรงกับ name (cgd_winners.winner).
    ไม่เจอ → None (ไม่ throw — ทำให้ชื่อกลายเป็น text เทาแทนลิงก์)."""
    from portal_views import _norm_name, _prefilter_key
    core, key = _norm_name(name), _prefilter_key(name)
    if not core or not key:
        return None
    try:
        cand = conn.execute(
            "SELECT bidder_tin, bidder_name FROM bid_results WHERE bidder_name LIKE ?",
            (f"%{key}%",)).fetchall()
    except sqlite3.OperationalError:
        return None
    for r in cand:
        if _norm_name(r["bidder_name"]) == core and r["bidder_tin"]:
            return r["bidder_tin"]
    return None
```
import `portal_views` จาก `cgd_intel` (ทิศทางเดียว — `portal_views` ไม่ import `cgd_intel` กลับ ไม่มี circular import) เรียก `_resolve_tin` ครั้งเดียวต่อชื่อ ไม่ใช่ต่อแถว (cache ใน dict ระดับ `intel_context()` กันยิงซ้ำชื่อเดียวกันหลาย scope block)

### 5.2 `intel_context()` — ประกอบ structured fields ใหม่

คืนค่าเพิ่ม 2 key ใน dict ที่คืนจาก `intel_context()`:

- `"company_tables": list[dict]` — 1 รายการต่อ scope block ที่ถูกเรียก (`_scope_block`), แต่ละรายการ `{"label": str, "n": int, "conf_tag": str, "p25": float|None, "p75": float|None, "companies": [...]}`
- `"winrate_table": dict|None` — ถ้า `field_and_winrate()` คืน grid (ไม่ None): `{"ns": [...], "rows": [...], "n_mean", "n_sd", "n_auctions", "n_bids", "conf": None|(emoji,scope_word), "price_basis": str, "budget": float}`

จุดที่เคยแทรก `winrate_lines()` text เข้า `lines` (บรรทัด ~593-602 เดิม) **เอาออกจาก `lines`** — ย้าย logic การตัดสินใจ "🟢 local แทนที่ a/b/c" / "🟡🟠 assisted คงทั้งคู่" ไปคุมแค่ว่าจะ append `predict_lines(...)` (ราคา a/b/c text) เข้า `lines` หรือไม่ ส่วน `winrate_table` ถูก set เสมอเมื่อ grid ไม่ None (ไม่ขึ้นกับ conf — ตารางโชว์เสมอถ้ามีข้อมูลพอ, การที่ราคา a/b/c โชว์คู่หรือไม่ค่อยแยกตัดสินใจอีกที):

```python
_grid, _fl, _conf = _bf.field_and_winrate(conn, province, tokens, budget,
                                          scope_label=_lbl, basis=basis, project_ids=_ids,
                                          cf=cf, amphoe=amphoe)
if _grid and _conf is None:                      # 🟢 local → ตารางแทน a/b/c
    pass    # ไม่ append predict_lines — ตารางพอ
elif _grid:                                       # 🟡/🟠 assisted → คงราคา local + ตารางแยก (price sacred)
    lines += [""] + predict_lines(pred, basis, contested=contested_only)
else:                                              # ไม่มี grid → การ์ดเดิม
    lines += [""] + predict_lines(pred, basis, contested=contested_only)
winrate_table = None
if _grid:
    winrate_table = {**_grid, "conf": _conf, "price_basis": basis}
```
(field_lines `_fl` ยังคง append เข้า `lines` เหมือนเดิม — ไม่แตะ 2B เจ้าตลาด)

## 6. การเปลี่ยน `portal_views.py`

### 6.1 `job_detail()` — ส่ง structured fields ผ่าน

เพิ่ม `"company_tables": intel_ctx.get("company_tables", [])` และ `"winrate_table": intel_ctx.get("winrate_table")` เข้า dict ที่คืนจาก `job_detail()` (ปัจจุบันมีแค่ `intel_lines`)

### 6.2 `render_job_page()` — build `<table>` จริง

แทนที่ส่วน `if data.get("intel_lines"):` (บรรทัด 411-414 เดิม) เพิ่ม 2 ตารางใหม่หลัง intel_lines:

**ตารางบริษัท** (1 ต่อ scope block ใน `company_tables`):
```html
<div class="bidhead">🏘️ {label} — {n} งาน {conf_tag}</div>
<table class="cotbl">
  <tr><th>บริษัท</th><th>งาน</th><th>ลด</th></tr>
  <tr><td><a href="/portal/company?t=...&tin=...&from=<pid>&area_ids=...&area_label=...">ชื่อ</a></td><td>3</td><td>28% (25–31%)</td></tr>
  <tr><td><span class="notin">ชื่อ (ไม่มีโปรไฟล์)</span></td><td>1</td><td>19%</td></tr>
  ...
</table>
```
`tin` มี → `<a>`; `tin` None → `<span class="notin">` (CSS: สีเทา, ไม่ underline — ตรงตามที่เลือกไว้ตอน brainstorm) `area_ids` = `",".join(company["project_ids"])`, `area_label` = label ของ scope block นั้น (เช่น "ต.สมสนุก/อ.ปากคาด")

**ตาราง win%:**
```html
<div class="bidhead">💵 โอกาสชนะตามจำนวนผู้ยื่น (งบ {budget:,.0f})</div>
<table class="wrtbl">
  <tr><th>ราคา\N ผู้ยื่น</th><th>1</th><th>2</th>...<th>{max}</th></tr>
  <tr><td>{price:,.0f}</td><td>{w}%</td>...</tr>
  ...
</table>
<div class="meta">📊 สนามนี้เฉลี่ย {n_mean} ผู้ยื่น (±{n_sd}) · จาก {n_auctions} งาน · {n_bids} ราย</div>
```
ถ้า `conf` ไม่ None (🟡/🟠 assisted) เพิ่ม `<div class="meta">⚠️ ราคาด้านบนยังอิง{price_basis}</div>` เหมือน `winrate_lines()` เดิม (ย้าย disclaimer text มาที่นี่)

CSS ใหม่ (`<style>` block เดิมใน `_HEAD`): `.cotbl`/`.wrtbl` (border-collapse, padding, มือถือ-first scroll แนวนอนถ้าคอลัมน์เกินจอ — `overflow-x:auto` wrapper), `.notin{color:#999;}` ทุก cell ที่เป็น dynamic data ใช้ `_h.escape()`

### 6.3 `company_profile()` / `render_company_page()` — area highlight

เพิ่มฟังก์ชันใหม่ `area_portfolio(conn, name, project_ids)`:
```python
def area_portfolio(conn, name, project_ids):
    """ผลงานเฉพาะ project_id ที่ส่งมา (มาจาก scope query ของ cgd_intel ตรงๆ — ไม่ fuzzy area-match ใหม่).
    คืน [] ถ้า project_ids ว่างหรือไม่เจอ."""
    if not project_ids:
        return []
    placeholders = ",".join("?" * len(project_ids))
    rows = conn.execute(
        f"SELECT project_id, project_name, win_price, budget, fiscal_year "
        f"FROM cgd_winners WHERE project_id IN ({placeholders}) AND winner=?",
        (*project_ids, name)).fetchall()
    out = []
    for r in rows:
        disc = _discount(_to_float(r["win_price"]), (r["budget"] or 0))
        out.append({"pid": r["project_id"], "name": r["project_name"], "discount": disc,
                    "fy": r["fiscal_year"]})
    return out
```
route `/portal/company` รับ query param เพิ่ม `area_ids` (comma-sep) + `area_label` (str, optional) → `bms_api.py` parse แล้วส่งเข้า `area_portfolio(conn, data["name"], area_ids.split(","))`. **`name` ใช้ค่าจาก `company_profile()` ที่ resolve จาก tin แล้ว** (ไม่ใช้ชื่อจาก URL ตรงๆ — กัน injection/mismatch)

`render_company_page()` เพิ่ม section ก่อน "timeline แยกรายปี" เดิม:
```html
{% if area_jobs %}
<div class="bidhead">📍 ผลงานใน {area_label} ({len(area_jobs)} งาน)</div>
<div class="meta">• {name} · ลด {discount:.0f}% · ปีงบ {fy}</div>
...
{% endif %}
```

## 7. Edge cases

- บริษัทชื่อสั้นเกิน/ว่าง (`_norm_name` คืน `""`) → `_resolve_tin` คืน `None` ทันที (ไม่ query) → text เทา
- บริษัทเดียวกันโผล่ทั้ง 2 scope block (ตำบล+อำเภอ คู่กันตอน `TAMBON_MIN` gate) → แต่ละ block มี `companies` list ของตัวเอง (ไม่ dedupe ข้าม block — ตามที่ตัดสินไว้ว่าคงโครงสร้าง dual-block เดิม)
- `area_ids` ที่ส่งมาไม่มี project_id ไหนตรงกับ `cgd_winners` จริง (ข้อมูลเปลี่ยน/ลบ) → `area_portfolio` คืน `[]` → section "ผลงานในพื้นที่นี้" ไม่แสดง (ไม่ error)
- grid ไม่ผ่าน gate (`fail_reason` != OK) → `winrate_table = None` → ไม่มีตาราง win% (เหมือนพฤติกรรมเดิมที่ไม่มี `_wl`)
- `ns` มีแค่ 1 ค่า (`max(sizes)==2`, scope เล็กมาก) → ตาราง win% มีคอลัมน์เดียว (N=2) — ทำงานได้ปกติ ไม่ error
- คอลัมน์ N เยอะมาก (เช่น 20) → ตาราง wrtbl กว้างเกินจอมือถือ → wrapper `overflow-x:auto` ให้เลื่อนแนวนอนได้ (ไม่ตัด ไม่ cap — ตามที่ user ขอ "N สูงสุดจริงเท่าไหร่ก็ได้")

## 8. การทดสอบ

- `test_bid_field.py`: `_center_stats` คืน `ns` เต็ม `[1,2..max]` (ไม่ใช่ 3 จุด), `k_mid == round(n_mean)` clamp ใน `[2,max]`; `_evaluate_winrate` คืน `rows` ที่คอลัมน์ N=1 = 100 ทุกแถวราคา (ไม่ผ่านสูตร); `field_and_winrate` คืน grid dict (มี key `rows`/`ns`) ไม่ใช่ text list ที่ตำแหน่งแรก; `winrate_lines()`ยังทำงานได้แยกถ้าป้อน grid ตรงๆ (regression เดิม)
- `test_cgd_intel.py`: `_scope_block` คืน `companies` ครบทุกตัวใน `rows` (ไม่ตัด 3); `_resolve_tin` เจอ/ไม่เจอ (seed `bid_results` ชื่อตรง/ไม่ตรง); `intel_context()` มี key `company_tables`/`winrate_table`; `lines` ไม่มี bullet รายบริษัทซ้ำกับ structured data
- `test_portal_views.py`: `render_job_page` มี `<table class="cotbl">`/`<table class="wrtbl">` เมื่อมีข้อมูล, มี `<a href=".../portal/company?...">` เมื่อ tin มี, มี `<span class="notin">` เมื่อ tin ไม่มี, escape ทำงาน (ชื่อมี `<`/`&`); `area_portfolio` คืนผลงานตรงตาม project_ids ที่ส่งเข้าไป, ว่างเมื่อไม่เจอ; `render_company_page` มี section "ผลงานในพื้นที่นี้" เมื่อมี `area_jobs`, ไม่มีเมื่อไม่มี

## 9. Deployment

ไฟล์ที่แก้: `scripts/bid_field.py`, `scripts/cgd_intel.py`, `scripts/portal_views.py`, `scripts/bms_api.py` (route param เพิ่ม) — scp ทั้ง 4 ไฟล์ขึ้น VPS แล้ว `systemctl restart bms-api`. verify ด้วยงานจริงที่เคยมี intel ครบ (เช่นที่ resolve location สำเร็จ + มีคู่แข่งในตำบล) ก่อนถือว่าเสร็จ
