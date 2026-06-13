"""_diag_egp.py — probe getProcureResult 1 ครั้ง: token/status/body (debug VPS rate-limit).
ใช้ชั่วคราว debug 2A backfill. รัน: python scripts/_diag_egp.py [projectId]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import process5_http_client as p
import requests

pid = sys.argv[1] if len(sys.argv) > 1 else "67129346506"
tok = p._get_token(pid)
h = p.HEADERS_NO_AUTH.copy()
h["X-Announcement-Token"] = tok or ""
try:
    r = requests.get(p.API_BASE + "/getProcureResult", params={"projectId": pid},
                     headers=h, timeout=p.TIMEOUT)
    print("token_len:", len(tok) if tok else None)
    print("status:", r.status_code)
    print("rate_limit_in_body:", ("rate limit" in r.text.lower()))
    print("body[:400]:", r.text[:400])
except Exception as e:
    print("token_len:", len(tok) if tok else None)
    print("EXCEPTION:", type(e).__name__, str(e)[:200])
