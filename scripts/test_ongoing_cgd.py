"""ongoing_bidder_capture Pass 2: CGD-FILL select + copy/API capture."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def _seed():
    """cgd_winners: เจาะจง(C1) + แข่ง(C2) ปีงบ>=2569; นอกเกณฑ์ ปีเก่า(C3)/จังหวัดผิด(C4)."""
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, winner, win_price, budget) "
            "VALUES (?,?,?,?,?,?,?)",
            [("C1", "นครพนม", "เฉพาะเจาะจง", "2569", "หจก. เอ", 100, 100),
             ("C2", "บึงกาฬ", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "2569", "หจก. บี", 90, 100),
             ("C3", "นครพนม", "เฉพาะเจาะจง", "2568", "หจก. ซี", 100, 100),     # ปีเก่า < epoch_fy
             ("C4", "ขอนแก่น", "เฉพาะเจาะจง", "2569", "หจก. ดี", 100, 100)])   # จังหวัดผิด

def test_select_floor_and_province():
    _seed()
    with db.get_connection() as conn:
        got = {r[0] for r in oc.select_cgd_candidates(conn, oc.PROVINCES, 2569, seen=set())}
    assert got == {"C1", "C2"}, got                  # ตัดปีเก่า + จังหวัดผิด
    print("✅ select_cgd floor(fy>=epoch) + province")

def test_capture_copy_no_api():
    _seed()
    store = db.SubscriptionStore()
    called = []
    api = lambda pid: called.append(pid) or {"bidders": []}
    # เฉพาะเจาะจง → copy ไม่เรียก API, source=cgd_copy, is_winner=1
    assert oc.capture_cgd_one(store, ("C1", "เฉพาะเจาะจง", "หจก. เอ", 100), api) == "copied"
    assert called == [], "copy ต้องไม่เรียก API"
    rows = store.get_bid_results("C1")
    assert len(rows) == 1 and rows[0]["source"] == "cgd_copy" and rows[0]["is_winner"] == 1, rows
    assert rows[0]["bidder_name"] == "หจก. เอ", rows
    print("✅ เฉพาะเจาะจง copy (no API, source=cgd_copy)")

def test_capture_competitive_api_then_fallback():
    store = db.SubscriptionStore()
    # แข่ง + API มีผล → stored, source=procure_api
    api_ok = lambda pid: {"bidders": [
        {"receiveNameTh": "บี", "receiveTin": "9", "priceAgree": "90", "priceProposal": "90"},
        {"receiveNameTh": "อี", "receiveTin": "8", "priceProposal": "95"}]}
    assert oc.capture_cgd_one(store, ("K1", "สอบราคา", "บี", 90), api_ok) == "stored"
    r1 = store.get_bid_results("K1")
    assert len(r1) == 2 and all(r["source"] == "procure_api" for r in r1), r1
    # แข่ง + API ล้ม → fallback copy winner, source=cgd_copy
    def boom(pid): raise RuntimeError("net")
    assert oc.capture_cgd_one(store, ("K2", "สอบราคา", "เอฟ", 80), boom) == "copied"
    r2 = store.get_bid_results("K2")
    assert len(r2) == 1 and r2[0]["source"] == "cgd_copy", r2
    print("✅ แข่ง API stored / API ล้ม fallback copy")

test_select_floor_and_province()
test_capture_copy_no_api()
test_capture_competitive_api_then_fallback()
print("ALL PASS ongoing_cgd")
