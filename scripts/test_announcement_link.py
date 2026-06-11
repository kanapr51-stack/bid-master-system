"""test_announcement_link.py — ลิงก์ประกาศ = view-pdf-file?templateId (PDF จริง สาธารณะ).
templateId = buildName2 จาก infoProcureDocAnnounZip. graceful (network จริงทดสอบบน VPS)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as snd
import process5_http_client as p


def test_pdf_url_format():
    # endpoint = view-pdf-file (PDF จริง) ไม่ใช่ procsearch (E4514)
    assert p.PDF_BASE.endswith("view-pdf-file"), p.PDF_BASE
    assert "process5" in p.PDF_BASE, p.PDF_BASE
    assert "infoProcureDocAnnounZip" in p.INFO_DOC_URL, p.INFO_DOC_URL
    print("✅ PDF_BASE = view-pdf-file + INFO_DOC_URL")


def test_graceful():
    # ไม่มี id → "" · มี id แต่ไม่มี network/token (local) → "" (ไม่ crash)
    assert snd._announcement_url("") == ""
    assert isinstance(snd._announcement_url("67129339090"), str)   # graceful
    assert isinstance(p.get_announce_pdf_url("67129339090"), str)  # graceful (local → "")
    print("✅ graceful (ไม่มี network/token ไม่ crash)")


def test_flex_doc_button():
    # build_job_flex ใส่ปุ่มเมื่อมี doc_url (view-pdf)
    url = p.PDF_BASE + "?templateId=ed86f3e8-9ead-4a4d-9d02-319398b7b1c8"
    flex = snd.build_job_flex("P1", "ถนน คสล.", "รายละเอียด", doc_url=url)
    s = str(flex)
    assert "ดูรายละเอียดงาน" in s and "view-pdf-file" in s, s
    print("✅ flex ปุ่มดูประกาศ (doc_url = view-pdf)")


if __name__ == "__main__":
    test_pdf_url_format()
    test_graceful()
    test_flex_doc_button()
    print("\n✅ ALL test_announcement_link PASS")
