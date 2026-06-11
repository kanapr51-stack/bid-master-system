"""test_repredict_followed.py — งาน 3: re-predict งานปักหมุดด้วย logic ใหม่ (dry-run / apply).
ยืนยัน: dry-run ไม่เขียน · apply เขียน prediction ใหม่ · ไม่แตะ verified_at."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import init_schema, get_connection, save_prediction, get_prediction
import repredict_followed as rp

EB = "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"


def _seed():
    init_schema()
    with get_connection() as c:
        c.execute("INSERT INTO followed_jobs (customer_id,project_id,starred_at,starred_stage,"
                  "last_stage_notified,status) VALUES (1,'PF1','t','D0','D0','active')")
        c.execute("INSERT INTO projects_seen (project_id,announce_type,province,budget,project_name,"
                  "dept_name,first_seen_at) VALUES ('PF1','D0','นครพนม',1000000,"
                  "'ก่อสร้างถนน คสล. ต.โพนทอง','องค์การบริหารส่วนตำบลโพนทอง','t')")
        # local อบต/เทศบาล (ลด 28-32%) ปน กรมทางหลวง (ลด 0.3-0.5%) — logic ใหม่ต้องตัด DOH ออก
        ref = [("องค์การบริหารส่วนตำบลโพนทอง", 30), ("องค์การบริหารส่วนตำบลโพนทอง", 28),
               ("เทศบาลตำบลโพนทอง", 32), ("แขวงทางหลวงนครพนม", 0.3), ("กรมทางหลวงชนบท", 0.5)]
        for i, (dept, disc) in enumerate(ref):
            c.execute("INSERT INTO cgd_winners (project_id,province,dept,project_name,winner,win_price,"
                      "discount_pct,fiscal_year,proc_type,district,subdistrict) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (f"R{i}", "นครพนม", dept, "ก่อสร้างถนน คสล. ต.โพนทอง", f"W{i}",
                       700000, disc, "2567", EB, "บ้านแพง", "โพนทอง"))
    # prediction เดิม (logic เก่า pool รวม DOH → ค่ากลางสูงผิด 850k) + verified ไว้
    save_prediction({"project_id": "PF1", "budget": 1000000, "area_disc_lo": 5, "area_disc_hi": 30,
                     "area_price_lo": 700000, "area_price_hi": 950000,
                     "area_disc_med": 15, "area_price_med": 850000})


def test_dry_run_no_write():
    _seed()
    before = get_prediction("PF1")["area_price_med"]
    summ = rp.run(apply=False)
    after = get_prediction("PF1")["area_price_med"]
    assert before == after == 850000, (before, after)        # dry-run ไม่เขียน
    assert summ["changed"] == 1, summ                          # เห็นว่าจะเปลี่ยน
    print("✅ dry-run ไม่เขียน + เห็นว่าจะเปลี่ยน")


def test_apply_writes_new_logic():
    summ = rp.run(apply=True)
    p = get_prediction("PF1")
    # logic ใหม่ market=local → อ้างอิงเฉพาะ อบต/เทศบาล (ลด ~30%) → ค่ากลาง ~700k ไม่ใช่ 850k
    assert p["area_price_med"] < 800000, p["area_price_med"]
    assert p["verified_at"] is None, "ต้องไม่แตะ verified_at"   # save_prediction อัปเฉพาะ prediction
    assert summ["applied"] == 1, summ
    print("✅ apply เขียน logic ใหม่ (local-only ~700k) + ไม่แตะ verified")


if __name__ == "__main__":
    test_dry_run_no_write()
    test_apply_writes_new_logic()
    print("\n✅ ALL test_repredict_followed PASS")
