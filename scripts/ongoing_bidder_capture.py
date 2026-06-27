"""ongoing_bidder_capture.py — เก็บผู้ยื่นทุกราย ทุกงาน หลังจากนี้ (นครพนม+บึงกาฬ, ทุก proc_type).
2 pass: LIVE (projects_seen → getProcureResult, แข่งสด) + CGD-FILL (cgd_winners → เฉพาะเจาะจง copy /
แข่ง API backstop). going-forward ไม่ใช่ backfill: epoch_date floor (Pass1) + epoch_fy floor (Pass2).
ดู spec 2026-06-27-ongoing-bidder-capture-design."""
import os, sys, json, time, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from Sebastian_Customer_DB import SubscriptionStore, get_connection
from cgd_intel import COMPETITIVE_SET
import backfill_bidders as bb   # reuse current_fy (DRY)

DATA_DIR = Path(os.environ.get("BMS_DATA_DIR", "data"))
STATE_PATH = DATA_DIR / "ongoing_capture_state.json"
SEEN_CGD_PATH = DATA_DIR / "ongoing_capture_seen_cgd.json"
PROVINCES = ["นครพนม", "บึงกาฬ"]
MIN_AGE_DAYS = 7      # ใหม่กว่านี้ = ยังไม่ award (ไม่ต้อง poll)
MAX_AGE_DAYS = 90     # เก่ากว่านี้ = เลิก poll (กัน loop งานที่ไม่มีผลถาวร)
SLEEP = 1.5
COOLDOWN_EVERY = 25
COOLDOWN_SEC = 130
CHECKPOINT_EVERY = 50


def log(msg: str):
    print(msg, flush=True)


def _today() -> datetime.date:
    return datetime.date.today()


def ensure_state(today: datetime.date = None) -> dict:
    """อ่าน/สร้าง state. epoch = เส้นแบ่ง going-forward (ไม่ backfill ของก่อน deploy).
    epoch_date = วันนี้ (ISO, floor ของ projects_seen.first_seen_at);
    epoch_fy = ปีงบไทยวันนี้ (floor ของ cgd_winners.fiscal_year — announce_date เป็น Thai date เทียบ ISO ไม่ได้)."""
    today = today or _today()
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state = {"epoch_date": today.isoformat(), "epoch_fy": bb.current_fy(today)}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


def load_seen(path: Path) -> set:
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            return set()
    return set()


def save_seen(path: Path, seen: set):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


# ─── Pass 2: CGD-FILL ─────────────────────────────────────────────────────────
def select_cgd_candidates(conn, provinces: list, epoch_fy: int, seen: set) -> list:
    """cgd_winners ในจังหวัดเป้าหมาย, fiscal_year >= epoch_fy (ไม่ backfill ปีเก่า),
    ยังไม่อยู่ bid_results, ไม่อยู่ seen. คืน [(project_id, proc_type, winner, win_price)]."""
    pv = ",".join("?" for _ in provinces)
    sql = (f"SELECT project_id, proc_type, winner, win_price FROM cgd_winners "
           f"WHERE province IN ({pv}) AND CAST(fiscal_year AS INTEGER) >= ? "
           f"AND project_id NOT IN (SELECT DISTINCT project_id FROM bid_results)")
    rows = conn.execute(sql, [*provinces, epoch_fy]).fetchall()
    return [(pid, pt, w, wp) for pid, pt, w, wp in rows if pid not in seen]


def _winner_as_bidder(winner, win_price) -> dict:
    """ผู้ชนะ cgd_winners → bidder dict (ผู้ยื่นรายเดียวงานเฉพาะเจาะจง). receiveTin='' →
    record_bid_results ใช้ name-fallback key (winner_tin เพี้ยน ~99%). priceAgree set → is_winner=1."""
    price = str(win_price) if win_price not in (None, "") else ""
    return {"receiveNameTh": winner or "", "receiveTin": "",
            "priceProposal": price, "priceAgree": price}


def capture_cgd_one(store, row, get_procure_result) -> str:
    """row=(pid, proc_type, winner, win_price). เฉพาะเจาะจง/ไม่แข่ง → copy (ไม่ยิง API);
    แข่ง → getProcureResult (fallback copy ถ้าล้ม/ว่าง). คืน 'copied'|'stored'|'empty'|'error'."""
    pid, proc_type, winner, win_price = row
    if proc_type not in COMPETITIVE_SET:
        if not winner:
            return "empty"
        store.record_bid_results(pid, [_winner_as_bidder(winner, win_price)], source="cgd_copy")
        return "copied"
    try:
        res = get_procure_result(pid)
    except Exception:
        res = {}
    if res.get("bidders"):
        store.record_bid_results(pid, res["bidders"], source="procure_api")
        return "stored"
    if winner:   # API ล้ม/ว่าง → มีผู้ชนะดีกว่าไม่มี
        store.record_bid_results(pid, [_winner_as_bidder(winner, win_price)], source="cgd_copy")
        return "copied"
    return "empty"


# ─── Pass 1: LIVE ─────────────────────────────────────────────────────────────
def select_live_candidates(conn, provinces: list, epoch_date: str, today: datetime.date = None,
                           min_age: int = MIN_AGE_DAYS, max_age: int = MAX_AGE_DAYS) -> list:
    """projects_seen ในจังหวัดเป้าหมาย, first_seen_at ในช่วง [max(epoch_date, today-max_age), today-min_age],
    ยังไม่อยู่ bid_results. (first_seen_at เป็น ISO timestamp → เทียบ date string แบบ prefix ได้;
    ±1 วันที่ขอบ window ยอมรับได้). คืน [project_id]."""
    today = today or _today()
    lo = max(epoch_date, (today - datetime.timedelta(days=max_age)).isoformat())
    hi = (today - datetime.timedelta(days=min_age)).isoformat()
    pv = ",".join("?" for _ in provinces)
    sql = (f"SELECT project_id FROM projects_seen WHERE province IN ({pv}) "
           f"AND first_seen_at >= ? AND first_seen_at <= ? "
           f"AND project_id NOT IN (SELECT DISTINCT project_id FROM bid_results)")
    return [r[0] for r in conn.execute(sql, [*provinces, lo, hi])]


def capture_live_one(store, pid: str, get_procure_result) -> str:
    """ดึง 1 งานสด → เก็บ bidders. ไม่มีผล (ยังไม่ award) → 'empty' (รอบหน้ายังเป็น candidate ตาม window).
    fail-open. คืน 'stored'|'empty'|'error'."""
    try:
        res = get_procure_result(pid)
    except Exception as e:
        log(f"  {pid} live fetch พลาด: {type(e).__name__}: {e}")
        return "error"
    if "bidders" not in res:
        return "error"
    if not res["bidders"]:
        return "empty"
    store.record_bid_results(pid, res["bidders"], source="procure_api")
    return "stored"


# ─── Run loops + CLI ──────────────────────────────────────────────────────────
def run_live(provinces, epoch_date, get_procure_result, sleep=SLEEP, today=None,
             cooldown_every=COOLDOWN_EVERY, cooldown_sec=COOLDOWN_SEC) -> dict:
    """Pass 1: poll งานสดใน window. ยิง API ทุก candidate → pace ทุก iteration."""
    with get_connection() as conn:
        cands = select_live_candidates(conn, provinces, epoch_date, today=today)
    log(f"[live] candidates: {len(cands)}")
    stats = {"stored": 0, "empty": 0, "error": 0}
    store = SubscriptionStore()
    for i, pid in enumerate(cands, 1):
        stats[capture_live_one(store, pid, get_procure_result)] += 1
        if sleep and cooldown_every and i % cooldown_every == 0 and i < len(cands):
            log(f"  💤 cooldown {cooldown_sec}s")
            time.sleep(cooldown_sec)
        elif sleep and i < len(cands):          # ไม่พักหลัง API ตัวสุดท้าย (ตรงกับ run_cgd)
            time.sleep(sleep)
    log(f"[live] stored={stats['stored']} empty={stats['empty']} error={stats['error']}")
    return stats


def run_cgd(provinces, epoch_fy, get_procure_result, sleep=SLEEP,
            cooldown_every=COOLDOWN_EVERY, cooldown_sec=COOLDOWN_SEC) -> dict:
    """Pass 2: เติมจาก cgd_winners. pace เฉพาะ API call (copy ไม่ยิง API → ไม่พัก กันค้างแสน copy).
    seen-set กัน re-poll empty/error; copied/stored ตัดด้วย NOT IN bid_results อยู่แล้ว."""
    seen = load_seen(SEEN_CGD_PATH)
    with get_connection() as conn:
        cands = select_cgd_candidates(conn, provinces, epoch_fy, seen)
    log(f"[cgd] candidates: {len(cands)}")
    stats = {"copied": 0, "stored": 0, "empty": 0, "error": 0}
    store = SubscriptionStore()
    api_calls = 0
    for i, row in enumerate(cands, 1):
        is_competitive = row[1] in COMPETITIVE_SET
        status = capture_cgd_one(store, row, get_procure_result)
        stats[status] += 1
        if status != "error":
            seen.add(row[0])
        if i % CHECKPOINT_EVERY == 0:
            save_seen(SEEN_CGD_PATH, seen)
        if is_competitive:                       # pace เฉพาะที่ยิง API
            api_calls += 1
            remaining_api = sum(1 for r in cands[i:] if r[1] in COMPETITIVE_SET)
            if sleep and cooldown_every and api_calls % cooldown_every == 0 and remaining_api:
                log(f"  💤 cooldown {cooldown_sec}s")
                time.sleep(cooldown_sec)
            elif sleep and remaining_api:
                time.sleep(sleep)
    save_seen(SEEN_CGD_PATH, seen)
    log(f"[cgd] copied={stats['copied']} stored={stats['stored']} "
        f"empty={stats['empty']} error={stats['error']}")
    return stats


def _notify(summary: dict):
    """ส่งสรุป Discord (best-effort — ไม่ให้ล้มงานถ้า notify พัง)."""
    try:
        from Sebastian_Discord_Notify import load_env, get_credentials, send
        load_env(); token, ch = get_credentials()
        parts = [f"{k}: {v}" for k, v in summary.items()]
        send(token, ch, "✅ Ongoing bidder capture เสร็จ — " + " | ".join(parts))
    except Exception as e:
        log(f"discord notify พลาด: {e}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Ongoing bidder capture (going-forward, 2 จังหวัด)")
    ap.add_argument("--provinces", default=",".join(PROVINCES), help="คั่นด้วย ,")
    ap.add_argument("--pass", dest="which", choices=["live", "cgd", "all"], default="all")
    ap.add_argument("--dry-run", action="store_true", help="นับ candidate ไม่เรียก API/ไม่เขียน")
    args = ap.parse_args()
    provinces = [p.strip() for p in args.provinces.split(",") if p.strip()]
    state = ensure_state()
    log(f"epoch_date={state['epoch_date']} epoch_fy={state['epoch_fy']} provinces={provinces}")
    if args.dry_run:
        with get_connection() as conn:
            nl = len(select_live_candidates(conn, provinces, state["epoch_date"]))
            nc = len(select_cgd_candidates(conn, provinces, state["epoch_fy"], load_seen(SEEN_CGD_PATH)))
        log(f"[dry-run] live candidates={nl}, cgd candidates={nc}")
        return
    from process5_http_client import get_procure_result
    summary = {}
    if args.which in ("live", "all"):
        summary["live"] = run_live(provinces, state["epoch_date"], get_procure_result)
    if args.which in ("cgd", "all"):
        summary["cgd"] = run_cgd(provinces, state["epoch_fy"], get_procure_result)
    _notify(summary)


if __name__ == "__main__":
    main()
