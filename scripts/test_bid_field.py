"""test_bid_field.py — dominant-detection: analyze_field / field_lines / _field_auctions."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import bid_field as bf

def mk(winner, wdisc, others):
    """auction: ผู้ชนะ + others=[(name,disc)]."""
    return [(winner, wdisc, True)] + [(n, d, False) for n, d in others]

def test_tier1_named_dominant():
    auctions = [
        mk("X", 40, [("A", 20), ("B", 19), ("C", 21)]),
        mk("X", 38, [("A", 20), ("B", 18)]),
        mk("X", 42, [("D", 22), ("B", 20)]),
        mk("X", 39, [("A", 21), ("C", 19)]),
        mk("A", 23, [("B", 21), ("C", 22)]),     # X ไม่มา
    ]
    fr = bf.analyze_field(auctions)
    assert fr["tier"] == 1, fr
    assert fr["dominant"]["name"] == "X", fr
    assert abs(fr["dominant"]["show_rate"] - 0.8) < 1e-9, fr   # X ลง 4/5
    assert fr["dominant"]["win_gap_med"] > 10, fr
    print("✅ tier1 named dominant")

def test_tier2_structural():
    auctions = [
        mk("W1", 40, [("A", 20), ("B", 19)]),
        mk("W2", 38, [("C", 20), ("D", 18)]),
        mk("W3", 42, [("E", 22), ("F", 20)]),
        mk("A", 22, [("B", 21)]),                # tight
        mk("C", 23, [("D", 22)]),                # tight
    ]
    fr = bf.analyze_field(auctions)
    assert fr["tier"] == 2, fr                    # landslide เยอะ แต่ไม่มีเจ้าเด่น
    assert fr["landslide_gap_med"] == 20, fr
    print("✅ tier2 structural")

def test_tier0_tight_and_gate():
    tight = [mk(f"W{i}", 22, [("A", 21), ("B", 20)]) for i in range(5)]
    assert bf.analyze_field(tight)["tier"] == 0, "สนามสูสี → tier0"
    assert bf.analyze_field(tight[:4])["tier"] == 0, "n<MIN_AUCTIONS → gate tier0"
    print("✅ tier0 tight + gate น้อย")

test_tier1_named_dominant()
test_tier2_structural()
test_tier0_tight_and_gate()

def test_field_lines():
    # tier1: budget 1,000,000 · win_disc 40 → 600,000 · pack 20 → 800,000
    fr1 = {"tier": 1, "pack_disc_med": 20.0,
           "dominant": {"name": "ห้างหุ้นส่วนจำกัด เอ็กซ์", "show_rate": 0.8,
                        "win_disc_med": 40.0, "win_gap_med": 22.0}}
    lines = bf.field_lines(fr1, 1_000_000); txt = "\n".join(lines)
    assert "เจ้าใหญ่" in txt and "หจก. เอ็กซ์" in txt, txt   # ย่อชื่อ
    assert "600,000" in txt and "800,000" in txt, txt        # baht 2 ฉากทัศน์
    assert "80%" in txt, txt                                  # show-rate
    # tier0 / ข้อมูลน้อย → []
    assert bf.field_lines({"tier": 0, "pack_disc_med": None}, 1_000_000) == []
    assert bf.field_lines(None, 1_000_000) == []
    assert bf.field_lines(fr1, 0) == []                       # ไม่มี budget
    # tier2
    fr2 = {"tier": 2, "pack_disc_med": 20.0, "landslide_gap_med": 18.0, "dominant": None}
    l2 = "\n".join(bf.field_lines(fr2, 1_000_000))
    assert "ขาดลอย" in l2 and "800,000" in l2, l2
    print("✅ field_lines baht (tier1/2/0)")

test_field_lines()
print("ALL PASS bid_field")
