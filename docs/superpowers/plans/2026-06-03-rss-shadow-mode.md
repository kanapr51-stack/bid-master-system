# RSS Shadow Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ส่ง user เฉพาะงานที่ Discovery/full sweep ยืนยัน (ประทับตรา) ใช้ RSS เป็น shadow audit คอยจับผิดว่า Discovery พลาดงานไหม

**Architecture:** เพิ่ม flag `discovery_confirmed` ใน `project_locations`. Discovery ประทับตรา=1 ให้ทุก project ที่ scan เจอ (claim งานที่ RSS เจอก่อนได้ ทะลุ landmine `INSERT OR IGNORE` ที่ทำให้ `source` ติด rss ถาวร). Enrichment Worker (RSS path: Pass 1+2) gate enqueue ด้วย flag นี้ คุมด้วย env `BMS_RSS_NOTIFY` (on=เดิม, off=shadow). Audit job รายงาน gap. ทุกอย่าง reversible ด้วย `BMS_RSS_NOTIFY=on`.

**Tech Stack:** Python 3, sqlite3, systemd timers, Discord webhook. **หมายเหตุ test style:** BMS ไม่ใช้ pytest — ใช้ **inline python verification + sanity check** (ตาม CLAUDE.md Sanity Check Protocol) และ verify บน VPS production DB

**ลำดับ deploy ปลอดภัย:** Task 1-2 (schema + Discovery ประทับตรา) deploy ก่อน → ให้ flag สะสมข้อมูล 1-2 วัน → แล้วค่อย Task 3 (เปิด gate) เพื่อไม่ให้ flag ยังว่างแล้วตัดงานทิ้ง

---

## File Structure

| ไฟล์ | ความรับผิดชอบ | Task |
|---|---|---|
| `scripts/Sebastian_Customer_DB.py` | schema migration `discovery_confirmed` | 1 |
| `scripts/Sebastian_Province_Discovery.py` | ประทับตรา + per-sweep report | 2 |
| `scripts/Sebastian_Enrichment_Worker.py` | gate enqueue (env toggle) | 3 |
| `scripts/Sebastian_Shadow_Audit.py` (ใหม่) | audit รายวัน Discord | 4 |
| `deploy/systemd/bms-shadow-audit.{service,timer}` (ใหม่) | timer 21:00 | 4 |
| deploy + rollout | migration + env + timer VPS | 5 |

---

## Task 1: Schema migration — `discovery_confirmed`

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py` (เพิ่ม `_migrate_v112` + เรียกใน `init_schema`)

- [ ] **Step 1: เพิ่มฟังก์ชัน migration** (วางถัดจาก `_migrate_v111`, ~line 218)

```python
def _migrate_v112():
    """Add discovery_confirmed to project_locations — RSS Shadow Mode (2026-06-03).
    1 = Discovery/full sweep ยืนยันเห็น project นี้ (claim ได้แม้ RSS เจอก่อน).
    แยกจาก source (provenance บริสุทธิ์) — gate: RSS path enqueue เฉพาะ =1 เมื่อ BMS_RSS_NOTIFY=off.
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "ALTER TABLE project_locations ADD COLUMN discovery_confirmed INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # already exists
```

- [ ] **Step 2: เรียกใน `init_schema`** — แก้ block ปลาย (line ~200-202)

หา:
```python
    _migrate_v110()
    _migrate_v111()
    print(f"Schema v1.11 ready: {DB_PATH}")
```
แทนด้วย:
```python
    _migrate_v110()
    _migrate_v111()
    _migrate_v112()
    print(f"Schema v1.12 ready: {DB_PATH}")
```

- [ ] **Step 3: Verify migration idempotent** (รัน 2 ครั้งไม่พัง + column มีจริง)

Run:
```bash
python -c "
import sys; sys.path.insert(0,'scripts')
import Sebastian_Customer_DB as DB
DB.init_schema(); DB.init_schema()  # 2 ครั้ง — ต้องไม่ error
import sqlite3
cols=[r[1] for r in sqlite3.connect(str(DB.DB_PATH)).execute('PRAGMA table_info(project_locations)')]
assert 'discovery_confirmed' in cols, cols
print('OK discovery_confirmed:', 'discovery_confirmed' in cols)
"
```
Expected: `Schema v1.12 ready` (×2) + `OK discovery_confirmed: True`

- [ ] **Step 4: Commit**

```bash
git -C "C:/Bid-Master-System" add scripts/Sebastian_Customer_DB.py
git -C "C:/Bid-Master-System" commit -m "feat(schema): + discovery_confirmed (RSS Shadow Mode migration v112)"
```

---

## Task 2: Discovery ประทับตรา + per-sweep report

**Files:**
- Modify: `scripts/Sebastian_Province_Discovery.py` (เพิ่ม `mark_discovery_confirmed` + เรียกหลัง ingest + per-sweep Discord report)

**บริบท:** `main()` มี `active` (list ของ rec ที่ scan เจอ, projectStatus≠R, line ~353) และ `ingest()` skip งานที่มีแล้ว (RSS เจอก่อน). การประทับตราต้องทำกับ **ทุก project ใน `active`** (รวมที่ skip) เพื่อ claim งาน RSS-first. ใช้ UPDATE (งาน RSS-first มี project_locations row จาก RSS Notifier อยู่แล้ว). งาน Discovery-first ไม่ต้อง mark (มัน source=province_api → ไป Pass 3 ไม่ผ่าน gate).

- [ ] **Step 1: เพิ่มฟังก์ชัน `mark_discovery_confirmed`** (วางถัดจาก `ingest`, ~line 288)

```python
def mark_discovery_confirmed(project_ids: list[str]) -> int:
    """ประทับ discovery_confirmed=1 ให้ project ที่ Discovery scan เจอ (claim งาน RSS-first).
    UPDATE เท่านั้น — งานที่มี project_locations row อยู่แล้ว (RSS Notifier insert pending).
    คืนจำนวน row ที่ประทับ (rowcount)."""
    if not project_ids:
        return 0
    conn = sqlite3.connect(_db_path())
    try:
        marked = 0
        for pid in project_ids:
            cur = conn.execute(
                "UPDATE project_locations SET discovery_confirmed=1 "
                "WHERE project_id=? AND discovery_confirmed=0", (pid,))
            marked += cur.rowcount
        conn.commit()
        return marked
    finally:
        conn.close()


def count_rss_gap() -> int:
    """นับงาน RSS-first ที่ resolve เป็นจังหวัดเป้าหมายแล้ว แต่ Discovery ยังไม่ประทับตรา.
    = สัญญาณ 'Discovery อาจพลาด' (province-level, ใช้ใน per-sweep report)."""
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM project_locations pl
            JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE ps.source='rss' AND pl.discovery_confirmed=0
              AND pl.province_name IN ('นครพนม','บึงกาฬ')
        """).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()
```

- [ ] **Step 2: เรียก `mark_discovery_confirmed` หลัง ingest** — แก้ block ingest (line ~377-384)

หา:
```python
    chosen = target if args.filter_amphoe else active
    ingested = 0
    if args.ingest and not args.dry_run:
        ingested, skipped = ingest(chosen)
        print(f"\n💾 ingest: +{ingested} ใหม่, {skipped} มีอยู่แล้ว (source=province_api)")
```
แทนด้วย:
```python
    chosen = target if args.filter_amphoe else active
    ingested = 0
    marked = 0
    if args.ingest and not args.dry_run:
        ingested, skipped = ingest(chosen)
        print(f"\n💾 ingest: +{ingested} ใหม่, {skipped} มีอยู่แล้ว (source=province_api)")
        # RSS Shadow Mode: ประทับตรา discovery_confirmed=1 ให้ทุก project ที่ scan เจอ (claim RSS-first)
        marked = mark_discovery_confirmed([r["project_id"] for r in active])
        print(f"🏷  ประทับตรา Discovery: {marked} งาน (claim RSS-first)")
```

- [ ] **Step 3: เพิ่ม per-sweep Discord report** — แก้ block Discord notify (line ~400-402)

หา:
```python
    # Discord notify ทุกรอบ incremental (7/13/19) — เจอ/ไม่เจองานใหม่ + รายละเอียด (กัญจน์ขอ 2026-06-01)
    # ไม่รวม full-sweep (safety net เงียบ — มี reconcile alert แยกถ้าเจอปัญหา)
    if args.ingest and not args.dry_run and not args.full:
```
เพิ่ม block **ก่อน** บรรทัดนั้น (per-sweep report สำหรับ full sweep — รายงานเสมอ):
```python
    # RSS Shadow Mode: per-sweep report (รายงานเสมอ จบทุก full sweep — 4 ครั้ง/วัน)
    if args.full and args.ingest and not args.dry_run:
        from datetime import datetime as _dtf, timezone as _tzf, timedelta as _tdf
        now_th_f = _dtf.now(_tzf(_tdf(hours=7))).strftime("%H:%M")
        prov_f = PROVINCE_MOI.get(moi_ids[0], moi_ids[0]) if len(moi_ids) == 1 else "ทุกจังหวัด"
        gap = count_rss_gap()
        gap_line = (f"RSS เห็นแต่ Discovery ยังไม่เจอ: {gap} งาน "
                    + ("✅" if gap == 0 else "⚠️ ดู audit รายวัน"))
        _discord("\n".join([
            f"🔍 Full sweep {prov_f} จบ ({now_th_f})",
            f"• scan เจอ: {len(active)} งาน",
            f"• ประทับตรา Discovery: {marked} งาน (ใหม่ {ingested})",
            f"• {gap_line}",
        ]))

```

- [ ] **Step 4: Verify — mark + gap ทำงาน** (test กับ local DB, mock 1 RSS row)

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0,'scripts')
import Sebastian_Customer_DB as DB; DB.init_schema()
import Sebastian_Province_Discovery as P
import sqlite3
db=P._db_path(); c=sqlite3.connect(db)
# mock: RSS row pending + projects_seen rss
c.execute(\"INSERT OR REPLACE INTO projects_seen(project_id,source,province,first_seen_at,announce_type,project_name,dept_name,budget,extraction_confidence) VALUES('TEST_SHADOW','rss','',?, 'D0','t','d',0,'low')\", (P._utc_now(),))
c.execute(\"INSERT OR REPLACE INTO project_locations(project_id,location_confidence,enrichment_status,created_at,discovery_confirmed) VALUES('TEST_SHADOW','unknown','pending',?,0)\", (P._utc_now(),))
c.commit(); c.close()
n=P.mark_discovery_confirmed(['TEST_SHADOW'])
assert n==1, n
c=sqlite3.connect(db)
v=c.execute(\"SELECT discovery_confirmed FROM project_locations WHERE project_id='TEST_SHADOW'\").fetchone()[0]
assert v==1, v
# cleanup
c.execute(\"DELETE FROM projects_seen WHERE project_id='TEST_SHADOW'\")
c.execute(\"DELETE FROM project_locations WHERE project_id='TEST_SHADOW'\"); c.commit(); c.close()
print('OK mark=1 confirmed=1')
"
```
Expected: `OK mark=1 confirmed=1`

- [ ] **Step 5: Verify syntax**

Run: `python -m py_compile scripts/Sebastian_Province_Discovery.py && echo OK`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git -C "C:/Bid-Master-System" add scripts/Sebastian_Province_Discovery.py
git -C "C:/Bid-Master-System" commit -m "feat(discovery): ประทับตรา discovery_confirmed + per-sweep report (Shadow Mode)"
```

---

## Task 3: Enrichment Worker — gate enqueue (env toggle)

**Files:**
- Modify: `scripts/Sebastian_Enrichment_Worker.py` (เพิ่ม env + helper + gate ที่ Pass 1 line ~383 และ Pass 2 line ~437)

**บริบท:** Pass 1 (RSS path) enqueue ที่ line ~383, Pass 2 (orphan repair) enqueue ที่ line ~437. **ทั้งคู่เป็น RSS path → ต้อง gate ทั้งสอง**. Pass 3 (`qualify_province_api`, province_api) ไม่แตะ (Discovery path, ไม่ผ่าน gate).

- [ ] **Step 1: เพิ่ม env + helper** (วางใกล้ import/config ด้านบนไฟล์ หลัง import `os`)

```python
# RSS Shadow Mode: gate RSS path enqueue ด้วย discovery_confirmed (reversible ด้วย env)
BMS_RSS_NOTIFY = os.environ.get("BMS_RSS_NOTIFY", "on").strip().lower()


def _rss_gate_ok(pid: str) -> bool:
    """RSS path enqueue gate.
    BMS_RSS_NOTIFY=on  → ผ่านเสมอ (พฤติกรรมเดิม)
    BMS_RSS_NOTIFY=off → ผ่านเฉพาะงานที่ Discovery ประทับตราแล้ว (discovery_confirmed=1)"""
    if BMS_RSS_NOTIFY != "off":
        return True
    with get_connection() as conn:
        row = conn.execute(
            "SELECT discovery_confirmed FROM project_locations WHERE project_id=?", (pid,)
        ).fetchone()
    return bool(row and row[0])
```

- [ ] **Step 2: Gate ที่ Pass 1** — แก้ block enqueue (line ~383-399)

หา:
```python
                n = store.enqueue_notifications({
                    "project_id":           pid,
                    "province":             province,
                    "announce_type":        announce_type,
                    "budget":               budget,
                    "project_name":         project_name,
                    "dept_name":            row.get("dept_name") or "",
                    "extraction_confidence": "high",
                    "is_backfill":          False,
                    "source_stage":         "api_enriched",
                }, min_confidence="high")

                if n > 0:
                    stats["enqueued"] += 1
                    log(f"    → ENQUEUED {n}x province={province} tambon={tambon}")
                else:
                    stats["dedup"] += 1
```
แทนด้วย (เพิ่ม gate ครอบ):
```python
                if not _rss_gate_ok(pid):
                    log(f"    ⏸ SHADOW: {pid} match {province} แต่ Discovery ยังไม่ประทับตรา → ไม่ส่ง (audit)")
                else:
                    n = store.enqueue_notifications({
                        "project_id":           pid,
                        "province":             province,
                        "announce_type":        announce_type,
                        "budget":               budget,
                        "project_name":         project_name,
                        "dept_name":            row.get("dept_name") or "",
                        "extraction_confidence": "high",
                        "is_backfill":          False,
                        "source_stage":         "api_enriched",
                    }, min_confidence="high")

                    if n > 0:
                        stats["enqueued"] += 1
                        log(f"    → ENQUEUED {n}x province={province} tambon={tambon}")
                    else:
                        stats["dedup"] += 1
```

- [ ] **Step 3: Gate ที่ Pass 2 (orphan repair)** — แก้ block (line ~436-449)

หา:
```python
        for orphan in orphans:
            n = store.enqueue_notifications({
                "project_id":            orphan["project_id"],
                "province":              orphan["province_name"],
                "announce_type":         orphan.get("announce_type") or "D0",
                "budget":                int(orphan.get("budget") or 0),
                "project_name":          orphan.get("project_name") or "",
                "dept_name":             orphan.get("dept_name") or "",
                "extraction_confidence": "high",
                "is_backfill":           False,
                "source_stage":          "repair_pass2",
            }, min_confidence="high")
            if n > 0:
                repaired += 1
```
แทนด้วย:
```python
        for orphan in orphans:
            if not _rss_gate_ok(orphan["project_id"]):
                continue  # SHADOW: Discovery ยังไม่ประทับตรา → ไม่ repair-enqueue
            n = store.enqueue_notifications({
                "project_id":            orphan["project_id"],
                "province":              orphan["province_name"],
                "announce_type":         orphan.get("announce_type") or "D0",
                "budget":                int(orphan.get("budget") or 0),
                "project_name":          orphan.get("project_name") or "",
                "dept_name":             orphan.get("dept_name") or "",
                "extraction_confidence": "high",
                "is_backfill":           False,
                "source_stage":          "repair_pass2",
            }, min_confidence="high")
            if n > 0:
                repaired += 1
```

- [ ] **Step 4: Verify gate logic** (on=ผ่าน, off+confirmed=0→บล็อก, off+confirmed=1→ผ่าน)

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "
import os, sys; sys.path.insert(0,'scripts')
import Sebastian_Customer_DB as DB; DB.init_schema()
import sqlite3
db=str(DB.DB_PATH); c=sqlite3.connect(db)
from datetime import datetime,timezone
now=datetime.now(timezone.utc).isoformat()
c.execute(\"INSERT OR REPLACE INTO project_locations(project_id,location_confidence,enrichment_status,created_at,discovery_confirmed) VALUES('GATE0','unknown','pending',?,0)\",(now,))
c.execute(\"INSERT OR REPLACE INTO project_locations(project_id,location_confidence,enrichment_status,created_at,discovery_confirmed) VALUES('GATE1','unknown','pending',?,1)\",(now,))
c.commit(); c.close()
# on → ผ่านเสมอ
os.environ['BMS_RSS_NOTIFY']='on'
import importlib, Sebastian_Enrichment_Worker as W; importlib.reload(W)
assert W._rss_gate_ok('GATE0') is True
# off → confirmed gate
os.environ['BMS_RSS_NOTIFY']='off'; importlib.reload(W)
assert W._rss_gate_ok('GATE0') is False, 'confirmed=0 ต้องบล็อก'
assert W._rss_gate_ok('GATE1') is True,  'confirmed=1 ต้องผ่าน'
c=sqlite3.connect(db); c.execute(\"DELETE FROM project_locations WHERE project_id IN ('GATE0','GATE1')\"); c.commit(); c.close()
print('OK gate: on=pass, off+0=block, off+1=pass')
"
```
Expected: `OK gate: on=pass, off+0=block, off+1=pass`

- [ ] **Step 5: Verify syntax**

Run: `python -m py_compile scripts/Sebastian_Enrichment_Worker.py && echo OK`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git -C "C:/Bid-Master-System" add scripts/Sebastian_Enrichment_Worker.py
git -C "C:/Bid-Master-System" commit -m "feat(enrichment): gate RSS-path enqueue ด้วย discovery_confirmed (env BMS_RSS_NOTIFY)"
```

---

## Task 4: Audit job รายวัน

> **อัปเดต 2026-06-03 (ChatGPT review):** audit ต้องมี **leading indicators** เพิ่ม (ดู spec §5.4 ฉบับ update) — shadow backlog size + age distribution (0-6/6-12/12-24/>24ชม) + confirmed rate. โค้ดด้านล่างเป็นเวอร์ชันแรก (lagging gap เท่านั้น) — ตอน implement จริงให้เพิ่ม 3 metric นี้ก่อน deploy (ใช้สำหรับ confirmed-rate gate ใน Task 5 Step 5)

**Files:**
- Create: `scripts/Sebastian_Shadow_Audit.py`
- Create: `deploy/systemd/bms-shadow-audit.service`
- Create: `deploy/systemd/bms-shadow-audit.timer`

- [ ] **Step 1: เขียนสคริปต์ audit** — `scripts/Sebastian_Shadow_Audit.py`

```python
"""
Sebastian_Shadow_Audit.py — RSS Shadow Mode audit รายวัน (2026-06-03)

รายงานเสมอ (ไม่ว่าสำเร็จหรือพบ gap) — heartbeat ว่า audit ยังทำงาน.
gap = งาน RSS-first ที่ resolve เป็นจังหวัดเป้าหมาย แต่ Discovery ไม่ประทับตรา
      และ RSS first_seen เกิน 24 ชม = Discovery น่าจะพลาดจริง.

Run: วันละครั้ง 21:00 ไทย (14:00 UTC) via systemd timer bms-shadow-audit
"""
import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

DB_PATH = os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"), "bms_customers.db")
GAP_HOURS = 24
TARGET = ("นครพนม", "บึงกาฬ")


def _discord(msg: str) -> None:
    try:
        from Sebastian_Discord_Notify import load_env, get_credentials, send
        load_env()
        t, ch = get_credentials()
        send(t, ch, msg)
    except Exception as e:
        print(f"discord fail (non-fatal): {e}")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")

    # Discovery ส่ง user วันนี้ (notification_queue ที่ source_stage ฝั่ง api/discovery, สร้างวันนี้)
    sent_today = conn.execute(
        "SELECT COUNT(DISTINCT project_id) FROM notification_queue "
        "WHERE substr(created_at,1,10)=?", (today,)
    ).fetchone()[0]

    # gap: RSS-first + resolve target + ยังไม่ประทับตรา + RSS เจอเกิน 24 ชม
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=GAP_HOURS)).isoformat()
    gap_rows = conn.execute("""
        SELECT pl.project_id, pl.province_name, ps.project_name, ps.first_seen_at
        FROM project_locations pl
        JOIN projects_seen ps ON ps.project_id = pl.project_id
        WHERE ps.source='rss' AND pl.discovery_confirmed=0
          AND pl.province_name IN (?, ?)
          AND ps.first_seen_at < ?
        ORDER BY ps.first_seen_at
    """, (*TARGET, cutoff)).fetchall()
    conn.close()

    lines = ["📊 RSS Shadow Audit รายวัน", f"• Discovery ส่ง user วันนี้: {sent_today} งาน",
             f"• RSS เห็นแต่ Discovery พลาด >{GAP_HOURS}ชม: {len(gap_rows)} งาน"]
    if gap_rows:
        lines.append(f"• สถานะ: ⚠️ พบ gap {len(gap_rows)} งาน — ตรวจว่า Discovery พลาดจริงไหม")
        for r in gap_rows[:8]:
            lines.append(f"  - {r['project_id']} | {r['province_name']} | {(r['project_name'] or '')[:38]}")
    else:
        lines.append("• สถานะ: ✅ Discovery จับครบ (พิสูจน์ value กำลังไปได้ดี)")
    _discord("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify สคริปต์รันได้ (local, ไม่ส่ง Discord จริงถ้า env ไม่มี)**

Run: `python -m py_compile scripts/Sebastian_Shadow_Audit.py && echo OK`
Expected: `OK`

- [ ] **Step 3: เขียน systemd service** — `deploy/systemd/bms-shadow-audit.service`

```ini
[Unit]
Description=BMS RSS Shadow Audit (รายงาน gap รายวัน)
After=network-online.target

[Service]
Type=oneshot
User=bms
WorkingDirectory=/opt/bms/app
Environment=BMS_DATA_DIR=/opt/bms/data
ExecStart=/opt/bms/venv/bin/python /opt/bms/app/scripts/Sebastian_Shadow_Audit.py
```

- [ ] **Step 4: เขียน systemd timer** — `deploy/systemd/bms-shadow-audit.timer`

```ini
[Unit]
Description=BMS RSS Shadow Audit — 21:00 ไทย (14:00 UTC) รายวัน

[Timer]
OnCalendar=*-*-* 14:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Commit**

```bash
git -C "C:/Bid-Master-System" add scripts/Sebastian_Shadow_Audit.py deploy/systemd/bms-shadow-audit.service deploy/systemd/bms-shadow-audit.timer
git -C "C:/Bid-Master-System" commit -m "feat(audit): Shadow Mode audit รายวัน 21:00 + systemd timer"
```

---

## Task 5: Deploy + Rollout (VPS)

**Files:** ไม่แก้ code — deploy artifacts ของ Task 1-4 ขึ้น VPS

**ลำดับปลอดภัย:** deploy Task 1-2 (schema + ประทับตรา) ก่อน + ยัง `BMS_RSS_NOTIFY=on` (ยังไม่ gate) → ให้ flag สะสม 1-2 วัน → แล้วค่อย flip `off`

- [ ] **Step 1: scp 4 ไฟล์ scripts ขึ้น VPS + compile**

```bash
ROOT="C:/Bid-Master-System"; KEY=~/.ssh/bms_vps; H=root@45.76.156.166
for f in Sebastian_Customer_DB Sebastian_Province_Discovery Sebastian_Enrichment_Worker Sebastian_Shadow_Audit; do
  scp -i $KEY -o StrictHostKeyChecking=no "$ROOT/scripts/$f.py" $H:/opt/bms/app/scripts/$f.py
done
ssh -i $KEY $H '/opt/bms/venv/bin/python -m py_compile /opt/bms/app/scripts/Sebastian_{Customer_DB,Province_Discovery,Enrichment_Worker,Shadow_Audit}.py && echo "VPS COMPILE OK"'
```
Expected: `VPS COMPILE OK`

- [ ] **Step 2: รัน migration บน VPS + verify column**

```bash
ssh -i $KEY $H 'cd /opt/bms/app && BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "
import sys; sys.path.insert(0,\"scripts\"); import Sebastian_Customer_DB as DB; DB.init_schema()
import sqlite3; cols=[r[1] for r in sqlite3.connect(\"/opt/bms/data/bms_customers.db\").execute(\"PRAGMA table_info(project_locations)\")]
print(\"discovery_confirmed in cols:\", \"discovery_confirmed\" in cols)"'
```
Expected: `Schema v1.12 ready` + `discovery_confirmed in cols: True`

- [ ] **Step 3: ติดตั้ง systemd audit timer**

```bash
scp -i $KEY "$ROOT/deploy/systemd/bms-shadow-audit.service" $H:/etc/systemd/system/
scp -i $KEY "$ROOT/deploy/systemd/bms-shadow-audit.timer" $H:/etc/systemd/system/
ssh -i $KEY $H 'systemctl daemon-reload && systemctl enable --now bms-shadow-audit.timer && systemctl list-timers bms-shadow-audit --no-pager'
```
Expected: timer `bms-shadow-audit` ปรากฏ NEXT = 14:00 UTC

- [ ] **Step 4: Backfill ประทับตรา + ทดสอบ audit (ยังไม่ flip gate)**

รัน full sweep 1 รอบเพื่อประทับตรางานที่มีอยู่ + ทดสอบ audit รายงาน:
```bash
ssh -i $KEY $H 'cd /opt/bms/app && BMS_DATA_DIR=/opt/bms/data BMS_TOKEN_WORKER=1 /opt/bms/venv/bin/python scripts/Sebastian_Shadow_Audit.py'
```
Expected: Discord ขึ้น "📊 RSS Shadow Audit รายวัน …" (รายงานเสมอ)

- [ ] **Step 5: 48h dry-run → flip เมื่อ confirmed rate สนับสนุน** (ADR-001, manual checkpoint)

**เปลี่ยนจาก "รอเวลาแล้ว flip" → "flip เมื่อหลักฐานสนับสนุน"** (ดู `docs/lessons_learned.md` ADR-001):
1. gate ยัง `on` 48 ชม — Discovery ประทับตราเดินปกติ + audit เก็บ metric
2. หลัง 48h ดู audit รายวัน:
   - **confirmed rate ≥ ~99%** + ไม่มี backlog age >24ชม ค้าง → **flip `off` ได้**
   - **confirmed rate ต่ำ (~80%)** หรือมี >24ชม ค้าง → **ห้าม flip** — สืบ gap ก่อน (Discovery อาจพลาด)
3. ยืนยันกับกัญจน์ก่อน flip เสมอ

ตั้ง env ใน service ของ enrichment worker ผ่าน drop-in file (ไม่ใช้ `systemctl edit` — มัน interactive จะ hang ใน ssh):
```bash
ssh -i $KEY $H 'mkdir -p /etc/systemd/system/bms-enrichment-worker.service.d && \
  printf "[Service]\nEnvironment=BMS_RSS_NOTIFY=off\n" > /etc/systemd/system/bms-enrichment-worker.service.d/shadow.conf && \
  systemctl daemon-reload && systemctl restart bms-enrichment-worker.service && \
  systemctl show bms-enrichment-worker.service -p Environment'
```
Expected: `Environment=BMS_RSS_NOTIFY=off` ปรากฏใน output

ตรวจว่า per-sweep report ก็ต้องเห็นงาน gate ทำงาน — หลัง flip ดู log enrichment ว่ามี `⏸ SHADOW` สำหรับงาน RSS-only

- [ ] **Step 6: Discord notify + progress_log**

```bash
cd "C:/Bid-Master-System" && python -c "
import sys; sys.path.insert(0,'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); t,ch=get_credentials()
send(t,ch,'🚀 RSS Shadow Mode deployed — Discovery ประทับตรา + audit รายวัน. gate ยัง on (จะ flip off หลัง flag สะสม 1-2 วัน)')"
```
อัปเดต `progress_log.md` (entry N+62: RSS Shadow Mode deployed)

---

## Rollout & Success Criteria (จาก spec §8, §10)
- หลัง flip `BMS_RSS_NOTIFY=off` → สังเกต ~1 สัปดาห์
- audit รายวันรายงานเสมอ — **gap = 0 ต่อเนื่อง = Discovery จับครบ = พิสูจน์ value สำเร็จ**
- ตรวจ: งานที่ RSS เจอก่อน + Discovery ประทับตรา → ยังส่งถึง user (landmine แก้แล้ว)
- reversible: `BMS_RSS_NOTIFY=on` + restart → RSS ส่งได้เหมือนเดิม
