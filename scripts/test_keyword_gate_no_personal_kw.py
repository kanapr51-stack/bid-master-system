"""test_keyword_gate_no_personal_kw.py — N+206: enqueue_notifications(keyword_gate=True)
ต้องไม่ enqueue ให้ลูกค้าที่ไม่ได้ตั้ง personal keyword เอง แม้ match_job (คำกลาง) จะตัดสิน
'send'/'whole_province_keyword' ก็ตาม (พลิกกลับ N+184 ที่เคย "ยัง enqueue เสมอ" — คนละ gate
กับ match_job: กันนี้เช็ค customers.notes.classes[].keywords ต่อคน).

3 cases:
  1. ไม่ตั้ง personal keyword เลย → ไม่ enqueue (แม้ construction keyword ตรงคำกลาง)
  2. ตั้ง personal keyword แต่ไม่ตรงชื่องาน → ไม่ enqueue
  3. ตั้ง personal keyword ตรงชื่องาน → enqueue
"""
import os, json, tempfile, sys
from datetime import date, timedelta
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
os.environ["BMS_MATCHING_MODE"] = "enforce"
os.environ["BMS_KEYWORD_FIRST_MODE"] = "off"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db          # noqa: E402
db.init_schema()
import migrate_qualification_schema as _mqs # noqa: E402
_mqs.migrate()
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


# ชื่องานนี้ตรงกับ config/matching_preferences.json keywords (whole_provinces นครพนม) → match_job='send'
NAME = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก หมู่ที่ 2"


def _set_keywords(cid, keywords):
    with db.get_connection() as c:
        c.execute("UPDATE customers SET notes=? WHERE id=?",
                  (json.dumps({"classes": [{"keywords": keywords}]}), cid))


def _queue_count(pid, cid):
    with db.get_connection() as c:
        return c.execute(
            "SELECT COUNT(*) FROM notification_queue WHERE project_id=? AND customer_id=?",
            (pid, cid)).fetchone()[0]


def test_no_personal_keyword_no_enqueue():
    s = db.SubscriptionStore()
    cid = s.add_customer("Ukw1", "ไม่ตั้ง keyword")
    s.add_subscription(cid, ["นครพนม"])
    # notes เริ่มว่างเปล่า (ไม่มี classes) — ตรงสภาพลูกค้าจริงตอนนี้
    disc.ingest([{"project_id": "K1", "project_status": "", "announce_type": "D0",
                  "province": "นครพนม", "budget": 500000, "project_name": NAME,
                  "dept_name": "อบต.บ้านแพง", "announce_date": "2026-07-01"}])
    ew.qualify_province_api(s, lambda *_: None, dsvc=_FakeDsvc())
    q = _queue_count("K1", cid)
    assert q == 0, f"ไม่ตั้ง personal keyword ต้องไม่ enqueue เลย (got {q})"
    print("✅ test_no_personal_keyword_no_enqueue")


def test_personal_keyword_no_hit_no_enqueue():
    s = db.SubscriptionStore()
    cid = s.add_customer("Ukw2", "ตั้ง keyword ไม่ตรง")
    s.add_subscription(cid, ["นครพนม"])
    _set_keywords(cid, ["ประปา"])  # ไม่ตรงชื่องาน NAME (ถนน/คอนกรีต)
    disc.ingest([{"project_id": "K2", "project_status": "", "announce_type": "D0",
                  "province": "นครพนม", "budget": 500000, "project_name": NAME,
                  "dept_name": "อบต.บ้านแพง", "announce_date": "2026-07-01"}])
    ew.qualify_province_api(s, lambda *_: None, dsvc=_FakeDsvc())
    q = _queue_count("K2", cid)
    assert q == 0, f"personal keyword ไม่ตรงชื่องาน ต้องไม่ enqueue (got {q})"
    print("✅ test_personal_keyword_no_hit_no_enqueue")


def test_personal_keyword_hit_enqueues():
    s = db.SubscriptionStore()
    cid = s.add_customer("Ukw3", "ตั้ง keyword ตรง")
    s.add_subscription(cid, ["นครพนม"])
    _set_keywords(cid, ["ถนน"])  # ตรงชื่องาน NAME
    disc.ingest([{"project_id": "K3", "project_status": "", "announce_type": "D0",
                  "province": "นครพนม", "budget": 500000, "project_name": NAME,
                  "dept_name": "อบต.บ้านแพง", "announce_date": "2026-07-01"}])
    ew.qualify_province_api(s, lambda *_: None, dsvc=_FakeDsvc())
    q = _queue_count("K3", cid)
    assert q == 1, f"personal keyword ตรงชื่องาน ต้อง enqueue (got {q})"
    print("✅ test_personal_keyword_hit_enqueues")


test_no_personal_keyword_no_enqueue()
test_personal_keyword_no_hit_no_enqueue()
test_personal_keyword_hit_enqueues()
print("ALL PASS keyword_gate_no_personal_kw")
