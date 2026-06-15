"""test_winrate_grid.py — งาน B/B.1: conditional win-rate ตาราง 3 ระดับ (invert F_bid)."""
import os, sys, tempfile
os.environ.setdefault("BMS_DATA_DIR", tempfile.mkdtemp())   # กัน import แตะ prod DB
os.environ.setdefault("BMS_ENV", "dev")
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf

def auc(*discs):
    """auction จาก list ของ disc — รายแรกเป็น winner (grid ไม่สน winner flag)."""
    return [(f"b{i}", d, i == 0) for i, d in enumerate(discs)]

def test_grid_invert_targets():
    # n คงที่=4 → ns=[4], k_mid=4. bids กระจายละเอียด (distinct) → 3 quantile แยกราคาได้
    auctions = [[(f"b{j}", i * 2 + j * 0.5, j == 0) for j in range(4)] for i in range(5)]  # disc 0..9.5
    g = bf.winrate_grid(auctions, 1000000)             # targets default (75,50,25)
    assert g is not None, g
    assert g["ns"] == [4], g["ns"]
    assert g["n_auctions"] == 5 and g["n_bids"] == 20, g
    mids = [w[0] for _, w in g["rows"]]                # n const → 1 คอลัมน์ (=k_mid)
    assert mids == [75, 50, 25], mids                  # คอลัมน์กลาง = target เป๊ะ (by construction)
    prices = [p for p, _ in g["rows"]]
    assert prices[0] < prices[1] < prices[2], prices   # ราคาเรียงขึ้น (75%ดุสุด→25%กำไร) ไม่ยุบ
    print("✅ invert: คอลัมน์กลาง = 75/50/25 + ราคาไม่ยุบ")

def test_grid_invert_columns():
    # ขนาดสนาม [2,4,4,4,6] → mean=4 sd≈1.41 → ns=[3,4,5], k_mid=ns[1]=4
    sizes = [2, 4, 4, 4, 6]
    auctions = [[(f"b{j}", j * 1.7, j == 0) for j in range(s)] for s in sizes]
    g = bf.winrate_grid(auctions, 1000000)
    assert g["ns"] == [3, 4, 5], g["ns"]
    r0 = g["rows"][0][1]                               # row เป้า 75% (ราคาต่ำสุด)
    assert r0[1] == 75, r0                             # คอลัมน์กลาง (k=4) = target เป๊ะ
    assert r0[0] > r0[1] > r0[2], ("k น้อย→win สูง", r0)   # 81 > 75 > 70
    print("✅ invert columns: mid=target, monotonic by k")

def test_grid_gate():
    base = [[(f"b{j}", j * 2.0, j == 0) for j in range(4)] for _ in range(5)]
    assert bf.winrate_grid(base[:4], 1000000) is None, "gate <5 → None"
    assert bf.winrate_grid([], 1000000) is None, "ว่าง → None"
    assert bf.winrate_grid(base, 0) is None, "ไม่มี budget → None"
    narrow = [[(f"b{j}", 20.0, j == 0) for j in range(4)] for _ in range(5)]  # disc เท่ากันหมด
    assert bf.winrate_grid(narrow, 1000000) is None, "ราคายุบ <2 แถว → None"
    print("✅ gating (<5 / ว่าง / ไม่มี budget / ราคายุบ → None)")

def test_winrate_lines_render():
    grid = {"ns": [4, 6, 8],
            "rows": [(1400000, [78, 68, 59]), (1600000, [55, 42, 32]), (1800000, [28, 18, 11])],
            "n_mean": 6.0, "n_sd": 2.0, "n_auctions": 18, "n_bids": 107,
            "ess": 40.0, "k_mid": 6, "budget": 2000000}
    lines = bf.winrate_lines(grid)                       # 🟢 local (conf=None)
    txt = "\n".join(lines)
    assert "โอกาสชนะตามจำนวนผู้ยื่น" in txt and "งบ 2,000,000" in txt, txt
    assert "4ราย" in txt and "1,400,000" in txt and "78%" in txt, txt
    assert "เฉลี่ย 6 ผู้ยื่น" in txt and "(±2)" in txt, txt
    assert "📈 จาก 18 งานที่มีข้อมูลผู้ยื่นครบ · 107 ราย" in txt, txt
    assert "⚠️" not in txt, "🟢 local ไม่มี disclaimer"
    assert bf.winrate_lines(None) == [], "None → []"
    print("✅ winrate_lines render (🟢 local)")

def test_winrate_lines_assisted():
    grid = {"ns": [3, 5, 7], "rows": [(1100000, [85, 75, 66]), (1200000, [36, 25, 16])],
            "n_mean": 5.0, "n_sd": 2.0, "n_auctions": 9, "n_bids": 41,
            "ess": 12.0, "k_mid": 5, "budget": 2000000}
    lines = bf.winrate_lines(grid, conf=("🟡", "อำเภอ"), price_basis="ตำบล")
    txt = "\n".join(lines)
    assert "🟡 โอกาส% อิงอำเภอ" in txt, txt
    assert "⚠️ ราคาด้านบนยังอิงตำบล" in txt, txt          # disclaimer เน้น (review R2)
    assert 'โอกาสชนะ%' in txt, txt
    print("✅ winrate_lines assisted (🟡 + disclaimer ราคา local)")

def test_field_and_winrate_endtoend():
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db)
    db.init_schema()
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        for i in range(6):                                   # 6 auctions ≥ MIN_AUCTIONS
            conn.execute("INSERT OR REPLACE INTO cgd_winners "
                         "(project_id, province, proc_type, project_name, budget) VALUES (?,?,?,?,?)",
                         (f"W{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                          "ก่อสร้างถนน อ.เมือง", 1000000))
    for i in range(6):                                       # disc กระจาย (10/15/22/30) → ราคาไม่ยุบ
        s.record_bid_results(f"W{i}", [
            {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "780000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "850000"},
            {"receiveNameTh": "หจก.ง", "receiveTin": "4", "priceProposal": "900000"}])
    with db.get_connection() as conn:
        wl, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                            district="เมือง", scope_label=" (อ.เมือง)", basis="อำเภอ")
    assert conf is None, conf                                # ไม่ผ่อน scope → 🟢 local
    wtxt = "\n".join(wl)
    assert "โอกาสชนะตามจำนวนผู้ยื่น" in wtxt, wtxt           # B table โผล่
    assert "📈 จาก 6 งานที่มีข้อมูลผู้ยื่นครบ · 24 ราย" in wtxt, wtxt  # 6 งาน × 4 ผู้ยื่น = 24
    assert isinstance(fl, list), fl                          # 2B block (อาจ [] ถ้าไม่มี leader) — ไม่ error
    print("✅ field_and_winrate end-to-end (อ่านรอบเดียว → 2 บล็อก)")


def test_field_auctions_project_ids():
    """project_ids mode → ดึงเฉพาะ id ที่ส่ง (population เดียวกับราคา)."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        for pid in ("P1", "P2", "P3"):
            conn.execute("INSERT OR REPLACE INTO cgd_winners "
                         "(project_id, province, proc_type, project_name, budget) VALUES (?,?,?,?,?)",
                         (pid, "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน", 1000000))
    for pid in ("P1", "P2", "P3"):
        s.record_bid_results(pid, [
            {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "850000"}])
    with db.get_connection() as conn:
        au_all = bf._field_auctions(conn, "นครพนม", ["ถนน"])
        au_sel = bf._field_auctions(conn, "นครพนม", ["ถนน"], project_ids=["P1", "P2", "P1"])  # dup ตัด
        au_empty = bf._field_auctions(conn, "นครพนม", ["ถนน"], project_ids=[])
    assert len(au_all) == 3, au_all                          # scope mode = ทั้งหมด
    assert len(au_sel) == 2, au_sel                          # project_ids → เฉพาะ P1,P2
    assert au_empty == [], au_empty                          # ว่าง → []
    print("✅ _field_auctions project_ids mode (population เดียวกับราคา)")

def test_gate_fallback_to_old_card():
    """scope ที่ bid_results ว่าง → ([],[]) → predict() จะ fallback การ์ดเดิม (graceful)."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    with db.get_connection() as conn:
        wl, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                            district="ไม่มี", basis="อำเภอ")
    assert wl == [] and fl == [] and conf is None, (wl, fl, conf)
    print("✅ gate: scope บาง → ([],[]) → การ์ดเดิม")


def test_ladder_relax_to_amphoe():
    """local (ตำบล) full-field < MIN_AUCTIONS → ผ่อนไปอำเภอ → conf 🟡 + ตารางขึ้น."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    s = db.SubscriptionStore()
    bids = [{"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "780000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "860000"}]
    with db.get_connection() as conn:
        for i in range(6):                                   # 6 งานในอำเภอ (พอ), แต่ตำบลมีแค่ 2
            tb = "ตำบลโพธิ์" if i < 2 else f"ตำบลอื่น{i}"
            conn.execute("INSERT OR REPLACE INTO cgd_winners (project_id, province, proc_type, "
                         "project_name, budget, fiscal_year, win_price, winner) VALUES (?,?,?,?,?,?,?,?)",
                         (f"L{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                          f"ก่อสร้างถนน {tb} อำเภอนาทม", 1000000, "2568", 820000, f"หจก.ชนะ{i}"))
    for i in range(6):
        s.record_bid_results(f"L{i}", bids)
    tambon_ids = ["L0", "L1"]                                # ตำบล = 2 auctions (<5)
    with db.get_connection() as conn:
        wl, fl, conf = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                            basis="ตำบล", project_ids=tambon_ids,
                                            cf={}, amphoe="นาทม")
    assert conf is not None and conf[0] == "🟡", conf        # ผ่อนไปอำเภอ
    assert any("โอกาสชนะตามจำนวนผู้ยื่น" in x for x in wl), wl    # ตารางขึ้น (เดิมไม่ขึ้น)
    assert any("ราคาด้านบนยังอิงตำบล" in x for x in wl), wl       # disclaimer
    print("✅ ladder: ตำบลบาง → ผ่อนอำเภอ 🟡 + ตารางขึ้น")


def test_weighted_quantile():
    pairs = [(0.0, 1.0), (10.0, 1.0), (20.0, 1.0), (30.0, 1.0)]   # น้ำหนักเท่ากัน
    q50 = bf._weighted_quantile(pairs, 0.5)
    assert 10.0 <= q50 <= 20.0, q50                               # กลาง ๆ
    assert bf._weighted_quantile(pairs, 0.0) == 0.0               # ต่ำสุด
    assert bf._weighted_quantile(pairs, 1.0) == 30.0             # สูงสุด
    heavy_high = [(0.0, 0.1), (30.0, 10.0)]                       # ถ่วงค่าสูง
    assert bf._weighted_quantile(heavy_high, 0.5) > 25.0, "น้ำหนักเอียงสูง → median สูง"
    print("✅ _weighted_quantile (Hazen weighted)")

def test_field_auctions_fiscal_year():
    """_field_auctions คืน 4-tuple (name, disc, is_winner, fiscal_year)."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO cgd_winners "
                     "(project_id, province, proc_type, project_name, budget, fiscal_year) "
                     "VALUES (?,?,?,?,?,?)",
                     ("F1", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน", 1000000, 2568))
    s.record_bid_results("F1", [
        {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
        {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "850000"}])
    with db.get_connection() as conn:
        au = bf._field_auctions(conn, "นครพนม", ["ถนน"])
    assert au and len(au[0][0]) == 4, au                          # 4-tuple
    assert au[0][0][3] == 2568, au[0][0]                          # fiscal_year ตัวที่ 4
    # 2B ยังทำงาน (รับ 4-tuple ไม่พัง)
    fr = bf.analyze_field(au)
    assert isinstance(fr, dict) and "tier" in fr, fr
    print("✅ _field_auctions 4-tuple + analyze_field รับได้")


def test_eval_fail_reasons():
    base = [[(f"b{j}", j * 2.0, j == 0, 2569) for j in range(4)] for _ in range(5)]   # 5×4, disc 0/2/4/6
    assert bf._evaluate_winrate(base[:4], 1000000)["fail_reason"] == "AUCTIONS"        # <5 auctions
    assert bf._evaluate_winrate(base, 0)["fail_reason"] == "BUDGET"
    narrow = [[(f"b{j}", 20.0, j == 0, 2569) for j in range(4)] for _ in range(5)]     # disc เท่ากัน
    nr = bf._evaluate_winrate(narrow, 1000000)
    assert nr["ess"] >= bf.ESS_FLOOR, nr          # anchor: ผ่าน gate ก่อน (กัน ESS_FLOOR ขยับแล้ว test เพี้ยน)
    assert nr["fail_reason"] == "PRICE_COLLAPSE"
    ok = bf._evaluate_winrate(base, 1000000)
    assert ok["ok"] and ok["fail_reason"] == "OK" and ok["ess"] >= 6, ok
    print("✅ _evaluate_winrate fail_reason (AUCTIONS/BUDGET/PRICE_COLLAPSE/OK)")

def test_eval_ess_gate_recency():
    # 5 auctions แต่ส่วนใหญ่เก่ามาก (2562) → ESS ต่ำ → gate ESS fail
    old = [[(f"b{j}", j * 3.0, j == 0, 2562) for j in range(2)] for _ in range(5)]     # 10 bids เก่า → w≈0.008
    r = bf._evaluate_winrate(old, 1000000)
    assert r["fail_reason"] == "ESS", r                      # ESS < 6 (เก่าจาง)
    print("✅ ESS gate (งานเก่าจาง → ESS fail)")

def test_eval_local_n_centering():
    # F-scope กว้าง n~8 (สนามใหญ่), local_auctions แคบ n~4 → center ตาม local
    big = [[(f"b{j}", j * 1.3, j == 0, 2569) for j in range(8)] for _ in range(5)]     # n=8
    local = [[(f"b{j}", j * 1.3, j == 0, 2569) for j in range(4)] for _ in range(4)]   # n=4, 4 auctions ≥3
    g = bf._evaluate_winrate(big, 1000000, local_auctions=local)
    assert g["ok"] and g["ns"][len(g["ns"]) // 2] == 4, g["ns"]    # center=4 (local) ไม่ใช่ 8
    # local น้อยกว่า MIN_N_AUCTIONS(3) → fallback ใช้ F-scope n
    g2 = bf._evaluate_winrate(big, 1000000, local_auctions=local[:2])
    assert g2["ns"][len(g2["ns"]) // 2] == 8, g2["ns"]            # center=8 (F-scope) เพราะ local<3
    print("✅ local-n centering + fallback เมื่อ local<MIN_N_AUCTIONS")


def test_predict_assisted_keeps_local_price():
    """🟡 assisted: ตาราง win% ต่อท้าย + บล็อกราคา a/b/c local ยังอยู่ (ไม่ถูกแทน)."""
    import importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    import cgd_intel as ci
    importlib.reload(ci)
    import bid_field as bf2
    importlib.reload(bf2)
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        for i in range(8):                                   # อำเภอหนา, ตำบลบาง
            tb = "โพธิ์หมากแข้ง" if i < 2 else f"อื่น{i}"
            conn.execute("INSERT OR REPLACE INTO cgd_winners (project_id, province, dept, proc_type, "
                         "project_name, winner, budget, win_price, discount_pct, fiscal_year) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (f"A{i}", "บึงกาฬ", "อบต.ทดสอบ", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                          f"ก่อสร้างถนน คสล. ตำบล{tb} อำเภอบึงโขงหลง", "หจก.ผู้ชนะ",
                          1000000, 820000, 18.0, "2568"))
        s2 = db.SubscriptionStore()
    for i in range(8):
        s.record_bid_results(f"A{i}", [
            {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "780000", "priceAgree": "780000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "840000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "900000"}])
    with db.get_connection() as conn:
        ctx = ci.intel_context("บึงกาฬ", "ก่อสร้างถนน คสล. ตำบลโพธิ์หมากแข้ง อำเภอบึงโขงหลง",
                               dept_name="อบต.ทดสอบ", project_id="X1", budget=1000000, conn=conn)
    assert ctx and ctx.get("lines"), ctx
    txt = "\n".join(ctx["lines"])
    # ถ้าโผล่ตาราง assisted → ต้องคงบล็อกราคา local (predict_lines = "แนะนำราคายื่น") + disclaimer
    if "🟡" in txt or "🟠" in txt:
        assert "แนะนำราคายื่น" in txt, "assisted: ต้องคงบล็อกราคา local (ไม่ถูกตารางแทน)"
        assert "ราคาด้านบนยังอิง" in txt, txt
    print("✅ predict assisted คงราคา local (หรือ 🟢/no-table graceful)")


test_grid_invert_targets()
test_grid_invert_columns()
test_grid_gate()
test_winrate_lines_render()
test_winrate_lines_assisted()
test_field_and_winrate_endtoend()
test_field_auctions_project_ids()
test_gate_fallback_to_old_card()
test_ladder_relax_to_amphoe()
test_weighted_quantile()
test_field_auctions_fiscal_year()
test_eval_fail_reasons()
test_eval_ess_gate_recency()
test_eval_local_n_centering()
test_predict_assisted_keeps_local_price()
print("ALL PASS winrate_grid")
