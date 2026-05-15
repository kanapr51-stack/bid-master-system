"""
Sebastian_LINE_Notify.py — ส่งสรุปงาน e-bidding ไป LINE หลัง pipeline รัน
ใช้ LINE Messaging API (push message) แทน LINE Notify ที่ปิดไปแล้ว

ตั้งใน .env:
    LINE_CHANNEL_ACCESS_TOKEN=xxxxxxx
    LINE_GROUP_ID=Cxxxxxxx
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID  = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET_TOR       = "tor_review"
SHEET_ACTIVE    = "active_bidding"
SHEET_PENDING   = "pending_award"
SHEET_AWARDED   = "awarded_jobs"
LINE_API_URL    = "https://api.line.me/v2/bot/message/push"
TOP_N           = 15


# ================================================================
# ENV
# ================================================================

def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_credentials() -> tuple[str, str]:
    token    = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip().lstrip("﻿")
    group_id = os.environ.get("LINE_GROUP_ID", "").strip()
    if not token:
        raise ValueError("ไม่พบ LINE_CHANNEL_ACCESS_TOKEN ใน .env")
    if not group_id:
        raise ValueError("ไม่พบ LINE_GROUP_ID ใน .env")
    return token, group_id


# ================================================================
# DATA
# ================================================================

def get_active_jobs() -> list[dict]:
    """อ่าน active_bidding (Classifier filter ตาม deadline >= today แล้ว — ไม่ต้อง re-filter)"""
    try:
        ws = open_sheet(SPREADSHEET_ID, SHEET_ACTIVE)
        return ws.get_all_records()
    except Exception as e:
        print(f"[WARN] อ่าน active_bidding ไม่ได้: {e}", flush=True)
        return []


def get_awarded_count() -> int:
    try:
        ws = open_sheet(SPREADSHEET_ID, SHEET_AWARDED)
        return len(ws.get_all_records())
    except Exception:
        return 0


def get_tor_review_jobs() -> list[dict]:
    """อ่าน tor_review (รับฟังคำวิจารณ์ — Classifier filter ตาม flowSeqno≤3 แล้ว)"""
    try:
        ws = open_sheet(SPREADSHEET_ID, SHEET_TOR)
        return ws.get_all_records()
    except Exception as e:
        print(f"[WARN] อ่าน tor_review ไม่ได้: {e}", flush=True)
        return []


# ================================================================
# FORMAT
# ================================================================

def fmt_budget(val) -> str:
    try:
        n = float(val)
        if n >= 1_000_000:
            return f"{n/1_000_000:.2f}ล้าน"
        return f"{n:,.0f}"
    except (ValueError, TypeError):
        return str(val)


def _build_job_block(i: int, job: dict) -> str:
    title       = str(job.get("title", "ไม่มีชื่อ"))
    budget      = fmt_budget(job.get("budget", 0))
    dept        = str(job.get("department", ""))
    announce    = str(job.get("publish_date", ""))
    due         = str(job.get("deadline", ""))
    days_left   = str(job.get("days_remaining", ""))
    job_id      = str(job.get("job_id", ""))

    lines = [f"", f"[{i}] {title}", f"    💰 {budget} บาท"]
    if dept:
        lines.append(f"    🏛️ {dept[:35]}")
    if announce:
        lines.append(f"    📢 ประกาศ: {announce}")
    if due:
        deadline_line = f"    📆 ยื่นซอง: {due}"
        if days_left:
            deadline_line += f"  ⏳ เหลือ {days_left} วัน"
        lines.append(deadline_line)
    if job_id:
        lines.append(f"    🔑 ID: {job_id}")
    return "\n".join(lines)


def _build_tor_block(i: int, job: dict) -> str:
    title    = str(job.get("title", "ไม่มีชื่อ"))
    budget   = fmt_budget(job.get("budget", 0))
    dept     = str(job.get("department", ""))
    announce = str(job.get("publish_date", ""))
    note     = str(job.get("stage_note", "รับฟังคำวิจารณ์"))
    job_id   = str(job.get("job_id", ""))

    lines = [f"", f"[{i}] {title}", f"    💰 {budget} บาท"]
    if dept:
        lines.append(f"    🏛️ {dept[:35]}")
    if announce:
        lines.append(f"    📢 ประกาศ: {announce}")
    lines.append(f"    📋 สถานะ: {note}")
    if job_id:
        lines.append(f"    🔑 ID: {job_id}")
    return "\n".join(lines)


def format_messages(jobs: list[dict], awarded_count: int, tor_jobs: list[dict] = None) -> list[str]:
    """สร้าง list ของ LINE messages — Part1: active_bidding, Part2: tor_review"""
    MAX_LEN = 4900
    today   = datetime.now().strftime("%d/%m/%Y %H:%M น.")
    footer  = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🤖 Sebastian · 06:00 น."
    tor_jobs = tor_jobs or []

    if not jobs and not tor_jobs:
        header = f"🏗️ Bid Master — รายงานประจำวัน\n📅 {today}\n\n📭 ไม่มีงาน e-bidding กำลังประมูลในพื้นที่ตอนนี้\n📦 งานที่ประกาศผู้ชนะแล้ว: {awarded_count} งาน"
        return [header + footer]

    messages = []

    def _pack_blocks(header_text: str, block_list: list) -> None:
        """แพ็ค blocks เข้า messages ไม่ตัดกลางงาน"""
        part    = 1
        current = header_text

        for block in block_list:
            candidate = current + block
            if len(candidate + footer) > MAX_LEN and current != header_text:
                messages.append(current + footer)
                part   += 1
                current = header_text.split("\n\n━━━")[0] + f"\n━━━ ต่อ (part {part}) ━━━" + block
            else:
                current = candidate
        messages.append(current + footer)

    # ── ส่วนที่ 1: Active Bidding ──
    if jobs:
        h1 = (f"🏗️ Bid Master — รายงานประจำวัน\n📅 {today}\n\n"
              f"🔔 e-bidding กำลังประมูล: {len(jobs)} งาน  📦 ประกาศผู้ชนะแล้ว: {awarded_count} งาน\n\n"
              f"━━━ ส่วนที่ 1: กำลังเปิดรับซอง ━━━")
        blocks = [_build_job_block(i, job) for i, job in enumerate(jobs, 1)]
        _pack_blocks(h1, blocks)

    # ── ส่วนที่ 2: รับฟังคำวิจารณ์ ──
    if tor_jobs:
        h2 = (f"🏗️ Bid Master — รายงานประจำวัน\n📅 {today}\n\n"
              f"📋 กำลังรับฟังคำวิจารณ์: {len(tor_jobs)} งาน\n\n"
              f"━━━ ส่วนที่ 2: รับฟังคำวิจารณ์ ━━━")
        tor_blocks = [_build_tor_block(i, job) for i, job in enumerate(tor_jobs, 1)]
        _pack_blocks(h2, tor_blocks)

    return messages


# ================================================================
# SEND
# ================================================================

def _send_one(token: str, group_id: str, message: str) -> bool:
    payload = json.dumps({
        "to": group_id,
        "messages": [{"type": "text", "text": message}]
    }).encode("utf-8")

    req = urllib.request.Request(
        LINE_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"❌ LINE ผิดพลาด {e.code}: {body}", flush=True)
    except Exception as e:
        print(f"❌ LINE error: {e}", flush=True)
    return False


def send_messages(token: str, group_id: str, messages: list[str]) -> bool:
    all_ok = True
    total  = len(messages)
    for idx, msg in enumerate(messages, 1):
        ok = _send_one(token, group_id, msg)
        label = f"part {idx}/{total}" if total > 1 else ""
        if ok:
            print(f"✅ ส่ง LINE {label}สำเร็จ".strip(), flush=True)
        else:
            all_ok = False
    return all_ok


# ================================================================
# MAIN
# ================================================================

def notify_jobs():
    """เรียกจาก Pipeline.py ได้โดยตรง"""
    load_env()
    token, group_id = get_credentials()
    jobs          = get_active_jobs()
    tor_jobs      = get_tor_review_jobs()
    awarded_count = get_awarded_count()
    messages      = format_messages(jobs, awarded_count, tor_jobs)
    for i, msg in enumerate(messages, 1):
        print(f"\n--- ข้อความ LINE part {i}/{len(messages)} ---\n{msg}\n", flush=True)
    return send_messages(token, group_id, messages)


def main():
    load_env()
    print("Sebastian LINE Notify — เริ่มต้น", flush=True)

    try:
        token, group_id = get_credentials()
    except ValueError as e:
        print(f"[ERROR] {e}", flush=True)
        sys.exit(1)

    print("อ่าน active_bidding...", flush=True)
    jobs = get_active_jobs()
    print(f"พบ {len(jobs)} งาน (active)", flush=True)

    print("อ่าน tor_review...", flush=True)
    tor_jobs = get_tor_review_jobs()
    print(f"พบ {len(tor_jobs)} งาน (รับฟังคำวิจารณ์)", flush=True)

    awarded_count = get_awarded_count()
    messages      = format_messages(jobs, awarded_count, tor_jobs)
    for i, msg in enumerate(messages, 1):
        print(f"\n--- ข้อความที่จะส่ง part {i}/{len(messages)} ---\n{msg}\n", flush=True)

    send_messages(token, group_id, messages)


# alias ให้ Pipeline.py เรียกได้
notify_ranked_jobs = notify_jobs


if __name__ == "__main__":
    main()
