"""test_water_subtype.py — แยก reference set คาดราคางานแหล่งน้ำ (ขุด vs โครงสร้าง).
requirement กัญจน์ 2026-06-11: gap %ลด 26 จุด (ขุดลอก ~37% vs ฝาย/ประปา ~10-13%) → ห้าม pool
(evidence: data/subtype_variance_report.json). excavation ชนะ structure ('ขุดลอกอ่างเก็บน้ำ' = งานขุด)."""
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
    rows = [  # ต.โพนทอง อ.บ้านแพง นครพนม — งานขุด (ลดลึก) ปนงานโครงสร้าง (ลดตื้น)
        ("E1", "ขุดลอกคลองสาธารณะ ต.โพนทอง", "หจก.ดิน", 38.0),
        ("E2", "ขุดสระเก็บน้ำ บ้านโพนทอง", "หจก.ดิน", 42.0),
        ("S1", "ก่อสร้างฝาย ต.โพนทอง", "หจก.โครง", 10.0),
        ("S2", "ก่อสร้างระบบประปาหมู่บ้าน โพนทอง", "หจก.โครง", 13.0),
        ("X1", "ขุดลอกอ่างเก็บน้ำ โพนทอง", "หจก.ดิน", 35.0),   # มีทั้งขุด+อ่าง → ขุดชนะ
    ]
    for pid, name, win, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", name, win, 100000, disc, "2567", EB, "บ้านแพง", "โพนทอง"))
    c.commit(); return c


def test_classifier():
    assert ci.water_subtype("ขุดลอกคลองสาธารณะ") == "water_excav"
    assert ci.water_subtype("ขุดสระเก็บน้ำ") == "water_excav"
    assert ci.water_subtype("ก่อสร้างฝาย") == "water_struct"
    assert ci.water_subtype("ก่อสร้างระบบประปาหมู่บ้าน") == "water_struct"
    assert ci.water_subtype("ขุดลอกอ่างเก็บน้ำ") == "water_excav"   # excavation ชนะ structure
    assert ci.water_subtype("ก่อสร้างถนน คสล.") is None
    assert ci.water_subtype("จัดซื้อรถยนต์") is None
    assert ci.water_subtype("") is None
    print("✅ water_subtype classifier (excavation-precedence)")


def test_fetch_subtype_filter():
    c = _conn(); tk = ["น้ำ", "ฝาย", "ขุด", "ประปา"]   # OR-match ครอบทุกแถวทดสอบ
    exc = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", subtype="water_excav")
    assert {r["winner"] for r in exc} == {"หจก.ดิน"}, exc           # เฉพาะงานขุด (+ขุดลอกอ่าง)
    assert {r["discount_pct"] for r in exc} == {38.0, 42.0, 35.0}, exc
    st = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", subtype="water_struct")
    assert {r["winner"] for r in st} == {"หจก.โครง"}, st            # ฝาย/ประปา (ไม่เอาขุดลอกอ่าง)
    assert {r["discount_pct"] for r in st} == {10.0, 13.0}, st
    pooled = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง")  # subtype=None → เดิม
    assert {r["winner"] for r in pooled} == {"หจก.ดิน", "หจก.โครง"}, pooled
    print("✅ _fetch subtype filter (excav/struct/pool back-compat)")


def test_build_intel_subtype():
    c = _conn(); tk = ["ฝาย", "ประปา"]
    # งานฝาย → อ้างอิงเฉพาะ struct (~10-13%) ไม่เจือจางด้วยงานขุด (~38%)
    ctx = ci._build_intel(c, "นครพนม", tk, "", None, 1000000, subtype="water_struct",
                          contested_only=False)
    assert ctx is not None, "struct ควรมี intel"
    txt = "\n".join(ctx["lines"])
    assert "หจก.โครง" in txt and "หจก.ดิน" not in txt, txt
    pred = ctx["prediction"]
    assert pred and pred["area_disc_hi"] <= 20, pred   # struct ลดตื้น ไม่ทะลุ 20%
    print("✅ _build_intel subtype (struct อ้างอิง struct อย่างเดียว)")


def test_contested_floor_subtype_aware():
    # water_struct แข่งจริงเริ่ม ~5% (ฝาย/ประปา) — floor ต้องต่ำกว่าถนน/ขุด
    assert ci._contested_floor("water_struct") == 5, "struct floor ต้อง 5"
    assert ci._contested_floor("water_excav") == 15, "excav ใช้ default 15"
    assert ci._contested_floor("concrete") == 15
    assert ci._contested_floor(None) == 15
    # contested filter ใช้ floor ต่อ subtype: struct เก็บงาน 10-13% ไว้ (ถ้าใช้ 15 จะหาย)
    c = _conn(); tk = ["ฝาย", "ประปา"]
    st = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง",
                   subtype="water_struct", contested_only=True)
    assert {r["discount_pct"] for r in st} == {10.0, 13.0}, st   # floor=5 → เก็บทั้งคู่
    print("✅ contested floor subtype-aware (struct=5, อื่น=15)")


def test_intel_context_end_to_end():
    c = _conn()
    # ผ่าน production entry: intel_context คำนวณ subtype จาก project_name เอง
    ctx = ci.intel_context("นครพนม", "ขุดลอกคลองสาธารณะ ต.โพนทอง", "", "", 1000000, c)
    assert ctx is not None, ctx
    txt = "\n".join(ctx["lines"])
    assert "หจก.ดิน" in txt and "หจก.โครง" not in txt, txt   # งานขุดไม่ดึงงานโครงสร้าง
    print("✅ intel_context subtype (end-to-end excavation)")


if __name__ == "__main__":
    test_classifier()
    test_fetch_subtype_filter()
    test_build_intel_subtype()
    test_contested_floor_subtype_aware()
    test_intel_context_end_to_end()
    print("\n✅ ALL test_water_subtype PASS")
