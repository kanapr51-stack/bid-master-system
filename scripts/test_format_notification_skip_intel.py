"""test_format_notification_skip_intel.py — skip_intel=True (N+216 hotfix) ต้องข้าม
cgd_intel.intel_context() ทั้งก้อน (LIKE scan ~2M แถว cgd_winners ไม่มี index ใช้ได้ — แพงมาก
ถ้าเรียกซ้ำหลายสิบครั้งต่อคำขอเดียวใน Sebastian chat feed, วัดจริง 44.8s สำหรับ 30 ข้อความ)"""
import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls
import cgd_intel as _ci

_PRED_CTX = {"amphoe": "เมือง", "tambon": "ในเมือง", "lines": ["💡 TEST"],
             "prediction": {"budget": 100}, "explain": None}


def test_default_skip_intel_false_still_calls_intel():
    with patch.object(_ci, "intel_context", return_value=dict(_PRED_CTX)) as mock_intel:
        text = ls.format_notification("P1", province="นครพนม", project_name="ถนน", announce_type="D0",
                                       record_prediction=False)
        mock_intel.assert_called_once()
        assert "ต.ในเมือง" in text and "อ.เมือง" in text, text
    print("✅ default (ไม่ระบุ skip_intel) ยังเรียก intel_context เหมือนเดิม + ได้รายละเอียด ต./อ.")


def test_skip_intel_true_never_calls_intel():
    with patch.object(_ci, "intel_context", return_value=dict(_PRED_CTX)) as mock_intel:
        text = ls.format_notification("P2", province="นครพนม", project_name="ถนน", announce_type="D0",
                                       record_prediction=False, skip_intel=True)
        mock_intel.assert_not_called()
        # ไม่มี intel_ctx → fallback บรรทัด 📍 เป็นจังหวัดเฉยๆ ไม่ใช่ ต./อ. — ยังต้อง render ได้ปกติ ไม่ crash
        assert "📍 นครพนม" in text, text
        assert "ต.ในเมือง" not in text, text
    print("✅ skip_intel=True ไม่เรียก intel_context เลย — fallback เป็นจังหวัดเฉยๆ ไม่ crash")


test_default_skip_intel_false_still_calls_intel()
test_skip_intel_true_never_calls_intel()
print("ALL PASS format_notification skip_intel flag")
