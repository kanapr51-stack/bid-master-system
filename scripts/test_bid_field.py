"""test_bid_field.py — market-leader intel: analyze_field / field_lines / _field_auctions."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf

def mk(winner, wdisc, others):
    """auction: ผู้ชนะ + others=[(name,disc)]."""
    return [(winner, wdisc, True)] + [(n, d, False) for n, d in others]

def test_leader_detected():
    # X ลง 6/6 ชนะ 4 (67%) → เจ้าตลาด · Y ลง6 ชนะ2 (33%) ไม่ผ่านเกณฑ์
    auctions = [mk("X", 30, [("Y", 20), ("Z", 22)]) for _ in range(4)]
    auctions += [mk("Y", 25, [("X", 20), ("Z", 22)]) for _ in range(2)]
    fr = bf.analyze_field(auctions)
    assert fr["tier"] == 1, fr
    assert fr["leaders"][0]["name"] == "X", fr
    assert fr["leaders"][0]["wins"] == 4 and fr["leaders"][0]["appears"] == 6, fr
    assert abs(fr["leaders"][0]["win_rate"] - 4 / 6) < 1e-9, fr
    assert fr["leaders"][0]["win_disc_med"] == 30, fr
    assert all(L["name"] != "Y" for L in fr["leaders"]), "Y win-rate 33% ไม่ใช่เจ้าตลาด"
    print("✅ market leader detected (win-frequency)")

def test_no_leader_and_gate():
    names = ["A", "B", "C", "D", "E", "F"]                     # ผู้ชนะกระจาย ไม่มีใครเด่น
    auctions = [mk(names[i], 25, [(names[(i + 1) % 6], 20), (names[(i + 2) % 6], 22)]) for i in range(6)]
    assert bf.analyze_field(auctions)["tier"] == 0, "ไม่มีเจ้าตลาด → tier0"
    assert bf.analyze_field(auctions[:4])["tier"] == 0, "n<MIN_AUCTIONS → gate"
    print("✅ no leader + gate น้อย")

test_leader_detected()
test_no_leader_and_gate()

def test_field_lines():
    # leader[0]=บัญชาศรี (ชนะเยอะสุด ลด 21%) · leader[1]=เมืองทอง (ลดลึกกว่า 29%)
    fr = {"tier": 1, "leaders": [
        {"name": "ห้างหุ้นส่วนจำกัด บัญชาศรี", "win_rate": 0.48, "wins": 10, "appears": 21, "win_disc_med": 21.0},
        {"name": "ห้างหุ้นส่วนจำกัด เมืองทอง", "win_rate": 0.69, "wins": 9, "appears": 13, "win_disc_med": 29.0}]}
    txt = "\n".join(bf.field_lines(fr, 2_000_000, " (ต.นาทม)"))
    assert "เจ้าตลาด" in txt and "หจก. เมืองทอง" in txt, txt    # ย่อชื่อ
    assert "(ต.นาทม)" in txt, txt                               # scope label
    assert "69%" in txt and "9/13" in txt, txt                  # win-rate + count
    assert "1,420,000" in txt, txt                              # ใช้ลดลึกสุด 29% (เมืองทอง) 2M*(1-0.29) ไม่ใช่ 21%
    assert "หจก. บัญชาศรี" in txt, txt                          # leader #1
    # tier0 / ไม่มี leader / ไม่มี budget → []
    assert bf.field_lines({"tier": 0, "leaders": []}, 2_000_000) == []
    assert bf.field_lines(None, 2_000_000) == []
    assert bf.field_lines(fr, 0) == []
    print("✅ field_lines leader intel")

test_field_lines()

def test_field_auctions_read():
    import Sebastian_Customer_DB as db
    db.init_schema()
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners (project_id, province, proc_type, project_name, budget) "
            "VALUES (?,?,?,?,?)",
            [("J1", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน ต.นาทม", 1000000),
             ("J2", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน ต.นาทม", 2000000),
             ("JX", "ขอนแก่น", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน", 1000000)])  # นอก scope
    s = db.SubscriptionStore()
    # J1: winner ลด 30% (700k) + loser ลด 10% (900k) + outlier ลด 95% (50k → ตัด)
    s.record_bid_results("J1", [
        {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
        {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "900000"},
        {"receiveNameTh": "หจก.outlier", "receiveTin": "3", "priceProposal": "50000"}])
    s.record_bid_results("J2", [
        {"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "1600000", "priceAgree": "1600000"},
        {"receiveNameTh": "หจก.ค", "receiveTin": "4", "priceProposal": "1800000"}])
    s.record_bid_results("JX", [
        {"receiveNameTh": "หจก.z", "receiveTin": "9", "priceProposal": "500000", "priceAgree": "500000"}])
    with db.get_connection() as conn:
        auctions = bf._field_auctions(conn, "นครพนม", ["ถนน"], subdistrict="นาทม")
    assert len(auctions) == 2, auctions                  # J1,J2 (JX นอกจังหวัด ตัด)
    j1 = next(a for a in auctions if any(abs(t[1] - 30.0) < 1e-9 for t in a))  # J1 มี disc 30
    discs = sorted(t[1] for t in j1)
    assert discs == [10.0, 30.0], discs                  # (1-700k/1M)=30, (1-900k/1M)=10 · outlier 95% ตัด
    assert any(t[2] for t in j1), "มี winner flag"
    print("✅ _field_auctions read + disc + outlier filter")

test_field_auctions_read()

def test_field_block_endtoend_and_gate():
    import Sebastian_Customer_DB as db
    db.init_schema()
    s = db.SubscriptionStore()
    # gate: bid_results ว่าง → field_and_winrate fl=[] (ปลอดภัยกับ _build_intel)
    with db.get_connection() as conn:
        assert bf.field_and_winrate(conn, "สกลนคร", ["ถนน"], 1000000)[1] == [], "scope ว่าง → []"
        for i in range(6):
            conn.execute("INSERT OR REPLACE INTO cgd_winners (project_id, province, proc_type, project_name, budget) "
                         "VALUES (?,?,?,?,?)",
                         (f"F{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ก่อสร้างถนน", 1000000))
    for i in range(5):  # วาย ลง 6 ชนะ 5 (83%) → เจ้าตลาด
        s.record_bid_results(f"F{i}", [
            {"receiveNameTh": "หจก.วาย", "receiveTin": "1", "priceProposal": "700000", "priceAgree": "700000"},
            {"receiveNameTh": "หจก.พ", "receiveTin": "2", "priceProposal": "800000"},
            {"receiveNameTh": "หจก.ม", "receiveTin": "3", "priceProposal": "810000"}])
    s.record_bid_results("F5", [   # วาย ลงแต่แพ้
        {"receiveNameTh": "หจก.พ", "receiveTin": "2", "priceProposal": "780000", "priceAgree": "780000"},
        {"receiveNameTh": "หจก.วาย", "receiveTin": "1", "priceProposal": "790000"},
        {"receiveNameTh": "หจก.ม", "receiveTin": "3", "priceProposal": "800000"}])
    with db.get_connection() as conn:
        block = bf.field_and_winrate(conn, "นครพนม", ["ถนน"], 1000000)[1]
    txt = "\n".join(block)
    assert "เจ้าตลาด" in txt and "วาย" in txt, txt
    print("✅ field_and_winrate 2B block end-to-end + gate")

test_field_block_endtoend_and_gate()

def test_gates_winrate():
    # fair-share property: ทุกคน P=0.5 → 1/(N+1)
    assert abs(bf.gates_winrate([0.5, 0.5, 0.5]) - 0.25) < 1e-9, bf.gates_winrate([0.5,0.5,0.5])
    # รายเดียว → P เอง
    assert abs(bf.gates_winrate([0.9]) - 0.9) < 1e-9, bf.gates_winrate([0.9])
    # ไม่ดิ่งศูนย์เท่า Friedman: 11 ราย @0.5 → Gates=1/12≈0.083 >> Friedman 0.5^11≈0.00049
    g = bf.gates_winrate([0.5] * 11)
    assert abs(g - 1/12) < 1e-9 and g > 0.5**11 * 100, g
    # ว่าง / None ล้วน → None
    assert bf.gates_winrate([]) is None
    assert bf.gates_winrate([None, None]) is None
    # ตัด None ทิ้งก่อนคิด
    assert abs(bf.gates_winrate([0.9, None]) - 0.9) < 1e-9, bf.gates_winrate([0.9, None])
    print("✅ gates_winrate (fair-share / single / no-collapse / empty)")

def test_p_beat():
    # ลด 30% → ชนะคนที่ลด 10,20 (2/3) ไม่ชนะคนลด 40
    d = [(10.0, 1.0), (20.0, 1.0), (40.0, 1.0)]
    assert abs(bf.p_beat(d, 30.0) - 2/3) < 1e-9, bf.p_beat(d, 30.0)
    # clamp สูง: ลดลึกกว่าทุกคน → 1.0 → 0.95
    assert bf.p_beat([(10.0,1.0),(20.0,1.0)], 50.0) == 0.95
    # clamp ต่ำ: ลดตื้นกว่าทุกคน → 0 → 0.05
    assert bf.p_beat([(40.0,1.0),(50.0,1.0)], 10.0) == 0.05
    # weight สำคัญ: bid ใหม่ (40, w=1.0) ถ่วงหนักกว่า bid เก่า (10, w=0.25) → P ต่ำ
    assert abs(bf.p_beat([(10.0,0.25),(40.0,1.0)], 30.0) - 0.2) < 1e-9, bf.p_beat([(10.0,0.25),(40.0,1.0)],30.0)
    # ว่าง / น้ำหนัก 0 → None
    assert bf.p_beat([], 30.0) is None
    assert bf.p_beat([(10.0, 0.0)], 30.0) is None
    print("✅ p_beat (fraction / clamp / weighted / empty)")

test_gates_winrate()
test_p_beat()

def test_pooled_and_company_dist():
    import Sebastian_Customer_DB as db
    db.init_schema()
    s = db.SubscriptionStore()
    # ชื่องาน encode subtype(concrete) + agency: local=อบต. / central=กรมทางหลวงชนบท
    LOCAL = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย{0} องค์การบริหารส่วนตำบลนาทม อำเภอนาทม จังหวัดนครพนม"
    CENTRAL = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย{0} กรมทางหลวงชนบท จังหวัดนครพนม"
    rows = []
    for i in range(6):   # 6 งาน concrete+local (อบต.)
        rows.append((f"L{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", LOCAL.format(i), 1000000, "2568"))
    for i in range(4):   # 4 งาน concrete+central (กรม) — agency ต่าง
        rows.append((f"C{i}", "นครพนม", "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", CENTRAL.format(i), 1000000, "2568"))
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners (project_id,province,proc_type,project_name,budget,fiscal_year) "
            "VALUES (?,?,?,?,?,?)", rows)
    # หจก.ครบ: ยื่นครบ 6 local → ผ่านชั้น1 (subtype+agency). ลด 20% (800k/1M)
    for i in range(6):
        s.record_bid_results(f"L{i}", [{"receiveNameTh": "หจก.ครบ", "receiveTin": "1", "priceProposal": "800000"}])
    # หจก.ตก: ยื่น 3 local + 4 central → local=3(<5 ตกชั้น1) แต่ concrete รวม 7 → ผ่านชั้น2 (subtype)
    for i in range(3):
        s.record_bid_results(f"L{i}", [{"receiveNameTh": "หจก.ตก", "receiveTin": "2", "priceProposal": "850000"}])
    for i in range(4):
        s.record_bid_results(f"C{i}", [{"receiveNameTh": "หจก.ตก", "receiveTin": "2", "priceProposal": "850000"}])
    with db.get_connection() as conn:
        # pooled: สนามถนน นครพนม → ต้องมี bids
        pooled = bf._pooled_dist(conn, "นครพนม", ["ถนน"])
        assert len(pooled) > 0 and all(len(t) == 2 for t in pooled), pooled
        # หจก.ครบ → ชั้น 1 (subtype+agency), label มีจำนวน
        dist1, lab1 = bf._company_bid_dist(conn, "หจก.ครบ", "concrete", "local")
        assert dist1 is not None and "หน่วยงาน" in lab1, (lab1, len(dist1 or []))
        assert len(dist1) == 6, dist1
        # หจก.ตก → concrete+local=3 <5 → ตกมาชั้น 2 (subtype only) = 7
        dist2, lab2 = bf._company_bid_dist(conn, "หจก.ตก", "concrete", "local")
        assert dist2 is not None and len(dist2) == 7, (lab2, len(dist2 or []))
        assert "ประเภทงาน" in lab2, lab2
        # ไม่มีประวัติ → (None, 'pooled')
        d3, lab3 = bf._company_bid_dist(conn, "หจก.ไม่มีเลย", "concrete", "local")
        assert d3 is None and lab3 == "pooled", (d3, lab3)
    print("✅ _pooled_dist + _company_bid_dist (layered raw-count gate)")

test_pooled_and_company_dist()
print("ALL PASS bid_field")
