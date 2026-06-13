"""test_winrate.py — เฟส 0: headline a/b/c "ยื่นราคา X → โอกาสชนะ Y%" (กัญจน์ 2026-06-13).
a=p75(ดุสุด,ชนะ75%) · b=median(50%) · c=p25(กำไรงาม,25%). win% = percentile (บิดดุกว่าผู้ชนะ X% = ชนะ ~X%)."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci


def test_predict_lines_winrate():
    # p25=10 p75=30 median=20 → a=งบ×(1-.30)=700k(75%) b=×(1-.20)=800k(50%) c=×(1-.10)=900k(25%)
    p = ci.predict_winning_price(1000000, 10.0, 30.0, area_median=20.0)
    lines = ci.predict_lines(p, "อำเภอ"); txt = "\n".join(lines)
    assert "แนะนำ" in txt, txt
    assert "700,000" in txt and "~75%" in txt, txt        # ดุสุด ชนะบ่อย
    assert "800,000" in txt and "~50%" in txt, txt
    assert "900,000" in txt and "~25%" in txt, txt        # กำไรงาม เสี่ยง
    assert any("เจ้าใหญ่" in l for l in lines), txt        # disclaimer คู่แข่ง
    assert ci.predict_lines(None) == []
    print("✅ predict_lines a/b/c (75/50/25%)")


def test_predict_lines_thin_dedupe():
    # p25=p50=20 → b,c ราคาเท่ากัน (800k) → dedupe + ข้อมูลน้อย + เก็บ win% ต่ำสุด (conservative)
    p = ci.predict_winning_price(1000000, 20.0, 40.0, area_median=20.0)
    lines = ci.predict_lines(p, "ตำบล"); txt = "\n".join(lines)
    assert sum(l.count("800,000") for l in lines) == 1, txt   # ไม่โชว์ราคาซ้ำ
    assert "~25%" in txt and "~50%" not in txt, txt           # conservative (ไม่ overstate)
    assert any("ข้อมูลน้อย" in l for l in lines), txt
    print("✅ predict_lines dedupe เมื่อข้อมูลน้อย (conservative win%)")


if __name__ == "__main__":
    test_predict_lines_winrate()
    test_predict_lines_thin_dedupe()
    print("ALL PASS (winrate headline)")
