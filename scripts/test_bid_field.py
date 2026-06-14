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
    fr = {"tier": 1, "leaders": [
        {"name": "ห้างหุ้นส่วนจำกัด เมืองทอง", "win_rate": 0.69, "wins": 9, "appears": 13, "win_disc_med": 25.0},
        {"name": "ห้างหุ้นส่วนจำกัด บัญชาศรี", "win_rate": 0.48, "wins": 10, "appears": 21, "win_disc_med": 22.0}]}
    txt = "\n".join(bf.field_lines(fr, 2_000_000))
    assert "เจ้าตลาด" in txt and "หจก. เมืองทอง" in txt, txt    # ย่อชื่อ
    assert "69%" in txt and "9/13" in txt, txt                  # win-rate + count
    assert "1,500,000" in txt, txt                              # 2M*(1-0.25) = ต้องลดสู้เจ้าตลาด
    assert "หจก. บัญชาศรี" in txt, txt                          # leader #2
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
    j1 = next(a for a in auctions if any(abs(d - 30.0) < 1e-9 for _n, d, _w in a))  # J1 มี disc 30
    discs = sorted(d for _n, d, _w in j1)
    assert discs == [10.0, 30.0], discs                  # (1-700k/1M)=30, (1-900k/1M)=10 · outlier 95% ตัด
    assert any(w for _n, _d, w in j1), "มี winner flag"
    print("✅ _field_auctions read + disc + outlier filter")

test_field_auctions_read()

def test_field_block_endtoend_and_gate():
    import Sebastian_Customer_DB as db
    db.init_schema()
    s = db.SubscriptionStore()
    # gate: bid_results ว่าง → field_block = [] (ปลอดภัยกับ _build_intel เดิม)
    with db.get_connection() as conn:
        assert bf.field_block(conn, "สกลนคร", ["ถนน"], 1000000) == [], "scope ว่าง → []"
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
        block = bf.field_block(conn, "นครพนม", ["ถนน"], 1000000)
    txt = "\n".join(block)
    assert "เจ้าตลาด" in txt and "วาย" in txt, txt
    print("✅ field_block end-to-end + gate")

test_field_block_endtoend_and_gate()
print("ALL PASS bid_field")
