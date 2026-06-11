"""resend_d0_jobs.py — ส่ง D0 ครบวงจร (ราคา logic ใหม่ + ⏰เวลา + 📄ลิงก์ + ⭐ปุ่มปักหมุด) ของงานเฉพาะ
แบบ approval-gated: ส่งกัญจน์ก่อน → approve → ส่งคนอื่น. กัญจน์ 2026-06-11.

push ตรง (เลี่ยง queue/dedup, คุม order) — reuse LINE_Sender. ⭐ tap → handler เดิม → followed_jobs.
การ์ด D0 = format_notification (intel/คาดราคา logic ใหม่) + build_job_flex(⭐) + ลิงก์ประกาศ + เวลายื่นซอง.

usage:
  python resend_d0_jobs.py --list                                  # ดู customers + งาน (ระบุ id กัญจน์)
  python resend_d0_jobs.py --projects A,B --customer <id>          # dry-run preview (กัญจน์)
  python resend_d0_jobs.py --projects A,B --customer <id> --live    # ส่งจริง (กัญจน์ก่อน)
  python resend_d0_jobs.py --projects A,B --all-except <id> --live  # ส่งคนอื่น (หลัง approve)
"""
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import get_connection
from Sebastian_LINE_Sender import (
    format_notification, send_line_push, build_follow_link,
    _deadline_from_db, _clean_project_name, _load_line_token)
from process5_http_client import get_announce_pdf_url


def _resolve_deadline(conn, pid):
    """resolve deadline สด (DocZip — ดึงวัน+เวลาจาก PDF) + เก็บลง project_locations. คืน (date, time)."""
    import datetime as _dt
    from deadline_provider_doczip import DocZipPdfDeadlineProvider
    res = DocZipPdfDeadlineProvider().resolve(pid)
    if not res.success:
        print(f"  ⚠️ {pid}: resolve deadline ไม่สำเร็จ ({res.outcome.value}) — ใช้ค่าเดิม")
        return None, None
    d_date = res.deadline.isoformat()
    d_time = res.deadline_time or ""
    conn.execute(
        "INSERT INTO project_locations (project_id, deadline, deadline_time, created_at) "
        "VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
        "deadline=excluded.deadline, deadline_time=excluded.deadline_time",
        (pid, d_date, d_time, _dt.datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    print(f"  ✅ {pid}: resolve ใหม่ → {d_date} {d_time}")
    return d_date, d_time


def _load_jobs(conn, project_ids, resolve_deadline=False):
    jobs = []
    for pid in project_ids:
        r = conn.execute("SELECT project_id, province, budget, project_name, dept_name, announce_type "
                         "FROM projects_seen WHERE project_id=?", (pid,)).fetchone()
        if not r:
            print(f"  ⚠️ {pid}: ไม่พบใน projects_seen — ข้าม"); continue
        d_date, d_time = _deadline_from_db(pid)
        if resolve_deadline and (not d_date or not d_time):   # เติมให้ครบ (วัน/เวลา) ถ้าขาด
            nd, nt = _resolve_deadline(conn, pid)
            if nd:
                d_date, d_time = nd, nt
        jobs.append({"project_id": r[0], "province": r[1] or "", "budget": r[2] or 0,
                     "project_name": r[3] or "", "dept_name": r[4] or "",
                     "bid_date": d_date, "bid_time": d_time})
    return jobs


def _build_text(j):
    """คืน (title, body) ข้อความการ์ด D0 ครบวงจร (intel/คาดราคา + เวลายื่นซอง)."""
    body = format_notification(
        project_id=j["project_id"], province=j["province"], announce_type="D0",
        budget=j["budget"], project_name=j["project_name"], dept_name=j["dept_name"],
        bid_submit_date=j["bid_date"], bid_submit_time=j["bid_time"],
        source_stage="api_enriched")   # หัวการ์ด = "🔔 พบงานเปิดยื่นซองใหม่" (ส่งใหม่ ไม่ใช่ followup)
    title = _clean_project_name(j["project_name"]) or j["project_id"]
    return title, body


def _compose(title, body, ann, follow):
    """ประกอบข้อความเต็ม = ชื่องาน + การ์ด + 📄ลิงก์ประกาศ + ⭐ลิงก์ติดตาม (ตาม production D0)."""
    ann_block = ("\n\n📄 ดูประกาศ:\n" + ann) if ann else ""
    follow_block = ("\n\n⭐ ติดตามงานนี้:\n" + follow) if follow else ""
    return title + "\n" + body + ann_block + follow_block


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", default="", help="comma list project_ids")
    ap.add_argument("--customer", type=int, help="ส่งลูกค้ารายเดียว (id) — เฟส 1 กัญจน์")
    ap.add_argument("--all-except", type=int, dest="all_except", help="ส่งทุกคนยกเว้น id นี้ — เฟส 2")
    ap.add_argument("--all", action="store_true", help="ส่งทุกคน active")
    ap.add_argument("--list", action="store_true", help="ดู customers + งาน")
    ap.add_argument("--resolve-deadline", action="store_true", dest="resolve_deadline",
                    help="resolve deadline สด (วัน+เวลา) ถ้าขาด ก่อนสร้างการ์ด")
    ap.add_argument("--live", action="store_true", help="ส่งจริง (default = dry-run)")
    a = ap.parse_args()

    with get_connection() as conn:
        if a.list:
            print("=== active customers (non-test) ===")
            for r in conn.execute("SELECT id, line_user_id, display_name FROM customers "
                                  "WHERE active=1 AND COALESCE(is_test_data,0)=0 ORDER BY id"):
                print(f"  id={r[0]:3d}  {r[2] or '(no name)'}  [{r[1][:12]}...]")
            return

        project_ids = [p.strip() for p in a.projects.split(",") if p.strip()]
        jobs = _load_jobs(conn, project_ids, resolve_deadline=a.resolve_deadline)
        if not jobs:
            print("ไม่มีงานให้ส่ง"); return

        if a.customer:
            rows = conn.execute("SELECT id, line_user_id, display_name FROM customers WHERE id=?",
                                (a.customer,)).fetchall()
        elif a.all_except is not None:
            rows = conn.execute("SELECT id, line_user_id, display_name FROM customers WHERE active=1 "
                                "AND COALESCE(is_test_data,0)=0 AND id!=? ORDER BY id", (a.all_except,)).fetchall()
        elif a.all:
            rows = conn.execute("SELECT id, line_user_id, display_name FROM customers WHERE active=1 "
                                "AND COALESCE(is_test_data,0)=0 ORDER BY id").fetchall()
        else:
            print("ระบุเป้าหมาย: --customer <id> | --all-except <id> | --all"); return
        customers = [{"id": r[0], "uid": r[1], "name": r[2]} for r in rows]

    mode = "LIVE (ส่งจริง)" if a.live else "DRY-RUN (preview)"
    print(f"=== resend D0 — {mode} ===")
    print(f"งาน: {len(jobs)} | ลูกค้า: {len(customers)} | รวม {len(jobs)*len(customers)} ข้อความ\n")
    for j in jobs:
        print(f"  • {j['project_id']} ฿{int(j['budget']):,} ยื่นซอง {j['bid_date']} {j['bid_time']} | {j['project_name'][:45]}")
    print(f"  → ถึง: {', '.join(c['name'] or str(c['id']) for c in customers)}\n")

    token = _load_line_token() if a.live else ""
    sent = 0
    for j in jobs:
        title, body = _build_text(j)
        # ลิงก์ประกาศ = view-pdf-file?templateId=buildName2 (PDF จริง, สาธารณะ) จาก infoProcureDocAnnounZip
        ann = get_announce_pdf_url(j["project_id"])
        if not a.live:
            preview = _compose(title, body, ann, "<ลิงก์ติดตาม — สร้างต่อคนตอนส่งจริง>")
            print(f"─── การ์ด {j['project_id']} ───\n{preview}\n")
            continue
        for c in customers:
            follow = build_follow_link(c["uid"], j["project_id"])   # signed token ต่อคน-ต่องาน
            msg = _compose(title, body, ann, follow)
            ok, et, em = send_line_push(token, c["uid"], msg)
            if ok: sent += 1
            else: print(f"  ✗ {j['project_id']}→{c['name']}: {em}")
            time.sleep(0.4)

    if a.live:
        print(f"\n✅ ส่งจริง {sent} ข้อความ")
    else:
        print("ℹ️ DRY-RUN — ยังไม่ส่ง (เพิ่ม --live เพื่อส่งจริง)")


if __name__ == "__main__":
    main()
