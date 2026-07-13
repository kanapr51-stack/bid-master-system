# scripts/test_webpush_mirror.py
"""send_line_push/send_line_flex mirror เข้า webpush_send.mirror_text ทุกครั้ง
(ทั้ง LINE สำเร็จและล้ม) และ webpush พังไม่กระทบผล LINE"""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ["BMS_WEBPUSH_DISABLED"] = "1"  # กัน DB/network จริงตอน import
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_LINE_Sender as ls

def _resp(code):
    m = MagicMock(); m.status_code = code
    m.json.return_value = {"message": "x"}; m.text = "x"
    return m

# 1) LINE 200 → mirror ถูกเรียกพร้อม ctx
with patch.object(ls, "req_lib") as rq, patch.object(ls, "_mirror_webpush") as mw:
    rq.post.return_value = _resp(200)
    ok, et, em = ls.send_line_push("tok", "U1", "hello\nworld",
                                   webpush_ctx={"project_id": "P1", "source_stage": "api_enriched"})
    assert ok is True
    mw.assert_called_once_with("U1", "hello\nworld", {"project_id": "P1", "source_stage": "api_enriched"})

# 2) LINE 429 (quota เต็ม) → mirror ยังถูกเรียก (นี่คือ use case หลัก!)
with patch.object(ls, "req_lib") as rq, patch.object(ls, "_mirror_webpush") as mw:
    rq.post.return_value = _resp(429)
    ok, et, em = ls.send_line_push("tok", "U1", "hi")
    assert ok is False and et == "retryable"
    mw.assert_called_once_with("U1", "hi", None)

# 3) mirror ระเบิด → ผล LINE ไม่กระทบ
with patch.object(ls, "req_lib") as rq, \
     patch.object(ls.webpush_send, "mirror_text", side_effect=RuntimeError("boom")):
    rq.post.return_value = _resp(200)
    ok, et, em = ls.send_line_push("tok", "U1", "hi")
    assert ok is True, (ok, et, em)

# 4) flex → mirror ด้วย alt_text
with patch.object(ls, "req_lib") as rq, patch.object(ls, "_mirror_webpush") as mw:
    rq.post.return_value = _resp(200)
    ok, et, em = ls.send_line_flex("tok", "U1", "alt สรุปงาน", {"type": "bubble"},
                                   webpush_ctx={"project_id": "P2", "source_stage": "province_qualified"})
    assert ok is True
    mw.assert_called_once_with("U1", "alt สรุปงาน", {"project_id": "P2", "source_stage": "province_qualified"})

print("PASS test_webpush_mirror")
