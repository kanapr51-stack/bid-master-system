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


def test_compute_stats():
    rows = [{"win_price": p, "discount_pct": d, "winner": w} for p, d, w in [
        (1_000_000, 2.0, "หจก.A"), (1_200_000, 3.0, "หจก.A"), (1_500_000, 4.0, "หจก.A"),
        (2_000_000, 5.0, "หจก.B"), (3_000_000, 20.0, "หจก.B"), (1_100_000, 4.0, "หจก.C")]]
    s = ci.compute_stats(rows)
    assert s["count"] == 6
    assert s["discount_median"] == 4.0, s["discount_median"]   # median ของ [2,3,4,4,5,20]
    assert s["discount_p25"] == 3.25 and s["discount_p75"] == 4.75, (s["discount_p25"], s["discount_p75"])
    assert s["top_winners"][0] == ("หจก.A", 3), s["top_winners"]
    assert s["price_lo"] is not None and s["price_hi"] >= s["price_lo"]
    # discount ทั้งหมด null → median/p25/p75 = None
    s2 = ci.compute_stats([{"win_price": 100, "discount_pct": None, "winner": "X"}])
    assert s2["discount_median"] is None and s2["discount_p25"] is None
    print("✅ compute_stats")


def test_intel_lines():
    c = _fixture_conn()   # มีงานนครพนมแค่ 2 (R1,R2) → < min_count
    # ต่ำกว่า threshold → []
    assert ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล.", min_count=10, conn=c) == []
    # ชื่อไม่มี work-type → []
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", min_count=1, conn=c) == []
    # min_count=1 → ได้ section (ทดสอบ format)
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล.", min_count=1, conn=c)
    assert out[0] == "💡 ราคาอ้างอิง (งานถนนในนครพนม)", out[0]
    assert any(l.startswith("📊 จาก 1 งาน") for l in out)        # ≥2-overlap = R1 เดี่ยว
    assert any("ส่วนลดที่พบบ่อย" in l for l in out)
    assert any(l.strip().startswith("• หจก.A (1)") for l in out)
    # fallback: ≥2 ได้ 1 (<2) → relax ≥1 ได้ 2
    out2 = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล.", min_count=2, conn=c)
    assert any(l.startswith("📊 จาก 2 งาน") for l in out2), out2
    print("✅ intel_lines")


if __name__ == "__main__":
    test_match_keywords()
    test_query_similar()
    test_compute_stats()
    test_intel_lines()
    print("ALL PASS (Task 1-4)")
