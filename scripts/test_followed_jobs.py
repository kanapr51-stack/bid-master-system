"""test_followed_jobs.py — ⭐ watchlist upsert + stage dedup + B0→D0 followers."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402

db.init_schema()
s = db.SubscriptionStore()

# add follow
s.add_follow(customer_id=2, project_id="P1", starred_stage="B0", now="2026-06-06T10:00:00")
act = s.get_active_follows()
assert any(f["project_id"] == "P1" and f["customer_id"] == 2 for f in act), act
assert [f for f in act if f["project_id"] == "P1"][0]["last_stage_notified"] == "B0"

# upsert idempotent (กดซ้ำ)
s.add_follow(2, "P1", "B0", "2026-06-06T11:00:00")
assert len([f for f in s.get_active_follows() if f["project_id"] == "P1" and f["customer_id"] == 2]) == 1

# mark stage notified
s.mark_stage_notified(2, "P1", "D0")
assert [f for f in s.get_active_follows() if f["project_id"] == "P1"][0]["last_stage_notified"] == "D0"

# close → ไม่อยู่ active
s.close_follow("P1", 2)
assert not any(f["project_id"] == "P1" and f["customer_id"] == 2 for f in s.get_active_follows())

# ── B0→D0 followers (job_followups) ──
s.add_follow(3, "P2", "B0", "2026-06-06T09:00:00")
import job_followups as jf  # noqa: E402
assert jf.followers_due_for_stage(s, "P2", "D0") == [3], jf.followers_due_for_stage(s, "P2", "D0")
s.mark_stage_notified(3, "P2", "D0")
assert jf.followers_due_for_stage(s, "P2", "D0") == []
# งานที่ไม่มีคนติดตาม → ว่าง
assert jf.followers_due_for_stage(s, "P_NONE", "D0") == []

# ── bid_open_followups: ติดดาวตอน B0 + งานเลื่อนเป็น D แล้ว → ต้องแจ้ง ──
follows = [
    {"customer_id": 5, "project_id": "X1", "last_stage_notified": "B0"},  # B0 → D = แจ้ง
    {"customer_id": 6, "project_id": "X2", "last_stage_notified": "D0"},  # แจ้ง D แล้ว = ข้าม
    {"customer_id": 7, "project_id": "X3", "last_stage_notified": "B0"},  # ยังเป็น B0 = ข้าม
]
current = {"X1": "D0", "X2": "D0", "X3": "B0"}
due = jf.bid_open_followups(follows, current)
assert due == [(5, "X1")], due

print("✅ PASS followed_jobs + job_followups")
