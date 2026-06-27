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
