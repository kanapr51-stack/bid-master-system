"""
Sebastian_LINE_Push.py — ส่งสรุปงานประมูลรายบุคคลผ่าน Sebastian LINE OA

Flow:
  1. อ่าน customers sheet → filter status trial/active + มี จังหวัด ตั้งค่าแล้ว
  2. สำหรับแต่ละ customer → filter active_bidding + tor_review ตาม จังหวัด/อำเภอ/keywords
  3. Push message ไป line_user_id ของแต่ละคน ด้วย SEBASTIAN_LINE_TOKEN

ใช้ SEBASTIAN_LINE_TOKEN (Sebastian OA) ไม่ใช่ LINE_CHANNEL_ACCESS_TOKEN (BSC group)

Usage:
    python scripts/Sebastian_LINE_Push.py
    python scripts/Sebastian_LINE_Push.py --dry-run   # preview เฉยๆ ไม่ส่งจริง
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.error
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from customers_db import list_all as list_customers
from Sebastian_LINE_Notify import (
    fmt_budget, clean_title, clean_dept,
    _active_sort_key, _tor_sort_key, _load_transitions, _transition_marker,
    _build_job_block, _build_tor_block, _sheet_link,
    SPREADSHEET_ID, SHEET_ACTIVE, SHEET_TOR, ACTIVE_GID, TOR_GID,
)

LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"
MAX_MSG_LEN   = 4900


# ── Env ─────────────────────────────────────────────────────────────────────

def load_env():
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_token() -> str:
    t = os.environ.get("SEBASTIAN_LINE_TOKEN", "").strip().lstrip("﻿")
    if not t:
        raise ValueError("SEBASTIAN_LINE_TOKEN ไม่พบใน .env")
    return t


# ── Data ────────────────────────────────────────────────────────────────────

def get_all_active_jobs() -> list[dict]:
    try:
        ws = open_sheet(SPREADSHEET_ID, SHEET_ACTIVE)
        return ws.get_all_records()
    except Exception as e:
        print(f"[WARN] อ่าน active_bidding ไม่ได้: {e}", flush=True)
        return []


def get_all_tor_jobs() -> list[dict]:
    try:
        ws = open_sheet(SPREADSHEET_ID, SHEET_TOR)
        return ws.get_all_records()
    except Exception as e:
        print(f"[WARN] อ่าน tor_review ไม่ได้: {e}", flush=True)
        return []


# ── Filter ──────────────────────────────────────────────────────────────────

def _parse_csv(val: str) -> list[str]:
    """'บึงกาฬ, นครพนม' → ['บึงกาฬ', 'นครพนม']"""
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


def _match_text(text: str, keywords: list[str]) -> bool:
    """True ถ้า text มีคำ keyword ใดๆ อยู่"""
    t = str(text).lower()
    return any(kw.lower() in t for kw in keywords)


def filter_jobs(jobs: list[dict], customer: dict) -> list[dict]:
    """Filter jobs ตาม customer จังหวัด/อำเภอ/keywords"""
    provinces = _parse_csv(customer.get("จังหวัด", ""))
    districts  = _parse_csv(customer.get("อำเภอ", ""))
    keywords   = _parse_csv(customer.get("keywords", ""))

    if not provinces:
        return []  # ถ้าไม่ตั้งค่าจังหวัด → ไม่ส่ง

    result = []
    for job in jobs:
        job_province = str(job.get("province", "") or "")
        job_district = str(job.get("district", "") or "")
        job_title    = str(job.get("title", "") or "")
        job_dept     = str(job.get("department", "") or "")

        # Province must match (required)
        if job_province not in provinces:
            continue

        # District filter (optional — ถ้าว่างหมายถึงทั้งจังหวัด)
        if districts and job_district not in districts:
            # Allow even if district is empty in job (province-level match is enough)
            if job_district:
                continue

        # Keywords filter (optional — ถ้าไม่ตั้ง ส่งทั้งหมด)
        if keywords:
            combined = f"{job_title} {job_dept}"
            if not _match_text(combined, keywords):
                continue

        result.append(job)
    return result


# ── Format ──────────────────────────────────────────────────────────────────

def format_customer_messages(
    customer: dict,
    active_jobs: list[dict],
    tor_jobs: list[dict],
    awarded_count: int,
) -> list[str]:
    """สร้างข้อความสำหรับ customer คนเดียว — multi-part ถ้ายาวเกิน"""
    today  = datetime.now().strftime("%d/%m/%Y %H:%M น.")
    name   = customer.get("display_name", "ลูกค้า") or "ลูกค้า"
    transitions = _load_transitions()

    messages: list[str] = []

    if not active_jobs and not tor_jobs:
        return [
            f"🏗️ Bid Master • {today}\n\n"
            f"สวัสดีครับ คุณ{name} 🎩\n\n"
            f"📭 ไม่มีงานประมูลใหม่ที่ตรงเงื่อนไขของคุณวันนี้\n"
            f"🏆 ประกาศผู้ชนะแล้ว: {awarded_count} งาน\n\n"
            f"🤖 Sebastian"
        ]

    def _pack(header: str, blocks: list[str], footer: str):
        current = header
        part_n  = 1
        for block in blocks:
            candidate = current + "\n\n" + block
            if len(candidate + footer) > MAX_MSG_LEN and current != header:
                messages.append(current + footer)
                part_n += 1
                h_short = header.split("━━━")[0].rstrip() + f"\n━━━ (ต่อ part {part_n}) ━━━"
                current = h_short + "\n\n" + block
            else:
                current = candidate
        messages.append(current + footer)

    # Part 1: Active Bidding
    if active_jobs:
        sorted_active = sorted(active_jobs, key=_active_sort_key)
        header1 = (
            f"🏗️ Bid Master • {today}\n"
            f"สวัสดีครับ คุณ{name} 🎩\n"
            f"🔔 ยื่นซอง {len(active_jobs)} • 🟢 รับฟัง {len(tor_jobs)} • 🏆 ประกาศแล้ว {awarded_count}\n\n"
            f"━━━ 🔵 ยื่นซองได้ตอนนี้ ━━━"
        )
        blocks1 = [_build_job_block(j, transitions) for j in sorted_active]
        footer1 = (
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 ดูชีต Active เต็ม:\n{_sheet_link(ACTIVE_GID)}\n\n"
            f"🤖 Sebastian"
        )
        _pack(header1, blocks1, footer1)

    # Part 2: TOR Review
    if tor_jobs:
        sorted_tor = sorted(tor_jobs, key=_tor_sort_key)
        header2 = (
            f"🏗️ Bid Master • {today}\n"
            f"สวัสดีครับ คุณ{name} 🎩\n\n"
            f"━━━ 🟢 รับฟังคำวิจารณ์ ━━━"
        )
        blocks2 = [_build_tor_block(j, transitions) for j in sorted_tor]
        footer2 = (
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 ดูชีต TOR:\n{_sheet_link(TOR_GID)}\n\n"
            f"🤖 Sebastian"
        )
        _pack(header2, blocks2, footer2)

    return messages


# ── Send ────────────────────────────────────────────────────────────────────

def push_to_user(token: str, line_user_id: str, messages: list[str], dry_run: bool = False) -> bool:
    all_ok = True
    for i, msg in enumerate(messages, 1):
        label = f"part {i}/{len(messages)}" if len(messages) > 1 else ""
        if dry_run:
            print(f"  [DRY-RUN] would send {label} ({len(msg)} chars) to {line_user_id[:12]}...")
            continue

        payload = json.dumps({
            "to": line_user_id,
            "messages": [{"type": "text", "text": msg}],
        }).encode("utf-8")

        req = urllib.request.Request(
            LINE_PUSH_API,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                ok = resp.status == 200
                status = "OK" if ok else f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  ❌ LINE push error {e.code}: {body}", flush=True)
            ok = False
        except Exception as e:
            print(f"  ❌ LINE push exception: {e}", flush=True)
            ok = False

        if ok:
            print(f"  ✅ sent {label}".strip(), flush=True)
        else:
            all_ok = False
        time.sleep(0.3)  # avoid burst

    return all_ok


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Sebastian LINE push — per-customer notifications")
    ap.add_argument("--dry-run", action="store_true", help="Preview เฉยๆ ไม่ส่งจริง")
    args = ap.parse_args()

    load_env()
    token = get_token()

    # Load data once
    print("อ่านข้อมูล...", flush=True)
    all_active = get_all_active_jobs()
    all_tor    = get_all_tor_jobs()
    customers  = list_customers()

    # awarded count (for header)
    try:
        ws_aw = open_sheet(SPREADSHEET_ID, "awarded_jobs")
        awarded_count = len(ws_aw.get_all_records())
    except Exception:
        awarded_count = 0

    eligible = [
        c for c in customers
        if c.get("status") in ("trial", "active") and c.get("จังหวัด", "").strip()
    ]

    print(f"Customers eligible: {len(eligible)} / {len(customers)}", flush=True)
    print(f"All active jobs: {len(all_active)} | TOR: {len(all_tor)}", flush=True)
    print()

    total_ok = 0
    total_fail = 0

    for customer in eligible:
        uid   = customer["line_user_id"]
        name  = customer.get("display_name", uid[:12])
        prov  = customer.get("จังหวัด", "")
        dist  = customer.get("อำเภอ", "")

        active_filtered = filter_jobs(all_active, customer)
        tor_filtered    = filter_jobs(all_tor, customer)

        print(f"[{name}] จังหวัด={prov} | อำเภอ={dist or '(ทั้งจังหวัด)'}")
        print(f"  active: {len(active_filtered)} | tor: {len(tor_filtered)}", flush=True)

        if not active_filtered and not tor_filtered:
            print(f"  ⏭️  ไม่มีงานตรงเงื่อนไข — ข้าม", flush=True)
            print()
            continue

        messages = format_customer_messages(customer, active_filtered, tor_filtered, awarded_count)
        print(f"  → {len(messages)} ข้อความ ({[len(m) for m in messages]} chars)", flush=True)

        for i, msg in enumerate(messages, 1):
            part_label = f"part {i}" if len(messages) > 1 else ""
            print(f"  --- {part_label} preview ---")
            print("  " + msg[:200].replace("\n", "\n  ") + ("..." if len(msg) > 200 else ""))
            print()

        ok = push_to_user(token, uid, messages, dry_run=args.dry_run)
        if ok or args.dry_run:
            total_ok += 1
        else:
            total_fail += 1
        print()

    mode = "(DRY-RUN)" if args.dry_run else ""
    print(f"เสร็จสิ้น {mode} — ส่งสำเร็จ {total_ok} คน | ล้มเหลว {total_fail} คน", flush=True)


if __name__ == "__main__":
    main()
