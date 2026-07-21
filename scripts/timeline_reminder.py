"""timeline_reminder.py — เตือนไทม์ไลน์งานที่ user จดไว้ (job_notes) เมื่อถึงวันที่ (entry_date == วันนี้).

SAFE BY DEFAULT: รันเฉยๆ = dry-run (shadow) — log ว่าจะเตือนใคร ไม่ส่ง LINE จริง.
ต้องใส่ --live ถึงจะ push LINE จริง.

    python scripts/timeline_reminder.py             # shadow (default) — แค่ log/print
    python scripts/timeline_reminder.py --live       # ส่ง LINE จริง

หา job_notes ที่ entry_date == วันนี้ (tz ไทย) ของ customer ที่ active → จัดกลุ่มต่อ user
(หลายงาน/หลายรายการรวมเป็นข้อความเดียว) แล้ว shadow-log หรือ push.
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import get_connection  # noqa: E402

TZ_TH = timezone(timedelta(hours=7))
_TH_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
_SHADOW_LOG = Path(__file__).parent.parent / "data" / "timeline_reminder_log.ndjson"


def _fmt_date_th(s):
    try:
        d = datetime.fromisoformat(str(s)[:10]).date()
    except (ValueError, TypeError):
        return str(s)
    return f"{d.day} {_TH_MONTHS[d.month]} {d.year + 543}"


def find_due_reminders(conn, today, tomorrow=None):
    """job_notes ที่ entry_date == today (และ tomorrow ถ้าระบุ) ของ customer active.
    คืน list ต่อ user: {line_user_id, display_name, today, jobs:[{project_id, project_name,
    items:[{note, entry_date, when}]}]} — when = 'วันนี้' | 'พรุ่งนี้'."""
    dates = [today] + ([tomorrow] if tomorrow else [])
    ph = ",".join("?" * len(dates))
    rows = conn.execute(
        "SELECT jn.customer_id, c.line_user_id, c.display_name, jn.project_id, jn.note, "
        "jn.entry_date, ps.project_name "
        "FROM job_notes jn "
        "JOIN customers c ON c.id = jn.customer_id AND c.active = 1 "
        "LEFT JOIN projects_seen ps ON ps.project_id = jn.project_id "
        f"WHERE jn.entry_date IN ({ph}) "
        "ORDER BY jn.customer_id, jn.project_id, jn.entry_date, jn.id",
        (*dates,)).fetchall()
    users = {}
    for r in rows:
        uid = r["line_user_id"]
        u = users.setdefault(uid, {"line_user_id": uid, "customer_id": r["customer_id"],
                                   "display_name": r["display_name"] or "",
                                   "today": today, "jobs": {}})
        pid = r["project_id"]
        job = u["jobs"].setdefault(pid, {"project_id": pid,
                                         "project_name": r["project_name"] or pid, "items": []})
        when = "วันนี้" if r["entry_date"] == today else "พรุ่งนี้"
        job["items"].append({"note": r["note"], "entry_date": r["entry_date"], "when": when})
    out = []
    for u in users.values():
        u["jobs"] = list(u["jobs"].values())
        out.append(u)
    return out


def build_reminder_text(group):
    """ข้อความเตือน LINE ต่อ user (รวมทุกงาน/รายการ วันนี้+พรุ่งนี้ ติดป้ายกำกับ)."""
    lines = [f"🚂 เตือนไทม์ไลน์งาน ({_fmt_date_th(group['today'])})", ""]
    for job in group["jobs"]:
        lines.append(f"📋 {job['project_name']}")
        for it in job["items"]:
            lines.append(f"  • [{it['when']}] {it['note']}")
        lines.append("")
    lines.append("— จากแผนงานที่คุณจดไว้ในไทม์ไลน์")
    return "\n".join(lines).strip()


def _shadow_log(records):
    _SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(TZ_TH).isoformat(timespec="seconds")
    with open(_SHADOW_LOG, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps({"ts": ts, **rec}, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Timeline reminder (job_notes due today)")
    ap.add_argument("--live", action="store_true", help="ส่ง LINE จริง (ไม่ใส่ = shadow/dry-run)")
    ap.add_argument("--all", action="store_true", help="ส่งทุกคนทันที ข้ามเช็คเวลา/marker (N+201)")
    ap.add_argument("--date", default=None, help="override วันที่ 'YYYY-MM-DD' (test)")
    args = ap.parse_args()
    import notify_schedule as ns
    now = datetime.now(TZ_TH)
    today = args.date or now.date().isoformat()
    tomorrow = (datetime.fromisoformat(today).date() + timedelta(days=1)).isoformat()
    now_th = now.strftime("%H:%M")
    now_iso = now.isoformat(timespec="seconds")
    # N+201: gate per-customer morningNotifyTime (default 07:30) + marker kind='timeline'
    with get_connection() as conn:
        by_uid = {g["line_user_id"]: g for g in find_due_reminders(conn, today, tomorrow)}
        customers = conn.execute(
            "SELECT id, line_user_id, display_name, notes FROM customers "
            "WHERE active=1 AND COALESCE(is_test_data,0)=0").fetchall()
        due, no_notes = [], []
        for c in customers:
            t = ns.pref_time(c["notes"], "morningNotifyTime", ns.DEFAULT_MORNING)
            if not args.all and not ns.is_due(conn, "timeline", c["id"], t, now_th, today):
                continue
            g = by_uid.get(c["line_user_id"])
            if g:
                due.append((c, g))
            else:
                no_notes.append(c["id"])
        if args.live:
            for cid in no_notes:   # due แต่ไม่มีโน้ตวันนี้ → mark ประมวลผลแล้ว (one-shot/วัน เท่าเดิม)
                ns.mark_sent(conn, "timeline", cid, today, now_iso)
    mode = "LIVE" if args.live else "SHADOW"
    print(f"[timeline_reminder] {mode} today={today} tomorrow={tomorrow} due_users={len(due)} (no-notes={len(no_notes)})")
    if not due:
        return
    token = None
    if args.live:
        from Sebastian_LINE_Sender import _load_line_token
        token = _load_line_token()
    shadow_records = []
    for c, g in due:
        text = build_reminder_text(g)
        n_items = sum(len(j["items"]) for j in g["jobs"])
        if args.live:
            from Sebastian_LINE_Sender import send_line_push
            with get_connection() as conn:
                wp_ctx = ns.webpush_ctx(conn, "timeline", c["id"], today, now_iso)
            ok, etype, emsg = send_line_push(token, g["line_user_id"], text, webpush_ctx=wp_ctx)
            if ok:
                with get_connection() as conn:
                    ns.mark_sent(conn, "timeline", c["id"], today, now_iso)
            print(f"  → {g['line_user_id'][:10]} sent={ok} items={n_items} {etype or ''}")
        else:
            print(f"  [SHADOW] {g['line_user_id'][:10]} would-send items={n_items}, jobs={len(g['jobs'])}")
            shadow_records.append({"line_user_id": g["line_user_id"], "date": today,
                                   "jobs": len(g["jobs"]), "items": n_items, "text": text})
    if shadow_records:
        _shadow_log(shadow_records)
        print(f"[timeline_reminder] shadow logged {len(shadow_records)} → {_SHADOW_LOG.name}")


if __name__ == "__main__":
    main()
