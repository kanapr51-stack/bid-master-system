"""
sebastian_health_check.py — Deterministic pipeline health check
รันหลัง pipeline เสร็จทุกครั้ง ตรวจสอบ 5 จุด แล้วรายงาน Discord
ไม่ใช้ AI API — ใช้ rule-based + เปรียบเทียบกับ baseline ครั้งก่อน
"""

import json
import os
import sys
import re
from datetime import datetime
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from Sebastian_Discord_Notify import load_env, get_credentials, send

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
BASELINE_PATH  = Path(__file__).parent.parent / "data" / "health_baseline.json"
SHEETS_TO_CHECK = [
    "all_jobs", "awarded_jobs", "pending_award",
    "active_bidding", "tor_review", "pre_tor", "cancelled_jobs",
]

# ────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────

def load_baseline() -> dict:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {}


def save_baseline(data: dict):
    BASELINE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def count_sheet_rows(gc, sheet_name: str) -> int:
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        return max(0, len(ws.get_all_values()) - 1)  # ลบ header
    except Exception as e:
        return -1  # -1 = error


def check_province_purity(gc) -> tuple[int, int]:
    """คืน (non_nakhon_count, total_rows)"""
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet("all_jobs")
    vals = ws.get_all_values()
    headers = vals[0]
    rows = vals[1:]
    prov_idx = next((i for i, h in enumerate(headers) if "province" in h.lower()), None)
    if prov_idx is None:
        return -1, len(rows)
    non_nakhon = sum(1 for r in rows if len(r) > prov_idx and r[prov_idx].strip() != "นครพนม")
    return non_nakhon, len(rows)


def check_winner_cache() -> int:
    path = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"
    if not path.exists():
        return -1
    return len(json.loads(path.read_text(encoding="utf-8")))


def check_seen_set() -> int:
    path = Path(__file__).parent.parent / "data" / "cgd_discovery_seen.json"
    if not path.exists():
        return -1
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return len(data.get("ids", []))
    return len(data)


# ────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────

def run_health_check(send_discord: bool = True) -> dict:
    from sheets_client import get_client
    gc = get_client()

    now     = datetime.now().strftime("%Y-%m-%d %H:%M")
    baseline = load_baseline()
    results  = {}
    issues   = []  # ⚠️ หรือ ❌
    oks      = []  # ✅

    # ── 1. Sheet row counts ──────────────────────
    sheet_counts = {}
    for name in SHEETS_TO_CHECK:
        n = count_sheet_rows(gc, name)
        sheet_counts[name] = n
    results["sheets"] = sheet_counts

    # all_jobs ต้องมีข้อมูล
    all_jobs_n = sheet_counts["all_jobs"]
    if all_jobs_n <= 0:
        issues.append(f"❌ all_jobs ว่างเปล่า ({all_jobs_n} rows)")
    else:
        oks.append(f"✅ all_jobs: {all_jobs_n:,} rows")

    # awarded_jobs ต้องไม่ลดลงจากครั้งก่อน
    prev_awarded = baseline.get("sheets", {}).get("awarded_jobs", 0)
    cur_awarded  = sheet_counts["awarded_jobs"]
    if cur_awarded < prev_awarded:
        issues.append(f"❌ awarded_jobs ลดลง {prev_awarded:,} → {cur_awarded:,}")
    elif cur_awarded > prev_awarded:
        delta = cur_awarded - prev_awarded
        oks.append(f"✅ awarded_jobs: {cur_awarded:,} (+{delta:,})")
    else:
        oks.append(f"✅ awarded_jobs: {cur_awarded:,} (ไม่เปลี่ยน)")

    # sum ทุก sheet ควร ≈ all_jobs (อนุญาต diff ≤ 50 จาก race condition)
    derived = ["awarded_jobs", "pending_award", "active_bidding",
               "tor_review", "pre_tor", "cancelled_jobs"]
    total_derived = sum(sheet_counts.get(s, 0) for s in derived)
    diff = abs(all_jobs_n - total_derived)
    if diff > 50:
        issues.append(f"⚠️ sheet sum mismatch: all_jobs={all_jobs_n:,} vs derived sum={total_derived:,} (diff={diff})")
    else:
        oks.append(f"✅ sheet sum consistent (diff={diff})")

    # ── 2. Province purity ───────────────────────
    non_nakhon, total = check_province_purity(gc)
    results["non_nakhon"] = non_nakhon
    if non_nakhon > 0:
        issues.append(f"⚠️ พบข้อมูลจังหวัดอื่นใน all_jobs: {non_nakhon} rows")
    else:
        oks.append(f"✅ all_jobs เป็นนครพนม 100%")

    # ── 3. Winner cache ──────────────────────────
    winner_n = check_winner_cache()
    results["winner_cache"] = winner_n
    prev_winner = baseline.get("winner_cache", 0)
    if winner_n < prev_winner:
        issues.append(f"❌ winner_cache ลดลง {prev_winner:,} → {winner_n:,}")
    elif winner_n < 0:
        issues.append("❌ winner_cache_bootstrap.json หาไม่เจอ")
    else:
        delta = winner_n - prev_winner
        oks.append(f"✅ winner_cache: {winner_n:,}" + (f" (+{delta:,})" if delta else ""))

    # ── 4. CGD seen set ──────────────────────────
    seen_n = check_seen_set()
    results["seen_set"] = seen_n
    prev_seen = baseline.get("seen_set", 0)
    if seen_n < 0:
        issues.append("❌ cgd_discovery_seen.json หาไม่เจอ")
    elif seen_n < prev_seen:
        issues.append(f"⚠️ CGD seen set ลดลง {prev_seen:,} → {seen_n:,}")
    else:
        oks.append(f"✅ CGD seen: {seen_n:,}")

    # ── 5. pending_award trend ───────────────────
    prev_pending = baseline.get("sheets", {}).get("pending_award", 0)
    cur_pending  = sheet_counts["pending_award"]
    if prev_pending and cur_pending > prev_pending * 1.2:
        issues.append(f"⚠️ pending_award โตผิดปกติ {prev_pending:,} → {cur_pending:,} (+{cur_pending-prev_pending:,})")
    else:
        oks.append(f"✅ pending_award: {cur_pending:,}")

    # ── Save new baseline ────────────────────────
    results["checked_at"] = now
    save_baseline(results)

    # ── Build Discord message ────────────────────
    status = "✅ สุขภาพดี" if not issues else ("⚠️ มีจุดน่าสังเกต" if all("⚠️" in i for i in issues) else "❌ พบปัญหา")

    lines = [f"🏥 Health Check {now} — {status}"]
    lines.append("")
    for ok in oks:
        lines.append(ok)
    if issues:
        lines.append("")
        for issue in issues:
            lines.append(issue)

    msg = "\n".join(lines)
    print(msg)

    if send_discord:
        load_env()
        token, ch = get_credentials()
        send(token, ch, msg)

    return results


if __name__ == "__main__":
    run_health_check(send_discord=True)
