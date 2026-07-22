"""test_format_notification_record_prediction.py — record_prediction=False (Sebastian chat
feed, N+211) ต้องไม่เขียน price_predictions ซ้ำตอน reconstruct ข้อความมาโชว์ในหน้าประวัติ"""
import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_LINE_Sender as ls
import Sebastian_Customer_DB as db
import cgd_intel as _ci

_PRED_CTX = {"lines": ["💡 TEST"], "prediction": {"budget": 100}, "explain": None}


def test_default_record_prediction_true_still_saves():
    _ci.intel_context = lambda *a, **k: dict(_PRED_CTX)
    with patch.object(db, "save_prediction") as mock_save:
        ls.format_notification("P1", province="นครพนม", project_name="ถนน", announce_type="D0")
        mock_save.assert_called_once()
    print("✅ default (ไม่ระบุ record_prediction) ยังบันทึกเหมือนเดิม")


def test_record_prediction_false_skips_save():
    _ci.intel_context = lambda *a, **k: dict(_PRED_CTX)
    with patch.object(db, "save_prediction") as mock_save:
        ls.format_notification("P2", province="นครพนม", project_name="ถนน", announce_type="D0",
                               record_prediction=False)
        mock_save.assert_not_called()
    print("✅ record_prediction=False ไม่เขียน price_predictions ซ้ำ")


test_default_record_prediction_true_still_saves()
test_record_prediction_false_skips_save()
print("ALL PASS format_notification record_prediction flag")
