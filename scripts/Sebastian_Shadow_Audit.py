"""
Sebastian_Shadow_Audit.py — RSS Shadow Mode audit รายวัน (2026-06-03)

รายงานเสมอ (ไม่ว่าสำเร็จหรือพบ gap) — heartbeat ว่า audit ยังทำงาน.
gap = งาน RSS-first ที่ resolve เป็นจังหวัดเป้าหมาย แต่ Discovery ไม่ประทับตรา
      และ RSS first_seen เกิน 24 ชม = Discovery น่าจะพลาดจริง.

Run: วันละครั้ง 21:00 ไทย (14:00 UTC) via systemd timer bms-shadow-audit
"""
import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

DB_PATH = os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"), "bms_customers.db")
GAP_HOURS = 24
TARGET = ("นครพนม", "บึงกาฬ")


def _discord(msg: str) -> None:
    try:
        from Sebastian_Discord_Notify import load_env, get_credentials, send
        load_env()
        t, ch = get_credentials()
        send(t, ch, msg)
    except Exception as e:
        print(f"discord fail (non-fatal): {e}")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")

    # Discovery ส่ง user วันนี้ (notification_queue ที่สร้างวันนี้)
    sent_today = conn.execute(
        "SELECT COUNT(DISTINCT project_id) FROM notification_queue "
        "WHERE substr(created_at,1,10)=?", (today,)
    ).fetchone()[0]

    # gap: RSS-first + resolve target + ยังไม่ประทับตรา + RSS เจอเกิน 24 ชม
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=GAP_HOURS)).isoformat()
    gap_rows = conn.execute("""
        SELECT pl.project_id, pl.province_name, ps.project_name, ps.first_seen_at
        FROM project_locations pl
        JOIN projects_seen ps ON ps.project_id = pl.project_id
        WHERE ps.source='rss' AND pl.discovery_confirmed=0
          AND pl.province_name IN (?, ?)
          AND ps.first_seen_at < ?
        ORDER BY ps.first_seen_at
    """, (*TARGET, cutoff)).fetchall()
    conn.close()

    lines = ["📊 RSS Shadow Audit รายวัน", f"• Discovery ส่ง user วันนี้: {sent_today} งาน",
             f"• RSS เห็นแต่ Discovery พลาด >{GAP_HOURS}ชม: {len(gap_rows)} งาน"]
    if gap_rows:
        lines.append(f"• สถานะ: ⚠️ พบ gap {len(gap_rows)} งาน — ตรวจว่า Discovery พลาดจริงไหม")
        for r in gap_rows[:8]:
            lines.append(f"  - {r['project_id']} | {r['province_name']} | {(r['project_name'] or '')[:38]}")
    else:
        lines.append("• สถานะ: ✅ Discovery จับครบ (พิสูจน์ value กำลังไปได้ดี)")
    _discord("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
