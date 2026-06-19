"""test_portal_views.py — job_detail + company_profile + render (Portal detail/company)."""
import os, sys, sqlite3, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _seed():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE projects_seen(project_id TEXT, project_name TEXT, budget REAL, province TEXT)")
    c.execute("CREATE TABLE bid_results(project_id TEXT, bidder_name TEXT, bidder_tin TEXT, "
              "price_proposal TEXT, price_agree TEXT, is_winner INT, is_sme INT)")
    c.execute("CREATE TABLE project_locations(project_id TEXT, moi_name TEXT, province_name TEXT)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000001','งานถนน A',1000000,'นครพนม')")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.เอ','T1','900000','900000',1,0)")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.บี','T2','800000','',0,1)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000002','งานไม่มีราคากลาง',0,'บึงกาฬ')")
    c.execute("INSERT INTO bid_results VALUES ('69010000002','หจก.เอ','T1','500000','',0,0)")
    return c


# --- job_detail ---
c = _seed()
d = pv.job_detail(c, "69010000001")
assert d["job"]["budget"] == 1000000 and d["job"]["name"] == "งานถนน A", d["job"]
assert len(d["bidders"]) == 2, d["bidders"]
assert d["bidders"][0]["is_winner"] and d["bidders"][0]["name"] == "หจก.เอ", d["bidders"]
assert d["bidders"][0]["discount"] == 10.0, d["bidders"][0]      # 1 - 900000/1000000
assert d["bidders"][1]["is_sme"] is True, d["bidders"][1]
d2 = pv.job_detail(c, "69010000002")
assert d2["bidders"][0]["discount"] is None, d2                  # budget=0
assert pv.job_detail(c, "NOPE") is None
print("OK job_detail")
