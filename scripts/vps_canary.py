"""vps_canary.py — VPS self-canary (P1-followup 2026-06-01)

แทน Windows BidMaster_WAF_Pulse ที่ disabled (canary frozen ตั้งแต่ 05-29) +
interim fix ตัด git push → Windows canary ไม่ sync VPS แล้ว. VPS ต้อง probe เอง.

ทำ: ยิง search canary (count_d0 นครพนม ผ่าน X-Announcement-Token) → ตัดสิน
HEALTHY / BLOCKED (rate-limited) / UNKNOWN (token reject) → เขียน api_ingestion_state
ที่ app/data (= path ที่ Enrichment_Worker._api_state() อ่าน. gate line 303 skip ถ้า !HEALTHY).

note: เขียน api_ingestion_state ผ่าน bms_paths.runtime_path → /opt/bms/data (เดียวกับ worker
หลัง migration 2026-06-05). เดิมเขียน app/data — migration N+8x ย้ายทั้ง worker+canary พร้อมกัน.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Province_Discovery as disc
import bms_paths  # single runtime-state authority (BMS_DATA_DIR) — post-migration 2026-06-05

TZ_TH = timezone(timedelta(hours=7))
STATE_FILE = bms_paths.runtime_path("api_ingestion_state.json")   # worker อ่านที่เดียวกัน (/opt/bms/data)
TOKEN_FILE = Path(os.environ.get("BMS_DATA_DIR") or str(Path(__file__).parent.parent / "data")) / "token_state.json"
CANARY_MOI = "480000"   # นครพนม
BUDGET_YEAR = "2569"


def _now() -> str:
    return datetime.now(TZ_TH).isoformat()


def probe_state() -> str:
    try:
        tok = (json.loads(TOKEN_FILE.read_text(encoding="utf-8")) or {}).get("token")
    except Exception as e:
        print(f"[canary] token load fail: {e}", file=sys.stderr)
        return "UNKNOWN"
    if not tok:
        return "UNKNOWN"
    try:
        total, _pages = disc.count_d0(tok, CANARY_MOI, BUDGET_YEAR)
    except disc.RateLimited:
        return "BLOCKED"
    except Exception as e:
        print(f"[canary] probe error: {e}", file=sys.stderr)
        return "UNKNOWN"
    if total == -2:
        return "BLOCKED"        # rate limited
    if total < 0:
        return "UNKNOWN"        # token reject / validateCfTurnstile
    return "HEALTHY"


def main():
    new_state = probe_state()
    try:
        st = json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        st = {}
    prev = st.get("api_state", "UNKNOWN")
    st["previous_state"] = prev
    st["api_state"] = new_state
    st["updated_at"] = _now()
    st["canary_source"] = "vps_self_canary"
    if new_state == "HEALTHY":
        st["last_canary_success"] = _now()
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[canary] {prev} -> {new_state} @ {_now()}")
    return 0 if new_state != "UNKNOWN" else 0   # ไม่ทำให้ systemd failed (UNKNOWN = transient)


if __name__ == "__main__":
    sys.exit(main())
