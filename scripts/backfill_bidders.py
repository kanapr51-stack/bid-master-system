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


def load_seen() -> set:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            return set()
    return set()


def save_seen(seen: set):
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def run(provinces: list, fy: list, limit=None, dry_run=False, sleep=SLEEP) -> dict:
    """loop backfill ทุก candidate. resumable (seen) + fail-open. คืน stats dict.
    Resume 2 ชั้น: stored ตัดด้วย bid_results SQL · empty ตัดด้วย seen-set.
    Trade-off (รับได้): SIGTERM ระหว่าง checkpoint → empty ≤CHECKPOINT_EVERY งานถูกดึงซ้ำ (ปลอดภัย ไม่ double-write
    เพราะ record_bid_results = INSERT OR REPLACE) · งาน empty ที่ภายหลังมี bidder จะไม่ถูกดึงซ้ำ (อยู่ใน seen)."""
    import time as _t
    seen = load_seen()
    with get_connection() as conn:
        cands = select_candidates(conn, provinces, fy, seen, limit)
    log(f"candidates: {len(cands)} งาน (seen={len(seen)}, dry_run={dry_run})")
    stats = {"stored": 0, "empty": 0, "error": 0}
    if dry_run:
        return stats
    store = SubscriptionStore()
    t0 = _t.time()
    for i, (pid, adate) in enumerate(cands, 1):
        status = backfill_one(store, pid, adate)
        stats[status] += 1
        if status != "error":          # error ไม่ mark seen → retry รอบหน้า
            seen.add(pid)
        if i % CHECKPOINT_EVERY == 0:
            save_seen(seen)
            el = _t.time() - t0
            eta = el / i * (len(cands) - i)
            log(f"  [{i}/{len(cands)}] stored={stats['stored']} empty={stats['empty']} "
                f"error={stats['error']} | {el:.0f}s elapsed, ETA ~{eta:.0f}s")
        if sleep:
            time.sleep(sleep)
    save_seen(seen)
    log(f"✅ เสร็จ: stored={stats['stored']} empty={stats['empty']} error={stats['error']}")
    return stats


def main():
    ap = argparse.ArgumentParser(description="Backfill full-bidder list (2A) จาก cgd_winners → bid_results")
    ap.add_argument("--provinces", default="นครพนม,บึงกาฬ", help="คั่นด้วย ,")
    ap.add_argument("--fy", default="2567,2568,2569", help="ปีงบ คั่นด้วย ,")
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนงาน (probe run)")
    ap.add_argument("--dry-run", action="store_true", help="นับ candidate อย่างเดียว ไม่ดึง API")
    args = ap.parse_args()
    run([p.strip() for p in args.provinces.split(",") if p.strip()],
        [f.strip() for f in args.fy.split(",") if f.strip()],
        limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
