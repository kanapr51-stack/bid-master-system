"""test_trend_prediction.py — _build_intel ปรับ percentile ตาม recency (area_win_series)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci

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
    # งานเก่าลด ~30%, งานล่าสุด ๆ ลด ~20% (เทรนด์ลดน้อยลง = ราคาสูงขึ้น) — ในจังหวัด
    data = [(30, "2566-01-01"), (30, "2566-06-01"), (30, "2567-01-01"),
            (20, "2567-11-01"), (20, "2568-01-01"), (20, "2568-05-01")]
    for i, (disc, ad) in enumerate(data):
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,announce_date,fiscal_year,proc_type,district,subdistrict) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (f"p{i}", "นครพนม", "ก่อสร้างถนน คสล.", f"หจก.{i}", 100000, disc, ad,
                   "256"+ad[3], EB, "เมือง", "ในเมือง"))
    c.commit(); return c


def test_recency_shifts_prediction():
    c = _conn()
    # province-level (amphoe=None) — budget 1,000,000
    ctx = ci._build_intel(c, "นครพนม", ["ถนน"], "", None, 1000000)
    assert ctx and ctx["prediction"], ctx
    pred = ctx["prediction"]
    # flat percentile ของ [30,30,30,20,20,20] = p25 20, p75 30 → กรอบบนราคา = 1,000,000*(1-0.20)=800,000
    # recency (EWMA ~22.4 < median 25 → delta ~-2.6) เลื่อนลง → p25'<20 → กรอบบนราคา area_price_hi สูงขึ้น
    assert pred["area_price_hi"] > 800000, pred       # ปรับขึ้นเพราะล่าสุดลดน้อยลง
    print("✅ recency ปรับ prediction ขึ้นตามงานล่าสุด (ลดน้อยลง → ราคาสูงขึ้น)")


if __name__ == "__main__":
    test_recency_shifts_prediction()
    print("\n✅ ALL test_trend_prediction PASS")
