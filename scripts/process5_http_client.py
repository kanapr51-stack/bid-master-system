"""
process5_http_client.py — HTTP-only wrapper สำหรับ eGP process5 API

Discovery 2026-05-19: getProjectDetail / getProcureResult / PDF download
Discovery 2026-05-28: X-Announcement-Token reverse-engineered
  - AES key: "RDCrypto" (CryptoJS passphrase)
  - Flow: double_encryptData(projectId) → POST generateToken → token (30 min TTL)
  - No auth required (noToken header bypasses Angular interceptor)

Usage:
    from process5_http_client import get_project_detail, get_procure_result, download_pdf
"""

import sys
import time
import random
import hashlib
import base64
import os
import json
import urllib.parse
import requests
from typing import Optional

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    _crypto_available = True
except ImportError:
    _crypto_available = False

try:
    from Sebastian_Telemetry import record_poll
    _telemetry = True
except ImportError:
    _telemetry = False


def _record(endpoint: str, success: bool, response_time_ms: float,
            bytes_received: int, items_count: int, failure_reason: str | None = None):
    if not _telemetry:
        return
    try:
        record_poll(
            endpoint=endpoint, dept_id="", anounce_type="",
            success=success, http_status=200 if success else -1,
            response_time_ms=response_time_ms, ttfb_ms=response_time_ms,
            bytes_received=bytes_received, items_count=items_count,
            failure_reason=failure_reason, source_type="process5_api",
        )
    except Exception:
        pass

sys.stdout.reconfigure(encoding="utf-8")

PROCESS5_BASE = "https://process5.gprocurement.go.th"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement"
PDF_BASE      = f"{PROCESS5_BASE}/egp-template-service/dwnt/view-pdf-file"
GENERATE_TOKEN_URL = f"{API_BASE}/generateToken"

_AES_PASSPHRASE = "RDCrypto"
_TOKEN_TTL_SEC  = 25 * 60  # ใช้ 25 นาที (token valid 30 นาที)
_token_cache: dict[str, tuple[str, float]] = {}  # {project_id: (token, expires_at)}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer":  f"{PROCESS5_BASE}/",
    "Accept":   "application/json, text/plain, */*",
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
}

HEADERS_NO_AUTH = {
    **HEADERS,
    "Content-Type": "application/json",
    "noToken": "noToken",
    "noDataProfile": "noDataProfile",
}

TIMEOUT     = 15  # วินาที ต่อ request
MAX_RETRIES = 3
_RL_BASE    = 30  # exponential backoff base (วินาที)
_RL_CAP     = 300 # cap สูงสุด (5 นาที)

# ---- Token Generation -------------------------------------------------------

def _evp_bytes_to_key(password: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """OpenSSL EVP_BytesToKey with MD5 (replicates CryptoJS default)."""
    d, d_i = b"", b""
    while len(d) < 48:  # 32 key + 16 iv
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:32], d[32:48]


def _cryptojs_encrypt(plain_text: str) -> str:
    """Replicates CryptoJS.AES.encrypt(text, passphrase).toString() → base64."""
    if not _crypto_available:
        raise RuntimeError("pycryptodome not installed: pip install pycryptodome")
    salt = os.urandom(8)
    key, iv = _evp_bytes_to_key(_AES_PASSPHRASE.encode(), salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plain_text.encode("utf-8"), AES.block_size))
    return base64.b64encode(b"Salted__" + salt + encrypted).decode()


def _encrypt_data(obj) -> str:
    """Replicates CryptoLib.encryptData(obj) → URL-encoded AES ciphertext."""
    json_str = json.dumps(obj, separators=(",", ":"))
    return urllib.parse.quote(_cryptojs_encrypt(json_str), safe="")


def _generate_announcement_key(project_id: str) -> str:
    """Replicates generateAnnouncementKey(projectId): double-encrypt projectId."""
    m = _encrypt_data({"projectId": project_id})
    return _encrypt_data(m)


def _fetch_token(project_id: str) -> Optional[str]:
    """POST generateToken endpoint → raw token string (30 min valid)."""
    key = _generate_announcement_key(project_id)
    try:
        r = requests.post(
            GENERATE_TOKEN_URL,
            json={"key": key},
            headers=HEADERS_NO_AUTH,
            timeout=TIMEOUT,
        )
        if r.ok:
            return r.json().get("data") or None
    except Exception:
        pass
    return None


def _get_token(project_id: str) -> Optional[str]:
    """Get cached token or generate new one."""
    now = time.time()
    cached = _token_cache.get(project_id)
    if cached and cached[1] > now:
        return cached[0]
    token = _fetch_token(project_id)
    if token:
        _token_cache[project_id] = (token, now + _TOKEN_TTL_SEC)
    return token


def _rl_sleep(attempt: int):
    """Exponential backoff + jitter: 30s → 60s → 120s (+ random 0-15s)"""
    wait = min(_RL_BASE * (2 ** (attempt - 1)), _RL_CAP) + random.uniform(0, 15)
    time.sleep(wait)


def _get(url: str, params: dict = None, token: str = None,
         retries: int = MAX_RETRIES) -> Optional[dict]:
    """
    GET url → JSON dict หรือ None ถ้าล้มเหลวหลัง retry ครบ
    token: X-Announcement-Token ถ้ามี
    """
    hdrs = HEADERS_NO_AUTH.copy() if token else HEADERS.copy()
    if token:
        hdrs["X-Announcement-Token"] = token

    for attempt in range(1, retries + 1):
        t0 = time.time()
        try:
            r = requests.get(url, params=params, headers=hdrs, timeout=TIMEOUT)
            rt_ms = (time.time() - t0) * 1000
            if r.status_code == 429:
                _record(url, False, rt_ms, 0, 0, "http_429")
                if attempt < retries:
                    _rl_sleep(attempt)
                    continue
                return None
            if not r.ok:
                _record(url, False, rt_ms, 0, 0, f"http_{r.status_code}")
                return None
            text = r.text
            if "Rate limit" in text or "rate limit" in text.lower():
                _record(url, False, rt_ms, len(r.content), 0, "rate_limit_body")
                if attempt < retries:
                    _rl_sleep(attempt)
                    continue
                return None
            _record(url, True, rt_ms, len(r.content), 1)
            return r.json()
        except requests.Timeout:
            rt_ms = (time.time() - t0) * 1000
            _record(url, False, rt_ms, 0, 0, "timeout")
            if attempt < retries:
                time.sleep(3 * attempt)
                continue
            return None
        except Exception:
            rt_ms = (time.time() - t0) * 1000
            _record(url, False, rt_ms, 0, 0, "unknown_error")
            return None
    return None


def get_project_detail(project_id: str, retry_on_empty: bool = True) -> dict:
    """
    เรียก getProjectDetail?projectId=X → dict ที่ compatible กับ fetch_project_detail เดิม

    Return keys:
      valid (bool), project_status (str), flow_seqno (int), step_id (str),
      flow_id (str), project_status_raw (str), announce_type (str),
      dept_sub_name (str), method_id (str), type_id (str)
    """
    token = _get_token(project_id)
    body = _get(f"{API_BASE}/getProjectDetail", {"projectId": project_id}, token=token)
    if body is None:
        return {"valid": False}

    # validateAnnouncementToken=0 หมายถึง token ไม่ valid → retry ด้วย fresh token
    if body.get("validateAnnouncementToken") == 0:
        _token_cache.pop(project_id, None)
        token = _get_token(project_id)
        body = _get(f"{API_BASE}/getProjectDetail", {"projectId": project_id}, token=token)
        if body is None or body.get("validateAnnouncementToken") == 0:
            return {"valid": False}

    data   = body.get("data", {}) or {}
    seqno  = data.get("flowSeqno", 0) or 0
    stepId = data.get("stepId", "") or ""
    flowId = data.get("flowId", "") or ""

    valid = bool(seqno > 0 or stepId or flowId)

    if not valid and retry_on_empty:
        time.sleep(3)
        return get_project_detail(project_id, retry_on_empty=False)

    if seqno <= 3:
        status = "กำลังเตรียม"
    elif seqno == 4:
        status = "กำลังประมูล"
    else:
        status = "ประมูลแล้ว"

    return {
        "valid":              valid,
        "project_status":     status,
        "flow_seqno":         seqno,
        "step_id":            stepId,
        "flow_id":            flowId,
        "project_status_raw": data.get("projectStatus", "") or "",
        "announce_type":      data.get("announceType", "") or "",
        "dept_sub_name":      data.get("deptSubName", "") or "",
        "method_id":          data.get("methodId", "") or "",
        "type_id":            data.get("typeId", "") or "",
    }


def _parse_iso_to_thai(date_str: str) -> str:
    if not date_str:
        return ""
    from datetime import datetime as _dt
    s = str(date_str)
    if "T" in s:
        try:
            return _dt.fromisoformat(s.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except Exception:
            return s[:10]
    return s


def get_procurement_detail(project_id: str) -> dict:
    """
    เรียก getProcurementDetail?projectId=X → ข้อมูลสำหรับ enriched notification

    Return keys:
      dept_sub_name (str), budget (float), deliver_day (int),
      report_date (str — DD/MM/YYYY Thai), moi_name (str),
      plan_project_name (str), valid (bool)
    """
    token = _get_token(project_id)
    body = _get(f"{API_BASE}/getProcurementDetail", {"projectId": project_id}, token=token)
    if body is None or body.get("validateAnnouncementToken") == 0:
        return {"valid": False}

    data = body.get("data", {}) or {}
    return {
        "valid":             bool(data),
        "dept_sub_name":     data.get("deptSubName", "") or "",
        "budget":            float(data.get("projectMoney") or 0),
        "deliver_day":       int(data.get("deliverDay") or 0),
        "report_date":       _parse_iso_to_thai(data.get("reportDate", "")),
        "moi_name":          data.get("moiName", "") or "",
        "plan_project_name": data.get("planProjectName", "") or "",
    }


def get_procure_result(project_id: str) -> dict:
    """
    เรียก getProcureResult?projectId=X → dict winner info + full bidders list

    Return keys (winner level):
      winner (str), winning_price (str), announce_date (str),
      discount_pct (str — ต้องคำนวณเอง จาก budget)
    Return key (full):
      bidders (list[dict]): receiveNameTh, receiveTin, priceProposal,
                            priceAgree, resultFlag, is_sme, jv_partners, considerDesc
    """
    token = _get_token(project_id)
    body = _get(f"{API_BASE}/getProcureResult", {"projectId": project_id}, token=token)
    if body is None:
        return {}

    data = body.get("data", {}) or {}
    announce_date = _parse_iso_to_thai(data.get("announceDate", ""))

    bidders = []
    winner_name  = ""
    winner_price = ""

    for group in data.get("procureResultList", []) or []:
        consider_desc = group.get("considerDesc", "") or ""
        for item in group.get("procureResultDataResponse", []) or []:
            price_agree   = item.get("priceAgree")
            price_proposal = item.get("priceProposal")
            jv_list = item.get("jointVentureAndConsortiumsResponseList", []) or []
            jv_names = [jv.get("receiveNameTh", "") for jv in jv_list if jv.get("receiveNameTh")]

            b = {
                "receiveNameTh":  item.get("receiveNameTh", "") or "",
                "receiveTin":     item.get("receiveTin", "") or "",
                "priceProposal":  str(price_proposal) if price_proposal is not None else "",
                "priceAgree":     str(price_agree)    if price_agree    is not None else "",
                "resultFlag":     item.get("resultFlag", "") or "",
                "is_sme":         item.get("scoreTypeId", "") == "SME",
                "is_jv":          bool(jv_names),
                "jv_partners":    ", ".join(jv_names),
                "considerDesc":   consider_desc,
            }
            bidders.append(b)

            if price_agree is not None and not winner_name:
                winner_name  = item.get("receiveNameTh", "") or ""
                winner_price = str(price_agree)

    if not winner_name:
        return {"bidders": bidders}

    return {
        "winner":       winner_name,
        "winning_price": winner_price,
        "announce_date": announce_date,
        "bidders":       bidders,
    }


def download_pdf(template_id: str) -> Optional[bytes]:
    """
    ดาวน์โหลด PDF จาก egp-template-service โดยตรง
    template_id มาจาก RSS <link> field (UUID-like string)
    คืนค่า bytes หรือ None ถ้าล้มเหลว
    """
    try:
        r = requests.get(
            PDF_BASE,
            params={"templateId": template_id},
            headers=HEADERS,
            timeout=30,
        )
        if r.ok and r.headers.get("Content-Type", "").startswith("application/pdf"):
            return r.content
    except Exception:
        pass
    return None


if __name__ == "__main__":
    # Quick test
    import json
    test_id = "68119564509"
    print(f"Testing getProjectDetail for {test_id}...")
    d = get_project_detail(test_id)
    print(json.dumps(d, ensure_ascii=False, indent=2))

    print(f"\nTesting getProcureResult for {test_id}...")
    w = get_procure_result(test_id)
    bidders = w.pop("bidders", [])
    print(json.dumps(w, ensure_ascii=False, indent=2))
    print(f"Bidders: {len(bidders)} คน")
    for b in bidders:
        flag = "✅" if b["resultFlag"] == "P" else "  "
        sme  = "[SME]" if b["is_sme"] else ""
        print(f"  {flag} {b['receiveNameTh'][:40]:40s} {sme:6s} {b['priceProposal']}")
