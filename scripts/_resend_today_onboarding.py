"""_resend_today_onboarding.py — one-off: intro ปุ่ม ⭐/❌ + ส่งงานวันนี้ใหม่ (มีปุ่ม ⭐) ให้ทุกคน.
push ตรง (เลี่ยง queue/dedup, คุม order) — reuse LINE_Sender. ⭐ tap → handler เดิม → followed_jobs.
รัน: python _resend_today_onboarding.py            (dry-run, preview)
     python _resend_today_onboarding.py --live     (ส่งจริง)
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_LINE_Sender import (  # noqa: E402
    format_notification, build_job_flex, send_line_flex, send_line_push)

DB = "/opt/bms/data/bms_customers.db"
ENV = "/opt/bms/app/.env"

INTRO = (
    "🔔 BMS อัปเดตใหม่ — ปุ่ม “ติดตามงาน” ⭐\n\n"
    "ตั้งแต่นี้ การ์ดงานแต่ละใบจะมี 2 ปุ่ม:\n\n"
    "⭐ ติดตามงานนี้\n"
    "= งานที่สนใจ กดเลย ระบบจะจำไว้ แล้วแจ้งอัตโนมัติเมื่อ\n"
    "  • งานเปิดประมูล (จากขั้นรับฟังคำวิจารณ์)\n"
    "  • ประกาศผู้ชนะ\n\n"
    "❌ ไม่เกี่ยว\n"
    "= งานที่ไม่เกี่ยวกับเรา กดเพื่อช่วยให้ระบบแม่นขึ้น\n\n"
    "เดี๋ยวจะส่งงานของวันนี้ให้ใหม่ ลองกด ⭐ งานที่อยากติดตามดูนะครับ 🙏"
)


def load_token():
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("LINE_CHANNEL_ACCESS_TOKEN"):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("no LINE token")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    token = load_token()
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row

    customers = [dict(r) for r in c.execute(
        "SELECT id, line_user_id, display_name FROM customers "
        "WHERE active=1 AND COALESCE(is_test_data,0)=0").fetchall()]
    # งานวันนี้ (distinct จาก notification_queue sent วันนี้) + ข้อมูลจาก projects_seen
    jobs = [dict(r) for r in c.execute("""
        SELECT DISTINCT nq.project_id, ps.province, ps.budget, ps.project_name,
               ps.dept_name, ps.announce_type, nq.source_stage
        FROM notification_queue nq LEFT JOIN projects_seen ps ON ps.project_id = nq.project_id
        WHERE nq.status='sent' AND nq.created_at >= '2026-06-06'
        ORDER BY ps.budget DESC
    """).fetchall()]
    print(f"customers: {len(customers)} | jobs วันนี้: {len(jobs)} | mode={'LIVE' if args.live else 'DRY-RUN'}")
    print(f"จะส่ง = {len(customers)} intro + {len(customers)*len(jobs)} การ์ด = {len(customers)*(1+len(jobs))} ข้อความ\n")
    for j in jobs:
        print(f"  - {j['project_id']} | ฿{int(j['budget'] or 0):,} | {(j['project_name'] or '')[:50]}")
    print()

    sent = 0
    for cust in customers:
        uid = cust["line_user_id"]; nm = cust["display_name"]
        if args.live:
            ok, et, em = send_line_push(token, uid, INTRO)
            if ok: sent += 1
            else: print(f"  ✗ intro→{nm}: {em}")
            time.sleep(0.4)
        else:
            print(f"  [DRY] intro → {nm}")
        for j in jobs:
            text = format_notification(
                project_id=j["project_id"], province=j["province"] or "",
                announce_type=j["announce_type"] or "B0", budget=j["budget"] or 0,
                project_name=j["project_name"] or "", dept_name=j["dept_name"] or "",
                source_stage=j["source_stage"] or "province_tor_review")
            if args.live:
                title = (j["project_name"] or j["project_id"])
                flex = build_job_flex(j["project_id"], title, text, doc_url="", with_feedback=True)
                ok, et, em = send_line_flex(token, uid, (title + " | " + text)[:400], flex)
                if ok: sent += 1
                else: print(f"  ✗ {j['project_id']}→{nm}: {em}")
                time.sleep(0.4)
            else:
                print(f"  [DRY] {j['project_id']} → {nm}")
    print(f"\n{'ส่งจริง' if args.live else 'จะส่ง'}: {sent if args.live else len(customers)*(1+len(jobs))} ข้อความ")


if __name__ == "__main__":
    main()
