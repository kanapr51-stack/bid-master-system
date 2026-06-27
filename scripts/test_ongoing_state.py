"""ongoing_bidder_capture: state (epoch) + seen helpers."""
import os, tempfile, sys, json, datetime
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def test_ensure_state_creates_then_persists():
    d = datetime.date(2026, 6, 27)
    st = oc.ensure_state(today=d)
    assert st["epoch_date"] == "2026-06-27", st
    assert st["epoch_fy"] == 2569, st            # ปีงบไทย ก่อน ต.ค. → 2569
    # ครั้งที่ 2 (วันอื่น) ต้องอ่านของเดิม ไม่ overwrite
    st2 = oc.ensure_state(today=datetime.date(2027, 1, 1))
    assert st2 == st, st2
    print("✅ ensure_state create + persist (no overwrite)")

def test_seen_roundtrip():
    p = oc.SEEN_CGD_PATH
    oc.save_seen(p, {"X1", "X2"})
    assert oc.load_seen(p) == {"X1", "X2"}
    # ไฟล์ไม่มี → set ว่าง
    missing = oc.DATA_DIR / "nope.json"
    assert oc.load_seen(missing) == set()
    print("✅ seen save/load roundtrip")

test_ensure_state_creates_then_persists()
test_seen_roundtrip()
print("ALL PASS ongoing_state")
