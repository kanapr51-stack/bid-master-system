"""test_geo_reverse.py — reverse-geocode พิกัด → อำเภอ (แยกตำบลซ้ำ) จาก thai_geo_raw."""
import sys, csv; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import geo_reverse as gr

_CSV = Path(__file__).parent.parent / "data" / "thai_geo_raw.csv"


def _find(prov, amphoe, tambon):
    with open(_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["province"] == prov and r["district"] == amphoe and r["subdistrict"] == tambon:
                return float(r["latitude"]), float(r["longitude"])
    return None


def test_reverse_geocode_disambiguates_tambon():
    bp = _find("นครพนม", "บ้านแพง", "โพนทอง")
    rn = _find("นครพนม", "เรณูนคร", "โพนทอง")
    assert bp and rn, (bp, rn)   # ทั้งสองโพนทองมีจริงใน geo
    p, a, t, d = gr.reverse_geocode(bp[0], bp[1])
    assert a == "บ้านแพง" and d < 1.0, (a, d)
    p2, a2, t2, d2 = gr.reverse_geocode(rn[0], rn[1])
    assert a2 == "เรณูนคร", a2
    print("✅ reverse_geocode disambiguate")


def test_reverse_geocode_bad_input():
    assert gr.reverse_geocode("", "") is None
    assert gr.reverse_geocode(None, 100.0) is None
    print("✅ reverse_geocode bad input")


def test_amphoes_of_tambon():
    amp = gr.amphoes_of_tambon("นครพนม", "โพนทอง")
    assert "บ้านแพง" in amp and "เรณูนคร" in amp and len(amp) >= 2, amp   # ซ้ำ
    assert gr.amphoes_of_tambon("นครพนม", "ไม่มีตำบลนี้") == []
    print("✅ amphoes_of_tambon")


if __name__ == "__main__":
    test_reverse_geocode_disambiguates_tambon()
    test_reverse_geocode_bad_input()
    test_amphoes_of_tambon()
    print("ALL PASS geo_reverse")
