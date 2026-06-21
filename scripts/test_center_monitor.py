"""test_center_monitor.py — B″ offline center-error monitor (observe-only).
ตรวจ _center_stats (centering math) + _log_center_breadcrumb (เขียนเฉพาะตอนผ่อน, exception-safe)."""
import os, tempfile, sys, json
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf


def auc(size, disc=30.0):
    """auction ที่มี `size` ผู้ยื่น (len>=2 ถึงนับ)."""
    return [(f"co{i}", disc, i == 0) for i in range(size)]


def test_center_stats_uniform():
    # 4 งาน ผู้ยื่น 4 เท่ากันหมด → mean=4 sd=0 ns=[1,2,3,4] k_mid=4
    st = bf._center_stats([auc(4) for _ in range(4)])
    assert st["n"] == 4, st
    assert abs(st["n_mean"] - 4.0) < 1e-9, st
    assert st["ns"] == [1, 2, 3, 4], st
    assert st["k_mid"] == 4, st
    print("✅ _center_stats uniform")


def test_center_stats_spread():
    # ผู้ยื่น [3,4,5] → mean=4 var=1 sd=1 ns=[1,2,3,4,5] k_mid=4
    st = bf._center_stats([auc(3), auc(4), auc(5)])
    assert abs(st["n_mean"] - 4.0) < 1e-9, st
    assert st["ns"] == [1, 2, 3, 4, 5], st
    assert st["k_mid"] == 4, st
    print("✅ _center_stats spread")


def test_center_stats_empty():
    st = bf._center_stats([])
    assert st["n"] == 0 and st["k_mid"] is None, st
    # auction ที่ผู้ยื่น <2 ถูกตัด → ว่างเหมือนกัน
    assert bf._center_stats([[("x", 10, True)]])["n"] == 0
    print("✅ _center_stats empty graceful")


def test_breadcrumb_written_when_relaxed():
    path = os.path.join(os.environ["BMS_DATA_DIR"], "winrate_center_monitor.ndjson")
    if os.path.exists(path):
        os.remove(path)
    local = [auc(2), auc(2)]                 # n_local=2 (<3 → fallback ทำงาน)
    amphoe = [auc(3) for _ in range(4)]      # n_amphoe=4 (>=3 → eligible) mean=3
    province = [auc(9) for _ in range(10)]   # n_province=10 mean=9
    grid = {"k_mid": 9, "ok": True}
    bf._log_center_breadcrumb(local, amphoe, province, grid, ("🟠", "จังหวัด"), basis="ตำบล")
    assert os.path.exists(path), "ผ่อน (conf!=None) → ต้องเขียน breadcrumb"
    rec = json.loads(open(path, encoding="utf-8").read().strip().splitlines()[-1])
    assert rec["n_local"] == 2 and rec["n_amphoe"] == 4 and rec["n_province"] == 10, rec
    assert abs(rec["mean_amphoe"] - 3.0) < 1e-9 and abs(rec["mean_province"] - 9.0) < 1e-9, rec
    assert abs(rec["delta_mean"] - 6.0) < 1e-9, rec      # |9-3|
    assert rec["amphoe_eligible"] is True, rec
    assert rec["kmid_chosen"] == 9, rec
    assert rec["conf"] == "จังหวัด" and rec["basis"] == "ตำบล", rec
    print("✅ breadcrumb เขียนตอนผ่อน + field ครบ")


def test_breadcrumb_skip_when_local():
    path = os.path.join(os.environ["BMS_DATA_DIR"], "winrate_center_monitor.ndjson")
    if os.path.exists(path):
        os.remove(path)
    # conf=None (🟢 local) → ไม่เขียน
    bf._log_center_breadcrumb([auc(5)], [], [], {"k_mid": 5, "ok": True}, None, basis="ตำบล")
    assert not os.path.exists(path), "conf=None → ห้ามเขียน (monitor เฉพาะตอนผ่อน)"
    # grid ว่าง → ไม่เขียน
    bf._log_center_breadcrumb([auc(5)], [], [], None, ("🟠", "จังหวัด"))
    assert not os.path.exists(path), "ไม่มี grid → ไม่เขียน"
    print("✅ ไม่เขียนตอน local / no-grid")


def test_breadcrumb_exception_safe():
    # grid พังรูปแบบ (k_mid หาย) ก็ต้องไม่ raise — observe-only
    try:
        bf._log_center_breadcrumb([auc(2)], [auc(3)], [auc(9)], {"ok": True}, ("🟠", "จังหวัด"))
    except Exception as e:
        assert False, f"monitor ต้องกลืน error ไม่ raise: {e}"
    print("✅ exception-safe (ไม่ทำการ์ดพัง)")


def test_field_and_winrate_writes_breadcrumb_on_relax():
    """integration: ตำบลบาง → ผ่อนอำเภอ 🟡 → field_and_winrate ต้องเขียน breadcrumb (observe-only)."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    import bid_field as bf2
    importlib.reload(bf2)
    s = db.SubscriptionStore()
    bids = [{"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "780000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "860000"}]
    with db.get_connection() as conn:
        for i in range(6):                                   # อำเภอ 6 งาน (พอ), ตำบล 2 (<5 → ผ่อน)
            tb = "ตำบลโพธิ์" if i < 2 else f"ตำบลอื่น{i}"
            conn.execute("INSERT OR REPLACE INTO cgd_winners (project_id, province, proc_type, "
                         "project_name, budget, fiscal_year, win_price, winner) VALUES (?,?,?,?,?,?,?,?)",
                         (f"L{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                          f"ก่อสร้างถนน {tb} อำเภอนาทม", 1000000, "2568", 820000, f"หจก.ชนะ{i}"))
    for i in range(6):
        s.record_bid_results(f"L{i}", bids)
    path = os.path.join(os.environ["BMS_DATA_DIR"], "winrate_center_monitor.ndjson")
    with db.get_connection() as conn:
        grid, fl, conf = bf2.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                               basis="ตำบล", project_ids=["L0", "L1"],
                                               cf={}, amphoe="นาทม")
    assert conf is not None and conf[0] == "🟡", conf        # ยืนยันว่าผ่อนจริง
    assert os.path.exists(path), "ผ่อน → field_and_winrate ต้องเขียน breadcrumb"
    rec = json.loads(open(path, encoding="utf-8").read().strip().splitlines()[-1])
    assert rec["conf"] == "อำเภอ" and rec["basis"] == "ตำบล", rec
    assert rec["n_local"] == 2 and rec["n_amphoe"] == 6, rec  # wiring ถูก: attempts[1]=อำเภอ
    print("✅ integration: field_and_winrate เขียน breadcrumb ตอนผ่อน (wiring ถูก)")


def test_analyze_summarize():
    import analyze_center_monitor as acm
    recs = [
        {"conf": "จังหวัด", "amphoe_eligible": True, "delta_mean": 6.0},
        {"conf": "จังหวัด", "amphoe_eligible": True, "delta_mean": 1.0},
        {"conf": "อำเภอ", "amphoe_eligible": True, "delta_mean": 0.0},
        {"conf": "จังหวัด", "amphoe_eligible": False, "delta_mean": 3.0},
    ]
    sm = acm.summarize(recs)
    assert sm["total"] == 4, sm
    assert sm["by_conf"]["จังหวัด"] == 3 and sm["by_conf"]["อำเภอ"] == 1, sm
    assert sm["amphoe_eligible"] == 3, sm
    # over eligible (delta [6,1,0]): median=1.0, %≥2 = 1/3
    assert abs(sm["delta_median"] - 1.0) < 1e-9, sm
    assert abs(sm["pct_delta_ge2"] - 100.0 / 3) < 1e-6, sm
    assert acm.summarize([])["total"] == 0          # ว่าง graceful
    print("✅ analyze summarize (distribution ถูก)")


test_center_stats_uniform()
test_center_stats_spread()
test_center_stats_empty()
test_breadcrumb_written_when_relaxed()
test_breadcrumb_skip_when_local()
test_breadcrumb_exception_safe()
test_field_and_winrate_writes_breadcrumb_on_relax()
test_analyze_summarize()
print("ALL PASS center_monitor")
