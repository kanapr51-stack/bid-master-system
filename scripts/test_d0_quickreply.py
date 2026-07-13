"""test_d0_quickreply.py — intel + quick-reply ทุกงาน D0 (อุด follow-timing gap).
ครอบ: is_following · _quick_reply_items · _text_message · send_line_push payload."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_WEBPUSH_DISABLED"] = "1"  # กัน mirror ยิงจริงใน test
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db; db.init_schema()
import Sebastian_LINE_Sender as ls


def test_is_following():
    with db.get_connection() as c:   # is_following query แค่ followed_jobs (ไม่พึ่ง customers)
        c.execute("INSERT INTO followed_jobs (customer_id, project_id, starred_at, starred_stage, "
                  "last_stage_notified, status) VALUES (9,'JOB_F','2026-06-08','D0','D0','active')")
        c.execute("INSERT INTO followed_jobs (customer_id, project_id, starred_at, starred_stage, "
                  "last_stage_notified, status) VALUES (9,'JOB_C','2026-06-08','D0','D0','closed')")
    assert db.is_following(9, "JOB_F") is True            # active → ตาม
    assert db.is_following(9, "JOB_C") is False           # closed → ไม่นับ
    assert db.is_following(9, "JOB_X") is False           # ไม่เคยตาม
    assert db.is_following(99, "JOB_F") is False          # คนอื่น
    print("✅ is_following (active/closed/none)")


def test_quick_reply_items():
    not_following = ls._quick_reply_items("P1", following=False)
    labels = [it["action"]["label"] for it in not_following]
    assert labels == [ls.FB_ACTIONS["star"], ls.FB_ACTIONS["irrelevant"]], labels   # ⭐ + ❌
    assert not_following[0]["action"]["data"] == "star:P1", not_following[0]
    assert not_following[1]["action"]["data"] == "fb:irrelevant:P1", not_following[1]
    following = ls._quick_reply_items("P1", following=True)
    labels2 = [it["action"]["label"] for it in following]
    assert labels2 == [ls.FB_ACTIONS["irrelevant"]], labels2   # ตามแล้ว → ❌ อย่างเดียว
    print("✅ _quick_reply_items (⭐ เฉพาะยังไม่ตาม)")


def test_text_message():
    plain = ls._text_message("hello")
    assert plain == {"type": "text", "text": "hello"}, plain   # ไม่มี quickReply
    qr = ls._quick_reply_items("P1", following=False)
    with_qr = ls._text_message("hello", qr)
    assert with_qr["quickReply"]["items"] == qr, with_qr       # แนบ quickReply
    assert with_qr["type"] == "text" and with_qr["text"] == "hello"
    print("✅ _text_message (แนบ quickReply ถ้ามี)")


def test_send_line_push_payload():
    """send_line_push ใส่ quickReply ลง payload ถูก (mock req_lib)."""
    captured = {}

    class _Resp:
        status_code = 200

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    orig = ls.req_lib.post
    ls.req_lib.post = _fake_post
    try:
        qr = ls._quick_reply_items("P1", following=False)
        ok, et, em = ls.send_line_push("tok", "U1", "hi", quick_reply=qr)
        assert ok is True, (ok, et, em)
        msg = captured["json"]["messages"][0]
        assert msg["text"] == "hi" and msg["quickReply"]["items"] == qr, msg
        # ไม่ส่ง quick_reply → ไม่มี key (backward-compat)
        ls.send_line_push("tok", "U1", "hi2")
        assert "quickReply" not in captured["json"]["messages"][0], captured["json"]
    finally:
        ls.req_lib.post = orig
    print("✅ send_line_push (quickReply ใน payload + backward-compat)")


def test_is_plain_text_stage():
    assert ls._is_plain_text_stage({"announce_type": "D0"}) is True
    assert ls._is_plain_text_stage({"source_stage": "province_tor_review"}) is True
    assert ls._is_plain_text_stage({"source_stage": "province_tor_review_soft"}) is True   # startswith
    assert ls._is_plain_text_stage({"announce_type": "B0", "source_stage": "api_enriched"}) is False
    assert ls._is_plain_text_stage({}) is False
    print("✅ _is_plain_text_stage (D0 + province_tor_review* → plain, อื่นๆ → การ์ด)")


def test_plain_text_body_header_before_name():
    # N+163: หัวข้อ (บรรทัดแรกของ text) ต้องขึ้นก่อนชื่องาน — เดิม full_name ขึ้นก่อน
    text = "🔔 พบงานเปิดกำหนดวันยื่นซองใหม่\n📍 นครพนม\n💰 ราคากลาง 1.0 ล้านบาท"
    body = ls._plain_text_body(text, "ก่อสร้างถนน คสล.")
    lines = body.split("\n")
    assert lines[0] == "🔔 พบงานเปิดกำหนดวันยื่นซองใหม่", lines
    assert lines[1] == "ก่อสร้างถนน คสล.", lines
    assert lines[2:] == ["📍 นครพนม", "💰 ราคากลาง 1.0 ล้านบาท"], lines
    # text บรรทัดเดียว (ไม่มี rest) → ไม่มี \n ท้ายเกิน
    body2 = ls._plain_text_body("🔔 หัวข้อเดียว", "ชื่องาน")
    assert body2 == "🔔 หัวข้อเดียว\nชื่องาน", body2
    print("✅ _plain_text_body (หัวข้อขึ้นก่อนชื่องาน)")


if __name__ == "__main__":
    test_is_following()
    test_quick_reply_items()
    test_text_message()
    test_send_line_push_payload()
    test_is_plain_text_stage()
    test_plain_text_body_header_before_name()
    print("ALL PASS d0 quickreply")
