# D0 Notification → Bid Board Job Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline competitive-intel text block in the D0 ("new job") LINE notification with a short link to that job's page on the BMS Bid Board, and render the same intel content there instead.

**Architecture:** `Sebastian_LINE_Sender.py::format_notification()` stops inlining `cgd_intel.intel_context()["lines"]` and instead emits one link line built by a new `build_job_link()` (mirrors the existing `build_follow_link()` token pattern). `portal_views.py::job_detail()` gains the same `cgd_intel.intel_context()` call (reusing the open DB connection) and attaches the result as `data["intel_lines"]`; `render_job_page()` renders it as a new section. No DB schema changes.

**Tech Stack:** Python 3, sqlite3, existing `follow_token` HMAC token module, plain-script test style (no pytest — `assert` + `print("OK ...")`, run via `python scripts/test_X.py`).

## Global Constraints

- Spec source of truth: `docs/superpowers/specs/2026-06-21-d0-notification-job-link-design.md`
- Scope is the D0 card only (`announce_type == "D0"`) — do not touch PRELIM/W0 notification formats.
- The `cgd_intel.intel_context()["prediction"]` → `save_prediction()` closed-loop logging must keep firing exactly where it does today (on notification dispatch) — never call it from the portal page render path.
- Do not modify `cgd_intel.py` internals (price/win% calculation logic is out of scope and high-risk per the spec).
- Any new value-add computation (intel resolution) must be wrapped so failure degrades gracefully (no crash, no missing section) — follow the existing `try/except Exception` pattern already used in this codebase for the same purpose.
- Test style: standalone script, top-level `assert` statements (or test-named functions called from `if __name__ == "__main__":` block — match whichever style the target file already uses), `print("OK ...")` on success, run with `python scripts/test_<name>.py` and confirm exit code 0 / expected stdout.
- Thai-text emoji header lines must round-trip through `sys.stdout.reconfigure(encoding="utf-8")` (already present in every touched test file — do not remove it).

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/Sebastian_LINE_Sender.py` | Modify: add `build_job_link()`, modify `format_notification()` (new param + body change), modify the production call site. |
| `scripts/test_job_link.py` | Create: unit test for `build_job_link()` (mirrors `scripts/test_follow_link.py`). |
| `scripts/test_cgd_intel.py` | Modify: update `test_wiring_format_notification()` for the new output shape. |
| `scripts/portal_views.py` | Modify: `job_detail()` gains `intel_lines`; `render_job_page()` renders it. |
| `scripts/test_portal_views.py` | Modify: add test cases for `job_detail()` intel wiring and `render_job_page()` intel section. |

---

### Task 1: `build_job_link()` in Sebastian_LINE_Sender.py

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (insert after `build_follow_link`, currently ending at line 345)
- Test: `scripts/test_job_link.py` (new)

**Interfaces:**
- Produces: `build_job_link(line_user_id: str, project_id: str) -> str` — returns a signed-token URL `"{PUBLIC_BASE_URL}/portal/job?t={token}&pid={project_id}"`, or `""` if token minting fails. Used by Task 2.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_job_link.py`:

```python
"""test_job_link.py — sender build_job_link มินต์ token ที่ bms_api verify ได้ (ลิงก์ไปหน้า /portal/job)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_FOLLOW_SECRET"] = "test-secret-123"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

import Sebastian_LINE_Sender as snd
import follow_token as ft

url = snd.build_job_link("Uabc", "P1")
assert url.startswith("https://api.butler-bms.com/portal/job?t="), url
assert url.endswith("&pid=P1"), url
tok = url.split("t=", 1)[1].split("&pid=", 1)[0]
v = ft.verify_token(tok, secret="test-secret-123")
assert v is not None and v[0] == "Uabc" and v[1] == "P1", v

# exception path: make_token raises → build_job_link returns "" (ห้าม NameError/throw)
_orig = ft.make_token
def _boom(*a, **k):
    raise RuntimeError("forced")
snd.follow_token.make_token = _boom
try:
    assert snd.build_job_link("Uabc", "P1") == "", "build_job_link must return '' on token error"
finally:
    snd.follow_token.make_token = _orig

print("OK test_job_link")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_job_link.py`
Expected: `AttributeError: module 'Sebastian_LINE_Sender' has no attribute 'build_job_link'`

- [ ] **Step 3: Implement `build_job_link()`**

In `scripts/Sebastian_LINE_Sender.py`, immediately after `build_follow_link` (the function currently spanning lines 338-345, ending with the `return ""` line), insert:

```python
def build_job_link(line_user_id: str, project_id: str) -> str:
    """ลิงก์ไปหน้า job detail บน Bid Board (signed token, ต่อคน-ต่องาน). คืน '' ถ้า make_token พลาด (ห้ามทำ D0 พัง)."""
    try:
        return PUBLIC_BASE_URL.rstrip("/") + "/portal/job?t=" + \
            follow_token.make_token(line_user_id, project_id) + "&pid=" + project_id
    except Exception as e:
        print(f"[build_job_link] follow_token error (ส่งต่อไม่มีลิงก์): {e}", file=sys.stderr)
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_job_link.py`
Expected: `OK test_job_link`

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/test_job_link.py
git commit -m "feat(line): add build_job_link for Bid Board deep links"
```

---

### Task 2: Wire `format_notification()` to emit the job link instead of inline intel

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (signature at lines 231-237, intel block at lines 292-306, call site at lines 835-848)
- Modify: `scripts/test_cgd_intel.py` (`test_wiring_format_notification`, lines 363-385)

**Interfaces:**
- Consumes: `build_job_link(line_user_id, project_id) -> str` (Task 1).
- Produces: `format_notification(..., line_user_id: str = "") -> str` — new optional trailing parameter. Existing callers that omit it are unaffected (link line simply omitted).

- [ ] **Step 1: Update the existing test to assert the new behavior (write failing test)**

In `scripts/test_cgd_intel.py`, add `import os` to the line-2 import statement and set the follow-link secret right after the `sys.path.insert` line (needed because `format_notification` will now call `build_job_link`, which needs `BMS_FOLLOW_SECRET` to mint a token). Change:

```python
import sys, sqlite3, csv; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci
```

to:

```python
import os, sys, sqlite3, csv; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("BMS_FOLLOW_SECRET", "test-secret-cgd-intel")
import cgd_intel as ci
```

Then replace the entire `test_wiring_format_notification` function body with:

```python
def test_wiring_format_notification():
    import Sebastian_LINE_Sender as ls
    import cgd_intel as _ci
    orig_ctx = _ci.intel_context
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 TEST INTEL", "🏘 ในตำบล"], "prediction": None}
    txt = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                 source_stage="followed_bid_open", line_user_id="Uabc")
    # บล็อกวิเคราะห์เต็มย้ายไปหน้า Bid Board แล้ว — ไม่ฝัง text ในข้อความอีก
    assert "💡 TEST INTEL" not in txt and "━" not in txt, txt
    assert "🔑 P1" in txt, txt
    assert "ดูวิเคราะห์ราคา+คู่แข่งบน Bid Board" in txt, txt
    assert "/portal/job?t=" in txt and "pid=P1" in txt, txt
    # ไม่มี line_user_id → ไม่มีลิงก์ (ไม่ error)
    txt_nouser = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                        source_stage="followed_bid_open")
    assert "Bid Board" not in txt_nouser, txt_nouser
    _ci.intel_context = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    txt2 = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="followed_bid_open", line_user_id="Uabc")
    assert "🔑 P1" in txt2 and "💡" not in txt2 and "Bid Board" not in txt2, txt2
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 SHOULD NOT APPEAR"], "prediction": None}
    txt3 = ls.format_notification("P2", province="นครพนม", project_name="ก่อสร้างถนน",
                                  announce_type="B0", source_stage="province_tor_review", line_user_id="Uabc")
    assert "💡" not in txt3 and "Bid Board" not in txt3, txt3   # non-D0 (B0) → ไม่มี intel/link เลย
    # D0 ที่ยังไม่ได้ติดตาม (เจอใหม่) → ต้องมีลิงก์ + หัวข้อ "พบงานเปิดกำหนดวันยื่นซอง"
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 NEW D0 INTEL"], "prediction": None}
    txt4 = ls.format_notification("P3", province="นครพนม", project_name="ก่อสร้างถนน",
                                  announce_type="D0", source_stage="province_qualified", line_user_id="Uabc")
    assert "💡 NEW D0 INTEL" not in txt4, txt4
    assert "Bid Board" in txt4 and "pid=P3" in txt4, txt4
    assert "พบงานเปิดกำหนดวันยื่นซอง" in txt4, txt4
    _ci.intel_context = orig_ctx
    print("✅ wiring format_notification (D0 ทุก stage, ลิงก์ Bid Board แทน intel inline)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_cgd_intel.py`
Expected: `AssertionError` on the `assert "💡 TEST INTEL" not in txt` line (current code still inlines the intel block, so the old text is present and the new link text is absent).

- [ ] **Step 3: Update `format_notification()` signature and body**

In `scripts/Sebastian_LINE_Sender.py`, change the signature (currently lines 231-237):

```python
def format_notification(project_id: str, province: str = "",
                         announce_type: str = "D0", budget: float = 0,
                         project_name: str = "", dept_name: str = "",
                         deliver_day: int = 0, report_date: str = "",
                         bid_submit_date: str = "", bid_submit_time: str = "",
                         is_backfill: bool = False,
                         source_stage: str = "api_enriched") -> str:
```

to:

```python
def format_notification(project_id: str, province: str = "",
                         announce_type: str = "D0", budget: float = 0,
                         project_name: str = "", dept_name: str = "",
                         deliver_day: int = 0, report_date: str = "",
                         bid_submit_date: str = "", bid_submit_time: str = "",
                         is_backfill: bool = False,
                         source_stage: str = "api_enriched",
                         line_user_id: str = "") -> str:
```

Then replace the intel block (currently lines 292-306):

```python
    # competitive intel block (resolve ไว้ข้างบนแล้ว — เฉพาะการ์ดเปิดประมูล D0)
    if intel_ctx:
        lines.append("━━━━━━━━━━━━━")
        lines.extend(intel_ctx["lines"])
        if intel_ctx.get("prediction") and project_id:   # เก็บคำทำนายไว้เทียบตอนประกาศผล (closed-loop)
            try:
                from Sebastian_Customer_DB import save_prediction
                _pp = {"project_id": project_id, **intel_ctx["prediction"]}
                if intel_ctx.get("explain") is not None:
                    import json as _json
                    _pp["explain_json"] = _json.dumps(intel_ctx["explain"], ensure_ascii=False)
                save_prediction(_pp)
            except Exception:
                pass
```

with:

```python
    # competitive intel — closed-loop prediction logging ยังทำเหมือนเดิม (resolve ไว้ข้างบนแล้ว)
    if intel_ctx:
        if intel_ctx.get("prediction") and project_id:   # เก็บคำทำนายไว้เทียบตอนประกาศผล (closed-loop)
            try:
                from Sebastian_Customer_DB import save_prediction
                _pp = {"project_id": project_id, **intel_ctx["prediction"]}
                if intel_ctx.get("explain") is not None:
                    import json as _json
                    _pp["explain_json"] = _json.dumps(intel_ctx["explain"], ensure_ascii=False)
                save_prediction(_pp)
            except Exception:
                pass
        # บล็อกวิเคราะห์เต็ม ย้ายไปแสดงใน Bid Board แทน (อ่านง่ายกว่า + ใส่รายละเอียดเชิงลึกได้มากขึ้น)
        if line_user_id and project_id:
            link = build_job_link(line_user_id, project_id)
            if link:
                lines.append(f"🔍 ดูวิเคราะห์ราคา+คู่แข่งบน Bid Board: {link}")
```

- [ ] **Step 4: Update the production call site**

In `scripts/Sebastian_LINE_Sender.py`, the call at lines 835-848 currently reads:

```python
    text = format_notification(
        project_id      = item["project_id"],
        province        = item.get("province") or "",
        announce_type   = item.get("announce_type") or "D0",
        budget          = budget,
        project_name    = item.get("project_name") or "",
        dept_name       = dept_name,
        deliver_day     = deliver_day,
        report_date     = report_date,
        bid_submit_date = bid_submit_date,
        bid_submit_time = bid_submit_time,
        is_backfill     = bool(item.get("is_backfill")),
        source_stage    = item.get("source_stage") or "api_enriched",
    )
```

Add `line_user_id` as the last keyword argument:

```python
    text = format_notification(
        project_id      = item["project_id"],
        province        = item.get("province") or "",
        announce_type   = item.get("announce_type") or "D0",
        budget          = budget,
        project_name    = item.get("project_name") or "",
        dept_name       = dept_name,
        deliver_day     = deliver_day,
        report_date     = report_date,
        bid_submit_date = bid_submit_date,
        bid_submit_time = bid_submit_time,
        is_backfill     = bool(item.get("is_backfill")),
        source_stage    = item.get("source_stage") or "api_enriched",
        line_user_id    = item["line_user_id"],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python scripts/test_cgd_intel.py`
Expected: last line of output is `ALL PASS (moi location disambiguation)` (the file's existing `if __name__ == "__main__":` block runs every test function in order; no assertion errors).

- [ ] **Step 6: Run the Task 1 test again to confirm no regression**

Run: `python scripts/test_job_link.py`
Expected: `OK test_job_link`

- [ ] **Step 7: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/test_cgd_intel.py
git commit -m "feat(line): D0 card links to Bid Board instead of inlining competitive intel"
```

---

### Task 3: `portal_views.job_detail()` resolves and attaches `intel_lines`

**Files:**
- Modify: `scripts/portal_views.py` (`job_detail`, currently lines 62-108)
- Test: `scripts/test_portal_views.py` (append new cases)

**Interfaces:**
- Consumes: `cgd_intel.intel_context(province, project_name, dept_name, project_id, budget, conn) -> dict | None` (existing function, unmodified — returns `{"lines": [...], "prediction": ..., ...}` or `None`).
- Produces: `job_detail(conn, pid)` return dict gains a new top-level key `intel_lines: list[str] | None` (sibling of `"job"` and `"bidders"`). Used by Task 4.

- [ ] **Step 1: Write the failing tests**

In `scripts/test_portal_views.py`, insert the following block right after the existing line `print("OK render_job_page_star")` (currently the last test block before the final `print("OK test_portal_views")`):

```python
# --- job_detail: intel_lines (cgd_intel wiring — value-add, must degrade gracefully) ---
import cgd_intel
_orig_intel_context = cgd_intel.intel_context

cgd_intel.intel_context = lambda *a, **k: {"lines": ["💡 ราคาอ้างอิง ทดสอบ", "🏆 คู่แข่งหลัก ทดสอบ"]}
try:
    c = _seed()
    d = pv.job_detail(c, "69010000001")
    assert d["intel_lines"] == ["💡 ราคาอ้างอิง ทดสอบ", "🏆 คู่แข่งหลัก ทดสอบ"], d["intel_lines"]
finally:
    cgd_intel.intel_context = _orig_intel_context
print("OK job_detail_intel_lines_present")

cgd_intel.intel_context = lambda *a, **k: None
try:
    c = _seed()
    d = pv.job_detail(c, "69010000001")
    assert d["intel_lines"] is None, d["intel_lines"]
finally:
    cgd_intel.intel_context = _orig_intel_context
print("OK job_detail_intel_lines_none")

def _raise_intel(*a, **k):
    raise RuntimeError("boom")
cgd_intel.intel_context = _raise_intel
try:
    c = _seed()
    d = pv.job_detail(c, "69010000001")
    assert d["intel_lines"] is None, d["intel_lines"]
finally:
    cgd_intel.intel_context = _orig_intel_context
print("OK job_detail_intel_lines_error_safe")

# dept_name (when the column exists) must reach cgd_intel.intel_context as the 3rd positional arg
captured = {}
def _capture_intel(province, project_name, dept_name, project_id, budget, conn=None):
    captured["dept_name"] = dept_name
    return None
cgd_intel.intel_context = _capture_intel
try:
    c = _seed()
    c.execute("ALTER TABLE projects_seen ADD COLUMN dept_name TEXT")
    c.execute("UPDATE projects_seen SET dept_name='อบต.ทดสอบ' WHERE project_id='69010000001'")
    pv.job_detail(c, "69010000001")
finally:
    cgd_intel.intel_context = _orig_intel_context
assert captured["dept_name"] == "อบต.ทดสอบ", captured
print("OK job_detail_dept_name_passthrough")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_portal_views.py`
Expected: `AssertionError` on `assert d["intel_lines"] == [...]` — `d["intel_lines"]` raises `KeyError` (key does not exist yet), since `job_detail` does not return that key yet. (If your Python raises `KeyError` instead of hitting the `assert`, that is the expected failure too — either way the run must fail before Step 3.)

- [ ] **Step 3: Implement `intel_lines` in `job_detail()`**

In `scripts/portal_views.py`, the current `job_detail` function (lines 62-108) reads:

```python
def job_detail(conn, pid):
    ps = conn.execute(
        "SELECT project_name, budget, province FROM projects_seen WHERE project_id=?",
        (pid,)).fetchone()
    rows = conn.execute(
        "SELECT bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme "
        "FROM bid_results WHERE project_id=?", (pid,)).fetchall()
    if not rows and not ps:
        return None
    budget = (ps["budget"] if ps else 0) or 0
    loc, deadline = "", None
```

Insert the `dept_name` lookup and `intel_lines` resolution between the `budget = ...` line and the `loc, deadline = "", None` line:

```python
def job_detail(conn, pid):
    ps = conn.execute(
        "SELECT project_name, budget, province FROM projects_seen WHERE project_id=?",
        (pid,)).fetchone()
    rows = conn.execute(
        "SELECT bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme "
        "FROM bid_results WHERE project_id=?", (pid,)).fetchall()
    if not rows and not ps:
        return None
    budget = (ps["budget"] if ps else 0) or 0
    dept_name = ""
    try:
        dn = conn.execute(
            "SELECT dept_name FROM projects_seen WHERE project_id=?", (pid,)).fetchone()
        if dn and "dept_name" in dn.keys():
            dept_name = dn["dept_name"] or ""
    except sqlite3.OperationalError:
        dept_name = ""
    intel_lines = None
    try:
        import cgd_intel
        intel_ctx = cgd_intel.intel_context(
            (ps["province"] if ps else "") or "", (ps["project_name"] if ps else "") or "",
            dept_name, pid, budget, conn)
        if intel_ctx:
            intel_lines = intel_ctx["lines"]
    except Exception:
        intel_lines = None
    loc, deadline = "", None
```

Then change the function's final `return` statement from:

```python
    return {"job": {"project_id": pid, "name": (ps["project_name"] if ps else "") or pid,
                    "location": loc, "budget": budget, "deadline": deadline,
                    "pred_lo": pred_lo, "pred_hi": pred_hi}, "bidders": bidders}
```

to:

```python
    return {"job": {"project_id": pid, "name": (ps["project_name"] if ps else "") or pid,
                    "location": loc, "budget": budget, "deadline": deadline,
                    "pred_lo": pred_lo, "pred_hi": pred_hi}, "bidders": bidders,
            "intel_lines": intel_lines}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_portal_views.py`
Expected: output includes `OK job_detail_intel_lines_present`, `OK job_detail_intel_lines_none`, `OK job_detail_intel_lines_error_safe`, `OK job_detail_dept_name_passthrough`, and ends with `OK test_portal_views` (no assertion errors anywhere — confirms the pre-existing tests in this file, including the ones using `_seed()` fixtures without a `dept_name` column, still pass).

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): job_detail resolves cgd_intel lines into intel_lines"
```

---

### Task 4: `render_job_page()` renders the intel section

**Files:**
- Modify: `scripts/portal_views.py` (`render_job_page`, currently lines 369-413)
- Test: `scripts/test_portal_views.py` (append new cases)

**Interfaces:**
- Consumes: `data["intel_lines"]: list[str] | None` (Task 3).
- Produces: when `data["intel_lines"]` is truthy, the returned HTML contains a `<div class="bidhead">📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่</div>` section followed by one `<div class="meta">` per line (HTML-escaped). When falsy, no such section appears.

- [ ] **Step 1: Write the failing test**

In `scripts/test_portal_views.py`, append (after the Task 3 test block, before the final `print("OK test_portal_views")`):

```python
# --- render_job_page: intel section (📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่) ---
c = _seed()
d = pv.job_detail(c, "69010000001")
d["intel_lines"] = ["💡 ราคาอ้างอิง ทดสอบ", "🏆 คู่แข่งหลัก ทดสอบ"]
h = pv.render_job_page(d, "TOK", 0)
assert "📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่" in h, h
assert "💡 ราคาอ้างอิง ทดสอบ" in h and "🏆 คู่แข่งหลัก ทดสอบ" in h, h
# ลำดับ: section นี้ต้องอยู่ก่อนรายชื่อผู้ยื่นจริง
assert h.index("📊 วิเคราะห์ราคา") < h.index("ผู้ยื่นทั้งหมด"), "ลำดับผิด — intel ต้องอยู่ก่อนผู้ยื่นจริง"
d["intel_lines"] = None
h0 = pv.render_job_page(d, "TOK", 0)
assert "📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่" not in h0, h0
print("OK render_job_page_intel")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_portal_views.py`
Expected: `AssertionError` on `assert "📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่" in h` (the section does not exist in the rendered HTML yet).

- [ ] **Step 3: Implement the intel section in `render_job_page()`**

In `scripts/portal_views.py`, the current code (lines 390-392) reads:

```python
    if j.get("pred_lo") and j.get("pred_hi"):
        b.append(f"<div class=\"meta\">💵 คาดราคา {_baht(j['pred_lo'])}–{_baht(j['pred_hi'])} บาท</div>")
    if not data["bidders"]:
```

Insert the intel section between the `pred_lo`/`pred_hi` block and the bidders block:

```python
    if j.get("pred_lo") and j.get("pred_hi"):
        b.append(f"<div class=\"meta\">💵 คาดราคา {_baht(j['pred_lo'])}–{_baht(j['pred_hi'])} บาท</div>")
    if data.get("intel_lines"):
        b.append("<div class=\"bidhead\">📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่</div>")
        for line in data["intel_lines"]:
            b.append(f"<div class=\"meta\">{_h.escape(line)}</div>")
    if not data["bidders"]:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_portal_views.py`
Expected: output includes `OK render_job_page_intel` and ends with `OK test_portal_views` (no assertion errors, including all earlier `render_job_page` tests in the file that don't set `intel_lines` at all — `data.get("intel_lines")` is `None`/missing for those `job_detail()` results only when `cgd_intel.intel_context` itself returns `None`/raises for those fixtures, so the new section silently does not appear for them, exactly as before this change).

- [ ] **Step 5: Commit**

```bash
git add scripts/portal_views.py scripts/test_portal_views.py
git commit -m "feat(portal): render intel section on job detail page"
```

---

### Task 5: Full regression pass

**Files:** none (verification only)

**Interfaces:** none — this task only runs the existing test files touched or adjacent to this feature and confirms none regressed.

- [ ] **Step 1: Run every test file touched by this plan**

Run:
```bash
python scripts/test_job_link.py
python scripts/test_follow_link.py
python scripts/test_cgd_intel.py
python scripts/test_portal_views.py
python scripts/test_portal_routes.py
python scripts/test_portal_jobs.py
python scripts/test_portal_page.py
python scripts/test_portal_notes.py
python scripts/test_portal_stars.py
python scripts/test_deadline_time.py
```

Expected: every file prints its own `OK ...` / `✅ ...` / `ALL PASS ...` success line and none raises `AssertionError`, `KeyError`, or `AttributeError`.

- [ ] **Step 2: Manual smoke check (dry-run, no live LINE send)**

Run a one-off interactive check that a real D0-shaped call produces a well-formed link line:

```bash
python -c "
import os, sys
os.environ.setdefault('BMS_FOLLOW_SECRET', 'smoke-test-secret')
sys.path.insert(0, 'scripts')
import Sebastian_LINE_Sender as ls
import cgd_intel as ci
ci.intel_context = lambda *a, **k: {'lines': ['x'], 'prediction': None}
print(ls.format_notification('69059132412', province='นครพนม', project_name='ก่อสร้างถนน คสล.', announce_type='D0', source_stage='province_qualified', line_user_id='Utestuser123'))
"
```

Note: `BMS_FOLLOW_SECRET` must be set (via env or the `setdefault` above) before `Sebastian_LINE_Sender` is imported — `follow_token` reads it once at import time.

Expected: printed message ends with a `🔍 ดูวิเคราะห์ราคา+คู่แข่งบน Bid Board: https://api.butler-bms.com/portal/job?t=...&pid=69059132412` line, no `💡`/`━` intel text inlined.

- [ ] **Step 3: Commit (only if Step 1/2 surfaced fixes)**

If Step 1 or Step 2 required any code changes to pass, stage and commit them with a message describing the regression fixed. If everything passed as written, there is nothing to commit for this task.
