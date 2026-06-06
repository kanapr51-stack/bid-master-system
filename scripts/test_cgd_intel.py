"""test_cgd_intel.py — competitive intel (query cgd_winners → stats → LINE lines)."""
import sys, sqlite3; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci


def test_match_keywords():
    kws = ["ถนน", "คสล", "อาคาร"]
    assert ci.match_keywords("ก่อสร้างถนน คสล. บ้านแพง", keywords=kws) == ["ถนน", "คสล"]
    assert ci.match_keywords("จัดซื้อรถยนต์", keywords=kws) == []
    assert ci.match_keywords("", keywords=kws) == []
    # default โหลด config จริง — งานถนนต้องเจอ token
    assert "ถนน" in ci.match_keywords("ปรับปรุงถนนลาดยาง")
    print("✅ match_keywords")


def _fixture_conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT, synced_at TEXT)""")
    rows = [
        ("R1", "นครพนม", "ก่อสร้างถนน คสล. บ้านแพง", "หจก.A", 1000000, 950000, 5.0),  # ถนน+คสล overlap2
        ("R2", "นครพนม", "ซ่อมถนนลูกรัง", "หจก.B", 800000, 760000, 5.0),               # ถนน overlap1
        ("R3", "บึงกาฬ", "ก่อสร้างถนน คสล.", "หจก.C", 1000000, 900000, 10.0),          # คนละจังหวัด
        ("R4", "นครพนม", "ก่อสร้างถนน คสล.", "หจก.D", 1000000, 0, None),               # win_price=0 ตัด
    ]
    for pid, prov, pname, win, bud, wp, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,budget,"
                  "win_price,discount_pct) VALUES (?,?,?,?,?,?,?)",
                  (pid, prov, pname, win, bud, wp, disc))
    c.commit(); return c


def test_query_similar():
    c = _fixture_conn(); tk = ["ถนน", "คสล"]
    r2 = ci.query_similar("นครพนม", tk, min_overlap=2, conn=c)
    assert [x["project_name"] for x in r2] == ["ก่อสร้างถนน คสล. บ้านแพง"], r2
    r1 = ci.query_similar("นครพนม", tk, min_overlap=1, conn=c)
    assert len(r1) == 2, r1   # R1+R2 (R3 คนละจังหวัด, R4 win_price=0)
    assert ci.query_similar("", tk, 1, conn=c) == []
    # graceful: ไม่มี table cgd_winners → []
    empty = sqlite3.connect(":memory:")
    assert ci.query_similar("นครพนม", tk, 1, conn=empty) == []
    print("✅ query_similar")


if __name__ == "__main__":
    test_match_keywords()
    test_query_similar()
    print("ALL PASS (Task 1-2)")
