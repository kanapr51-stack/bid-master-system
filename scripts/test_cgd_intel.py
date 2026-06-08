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
        ("R7", "นครพนม", "ถนนลาดยาง ไผ่ล้อม", "หจก.C", 600000, 15.0, "2567", EB, "บ้านแพง", "ไผ่ล้อม"),  # อำเภอเดียวกัน ตำบลอื่น
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


def test_build_intel_dual():
    """dual-block: ตำบลโพนทอง(3 งาน A,A,B)<5 → โชว์อำเภอบ้านแพง(4 งาน +C) คู่กัน · คาดอิงตำบล."""
    c = _fixture_conn(); tk = ["ถนน"]
    ctx = ci._build_intel(c, "นครพนม", tk, "โพนทอง", "บ้านแพง", budget=1000000)
    L = "\n".join(ctx["lines"])
    assert ctx["lines"][0].startswith("💡 ราคาอ้างอิง (งานถนน ต.โพนทอง อ.บ้านแพง)"), ctx["lines"][0]
    assert "🏘 ในตำบลโพนทอง" in L and "🏙 ในอำเภอบ้านแพง" in L, L      # 2 บล็อก
    assert "หจก.C" not in L.split("ในอำเภอ")[0], "ตำบลไม่ควรมี C (อยู่ไผ่ล้อม)"  # scope-local ตำบล
    assert "หจก.C" in L, "อำเภอควรมี C"                              # อำเภอรวม ไผ่ล้อม
    assert "หจก.X" not in L, "เรณูนคร ไม่ควรโผล่ (คนละอำเภอ)"
    assert "อิงตำบล" in L and "คาดราคาที่จะชนะ" in L, L              # คาดอิงตำบล
    assert ctx["prediction"] and ctx["prediction"]["area_price_lo"] > 0, ctx["prediction"]
    # ตำบลไม่มีงาน → "ยังไม่มี" + อำเภอยังโชว์
    ctx2 = ci._build_intel(c, "นครพนม", tk, "หนองซน", "บ้านแพง", budget=1000000)
    assert ctx2 and "🏘 ในตำบลหนองซน — ยังไม่มีงานประเภทนี้" in "\n".join(ctx2["lines"]), ctx2
    print("✅ _build_intel dual-block (ตำบล+อำเภอ, scope-local)")


def test_intel_context():
    c = _fixture_conn()
    # ไม่มี project_locations → resolve เป็น province (โพนทอง ambiguous) → block จังหวัด
    ctx = ci.intel_context("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", "", "", 1000000, c)
    assert ctx is not None and ctx["lines"][0].startswith("💡 ราคาอ้างอิง (งานถนน"), ctx
    assert ctx.get("prediction") is not None, ctx                    # มี budget → คาดราคา
    assert ci.intel_context("นครพนม", "จัดซื้อรถยนต์", "", "", 0, c) is None   # ไม่มี work-type
    assert ci.intel_context("เชียงใหม่", "ก่อสร้างถนน", "", "", 0, c) is None   # ไม่มีคู่แข่ง
    print("✅ intel_context")


def test_predict_winning_price():
    p = ci.predict_winning_price(2000000, 8.0, 15.0, "หจก.A", 11.0)
    assert p["area_price_lo"] == 1700000 and p["area_price_hi"] == 1840000, p   # ×(1-.15), ×(1-.08)
    assert p["top_price"] == 1780000, p
    assert ci.predict_winning_price(0, 8, 15, "x", 11) is None              # ไม่มี budget
    assert ci.predict_winning_price(2000000, None, None, None, None) is None  # ไม่มี stat
    print("✅ predict_winning_price")


def test_predict_lines():
    p = ci.predict_winning_price(2100000, 8.0, 15.0, "หจก.ศิรประภา", 11.0)
    lines = ci.predict_lines(p, "อำเภอ")
    assert any("คาดราคาที่จะชนะ" in l for l in lines), lines
    assert any("อิงอำเภอ ลด 8–15%" in l for l in lines), lines   # basis + % ก่อน
    assert any("บาท" in l for l in lines), lines                # ราคาเป็นบาทเต็ม
    assert any("โปรดคำนวณต้นทุน" in l for l in lines), lines    # disclaimer
    assert ci.predict_lines(None) == []
    print("✅ predict_lines")


def test_scope_stats():
    c = _fixture_conn(); tk = ["ถนน"]
    rows = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง")  # A,A,B (R5 เฉพาะเจาะจงตัด)
    s = ci._company_stats_from_rows(rows, "หจก.A")   # 2 งาน disc 5,8 → median 6.5, ไม่มี IQR
    assert s["games"] == 2 and s["median"] == 6.5 and s["p25"] is None, s
    assert ci._company_stats_from_rows(rows, "หจก.D")["games"] == 0   # ไม่อยู่ใน scope
    lines, p25, p75, n, top, topm = ci._scope_block(rows, "🏘 ในตำบลโพนทอง")
    assert n == 3 and lines[0].startswith("🏘 ในตำบลโพนทอง — 3 งาน"), (n, lines[0])
    assert any("หจก.A" in l for l in lines), lines
    print("✅ scope stats + block (scope-local)")


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
    assert any("• หจก." in l for l in out), out                  # มีคู่แข่ง
    assert any("ส่วนลด" in l for l in out), out
    assert ci.intel_lines("นครพนม", "จัดซื้อรถยนต์", conn=c) == []
    assert ci.intel_lines("เชียงใหม่", "ก่อสร้างถนน", conn=c) == []
    print("✅ intel_lines")


def test_wiring_format_notification():
    import Sebastian_LINE_Sender as ls
    import cgd_intel as _ci
    orig_ctx = _ci.intel_context
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 TEST INTEL", "🏘 ในตำบล"], "prediction": None}
    txt = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                 source_stage="followed_bid_open")
    assert "💡 TEST INTEL" in txt and "🔑 P1" in txt and "━" in txt, txt
    _ci.intel_context = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    txt2 = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="followed_bid_open")
    assert "🔑 P1" in txt2 and "💡" not in txt2, txt2
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 SHOULD NOT APPEAR"], "prediction": None}
    txt3 = ls.format_notification("P2", province="นครพนม", project_name="ก่อสร้างถนน",
                                  announce_type="B0", source_stage="province_tor_review")
    assert "💡" not in txt3, txt3   # non-D0 (B0) → ไม่มี intel
    # D0 ที่ยังไม่ได้ติดตาม (เจอใหม่) → ต้องมี intel + หัวข้อ "พบงานเปิดกำหนดวันยื่นซอง"
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 NEW D0 INTEL"], "prediction": None}
    txt4 = ls.format_notification("P3", province="นครพนม", project_name="ก่อสร้างถนน",
                                  announce_type="D0", source_stage="province_qualified")
    assert "💡 NEW D0 INTEL" in txt4 and "พบงานเปิดกำหนดวันยื่นซอง" in txt4, txt4
    _ci.intel_context = orig_ctx
    print("✅ wiring format_notification (D0 ทุก stage)")


if __name__ == "__main__":
    test_match_keywords()
    test_resolve_location_geo()
    test_resolve_location_fallbacks()
    test_select_competitors()
    test_golden_amphoe_better_than_province()
    test_build_intel_dual()
    test_intel_context()
    test_predict_winning_price()
    test_predict_lines()
    test_scope_stats()
    test_confidence_label()
    test_intel_lines()
    test_wiring_format_notification()
    print("ALL PASS (moi location disambiguation)")
