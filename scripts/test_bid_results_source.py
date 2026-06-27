"""bid_results.source column + record_bid_results source param (v136)."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()

def test_source_column_exists():
    with db.get_connection() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(bid_results)")]
    assert "source" in cols, cols
    print("✅ bid_results.source column exists")

def test_default_and_explicit_source():
    store = db.SubscriptionStore()
    store.record_bid_results("A1", [{"receiveNameTh": "ก", "receiveTin": "1", "priceProposal": "90"}])
    store.record_bid_results("A2", [{"receiveNameTh": "ข", "receiveTin": "2", "priceProposal": "80"}],
                             source="cgd_copy")
    rows = {r["project_id"]: r for r in db.SubscriptionStore().get_bid_results("A1")
            + db.SubscriptionStore().get_bid_results("A2")}
    assert rows["A1"]["source"] == "procure_api", rows["A1"]
    assert rows["A2"]["source"] == "cgd_copy", rows["A2"]
    print("✅ default=procure_api, explicit=cgd_copy")

def test_rewrite_keeps_source():
    """INSERT OR REPLACE เขียนทั้งแถว — รันซ้ำด้วย source ใหม่ ต้องอัปเดต ไม่ใช่หาย."""
    store = db.SubscriptionStore()
    store.record_bid_results("A3", [{"receiveNameTh": "ค", "receiveTin": "3", "priceProposal": "70"}],
                             source="cgd_copy")
    store.record_bid_results("A3", [{"receiveNameTh": "ค", "receiveTin": "3", "priceAgree": "70",
                                     "priceProposal": "70"}], source="procure_api")
    rows = db.SubscriptionStore().get_bid_results("A3")
    assert len(rows) == 1 and rows[0]["source"] == "procure_api", rows
    print("✅ rewrite updates source (no loss)")

test_source_column_exists()
test_default_and_explicit_source()
test_rewrite_keeps_source()
print("ALL PASS bid_results source")
