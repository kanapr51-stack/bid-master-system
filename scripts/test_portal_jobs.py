"""test_portal_jobs.py — _portal_jobs จัดกลุ่ม followed jobs (won/bidding/pre) + ซ่อน unfollowed."""
import os, sys, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as c:
    c.execute("INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('U','n','trial',1,'t','t')")
    cid = c.execute("SELECT id FROM customers WHERE line_user_id='U'").fetchone()[0]
    for pid, ann, nm in [("PD","D0","ถนน D0"),("PW","D0","ถนน W"),("PB","B0","ถนน B0"),
                         ("PP","D0","ถนน PRELIM"),("PU","D0","ซ่อน")]:
        c.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
                  "VALUES (?,?,?,?,?,?)", (pid, nm, ann, "บึงกาฬ", 1000000, "t"))
    # PP = stage D0 แต่แจ้ง PRELIM แล้ว (สรุปราคาเบื้องต้น ยังไม่มีผู้ชนะทางการ)
    for pid, st, lsn in [("PD","active","D0"),("PW","closed","W0"),("PB","active","D0"),
                         ("PP","active","PRELIM"),("PU","unfollowed","D0")]:
        c.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,last_stage_notified,status) "
                  "VALUES (?,?,?,?,?,?)", (cid, pid, "t", "D0", lsn, st))
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,fetched_at) "
              "VALUES ('PW','หจก.X','T1','740000','738000',1,'t')")
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,fetched_at) "
              "VALUES ('PW','หจก.Y','T2','752000','',0,'t')")
    # prelim: มีราคาเสนอ แต่ไม่มีผู้ชนะ (is_winner=0, price_agree ว่าง)
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,fetched_at) "
              "VALUES ('PP','','PT1','820000','',0,'t')")
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,fetched_at) "
              "VALUES ('PP','','PT2','795000','',0,'t')")
    c.execute("INSERT INTO price_predictions (project_id,budget,area_price_lo,area_price_hi,predicted_at) "
              "VALUES ('PD',1000000,679000,730000,'t')")
    try:
        c.execute("INSERT INTO project_locations (project_id,moi_name,deadline,deadline_time,created_at) VALUES ('PD','โพธิ์หมากแข้ง','15 มิ.ย. 2569','09.00-12.00 น.','t')")
    except Exception:
        c.execute("UPDATE project_locations SET moi_name='โพธิ์หมากแข้ง', deadline='15 มิ.ย. 2569', deadline_time='09.00-12.00 น.' WHERE project_id='PD'")

import bms_api as api
g = api._portal_jobs("U")
assert g is not None, g
assert [j["project_id"] for j in g["bidding"]] == ["PD"], g["bidding"]
assert [j["project_id"] for j in g["won"]] == ["PW"], g["won"]
assert [j["project_id"] for j in g["pre"]] == ["PB"], g["pre"]
assert [j["project_id"] for j in g["prelim"]] == ["PP"], g["prelim"]
pp = g["prelim"][0]
assert pp["prelim_low"] == 795000.0 and pp["prelim_n"] == 2, pp
allpids = [j["project_id"] for grp in g.values() for j in grp]
assert "PU" not in allpids, allpids
bd = g["bidding"][0]
assert bd["pred_lo"] == 679000 and bd["pred_hi"] == 730000, bd
assert "15 มิ.ย." in bd["deadline"] and "โพธิ์หมากแข้ง" in bd["location"], bd
assert bd["deadline_time"] == "09.00-12.00 น.", bd
w = g["won"][0]
assert w["winner"] == "หจก.X" and w["winner_price"] == 738000.0, w
assert w["winner_disc"] == 26.2, w
assert w["competitors"] and w["competitors"][0]["name"] == "หจก.Y", w
# bidders: ครบทุกราย, ผู้ชนะมาก่อน
assert len(w["bidders"]) == 2, w["bidders"]
assert w["bidders"][0]["is_winner"] and w["bidders"][0]["name"] == "หจก.X", w["bidders"]
assert not w["bidders"][1]["is_winner"], w["bidders"]
assert api._portal_jobs("NOPE") is None
print("OK test_portal_jobs")
