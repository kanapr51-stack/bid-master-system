"""test_winner_poller.py — poll_winners: ได้ผล→แจ้ง+เก็บ+ปิด · ไม่มีผล→รอ · เกิน max_days→ปิด."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()
import Sebastian_Winner_Poller as wp  # noqa: E402

s = db.SubscriptionStore()
c1 = s.add_customer("U1", "พ่อ")
with db.get_connection() as conn:
    for pid, name in [("W1", "ถนน A"), ("W2", "ถนน B"), ("W3", "ถนน C")]:
        conn.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name) "
                     "VALUES (?,?,?,?,?,?)", (pid, "D0", "นครพนม", "province_api", "2026-05-01", name))

# W1: ติดตาม (ถึง D0) + จะมีผล → ควรแจ้ง+ปิด
s.add_follow(c1, "W1", "D0", "2026-06-01T00:00:00"); s.mark_stage_notified(c1, "W1", "D0")
# W2: ติดตาม + ยังไม่มีผล + เพิ่งติดตาม → ควรคงไว้
s.add_follow(c1, "W2", "D0", "2026-06-05T00:00:00"); s.mark_stage_notified(c1, "W2", "D0")
# W3: ติดตาม + ไม่มีผล + ติดตามนานเกิน 60 วัน → ปิด (stale)
s.add_follow(c1, "W3", "D0", "2026-03-01T00:00:00"); s.mark_stage_notified(c1, "W3", "D0")

def fake_resolve(pid):
    if pid == "W1":
        return {"winner": "บ.A", "winning_price": "950000",
                "bidders": [{"receiveNameTh": "บ.A", "receiveTin": "1", "priceProposal": "950000",
                             "priceAgree": "950000"},
                            {"receiveNameTh": "บ.B", "receiveTin": "2", "priceProposal": "1100000",
                             "priceAgree": ""}]}
    return {}  # W2, W3 ยังไม่มีผล

stats = wp.poll_winners(s, fake_resolve, now="2026-06-06T00:00:00", log=lambda m: None, max_days=60)

# W1 → แจ้ง + เก็บ bid_results + mark W0 + close
assert stats["notified"] == 1, stats
with db.get_connection() as c:
    q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='W1' AND source_stage='followed_winner'").fetchone()[0]
assert q == 1, f"ควร enqueue winner: {q}"
assert len(s.get_bid_results("W1")) == 2, "ควรเก็บ bid_results"
assert not any(f["project_id"] == "W1" for f in s.get_active_follows()), "W1 ควรถูกปิด"
# W2 ยังคงอยู่ (รอผล)
assert any(f["project_id"] == "W2" for f in s.get_active_follows()), "W2 ควรยังตามอยู่"
# W3 stale → ปิด
assert not any(f["project_id"] == "W3" for f in s.get_active_follows()), "W3 ควรปิด (stale)"
assert stats["closed_stale"] == 1, stats

print("✅ PASS winner poller")
