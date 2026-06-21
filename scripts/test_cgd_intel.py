"""test_cgd_intel.py — competitor-profile intel + location disambiguation (resolve→select→lines)."""
import os, sys, sqlite3, csv; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("BMS_FOLLOW_SECRET", "test-secret-cgd-intel")
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


def _contested_conn():
    """fixture: ตำบลนาทม งานก่อสร้างคอนกรีต ส่วนลดผสม no-competition(2,8) + contested(25,32,35,38)."""
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    data = [("C1", "หจก.ก", 2.0), ("C2", "หจก.ข", 8.0), ("C3", "หจก.ค", 25.0),
            ("C4", "หจก.ง", 32.0), ("C5", "หจก.จ", 35.0), ("C6", "หจก.ฉ", 38.0)]
    for pid, win, disc in data:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", "จ้างก่อสร้างถนนคอนกรีตเสริมเหล็ก ตำบลนาทม", win,
                   500000, disc, "2568", EB, "นาทม", "นาทม"))
    c.commit(); return c


def test_fetch_contested_only():
    """contested_only=True → ตัดงานไม่มีคู่แข่ง (ลด < CONTESTED_MIN_DISCOUNT) ออก."""
    c = _contested_conn()
    allrows = ci._fetch(c, "นครพนม", ["คอนกรีต"], district="นาทม")
    assert len(allrows) == 6, allrows
    cont = ci._fetch(c, "นครพนม", ["คอนกรีต"], district="นาทม", contested_only=True, subtype="concrete")
    assert all(r["discount_pct"] >= ci.CONTESTED_MIN_DISCOUNT for r in cont), cont   # ถนน floor=15
    assert len(cont) == 4, cont                  # 25,32,35,38 (ตัด 2,8)
    print("✅ _fetch contested_only (ตัดงานไม่มีคู่แข่ง)")


def test_predict_includes_median():
    """predict_winning_price + predict_lines มีค่าปกติ (median) สำหรับ framing 'ปกติ ~X%'."""
    p = ci.predict_winning_price(1000000, 31, 42, area_median=35)
    assert p["area_disc_med"] == 35, p
    assert p["area_price_med"] == round(1000000 * (1 - 35 / 100)), p
    lines = ci.predict_lines(p)
    assert any("~50%" in ln for ln in lines), lines   # median = rung โอกาสชนะ 50%
    print("✅ predict median (rung 50%)")


def test_build_intel_contested_focus():
    """_build_intel(contested_only=True) → บล็อก+คาดราคา ใช้เฉพาะงานแข่งจริง + ป้าย."""
    c = _contested_conn()
    ctx = ci._build_intel(c, "นครพนม", ["คอนกรีต"], "นาทม", "นาทม", 1000000,
                          "concrete", "construction", contested_only=True)
    assert ctx and ctx["prediction"], ctx
    assert ctx["prediction"]["area_disc_lo"] >= ci.CONTESTED_MIN_DISCOUNT, ctx["prediction"]
    txt = "\n".join(ctx["lines"])
    assert "แข่งจริง" in txt, txt
    print("✅ _build_intel contested-focus + label")


def test_fetch_matches_location_by_name_despite_wrong_column():
    """คอลัมน์ district/subdistrict (geocode จากพิกัด) เพี้ยน — snap ไปอำเภอเมือง.
    งานชื่อ 'ตำบลนาทม อำเภอนาทม' ถูก tag column='เมืองนครพนม/ในเมือง' → ต้อง match จากชื่องาน
    (ground truth) ไม่งั้น intel จับคู่พื้นที่ไม่เจอ (bug งาน 69059327097)."""
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    # ชื่อระบุนาทม ถูก แต่ column เพี้ยนเป็นเมืองนครพนม
    c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
              "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
              ("M1", "นครพนม", "ก่อสร้างถนน คสล. บ้านดงสว่าง ตำบลนาทม อำเภอนาทม จังหวัดนครพนม",
               "หจก.นาทม", 800000, 15.0, "2568", EB, "เมืองนครพนม", "ในเมือง"))
    # งานที่ column ถูก (ไม่ได้ระบุตำบลในชื่อ) → ต้องยังเจอจาก column (belt-and-suspenders)
    c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
              "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
              ("M2", "นครพนม", "ก่อสร้างถนน คสล. หมู่ 5", "หจก.คอลัมน์",
               700000, 12.0, "2568", EB, "นาทม", "นาทม"))
    c.commit()
    arows = ci._fetch(c, "นครพนม", ["ถนน"], district="นาทม")
    assert {r["winner"] for r in arows} == {"หจก.นาทม", "หจก.คอลัมน์"}, arows  # name OR column
    trows = ci._fetch(c, "นครพนม", ["ถนน"], subdistrict="นาทม", district="นาทม")
    assert {r["winner"] for r in trows} == {"หจก.นาทม", "หจก.คอลัมน์"}, trows
    print("✅ _fetch matches location by name (geocode column เพี้ยน)")


def test_work_nature():
    """แยกลักษณะงาน: 'ซื้อ' (วัสดุ) vs 'จ้างก่อสร้าง'. งานซื้อลด ~0-2%, งานจ้างลด ~25-38% — คนละ pool."""
    assert ci.work_nature("ประกวดราคาซื้อคอนกรีตผสมเสร็จ และอื่นๆ ฝายห้วยหลวง") == "purchase"
    assert ci.work_nature("ประกวดราคาซื้อเหล็กเส้นเสริมคอนกรีต งานอาคารบังคับน้ำ") == "purchase"
    assert ci.work_nature("ประกวดราคาจ้างก่อสร้างถนนคอนกรีตเสริมเหล็ก") == "construction"
    assert ci.work_nature("ก่อสร้างถนน คสล. หมู่ 5") == "construction"   # ไม่มี ซื้อ
    print("✅ work_nature (ซื้อ=purchase, จ้าง=construction)")


def test_fetch_filters_work_nature():
    """reference ต้องตรงลักษณะงาน — งานก่อสร้างถนนไม่เอางาน 'ซื้อคอนกรีต' มาปน (กัน range เพี้ยน)."""
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    rows = [
        ("J1", "ประกวดราคาจ้างก่อสร้างถนนคอนกรีตเสริมเหล็ก ตำบลนาทม", "หจก.จ้าง", 30.0),
        ("S1", "ประกวดราคาซื้อคอนกรีตผสมเสร็จ ฝายห้วยหลวง ตำบลนาทม", "หจก.ซื้อ", 2.0),
    ]
    for pid, nm, win, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", nm, win, 500000, disc, "2568", EB, "นาทม", "นาทม"))
    c.commit()
    cons = ci._fetch(c, "นครพนม", ["คอนกรีต"], district="นาทม", nature="construction")
    assert {r["winner"] for r in cons} == {"หจก.จ้าง"}, cons    # ตัดงานซื้อออก
    pur = ci._fetch(c, "นครพนม", ["คอนกรีต"], district="นาทม", nature="purchase")
    assert {r["winner"] for r in pur} == {"หจก.ซื้อ"}, pur
    both = ci._fetch(c, "นครพนม", ["คอนกรีต"], district="นาทม")    # None = back-compat
    assert {r["winner"] for r in both} == {"หจก.จ้าง", "หจก.ซื้อ"}, both
    print("✅ _fetch filters by work_nature (construction ตัดงานซื้อ)")


def test_fetch_matches_abbreviated_location():
    """ชื่องานบางงานเขียนย่อ 'ต.นาทม อ.นาทม' (ไม่ใช่ 'ตำบล/อำเภอ' เต็ม) — LIKE ต้องจับทั้งสองแบบ."""
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
              "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
              ("A1", "นครพนม", "ก่อสร้างถนน คสล. หมู่ 3 ต.นาทม อ.นาทม จ.นครพนม", "หจก.ย่อ",
               800000, 16.0, "2568", EB, "เมืองนครพนม", "ในเมือง"))  # column เพี้ยน + ชื่อย่อ
    c.commit()
    arows = ci._fetch(c, "นครพนม", ["ถนน"], district="นาทม")
    assert {r["winner"] for r in arows} == {"หจก.ย่อ"}, arows
    trows = ci._fetch(c, "นครพนม", ["ถนน"], subdistrict="นาทม", district="นาทม")
    assert {r["winner"] for r in trows} == {"หจก.ย่อ"}, trows
    print("✅ _fetch matches abbreviated ต./อ.")


def _old_years_conn():
    """fixture: ตำบลนาทม มีงาน competitive เฉพาะปีเก่า (2563,2564) ไม่มีใน 3 ปีล่าสุด."""
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT,
        dept TEXT, project_name TEXT, winner TEXT, winner_tin TEXT, budget INTEGER,
        win_price INTEGER, discount_pct REAL, announce_date TEXT, fiscal_year TEXT,
        proc_type TEXT, district TEXT, subdistrict TEXT, synced_at TEXT)""")
    EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    rows = [
        ("O1", "ถนน คสล. ตำบลนาทม อำเภอนาทม", "หจก.เก่า1", 800000, 20.0, "2563"),
        ("O2", "ถนน คสล. ตำบลนาทม อำเภอนาทม", "หจก.เก่า2", 750000, 25.0, "2564"),
    ]
    for pid, pname, win, wp, disc, fy in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", pname, win, wp, disc, fy, EB, "นาทม", "นาทม"))
    c.commit(); return c


def test_fetch_include_old_years():
    """พื้นที่ข้อมูลน้อย: 3 ปีล่าสุดไม่มีงาน แต่ย้อนลึกเจอ → include_old=True ดึงทุกปีงบ."""
    c = _old_years_conn()
    recent = ci._fetch(c, "นครพนม", ["ถนน"], district="นาทม")          # default = 3 ปีล่าสุด
    assert recent == [], recent
    allyears = ci._fetch(c, "นครพนม", ["ถนน"], district="นาทม", include_old=True)
    assert {r["winner"] for r in allyears} == {"หจก.เก่า1", "หจก.เก่า2"}, allyears
    print("✅ _fetch include_old (ย้อนลึกกว่า 3 ปี)")


def test_build_intel_old_data_label():
    """พื้นที่มีแต่ข้อมูลเก่า → ยังคาดราคาได้ + ติดป้าย 'รวมข้อมูลเก่า' ให้ผู้ใช้รู้."""
    c = _old_years_conn()
    ctx = ci._build_intel(c, "นครพนม", ["ถนน"], "นาทม", "นาทม", 1000000)
    assert ctx is not None, "ต้องไม่ None — มีข้อมูลเก่าให้คาดได้"
    assert ctx["prediction"] is not None, ctx
    txt = "\n".join(ctx["lines"])
    assert "ข้อมูลเก่า" in txt, txt
    print("✅ _build_intel ติดป้ายข้อมูลเก่าเมื่อ fallback ปีเก่า")


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
    assert "อิงตำบล" in L and "แนะนำราคายื่น" in L, L              # คาดอิงตำบล + headline ใหม่
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
    assert any("แนะนำราคายื่น" in l for l in lines), lines       # headline ใหม่ (win-objective)
    assert any("โอกาสชนะ ~75%" in l for l in lines), lines       # a/b/c
    assert any("อิงอำเภอ · ลด 8–15%" in l for l in lines), lines
    assert any("บาท" in l for l in lines), lines                # ราคาเป็นบาทเต็ม
    assert any("เจ้าใหญ่" in l for l in lines), lines           # disclaimer คู่แข่ง
    assert ci.predict_lines(None) == []
    print("✅ predict_lines (a/b/c win%)")


def test_scope_stats():
    c = _fixture_conn(); tk = ["ถนน"]
    rows = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง")  # A,A,B (R5 เฉพาะเจาะจงตัด)
    s = ci._company_stats_from_rows(rows, "หจก.A")   # 2 งาน disc 5,8 → median 6.5, ไม่มี IQR
    assert s["games"] == 2 and s["median"] == 6.5 and s["p25"] is None, s
    assert ci._company_stats_from_rows(rows, "หจก.D")["games"] == 0   # ไม่อยู่ใน scope
    lines, p25, p75, n, top, topm, med = ci._scope_block(rows, "🏘 ในตำบลโพนทอง")
    assert n == 3 and lines[0].startswith("🏘 ในตำบลโพนทอง — 3 งาน"), (n, lines[0])
    assert any("หจก.A" in l for l in lines), lines
    assert med is not None, med   # median ของ scope (สำหรับ 'ปกติ' ในคาดราคา)
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
                                 source_stage="followed_bid_open", line_user_id="Uabc")
    # บล็อกวิเคราะห์เต็มย้ายไปหน้า Bid Board แล้ว — ไม่ฝัง text ในข้อความอีก
    assert "💡 TEST INTEL" not in txt and "━" not in txt, txt
    assert "🔑 P1" in txt, txt
    assert "ดูวิเคราะห์ราคา+คู่แข่งบน Bid Board" in txt, txt
    assert "/portal/job?t=" in txt and "pid=P1" in txt, txt
    # ไม่มี line_user_id → ไม่มีลิงก์ (ไม่ error)
    txt_nouser = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                        source_stage="followed_bid_open")
    assert "Bid Board" not in txt_nouser, txt_nouser
    _ci.intel_context = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    txt2 = ls.format_notification("P1", province="นครพนม", project_name="ก่อสร้างถนน",
                                  source_stage="followed_bid_open", line_user_id="Uabc")
    assert "🔑 P1" in txt2 and "💡" not in txt2 and "Bid Board" not in txt2, txt2
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 SHOULD NOT APPEAR"], "prediction": None}
    txt3 = ls.format_notification("P2", province="นครพนม", project_name="ก่อสร้างถนน",
                                  announce_type="B0", source_stage="province_tor_review", line_user_id="Uabc")
    assert "💡" not in txt3 and "Bid Board" not in txt3, txt3   # non-D0 (B0) → ไม่มี intel/link เลย
    # D0 ที่ยังไม่ได้ติดตาม (เจอใหม่) → ต้องมีลิงก์ + หัวข้อ "พบงานเปิดกำหนดวันยื่นซอง"
    _ci.intel_context = lambda *a, **k: {"lines": ["💡 NEW D0 INTEL"], "prediction": None}
    txt4 = ls.format_notification("P3", province="นครพนม", project_name="ก่อสร้างถนน",
                                  announce_type="D0", source_stage="province_qualified", line_user_id="Uabc")
    assert "💡 NEW D0 INTEL" not in txt4, txt4
    assert "Bid Board" in txt4 and "pid=P3" in txt4, txt4
    assert "พบงานเปิดกำหนดวันยื่นซอง" in txt4, txt4
    _ci.intel_context = orig_ctx
    print("✅ wiring format_notification (D0 ทุก stage, ลิงก์ Bid Board แทน intel inline)")


if __name__ == "__main__":
    test_match_keywords()
    test_resolve_location_geo()
    test_resolve_location_fallbacks()
    test_select_competitors()
    test_golden_amphoe_better_than_province()
    test_work_nature()
    test_fetch_filters_work_nature()
    test_fetch_contested_only()
    test_predict_includes_median()
    test_build_intel_contested_focus()
    test_fetch_matches_location_by_name_despite_wrong_column()
    test_fetch_matches_abbreviated_location()
    test_fetch_include_old_years()
    test_build_intel_old_data_label()
    test_build_intel_dual()
    test_intel_context()
    test_predict_winning_price()
    test_predict_lines()
    test_scope_stats()
    test_confidence_label()
    test_intel_lines()
    test_wiring_format_notification()
    print("ALL PASS (moi location disambiguation)")
