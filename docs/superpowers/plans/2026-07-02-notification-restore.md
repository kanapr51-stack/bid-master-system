# Notification Restore (instant + เต็ม + ทั้งจังหวัด + lifecycle labels + สรุป 23:00) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** คืนพฤติกรรมแจ้งเตือนแบบเดิม — งาน D0 ใหม่ทั้งจังหวัด (นครพนม/บึงกาฬ ไม่กรอง) ส่ง LINE ทันทีเต็มรูปแบบ, งานติดตามเลื่อนเฟสส่งทันทีพร้อมป้ายหัวข้อ, และ 23:00 เปลี่ยนจากส่งงานเป็นสรุปประจำวัน.

**Architecture:** แก้ตรงจุดตัดใน `qualify_province_api` ให้งาน province ที่ resolve แล้วเปิดอยู่ **enqueue เสมอ** (เลิก `qualified_digest` + เลิก enforce-cut) โดย `match_job` ยังรันเป็น shadow-log เฉยๆ ไม่ drop → ทาง `enqueue_notifications() → line-sender` เดิมส่งข้อความเต็ม (ชื่อ+ลิงก์ประกาศ+ลิงก์ติดตาม) อัตโนมัติ. Winner-poller labels มีครบแล้ว (verify). Daily summary เปลี่ยนเป็น recap. ลบ 89-keyword seed. ปิดช่อง silent-bypass ของ follow link.

**Tech Stack:** Python 3, SQLite (`Sebastian_Customer_DB`), standalone test scripts (`python scripts/test_*.py`), LINE Messaging API ผ่าน `Sebastian_LINE_Sender`.

## Global Constraints

- **ใช้ทางส่งจริงเสมอ — ห้ามประกอบข้อความ LINE เอง.** ทุก notification ต้องผ่าน `enqueue_notifications()` → `Sebastian_LINE_Sender` (บทเรียน INC 2026-07-01 [[feedback_never_bypass_send_path]]).
- **จังหวัดในสโคป = `นครพนม`, `บึงกาฬ` เท่านั้น** (ค่าคงที่ที่มีอยู่ใน worker — ห้ามขยาย).
- **completeness-first / ไม่พลาดงาน:** งาน province ที่ resolve แล้วเปิดอยู่ ต้อง enqueue ทุกงาน ห้าม cut เงียบ.
- **`config/matching_preferences.json` ต้องไม่ถูกลบ** — `match_job` ยังรันเพื่อ shadow logging แต่ **ไม่ cut** อีกต่อไป.
- **fail-loud:** ถ้า follow link ประกอบไม่ได้ (BMS_FOLLOW_SECRET หาย) ต้อง raise ไม่ใช่ส่งข้อความที่ลิงก์หาย.
- **tests ตั้ง `BMS_DATA_DIR=tempfile.mkdtemp()` ก่อน import** `Sebastian_Customer_DB` เสมอ (กัน touch prod DB).
- **Deploy prerequisite (กัญจน์ทำเอง):** อัปเกรด LINE OA เป็น paid plan **ก่อน** flip เป็น instant enforce (free 300/เดือน ไม่พอ ~400-500/เดือน). เขียน code + shadow ได้ก่อน; enforce หลัง quota ขยายแล้วเท่านั้น.

---

### Task 1: Enrichment — งาน province เปิดอยู่ enqueue เสมอ (เลิก digest + เลิก enforce-cut)

**Files:**
- Modify: `scripts/Sebastian_Enrichment_Worker.py` — `qualify_province_api` (signature + B0 path ~316-355 + D0 path ~402-474)
- Test: `scripts/test_province_no_cut.py` (create)

**Interfaces:**
- Consumes: `store.enqueue_notifications(payload: dict, min_confidence="high") -> int` (มีอยู่), `deadline_service.DeadlineService` / `DeadlineOutcome` (มีอยู่).
- Produces: `qualify_province_api(store, log, dsvc=None) -> int` — เพิ่ม param `dsvc` (inject fake ใน test; `None` = สร้างจริงเหมือนเดิม). พฤติกรรมใหม่: RESOLVED+open → enqueue เสมอ (ไม่มี `qualified_digest`, ไม่มี `filtered_no_match` จาก match). `match_job` ยังรัน log; `soft_include` ยังได้ `source_stage='province_soft_location'`.

- [ ] **Step 1: เขียน failing test**

สร้าง `scripts/test_province_no_cut.py`:

```python
"""test_province_no_cut.py — งาน province ที่ resolve เปิดอยู่ enqueue เสมอ
แม้ match_job ตัดสินว่า 'cut' หรือ whole_province (เลิก digest + เลิก enforce-cut)."""
import os, tempfile, sys, types
from datetime import date, timedelta
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
os.environ["BMS_MATCHING_MODE"] = "enforce"   # โหมดที่ของเดิมจะ cut/digest — พิสูจน์ว่าไม่ cut แล้ว
os.environ["BMS_KEYWORD_FIRST_MODE"] = "off"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db          # noqa: E402
db.init_schema()
# get_procurement_detail ถูกเรียกใน enforce path → stub กัน HTTP จริง
import process5_http_client                 # noqa: E402
process5_http_client.get_procurement_detail = lambda pid: {"valid": False}
import Sebastian_Enrichment_Worker as ew    # noqa: E402
import Sebastian_Province_Discovery as disc # noqa: E402
from deadline_service import DeadlineOutcome # noqa: E402


class _FakeRes:
    outcome = DeadlineOutcome.RESOLVED
    deadline = date.today() + timedelta(days=7)
    deadline_time = "13.00-16.00 น."
    def is_open(self): return True


class _FakeDsvc:
    def resolve(self, pid): return _FakeRes()


def test_open_job_enqueued_even_if_match_cuts():
    s = db.SubscriptionStore()
    cid = s.add_customer("Uxx", "พ่อ")
    s.add_subscription(cid, ["นครพนม"])   # ลูกค้ารับจังหวัดนี้ (enqueue fan-out ถึงจะนับ)
    # งานนอกสาย (match_job จะตัดสิน cut) — ยังต้อง enqueue
    disc.ingest([{"project_id": "J1", "project_status": "", "announce_type": "D0",
                  "province": "นครพนม", "budget": 300000,
                  "project_name": "จ้างเหมาบริการทำความสะอาดอาคาร",
                  "dept_name": "อบต.บ้านแพง", "announce_date": "2026-07-01"}])
    n = ew.qualify_province_api(s, lambda *_: None, dsvc=_FakeDsvc())
    with db.get_connection() as c:
        q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='J1'").fetchone()[0]
        st = c.execute("SELECT qualification_status FROM project_locations WHERE project_id='J1'").fetchone()[0]
    assert q == 1, f"งานเปิดอยู่ต้อง enqueue (got queue={q})"
    assert st == "enqueued", f"status ต้อง enqueued ไม่ใช่ filtered/digest (got {st})"
    print("✅ open job enqueued — ไม่ cut ไม่ digest")


test_open_job_enqueued_even_if_match_cuts()
print("ALL PASS province_no_cut")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `python scripts/test_province_no_cut.py`
Expected: FAIL — ของเดิม `qualify_province_api` ไม่รับ param `dsvc` → `TypeError: unexpected keyword argument 'dsvc'` (หรือถ้ารันได้ status จะเป็น `filtered_no_match`/`qualified_digest`).

- [ ] **Step 3: เพิ่ม param `dsvc` ให้ inject ได้**

ใน `scripts/Sebastian_Enrichment_Worker.py` เปลี่ยน signature:

```python
def qualify_province_api(store, log, dsvc=None) -> int:
```

แล้วแก้บรรทัดสร้าง dsvc (เดิม `dsvc = DeadlineService(make_deadline_provider())`) เป็น:

```python
    if dsvc is None:
        dsvc = DeadlineService(make_deadline_provider())
```

(`make_deadline_provider` / `DeadlineService` import อยู่บรรทัดบนเหมือนเดิม — ไม่ย้าย)

- [ ] **Step 4: เลิก enforce-cut ใน B0 path**

ในบล็อก B0 (`if (c.get("announce_type") or "").upper().startswith("B"):`) ลบ 4 บรรทัดนี้ทิ้ง:

```python
                if mmode == "enforce" and decision == "cut":
                    with get_connection() as conn:
                        conn.execute("UPDATE project_locations SET qualification_status='filtered_no_match' WHERE project_id=?", (pid,))
                    stats["filtered"] += 1
                    continue
```

คงบรรทัด `if decision == "soft_include":` ที่ตามมาไว้ (soft label ยังทำงาน).

- [ ] **Step 5: เลิก digest + เลิก enforce-cut ใน D0 path**

ใน terminal outcome `if res.outcome == DeadlineOutcome.RESOLVED and res.is_open():`:

(a) ลบบรรทัด `is_digest = False   # ...` ทิ้ง.

(b) แทนทั้งบล็อก `if mmode == "enforce":` (เดิม cut→filtered / soft / send→is_digest) ด้วยบล็อกที่คง soft label แต่ไม่ cut/ไม่ digest:

```python
                if decision == "soft_include":
                    src_stage = "province_soft_location"
                    stats["soft"] += 1
```

(ลบ `if decision == "cut": ...continue` และ `elif decision == "send" and ... is_digest = True` ออกทั้งหมด — คงเฉพาะ soft label ซึ่งตอนนี้ applies ทุกโหมดที่ `mmode != "off"`)

(c) ลบบล็อก digest ทิ้งทั้งก้อน:

```python
            if is_digest:
                status = "qualified_digest"
                stats["digest"] = stats.get("digest", 0) + 1
                log(f"  → 📋 DIGEST {pid} {c['province']} (รวมในสรุปวันละครั้ง)")
            elif mode == "live":
```

เปลี่ยนหัวบล็อกถัดไปจาก `elif mode == "live":` เป็น `if mode == "live":`.

- [ ] **Step 6: รัน test ให้ผ่าน**

Run: `python scripts/test_province_no_cut.py`
Expected: PASS — `✅ open job enqueued — ไม่ cut ไม่ digest` + `ALL PASS province_no_cut`

- [ ] **Step 7: รัน regression suite ที่เกี่ยว**

Run: `python scripts/test_bid_open_pass.py && python scripts/test_job_matcher.py`
Expected: ทั้งคู่ PASS (ยืนยัน followup + matcher เดิมไม่พัง)

- [ ] **Step 8: Commit**

```bash
git add scripts/Sebastian_Enrichment_Worker.py scripts/test_province_no_cut.py
git commit -m "feat(enrichment): province open jobs enqueue เสมอ — เลิก digest+enforce-cut (สเตจ1)"
```

---

### Task 2: Winner-poller lifecycle labels — verify ป้ายหัวข้อครบ 4 แบบ

**Files:**
- Modify (ถ้าขาดเท่านั้น): `scripts/Sebastian_LINE_Sender.py`
- Test: `scripts/test_lifecycle_labels.py` (create)

**Interfaces:**
- Consumes: `Sebastian_LINE_Sender.format_notification(project_id, province="", announce_type="D0", budget=0, project_name="", dept_name="", ..., source_stage="api_enriched") -> str` (บรรทัด ~231). Label wiring: `source_stage='followed_bid_open'` → `"⭐ งานที่คุณติดตามกำหนดวันยื่นซองแล้ว!"` (บรรทัด ~255-256); `followed_prelim` → `format_prelim_notification`; `followed_winner` → `format_winner`/`format_winner_detailed`; `followed_cancelled` → `format_cancelled_notification`.
- Produces: test ที่ล็อกข้อความป้ายกัน regression (ไม่คาดว่าต้องแก้ production — labels มีครบแล้ว).

- [ ] **Step 1: เขียน test ยืนยันป้าย bid_open**

สร้าง `scripts/test_lifecycle_labels.py`:

```python
"""test_lifecycle_labels.py — ยืนยันป้ายหัวข้อ lifecycle ครบ (bid_open/prelim/winner)."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls   # noqa: E402


def test_bid_open_label():
    body = ls.format_notification(
        "J1", province="นครพนม", budget=500000,
        project_name="งานถนน", dept_name="อบต.บ้านแพง",
        announce_type="D0", source_stage="followed_bid_open")
    assert "ติดตาม" in body and "ยื่นซอง" in body, body
    print("✅ followed_bid_open label")


test_bid_open_label()
print("ALL PASS lifecycle_labels")
```

- [ ] **Step 2: รัน test**

Run: `python scripts/test_lifecycle_labels.py`
Expected: PASS. **ถ้า FAIL เพราะ label ขาด** → เติมบรรทัด label ที่ตรง source_stage ใน `format_notification` (บล็อก if source_stage ~255) แล้วรันซ้ำจนผ่าน. ถ้าผ่านทันที = production มีครบแล้ว (ไม่ต้องแก้ code).

- [ ] **Step 3: รัน prelim/winner test เดิมเพื่อยืนยัน 2 ป้ายที่เหลือ**

Run: `python scripts/test_winner_poller.py && python scripts/test_format_prelim.py`
Expected: PASS (fixture PRELIM/W0 เดิมยืนยัน label prelim + winner).

- [ ] **Step 4: Commit**

```bash
git add scripts/test_lifecycle_labels.py
git commit -m "test(labels): ยืนยันป้าย lifecycle bid_open ครบ (สเตจ1)"
```

---

### Task 3: Daily summary → recap (นับวันนี้ + todo พรุ่งนี้รวมโน้ต + รายการงานวันนี้)

**Files:**
- Modify: `scripts/Sebastian_Daily_User_Summary.py` (`build_message` + `main` + เพิ่ม 2 helper; ลบ digest wiring)
- Test: `scripts/test_daily_recap.py` (create), ลบ `scripts/test_daily_digest.py`

**Interfaces:**
- Consumes: `job_notes(customer_id, project_id, entry_date, note)` schema (มีอยู่); `delivery_log(customer_id, project_id, status, attempted_at)`; `bid_open.bid_open_for_customer(conn, customer_id, date_str)` (มีอยู่).
- Produces:
  - `fetch_today_sent(conn, customer_id: int, today_th: str) -> list[dict]` → `[{project_id, name}]` งานที่ส่งสำเร็จวันนี้.
  - `fetch_notes_due(conn, customer_id: int, date_th: str) -> list[dict]` → `[{project_id, note}]` โน้ตที่ `entry_date == date_th`.
  - `build_message(name, matched_today, today_jobs=None, tomorrow_jobs=None, notes_due=None, link_fn=None) -> str` (เปลี่ยน signature — เลิกรับ `digest_jobs`).

- [ ] **Step 1: เขียน failing test สำหรับ 2 helper + recap message**

สร้าง `scripts/test_daily_recap.py`:

```python
"""test_daily_recap.py — Daily summary = recap: นับงานวันนี้ + todo พรุ่งนี้ + โน้ต due."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db   # noqa: E402
db.init_schema()
import Sebastian_Daily_User_Summary as dus  # noqa: E402

TODAY = "2026-07-02"
TOMORROW = "2026-07-03"


def _seed():
    s = db.SubscriptionStore()
    cid = s.add_customer("Uaa", "กัญจน์")
    with db.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO projects_seen (project_id, province, project_name, first_seen_at) "
                     "VALUES ('P1','นครพนม','ก่อสร้างถนน คสล.', ?)", (TODAY,))
        conn.execute("INSERT INTO delivery_log (customer_id, project_id, status, attempted_at, is_test_data) "
                     "VALUES (?, 'P1', 'sent', ?, 0)", (cid, TODAY + "T09:00:00"))
        conn.execute("INSERT INTO job_notes (customer_id, project_id, entry_date, note, created_at) "
                     "VALUES (?, 'P1', ?, 'เตรียมเอกสารยื่นซอง', ?)", (cid, TOMORROW, TODAY))
    return cid


def test_fetch_today_sent():
    cid = _seed()
    with db.get_connection() as conn:
        jobs = dus.fetch_today_sent(conn, cid, TODAY)
    assert len(jobs) == 1 and jobs[0]["project_id"] == "P1", jobs
    assert "ถนน" in jobs[0]["name"], jobs
    print("✅ fetch_today_sent")


def test_fetch_notes_due():
    cid = _seed()
    with db.get_connection() as conn:
        due = dus.fetch_notes_due(conn, cid, TOMORROW)
    assert len(due) == 1 and "เอกสาร" in due[0]["note"], due
    print("✅ fetch_notes_due")


def test_recap_message_has_all_sections():
    msg = dus.build_message(
        "กัญจน์", 1,
        today_jobs=[{"project_id": "P1", "name": "ก่อสร้างถนน คสล."}],
        tomorrow_jobs=[{"project_id": "P2", "name": "งานยื่นพรุ่งนี้"}],
        notes_due=[{"project_id": "P1", "note": "เตรียมเอกสารยื่นซอง"}])
    assert "1 งาน" in msg, msg          # นับวันนี้
    assert "ถนน" in msg, msg             # รายการวันนี้
    assert "พรุ่งนี้" in msg, msg        # todo พรุ่งนี้
    assert "เอกสาร" in msg, msg          # โน้ต due
    print("✅ recap message ครบ 4 ส่วน")


test_fetch_today_sent()
test_fetch_notes_due()
test_recap_message_has_all_sections()
print("ALL PASS daily_recap")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `python scripts/test_daily_recap.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'fetch_today_sent'`

- [ ] **Step 3: เพิ่ม 2 helper + เขียน build_message ใหม่**

ใน `scripts/Sebastian_Daily_User_Summary.py` ลบ `fetch_digest_jobs` + `mark_digest_listed` ทิ้ง แล้วเพิ่ม:

```python
def fetch_today_sent(conn, customer_id: int, today_th: str) -> list:
    """งานที่ส่งสำเร็จให้ลูกค้ารายนี้วันนี้ (delivery_log status='sent', ไม่นับ test).
    คืน [{project_id, name}]. graceful."""
    try:
        rows = conn.execute("""
            SELECT DISTINCT dl.project_id, COALESCE(ps.project_name, dl.project_id)
            FROM delivery_log dl
            LEFT JOIN projects_seen ps ON ps.project_id = dl.project_id
            WHERE dl.customer_id=? AND dl.status='sent'
              AND COALESCE(dl.is_test_data,0)=0 AND dl.attempted_at LIKE ?
        """, (customer_id, today_th + "%")).fetchall()
    except Exception:
        return []
    return [{"project_id": r[0], "name": r[1] or r[0]} for r in rows]


def fetch_notes_due(conn, customer_id: int, date_th: str) -> list:
    """job_notes ที่ entry_date == วันที่ระบุ (โน้ต/timeline ที่ถึงกำหนด). คืน [{project_id, note}]."""
    try:
        rows = conn.execute(
            "SELECT project_id, note FROM job_notes WHERE customer_id=? AND entry_date=?",
            (customer_id, date_th)).fetchall()
    except Exception:
        return []
    return [{"project_id": r[0], "note": r[1]} for r in rows]
```

แล้วแทน `build_message` ทั้งฟังก์ชันด้วย:

```python
def build_message(name: str, matched_today: int, today_jobs=None, tomorrow_jobs=None,
                  notes_due=None, link_fn=None) -> str:
    """สรุปประจำวัน (recap ไม่ใช่ส่งงาน): นับวันนี้ + รายการงานวันนี้ + todo พรุ่งนี้ + โน้ต due พรุ่งนี้."""
    import bid_open
    name = name or "ลูกค้า"
    d = datetime.now(TZ_TH)
    today = f"{d.day}/{d.month}"
    parts = [f"🎩 สรุปประจำวัน {today} — Sebastian\n\nสวัสดีครับ คุณ{name}"]
    if matched_today > 0:
        parts.append(f"📬 วันนี้ผมส่งงานในพื้นที่ของคุณไปแล้ว {matched_today} งาน:\n"
                     + bid_open.format_job_bullets(today_jobs or [], link_fn))
    else:
        parts.append("📭 วันนี้ยังไม่มีงานใหม่ในพื้นที่ของคุณ\nไม่ต้องห่วงครับ ผมเฝ้าตรวจให้ตลอด 🫡")
    if tomorrow_jobs:
        parts.append(f"📅 พรุ่งนี้มีงานเปิดยื่นซอง {len(tomorrow_jobs)} งาน:\n"
                     + bid_open.format_job_bullets(tomorrow_jobs, link_fn))
    if notes_due:
        note_lines = "\n".join(f"• {n['note']}" for n in notes_due)
        parts.append(f"📝 โน้ตที่ถึงกำหนดพรุ่งนี้ ({len(notes_due)}):\n{note_lines}")
    return "\n\n".join(parts)
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `python scripts/test_daily_recap.py`
Expected: PASS — 3 บรรทัด ✅ + `ALL PASS daily_recap`

- [ ] **Step 5: แก้ `main()` ให้ประกอบ recap (ไม่ใช่ digest)**

ใน `main()` แทนบล็อกที่ดึง `digest_jobs` + loop เดิม ด้วย (ตัด `fetch_digest_jobs`/`mark_digest_listed`):

```python
    import bid_open
    with get_connection() as conn:
        customers = conn.execute(
            "SELECT id, line_user_id, display_name FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0"
        ).fetchall()
        targets = []
        for c in customers:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM delivery_log WHERE customer_id=? AND status='sent' "
                "AND COALESCE(is_test_data,0)=0 AND attempted_at LIKE ?",
                (c["id"], today_th + "%")).fetchone()[0]
            today_jobs = fetch_today_sent(conn, c["id"], today_th)
            tomorrow_jobs = bid_open.bid_open_for_customer(conn, c["id"], tomorrow_th)
            notes_due = fetch_notes_due(conn, c["id"], tomorrow_th)
            targets.append((c, cnt, today_jobs, tomorrow_jobs, notes_due))

    print(f"[{now_th}] daily recap — {len(targets)} real customers (today_th={today_th})", flush=True)

    from Sebastian_LINE_Sender import build_follow_link
    token = None if args.dry_run else _load_line_token()
    ok = fail = 0
    for c, cnt, today_jobs, tomorrow_jobs, notes_due in targets:
        name = c["display_name"] or c["line_user_id"][:10]
        link_fn = (lambda uid: lambda pid: build_follow_link(uid, pid))(c["line_user_id"])
        msg = build_message(name, cnt, today_jobs=today_jobs, tomorrow_jobs=tomorrow_jobs,
                            notes_due=notes_due, link_fn=link_fn)
        if args.dry_run:
            print(f"\n--- [{name}] วันนี้={cnt} พรุ่งนี้={len(tomorrow_jobs)} โน้ต={len(notes_due)} ---\n{msg}\n", flush=True)
            ok += 1
            continue
        success, error_type, error_msg = send_line_push(token, c["line_user_id"], msg)
        if success:
            ok += 1
            print(f"  ✅ {name} (วันนี้={cnt})", flush=True)
        else:
            fail += 1
            print(f"  ❌ {name}: {error_type} {error_msg}", flush=True)

    summary = f"📋 Daily recap {now_th} — ส่ง {ok}/{len(targets)} คน"
    if fail:
        summary += f" (ล้มเหลว {fail})"
    print(summary, flush=True)
    if not args.dry_run and targets:
        _discord(summary)
```

(ลบบล็อก `mark digest jobs ว่าลิสต์แล้ว` ทิ้งทั้งก้อน — ไม่มี digest แล้ว)

- [ ] **Step 6: ลบ test เดิมที่ตายแล้ว + verify dry-run**

```bash
git rm scripts/test_daily_digest.py
```

Run: `python scripts/Sebastian_Daily_User_Summary.py --dry-run`
Expected: exit 0, พิมพ์ recap ต่อ customer (ไม่มี traceback, ไม่มี reference ถึง digest)

- [ ] **Step 7: Commit**

```bash
git add scripts/Sebastian_Daily_User_Summary.py scripts/test_daily_recap.py
git commit -m "feat(summary): 23:00 = recap (นับวันนี้+todo พรุ่งนี้+โน้ต due) เลิก digest (สเตจ1)"
```

---

### Task 4: ปิดช่อง silent-bypass ของ follow link (fail-loud)

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` — `build_follow_link` (บรรทัด ~351-358)
- Test: `scripts/test_follow_link_guard.py` (create)

**Interfaces:**
- Consumes: `follow_token.make_token(line_user_id, project_id) -> str` (ต้องมี `BMS_FOLLOW_SECRET`).
- Produces: `build_follow_link(line_user_id, project_id, strict=True) -> str` — raise `RuntimeError` เมื่อประกอบลิงก์ไม่ได้ (แทนคืน `''` เงียบ). `strict=False` = พฤติกรรมเดิม (คืน `''`) เผื่อ caller ที่ยอมไม่มีลิงก์ได้จริง.

- [ ] **Step 1: เขียน failing test**

สร้าง `scripts/test_follow_link_guard.py`:

```python
"""test_follow_link_guard.py — build_follow_link ต้อง fail-loud เมื่อประกอบลิงก์ไม่ได้."""
import os, sys
from pathlib import Path
os.environ.pop("BMS_FOLLOW_SECRET", None)   # ทำให้ make_token พลาด
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls   # noqa: E402


def test_strict_raises_when_link_broken():
    raised = False
    try:
        ls.build_follow_link("Uxx", "J1")   # strict default → ต้อง raise
    except RuntimeError:
        raised = True
    assert raised, "ประกอบลิงก์ไม่ได้ต้อง raise ไม่ใช่คืน '' เงียบ"
    print("✅ build_follow_link strict fail-loud")


def test_non_strict_returns_empty():
    out = ls.build_follow_link("Uxx", "J1", strict=False)
    assert out == "", out
    print("✅ non-strict คืน '' (พฤติกรรมเดิม)")


test_strict_raises_when_link_broken()
test_non_strict_returns_empty()
print("ALL PASS follow_link_guard")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `python scripts/test_follow_link_guard.py`
Expected: FAIL — ของเดิมคืน `''` เสมอ → `AssertionError: ประกอบลิงก์ไม่ได้ต้อง raise`

- [ ] **Step 3: แก้ `build_follow_link` ให้ fail-loud**

แทนฟังก์ชันเดิมด้วย:

```python
def build_follow_link(line_user_id: str, project_id: str, strict: bool = True) -> str:
    """ลิงก์ติดตามงาน (signed token, ต่อคน-ต่องาน).
    strict=True (default) → raise RuntimeError ถ้าประกอบไม่ได้ (กันส่งข้อความลิงก์หายเงียบ —
    บทเรียน INC 2026-07-01). strict=False → คืน '' (เดิม)."""
    try:
        return PUBLIC_BASE_URL.rstrip("/") + "/follow?t=" + \
            follow_token.make_token(line_user_id, project_id)
    except Exception as e:
        if strict:
            raise RuntimeError(f"build_follow_link ประกอบลิงก์ไม่ได้ (BMS_FOLLOW_SECRET?): {e}") from e
        print(f"[build_follow_link] follow_token error (ส่งต่อไม่มีลิงก์): {e}", file=sys.stderr)
        return ""
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `python scripts/test_follow_link_guard.py`
Expected: PASS — 2 บรรทัด ✅ + `ALL PASS follow_link_guard`

- [ ] **Step 5: ยืนยัน caller เดิมไม่พังตอน secret มีจริง**

Run: `python scripts/test_lifecycle_labels.py && python scripts/test_daily_recap.py`
Expected: PASS (callers ที่มี secret จริงยังทำงาน; strict default ไม่กระทบ path ปกติ)

- [ ] **Step 6: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py scripts/test_follow_link_guard.py
git commit -m "fix(sender): build_follow_link fail-loud เมื่อลิงก์ประกอบไม่ได้ (never-bypass)"
```

---

### Task 5: ลบ 89-keyword seed ของลูกค้า 5 ราย (idempotent + backup)

**Files:**
- Create: `scripts/clear_keyword_seed.py` (one-off, run explicit)
- Test: `scripts/test_clear_keyword_seed.py` (create)

**Interfaces:**
- Consumes: `customers.notes` (JSON string ที่มี key `classes` — seed จาก N+181, shape ตาม `classes/_client.tsx:1033`).
- Produces: `clear_keyword_seed(conn) -> int` — เคลียร์ `classes` ที่มาจาก seed ออกจาก `notes` ของทุก customer (idempotent, คืนจำนวนแถวที่แก้). "ไม่มี keyword = เห็นทั้งจังหวัด".

- [ ] **Step 1: เขียน failing test**

สร้าง `scripts/test_clear_keyword_seed.py`:

```python
"""test_clear_keyword_seed.py — เคลียร์ 89-keyword seed ออกจาก customers.notes (idempotent)."""
import os, tempfile, sys, json
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db   # noqa: E402
db.init_schema()
import clear_keyword_seed as cks      # noqa: E402


def test_clears_classes_key():
    s = db.SubscriptionStore()
    cid = s.add_customer("Uaa", "กัญจน์")
    seeded = json.dumps({"classes": [{"keywords": ["ก่อสร้าง"] * 89}], "other": 1})
    with db.get_connection() as conn:
        conn.execute("UPDATE customers SET notes=? WHERE id=?", (seeded, cid))
        n = cks.clear_keyword_seed(conn)
        assert n == 1, n
        notes = conn.execute("SELECT notes FROM customers WHERE id=?", (cid,)).fetchone()[0]
    parsed = json.loads(notes)
    assert "classes" not in parsed or parsed["classes"] == [], parsed
    assert parsed.get("other") == 1, "ต้องไม่แตะ key อื่น"
    # idempotent — รันซ้ำ = 0 แถว
    with db.get_connection() as conn:
        assert cks.clear_keyword_seed(conn) == 0
    print("✅ clear_keyword_seed — เคลียร์ classes, คง key อื่น, idempotent")


test_clears_classes_key()
print("ALL PASS clear_keyword_seed")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `python scripts/test_clear_keyword_seed.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'clear_keyword_seed'`

- [ ] **Step 3: เขียน `clear_keyword_seed.py`**

```python
"""clear_keyword_seed.py — ลบ 89-keyword seed (N+181) ออกจาก customers.notes.
"ไม่มี keyword = เห็น/ส่งทั้งจังหวัด". idempotent. รัน one-off บน prod แบบ:
    BMS_DATA_DIR=/opt/bms/data python scripts/clear_keyword_seed.py --apply
(default = dry-run; --apply เท่านั้นถึงเขียน). backup DB ก่อนเสมอ (ดู Rollout)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import get_connection


def clear_keyword_seed(conn) -> int:
    """ลบ key 'classes' ออกจาก notes JSON ของทุก customer ที่มี. คืนจำนวนแถวที่แก้."""
    rows = conn.execute("SELECT id, notes FROM customers WHERE notes IS NOT NULL AND notes!=''").fetchall()
    changed = 0
    for r in rows:
        try:
            parsed = json.loads(r["notes"])
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("classes"):
            parsed["classes"] = []
            conn.execute("UPDATE customers SET notes=? WHERE id=?",
                         (json.dumps(parsed, ensure_ascii=False), r["id"]))
            changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="เขียนจริง (default = dry-run)")
    args = ap.parse_args()
    with get_connection() as conn:
        if not args.apply:
            rows = conn.execute("SELECT id, notes FROM customers WHERE notes LIKE '%\"classes\"%'").fetchall()
            print(f"[dry-run] จะเคลียร์ classes ของ {len(rows)} customer (ใส่ --apply เพื่อเขียนจริง)", flush=True)
            return
        n = clear_keyword_seed(conn)
    print(f"✅ เคลียร์ keyword seed แล้ว {n} customer", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `python scripts/test_clear_keyword_seed.py`
Expected: PASS — `✅ clear_keyword_seed ...` + `ALL PASS clear_keyword_seed`

- [ ] **Step 5: Commit (ยังไม่รันบน prod — รอ Rollout)**

```bash
git add scripts/clear_keyword_seed.py scripts/test_clear_keyword_seed.py
git commit -m "feat(seed): clear_keyword_seed one-off — ลบ 89-keyword (idempotent, dry-run default)"
```

> ⚠️ **ห้ามรันบน prod ใน task นี้** — การรันจริง (`--apply`) อยู่ใน Rollout Step หลัง backup DB. [[feedback_migration_no_seed]]

---

## Rollout (หลัง 5 task ผ่าน — ทำตามลำดับ ห้ามข้าม)

1. **Prerequisite:** ยืนยันกับกัญจน์ว่า **อัปเกรด LINE OA เป็น paid plan แล้ว** — เช็ก quota: `GET https://api.line.me/v2/bot/message/quota` ต้องไม่ใช่ `{"type":"limited","value":300}`. ถ้ายัง free → **หยุด** (instant จะชน quota ซ้ำ 24 มิ.ย.).
2. **Deploy code:** push origin → reconcile VPS (`/opt/bms/app/scripts/`) ตาม trick ใน [[project_resume_session]] (`git -c credential.helper='!gh auth git-credential' push origin main`; VPS `git stash` + `git pull --ff-only` **ห้าม `stash -u`**).
3. **Shadow 1 รอบ:** ปล่อย enrichment รันปกติ 1 วัน ดู log `enqueued=N` ต่อรอบ → ยืนยันปริมาณจริง/วัน เทียบ quota ที่อัปเกรดแล้ว (Success criteria: instant ~400-500/เดือน < quota ใหม่).
4. **Test-send ตัวเอง (บังคับก่อน broadcast):** เลือกงาน D0 จริง 1 งาน → ยืนยันข้อความเข้า LINE กัญจน์ มี **ชื่องาน + ลิงก์ดูประกาศ + ลิงก์ติดตาม** ครบ (เปิดกดจริง). บทเรียน 2026-07-01 [[feedback_never_bypass_send_path]].
5. **Backup + ลบ seed:** บน VPS — `cp /opt/bms/data/bms_customers.db /opt/bms/data/backups/bms_customers_pre_clearseed_$(date +%Y%m%d_%H%M%S).db` → `BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python3 /opt/bms/app/scripts/clear_keyword_seed.py --apply`.
6. **ตั้ง 23:00 recap:** ยืนยัน cron/timer เรียก `Sebastian_Daily_User_Summary.py` เวลา 23:00 ไทย (เดิม 20:00 — ปรับเวลาตาม spec).
7. **Sanity (Sophia):** dispatch Sophia ตรวจ `notification_queue`/`delivery_log` ว่างานเข้าครบ ไม่มี dup, ไม่มีงาน D0 พื้นที่เปิดค้าง `filtered_no_match`.

## Out of scope (→ phase-B)
- ปุ่มติ๊กหมวดบน Board B (อาคาร/ถนน/ชลประทาน/วัสดุ/อื่นๆ) — `2026-07-01-category-matching-design-DRAFT.md`
- ปรับความถี่ winner-poller / ปรับเวลา discovery 07/13/19
