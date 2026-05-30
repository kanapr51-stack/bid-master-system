"""
token_service.py — Discovery Plane Token Control (X-Announcement-Token)

Architecture (ChatGPT + Claude converged 2026-05-30):
- ITokenProvider abstraction → สลับแหล่ง token โดยไม่แตะ Discovery
- TokenService: single-writer cache + state machine VALID/EXPIRING/REFRESHING/FAILED/EXPIRED
- token encode expiry ในตัว (EGP-ANNOUNCEMENT-KEY:TS_ms:HMAC, TTL 30 นาที) → ไม่ต้องเดา
- telemetry: time_to_first_token, refresh_count/failures, provider_used

หลัก: "obtain ≥1 usable token before discovery deadline" — ไม่ใช่ per-request success rate
KPI: Discovery Readiness Probability = P(token acquired within window)

Providers (beta decision 2026-05-30):
  primary    = Chrome9222Provider   (residential IP ผ่าน Turnstile ง่าย)
  fallback   = ManualProvider       (emergency — paste token)
  experimental = PlaywrightProvider  (VPS canary track — ยังไม่ promote)
"""

import os
import sys
import json
import time
import base64
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")

TOKEN_TTL_SEC = 30 * 60          # 18e5 ms (จาก JS: checkAnnouncementTokenTime 18e5)
REFRESH_MARGIN_SEC = 5 * 60      # refresh เมื่อเหลือ < 5 นาที (proactive)
TOKEN_PREFIX = "EGP-ANNOUNCEMENT-KEY"

ANNOUNCE_PAGE = ("https://process5.gprocurement.go.th/egp-agpc01-web/"
                 "announcement?advancedSearch=true")


def _data_dir() -> str:
    return os.environ.get("BMS_DATA_DIR",
                          os.path.join(os.path.dirname(__file__), "..", "data"))


def _now() -> float:
    return time.time()


# ── Token expiry parsing (token เก็บ expiry ในตัว) ──────────────────────────────

def parse_token_expiry(token_b64: str) -> Optional[float]:
    """
    decode EGP-ANNOUNCEMENT-KEY:TS_ms:HMAC → expiry epoch seconds (TS/1000 + TTL)
    คืน None ถ้า parse ไม่ได้
    """
    if not token_b64:
        return None
    try:
        raw = base64.b64decode(token_b64).decode("utf-8", "replace")
    except Exception:
        return None
    if TOKEN_PREFIX not in raw:
        return None
    parts = raw.split(":")
    if len(parts) < 3:
        return None
    try:
        ts_ms = int(parts[1])
    except ValueError:
        return None
    return ts_ms / 1000.0 + TOKEN_TTL_SEC


# ── State machine ──────────────────────────────────────────────────────────────

class TokenState(Enum):
    EMPTY = "empty"           # ไม่มี token
    VALID = "valid"           # ใช้ได้ เหลือเวลา > margin
    EXPIRING = "expiring"     # ใช้ได้ แต่เหลือ < margin → ควร refresh
    REFRESHING = "refreshing"
    FAILED = "failed"         # refresh ล่าสุดล้มเหลว
    EXPIRED = "expired"       # หมดอายุ ใช้ไม่ได้


@dataclass
class TokenResult:
    token: Optional[str]
    expires_at: float
    provider: str
    acquired_at: float
    time_to_token_ms: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.token) and self.expires_at > _now()


class TokenError(Exception):
    pass


# ── Provider interface ──────────────────────────────────────────────────────────

class ITokenProvider:
    name = "base"

    def get_token(self) -> TokenResult:
        raise NotImplementedError


class ManualProvider(ITokenProvider):
    """อ่าน token จาก env BMS_ANNOUNCEMENT_TOKEN หรือไฟล์ data/manual_token.txt"""
    name = "manual"

    def __init__(self, token: str = "", file_path: str = ""):
        self._token = token
        self._file = file_path or os.path.join(_data_dir(), "manual_token.txt")

    def get_token(self) -> TokenResult:
        t0 = _now()
        token = self._token or os.environ.get("BMS_ANNOUNCEMENT_TOKEN", "")
        if not token and os.path.exists(self._file):
            with open(self._file, encoding="utf-8") as f:
                token = f.read().strip()
        if not token:
            return TokenResult(None, 0, self.name, t0, 0, "no manual token")
        exp = parse_token_expiry(token)
        if exp is None:
            return TokenResult(None, 0, self.name, t0, 0, "unparseable token")
        return TokenResult(token, exp, self.name, t0, int((_now() - t0) * 1000))


class Chrome9222Provider(ITokenProvider):
    """
    Harvest X-Announcement-Token ผ่าน Chrome DevTools Protocol (debug port 9222)
    บนเครื่อง residential — Turnstile โหมด managed มัก auto-pass browser ที่ trusted

    *** ยังไม่ได้ test live (ต้องเปิด Chrome --remote-debugging-port=9222 ก่อน) ***
    capture จาก 2 ทาง (อันไหนมาก่อนใช้อันนั้น):
      1. request header X-Announcement-Token ของ call /announcement
      2. response body ของ cfturnstile/validate (.data = token)
    """
    name = "chrome9222"

    def __init__(self, debug_url: str = "http://localhost:9222",
                 page_url: str = ANNOUNCE_PAGE, timeout: int = 75):
        self.debug_url = debug_url.rstrip("/")
        self.page_url = page_url
        self.timeout = timeout

    def get_token(self) -> TokenResult:
        t0 = _now()
        try:
            token = self._harvest()
        except Exception as e:
            return TokenResult(None, 0, self.name, t0, int((_now() - t0) * 1000),
                               f"{type(e).__name__}: {e}")
        if not token:
            return TokenResult(None, 0, self.name, t0, int((_now() - t0) * 1000),
                               "timeout — no token captured")
        exp = parse_token_expiry(token) or (_now() + TOKEN_TTL_SEC)
        return TokenResult(token, exp, self.name, t0, int((_now() - t0) * 1000))

    def _harvest(self) -> Optional[str]:
        import requests
        import websocket  # websocket-client

        # เปิด tab ใหม่ที่หน้า announcement
        r = requests.put(f"{self.debug_url}/json/new?{self.page_url}", timeout=10) \
            if False else requests.get(f"{self.debug_url}/json/new?{self.page_url}", timeout=10)
        tab = r.json()
        ws_url = tab["webSocketDebuggerUrl"]
        tab_id = tab["id"]
        token_box = {"token": None}

        try:
            ws = websocket.create_connection(ws_url, timeout=self.timeout)
            mid = {"n": 0}

            def send(method, params=None):
                mid["n"] += 1
                ws.send(json.dumps({"id": mid["n"], "method": method,
                                    "params": params or {}}))

            send("Network.enable")
            send("Page.enable")
            send("Page.navigate", {"url": self.page_url})

            deadline = _now() + self.timeout
            pending_validate = {}   # requestId → True
            ws.settimeout(5)
            while _now() < deadline and not token_box["token"]:
                try:
                    msg = json.loads(ws.recv())
                except Exception:
                    continue
                method = msg.get("method")
                if method == "Network.requestWillBeSent":
                    req = msg["params"]["request"]
                    hdrs = req.get("headers", {})
                    for k, v in hdrs.items():
                        if k.lower() == "x-announcement-token" and v:
                            token_box["token"] = v
                            break
                    if "cfturnstile/validate" in req.get("url", ""):
                        pending_validate[msg["params"]["requestId"]] = True
                elif method == "Network.loadingFinished":
                    rid = msg["params"]["requestId"]
                    if rid in pending_validate:
                        send("Network.getResponseBody", {"requestId": rid})
                elif "result" in msg and "body" in msg.get("result", {}):
                    try:
                        body = msg["result"]["body"]
                        if msg["result"].get("base64Encoded"):
                            body = base64.b64decode(body).decode("utf-8", "replace")
                        data = json.loads(body).get("data")
                        if data and TOKEN_PREFIX in base64.b64decode(data).decode("utf-8", "replace"):
                            token_box["token"] = data
                    except Exception:
                        pass
            ws.close()
        finally:
            try:
                requests.get(f"{self.debug_url}/json/close/{tab_id}", timeout=5)
            except Exception:
                pass
        return token_box["token"]


class PlaywrightProvider(ITokenProvider):
    """experimental — VPS canary track. ยังไม่ promote เป็น production (รอ acquisition latency data)"""
    name = "playwright"

    def get_token(self) -> TokenResult:
        raise NotImplementedError(
            "PlaywrightProvider ยัง experimental — รัน canary เก็บ acquisition latency ก่อน")


# ── Token Service (single-writer cache + state machine) ─────────────────────────

class TokenService:
    def __init__(self, provider: ITokenProvider,
                 state_path: str = "", telemetry_path: str = "",
                 refresh_margin: int = REFRESH_MARGIN_SEC,
                 allow_refresh: bool = True):
        self.provider = provider
        self.state_path = state_path or os.path.join(_data_dir(), "token_state.json")
        self.telemetry_path = telemetry_path or os.path.join(_data_dir(), "token_harvest_log.ndjson")
        self.refresh_margin = refresh_margin
        self.allow_refresh = allow_refresh   # False = worker (read-only), True = single writer

    # -- cache I/O --
    def _load(self) -> dict:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self, d: dict):
        os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_path)   # atomic — single writer

    # -- state classification --
    def classify(self, cache: dict = None) -> TokenState:
        cache = cache if cache is not None else self._load()
        token = cache.get("token")
        exp = cache.get("expires_at", 0)
        if not token:
            return TokenState.EMPTY
        remaining = exp - _now()
        if remaining <= 0:
            return TokenState.EXPIRED
        if remaining < self.refresh_margin:
            return TokenState.EXPIRING
        return TokenState.VALID

    def state(self) -> TokenState:
        return self.classify()

    # -- telemetry --
    def _record(self, res: TokenResult, state_before: TokenState):
        rec = {
            "ts": _now(),
            "provider": res.provider,
            "success": res.ok,
            "time_to_token_ms": res.time_to_token_ms,
            "state_before": state_before.value,
            "expires_at": res.expires_at,
            "error": res.error,
        }
        try:
            with open(self.telemetry_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # -- refresh (single writer) --
    def _refresh(self, cache: dict, state_before: TokenState) -> dict:
        cache["last_refresh_attempt"] = _now()
        cache["refresh_count"] = cache.get("refresh_count", 0) + 1
        res = self.provider.get_token()
        self._record(res, state_before)
        if res.ok:
            cache.update({
                "token": res.token,
                "acquired_at": res.acquired_at,
                "expires_at": res.expires_at,
                "provider": res.provider,
                "last_state": TokenState.VALID.value,
                "last_error": None,
            })
        else:
            cache["refresh_failures"] = cache.get("refresh_failures", 0) + 1
            cache["last_state"] = TokenState.FAILED.value
            cache["last_error"] = res.error
        self._save(cache)
        return cache

    # -- public API --
    def get_valid_token(self) -> Optional[str]:
        """คืน token ที่ใช้ได้ (refresh ถ้าจำเป็นและ allow_refresh) หรือ None"""
        cache = self._load()
        st = self.classify(cache)
        if st == TokenState.VALID:
            return cache.get("token")
        # EXPIRING ยังใช้ได้ — แต่ถ้าเป็น writer ให้ refresh เชิงรุก
        if st == TokenState.EXPIRING and not self.allow_refresh:
            return cache.get("token")
        if not self.allow_refresh:
            return cache.get("token") if st in (TokenState.VALID, TokenState.EXPIRING) else None
        cache = self._refresh(cache, st)
        return cache.get("token") if self.classify(cache) in (TokenState.VALID, TokenState.EXPIRING) else None

    def health(self) -> dict:
        cache = self._load()
        st = self.classify(cache)
        exp = cache.get("expires_at", 0)
        return {
            "state": st.value,
            "provider": cache.get("provider"),
            "token_age_sec": int(_now() - cache.get("acquired_at", _now())) if cache.get("token") else None,
            "remaining_sec": int(exp - _now()) if exp else 0,
            "refresh_count": cache.get("refresh_count", 0),
            "refresh_failures": cache.get("refresh_failures", 0),
            "last_error": cache.get("last_error"),
        }


# ── factory ─────────────────────────────────────────────────────────────────────

def make_provider(name: str = "", **kw) -> ITokenProvider:
    name = name or os.environ.get("BMS_TOKEN_PROVIDER", "manual")
    if name == "chrome9222":
        return Chrome9222Provider(**kw)
    if name == "playwright":
        return PlaywrightProvider()
    return ManualProvider(**kw)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="manual")
    ap.add_argument("--token", default="")
    ap.add_argument("--health", action="store_true")
    a = ap.parse_args()
    svc = TokenService(make_provider(a.provider, token=a.token) if a.provider == "manual"
                       else make_provider(a.provider))
    if a.health:
        print(json.dumps(svc.health(), ensure_ascii=False, indent=2))
    else:
        tok = svc.get_valid_token()
        print("token:", (tok[:50] + "...") if tok else None)
        print("health:", json.dumps(svc.health(), ensure_ascii=False))
