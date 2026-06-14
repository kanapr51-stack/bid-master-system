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


class FakeRequestsError(Exception):
    pass


class FakeCffi:
    """แทน spd.cffi_requests — get() คืน item ถัดไปใน queue (response หรือ raise ถ้าเป็น Exception)"""
    RequestsError = FakeRequestsError

    def __init__(self, items):
        self._items = list(items)
        self.calls = 0

    def get(self, *a, **k):
        item = self._items[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _patch_cffi(items):
    """ติดตั้ง FakeCffi แทน spd.cffi_requests → คืน (fake, restore_fn)"""
    fake = FakeCffi(items)
    orig = spd.cffi_requests
    spd.cffi_requests = fake

    def restore():
        spd.cffi_requests = orig
    return fake, restore


def _patch(items):
    """เหมือน _patch_cffi + no-op time.sleep & random.uniform (สำหรับ test retry — ไม่หน่วงจริง)"""
    fake, restore_cffi = _patch_cffi(items)
    orig_sleep, orig_uniform = spd.time.sleep, spd.random.uniform
    spd.time.sleep = lambda *a, **k: None
    spd.random.uniform = lambda a, b: 0.0

    def restore():
        spd.time.sleep, spd.random.uniform = orig_sleep, orig_uniform
        restore_cffi()
    return fake, restore


def test_get_success():
    fake, restore = _patch_cffi([FakeResp(200, '{"data":1}', json_data={"data": 1})])
    try:
        assert spd._get("tok", {}) == {"data": 1}
        assert fake.calls == 1
    finally:
        restore()
    print("✅ test_get_success")


def test_get_persistent_challenge_returns_none():
    # challenge ตลอด → None หลัง MAX_CHALLENGE_RETRY (=3) → เรียก get 4 ครั้ง (1+3)
    items = [FakeResp(503, "just a moment", "text/html")] * (spd.MAX_CHALLENGE_RETRY + 1)
    fake, restore = _patch(items)
    try:
        assert spd._get("tok", {}) is None
        assert fake.calls == spd.MAX_CHALLENGE_RETRY + 1
    finally:
        restore()
    print("✅ test_get_persistent_challenge_returns_none")


def test_get_recovered_after_challenge():
    # challenge 2 ครั้งแล้วสำเร็จ → คืน JSON + print CF_RECOVERED
    import builtins
    items = [FakeResp(200, "just a moment", "text/html"),
             FakeResp(403, "blocked", "text/html"),
             FakeResp(200, '{"ok":1}', json_data={"ok": 1})]
    fake, restore = _patch(items)
    logs = []
    orig_print = builtins.print
    builtins.print = lambda *a, **k: logs.append(" ".join(str(x) for x in a))
    try:
        assert spd._get("tok", {"page": "3"}) == {"ok": 1}
        assert fake.calls == 3
        assert any("CF_RECOVERED" in m for m in logs), logs
    finally:
        builtins.print = orig_print
        restore()
    print("✅ test_get_recovered_after_challenge")


def test_get_ratelimit_propagates():
    fake, restore = _patch_cffi([FakeResp(200, "Rate limit exceeded", "text/plain")])
    try:
        raised = False
        try:
            spd._get("tok", {})
        except spd.RateLimited:
            raised = True
        assert raised, "RateLimited ต้อง propagate ไม่ถูกกลืน"
    finally:
        restore()
    print("✅ test_get_ratelimit_propagates")


def test_get_network_error_returns_none():
    fake, restore = _patch_cffi([FakeRequestsError("dns fail")])
    try:
        assert spd._get("tok", {}) is None
    finally:
        restore()
    print("✅ test_get_network_error_returns_none")


def test_get_json_error_logged_not_swallowed():
    # response ok แต่ json() พัง → คืน None + ต้อง print (ไม่กลืนเงียบ)
    import builtins
    fake, restore = _patch_cffi([FakeResp(200, "weird", json_raises=True)])
    logs = []
    orig_print = builtins.print   # _get ใช้ bare print() → resolve เป็น builtins.print
    builtins.print = lambda *a, **k: logs.append(" ".join(str(x) for x in a))
    try:
        assert spd._get("tok", {}) is None
        assert any("JSON decode error" in m for m in logs), logs
    finally:
        builtins.print = orig_print
        restore()
    print("✅ test_get_json_error_logged_not_swallowed")


if __name__ == "__main__":
    test_is_challenge()
    test_get_success()
    test_get_persistent_challenge_returns_none()
    test_get_recovered_after_challenge()
    test_get_ratelimit_propagates()
    test_get_network_error_returns_none()
    test_get_json_error_logged_not_swallowed()
    print("\n✅ ALL test_discovery_http PASS")
