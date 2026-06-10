"""test_round2_analysis.py — company_area_history + analyze_bidders (ranking, ประวัติ, ป้าย)."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    rows = [  # หจก.X เคยลดในตำบลโพนทอง 2 ครั้ง (24,26→median25)
        ("h1", "ถนน คสล. โพนทอง", "หจก.X", 24.0, "บ้านแพง", "โพนทอง"),
        ("h2", "ถนน คสล. โพนทอง", "หจก.X", 26.0, "บ้านแพง", "โพนทอง"),
        ("h3", "ถนน คสล. นาแก", "หจก.Y", 30.0, "นาแก", "พิมาน"),   # Y นอกตำบลโพนทอง
    ]
    for pid, name, win, disc, dist, sub in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", name, win, 100000, disc, "2567", EB, dist, sub))
    c.commit(); return c


def test_company_area_history():
    c = _conn()
    h = ci.company_area_history(c, "นครพนม", ["ถนน"], "หจก.X", "โพนทอง", "บ้านแพง")
    assert h["scope"] == "ตำบล" and h["n"] == 2 and abs(h["median"] - 25) < 0.01, h
    h2 = ci.company_area_history(c, "นครพนม", ["ถนน"], "หจก.Y", "โพนทอง", "บ้านแพง")
    assert h2["scope"] == "นอกตำบล" and h2["n"] == 1, h2   # Y ไม่มีในโพนทอง → fallback ทั้งจังหวัด
    h3 = ci.company_area_history(c, "นครพนม", ["ถนน"], "หจก.Z", "โพนทอง", "บ้านแพง")
    assert h3["n"] == 0, h3                                  # หน้าใหม่
    print("✅ company_area_history")


def test_analyze_bidders():
    c = _conn()
    bidders = [  # จาก bid_results: name, price_proposal, is_winner
        {"bidder_name": "หจก.X", "price_proposal": "738000", "is_winner": 1},
        {"bidder_name": "หจก.Y", "price_proposal": "752000", "is_winner": 0},
        {"bidder_name": "หจก.Z", "price_proposal": "760000", "is_winner": 0},
    ]
    warned = ["หจก.X"]   # top-3 intel ที่เตือนตอน D0
    out = ci.analyze_bidders(c, "นครพนม", ["ถนน"], "โพนทอง", "บ้านแพง", 1017000, bidders, warned)
    assert [b["name"] for b in out] == ["หจก.X", "หจก.Y", "หจก.Z"], out   # เรียงราคา
    assert out[0]["is_winner"] and out[0]["tag"] == "warned", out          # X เตือนแล้ว
    assert out[1]["tag"] == "regular_missed", out                          # Y มีประวัติ(นอกตำบล) แต่ไม่เตือน
    assert out[2]["tag"] == "newcomer", out                                # Z หน้าใหม่
    assert out[0]["hist"]["n"] == 2, out                                   # X ประวัติตำบล 2 ครั้ง
    assert "ewma" in out[0]["hist"], out[0]            # มี ewma (recency) — Sub-2a
    print("✅ analyze_bidders")


if __name__ == "__main__":
    test_company_area_history()
    test_analyze_bidders()
    print("\n✅ ALL test_round2_analysis PASS")
