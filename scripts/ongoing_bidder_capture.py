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
