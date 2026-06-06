"""test_star_metrics.py — ⭐ Follow telemetry readout (pull-based, observe phase)."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()
import star_metrics as sm  # noqa: E402

s = db.SubscriptionStore()
c1 = s.add_customer("U1", "พ่อ")
c2 = s.add_customer("U2", "แม่")

with db.get_connection() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "customer_id INTEGER NOT NULL, project_id TEXT, action TEXT NOT NULL, "
                 "raw_text TEXT, created_at TEXT NOT NULL)")
    # 10 งานที่ส่งแล้ว (sent)
    for i in range(10):
        conn.execute("INSERT INTO notification_queue (customer_id,project_id,status,created_at,source_stage) "
                     "VALUES (?,?,?,?,?)", (c1, f"J{i}", "sent", "2026-06-05T10:00:00", "api_enriched"))
    # ชื่องาน (สำหรับ category)
    for pid, name in [("J0", "ก่อสร้างถนน คสล."), ("J1", "ก่อสร้างอาคารสำนักงาน"), ("J2", "วางท่อระบายน้ำ")]:
        conn.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name) "
                     "VALUES (?,?,?,?,?,?)", (pid, "D0", "นครพนม", "province_api", "2026-06-05", name))
    # ❌ irrelevant 1
    conn.execute("INSERT INTO feedback (customer_id,project_id,action,raw_text,created_at) VALUES (?,?,?,?,?)",
                 (c1, "J9", "irrelevant", "", "2026-06-05T11:00:00"))

# ⭐: J0 (B0→D0 converted), J1 (B0 ยังไม่ convert), J2 (starred ตอน D0)
s.add_follow(c1, "J0", "B0", "2026-06-05T10:00:00"); s.mark_stage_notified(c1, "J0", "D0")
s.add_follow(c1, "J1", "B0", "2026-06-05T10:00:00")
s.add_follow(c2, "J2", "D0", "2026-06-05T10:00:00")

m = sm.compute_metrics(days=14, now="2026-06-06T00:00:00")
assert m["sent"] == 10, m["sent"]
assert m["stars"] == 3, m["stars"]
assert m["dismiss"] == 1, m["dismiss"]
# B0 conversion: B0 stars=2 (J0,J1), converted=1 (J0) → 50%
assert m["b0_total"] == 2 and m["b0_converted"] == 1, (m["b0_total"], m["b0_converted"])
# categories
cats = dict(m["top_categories"])
assert cats.get("ถนน") == 1 and cats.get("อาคาร") == 1 and cats.get("ระบายน้ำ/ชลประทาน") == 1, cats
# recent stars มีชื่องาน
assert len(m["recent_stars"]) == 3, m["recent_stars"]
# render ไม่ error + มีหัวข้อ
text = sm.render(m)
assert "Follow Metrics" in text and "ถนน" in text, text

print("✅ PASS star_metrics")
