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
print("ALL PASS winner_sweep")
