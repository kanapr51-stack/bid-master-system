"""bid_open.py — งานที่ "เปิดประมูล" (วันยื่นซอง = วันเป้าหมาย) ในพื้นที่ที่ระบบ match ให้ลูกค้า.

scope = distinct project ใน delivery_log (customer, non-test) = งานที่เคย surface ให้ลูกค้า
(ตรงกับนิยาม "พื้นที่ที่ subscribe" + เดียวกับที่ Daily_User_Summary นับ).
ใช้ทั้งแจ้งเช้า (today) และ section สรุปเย็น (tomorrow).
"""
import sqlite3

_SQL = """
SELECT DISTINCT dl.project_id,
       ps.project_name,
       COALESCE(pl.deadline, pe.bid_submit_date)       AS deadline,
       COALESCE(pl.deadline_time, pe.bid_submit_time)  AS deadline_time
FROM delivery_log dl
LEFT JOIN projects_seen ps        ON ps.project_id = dl.project_id
LEFT JOIN project_locations pl    ON pl.project_id = dl.project_id
LEFT JOIN project_enrichments pe  ON pe.project_id = dl.project_id
WHERE dl.customer_id = ?
  AND COALESCE(dl.is_test_data, 0) = 0
  AND substr(COALESCE(pl.deadline, pe.bid_submit_date), 1, 10) = ?
"""


def bid_open_for_customer(conn, customer_id, target_date):
    """คืน list งาน (ในพื้นที่ที่ match ให้ลูกค้า) ที่วันยื่นซอง == target_date ('YYYY-MM-DD').
    แต่ละงาน = {project_id, name, deadline, deadline_time}. graceful: error → []."""
    try:
        rows = conn.execute(_SQL, (customer_id, target_date)).fetchall()
    except sqlite3.DatabaseError:
        return []
    out = [{"project_id": r[0], "name": r[1] or r[0],
            "deadline": r[2], "deadline_time": r[3] or ""} for r in rows]
    out.sort(key=lambda j: j["name"] or "")
    return out


def format_job_bullets(jobs, link_fn=None):
    """แปลง list งาน → bullet lines (เลข. ชื่อ / ⏰ เวลา / ลิงก์). link_fn(pid)->url (None=ไม่ใส่ลิงก์)."""
    lines = []
    for i, j in enumerate(jobs, 1):
        lines.append(f"{i}. {j['name']}")
        if j.get("deadline_time"):
            lines.append(f"   ⏰ {j['deadline_time']}")
        if link_fn:
            url = link_fn(j["project_id"])
            if url:
                lines.append(f"   {url}")
    return "\n".join(lines)
