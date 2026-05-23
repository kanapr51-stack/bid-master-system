"""
process5_http_client.py — HTTP-only wrapper สำหรับ eGP process5 API

Discovery 2026-05-19: getProjectDetail / getProcureResult / PDF download
ผ่าน Cloudflare ได้ด้วย Mozilla UA + Referer โดยไม่ต้อง Chrome เลย

Usage:
    from process5_http_client import get_project_detail, get_procure_result, download_pdf
"""

import sys
import time
import random
import requests
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")

PROCESS5_BASE = "https://process5.gprocurement.go.th"
API_BASE      = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement"
PDF_BASE      = f"{PROCESS5_BASE}/egp-template-service/dwnt/view-pdf-file"

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

TIMEOUT     = 15  # วินาที ต่อ request
MAX_RETRIES = 3
_RL_BASE    = 30  # exponential backoff base (วินาที)
_RL_CAP     = 300 # cap สูงสุด (5 นาที)


def _rl_sleep(attempt: int):
    """Exponential backoff + jitter: 30s → 60s → 120s (+ random 0-15s)"""
    wait = min(_RL_BASE * (2 ** (attempt - 1)), _RL_CAP) + random.uniform(0, 15)
    time.sleep(wait)


def _get(url: str, params: dict = None, retries: int = MAX_RETRIES) -> Optional[dict]:
    """
    GET url → JSON dict หรือ None ถ้าล้มเหลวหลัง retry ครบ
    Rate limit detection: response code 429 หรือ body ที่มี 'Rate limit'
    Backoff: exponential 30s→60s→120s + jitter แทน fixed 90s
    """
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429:
                if attempt < retries:
                    _rl_sleep(attempt)
                    continue
                return None
            if not r.ok:
                return None
            text = r.text
            if "Rate limit" in text or "rate limit" in text.lower():
                if attempt < retries:
                    _rl_sleep(attempt)
                    continue
                return None
            return r.json()
        except requests.Timeout:
            if attempt < retries:
                time.sleep(3 * attempt)
                continue
            return None
        except Exception:
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
    body = _get(f"{API_BASE}/getProjectDetail", {"projectId": project_id})
    if body is None:
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
    body = _get(f"{API_BASE}/getProcureResult", {"projectId": project_id})
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
