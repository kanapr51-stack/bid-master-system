"""test_bid_results.py — เก็บ bidders (competitive intel) + idempotent + dedupe ราย."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()
s = db.SubscriptionStore()

bidders = [
    {"receiveNameTh": "บ.A", "receiveTin": "111", "priceProposal": "100", "priceAgree": "95",
     "resultFlag": "", "is_sme": True},
    {"receiveNameTh": "บ.B", "receiveTin": "222", "priceProposal": "110", "priceAgree": "",
     "resultFlag": "", "is_sme": False},
]
s.record_bid_results("P1", bidders, fetched_at="2026-06-06")
got = s.get_bid_results("P1")
assert len(got) == 2, got
win = [g for g in got if g["is_winner"]]
assert len(win) == 1 and win[0]["bidder_name"] == "บ.A", win
assert win[0]["price_agree"] == "95", win[0]

# idempotent: เก็บซ้ำ (UNIQUE project+tin) → ไม่เพิ่ม row
s.record_bid_results("P1", bidders, fetched_at="2026-06-07")
assert len(s.get_bid_results("P1")) == 2, "idempotent fail"

# คนละงาน
s.record_bid_results("P2", [bidders[0]], fetched_at="2026-06-06")
assert len(s.get_bid_results("P2")) == 1
assert len(s.get_bid_results("P1")) == 2

print("✅ PASS bid_results")
