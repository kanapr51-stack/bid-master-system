"""test_bidopen_notify.py — message builders: bullets + แจ้งเช้า + section พรุ่งนี้ในสรุปเย็น."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import bid_open
import Sebastian_BidOpen_Morning as morning
import Sebastian_Daily_User_Summary as summary

JOBS = [{"project_id": "P1", "name": "ถนน A", "deadline": "2026-06-24", "deadline_time": "09.00-12.00 น."},
        {"project_id": "P2", "name": "ถนน B", "deadline": "2026-06-24", "deadline_time": ""}]
_link = lambda pid: f"https://x/job?pid={pid}"

# --- format_job_bullets ---
b = bid_open.format_job_bullets(JOBS, _link)
assert "1. ถนน A" in b and "⏰ 09.00-12.00 น." in b and "https://x/job?pid=P1" in b, b
assert "2. ถนน B" in b and "https://x/job?pid=P2" in b, b
# P2 ไม่มีเวลา → ไม่มีบรรทัด ⏰ ของ P2 (มี ⏰ แค่ครั้งเดียว = ของ P1)
assert b.count("⏰") == 1, b
# ไม่มี link_fn → ไม่มีลิงก์
assert "https://" not in bid_open.format_job_bullets(JOBS), bid_open.format_job_bullets(JOBS)
print("OK format_job_bullets")

# --- แจ้งเช้า ---
m = morning.build_morning_message("ก", JOBS, link_fn=_link, portal_link="https://x/portal")
assert "เปิดประมูลวันนี้" in m and "2 งาน" in m, m
assert "1. ถนน A" in m and "https://x/job?pid=P1" in m, m
assert "https://x/portal" in m, m
print("OK build_morning_message")

# --- สรุปเย็น: section พรุ่งนี้ ---
s = summary.build_message("ก", 3, tomorrow_jobs=JOBS, link_fn=_link)
assert "เจองานที่เกี่ยวกับคุณ 3 งาน" in s, s          # heartbeat เดิมคงอยู่
assert "พรุ่งนี้มีงานเปิดประมูล 2 งาน" in s, s         # section ใหม่
assert "ถนน A" in s and "ถนน B" in s, s
# ไม่มีงานพรุ่งนี้ → ไม่มี section (backward-compat: เรียกแบบเดิมได้)
s0 = summary.build_message("ก", 0)
assert "พรุ่งนี้มีงานเปิดประมูล" not in s0, s0
assert "ยังไม่มีงานใหม่" in s0, s0
print("OK build_message tomorrow section")
print("OK test_bidopen_notify")
