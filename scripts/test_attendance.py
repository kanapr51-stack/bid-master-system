"""test_attendance.py — attendance_probs (N+196 auto-competitor): โอกาสบริษัทมายื่นต่อสนาม
recency-weighted appearance share + ladder 🟢→🟡→🟠 + threshold/cap/clamp."""
import os, sys, tempfile; from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()   # isolate จาก prod ก่อน import DB
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("BMS_FOLLOW_SECRET", "test-secret-attendance")
import bid_field as bf

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _db():
    import Sebastian_Customer_DB as db
    db.init_schema()
    return db


def _seed_field(db, province, prefix, name_tmpl, n_auctions, bidders_fn, fy="2569", budget=1000000):
    """seed cgd_winners + bid_results: auction ละ 1 แถว winner + bidders จาก bidders_fn(i)."""
    s = db.SubscriptionStore()
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id,province,proc_type,project_name,budget,fiscal_year,winner,win_price,"
            "discount_pct,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(f"{prefix}{i}", province, EB, name_tmpl.format(i), budget,
              fy if not callable(fy) else fy(i), "หจก.ประจำ", 850000, 15.0, "นาทม", "นาทม")
             for i in range(n_auctions)])
    for i in range(n_auctions):
        s.record_bid_results(f"{prefix}{i}", bidders_fn(i))


NAME_NATHOM = "ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย{0} องค์การบริหารส่วนตำบลนาทม อำเภอนาทม จังหวัดนครพนม"


def _seed_basic(db):
    """8 auctions ปีปัจจุบัน: หจก.ประจำ 8/8, หจก.ครึ่งเดียว 4/8, หจก.ขาจรi 1/8"""
    def bidders(i):
        b = [{"receiveNameTh": "หจก.ประจำ", "receiveTin": "1", "priceProposal": "850000"},
             {"receiveNameTh": f"หจก.ขาจร{i}", "receiveTin": str(100 + i), "priceProposal": "900000"}]
        if i < 4:
            b.append({"receiveNameTh": "หจก.ครึ่งเดียว", "receiveTin": "2", "priceProposal": "880000"})
        return b
    _seed_field(db, "นครพนม", "A", NAME_NATHOM, 8, bidders)


def test_attendance_basic_threshold_clamp():
    db = _db(); _seed_basic(db)
    with db.get_connection() as conn:
        out = bf.attendance_probs(conn, "นครพนม", ["ถนน"])
    assert out is not None, out
    assert out["conf"] is None and out["n_auctions"] == 8, out
    assert out["probs"]["หจก.ประจำ"] == 0.95, out          # 8/8=1.0 → clamp 0.95
    assert out["probs"]["หจก.ครึ่งเดียว"] == 0.5, out       # 4/8
    assert all("ขาจร" not in k for k in out["probs"]), out  # 1/8=0.125 < 0.15 → ตัด
    print("✅ attendance basic + threshold + clamp")


def test_attendance_recency_weighting():
    """งานเก่า (2565, w=0.0625) แทบไม่นับ: หจก.เก่า โผล่ 3/8 ดิบ (0.375 ถ้าไม่ถ่วง)
    แต่ถ่วงแล้ว = 3×0.0625/(5+3×0.0625) ≈ 0.036 → ต้องไม่ติดลิสต์"""
    db = _db()
    NAME = "ก่อสร้างถนนลาดยาง สาย{0} ตำบลไชยบุรี อำเภอท่าอุเทน จังหวัดมุกดาหาร"
    def bidders(i):
        if i < 5:   # ปีปัจจุบัน
            return [{"receiveNameTh": "หจก.สด", "receiveTin": "1", "priceProposal": "850000"},
                    {"receiveNameTh": "หจก.สดสอง", "receiveTin": "2", "priceProposal": "900000"}]
        return [{"receiveNameTh": "หจก.เก่า", "receiveTin": "3", "priceProposal": "850000"},
                {"receiveNameTh": "หจก.เก่าสอง", "receiveTin": "4", "priceProposal": "900000"}]
    _seed_field(db, "มุกดาหาร", "R", NAME, 8, bidders, fy=lambda i: "2569" if i < 5 else "2565")
    with db.get_connection() as conn:
        out = bf.attendance_probs(conn, "มุกดาหาร", ["ถนน"])
    assert out is not None, out
    assert out["probs"]["หจก.สด"] == 0.95, out              # 5/5.1875=0.964 → clamp
    assert "หจก.เก่า" not in out["probs"], out               # recency ฆ่าข้อมูลเก่า
    print("✅ attendance recency weighting")


def test_attendance_gate_and_ladder():
    db = _db()
    # จังหวัดที่มีแค่ 3 auctions → ไม่พอ (MIN_AUCTIONS=5) → None
    NAME_BK = "ก่อสร้างถนนคอนกรีต สาย{0} ตำบลบึงโขงหลง อำเภอบึงโขงหลง จังหวัดบึงกาฬ"
    _seed_field(db, "บึงกาฬ", "T", NAME_BK, 3,
                lambda i: [{"receiveNameTh": "หจก.ก", "receiveTin": "1", "priceProposal": "850000"},
                           {"receiveNameTh": "หจก.ข", "receiveTin": "2", "priceProposal": "900000"}])
    _seed_basic(db)   # นครพนม 8 auctions (อ.นาทม)
    with db.get_connection() as conn:
        assert bf.attendance_probs(conn, "บึงกาฬ", ["ถนน"]) is None
        # local (project_ids) แค่ 2 → ผ่อนไปอำเภอ (🟡) เจอ 8 งานของ อ.นาทม
        out = bf.attendance_probs(conn, "นครพนม", ["ถนน"], project_ids=["A0", "A1"],
                                  cf={}, amphoe="นาทม")
    assert out is not None and out["conf"] == ("🟡", "อำเภอ"), out
    assert out["probs"]["หจก.ประจำ"] == 0.95, out
    print("✅ attendance MIN_AUCTIONS gate + ladder อำเภอ")


def test_attendance_cap10():
    db = _db()
    NAME = "ก่อสร้างถนนคอนกรีต สาย{0} ตำบลธาตุเชิงชุม อำเภอเมืองสกลนคร จังหวัดสกลนคร"
    _seed_field(db, "สกลนคร", "C", NAME, 6,
                lambda i: [{"receiveNameTh": f"บริษัท แคป{j} จำกัด", "receiveTin": str(j),
                            "priceProposal": "880000"} for j in range(12)])
    with db.get_connection() as conn:
        out = bf.attendance_probs(conn, "สกลนคร", ["ถนน"])
    assert out is not None and len(out["probs"]) == 10, out   # 12 เจ้า p=0.95 หมด → cap 10
    print("✅ attendance cap 10")


def test_attendance_graceful_bad_conn():
    import sqlite3
    empty = sqlite3.connect(":memory:")   # ไม่มีตารางเลย → ต้อง None ไม่ throw
    assert bf.attendance_probs(empty, "นครพนม", ["ถนน"]) is None
    print("✅ attendance graceful (no tables)")


if __name__ == "__main__":
    test_attendance_basic_threshold_clamp()
    test_attendance_recency_weighting()
    test_attendance_gate_and_ladder()
    test_attendance_cap10()
    test_attendance_graceful_bad_conn()
    print("ALL PASS (attendance)")
