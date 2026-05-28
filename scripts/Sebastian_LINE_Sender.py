"""
Sebastian_LINE_Sender.py — LINE push notification worker v1

Runs every 1 min via Task Scheduler (BidMaster_LINE_Sender).
Single iteration per run: recover stuck → acquire 1 item → send → mark result.

Flags:
  --dry-run   render message + log queue transitions, skip actual LINE API call
              (ใช้ก่อน live send เพื่อ validate formatting + delivery semantics)

Error classification:
  retryable : 429, 5xx, timeout, network error (max 3 retries, 5-min fixed delay)
  terminal  : 400/403 invalid user, blocked, unlinked LINE account

State transitions handled by SubscriptionStore.
Logs: logs/line_sender/sender_YYYYMMDD.log
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests as req_lib

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import (
    SubscriptionStore, init_schema, worker_id, _now,
)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Constants ─────────────────────────────────────────────────────────────────

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
BATCH_SIZE    = 1   # correctness > throughput during pilot
LOG_DIR       = Path(__file__).parent.parent / "logs" / "line_sender"
TZ_TH         = timezone(timedelta(hours=7))

TYPE_LABELS = {
    "D0": "ประกาศจัดซื้อจัดจ้าง",
    "W0": "ประกาศผลผู้ชนะ",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_line_token() -> str:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEBASTIAN_LINE_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    token = os.environ.get("SEBASTIAN_LINE_TOKEN", "")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN not found in .env or environment")
    return token


def _shorten_project_name(name: str, max_len: int = 60) -> str:
    """ตัดชื่อโครงการ — ลบ prefix ที่ไม่มีความหมายออก"""
    prefixes = [
        "ประกวดราคาจ้างก่อสร้าง", "ประกวดราคาจ้าง", "ประกวดราคาซื้อ",
        "ซื้อ", "จ้าง", "จ้างก่อสร้าง", "ประกวดราคา",
    ]
    result = name.strip()
    for p in prefixes:
        if result.startswith(p):
            result = result[len(p):].lstrip()
            break
    # ตัด suffix เช่น "ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    for suffix in [" ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                   " โดยวิธีเฉพาะเจาะจง", " ด้วยวิธีคัดเลือก"]:
        if result.endswith(suffix):
            result = result[:-len(suffix)].rstrip()
    if len(result) > max_len:
        result = result[:max_len] + "..."
    return result or name[:max_len]


def _fmt_budget(budget: float) -> str:
    """แสดงราคากลางในรูปแบบอ่านง่าย เช่น 21.7 ล้าน / 850,000"""
    if not budget:
        return "ไม่ระบุ"
    if budget >= 1_000_000:
        return f"{budget / 1_000_000:.1f} ล้านบาท"
    return f"{int(budget):,} บาท"


def format_notification(project_id: str, province: str = "",
                         announce_type: str = "D0", budget: float = 0,
                         project_name: str = "", dept_name: str = "",
                         deliver_day: int = 0, report_date: str = "",
                         is_backfill: bool = False,
                         source_stage: str = "api_enriched") -> str:
    """
    v1 Mobile-first format — optimize สำหรับ 3-second decision scan
    ลำดับ: geography → project → money → agency → timeline
    """
    short_name = _shorten_project_name(project_name) if project_name else project_id
    lines = []

    if is_backfill:
        lines.append("📦 โครงการที่ยังเปิดประมูลอยู่")
    else:
        lines.append("🔔 พบโครงการใหม่")

    lines.append(f"📍 {province or 'ไม่ระบุจังหวัด'}")
    lines.append(f"🏗 {short_name}")
    lines.append(f"💰 ราคากลาง {_fmt_budget(budget)}")

    if dept_name:
        lines.append(f"🏢 {dept_name}")

    if deliver_day:
        lines.append(f"⏱ ระยะเวลา {deliver_day} วัน")

    if report_date:
        lines.append(f"📅 ประกาศ {report_date}")

    lines.append(f"\n🔑 รหัส: {project_id}")

    if source_stage == "rss_provisional":
        lines.append("📡 ข้อมูลเบื้องต้นจาก RSS")

    return "\n".join(lines)


def send_line_push(token: str, line_user_id: str, text: str) -> tuple[bool, str, str]:
    """
    Returns (success, error_type, error_msg).
    error_type: '' | 'retryable' | 'terminal'
    """
    try:
        r = req_lib.post(
            LINE_PUSH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"to": line_user_id, "messages": [{"type": "text", "text": text}]},
            timeout=10,
        )
        if r.status_code == 200:
            return True, "", ""
        try:
            detail = r.json().get("message", r.text[:120])
        except Exception:
            detail = r.text[:120]
        if r.status_code == 429:
            return False, "retryable", f"HTTP 429 rate_limit: {detail}"
        if r.status_code >= 500:
            return False, "retryable", f"HTTP {r.status_code}: {detail}"
        # 400/403 — invalid user ID, blocked, unlinked
        return False, "terminal", f"HTTP {r.status_code}: {detail}"
    except req_lib.Timeout:
        return False, "retryable", "timeout"
    except Exception as e:
        return False, "retryable", str(e)[:200]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LINE notification sender worker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render message + log transitions, skip actual LINE API call")
    args, _ = parser.parse_known_args()
    dry_run = args.dry_run

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"sender_{datetime.now().strftime('%Y%m%d')}.log"

    def log(msg: str):
        line = f"[{_now()}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    init_schema()
    store = SubscriptionStore()
    wid   = worker_id()
    mode  = "DRY RUN" if dry_run else "LIVE"
    log(f"=== LINE Sender start worker_id={wid} mode={mode} ===")

    # Step 1: recover stuck 'sending' items (crash window cleanup)
    recovered = store.recover_stuck_sending()
    if recovered:
        log(f"Recovered {recovered} stuck sending → pending (worker_timeout)")

    # Step 2: load LINE token (skip validation in dry-run)
    token = ""
    if not dry_run:
        try:
            token = _load_line_token()
        except RuntimeError as e:
            log(f"ABORT: {e}")
            return

    # Step 3: atomic acquire
    items = store.acquire_batch(batch_size=BATCH_SIZE, wid=wid)
    if not items:
        log("No pending items — exit")
        return

    item = items[0]
    log(
        f"Acquired queue_id={item['id']} project={item['project_id']} "
        f"customer={item['customer_id']} retry={item['retry_count']}"
    )

    # Step 4: enrich missing fields from process5 API (opportunistic — fallback to snapshot)
    dept_name   = item.get("dept_name") or ""
    budget      = float(item.get("budget") or 0)
    deliver_day = 0
    report_date = ""

    if not dept_name or not budget:
        try:
            from process5_http_client import get_procurement_detail
            enriched = get_procurement_detail(item["project_id"])
            if enriched.get("valid"):
                dept_name   = enriched.get("dept_sub_name") or dept_name
                budget      = enriched.get("budget") or budget
                deliver_day = enriched.get("deliver_day") or 0
                report_date = enriched.get("report_date") or ""
                log(f"  Enriched: dept={dept_name[:30]} budget={budget} days={deliver_day}")
        except Exception as e:
            log(f"  Enrich failed (non-fatal): {e}")

    # Step 5: format message
    text = format_notification(
        project_id    = item["project_id"],
        province      = item.get("province") or "",
        announce_type = item.get("announce_type") or "D0",
        budget        = budget,
        project_name  = item.get("project_name") or "",
        dept_name     = dept_name,
        deliver_day   = deliver_day,
        report_date   = report_date,
        is_backfill   = bool(item.get("is_backfill")),
        source_stage  = item.get("source_stage") or "api_enriched",
    )

    if dry_run:
        log("─── DRY RUN: message preview ───────────────────────────")
        for line_text in text.splitlines():
            log(f"  {line_text}")
        log(f"  → TO: {item['line_user_id']}")
        log("────────────────────────────────────────────────────────")
        # Release back to pending — dry run doesn't consume the item
        store.mark_delivery_result(
            queue_id    = item["id"],
            customer_id = item["customer_id"],
            project_id  = item["project_id"],
            status      = "failed",
            error       = "dry_run — not sent",
            error_type  = "retryable",
        )
        log("DRY RUN complete — item returned to pending queue")
        log("=== LINE Sender done (dry-run) ===")
        return

    # Step 5: send live
    success, error_type, error_msg = send_line_push(token, item["line_user_id"], text)

    # Step 6: mark result
    store.mark_delivery_result(
        queue_id    = item["id"],
        customer_id = item["customer_id"],
        project_id  = item["project_id"],
        status      = "sent" if success else "failed",
        error       = error_msg,
        error_type  = error_type,
    )

    if success:
        log(f"SENT   queue_id={item['id']} → {item['line_user_id']}")
    elif error_type == "terminal":
        log(f"FAILED queue_id={item['id']} terminal error_type={error_type} msg={error_msg[:80]}")
    else:
        log(f"RETRY  queue_id={item['id']} retryable={error_type} msg={error_msg[:80]}")

    log("=== LINE Sender done ===")


if __name__ == "__main__":
    main()
