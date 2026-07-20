"""test_province_no_cut.py — งาน province ที่ resolve เปิดอยู่ enqueue เสมอ
แม้ match_job ตัดสินว่า 'cut' หรือ whole_province (เลิก digest + เลิก enforce-cut).

3 cases:
  1. test_digest_removed          — whole_province_keyword (เดิม trigger digest) → ยัง enqueue (D0)
  2. test_d0_cut_removed          — purchasing_excluded → decision='cut' จริง → ยัง enqueue (D0)
  3. test_b0_cut_removed          — purchasing_excluded → decision='cut' จริง → ยัง enqueue (B0/tor_review)
"""
import os, tempfile, sys
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
# NOTE: init_schema() ไม่มี source_epochs/qualification_status(project_locations) —
# columns/table เหล่านี้มาจาก migrate_qualification_schema.py (one-off ที่รันบน prod DB จริงแล้ว
# ไม่เคยพับเข้า init_schema()). รันบน temp DB นี้เพื่อ bridge gap ก่อน seed (ไม่แตะ prod, ไม่แก้ product code).
import migrate_qualification_schema as _mqs # noqa: E402
_mqs.migrate()
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


# งานชื่อนี้ยืนยันแล้วว่า match_job คืน decision='send' (reason='whole_province_keyword' — เดิม trigger digest)
DIGEST_NAME = "จ้างเหมาบริการทำความสะอาดอาคาร"
# งานชื่อนี้ยืนยันแล้วว่า match_job คืน decision='cut' (reason='purchasing_excluded') — ดู task-1-report.md
CUT_NAME = "จัดซื้อครุภัณฑ์คอมพิวเตอร์"


def test_digest_removed():
    """whole_province_keyword (เดิม trigger digest path) → ยังต้อง enqueue ตรง ไม่ลง digest."""
    s = db.SubscriptionStore()
    cid = s.add_customer("Uxx", "พ่อ")
    s.add_subscription(cid, ["นครพนม"])   # ลูกค้ารับจังหวัดนี้ (enqueue fan-out ถึงจะนับ)
    disc.ingest([{"project_id": "J1", "project_status": "", "announce_type": "D0",
                  "province": "นครพนม", "budget": 300000,
                  "project_name": DIGEST_NAME,
                  "dept_name": "อบต.บ้านแพง", "announce_date": "2026-07-01"}])
    ew.qualify_province_api(s, lambda *_: None, dsvc=_FakeDsvc())
    with db.get_connection() as c:
        q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='J1' AND customer_id=?", (cid,)).fetchone()[0]
        st = c.execute("SELECT qualification_status FROM project_locations WHERE project_id='J1'").fetchone()[0]
    assert q == 1, f"งานเปิดอยู่ต้อง enqueue (got queue={q})"
    assert st == "enqueued", f"status ต้อง enqueued ไม่ใช่ filtered/digest (got {st})"
    print("✅ test_digest_removed — whole_province_keyword ไม่ลง digest, enqueue ตรง")


def test_d0_cut_removed():
    """D0 path: match_job คืน decision='cut' จริง (purchasing_excluded) — ต้อง enqueue อยู่ดี (enforce-cut removed)."""
    s = db.SubscriptionStore()
    cid = s.add_customer("Uyy", "แม่")
    s.add_subscription(cid, ["นครพนม"])
    disc.ingest([{"project_id": "J2", "project_status": "", "announce_type": "D0",
                  "province": "นครพนม", "budget": 150000,
                  "project_name": CUT_NAME,
                  "dept_name": "อบต.บ้านแพง", "announce_date": "2026-07-01"}])
    ew.qualify_province_api(s, lambda *_: None, dsvc=_FakeDsvc())
    with db.get_connection() as c:
        q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='J2' AND customer_id=?", (cid,)).fetchone()[0]
        st = c.execute("SELECT qualification_status FROM project_locations WHERE project_id='J2'").fetchone()[0]
    assert q == 1, f"D0 decision='cut' ต้อง enqueue อยู่ดี (got queue={q})"
    assert st == "enqueued", f"status ต้อง enqueued ไม่ใช่ filtered_no_match (got {st})"
    print("✅ test_d0_cut_removed — D0 decision='cut' ยัง enqueue (enforce-cut removed)")


def test_b0_cut_removed():
    """B0 (รับฟังคำวิจารณ์) path: match_job คืน decision='cut' จริง — ต้อง enqueue อยู่ดี.
    B0 ไม่ resolve deadline (early-radar) → _FakeDsvc ไม่ถูกเรียกสำหรับเคสนี้; ใช้ announce_date=วันนี้
    ให้ผ่าน freshness gate (BMS_TOR_FRESH_DAYS default 14)."""
    s = db.SubscriptionStore()
    cid = s.add_customer("Uzz", "ป้า")
    s.add_subscription(cid, ["นครพนม"], announce_types=["D0", "B0"])  # default subscription=D0 เท่านั้น — ต้องเปิด B0 ด้วยถึงจะ fan-out
    disc.ingest([{"project_id": "J3", "project_status": "", "announce_type": "B0",
                  "province": "นครพนม", "budget": 150000,
                  "project_name": CUT_NAME,
                  "dept_name": "อบต.บ้านแพง", "announce_date": date.today().isoformat()}])
    ew.qualify_province_api(s, lambda *_: None, dsvc=_FakeDsvc())
    with db.get_connection() as c:
        q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='J3' AND customer_id=?", (cid,)).fetchone()[0]
        st = c.execute("SELECT qualification_status FROM project_locations WHERE project_id='J3'").fetchone()[0]
        ss = c.execute("SELECT source_stage FROM notification_queue WHERE project_id='J3' AND customer_id=?", (cid,)).fetchone()[0]
    assert q == 1, f"B0 decision='cut' ต้อง enqueue อยู่ดี (got queue={q})"
    assert st == "enqueued", f"status ต้อง enqueued ไม่ใช่ filtered_no_match (got {st})"
    assert ss == "province_tor_review", f"B0 source_stage ผิด (got {ss})"
    print("✅ test_b0_cut_removed — B0 decision='cut' ยัง enqueue (enforce-cut removed)")


test_digest_removed()
test_d0_cut_removed()
test_b0_cut_removed()
print("ALL PASS province_no_cut")
