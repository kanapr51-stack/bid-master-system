"""test_road_subtype.py — แยก reference set คาดราคาตามประเภทผิวถนน (concrete vs asphalt).
requirement กัญจน์ 2026-06-09: %ลดของ 2 ประเภทต่างกันชัด → ห้าม pool (evidence: probe).
asphalt ชนะ concrete ('แอสฟัลท์ติกคอนกรีต' = ผิวแอสฟัลต์)."""
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
    rows = [  # ตำบลโพนทอง อ.บ้านแพง นครพนม — concrete กับ asphalt ปนกัน
        ("C1", "ก่อสร้างถนน คสล. ต.โพนทอง", "หจก.K", 25.0),
        ("C2", "ถนนคอนกรีตเสริมเหล็ก สายบ้านโพนทอง", "หจก.K", 30.0),
        ("A1", "เสริมผิวถนนแอสฟัลท์ติกคอนกรีต ต.โพนทอง", "หจก.M", 2.0),   # asphaltic concrete = asphalt
        ("A2", "ปรับปรุงถนนลาดยาง โพนทอง", "หจก.M", 5.0),
        ("U1", "ก่อสร้างถนนลูกรัง โพนทอง", "หจก.N", 8.0),              # unknown subtype
    ]
    for pid, name, win, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", name, win, 100000, disc, "2567", EB, "บ้านแพง", "โพนทอง"))
    c.commit(); return c


def test_classifier():
    assert ci.road_subtype("ก่อสร้างถนน คสล. ต.โพนทอง") == "concrete"
    assert ci.road_subtype("ถนนคอนกรีตเสริมเหล็ก") == "concrete"
    assert ci.road_subtype("ปรับปรุงถนนลาดยาง") == "asphalt"
    assert ci.road_subtype("เสริมผิวแอสฟัลท์ติกคอนกรีต") == "asphalt"   # asphalt ชนะ concrete
    assert ci.road_subtype("ก่อสร้างถนนลูกรัง") is None
    assert ci.road_subtype("จัดซื้อรถยนต์") is None
    assert ci.road_subtype("") is None
    print("✅ road_subtype classifier (asphalt-precedence)")


def test_fetch_subtype_filter():
    c = _conn(); tk = ["ถนน"]
    con = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", subtype="concrete")
    assert {r["winner"] for r in con} == {"หจก.K"}, con           # เฉพาะ concrete
    assert {r["discount_pct"] for r in con} == {25.0, 30.0}, con
    asp = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", subtype="asphalt")
    assert {r["winner"] for r in asp} == {"หจก.M"}, asp           # asphalt + asphaltic-concrete
    assert {r["discount_pct"] for r in asp} == {2.0, 5.0}, asp
    pooled = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง")  # subtype=None → เดิม
    assert {r["winner"] for r in pooled} == {"หจก.K", "หจก.M", "หจก.N"}, pooled
    print("✅ _fetch subtype filter (concrete/asphalt/pool back-compat)")


def test_build_intel_subtype():
    c = _conn(); tk = ["ถนน"]
    # concrete job → อ้างอิงเฉพาะ concrete (หจก.K) ไม่เอา asphalt (หจก.M)
    ctx = ci._build_intel(c, "นครพนม", tk, "", None, 1000000, subtype="concrete")
    assert ctx is not None, "concrete ควรมี intel"
    names = [cmp["name"] for ct in ctx["company_tables"] for cmp in ct["companies"]]
    assert "หจก.K" in names and "หจก.M" not in names, names
    pred = ctx["prediction"]
    # discount concrete = {25,30} → area_disc ระหว่าง 25-30 (ไม่เจือจางด้วย asphalt 2-5)
    assert pred and pred["area_disc_lo"] >= 20, pred
    print("✅ _build_intel subtype (concrete อ้างอิง concrete อย่างเดียว)")


def test_intel_context_subtype():
    c = _conn()
    # ผ่าน production entry: intel_context คำนวณ subtype จาก project_name เอง
    ctx = ci.intel_context("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง", "", "", 1000000, c)
    assert ctx is not None, ctx
    names = [cmp["name"] for ct in ctx["company_tables"] for cmp in ct["companies"]]
    assert "หจก.K" in names and "หจก.M" not in names, names   # concrete job ไม่ดึง asphalt
    print("✅ intel_context subtype (end-to-end concrete)")


if __name__ == "__main__":
    test_classifier()
    test_fetch_subtype_filter()
    test_build_intel_subtype()
    test_intel_context_subtype()
    print("\n✅ ALL test_road_subtype PASS")
