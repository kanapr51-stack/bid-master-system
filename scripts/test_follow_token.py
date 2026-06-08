"""test_follow_token.py — HMAC token mint/verify: roundtrip, tamper, expiry, portal token."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import follow_token as ft

SECRET = "test-secret-123"
EXP = 1000 + 120 * 86400

# roundtrip (follow token มี project_id)
t = ft.make_token("Uabc", "P1", secret=SECRET, now=1000)
assert ft.verify_token(t, secret=SECRET, now=1000) == ("Uabc", "P1", EXP), ft.verify_token(t, secret=SECRET, now=1000)

# tamper 1 char → reject
bad = t[:-1] + ("A" if t[-1] != "A" else "B")
assert ft.verify_token(bad, secret=SECRET, now=1000) is None

# wrong secret → reject
assert ft.verify_token(t, secret="other", now=1000) is None

# expired → reject
assert ft.verify_token(t, secret=SECRET, now=EXP + 1) is None

# portal token (p=None) → roundtrip
pt = ft.make_token("Uabc", None, secret=SECRET, now=1000)
assert ft.verify_token(pt, secret=SECRET, now=1000) == ("Uabc", None, EXP)

# garbage / empty → None (ไม่ throw)
assert ft.verify_token("", secret=SECRET) is None
assert ft.verify_token("no-dot-here", secret=SECRET) is None

# missing secret → make_token raises
try:
    ft.make_token("Uabc", "P1", secret="")
    assert False, "should raise RuntimeError"
except RuntimeError:
    pass

print("OK test_follow_token")
