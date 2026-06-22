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

# no-TIN: 2 bidder ไม่มี receiveTin คนละชื่อ → ต้องเก็บครบ 2 (เดิม PK ชนเหลือ 1)
s.record_bid_results("P3", [
    {"receiveNameTh": "หจก.ไร้ทิน A", "receiveTin": "", "priceProposal": "800000", "priceAgree": ""},
    {"receiveNameTh": "หจก.ไร้ทิน B", "receiveTin": "", "priceProposal": "900000", "priceAgree": ""},
], fetched_at="2026-06-13")
rows = s.get_bid_results("P3")
assert len(rows) == 2, f"no-TIN ต้องเก็บครบ 2: {len(rows)}"
# bidder ไม่มีทั้ง tin/name → ข้าม
s.record_bid_results("P4", [{"receiveNameTh": "", "receiveTin": "", "priceProposal": "1"}], fetched_at="2026-06-13")
assert len(s.get_bid_results("P4")) == 0, "ไม่มี tin/name → ข้าม"
print("✅ no-TIN name-fallback")

# v135 perf fix: normalized_name ต้องถูกคำนวณตอนเขียน และไม่ถูกเคลียร์เป็น NULL ตอนเขียนซ้ำ
import portal_views as pv
with db.get_connection() as c:
    nn = c.execute("SELECT normalized_name FROM bid_results WHERE project_id='P1' AND bidder_tin='111'").fetchone()
assert nn[0] == pv._norm_name("บ.A"), nn
s.record_bid_results("P1", bidders, fetched_at="2026-06-08")   # เขียนซ้ำ (เช่น winner-poller อัปเดต)
with db.get_connection() as c:
    nn2 = c.execute("SELECT normalized_name FROM bid_results WHERE project_id='P1' AND bidder_tin='111'").fetchone()
assert nn2[0] == pv._norm_name("บ.A"), nn2   # ต้องไม่หาย
print("✅ record_bid_results: normalized_name คงอยู่หลังเขียนซ้ำ")

print("✅ PASS bid_results")
