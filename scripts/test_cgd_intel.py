"""test_cgd_intel.py — competitor-profile intel + location disambiguation (resolve→select→lines)."""
import sys, sqlite3, csv; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci

_GEO = Path(__file__).parent.parent / "data" / "thai_geo_raw.csv"


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
        ("R1", "นครพนม", "ถนน คสล. บ้านแพง", "หจก.A", 950000, 5.0, "2567", EB, "บ้านแพง", "โพนทอง"),
        ("R2", "นครพนม", "ถนนลาดยาง บ้านแพง", "หจก.A", 900000, 8.0, "2567", EB, "บ้านแพง", "โพนทอง"),
        ("R3", "นครพนม", "ถนน คสล.", "หจก.B", 800000, 10.0, "2568", EB, "บ้านแพง", "โพนทอง"),
        ("R4", "นครพนม", "ถนนเมือง", "หจก.C", 700000, 12.0, "2567", EB, "เมืองนครพนม", "ในเมือง"),
        ("R5", "นครพนม", "ถนนเฉพาะเจาะจง", "หจก.D", 1000000, 0.0, "2567", "เฉพาะเจาะจง", "บ้านแพง", "โพนทอง"),
        ("R6", "นครพนม", "ถนน คสล. เรณู", "หจก.X", 850000, 9.0, "2567", EB, "เรณูนคร", "โพนทอง"),  # โพนทองอีกอำเภอ
    ]
    for pid, prov, pname, win, wp, disc, fy, proc, dist, sub in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, prov, pname, win, wp, disc, fy, proc, dist, sub))
    c.commit(); return c


def _loc_conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE project_locations (project_id TEXT PRIMARY KEY,
        district_moi_id TEXT, moi_name TEXT, latitude TEXT, longitude TEXT)""")
    return c


def _coords(prov, amphoe, tambon):
    for r in csv.DictReader(open(_GEO, encoding="utf-8")):
        if r["province"] == prov and r["district"] == amphoe and r["subdistrict"] == tambon:
            return r["latitude"], r["longitude"]
    return None


def test_resolve_location_geo():
    bp = _coords("นครพนม", "บ้านแพง", "โพนทอง")
    assert bp, "fixture coords"
    c = _loc_conn()
    c.execute("INSERT INTO project_locations VALUES ('P1','','โพนทอง',?,?)", (bp[0], bp[1]))
    out = ci.resolve_location("P1", "ก่อสร้างถนน", "", "นครพนม", c)
    assert out["amphoe"] == "บ้านแพง" and out["source"] == "geo", out
    assert out["location_confidence"] in ("HIGH", "MEDIUM"), out
    assert isinstance(out["resolution_trace"], list) and any("geo" in t for t in out["resolution_trace"]), out
    print("✅ resolve_location geo (disambiguate โพนทอง→บ้านแพง)")


def test_resolve_location_fallbacks():
    c = _loc_conn()
    # ไม่มี row + ตำบลซ้ำ (โพนทอง) → ไม่มีพิกัด → ambiguous → dept ไม่มี → province
    out = ci.resolve_location("PX", "ก่อสร้างถนน ต.โพนทอง", "", "นครพนม", c)
    assert out["amphoe"] is None and out["source"] == "province" and out["location_confidence"] == "LOW", out
    # ไม่มี work-type/ตำบล → province LOW
    out2 = ci.resolve_location("PY", "จัดซื้อรถ", "", "นครพนม", c)
    assert out2["amphoe"] is None and out2["location_confidence"] == "LOW", out2
    # dept ช่วย: ตำบลซ้ำ (โพนทอง) + dept อบต.เรณู (ถ้า เรณู unique) — ใช้ตำบลไม่ซ้ำแทนเพื่อ deterministic
    print("✅ resolve_location fallbacks (precision preserve → province)")


def test_select_competitors():
    c = _fixture_conn(); tk = ["ถนน"]
    # amphoe ระบุ → tambon level (subdistrict+district)
    rows, scope, level = ci.select_competitors("นครพนม", tk, "โพนทอง", "บ้านแพง", c)
    assert level == "tambon" and "ต.โพนทอง" in scope and "บ้านแพง" in scope, (level, scope)
    assert {r["winner"] for r in rows} == {"หจก.A", "หจก.B"}, rows   # R5 เฉพาะเจาะจง ตัด, R4 อำเภออื่น
    # amphoe=None → province (ไม่ใช่ WHERE district IS NULL) — precision preserve
    rows2, _s2, level2 = ci.select_competitors("นครพนม", tk, "", None, c)
    assert level2 == "province" and {"หจก.A", "หจก.B", "หจก.C"} <= {r["winner"] for r in rows2}, rows2
    # จังหวัดไม่มีงาน → []
    assert ci.select_competitors("เชียงใหม่", tk, "", None, c)[0] == []
    print("✅ select_competitors (amphoe + province fallback)")


def test_golden_amphoe_better_than_province():
    """golden: โพนทองมี 2 อำเภอ (บ้านแพง=A,B · เรณูนคร=X). amphoe-level ต้องตัด X ออก
    (เลือกเฉพาะคู่แข่งบ้านแพง) ขณะ province รวม X มาด้วย → พิสูจน์ disambiguation ดีขึ้นจริง."""
    c = _fixture_conn(); tk = ["ถนน"]
    amp_rows, _s, lv = ci.select_competitors("นครพนม", tk, "โพนทอง", "บ้านแพง", c)
    amp_winners = {r["winner"] for r in amp_rows}
    prov_rows, _s2, lv2 = ci.select_competitors("นครพนม", tk, "", None, c)
    prov_winners = {r["winner"] for r in prov_rows}
    assert lv == "tambon" and "หจก.X" not in amp_winners, amp_winners       # เรณูนคร ถูกตัด
    assert amp_winners == {"หจก.A", "หจก.B"}, amp_winners
    assert "หจก.X" in prov_winners and "หจก.C" in prov_winners, prov_winners # province รวมทุกอำเภอ
    assert amp_winners < prov_winners                                       # amphoe เจาะกว่า province
    print("✅ golden: amphoe ตัดคู่แข่งคนละอำเภอ (โพนทองเรณู) ออกจริง")


def test_company_stats():
    c = _fixture_conn(); tk = ["ถนน"]
    s = ci.company_stats("หจก.A", tk, c)   # 2 งาน disc 5,8 → median 6.5, ไม่มี IQR
    assert s["games"] == 2 and s["median"] == 6.5 and s["p25"] is None, s
    assert ci.company_stats("หจก.D", tk, c)["games"] == 0   # เฉพาะเจาะจง → competitive filter ตัด
    print("✅ company_stats")


def test_confidence_label():
    assert ci.confidence_label(40, 5, 10).startswith("🟢")
    assert ci.confidence_label(15, 5, 10).startswith("🟡")
    assert ci.confidence_label(40, 5, 30).startswith("🟡")
    assert ci.confidence_label(5, None, None).startswith("🔴")
    print("✅ confidence_label")


def test_intel_lines():
    c = _fixture_conn()   # ไม่มี project_locations → resolve degrade province (graceful)
    out = ci.intel_lines("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", conn=c)
    assert out and out[0].startswith("💡 ราคาอ้างอิง (งานถนน"), out
    assert "🏆 คู่แข่งแถบนี้:" in out and any("หจก." in l for l in out), out
    assert any(l.startswith("📊 ภาพรวม") for l in out) and any(l[0] in "🟢🟡🔴" for l in out), out
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", conn=c) == []
    assert ci.intel_lines("เชียงใหม่", "ก่อสร้างถนน", conn=c) == []
    print("✅ intel_lines")


def test_wiring_format_notification():
    import Sebastian_LINE_Sender as ls
    import cgd_intel as _ci
    orig = _ci.intel_lines
    _ci.intel_lines = lambda *a, **k: ["💡 TEST INTEL", "🏆 คู่แข่งแถบนี้:"]
    txt = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                 source_stage="followed_bid_open")
    assert "💡 TEST INTEL" in txt and "🔑 P1" in txt and "━" in txt, txt
    _ci.intel_lines = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    txt2 = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="followed_bid_open")
    assert "🔑 P1" in txt2 and "💡" not in txt2, txt2
    _ci.intel_lines = lambda *a, **k: ["💡 SHOULD NOT APPEAR"]
    txt3 = ls.format_notification("P2", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="api_enriched")
    assert "💡" not in txt3, txt3
    _ci.intel_lines = orig
    print("✅ wiring format_notification")


if __name__ == "__main__":
    test_match_keywords()
    test_resolve_location_geo()
    test_resolve_location_fallbacks()
    test_select_competitors()
    test_golden_amphoe_better_than_province()
    test_company_stats()
    test_confidence_label()
    test_intel_lines()
    test_wiring_format_notification()
    print("ALL PASS (moi location disambiguation)")
