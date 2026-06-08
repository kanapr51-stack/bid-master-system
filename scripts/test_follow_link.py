"""test_follow_link.py — sender build_follow_link มินต์ token ที่ bms_api verify ได้."""
import os, sys, tempfile
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_FOLLOW_SECRET"] = "test-secret-123"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

import Sebastian_LINE_Sender as snd
import follow_token as ft

url = snd.build_follow_link("Uabc", "P1")
assert url.startswith("https://api.butler-bms.com/follow?t="), url
tok = url.split("t=", 1)[1]
v = ft.verify_token(tok, secret="test-secret-123")
assert v is not None and v[0] == "Uabc" and v[1] == "P1", v

print("OK test_follow_link")
