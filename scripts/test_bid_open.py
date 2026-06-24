"""test_bid_open.py — bid_open_for_customer: งานยื่นซอง=วันเป้าหมาย ใน scope delivery_log (non-test)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import init_schema, get_connection
import bid_open

init_schema()
with get_connection() as c:
    c.execute("INSERT INTO customers (id,line_user_id,display_name,active,created_at,updated_at) "
              "VALUES (1,'U1','ก',1,'t','t')")
    for pid, name in [("P_TODAY", "ถนน วันนี้"), ("P_TMRW", "ถนน พรุ่งนี้"),
                      ("P_OTHER", "ถนน วันอื่น"), ("P_TEST", "งานเทส")]:
        c.execute("INSERT INTO projects_seen (project_id, project_name, first_seen_at) VALUES (?,?,'t')", (pid, name))
    # deadline จาก project_locations (TODAY, OTHER, TEST) + จาก enrichment fallback (TMRW)
    c.execute("INSERT INTO project_locations (project_id, deadline, deadline_time, created_at) "
              "VALUES ('P_TODAY','2026-06-24','09.00-12.00 น.','t')")
    c.execute("INSERT INTO project_enrichments (project_id, parser_version, enrichment_status, parsed_at, "
              "bid_submit_date, bid_submit_time) VALUES ('P_TMRW','v1','success','t','2026-06-25','13.00-16.00 น.')")
    c.execute("INSERT INTO project_locations (project_id, deadline, created_at) VALUES ('P_OTHER','2026-07-01','t')")
    c.execute("INSERT INTO project_locations (project_id, deadline, deadline_time, created_at) "
              "VALUES ('P_TEST','2026-06-24','09.00 น.','t')")
    # delivery_log: customer 1 match P_TODAY/P_TMRW/P_OTHER (non-test); P_TEST = test_data
    for pid in ["P_TODAY", "P_TMRW", "P_OTHER"]:
        c.execute("INSERT INTO delivery_log (customer_id, project_id, channel, status, attempted_at, is_test_data) "
                  "VALUES (1,?, 'line','sent','t',0)", (pid,))
    c.execute("INSERT INTO delivery_log (customer_id, project_id, channel, status, attempted_at, is_test_data) "
              "VALUES (1,'P_TEST','line','sent','t',1)")

with get_connection() as c:
    today = bid_open.bid_open_for_customer(c, 1, "2026-06-24")
    assert [j["project_id"] for j in today] == ["P_TODAY"], today          # วันนี้ → เฉพาะ P_TODAY (P_TEST ถูกกรอง)
    assert today[0]["name"] == "ถนน วันนี้" and today[0]["deadline_time"] == "09.00-12.00 น.", today

    tmrw = bid_open.bid_open_for_customer(c, 1, "2026-06-25")
    assert [j["project_id"] for j in tmrw] == ["P_TMRW"], tmrw             # พรุ่งนี้ → P_TMRW (ผ่าน enrichment fallback)
    assert tmrw[0]["deadline"] == "2026-06-25" and tmrw[0]["deadline_time"] == "13.00-16.00 น.", tmrw

    assert bid_open.bid_open_for_customer(c, 1, "2026-06-26") == []        # ไม่มีงานวันนั้น
    assert all(j["project_id"] != "P_TEST" for j in today), today          # test_data ไม่นับ
    assert bid_open.bid_open_for_customer(c, 99, "2026-06-24") == []       # customer ไม่มี delivery_log

print("OK test_bid_open")
