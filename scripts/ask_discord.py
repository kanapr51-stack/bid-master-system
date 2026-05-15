"""
ask_discord.py — GSD ใช้ถามคุณกัญจน์ใน Discord แล้วรอคำตอบ

ใช้งาน:
    python scripts/ask_discord.py "Sebastian ต้องการ input: [คำถาม]"

หรือใน Python:
    from ask_discord import ask
    answer = ask("ต้องการ Google Sheets credentials ไหมครับ? (yes/no)")

กลไก:
    1. ส่งคำถามไปใน Discord channel
    2. สร้างไฟล์ data/discord_waiting.txt เพื่อบอก Bot ว่ากำลังรอคำตอบ
    3. รอ reply จากคุณกัญจน์ (Bot จะเขียนคำตอบลง data/discord_reply.txt)
    4. อ่านคำตอบแล้วลบไฟล์ทิ้ง คืนค่ากลับ

Timeout: 30 นาที (configurable)
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR      = Path(__file__).parent.parent
REPLY_FILE    = BASE_DIR / "data" / "discord_reply.txt"
WAITING_FILE  = BASE_DIR / "data" / "discord_waiting.txt"
DEFAULT_TIMEOUT = 30 * 60  # 30 นาที
POLL_INTERVAL   = 3        # เช็คทุก 3 วินาที

DISCORD_API_BASE = "https://discord.com/api/v10"


def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()


def get_credentials():
    token      = os.environ.get("DISCORD_BOT_TOKEN", "").strip().lstrip("\ufeff")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
    if not token:
        raise ValueError("ไม่พบ DISCORD_BOT_TOKEN ใน .env")
    if not channel_id:
        raise ValueError("ไม่พบ DISCORD_CHANNEL_ID ใน .env")
    if not token.startswith("Bot "):
        token = f"Bot {token}"
    return token, channel_id


def send_message(token: str, channel_id: str, content: str) -> bool:
    url     = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    payload = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": token,
            "User-Agent": "DiscordBot (BidMasterSystem, 1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 201)
    except Exception as e:
        print(f"[ask_discord] ส่งข้อความไม่ได้: {e}", flush=True)
        return False


def ask(question: str, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """
    ส่งคำถามไป Discord แล้วรอคำตอบ
    คืนค่า: str คำตอบ, หรือ None ถ้า timeout
    """
    load_env()
    token, channel_id = get_credentials()

    # ลบไฟล์เก่าทิ้งก่อน
    REPLY_FILE.unlink(missing_ok=True)
    WAITING_FILE.unlink(missing_ok=True)

    # สร้าง data dir ถ้ายังไม่มี
    REPLY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ส่งคำถาม
    ts  = datetime.now().strftime("%H:%M")
    msg = (
        f"**[Sebastian {ts}]** {question}\n"
        f"*พิมพ์คำตอบในช่องนี้ได้เลยครับ*"
    )
    ok = send_message(token, channel_id, msg)
    if not ok:
        print("[ask_discord] ส่งคำถามไม่ได้", flush=True)
        return None

    # บอก Bot ว่ากำลังรอ
    WAITING_FILE.write_text(question[:200], encoding="utf-8")
    print(f"[ask_discord] รอคำตอบ (timeout {timeout//60} นาที)...", flush=True)

    # Polling รอคำตอบ
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        if REPLY_FILE.exists():
            answer = REPLY_FILE.read_text(encoding="utf-8").strip()
            REPLY_FILE.unlink(missing_ok=True)
            WAITING_FILE.unlink(missing_ok=True)
            print(f"[ask_discord] ได้คำตอบ: {answer[:80]}", flush=True)
            return answer

    # Timeout
    WAITING_FILE.unlink(missing_ok=True)
    timeout_msg = (
        f"**[Sebastian]** หมดเวลารอคำตอบ ({timeout//60} นาที)\n"
        f"Sebastian จะใช้ค่า default แทนครับ"
    )
    send_message(token, channel_id, timeout_msg)
    print(f"[ask_discord] timeout หลังจาก {timeout//60} นาที", flush=True)
    return None


def notify(message: str) -> bool:
    """ส่งข้อความแจ้งเตือนธรรมดา (ไม่รอ reply)"""
    load_env()
    token, channel_id = get_credentials()
    return send_message(token, channel_id, message)


def progress(step: str, detail: str = "") -> bool:
    """แจ้งความคืบหน้า GSD auto-mode"""
    ts  = datetime.now().strftime("%H:%M")
    msg = f"**[Sebastian {ts}]** {step}"
    if detail:
        msg += f"\n> {detail}"
    return notify(msg)


# ================================================================
# CLI
# ================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ask_discord.py \"คำถาม\"")
        print("       python ask_discord.py --notify \"ข้อความ\"")
        sys.exit(1)

    if sys.argv[1] == "--notify":
        message = " ".join(sys.argv[2:])
        ok = notify(message)
        sys.exit(0 if ok else 1)

    question = " ".join(sys.argv[1:])
    print(f"ถามใน Discord: {question}", flush=True)
    answer = ask(question)
    if answer:
        print(f"คำตอบ: {answer}", flush=True)
        sys.exit(0)
    else:
        print("ไม่ได้รับคำตอบ (timeout)", flush=True)
        sys.exit(1)
