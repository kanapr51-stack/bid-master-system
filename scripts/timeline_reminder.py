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


def find_due_reminders(conn, today):
    """job_notes ที่ entry_date == today (str 'YYYY-MM-DD') ของ customer active.
    คืน list ต่อ user: {line_user_id, display_name, today, jobs:[{project_id, project_name, items:[note]}]}."""
    rows = conn.execute(
        "SELECT jn.customer_id, c.line_user_id, c.display_name, jn.project_id, jn.note, "
        "ps.project_name "
        "FROM job_notes jn "
        "JOIN customers c ON c.id = jn.customer_id AND c.active = 1 "
        "LEFT JOIN projects_seen ps ON ps.project_id = jn.project_id "
        "WHERE jn.entry_date = ? "
        "ORDER BY jn.customer_id, jn.project_id, jn.id",
        (today,)).fetchall()
    users = {}
    for r in rows:
        uid = r["line_user_id"]
        u = users.setdefault(uid, {"line_user_id": uid, "display_name": r["display_name"] or "",
                                   "today": today, "jobs": {}})
        pid = r["project_id"]
        job = u["jobs"].setdefault(pid, {"project_id": pid,
                                         "project_name": r["project_name"] or pid, "items": []})
        job["items"].append(r["note"])
    out = []
    for u in users.values():
        u["jobs"] = list(u["jobs"].values())
        out.append(u)
    return out


def build_reminder_text(group):
    """ข้อความเตือน LINE ต่อ user (รวมทุกงาน/รายการของวันนี้)."""
    lines = [f"🚂 ไทม์ไลน์วันนี้ ({_fmt_date_th(group['today'])})", ""]
    for job in group["jobs"]:
        lines.append(f"📋 {job['project_name']}")
        for note in job["items"]:
            lines.append(f"  • {note}")
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
    ap.add_argument("--date", default=None, help="override วันที่ 'YYYY-MM-DD' (test)")
    args = ap.parse_args()
    today = args.date or datetime.now(TZ_TH).date().isoformat()
    with get_connection() as conn:
        groups = find_due_reminders(conn, today)
    mode = "LIVE" if args.live else "SHADOW"
    print(f"[timeline_reminder] {mode} date={today} due_users={len(groups)}")
    if not groups:
        return
    token = None
    if args.live:
        from Sebastian_LINE_Sender import _load_line_token
        token = _load_line_token()
    shadow_records = []
    for g in groups:
        text = build_reminder_text(g)
        n_items = sum(len(j["items"]) for j in g["jobs"])
        if args.live:
            from Sebastian_LINE_Sender import send_line_push
            ok, etype, emsg = send_line_push(token, g["line_user_id"], text)
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
