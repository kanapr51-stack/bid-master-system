"""test_portal_routes.py — /portal/job + /portal/company ผ่าน async handler + token เดิม."""
import os, sys, asyncio, tempfile
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["BMS_DATA_DIR"] = tmp
os.environ["BMS_DB_PATH"] = str(Path(tmp) / "bms_customers.db")
os.environ["BMS_FOLLOW_SECRET"] = "test-secret-123"
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
with db.get_connection() as c:
    c.execute("INSERT INTO customers (line_user_id,display_name,tier,active,created_at,updated_at) "
              "VALUES ('U','n','trial',1,'t','t')")
    c.execute("INSERT INTO projects_seen (project_id,project_name,announce_type,province,budget,first_seen_at) "
              "VALUES ('69010000001','งานถนน A','D0','นครพนม',1000000,'t')")
    c.execute("INSERT INTO bid_results (project_id,bidder_name,bidder_tin,price_proposal,price_agree,is_winner,is_sme,fetched_at) "
              "VALUES ('69010000001','หจก.เอ','T1','900000','900000',1,0,'t')")

import bms_api as api
import follow_token
tok = follow_token.make_token("U", None)

r = asyncio.run(api.portal_job_get(t=tok, pid="69010000001"))
body = r.body.decode("utf-8")
assert "งานถนน A" in body and "หจก.เอ" in body and "ส่วนลด 10.0%" in body, body[:400]

rc = asyncio.run(api.portal_company_get(t=tok, tin="T1", from_="69010000001"))
bodyc = rc.body.decode("utf-8")
assert "หจก.เอ" in bodyc and "ยื่น" in bodyc, bodyc[:400]

rbad = asyncio.run(api.portal_job_get(t="BAD", pid="69010000001"))
assert "ลิงก์ไม่ถูกต้อง" in rbad.body.decode("utf-8") or "ใช้ไม่ได้" in rbad.body.decode("utf-8")
print("OK test_portal_routes")
