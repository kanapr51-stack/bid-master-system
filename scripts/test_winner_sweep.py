"""test_winner_sweep.py — persist_bid_results: เขียน sequential + fail-open."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import winner_sweep as ws

def test_persist_fail_open():
    written = []
    class FakeStore:
        def record_bid_results(self, jid, bidders):
            if jid == "BOOM":
                raise RuntimeError("db error")
            written.append((jid, len(bidders)))
    by_jid = {"J1": [{"receiveTin": "1"}], "BOOM": [{"receiveTin": "2"}], "J2": [{"receiveTin": "3"}], "J3": []}
    n = ws.persist_bid_results(FakeStore(), by_jid, log=lambda m: None)
    assert written == [("J1", 1), ("J2", 1)], written   # J3 ว่างข้าม, BOOM พังแต่ไม่ล้ม
    assert n == 2, n
    print("✅ persist_bid_results sequential + fail-open")

test_persist_fail_open()

def test_sweep_egp_collects_bidders():
    """sweep_egp ต้องคืน bidders ต่อ job (ไม่ใช่แค่ winner) — monkeypatch get_procure_result."""
    fake = {"PA": {"winner": "หจก.X", "winning_price": "950000",
                   "bidders": [{"receiveTin": "1", "priceAgree": "950000"},
                               {"receiveTin": "2", "priceProposal": "1100000"}]},
            "PB": {"bidders": [{"receiveTin": "3", "priceProposal": "500000"}]}}  # prelim ไม่มี winner
    ws.get_procure_result = lambda jid: fake.get(jid, {})
    results, bidders_by_jid = ws.sweep_egp(["PA", "PB"], {}, workers=2)
    assert set(bidders_by_jid) == {"PA", "PB"}, bidders_by_jid
    assert len(bidders_by_jid["PA"]) == 2 and len(bidders_by_jid["PB"]) == 1
    assert "PA" in results and "PB" not in results   # winner เฉพาะ PA
    print("✅ sweep_egp collects bidders (prelim + winner)")

test_sweep_egp_collects_bidders()
print("ALL PASS winner_sweep")
