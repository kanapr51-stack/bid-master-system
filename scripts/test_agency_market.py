"""test_agency_market.py — แยก reference pool ตามระบอบตลาด/หน่วยงาน (ท้องถิ่น vs ส่วนกลาง).
requirement กัญจน์ 2026-06-11: ตัวขับ %ส่วนลด = ระบอบตลาด (ท้องถิ่นแข่งดุ ~28% vs กรมทางหลวงชิดเพดาน ~0.3%)
ไม่ใช่ budget/ชั้น (evidence: docs/research_market_regime_discount.md). งานท้องถิ่นต้องอ้างอิงงานท้องถิ่นเท่านั้น."""
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
    rows = [  # ต.โพนทอง — งานถนนท้องถิ่น (แข่งดุ) ปนงานกรมทางหลวง (ชิดเพดาน)
        ("L1", "องค์การบริหารส่วนตำบลโพนทอง", "ก่อสร้างถนน คสล. ต.โพนทอง", "หจก.ท้องถิ่น1", 30.0),
        ("L2", "เทศบาลตำบลโพนทอง", "ถนน คสล. สายโพนทอง", "หจก.ท้องถิ่น2", 28.0),
        ("P1", "องค์การบริหารส่วนจังหวัดนครพนม", "ก่อสร้างถนน คสล. โพนทอง", "หจก.อบจ", 2.0),
        ("D1", "แขวงทางหลวงนครพนม", "ปรับปรุงผิวทางถนน คสล. โพนทอง", "หจก.ทางหลวง1", 0.3),
        ("D2", "กรมทางหลวงชนบท", "ก่อสร้างถนน คสล. โพนทอง", "หจก.ทางหลวง2", 0.5),
    ]
    for pid, dept, name, win, disc in rows:
        c.execute("INSERT INTO cgd_winners (project_id,province,dept,project_name,winner,win_price,"
                  "discount_pct,fiscal_year,proc_type,district,subdistrict) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (pid, "นครพนม", dept, name, win, 100000, disc, "2567", EB, "บ้านแพง", "โพนทอง"))
    c.commit(); return c


def test_classifier():
    assert ci.agency_market("องค์การบริหารส่วนตำบลบ้านแพง") == "local"
    assert ci.agency_market("เทศบาลตำบลพรเจริญ") == "local"
    assert ci.agency_market("องค์การบริหารส่วนจังหวัดบึงกาฬ") == "provincial"   # อบจ. คนละระบอบ
    assert ci.agency_market("กรมทางหลวง") == "central"
    assert ci.agency_market("แขวงทางหลวงนครพนมที่ 1") == "central"
    assert ci.agency_market("กรมชลประทาน") == "central"
    assert ci.agency_market("มหาวิทยาลัยนครพนม") == "central"
    assert ci.agency_market("") is None
    assert ci.agency_market(None) is None
    print("✅ agency_market classifier (local / provincial(อบจ) / central / None)")


def test_fetch_market_filter():
    c = _conn(); tk = ["ถนน"]
    loc = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", market="local")
    assert {r["winner"] for r in loc} == {"หจก.ท้องถิ่น1", "หจก.ท้องถิ่น2"}, loc
    assert {r["discount_pct"] for r in loc} == {30.0, 28.0}, loc            # อบต/เทศบาล เท่านั้น
    prov = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", market="provincial")
    assert {r["winner"] for r in prov} == {"หจก.อบจ"}, prov                 # อบจ. แยกออกมา
    assert {r["discount_pct"] for r in prov} == {2.0}, prov
    cen = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง", market="central")
    assert {r["winner"] for r in cen} == {"หจก.ทางหลวง1", "หจก.ทางหลวง2"}, cen  # ไม่รวม อบจ.
    pooled = ci._fetch(c, "นครพนม", tk, subdistrict="โพนทอง", district="บ้านแพง")  # market=None → เดิม
    assert len(pooled) == 5, pooled
    print("✅ _fetch market filter (local/provincial/central/pool back-compat)")


def test_build_intel_market():
    c = _conn(); tk = ["ถนน"]
    # งานท้องถิ่น → อ้างอิงเฉพาะท้องถิ่น (~26-30%) ไม่เจือจางด้วยกรมทางหลวง (~0.3%)
    ctx = ci._build_intel(c, "นครพนม", tk, "", None, 1000000, market="local", contested_only=False)
    assert ctx is not None, "local ควรมี intel"
    pred = ctx["prediction"]
    assert pred and pred["area_disc_lo"] >= 20, pred    # ท้องถิ่นลดลึก ไม่ถูก DOH ดึงลง
    print("✅ _build_intel market (local อ้างอิง local อย่างเดียว)")


def test_intel_context_end_to_end():
    c = _conn()
    # production entry: intel_context คำนวณ market จาก dept_name เอง
    ctx = ci.intel_context("นครพนม", "ก่อสร้างถนน คสล. ต.โพนทอง",
                           "องค์การบริหารส่วนตำบลโพนทอง", "", 1000000, c)
    assert ctx is not None, ctx
    txt = "\n".join(ctx["lines"])
    assert "หจก.ทางหลวง" not in txt, txt   # งานท้องถิ่นไม่ดึงงานกรมทางหลวง
    print("✅ intel_context market (end-to-end local ไม่ดึง DOH)")


if __name__ == "__main__":
    test_classifier()
    test_fetch_market_filter()
    test_build_intel_market()
    test_intel_context_end_to_end()
    print("\n✅ ALL test_agency_market PASS")
