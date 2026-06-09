"""test_winner_poller_prelim.py — stage machine D0→PRELIM→W0 (inject resolvers)."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
                 "VALUES ('U','n','trial',1,'t','t')")
    conn.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
                 "VALUES ('PA','งานA','D0','นครพนม',1000000,'t')")
import Sebastian_Winner_Poller as wp
store = db.SubscriptionStore()
store.add_follow(1, "PA", "D0")   # follow @ D0

# รอบ 1: prelim มี → Round 1 + mark PRELIM
stats = wp.poll_winners(store, lambda pid: {},   # formal ยังไม่มี
                        resolve_prelim=lambda pid: {"has_summary": True, "has_price": True,
                                                    "lowest_price": 740000, "num_bidders": 3, "revealed_at": "x"})
with db.get_connection() as c:
    q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='PA' AND source_stage='followed_prelim'").fetchone()[0]
    st = c.execute("SELECT last_stage_notified FROM followed_jobs WHERE project_id='PA'").fetchone()[0]
assert q == 1 and st == "PRELIM", (q, st)

# รอบ 2: formal มี → Round 2 + mark W0 + close
stats2 = wp.poll_winners(store, lambda pid: {"winner": "หจก.X", "winning_price": "738000",
                                             "bidders": [{"bidder_name": "หจก.X", "is_winner": True}]},
                         resolve_prelim=lambda pid: {"has_summary": False})
with db.get_connection() as c:
    qw = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='PA' AND source_stage='followed_winner'").fetchone()[0]
    active = c.execute("SELECT COUNT(*) FROM followed_jobs WHERE project_id='PA' AND status='active'").fetchone()[0]
assert qw == 1 and active == 0, (qw, active)   # ยิง winner + ปิด follow
print("OK test_winner_poller_prelim")
