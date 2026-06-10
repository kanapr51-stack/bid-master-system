"""test_competitor_trend_series.py — area_win_series + company_series (cgd_winners + bid_results)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import competitor_trend as ct

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        project_name TEXT, winner TEXT, win_price INTEGER, discount_pct REAL,
        announce_date TEXT, fiscal_year TEXT, proc_type TEXT, district TEXT, subdistrict TEXT)""")
    c.execute("""CREATE TABLE bid_results (project_id TEXT, bidder_name TEXT, bidder_tin TEXT,
        price_proposal TEXT, price_agree TEXT, is_winner INTEGER, result_flag TEXT, fetched_at TEXT,
        PRIMARY KEY(project_id, bidder_tin))""")
    c.execute("""CREATE TABLE projects_seen (project_id TEXT PRIMARY KEY, province TEXT, budget INTEGER)""")
    # cgd_winners: ถนนโพนทอง — หจก.X ชนะ 2 งาน (ลด 20 เก่า, 24 ใหม่), หจก.Y ลด 30
    w = [("w1", "ถนน คสล. โพนทอง", "หจก.X", 20.0, "2566-01-01", "บ้านแพง", "โพนทอง"),
         ("w2", "ถนน คสล. โพนทอง", "หจก.X", 24.0, "2567-06-01", "บ้านแพง", "โพนทอง"),
         ("w3", "ถนน คสล. โพนทอง", "หจก.Y", 30.0, "2567-01-01", "บ้านแพง", "โพนทอง")]
    for pid, nm, win, disc, ad, dist, sub in w:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,announce_date,fiscal_year,proc_type,district,subdistrict) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", nm, win, 100000, disc, ad, "256"+ad[3], EB, dist, sub))
    # bid_results: หจก.X เสนอราคางานใหม่ (price_proposal 700000 บน budget 1,000,000 = ลด 30) ล่าสุด
    c.execute("INSERT INTO projects_seen VALUES ('b1','นครพนม',1000000)")
    c.execute("INSERT INTO bid_results VALUES ('b1','หจก.X','T1','700000','700000',1,'P','2568-06-01')")
    c.commit(); return c


def test_area_win_series():
    c = _conn()
    s = ct.area_win_series(c, "นครพนม", ["ถนน"], subdistrict="โพนทอง", district="บ้านแพง")
    # winner discounts เรียงเวลา: w1(20,2566) w3(30,2567-01) w2(24,2567-06) b1(30,2568) → ตัวท้ายใหม่สุด
    assert s[-1] == 30.0, s                      # bid_results winner ล่าสุด
    assert s[0] == 20.0, s                       # cgd เก่าสุด
    assert len(s) == 4, s                        # 3 cgd winners + 1 bid_result winner
    print("✅ area_win_series (cgd_winners + bid_results winner, เรียงเวลา)")


def test_company_series():
    c = _conn()
    discs, scope = ct.company_series(c, "นครพนม", ["ถนน"], "หจก.X", subdistrict="โพนทอง", district="บ้านแพง")
    # หจก.X: cgd win 20(2566),24(2567) + bid_result เสนอ 30(2568) → เรียง [20,24,30]
    assert discs == [20.0, 24.0, 30.0], discs
    assert scope == "ตำบล", scope
    # บริษัทไม่มีในตำบล → fallback จังหวัด (Y มีแต่ในโพนทองด้วย — ใช้บริษัทใหม่)
    d2, sc2 = ct.company_series(c, "นครพนม", ["ถนน"], "หจก.ใหม่", subdistrict="โพนทอง", district="บ้านแพง")
    assert d2 == [] and sc2 == "", (d2, sc2)
    print("✅ company_series (cgd win + bid proposal, scope ตำบล→จังหวัด)")


if __name__ == "__main__":
    test_area_win_series()
    test_company_series()
    print("\n✅ ALL test_competitor_trend_series PASS")
