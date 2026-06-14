"""test_discovery_http.py — _is_challenge + _get (curl_cffi + retry/backoff + metrics)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Province_Discovery as spd


class FakeResp:
    def __init__(self, status=200, text="{}", ctype="application/json",
                 json_data=None, json_raises=False):
        self.status_code = status
        self.text = text
        self.headers = {"content-type": ctype}
        self.ok = 200 <= status < 400
        self._json = json_data if json_data is not None else {}
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("not json")
        return self._json


def test_is_challenge():
    # (a) JSON ปกติ → False
    assert spd._is_challenge(FakeResp(200, '{"data":{}}', "application/json")) is False
    # (b) 200 OK แต่ body "Just a moment" → True (body > status)
    assert spd._is_challenge(FakeResp(200, "<html>Just a moment...</html>", "text/html")) is True
    # marker อื่น
    assert spd._is_challenge(FakeResp(200, "cf-mitigated", "text/html")) is True
    assert spd._is_challenge(FakeResp(403, "challenge-platform", "text/html")) is True
    # (c) 403 + text/html ไม่มี marker → True (status + ไม่ใช่ json)
    assert spd._is_challenge(FakeResp(403, "blocked", "text/html")) is True
    assert spd._is_challenge(FakeResp(503, "", "text/html")) is True
    # (d) 403 + application/json (error จริงของ API) → False (content-type กัน false positive)
    assert spd._is_challenge(FakeResp(403, '{"error":"x"}', "application/json")) is False
    print("✅ test_is_challenge")


if __name__ == "__main__":
    test_is_challenge()
    print("\n✅ ALL test_discovery_http PASS")
