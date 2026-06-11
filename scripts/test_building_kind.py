"""test_building_kind.py — แยกอาคาร สร้างใหม่ vs ปรับปรุง/ซ่อม (เฉพาะอาคาร).
requirement กัญจน์ 2026-06-12: ปรับปรุง median 17.8% vs สร้างใหม่ 12.4% (gap +5.4). scope เฉพาะอาคาร
(research: ถนน/น้ำ เทรนด์กลับด้าน). อาคารเช็คก่อน road/water — กันอาคารคอนกรีตเป็น concrete road."""
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
    rows = [  # อ.บ้านแพง — อาคารสร้างใหม่ (ลดตื้น) ปน อาคารปรับปรุง (ลดลึก)
        ("N1", "ก่อสร้างอาคารสำนักงาน อบต. โพนทอง", "หจก.ใหม่1", 12.0),
        ("N2", "ก่อสร้างอาคารศูนย์พัฒนาเด็กเล็ก โพนทอง", "หจก.ใหม่2", 11.0),
        ("R1", "ปรับปรุงอาคารสำนักงานเกษตร บ้านแพง", "หจก.ปรับ1", 26.0),
        ("R2", "ซ่อมแซมอาคารที่ว่าการอำเภอบ้านแพง", "หจก.ปรับ2", 24.0),
    ]
    for pid, name, win, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,dept,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", "อบต.โพนทอง", name, win, 100000, disc, "2567", EB, "บ้านแพง", "โพนทอง"))
    c.commit(); return c


def test_classifier():
    assert ci.building_kind("ก่อสร้างอาคารสำนักงาน อบต. (หลังใหม่)") == "bld_new"
    assert ci.building_kind("ปรับปรุงอาคารสำนักงาน") == "bld_reno"
    assert ci.building_kind("ซ่อมแซมหอประชุมที่ว่าการอำเภอ") == "bld_reno"
    assert ci.building_kind("ก่อสร้างถนนคอนกรีตเสริมเหล็ก") is None      # ไม่ใช่อาคาร
    assert ci.building_kind("ขุดลอกคลอง") is None
    assert ci.building_kind("") is None
    print("✅ building_kind classifier (bld_new/bld_reno/None)")


def test_precedence_over_road():
    # อาคารคอนกรีต → bld_new (ไม่ใช่ concrete road) เพราะ building_kind เช็คก่อนใน intel_context
    assert ci.building_kind("ก่อสร้างอาคารสำนักงานคอนกรีตเสริมเหล็ก") == "bld_new"
    assert ci.road_subtype("ก่อสร้างอาคารสำนักงานคอนกรีตเสริมเหล็ก") == "concrete"  # road เดี่ยวจับ
    # chain ใน intel_context: building_kind ก่อน → ชนะ
    sub = ci.building_kind("ก่อสร้างอาคารสำนักงานคอนกรีต") or ci.road_subtype("ก่อสร้างอาคารสำนักงานคอนกรีต")
    assert sub == "bld_new", sub
    print("✅ อาคารคอนกรีต → bld_new (precedence เหนือ concrete road)")


def test_fetch_filter():
    c = _conn(); tk = ["อาคาร"]
    new = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", subtype="bld_new")
    assert {r["discount_pct"] for r in new} == {12.0, 11.0}, new       # สร้างใหม่เท่านั้น
    reno = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", subtype="bld_reno")
    assert {r["discount_pct"] for r in reno} == {26.0, 24.0}, reno     # ปรับปรุงเท่านั้น
    print("✅ _fetch filter (bld_new/bld_reno)")


def test_end_to_end():
    c = _conn()
    # งานอาคารสำนักงานใหม่ → อ้างอิงเฉพาะสร้างใหม่ (~11-12%) ไม่เอาปรับปรุง (~24-26%)
    ctx = ci.intel_context("นครพนม", "ก่อสร้างอาคารสำนักงาน อบต.โพนทอง (หลังใหม่)",
                           "องค์การบริหารส่วนตำบลโพนทอง", "", 5000000, c)
    assert ctx is not None, ctx
    txt = "\n".join(ctx["lines"])
    assert "หจก.ปรับ" not in txt, txt   # งานสร้างใหม่ไม่ดึงงานปรับปรุง
    pred = ctx["prediction"]
    assert pred and pred["area_disc_hi"] <= 18, pred   # สร้างใหม่ลดตื้น ไม่ทะลุงานปรับปรุง
    print("✅ intel_context (อาคารใหม่ อ้างอิงสร้างใหม่อย่างเดียว)")


if __name__ == "__main__":
    test_classifier()
    test_precedence_over_road()
    test_fetch_filter()
    test_end_to_end()
    print("\n✅ ALL test_building_kind PASS")
