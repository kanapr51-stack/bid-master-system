"""star_metrics.py — ⭐ Follow telemetry readout (pull-based, ช่วง Observe).

รัน: python scripts/star_metrics.py [--days 14]
ตั้งใจให้ "หยิบดูเมื่ออยากดู" — ยังไม่แปะ daily digest อัตโนมัติ (กัญจน์ 2026-06-06).
⚠️ N=5 (ครอบครัว) → ตัวเลขเป็น **directional** ไม่ใช่ statistical. 1 คำตอบจากพ่อ > Star Rate ทั้งสัปดาห์.
"""
import argparse
import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import get_connection  # noqa: E402

# หมวดงาน (implicit preference — รู้ใจครอบครัวโดยไม่ต้องถาม). bucket แบบ directional ไม่ใช่ classifier เต็ม
_CATS = [
    ("ถนน", ["ถนน", "ผิวจราจร", "ผิวทาง", "ลาดยาง", "ไหล่ทาง", "แอสฟัล", "เสริมผิว"]),
    ("อาคาร", ["อาคาร", "ห้อง", "หอประชุม", "สำนักงาน", "โรงเรือน", "ที่ทำการ", "โดม"]),
    ("ระบายน้ำ/ชลประทาน", ["ระบายน้ำ", "ราง", "ท่อ", "ฝาย", "ขุดลอก", "เขื่อน", "ตลิ่ง", "ลำห้วย", "คลอง"]),
    ("ประปา", ["ประปา", "น้ำประปา", "หอถัง", "ถังเก็บน้ำ"]),
    ("ไฟฟ้า", ["ไฟฟ้า", "โซล่า", "ฟีดเดอร์", "แสงอาทิตย์", "ระบบจำหน่าย"]),
]


def categorize(name: str) -> str:
    name = name or ""
    for cat, kws in _CATS:
        if any(k in name for k in kws):
            return cat
    return "อื่นๆ"


def compute_metrics(days: int = 14, now: str = None) -> dict:
    """อ่าน 4 metrics + recent stars + top categories จาก DB. now=ISO (เทสฉีดได้)."""
    nowdt = _dt.datetime.fromisoformat(now) if now else _dt.datetime.now()
    cutoff = (nowdt - _dt.timedelta(days=days)).isoformat()
    with get_connection() as conn:
        conn.row_factory = None
        sent = conn.execute(
            "SELECT COUNT(*) FROM notification_queue WHERE status='sent' AND created_at >= ?",
            (cutoff,)).fetchone()[0]
        stars = conn.execute(
            "SELECT COUNT(*) FROM followed_jobs WHERE starred_at >= ?", (cutoff,)).fetchone()[0]
        try:
            dismiss = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE action='irrelevant' AND created_at >= ?",
                (cutoff,)).fetchone()[0]
        except Exception:
            dismiss = 0  # feedback table อาจยังไม่ถูกสร้าง (migrate_feedback_schema แยก)
        # B0 conversion (lifetime — conversion ใช้เวลา): B0 stars → ที่ขยับถึง D0/W0
        b0_total = conn.execute(
            "SELECT COUNT(*) FROM followed_jobs WHERE starred_stage LIKE 'B%'").fetchone()[0]
        b0_converted = conn.execute(
            "SELECT COUNT(*) FROM followed_jobs WHERE starred_stage LIKE 'B%' "
            "AND last_stage_notified IN ('D0','W0')").fetchone()[0]
        # weekly retention (distinct ผู้กด ⭐ ต่อสัปดาห์)
        retention = conn.execute(
            "SELECT strftime('%Y-W%W', starred_at) wk, COUNT(DISTINCT customer_id) "
            "FROM followed_jobs GROUP BY wk ORDER BY wk DESC LIMIT 4").fetchall()
        # recent stars + ชื่อ
        recent = conn.execute(
            "SELECT f.project_id, COALESCE(ps.project_name,'') FROM followed_jobs f "
            "LEFT JOIN projects_seen ps ON ps.project_id=f.project_id "
            "ORDER BY f.starred_at DESC LIMIT 6").fetchall()
        # top categories (จากทุกงานที่ติดดาว)
        names = conn.execute(
            "SELECT COALESCE(ps.project_name,'') FROM followed_jobs f "
            "LEFT JOIN projects_seen ps ON ps.project_id=f.project_id").fetchall()
    cat_count = {}
    for (nm,) in names:
        cat_count[categorize(nm)] = cat_count.get(categorize(nm), 0) + 1
    top_categories = sorted(cat_count.items(), key=lambda x: -x[1])
    return {
        "days": days, "sent": sent, "stars": stars, "dismiss": dismiss,
        "star_rate": (stars / sent * 100) if sent else 0.0,
        "dismiss_rate": (dismiss / sent * 100) if sent else 0.0,
        "b0_total": b0_total, "b0_converted": b0_converted,
        "b0_conv_rate": (b0_converted / b0_total * 100) if b0_total else 0.0,
        "retention": [(r[0], r[1]) for r in retention],
        "recent_stars": [(r[0], r[1]) for r in recent],
        "top_categories": top_categories,
    }


def render(m: dict) -> str:
    L = [f"⭐ BMS Follow Metrics (Last {m['days']} days)", ""]
    L.append(f"Sent jobs:   {m['sent']}")
    L.append(f"⭐ Stars:     {m['stars']} ({m['star_rate']:.1f}%)")
    L.append(f"❌ Irrelevant: {m['dismiss']} ({m['dismiss_rate']:.1f}%)")
    L.append("")
    L.append(f"B0⭐ → D0 conversion: {m['b0_converted']}/{m['b0_total']} ({m['b0_conv_rate']:.0f}%)")
    L.append("")
    L.append("Weekly retention (distinct ผู้กด ⭐):")
    for wk, n in m["retention"] or [("—", 0)]:
        L.append(f"  {wk}: {n} users")
    L.append("")
    L.append("⭐ Top followed categories:")
    for cat, n in m["top_categories"] or []:
        L.append(f"  {cat:18} {n} ⭐")
    L.append("")
    L.append("Recent stars:")
    for pid, name in m["recent_stars"]:
        L.append(f"  - {(name or pid)[:48]}")
    L.append("")
    L.append("⚠️ N=5 → directional เท่านั้น. คุยกับพ่อ > ตัวเลข.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(render(compute_metrics(days=args.days)))


if __name__ == "__main__":
    main()
