"""test_lookup_company.py — pure stats ของ company profiler (จำแนกวิธี/หมวด/สถิติ/กรอง bad row)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import lookup_company as lc


def test_q_term_strips_legal_prefix():
    assert lc._q_term("ห้างหุ้นส่วนจำกัด หนองหว้า การก่อสร้าง") == "หนองหว้า การก่อสร้าง"
    assert lc._q_term("บริษัท ก ข ค จำกัด") == "ก ข ค จำกัด"
    assert lc._q_term("หจก.ทดสอบ") == "ทดสอบ"
    print("✅ _q_term strips legal prefix")


def test_method_and_category():
    assert lc._method("ประกวดราคาจ้างก่อสร้างถนน...") == "competitive"
    assert lc._method("จ้างซ่อมแซมห้องเรียน โดยวิธีเฉพาะเจาะจง") == "direct"
    assert lc._method("จ้างปรับปรุงอาคาร โดยวิธีเฉพาะ") == "direct"
    assert lc._method("อื่นๆไม่รู้") == "other"
    assert lc._category("ก่อสร้างถนนคอนกรีตเสริมเหล็ก") == "ถนน"
    assert lc._category("ก่อสร้างระบบบำบัดน้ำเสีย") == "น้ำ"
    assert lc._category("ปรับปรุงซ่อมแซมอาคารเรียน") == "อาคาร"
    print("✅ _method + _category")


def _job(pid, yr, prov, budget, agree, name):
    return {"pid": pid, "yr": yr, "prov": prov, "budget": budget, "agree": agree,
            "name": name, "dept": ""}


def test_compute_profile():
    jobs = [
        _job("1", "2566", "สระแก้ว", 1000000, 900000, "ประกวดราคาจ้างก่อสร้างถนน"),     # comp ลด10%
        _job("2", "2566", "สระแก้ว", 500000, 425000, "ประกวดราคาจ้างก่อสร้างอาคาร"),     # comp ลด15%
        _job("3", "2567", "อุดรธานี", 200000, 200000, "จ้างซ่อมแซม โดยวิธีเฉพาะเจาะจง"),  # direct 0%
        _job("4", "2559", "สระแก้ว", 500000, 856000, "จ้างถนนลูกรัง โดยวิธีเฉพาะ"),       # bad: ตกลง>งบ
    ]
    p = lc.compute_profile(jobs)
    assert p["total_wins"] == 4, p
    assert p["year_min"] == "2559" and p["year_max"] == "2567", p
    assert p["home_province"] == "สระแก้ว", p["by_province"]
    assert p["by_province"]["สระแก้ว"] == 3, p["by_province"]
    assert p["by_method"]["competitive"] == 2 and p["by_method"]["direct"] == 2, p["by_method"]
    # discount แยก: competitive 2 งาน (10,15 → median 12.5), direct ที่ valid = งาน#3 (0%)
    assert p["competitive_disc"]["n"] == 2 and abs(p["competitive_disc"]["median"] - 12.5) < 0.01, p["competitive_disc"]
    assert p["bad_rows"] == 1, p   # งาน#4 ตกลง>งบ → bad
    # total value = sum ราคาตกลง
    assert p["total_value"] == 900000 + 425000 + 200000 + 856000, p["total_value"]
    print("✅ compute_profile (aggregation/method-split/bad-row filter)")


def test_compute_profile_empty():
    p = lc.compute_profile([])
    assert p["total_wins"] == 0 and p["home_province"] is None, p
    print("✅ compute_profile empty")


test_q_term_strips_legal_prefix()
test_method_and_category()
test_compute_profile()
test_compute_profile_empty()
print("ALL PASS lookup_company")
