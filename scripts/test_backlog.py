"""test_backlog.py — undelivered_backlog (งานที่ส่งไม่ออกช่วง quota เต็ม) + ข้อความ digest."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import init_schema, get_connection
import bid_open
import Sebastian_Backlog_Digest as bd

init_schema()


def _seen(c, pid, name, deadline=None, dtime=None):
    c.execute("INSERT INTO projects_seen (project_id, project_name, first_seen_at) VALUES (?,?,'t')", (pid, name))
    if deadline:
        c.execute("INSERT INTO project_locations (project_id, deadline, deadline_time, created_at) VALUES (?,?,?,'t')",
                  (pid, deadline, dtime))


def _log(c, pid, status, at, test=0, etype="retryable"):
    c.execute("INSERT INTO delivery_log (customer_id, project_id, channel, status, error_type, attempted_at, is_test_data) "
              "VALUES (1,?, 'line',?,?,?,?)", (pid, status, etype, at, test))


with get_connection() as c:
    c.execute("INSERT INTO customers (id,line_user_id,display_name,active,created_at,updated_at) VALUES (1,'U1','ก',1,'t','t')")
    _seen(c, "P_FAIL1", "ถนน 1", "2026-07-05", "09.00-12.00 น.")
    _seen(c, "P_FAIL2", "ถนน 2", "2026-07-02", "13.00-16.00 น.")
    _seen(c, "P_SENT",  "ถนน ส่งแล้ว", "2026-07-03")
    _seen(c, "P_CLOSED", "ถนน ปิดแล้ว", "2026-06-22")
    _seen(c, "P_OLD",   "ถนน เก่า", "2026-07-10")
    _seen(c, "P_TEST",  "งานเทส", "2026-07-09")
    _log(c, "P_FAIL1", "failed", "2026-06-24T08:00:00+07:00")
    _log(c, "P_FAIL2", "failed", "2026-06-25T08:00:00+07:00")
    _log(c, "P_SENT",  "failed", "2026-06-24T08:00:00+07:00")
    _log(c, "P_SENT",  "sent",   "2026-06-26T08:00:00+07:00")            # ส่งสำเร็จแล้ว → ไม่อยู่ backlog
    _log(c, "P_CLOSED", "failed", "2026-06-24T08:00:00+07:00")           # deadline ผ่าน → กรองออก
    _log(c, "P_OLD",   "failed", "2026-06-10T08:00:00+07:00")            # ก่อน since → กรองออก
    _log(c, "P_TEST",  "failed", "2026-06-24T08:00:00+07:00", test=1)    # test → ไม่นับ

with get_connection() as c:
    jobs = bid_open.undelivered_backlog(c, 1, since="2026-06-20", min_deadline="2026-06-24")
    ids = [j["project_id"] for j in jobs]
    assert ids == ["P_FAIL2", "P_FAIL1"], ids        # เรียง deadline ใกล้สุดก่อน (07-02 ก่อน 07-05)
    assert jobs[0]["name"] == "ถนน 2" and jobs[0]["deadline_time"] == "13.00-16.00 น.", jobs[0]
    # customer ไม่มี backlog → []
    assert bid_open.undelivered_backlog(c, 99, since="2026-06-20", min_deadline="2026-06-24") == []
print("OK undelivered_backlog")

# --- ข้อความ digest ---
JOBS = [{"project_id": "P1", "name": "ถนน A", "deadline": "2026-07-02", "deadline_time": "09.00-12.00 น."},
        {"project_id": "P2", "name": "ถนน B", "deadline": "2026-07-05", "deadline_time": ""}]
m = bd.build_backlog_message("ก", JOBS, link_fn=lambda pid: f"https://x/{pid}", portal_link="https://x/p")
assert "2 งาน" in m and "ถนน A" in m and "ถนน B" in m, m
assert "https://x/P1" in m and "https://x/p" in m, m
print("OK build_backlog_message")
print("OK test_backlog")
