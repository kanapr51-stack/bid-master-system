"""
Sebastian_LINE_Notify.py — ส่งสรุปงาน e-bidding ไป LINE หลัง pipeline รัน
ใช้ LINE Messaging API (push message) แทน LINE Notify ที่ปิดไปแล้ว

ตั้งใน .env:
    LINE_CHANNEL_ACCESS_TOKEN=xxxxxxx
    LINE_GROUP_ID=Cxxxxxxx
"""

import os
import re
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

# Google Sheet tab GIDs (for deep-link)
ACTIVE_GID = 827075644
TOR_GID    = 1025189196

TRANSITIONS_FILE = Path(__file__).parent.parent / "data" / "transitions_latest.json"


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
    """< 1M → '521,900 บาท', 1M-999M → '2.05 ล้าน', ≥ 1B → '1.5 พันล้าน'"""
    try:
        n = float(str(val).replace(",", "").strip())
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:.1f} พันล้าน"
        if n >= 1_000_000:
            return f"{n/1_000_000:.2f} ล้าน"
        return f"{n:,.0f} บาท"
    except (ValueError, TypeError):
        return str(val)


# ── Title / Department cleanup ────────────────────────────────
_TITLE_PREFIX_RE = re.compile(r'^ประกวดราคา(จ้าง|ซื้อ)?(ก่อสร้าง)?(โครงการ)?(ก่อสร้าง)?(งาน)?\s*')
_TITLE_SUFFIX_RE = re.compile(r'\s*(ด้วยวิธี|โดยวิธี).+?\(e[-‐]bidding\)\s*$', re.IGNORECASE)
# "ตำบลX อำเภอY จังหวัดZ" — ตัดออกเพราะ department บอกอยู่แล้ว
_LOCATION_RE  = re.compile(r'\s*(ตำบล\S+\s+)?(อำเภอ\S+\s+)?จังหวัด\S+\s*$')
_LOCATION_RE2 = re.compile(r'\s*ตำบล\S+(\s+อำเภอ\S+)?\s*$')
# "ขนาด..." / "ปริมาณงาน..." / "รวมยาว..." — ทุกอย่างหลังคำเหล่านี้ตัด
_SPECS_RE     = re.compile(r'\s*(ขนาด|ปริมาณงาน|รวมยาว|รวมระยะ|พร้อมติดตั้ง|พร้อมงาน).*$')
# "กว้าง N เมตร ยาว M เมตร หนา..." — มีตัวเลขตาม
_DIM_RE       = re.compile(r'\s*(กว้าง|ยาว|หนา)\s+[0-9.,]+.*$')
_THAI_NUMERALS   = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
_MOO_RE          = re.compile(r'หมู่ที่\s*(\d+)')

def clean_title(title: str, max_len: int = 70) -> str:
    t = str(title).strip()
    t = _TITLE_PREFIX_RE.sub('', t)
    t = _TITLE_SUFFIX_RE.sub('', t)
    # ตัด specs ก่อน (อยู่ภายในก่อน location) — รอบเดียว
    t = _SPECS_RE.sub('', t).strip()
    t = _DIM_RE.sub('', t).strip()
    # ตัด location ที่ท้าย — รอบ 2-3 (กรณี nested)
    for _ in range(2):
        t = _LOCATION_RE.sub('', t).strip()
        t = _LOCATION_RE2.sub('', t).strip()
    # Abbreviations
    t = t.replace('คอนกรีตเสริมเหล็ก', 'คสล.')
    t = t.replace('แอสฟัลท์ติกคอนกรีต', 'แอสฟัลต์')
    t = t.replace('แอสฟัลต์คอนกรีต', 'แอสฟัลต์')
    t = t.replace('คอนกรีดเสริมเหล็ก', 'คสล.')  # typo in original data
    # Convert Thai numerals + หมู่ที่
    t = t.translate(_THAI_NUMERALS)
    t = _MOO_RE.sub(r'ม.\1', t)
    t = t.strip()
    if len(t) > max_len:
        t = t[:max_len-3].rstrip() + '...'
    return t


_DEPT_REPLACEMENTS = [
    ('องค์การบริหารส่วนตำบล', 'อบต.'),
    ('องค์การบริหารส่วนจังหวัด', 'อบจ.'),
    ('เทศบาลตำบล', 'ทต.'),
    ('เทศบาลเมือง', 'ทม.'),
    ('เทศบาลนคร', 'ทน.'),
    ('การประปาส่วนภูมิภาคเขต', 'ประปาเขต'),
    ('การประปาส่วนภูมิภาค', 'ประปา'),
    ('แขวงทางหลวงชนบท', 'ทล.ชนบท'),
    ('แขวงทางหลวง', 'ทล.'),
    ('โยธาธิการและผังเมือง', 'โยธาฯ'),
    ('สำนักก่อสร้างทาง กรมทางหลวงชนบท', 'สนง.ก่อสร้างทาง กทล.ชนบท'),
    ('กรมทางหลวงชนบท', 'กทล.ชนบท'),
    ('กรมทางหลวง', 'กรมทล.'),
    ('กรมชลประทาน', 'กรมชลฯ'),
]

def clean_dept(dept: str, max_len: int = 35) -> str:
    d = str(dept)
    for old, new in _DEPT_REPLACEMENTS:
        d = d.replace(old, new)
    d = d.strip()
    if len(d) > max_len:
        d = d[:max_len-3] + '...'
    return d


# ── Transitions (from Classifier snapshot) ────────────────────
def _load_transitions() -> dict:
    if not TRANSITIONS_FILE.exists():
        return {}
    try:
        return json.loads(TRANSITIONS_FILE.read_text(encoding="utf-8")).get("transitions", {})
    except Exception:
        return {}


_FROM_TH = {
    "pre_tor": "วางแผน", "tor_review": "รับฟัง",
    "active_bidding": "ยื่นซอง", "pending_award": "รอผล",
    "awarded_jobs": "ประกาศแล้ว", "cancelled_jobs": "ยกเลิก",
}

def _transition_marker(jid: str, transitions: dict) -> str:
    """คืน '' หรือ ' 🆕' / ' ⬆️ จาก รับฟัง'"""
    t = transitions.get(jid)
    if not t:
        return ""
    if t["type"] == "new":
        return " 🆕"
    if t["type"] == "moved":
        from_th = _FROM_TH.get(t["from"], t["from"])
        return f" {t['arrow']} จาก {from_th}"
    return ""


# ── Card builders ─────────────────────────────────────────────

def _build_job_block(job: dict, transitions: dict) -> str:
    """Active bidding card — 5 lines"""
    title = clean_title(job.get("title", "ไม่มีชื่อ"))
    budget = fmt_budget(job.get("budget", 0))
    dept = clean_dept(job.get("department", ""))
    days = str(job.get("days_remaining", "")).strip()
    jid = str(job.get("job_id", ""))

    # Urgency emoji + label
    try:
        d = int(days)
        urgency = f"🚨 เหลือ {d} วัน" if d <= 1 else f"⏳ เหลือ {d} วัน"
    except ValueError:
        if days:
            urgency = f"⚠️ {days}"
        else:
            urgency = "⚠️ ไม่มี deadline"

    marker = _transition_marker(jid, transitions)

    lines = [
        f"{urgency}{marker}",
        f"└ {title}",
        f"  💰 {budget}",
        f"  🏛️ {dept}",
        f"  🆔 {jid}",
    ]
    return "\n".join(lines)


def _build_tor_block(job: dict, transitions: dict) -> str:
    """TOR review card — 5 lines, header = publish date"""
    title = clean_title(job.get("title", "ไม่มีชื่อ"))
    budget = fmt_budget(job.get("budget", 0))
    dept = clean_dept(job.get("department", ""))
    publish = str(job.get("publish_date", "")).strip()
    jid = str(job.get("job_id", ""))

    # Shorten DD/MM/YYYY → DD/MM
    pub_label = publish
    if "/" in publish:
        parts = publish.split("/")
        if len(parts) >= 2:
            pub_label = f"{parts[0]}/{parts[1]}"

    marker = _transition_marker(jid, transitions)

    lines = [
        f"📋 ประกาศ {pub_label}{marker}",
        f"└ {title}",
        f"  💰 {budget}",
        f"  🏛️ {dept}",
        f"  🆔 {jid}",
    ]
    return "\n".join(lines)


def _active_sort_key(job: dict):
    """Sort active jobs by days_remaining ascending (urgent first)"""
    d = str(job.get("days_remaining", "")).strip()
    try:
        return (0, int(d))
    except ValueError:
        return (1, 9999)  # non-numeric (deadline ผ่าน, ว่าง) → ท้าย


def _tor_sort_key(job: dict):
    """Sort tor jobs by publish_date ascending (เก่า first)"""
    pub = str(job.get("publish_date", ""))
    try:
        parts = pub.split("/")
        if len(parts) == 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y > 2400:
                y -= 543
            return (y, m, d)
    except Exception:
        pass
    return (9999, 99, 99)


def _sheet_link(gid: int) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={gid}"


def format_messages(jobs: list[dict], awarded_count: int, tor_jobs: list[dict] = None) -> list[str]:
    """
    Style A — Card format + Google Sheet link
    Part 1: active_bidding (sorted by days_remaining asc, urgent first)
    Part 2: tor_review (sorted by publish_date asc, เก่า first)
    """
    MAX_LEN  = 4900
    today    = datetime.now().strftime("%d/%m/%Y %H:%M น.")
    tor_jobs = tor_jobs or []
    transitions = _load_transitions()

    if not jobs and not tor_jobs:
        msg = (
            f"🏗️ Bid Master • {today}\n\n"
            f"📭 ไม่มีงาน e-bidding กำลังประมูลหรือรับฟังตอนนี้\n"
            f"🏆 ประกาศผู้ชนะแล้ว: {awarded_count} งาน\n\n"
            f"🤖 Sebastian"
        )
        return [msg]

    messages = []

    def _pack(header: str, blocks: list, footer: str):
        """แพ็ค blocks เข้า messages — ไม่ตัดกลาง block"""
        current = header
        part_n  = 1
        for block in blocks:
            candidate = current + "\n\n" + block
            if len(candidate + footer) > MAX_LEN and current != header:
                messages.append(current + footer)
                part_n += 1
                header_short = header.split("━━━")[0].rstrip() + f"\n━━━ (ต่อ part {part_n}) ━━━"
                current = header_short + "\n\n" + block
            else:
                current = candidate
        messages.append(current + footer)

    # ── Part 1: Active Bidding ──
    if jobs:
        sorted_active = sorted(jobs, key=_active_sort_key)
        header1 = (
            f"🏗️ Bid Master • {today}\n"
            f"🔔 ยื่นซอง {len(jobs)} • 🟢 รับฟัง {len(tor_jobs)} • 🏆 ประกาศแล้ว {awarded_count}\n\n"
            f"━━━ 🔵 ยื่นซองได้ตอนนี้ ━━━"
        )
        blocks1 = [_build_job_block(job, transitions) for job in sorted_active]
        footer1 = (
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 ดูชีต Active เต็ม:\n{_sheet_link(ACTIVE_GID)}\n\n"
            f"🤖 Sebastian"
        )
        _pack(header1, blocks1, footer1)

    # ── Part 2: TOR Review ──
    if tor_jobs:
        sorted_tor = sorted(tor_jobs, key=_tor_sort_key)
        header2 = (
            f"🏗️ Bid Master • {today}\n\n"
            f"━━━ 🟢 รับฟังคำวิจารณ์ ━━━"
        )
        blocks2 = [_build_tor_block(job, transitions) for job in sorted_tor]
        footer2 = (
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 ดูชีต TOR เต็ม:\n{_sheet_link(TOR_GID)}\n\n"
            f"🤖 Sebastian"
        )
        _pack(header2, blocks2, footer2)

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
