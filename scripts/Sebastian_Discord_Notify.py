"""
Sebastian_Discord_Notify.py — ส่งข้อความไป Discord ผ่าน Bot Token

ใช้สำหรับ:
  1. notify_pipeline_start()   — แจ้งตอนเริ่ม pipeline
  2. notify_step_done()        — แจ้งตอน step เสร็จ
  3. notify_error()            — แจ้งตอนติดปัญหา
  4. notify_ranked_jobs()      — รายงานสรุปงานประจำวัน (เหมือน LINE)

ตั้งใน .env:
    DISCORD_BOT_TOKEN=Bot xxxxxxx
    DISCORD_CHANNEL_ID=123456789012345678
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

DISCORD_API_BASE = "https://discord.com/api/v10"
TOP_N = 50


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
                os.environ[k.strip()] = v.strip()


def get_credentials() -> tuple[str, str]:
    token      = os.environ.get("DISCORD_BOT_TOKEN", "").strip().lstrip("\ufeff")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
    if not token:
        raise ValueError("ไม่พบ DISCORD_BOT_TOKEN ใน .env")
    if not channel_id:
        raise ValueError("ไม่พบ DISCORD_CHANNEL_ID ใน .env")
    # รองรับทั้ง "Bot xxx" และ "xxx" (เพิ่ม prefix อัตโนมัติ)
    if not token.startswith("Bot "):
        token = f"Bot {token}"
    return token, channel_id


# ================================================================
# SEND
# ================================================================

def send(token: str, channel_id: str, content: str) -> bool:
    """ส่งข้อความ plain text ไป Discord channel"""
    url     = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    payload = json.dumps({"content": content}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": token,
            "User-Agent": "DiscordBot (https://github.com/BidMasterSystem, 1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201):
                print("Discord: ส่งสำเร็จ", flush=True)
                return True
            print(f"Discord: status {resp.status}", flush=True)
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Discord error {e.code}: {body}", flush=True)
    except Exception as e:
        print(f"Discord error: {e}", flush=True)
    return False


# ================================================================
# HELPER — ข้อความสำเร็จรูป
# ================================================================

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def notify_pipeline_start(token: str, channel_id: str):
    msg = f"**[Sebastian]** เริ่ม pipeline `{datetime.now().strftime('%d/%m/%Y %H:%M')} น.`"
    send(token, channel_id, msg)


def notify_step_done(token: str, channel_id: str, step_name: str, detail: str = ""):
    msg = f"**[{_now()}]** ✅ `{step_name}` เสร็จแล้ว"
    if detail:
        msg += f"\n> {detail}"
    send(token, channel_id, msg)


def notify_step_warn(token: str, channel_id: str, step_name: str, detail: str = ""):
    msg = f"**[{_now()}]** ⚠️ `{step_name}` เตือน"
    if detail:
        msg += f"\n> {detail}"
    send(token, channel_id, msg)


def notify_error(token: str, channel_id: str, step_name: str, error: str):
    msg = (
        f"**[Sebastian]** ❌ ติดปัญหาที่ `{step_name}`\n"
        f"```\n{error[:1800]}\n```\n"
        f"กรุณาตรวจสอบหรือสั่ง `/run` อีกครั้ง"
    )
    send(token, channel_id, msg)


def notify_pipeline_done(token: str, channel_id: str, elapsed: float):
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    duration = f"{mins}m {secs}s" if mins else f"{secs}s"
    msg = f"**[Sebastian]** Pipeline เสร็จสิ้น ใช้เวลา `{duration}`"
    send(token, channel_id, msg)


# ================================================================
# รายงานสรุปงาน (เหมือน LINE แต่ใช้ Discord markdown)
# ================================================================

def fmt_budget(val) -> str:
    try:
        n = float(val)
        if n >= 1_000_000:
            return f"{n/1_000_000:.2f}ล้าน"
        return f"{n:,.0f}"
    except (ValueError, TypeError):
        return str(val)


def format_summary(jobs: list[dict], awarded_count: int) -> str:
    today = datetime.now().strftime("%d/%m/%Y %H:%M น.")
    top   = jobs[:TOP_N]

    lines = [
        f"**Sebastian — รายงานประจำวัน**",
        f"วันที่ {today}",
        "",
    ]

    if not jobs:
        lines += [
            f"ไม่มีงาน e-bidding กำลังประมูลในพื้นที่ตอนนี้",
            f"งานที่ประกาศผู้ชนะแล้ว: {awarded_count} งาน",
        ]
        return "\n".join(lines)

    lines += [
        f"งาน e-bidding กำลังประมูล: **{len(jobs)} งาน**",
        f"ประกาศผู้ชนะแล้ว: {awarded_count} งาน",
        "",
        "```",
    ]

    for i, job in enumerate(top, 1):
        title  = str(job.get("title", "ไม่มีชื่อ"))
        budget = fmt_budget(job.get("budget", 0))
        dept   = str(job.get("department", ""))
        due    = str(job.get("submission_deadline", "") or job.get("deadline", ""))
        job_id = str(job.get("job_id", ""))

        lines.append(f"[{i}] {title}")
        lines.append(f"    งบ: {budget} บาท")
        if dept:
            lines.append(f"    หน่วยงาน: {dept[:35]}")
        if due:
            lines.append(f"    ยื่นถึง: {due}")
        if job_id:
            lines.append(f"    ID: {job_id}")
        lines.append("")

    lines += ["```", f"Sebastian · 06:00 น."]
    return "\n".join(lines)


def notify_ranked_jobs():
    """เรียกจาก Pipeline.py ได้โดยตรง — ส่งรายงานสรุปงานไป Discord"""
    load_env()
    token, channel_id = get_credentials()

    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet

    SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"

    try:
        ws   = open_sheet(SPREADSHEET_ID, "active_bidding")
        jobs = ws.get_all_records()
    except Exception as e:
        print(f"[WARN] อ่าน active_bidding ไม่ได้: {e}", flush=True)
        jobs = []

    try:
        ws2           = open_sheet(SPREADSHEET_ID, "awarded_jobs")
        awarded_count = len(ws2.get_all_records())
    except Exception:
        awarded_count = 0

    message = format_summary(jobs, awarded_count)
    print(f"\nข้อความ Discord:\n{message}\n", flush=True)
    return send(token, channel_id, message)


# ================================================================
# MAIN — ทดสอบส่งข้อความเดี่ยว
# ================================================================

def main():
    load_env()
    print("Sebastian Discord Notify — ทดสอบ", flush=True)

    try:
        token, channel_id = get_credentials()
    except ValueError as e:
        print(f"[ERROR] {e}", flush=True)
        sys.exit(1)

    msg = f"**[Sebastian]** ทดสอบการเชื่อมต่อ Discord — `{datetime.now().strftime('%d/%m/%Y %H:%M')}`"
    ok  = send(token, channel_id, msg)
    if ok:
        print("ส่งทดสอบสำเร็จ", flush=True)
    else:
        print("ส่งทดสอบไม่สำเร็จ ตรวจสอบ token/channel_id", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
