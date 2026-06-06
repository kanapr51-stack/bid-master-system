"""test_cgd_intel.py — competitor-profile intel ระดับท้องถิ่น (resolve→select→stats→lines)."""
import sys, sqlite3; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci


def test_match_keywords():
    kws = ["ถนน", "คสล", "อาคาร"]
    assert ci.match_keywords("ก่อสร้างถนน คสล. บ้านแพง", keywords=kws) == ["ถนน", "คสล"]
    assert ci.match_keywords("จัดซื้อรถยนต์", keywords=kws) == []
    assert "ถนน" in ci.match_keywords("ปรับปรุงถนนลาดยาง")
    print("✅ match_keywords")


def _fixture_conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    rows = [
        # pid, prov, pname, winner, wp, disc, fy, proc, district, subdistrict
        ("R1", "นครพนม", "ถนน คสล. บ้านแพง", "หจก.A", 950000, 5.0, "2567", EB, "บ้านแพง", "โพนทอง"),
        ("R2", "นครพนม", "ถนนลาดยาง บ้านแพง", "หจก.A", 900000, 8.0, "2567", EB, "บ้านแพง", "โพนทอง"),
        ("R3", "นครพนม", "ถนน คสล.", "หจก.B", 800000, 10.0, "2568", EB, "บ้านแพง", "โพนทอง"),
        ("R4", "นครพนม", "ถนนเมือง", "หจก.C", 700000, 12.0, "2567", EB, "เมืองนครพนม", "ในเมือง"),
        ("R5", "นครพนม", "ถนนเฉพาะเจาะจง", "หจก.D", 1000000, 0.0, "2567", "เฉพาะเจาะจง", "บ้านแพง", "โพนทอง"),
    ]
    for pid, prov, pname, win, wp, disc, fy, proc, dist, sub in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, prov, pname, win, wp, disc, fy, proc, dist, sub))
    c.commit(); return c


def test_resolve_tambon():
    assert ci.resolve_tambon("ก่อสร้างถนน ต.โพนทอง") == "โพนทอง"
    assert ci.resolve_tambon("ก่อสร้างถนน", "องค์การบริหารส่วนตำบลบ้านแพง") == "บ้านแพง"
    assert ci.resolve_tambon("ก่อสร้างถนน", "") == ""
    print("✅ resolve_tambon")


def test_select_competitors():
    c = _fixture_conn(); tk = ["ถนน"]
    # tambon โพนทอง อ.บ้านแพง: winners A,B (≥MIN=2) → tambon. R5 เฉพาะเจาะจงถูกตัด
    rows, scope, level = ci.select_competitors("นครพนม", tk, "โพนทอง", c)
    assert level == "tambon" and "ต.โพนทอง" in scope, (level, scope)
    assert {r["winner"] for r in rows} == {"หจก.A", "หจก.B"}, rows
    # ตำบลไม่มี → fallback province
    rows2, _scope2, level2 = ci.select_competitors("นครพนม", tk, "ไม่มีตำบลนี้", c)
    assert level2 == "province" and {"หจก.A", "หจก.B", "หจก.C"} <= {r["winner"] for r in rows2}, rows2
    # resolve ไม่ได้ (tambon='') → province
    assert ci.select_competitors("นครพนม", tk, "", c)[2] == "province"
    # จังหวัดไม่มีงานเลย → []
    assert ci.select_competitors("เชียงใหม่", tk, "", c)[0] == []
    print("✅ select_competitors")


def test_company_stats():
    c = _fixture_conn(); tk = ["ถนน"]
    # หจก.A 2 งาน (disc 5,8) → games=2 < MIN_GAMES_FOR_IQR=3 → ไม่มี IQR, median 6.5
    s = ci.company_stats("หจก.A", tk, c)
    assert s["games"] == 2 and s["median"] == 6.5 and s["p25"] is None, s
    # หจก.D ทำแต่งานเฉพาะเจาะจง → competitive filter ตัดหมด → games=0
    assert ci.company_stats("หจก.D", tk, c)["games"] == 0
    print("✅ company_stats")


def test_confidence_label():
    assert ci.confidence_label(40, 5, 10).startswith("🟢")
    assert ci.confidence_label(15, 5, 10).startswith("🟡")     # n<30
    assert ci.confidence_label(40, 5, 30).startswith("🟡")     # IQR กว้าง (25>20)
    assert ci.confidence_label(5, None, None).startswith("🔴") # n<10
    print("✅ confidence_label")


def test_intel_lines():
    c = _fixture_conn()
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", conn=c)
    assert out[0] == "💡 ราคาอ้างอิง (งานถนน ต.โพนทอง อ.บ้านแพง)", out[0]
    assert "🏆 คู่แข่งแถบนี้:" in out, out
    assert any("หจก.A" in l and "งาน" in l for l in out), out
    assert any(l.startswith("📊 ภาพรวม") for l in out), out
    assert any(l[0] in "🟢🟡🔴" for l in out), out
    # ชื่อไม่มี work-type → []
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", conn=c) == []
    # จังหวัดไม่มีคู่แข่ง → []
    assert ci.intel_lines("เชียงใหม่", "ก่อสร้างถนน", conn=c) == []
    print("✅ intel_lines")


def test_wiring_format_notification():
    import Sebastian_LINE_Sender as ls
    import cgd_intel as _ci
    orig = _ci.intel_lines
    # (1) intel มีข้อมูล → แทรกใน card + divider
    _ci.intel_lines = lambda *a, **k: ["💡 TEST INTEL", "🏆 คู่แข่งแถบนี้:"]
    txt = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                 source_stage="followed_bid_open")
    assert "💡 TEST INTEL" in txt and "🔑 P1" in txt and "━" in txt, txt
    # (2) intel throw → card ยังออก (value-add ห้ามพัง)
    _ci.intel_lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    txt2 = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="followed_bid_open")
    assert "🔑 P1" in txt2 and "💡" not in txt2, txt2
    # (3) source_stage อื่น → ไม่แตะ intel
    _ci.intel_lines = lambda *a, **k: ["💡 SHOULD NOT APPEAR"]
    txt3 = ls.format_notification("P2", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="api_enriched")
    assert "💡" not in txt3, txt3
    _ci.intel_lines = orig
    print("✅ wiring format_notification")


if __name__ == "__main__":
    test_match_keywords()
    test_resolve_tambon()
    test_select_competitors()
    test_company_stats()
    test_confidence_label()
    test_intel_lines()
    test_wiring_format_notification()
    print("ALL PASS (tambon competitor intel)")
