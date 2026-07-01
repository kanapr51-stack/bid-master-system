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
