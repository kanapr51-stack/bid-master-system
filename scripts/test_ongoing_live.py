"""ongoing_bidder_capture Pass 1: LIVE select(age window/epoch/province) + capture."""
import os, tempfile, sys, datetime
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def _seed():
    """projects_seen: first_seen_at ต่างวันเพื่อทดสอบ window/epoch/province."""
    def ins(pid, prov, fs):
        with db.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO projects_seen "
                         "(project_id, province, first_seen_at) VALUES (?,?,?)", (pid, prov, fs))
    ins("L_ok",      "นครพนม", "2026-06-15T00:00:00")   # อายุ 12 วัน (today 6-27) → ในช่วง [7,90]
    ins("L_new",     "นครพนม", "2026-06-25T00:00:00")   # อายุ 2 วัน → ใหม่เกิน (ตัด)
    ins("L_old",     "บึงกาฬ", "2026-02-01T00:00:00")   # อายุ >90 วัน → เก่าเกิน (ตัด)
    ins("L_preepoch","นครพนม", "2026-06-10T00:00:00")   # ก่อน epoch_date 6-12 (ตัด แม้ window ผ่าน)
    ins("L_other",   "ขอนแก่น", "2026-06-15T00:00:00")  # จังหวัดผิด (ตัด)

def test_select_window_epoch_province():
    _seed()
    today = datetime.date(2026, 6, 27)
    with db.get_connection() as conn:
        got = set(oc.select_live_candidates(conn, oc.PROVINCES, "2026-06-12", today=today))
    assert got == {"L_ok"}, got     # เหลือแค่ตัวที่ผ่านทั้ง window+epoch+province
    print("✅ select_live window + epoch + province")

def test_select_skips_captured():
    """งานที่มีใน bid_results แล้ว → ไม่คืน (idempotent)."""
    db.SubscriptionStore().record_bid_results("L_ok", [{"receiveNameTh": "ก", "receiveTin": "1"}])
    today = datetime.date(2026, 6, 27)
    with db.get_connection() as conn:
        got = set(oc.select_live_candidates(conn, oc.PROVINCES, "2026-06-12", today=today))
    assert "L_ok" not in got, got
    print("✅ select_live skips captured")

def test_capture_live_status():
    store = db.SubscriptionStore()
    oc_api = lambda pid: {"winner": "ก", "bidders": [
        {"receiveNameTh": "ก", "receiveTin": "1", "priceAgree": "90", "priceProposal": "90"}]}
    assert oc.capture_live_one(store, "M1", oc_api) == "stored"
    assert store.get_bid_results("M1")[0]["source"] == "procure_api"
    assert oc.capture_live_one(store, "M2", lambda pid: {"bidders": []}) == "empty"   # ยังไม่ award
    assert oc.capture_live_one(store, "M3", lambda pid: {}) == "error"                # ไม่มี key
    def boom(pid): raise RuntimeError("net")
    assert oc.capture_live_one(store, "M4", boom) == "error"
    print("✅ capture_live stored/empty/error (source=procure_api)")

test_select_window_epoch_province()
test_select_skips_captured()
test_capture_live_status()
print("ALL PASS ongoing_live")
