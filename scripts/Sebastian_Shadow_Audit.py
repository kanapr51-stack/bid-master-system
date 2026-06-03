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


def _age_hours(iso_ts: str) -> float:
    """ชม. ตั้งแต่ first_seen (robust parse). RSS first_seen = _now() ไทย (+07:00)."""
    try:
        t = datetime.fromisoformat(iso_ts)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone(timedelta(hours=7)))
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except Exception:
        return 0.0


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")

    # Discovery ส่ง user วันนี้ (notification_queue ที่สร้างวันนี้)
    sent_today = conn.execute(
        "SELECT COUNT(DISTINCT project_id) FROM notification_queue "
        "WHERE substr(created_at,1,10)=?", (today,)
    ).fetchone()[0]

    # ── Leading indicators (ADR-001): RSS target resolved → confirmed rate + backlog ──
    rss_target = conn.execute("""
        SELECT pl.discovery_confirmed AS dc, ps.first_seen_at AS fs
        FROM project_locations pl
        JOIN projects_seen ps ON ps.project_id = pl.project_id
        WHERE ps.source='rss' AND pl.province_name IN (?, ?)
    """, TARGET).fetchall()
    total = len(rss_target)
    confirmed = sum(1 for r in rss_target if r["dc"])
    confirmed_rate = (confirmed / total * 100) if total else 100.0

    # shadow backlog (confirmed=0) + age distribution
    buckets = {"0-6": 0, "6-12": 0, "12-24": 0, ">24": 0}
    for r in rss_target:
        if r["dc"]:
            continue
        age = _age_hours(r["fs"])
        if age < 6:
            buckets["0-6"] += 1
        elif age < 12:
            buckets["6-12"] += 1
        elif age < 24:
            buckets["12-24"] += 1
        else:
            buckets[">24"] += 1
    backlog = sum(buckets.values())

    # gap detail (lagging, >24 ชม) — project list สำหรับตรวจ
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=GAP_HOURS)).isoformat()
    gap_rows = conn.execute("""
        SELECT pl.project_id, pl.province_name, ps.project_name
        FROM project_locations pl
        JOIN projects_seen ps ON ps.project_id = pl.project_id
        WHERE ps.source='rss' AND pl.discovery_confirmed=0
          AND pl.province_name IN (?, ?)
          AND ps.first_seen_at < ?
        ORDER BY ps.first_seen_at
    """, (*TARGET, cutoff)).fetchall()
    conn.close()

    lines = [
        "📊 RSS Shadow Audit รายวัน",
        f"• Discovery ส่ง user วันนี้: {sent_today} งาน",
        f"• Shadow backlog (RSS target, confirmed=0): {backlog} งาน",
        f"    อายุ: 0-6ชม {buckets['0-6']} · 6-12ชม {buckets['6-12']} · "
        f"12-24ชม {buckets['12-24']} · >24ชม {buckets['>24']}",
        f"• confirmed rate: {confirmed_rate:.0f}% ({confirmed}/{total} RSS target resolved)",
        f"• RSS เห็นแต่ Discovery พลาด >{GAP_HOURS}ชม: {len(gap_rows)} งาน",
    ]
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
