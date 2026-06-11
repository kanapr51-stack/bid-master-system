"""test_work_kind.py — มิติ สร้างใหม่ vs ปรับปรุง/ซ่อม (ตั้งฉากกับ subtype).
requirement กัญจน์ 2026-06-12: ราคาต่างกัน(±)ก็ต้องแยก. local-controlled: อาคาร+5/ถนนคอนกรีต−5/แหล่งน้ำ+3.
scope เฉพาะ อาคาร/ถนน/แหล่งน้ำ (ไฟฟ้า/ราง งานปรับปรุงน้อยเกิน). + fallback กัน pool บางเกิน."""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import cgd_intel as ci

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def test_classifier():
    # อาคาร
    assert ci.work_kind("ก่อสร้างอาคารสำนักงาน (หลังใหม่)") == "new"
    assert ci.work_kind("ปรับปรุงอาคารสำนักงาน") == "reno"
    # ถนน (subtype concrete/asphalt หรือ token ถนน)
    assert ci.work_kind("ก่อสร้างถนนคอนกรีตเสริมเหล็ก", "concrete") == "new"
    assert ci.work_kind("ปรับปรุงถนนลาดยาง", "asphalt") == "reno"
    assert ci.work_kind("ซ่อมสร้างถนนคอนกรีต") == "reno"          # มี token ถนน
    # แหล่งน้ำ
    assert ci.work_kind("ขุดลอกคลอง", "water_excav") == "new"
    assert ci.work_kind("ปรับปรุงฝาย", "water_struct") == "reno"
    # ไฟฟ้า/ราง/อื่น — ไม่ split (None)
    assert ci.work_kind("ปรับปรุงไฟฟ้าส่องสว่าง") is None
    assert ci.work_kind("ก่อสร้างรางระบายน้ำ") is None
    assert ci.work_kind("จัดซื้อรถยนต์") is None
    print("✅ work_kind classifier (อาคาร/ถนน/น้ำ new-reno · ไฟฟ้า/ราง=None)")


def test_building_suppresses_road():
    # อาคารคอนกรีต → is_building → intel_context ตั้ง sub=None (ไม่ใช่ concrete road)
    assert ci.is_building("ก่อสร้างอาคารสำนักงานคอนกรีตเสริมเหล็ก") is True
    assert ci.work_kind("ก่อสร้างอาคารสำนักงานคอนกรีต") == "new"   # อาคาร → splittable
    print("✅ is_building + อาคารคอนกรีต = work_kind new (ไม่ใช่ road)")


def _conn(rows):
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, province TEXT, dept TEXT,
        project_name TEXT, winner TEXT, win_price INT, discount_pct REAL, announce_date TEXT,
        fiscal_year TEXT, proc_type TEXT, district TEXT, subdistrict TEXT)""")
    for i, (name, win, disc) in enumerate(rows):
        c.execute("INSERT INTO cgd_winners (project_id,province,dept,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (f"P{i}", "นครพนม", "อบต.x", name, win, 100000, disc, "2567", EB, "บ้านแพง", "โพนทอง"))
    c.commit(); return c


def test_fetch_filter():
    c = _conn([
        ("ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย A", "W1", 32.0),
        ("ก่อสร้างถนนคอนกรีตเสริมเหล็ก สาย B", "W2", 30.0),
        ("ปรับปรุงถนนคอนกรีตเสริมเหล็ก สาย C", "W3", 26.0),
        ("ซ่อมแซมถนนคอนกรีตเสริมเหล็ก สาย D", "W4", 25.0),
    ])
    tk = ["ถนน"]
    new = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง",
                    subtype="concrete", work_kind="new")
    assert {r["discount_pct"] for r in new} == {32.0, 30.0}, new
    reno = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง",
                     subtype="concrete", work_kind="reno")
    assert {r["discount_pct"] for r in reno} == {26.0, 25.0}, reno
    print("✅ _fetch work_kind filter (new/reno × subtype concrete)")


def test_fallback_thin_pool():
    # new pool บางเกิน (1 งาน < MIN_COMPETITORS=2) → _fetch_scope ผ่อน work_kind → ใช้ pool รวม
    c = _conn([
        ("ก่อสร้างอาคารสำนักงาน A", "W1", 12.0),                 # new เดียว
        ("ปรับปรุงอาคารสำนักงาน B", "W2", 20.0),
        ("ปรับปรุงอาคารสำนักงาน C", "W3", 22.0),
    ])
    rows, _old = ci._fetch_scope(c, "นครพนม", ["อาคาร"], subdistrict="โพนทอง", district="บ้านแพง",
                                 work_kind="new")   # new มี 1 → ผ่อนเป็น pool รวม (3 งาน)
    assert ci._distinct_winners(rows) >= 2, f"ควร fallback เป็น pool รวม: {len(rows)}"
    print("✅ fallback: new pool บางเกิน → ผ่อน work_kind (ไม่คาดจาก 1 งาน)")


if __name__ == "__main__":
    test_classifier()
    test_building_suppresses_road()
    test_fetch_filter()
    test_fallback_thin_pool()
    print("\n✅ ALL test_work_kind PASS")
