"""backfill_bidders.py — เติม bid_results ด้วย full-bidder list ของงานที่จบแล้ว (2A).
รันบน VPS: ดึง projectId งานแข่งจริงจาก cgd_winners → getProcureResult → record_bid_results.
sequential + politeness sleep + resumable (backfill_seen.json) + fail-open ต่องาน.
fetched_at = announce_date ของงาน (recency ถูกต้องสำหรับ 2B). ดู spec 2026-06-13-allbidders-backfill-2a."""
import os, sys, json, time, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from process5_http_client import get_procure_result
from Sebastian_Customer_DB import SubscriptionStore, get_connection
from cgd_intel import COMPETITIVE_SET

DATA_DIR = Path(os.environ.get("BMS_DATA_DIR", "data"))
SEEN_PATH = DATA_DIR / "backfill_seen.json"
SLEEP = 1.5            # politeness ต่องาน (rate-limit retry อยู่ใน _get แล้ว)
CHECKPOINT_EVERY = 50


def log(msg: str):
    print(msg, flush=True)


def select_candidates(conn, provinces: list, fy: list, seen: set, limit=None) -> list:
    """คืน [(project_id, announce_date)] จาก cgd_winners ตาม scope, ตัดที่มีใน bid_results + seen.
    เรียง announce_date ใหม่→เก่า (งานสดก่อน). limit=None → ทั้งหมด."""
    pv = ",".join("?" for _ in provinces)
    fyp = ",".join("?" for _ in fy)
    ct = ",".join("?" for _ in COMPETITIVE_SET)
    sql = (f"SELECT project_id, COALESCE(announce_date,'') FROM cgd_winners "
           f"WHERE province IN ({pv}) AND proc_type IN ({ct}) AND fiscal_year IN ({fyp}) "
           f"AND win_price>0 AND project_id NOT IN (SELECT DISTINCT project_id FROM bid_results) "
           f"ORDER BY announce_date DESC")
    params = [*provinces, *COMPETITIVE_SET, *fy]
    rows = [(pid, d) for pid, d in conn.execute(sql, params) if pid not in seen]
    return rows[:limit] if limit is not None else rows


def backfill_one(store, pid: str, announce_date) -> str:
    """ดึง 1 งาน → เก็บ bidders. คืน 'stored'|'empty'|'error'.
    announce_date: str | None ('' จาก COALESCE → fallback now). fetched_at=announce_date
    (งานเก่า ไม่ใช่ now → recency ถูก). fail-open: exception/{}→'error' (ไม่ mark seen → retry รอบหน้า)."""
    try:
        res = get_procure_result(pid)
    except Exception as e:
        log(f"  {pid} fetch พลาด: {type(e).__name__}: {e}")
        return "error"
    if "bidders" not in res:          # {} = API error/rate หลัง retry ใน _get → ไม่ mark seen
        log(f"  {pid} API คืน {{}} (ไม่มี key bidders) — error")
        return "error"
    bidders = res["bidders"]
    if not bidders:
        return "empty"
    store.record_bid_results(pid, bidders, fetched_at=announce_date or None)
    return "stored"
