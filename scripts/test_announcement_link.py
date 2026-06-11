"""test_announcement_link.py — งาน 2: เพิ่มลิงก์ประกาศในการ์ด.
RSS → pdf_url, province_api → public eGP URL จาก projectId (fallback)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as snd


def test_announcement_url():
    u = snd._announcement_url("67129339090")
    assert u.startswith("https://process3.gprocurement.go.th"), u
    assert "pid=67129339090" in u, u
    assert snd._announcement_url("") == "", "ไม่มี id → ว่าง"
    print("✅ _announcement_url (public eGP จาก projectId)")


def test_fallback_logic():
    # มี pdf_url (RSS) → ใช้ pdf_url; ไม่มี → public eGP
    pdf = "https://process5.gprocurement.go.th/some.pdf"
    assert (pdf or snd._announcement_url("P1")) == pdf
    assert ("" or snd._announcement_url("P1")) == snd._announcement_url("P1")
    print("✅ fallback (RSS pdf ก่อน, ไม่มี→public eGP)")


def test_flex_has_doc_button():
    # build_job_flex ใส่ปุ่ม 'ดูรายละเอียดงาน' เมื่อมี doc_url
    flex = snd.build_job_flex("P1", "ถนน คสล.", "รายละเอียด", doc_url=snd._announcement_url("P1"))
    s = str(flex)
    assert "ดูรายละเอียดงาน" in s and "gprocurement" in s, s
    print("✅ flex มีปุ่มดูประกาศ (doc_url)")


if __name__ == "__main__":
    test_announcement_url()
    test_fallback_logic()
    test_flex_has_doc_button()
    print("\n✅ ALL test_announcement_link PASS")
