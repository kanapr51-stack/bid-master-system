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

# exception path (strict=False): make_token raises → build_follow_link returns "" (ห้าม NameError/throw)
# strict=True (default) → raise; คุมโดย test_follow_link_guard.py (fail-loud, INC 2026-07-01)
_orig = ft.make_token
def _boom(*a, **k):
    raise RuntimeError("forced")
snd.follow_token.make_token = _boom
try:
    assert snd.build_follow_link("Uabc", "P1", strict=False) == "", "strict=False ต้องคืน '' on token error"
finally:
    snd.follow_token.make_token = _orig

print("OK test_follow_link")
