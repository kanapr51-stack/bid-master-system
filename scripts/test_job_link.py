"""test_job_link.py — sender build_job_link มินต์ token ที่ bms_api verify ได้ (ลิงก์ไปหน้า /portal/job)."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_FOLLOW_SECRET"] = "test-secret-123"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

import Sebastian_LINE_Sender as snd
import follow_token as ft

url = snd.build_job_link("Uabc", "P1")
assert url.startswith("https://api.butler-bms.com/portal/job?t="), url
assert url.endswith("&pid=P1"), url
tok = url.split("t=", 1)[1].split("&pid=", 1)[0]
v = ft.verify_token(tok, secret="test-secret-123")
assert v is not None and v[0] == "Uabc" and v[1] == "P1", v

# exception path: make_token raises → build_job_link returns "" (ห้าม NameError/throw)
_orig = ft.make_token
def _boom(*a, **k):
    raise RuntimeError("forced")
snd.follow_token.make_token = _boom
try:
    assert snd.build_job_link("Uabc", "P1") == "", "build_job_link must return '' on token error"
finally:
    snd.follow_token.make_token = _orig

print("OK test_job_link")
