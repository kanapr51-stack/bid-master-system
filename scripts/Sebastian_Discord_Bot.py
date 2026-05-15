"""
Sebastian_Discord_Bot.py — Discord Bot เชื่อม Claude API โดยตรง (ไม่ผ่าน claude CLI)

ฟีเจอร์:
  - พิมพ์ข้อความตรงๆ → Claude API (เร็วกว่า subprocess ~5-10x)
  - Tools: read_file, edit_file, write_file, run_command, list_directory, search_files
  - !status / !run / !stop / !ping / !help
  - Error monitor อัตโนมัติทุก 5 นาที
"""

import os
import re
import sys
import asyncio
import subprocess
import threading
from pathlib import Path
from datetime import datetime

import discord
from discord.ext import commands, tasks

sys.stdout.reconfigure(encoding="utf-8")

# ================================================================
# CONFIG
# ================================================================

BASE_DIR   = Path(__file__).parent.parent
SCRIPTS    = Path(__file__).parent
REPLY_FILE  = BASE_DIR / "data" / "discord_reply.txt"
LOG_FILE    = BASE_DIR / "logs" / "discord_bot.log"
CLAUDE_CMD  = r"C:\Users\Ace\AppData\Roaming\npm\claude.cmd"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
REPLY_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()


load_env()
BOT_TOKEN  = os.environ.get("DISCORD_BOT_TOKEN", "").strip().lstrip("﻿")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
if not BOT_TOKEN:
    print("[ERROR] ไม่พบ DISCORD_BOT_TOKEN ใน .env", flush=True)
    sys.exit(1)
if not CHANNEL_ID:
    print("[ERROR] ไม่พบ DISCORD_CHANNEL_ID ใน .env", flush=True)
    sys.exit(1)

# ================================================================
# BOT SETUP
# ================================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

_pipeline_proc: subprocess.Popen | None = None
_claude_busy   = False
_last_log_size = 0

# ================================================================
# HELPERS
# ================================================================

def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def split_message(text: str, limit: int = 1900) -> list[str]:
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks or ["(ว่าง)"]


async def send_chunks(channel, text: str):
    chunks = split_message(text)
    total  = len(chunks)
    for i, chunk in enumerate(chunks):
        part = f" (ต่อ {i+1}/{total})" if total > 1 and i > 0 else ""
        await channel.send(f"**[Sebastian]{part}**\n{chunk}")

# ================================================================
# CLAUDE TOOLS
# ================================================================

TOOLS = [
    {
        "name": "read_file",
        "description": "อ่านเนื้อหาไฟล์",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของไฟล์ (relative to C:\\Bid-Master-System หรือ absolute)"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "edit_file",
        "description": "แก้ไขบางส่วนของไฟล์ด้วย old_string → new_string",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":       {"type": "string"},
                "old_string": {"type": "string", "description": "ข้อความที่ต้องการแทนที่ (ต้องตรงทุกตัวอักษร)"},
                "new_string": {"type": "string", "description": "ข้อความใหม่ที่จะใส่แทน"}
            },
            "required": ["path", "old_string", "new_string"]
        }
    },
    {
        "name": "write_file",
        "description": "เขียนทับไฟล์ทั้งหมด (ใช้เมื่อสร้างไฟล์ใหม่หรือเขียนใหม่ทั้งหมด)",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "run_command",
        "description": "รัน shell command บน Windows (PowerShell/cmd)",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "command ที่จะรัน"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "list_directory",
        "description": "แสดงรายการไฟล์ใน directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "path ของ directory"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_files",
        "description": "ค้นหา text ในไฟล์ (grep)",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "regex pattern ที่ต้องการค้นหา"},
                "path":    {"type": "string", "description": "directory หรือไฟล์ที่จะค้นหา"},
                "glob":    {"type": "string", "description": "glob filter เช่น *.py (optional)"}
            },
            "required": ["pattern", "path"]
        }
    }
]

SYSTEM_PROMPT = f"""คุณคือ Sebastian Michaelis — AI assistant สำหรับ Bid Master System (BMS) ของคุณกัญจน์

Project: C:\\Bid-Master-System
วันนี้: {datetime.now().strftime('%d/%m/%Y')}

ไฟล์สำคัญ:
- scripts/Sebastian_Scraper.py — ดึงงานจาก eGP (FILTER_KEYWORDS, DEPT_SEARCH_TERMS)
- scripts/Sebastian_Classifier.py — จำแนกงานเข้า Sheet ต่างๆ
- scripts/Sebastian_Winner_Checker.py — ดึงชื่อผู้ชนะ
- scripts/Sebastian_LINE_Notify.py — ส่ง LINE
- run_pipeline.bat — pipeline อัตโนมัติตี 6
- logs/pipeline_YYYYMMDD.txt — log รายวัน
- progress_log.md — ประวัติการพัฒนาทั้งหมด

Sheets (Google Spreadsheet):
- raw_jobs — งานทั้งหมดในพื้นที่
- active_bidding — e-bidding กำลังประมูล
- awarded_jobs — ประกาศผู้ชนะแล้ว
- calc_road — ชีทคำนวนปริมาณวัสดุ (กรอก L ที่ C5)

ตอบเป็นภาษาไทย กระชับ ตรงประเด็น ถ้าแก้ไฟล์ให้บอกด้วยว่าแก้อะไรไปบ้าง"""


def resolve_path(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "read_file":
            p = resolve_path(inputs["path"])
            if not p.exists():
                return f"ไม่พบไฟล์: {p}"
            return p.read_text(encoding="utf-8", errors="replace")

        elif name == "edit_file":
            p = resolve_path(inputs["path"])
            if not p.exists():
                return f"ไม่พบไฟล์: {p}"
            content = p.read_text(encoding="utf-8", errors="replace")
            old, new = inputs["old_string"], inputs["new_string"]
            if old not in content:
                return f"ไม่พบ old_string ในไฟล์ — ตรวจสอบข้อความให้ตรงทุกตัวอักษร"
            p.write_text(content.replace(old, new, 1), encoding="utf-8")
            return f"แก้ไขสำเร็จ: {p.name}"

        elif name == "write_file":
            p = resolve_path(inputs["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(inputs["content"], encoding="utf-8")
            return f"เขียนไฟล์สำเร็จ: {p.name} ({len(inputs['content'])} ตัวอักษร)"

        elif name == "run_command":
            result = subprocess.run(
                inputs["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(BASE_DIR),
                encoding="utf-8",
                errors="replace"
            )
            output = (result.stdout + result.stderr).strip()
            return output[:3000] or "(ไม่มี output)"

        elif name == "list_directory":
            p = resolve_path(inputs["path"])
            if not p.exists():
                return f"ไม่พบ directory: {p}"
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            return "\n".join(
                f"{'📁' if item.is_dir() else '📄'} {item.name}"
                for item in items[:60]
            )

        elif name == "search_files":
            p      = resolve_path(inputs["path"])
            glob   = inputs.get("glob", "")
            pattern = inputs["pattern"]
            cmd = f'rg --no-heading -n "{pattern}" "{p}"'
            if glob:
                cmd += f' -g "{glob}"'
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                    text=True, timeout=30, encoding="utf-8", errors="replace")
            output = (result.stdout or result.stderr or "(ไม่พบ)").strip()
            return output[:3000]

        else:
            return f"ไม่รู้จัก tool: {name}"

    except subprocess.TimeoutExpired:
        return "หมดเวลา 60 วินาที"
    except Exception as e:
        return f"Error: {e}"


# ================================================================
# CLAUDE CODE (subprocess — ใช้ subscription ไม่คิด token)
# ================================================================

def strip_ansi(text: str) -> str:
    return re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", text)


async def ask_claude(prompt: str) -> str:
    loop = asyncio.get_event_loop()

    def _run():
        try:
            result = subprocess.run(
                [CLAUDE_CMD, "-p", prompt],
                capture_output=True,
                text=True,
                timeout=1800,
                cwd=str(BASE_DIR),
                encoding="utf-8",
                errors="replace",
                env=os.environ.copy(),
            )
            output = result.stdout or result.stderr or "(ไม่มีผลลัพธ์)"
            return strip_ansi(output).strip()
        except subprocess.TimeoutExpired:
            return "⚠️ หมดเวลา 30 นาที — ลองแบ่งคำสั่งให้เล็กลงครับ"
        except FileNotFoundError:
            return f"⚠️ ไม่พบ claude CLI ที่ {CLAUDE_CMD}"
        except Exception as e:
            return f"⚠️ Error: {e}"

    return await loop.run_in_executor(None, _run)

# ================================================================
# ERROR MONITOR
# ================================================================

def get_today_log() -> Path:
    return BASE_DIR / "logs" / f"pipeline_{datetime.now().strftime('%Y%m%d')}.txt"


def extract_errors(text: str) -> list[str]:
    return [
        line.strip() for line in text.splitlines()
        if any(kw in line for kw in ["Error", "ERROR", "Traceback", "WARN", "ไม่สำเร็จ", "RuntimeError"])
    ]


@tasks.loop(minutes=5)
async def monitor_pipeline_errors():
    global _last_log_size
    log_path = get_today_log()
    if not log_path.exists():
        return
    size = log_path.stat().st_size
    if size <= _last_log_size:
        return
    with open(log_path, encoding="utf-8", errors="replace") as f:
        f.seek(_last_log_size)
        new_text = f.read()
    _last_log_size = size

    errors = extract_errors(new_text)
    if not errors:
        return

    ch = bot.get_channel(CHANNEL_ID)
    if not ch:
        return

    error_summary = "\n".join(errors[:10])
    explanation   = await ask_claude(
        f"Pipeline log มี error ใหม่:\n{error_summary}\n\n"
        f"อธิบายเป็นภาษาไทยแบบกระชับ: เกิดอะไร, สาเหตุ, แก้ยังไง (ไม่เกิน 4 บรรทัด)"
    )
    await ch.send(f"⚠️ **[Sebastian] พบ Error**\n{explanation}")
    log("ส่งแจ้งเตือน error อัตโนมัติ")

# ================================================================
# EVENTS
# ================================================================

@bot.event
async def on_ready():
    log(f"Sebastian Bot online — {bot.user}")
    monitor_pipeline_errors.start()
    ch = bot.get_channel(CHANNEL_ID)
    if ch:
        await ch.send(
            f"**[Sebastian]** พร้อมแล้วครับ `{datetime.now().strftime('%d/%m/%Y %H:%M')}`\n"
            f"พิมพ์ข้อความตรงๆ เพื่อสั่งงาน หรือ `!help` ดู command ลัด"
        )


@bot.event
async def on_message(message: discord.Message):
    global _claude_busy

    if message.author.bot:
        return
    if message.channel.id != CHANNEL_ID:
        return

    content = message.content.strip()
    if not content:
        return

    # ถ้า GSD รอ reply
    waiting_file = BASE_DIR / "data" / "discord_waiting.txt"
    if waiting_file.exists() and not content.startswith("!"):
        try:
            REPLY_FILE.write_text(content, encoding="utf-8")
            waiting_file.unlink(missing_ok=True)
            await message.add_reaction("✅")
        except Exception as e:
            log(f"[ERROR] reply: {e}")
        return

    if content.startswith("!"):
        await bot.process_commands(message)
        return

    # ส่งให้ Claude API
    if _claude_busy:
        await message.channel.send(
            "**[Sebastian]** กำลังทำงานอยู่ครับ รอสักครู่ หรือพิมพ์ `!stop` เพื่อหยุด"
        )
        return

    _claude_busy = True
    log(f"Claude ← {content[:100]}")
    await message.add_reaction("⏳")
    thinking = await message.channel.send("**[Sebastian]** กำลังคิดอยู่ครับ...")

    response = await ask_claude(content)

    try:
        await thinking.delete()
        await message.remove_reaction("⏳", bot.user)
    except Exception:
        pass
    await message.add_reaction("✅")
    await send_chunks(message.channel, response)
    _claude_busy = False

# ================================================================
# COMMANDS
# ================================================================

@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    if ctx.channel.id != CHANNEL_ID:
        return
    await ctx.send(
        "**Sebastian — วิธีใช้**\n\n"
        "💬 **พิมพ์ตรงๆ** — Claude API ตอบทันที\n"
        "ตัวอย่าง: `เพิ่ม keyword ฝายน้ำล้น ใน FILTER_KEYWORDS`\n"
        "ตัวอย่าง: `pipeline เมื่อคืน error อะไร`\n\n"
        "**Command ลัด:**\n"
        "```\n"
        "!status    สถานะระบบ\n"
        "!run       รัน pipeline ทันที\n"
        "!stop      หยุด pipeline / Claude\n"
        "!ping      ทดสอบ connection\n"
        "!help      แสดงข้อความนี้\n"
        "```"
    )


@bot.command(name="ping")
async def cmd_ping(ctx: commands.Context):
    if ctx.channel.id != CHANNEL_ID:
        return
    await ctx.send(f"**[Sebastian]** Pong! `{round(bot.latency * 1000)}ms`")


@bot.command(name="status")
async def cmd_status(ctx: commands.Context):
    if ctx.channel.id != CHANNEL_ID:
        return
    running = _pipeline_proc is not None and _pipeline_proc.poll() is None
    waiting = (BASE_DIR / "data" / "discord_waiting.txt").exists()
    lines   = [
        "**[Sebastian] สถานะระบบ**",
        f"Pipeline: {'🟢 รันอยู่' if running else '⚪ หยุด'}",
        f"Claude:   {'🟡 กำลังคิด' if _claude_busy else '🟢 พร้อม'}",
        f"รอคำตอบ: {'ใช่' if waiting else 'ไม่'}",
    ]
    log_path = get_today_log()
    if log_path.exists():
        last = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if last:
            lines.append(f"Log ล่าสุด: `{last[-1][:100]}`")
    await ctx.send("\n".join(lines))


@bot.command(name="run")
async def cmd_run(ctx: commands.Context):
    if ctx.channel.id != CHANNEL_ID:
        return
    global _pipeline_proc
    if _pipeline_proc is not None and _pipeline_proc.poll() is None:
        await ctx.send("**[Sebastian]** Pipeline กำลังรันอยู่แล้ว ใช้ `!stop` ก่อน")
        return
    await ctx.send("**[Sebastian]** เริ่ม pipeline ครับ...")
    log("!run")

    def run_bg():
        global _pipeline_proc
        try:
            _pipeline_proc = subprocess.Popen(
                [sys.executable, str(SCRIPTS / "Sebastian_Pipeline.py")],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace",
            )
            _pipeline_proc.wait()
            log(f"Pipeline เสร็จ (exit {_pipeline_proc.returncode})")
        except Exception as e:
            log(f"[ERROR] !run: {e}")

    threading.Thread(target=run_bg, daemon=True).start()


@bot.command(name="stop")
async def cmd_stop(ctx: commands.Context):
    global _pipeline_proc, _claude_busy
    if ctx.channel.id != CHANNEL_ID:
        return
    stopped = []
    if _pipeline_proc is not None and _pipeline_proc.poll() is None:
        _pipeline_proc.terminate()
        stopped.append("Pipeline")
    if _claude_busy:
        _claude_busy = False
        stopped.append("Claude")
    msg = f"หยุด {', '.join(stopped)} แล้วครับ" if stopped else "ไม่มีอะไรรันอยู่ครับ"
    await ctx.send(f"**[Sebastian]** {msg}")
    log(f"!stop: {stopped or 'ไม่มี'}")

# ================================================================
# MAIN
# ================================================================

def main():
    log("Sebastian Discord Bot เริ่มต้น...")
    token = BOT_TOKEN.removeprefix("Bot ")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
