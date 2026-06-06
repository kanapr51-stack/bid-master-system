"""test_bid_open_pass.py — integration: ติดดาว B0 → งานเลื่อน D0 → notify_bid_open_followups enqueue."""
import os, tempfile, sys, sqlite3
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()
import Sebastian_Province_Discovery as disc  # noqa: E402
import Sebastian_Enrichment_Worker as ew  # noqa: E402

s = db.SubscriptionStore()
cid = s.add_customer("Uxx", "พ่อ")

# งานเข้า B0 → ติดดาว
disc.ingest([{"project_id": "J1", "project_status": "", "announce_type": "B0",
              "province": "นครพนม", "budget": 500000, "project_name": "งานถนน คสล. ต.บ้านแพง",
              "dept_name": "อบต.บ้านแพง", "announce_date": "2026-06-05"}])
s.add_follow(cid, "J1", "B0")
# project_locations row (มีตอน B0 ผ่าน qualify seed) — followup จะ UPDATE deadline ลงตรงนี้
with db.get_connection() as conn:
    conn.execute("INSERT INTO project_locations (project_id, province_name, location_confidence, "
                 "enrichment_status, created_at) VALUES (?,?,?,?,?)",
                 ("J1", "นครพนม", "hard", "failed", "2026-06-06"))

FAKE_DL = lambda pid: "2026-06-20 16:30:00"  # noqa: E731

# ยังเป็น B0 → followup ยังไม่ควรเกิด
logs = []
ew.notify_bid_open_followups(s, logs.append, resolve_deadline=FAKE_DL)
assert s.enqueue_for_customer  # method exists
with db.get_connection() as c:
    n0 = c.execute("SELECT COUNT(*) FROM notification_queue WHERE source_stage='followed_bid_open'").fetchone()[0]
assert n0 == 0, f"ยังไม่ควร enqueue ตอน B0 (got {n0})"

# งานเลื่อน B0→D0 (advance-stage)
disc.ingest([{"project_id": "J1", "project_status": "", "announce_type": "D0",
              "province": "นครพนม", "budget": 500000, "project_name": "งานถนน คสล. ต.บ้านแพง",
              "dept_name": "อบต.บ้านแพง", "announce_date": "2026-06-05"}])

# followup ควรเกิด → enqueue ให้ cust + mark D0 + resolve+เก็บ deadline
sent = ew.notify_bid_open_followups(s, logs.append, resolve_deadline=FAKE_DL)
assert sent == 1, (sent, logs)
with db.get_connection() as c:
    row = c.execute("SELECT customer_id, source_stage, status FROM notification_queue "
                    "WHERE project_id='J1' AND source_stage='followed_bid_open'").fetchone()
    dl = c.execute("SELECT deadline FROM project_locations WHERE project_id='J1'").fetchone()[0]
assert row and row[0] == cid and row[2] == "pending", row
assert dl == "2026-06-20 16:30:00", f"deadline ควรถูก resolve+เก็บ: {dl}"
# mark D0 → ไม่ enqueue ซ้ำรอบสอง
sent2 = ew.notify_bid_open_followups(s, logs.append, resolve_deadline=FAKE_DL)
assert sent2 == 0, sent2

print("✅ PASS bid-open followup pass (B0→D0 targeted enqueue + dedup)")
