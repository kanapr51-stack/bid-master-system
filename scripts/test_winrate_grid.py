"""test_winrate_grid.py — งาน B: conditional win-rate (F_bid^k) + ตาราง 3 ระดับ."""
import os, sys, tempfile
os.environ.setdefault("BMS_DATA_DIR", tempfile.mkdtemp())   # กัน import แตะ prod DB
os.environ.setdefault("BMS_ENV", "dev")
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf

def auc(*discs):
    """auction จาก list ของ disc — รายแรกเป็น winner (grid ไม่สน winner flag)."""
    return [(f"b{i}", d, i == 0) for i, d in enumerate(discs)]

def test_grid_math():
    # 5 auctions × 4 bidders (n คงที่=4 → SD=0 → 1 คอลัมน์ k=4)
    # pooled disc: 10 ตัวที่ 10%, 10 ตัวที่ 30% → F_bid(30)=20/20=1.0 · F_bid(10)=10/20=0.5
    auctions = [auc(30, 30, 10, 10) for _ in range(5)]
    g = bf.winrate_grid(auctions, [700000, 900000, None], 1000000)
    assert g is not None, g
    assert g["ns"] == [4], g["ns"]
    assert g["n_auctions"] == 5 and g["n_bids"] == 20, g
    rows = dict((p, w) for p, w in g["rows"])
    assert rows[700000] == [100], rows          # disc 30 → 1.0^4=100%
    assert rows[900000] == [6], rows            # disc 10 → 0.5^4=6.25%→6%
    print("✅ grid math (F_bid^k) ถูกต้อง")

def test_grid_columns_and_monotonic():
    # ขนาดสนาม [2,4,4,4,6] → mean=4, sample-SD=√2≈1.41 → คอลัมน์ [3,4,5]
    sizes = [2, 4, 4, 4, 6]
    auctions = []
    for s in sizes:
        auctions.append(auc(*[5 + 2 * j for j in range(s)]))   # disc 5,7,9,...
    # price 900000 → disc 10% → F_bid(10)=14/20=0.7 (อยู่ใน (0,1) → k มีผลจริง)
    g = bf.winrate_grid(auctions, [900000, None, None], 1000000)
    assert g["ns"] == [3, 4, 5], g["ns"]
    assert g["rows"][0][0] == 900000, g["rows"]      # row label ตรง price ที่ส่ง
    ws = g["rows"][0][1]
    assert len(ws) == 3, ws
    assert ws[0] > ws[1] > ws[2], ("คู่แข่งเยอะ → win% ลด (strict)", ws)   # 34>24>17
    print("✅ คอลัมน์ mean±SD + monotonic (k↑→%↓)")

def test_grid_rows_monotonic():
    auctions = [auc(30, 20, 10, 25) for _ in range(5)]    # n=4 คงที่
    g = bf.winrate_grid(auctions, [700000, 800000, 900000], 1000000)  # disc 30/20/10
    w_lo = g["rows"][0][1][0]   # 700000 (disc 30)
    w_hi = g["rows"][2][1][0]   # 900000 (disc 10)
    assert w_lo > w_hi, ("ราคาต่ำต้องชนะมากกว่า", w_lo, w_hi)
    print("✅ ราคาต่ำ → win% สูงกว่า (rows monotonic)")

def test_grid_gate():
    auctions = [auc(20, 10) for _ in range(4)]            # n_auctions=4 < MIN_AUCTIONS(5)
    assert bf.winrate_grid(auctions, [800000], 1000000) is None, "gate <5 → None"
    assert bf.winrate_grid([], [800000], 1000000) is None, "ว่าง → None"
    assert bf.winrate_grid([auc(20, 10) for _ in range(5)], [], 1000000) is None, "ไม่มี price → None"
    assert bf.winrate_grid([auc(20, 10) for _ in range(5)], [800000], 0) is None, "ไม่มี budget → None"
    print("✅ gating (น้อย/ว่าง/ไม่มี budget → None)")

def test_winrate_lines_render():
    grid = {"ns": [4, 6, 8],
            "rows": [(1400000, [78, 68, 59]), (1600000, [55, 42, 32]), (1800000, [28, 18, 11])],
            "n_mean": 6.0, "n_sd": 2.0, "n_auctions": 18, "n_bids": 107, "budget": 2000000}
    lines = bf.winrate_lines(grid, "อำเภอ")
    txt = "\n".join(lines)
    assert "โอกาสชนะตามจำนวนผู้ยื่น" in txt, txt
    assert "งบ 2,000,000" in txt, txt
    assert "4ราย" in txt and "6ราย" in txt and "8ราย" in txt, txt
    assert "1,400,000" in txt and "78%" in txt, txt
    assert "เฉลี่ย 6 ผู้ยื่น" in txt and "(±2)" in txt and "อิงอำเภอ" in txt, txt
    assert "📈 สถิติจาก 18 งาน · 107 ผู้ยื่น" in txt, txt
    assert bf.winrate_lines(None, "อำเภอ") == [], "None → []"
    print("✅ winrate_lines render + sample size")

def test_field_and_winrate_endtoend():
    import tempfile, importlib
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
    for i in range(6):
        s.record_bid_results(f"W{i}", [
            {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "850000"},
            {"receiveNameTh": "หจก.ค", "receiveTin": "3", "priceProposal": "900000"}])
    with db.get_connection() as conn:
        wl, fl = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                      [700000, 850000, 900000], district="เมือง",
                                      scope_label=" (อ.เมือง)", basis="อำเภอ")
    wtxt = "\n".join(wl)
    assert "โอกาสชนะตามจำนวนผู้ยื่น" in wtxt, wtxt           # B table โผล่
    assert "📈 สถิติจาก 6 งาน · 18 ผู้ยื่น" in wtxt, wtxt     # 6 งาน × 3 ผู้ยื่น = 18
    assert isinstance(fl, list), fl                          # 2B block (อาจ [] ถ้าไม่มี leader) — ไม่ error
    print("✅ field_and_winrate end-to-end (อ่านรอบเดียว → 2 บล็อก)")


def test_gate_fallback_to_old_card():
    """scope ที่ bid_results ว่าง → ([],[]) → predict() จะ fallback การ์ดเดิม (graceful)."""
    import tempfile, importlib
    os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
    import Sebastian_Customer_DB as db
    importlib.reload(db); db.init_schema()
    with db.get_connection() as conn:
        wl, fl = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000,
                                      [700000, 800000, 900000], district="ไม่มี", basis="อำเภอ")
    assert wl == [] and fl == [], (wl, fl)                    # ว่าง → predict() ใช้ predict_lines เดิม
    print("✅ gate: scope บาง → ([],[]) → การ์ดเดิม")


test_grid_math()
test_grid_columns_and_monotonic()
test_grid_rows_monotonic()
test_grid_gate()
test_winrate_lines_render()
test_field_and_winrate_endtoend()
test_gate_fallback_to_old_card()
print("ALL PASS winrate_grid")
