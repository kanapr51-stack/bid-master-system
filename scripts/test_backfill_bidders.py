"""test_backfill_bidders.py — backfill engine: select / fetch-store / run loop."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import backfill_bidders as bb

def _seed_cgd():
    """cgd_winners: 2 งานเป้าหมาย (P1,P2) + นอกเกณฑ์ (จังหวัดผิด/proc ผิด/win_price=0)."""
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, win_price, budget, announce_date) "
            "VALUES (?,?,?,?,?,?,?)",
            [("P1", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2568", 100, 200, "2568-01-01"),
             ("P2", "บึงกาฬ", "สอบราคา", "2567", 100, 200, "2567-05-05"),
             ("PX", "ขอนแก่น", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2568", 100, 200, "2568-01-01"),  # จังหวัดผิด
             ("PY", "นครพนม", "เฉพาะเจาะจง", "2568", 100, 200, "2568-01-01"),                          # proc ผิด
             ("PZ", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2568", 0, 200, "2568-01-01")])    # win_price=0

def test_select_filters_and_dedup():
    _seed_cgd()
    prov = ["นครพนม", "บึงกาฬ"]; fy = ["2567", "2568", "2569"]
    with db.get_connection() as conn:
        got = bb.select_candidates(conn, prov, fy, seen=set())
    ids = {pid for pid, _date in got}
    assert ids == {"P1", "P2"}, ids                          # นอกเกณฑ์ถูกตัด
    assert dict(got)["P1"] == "2568-01-01"                   # คืน announce_date ด้วย
    # dedup: P1 มีใน bid_results แล้ว → ไม่คืน
    db.SubscriptionStore().record_bid_results("P1", [{"receiveNameTh": "ก", "receiveTin": "1"}])
    with db.get_connection() as conn:
        ids2 = {pid for pid, _ in bb.select_candidates(conn, prov, fy, seen=set())}
    assert ids2 == {"P2"}, ids2
    print("✅ select_candidates filter + dedup")

test_select_filters_and_dedup()

def test_backfill_one_status():
    store = db.SubscriptionStore()
    # stored: มี bidder → เขียน + fetched_at = announce_date ที่ส่งเข้า
    bb.get_procure_result = lambda pid: {"winner": "ก", "bidders": [
        {"receiveNameTh": "ก", "receiveTin": "1", "priceAgree": "90", "priceProposal": "90"},
        {"receiveNameTh": "ข", "receiveTin": "2", "priceProposal": "110"}]}
    assert bb.backfill_one(store, "Q1", "2568-03-03") == "stored"
    rows = store.get_bid_results("Q1")
    assert len(rows) == 2 and all(r["fetched_at"] == "2568-03-03" for r in rows), rows
    # empty: bidders ว่าง → ไม่เขียน
    bb.get_procure_result = lambda pid: {"bidders": []}
    assert bb.backfill_one(store, "Q2", "2568-01-01") == "empty"
    assert store.get_bid_results("Q2") == []
    # error: ไม่มี key bidders ({}) → error
    bb.get_procure_result = lambda pid: {}
    assert bb.backfill_one(store, "Q3", "2568-01-01") == "error"
    # error: exception → error (fail-open, ไม่โยนต่อ)
    def _boom(pid): raise RuntimeError("net")
    bb.get_procure_result = _boom
    assert bb.backfill_one(store, "Q4", "2568-01-01") == "error"
    print("✅ backfill_one stored/empty/error")

test_backfill_one_status()
print("ALL PASS backfill_bidders")
