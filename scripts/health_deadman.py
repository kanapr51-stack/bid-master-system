"""
health_deadman.py — Dead-Man Switch (P1, 2026-05-30 ChatGPT+Claude converged)

ระบบ live แล้ว → failure mode ที่อันตรายสุด = SILENT FAILURE
("harvest report success แต่ token stale" — เจอจริง 2026-05-30)
หน้าที่: เปลี่ยน silent failure → observable failure (Discord alert) ภายในไม่กี่นาที

รันบน VPS ทุก 15 นาที (bms-deadman.timer). ตรวจ:
  1. TOKEN_EXPIRED   — VPS token หมดอายุ (harvest pipeline พัง) [CRITICAL, fast]
  2. HARVEST_STALE   — ไม่มี refresh attempt > 40 นาที (Windows task/เครื่องตาย) [CRITICAL]
  3. DISCOVERY_STALE — discovery ไม่รัน > 14 ชม. (เผื่อ overnight gap 12 ชม.) [WARN]
  4. DISCOVERY_NODATA— discovery รอบล่าสุดได้ 0 (token reject?) [WARN]
  5. WORKER_STALE    — enrichment worker ไม่รัน > 12 นาที (timer/process ตาย) [CRITICAL]
  6. RESOLVE_DEAD    — resolve ไม่สำเร็จ > 75 นาที + มี pending + ไม่ cooldown (= INC-001 ตายเงียบ) [CRITICAL]
  7. RESOLVE_STUCK   — cooldown ค้าง + ไม่สำเร็จ > 2 ชม (WAF/outage ยาว) [CRITICAL]
  (5-7 = INC-001 P1: ปิด gap resolve plane ที่เคยพังเงียบ 1.5 วัน — L-004)

cooldown 60 นาที/issue (กัน spam) — state ใน deadman_state.json
exit 0 = healthy, exit 1 = มี alert (ไว้ดูใน journal)
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = os.environ.get("BMS_DATA_DIR", "/opt/bms/data")
TOKEN_FILE = os.path.join(DATA_DIR, "token_state.json")
HEARTBEAT_FILE = os.path.join(DATA_DIR, "last_discovery_run.json")
STATE_FILE = os.path.join(DATA_DIR, "deadman_state.json")

HARVEST_STALE_SEC = 40 * 60        # harvest ทุก 25 นาที → >40 นาที = ผิดปกติ
DISCOVERY_STALE_SEC = 14 * 60 * 60  # รัน 07/13/19 → overnight gap 12 ชม. → ใช้ 14 ชม.
COOLDOWN_SEC = 60 * 60             # alert ซ้ำ issue เดิมไม่ถี่กว่า 60 นาที

# INC-001 P1: resolve-plane health — ปิด gap ที่ทำให้ production ตายเงียบ 1.5 วัน (L-004)
# heartbeat เขียนโดย Enrichment_Worker ที่ app/data (ไม่ใช่ BMS_DATA_DIR — deploy-debt 2 dir)
APP_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
RESOLVE_HB_FILE = os.path.join(APP_DATA_DIR, "resolve_heartbeat.json")
WORKER_STALE_SEC  = 12 * 60      # worker รันทุก 2 นาที → >12 นาที = timer/worker ตาย
RESOLVE_DEAD_SEC  = 75 * 60      # resolve ไม่สำเร็จ >75 นาที + มี pending + ไม่ cooldown = ตายเงียบ
RESOLVE_STUCK_SEC = 120 * 60     # cooldown ค้าง + ไม่สำเร็จ >2 ชม = resolve plane ลงจริง


def _now() -> float:
    return time.time()


def _load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def _iso_to_epoch(s):
    """'2026-05-30T16:00:00Z' → epoch. คืน None ถ้า parse ไม่ได้"""
    if not s:
        return None
    try:
        import datetime as dt
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc).timestamp()
    except Exception:
        return None


def _iso_any(s):
    """รองรับ ISO ที่มี offset ('...+07:00' จาก worker._now()) + fallback Z-format"""
    if not s:
        return None
    try:
        import datetime as dt
        return dt.datetime.fromisoformat(s).timestamp()
    except Exception:
        return _iso_to_epoch(s)


def check() -> list:
    """คืน list ของ (issue_key, severity, message)"""
    issues = []
    now = _now()

    # --- token checks ---
    # หลักการ: alert = อาการ (ตัวเลข/fact) เท่านั้น — ไม่เดาสาเหตุ (กัน confirmation bias)
    # สาเหตุที่เป็นไปได้ + วิธีแก้ ดู deploy/RUNBOOK.md
    tok = _load_json(TOKEN_FILE)
    if not tok:
        issues.append(("token_missing", "CRITICAL", "TOKEN_STATE หาย/อ่านไม่ได้"))
    else:
        exp = tok.get("expires_at") or 0
        last_refresh = tok.get("last_refresh_attempt") or 0
        if now >= exp:
            mins = int((now - exp) / 60)
            issues.append(("token_expired", "CRITICAL",
                           f"TOKEN EXPIRED — หมดอายุ {mins} นาที (TTL remaining: 0)"))
        if last_refresh and (now - last_refresh) > HARVEST_STALE_SEC:
            mins = int((now - last_refresh) / 60)
            issues.append(("harvest_stale", "CRITICAL",
                           f"NO REFRESH — ไม่มี harvest refresh attempt {mins} นาที"))

    # --- discovery heartbeat checks ---
    hb = _load_json(HEARTBEAT_FILE)
    if hb is None:
        issues.append(("discovery_no_heartbeat", "WARN",
                       "NO HEARTBEAT — ไม่มี heartbeat discovery"))
    else:
        ts = _iso_to_epoch(hb.get("ts"))
        if ts and (now - ts) > DISCOVERY_STALE_SEC:
            hrs = round((now - ts) / 3600, 1)
            issues.append(("discovery_stale", "WARN",
                           f"DISCOVERY STALE — ไม่มี discovery run {hrs} ชม."))
        if hb.get("status") == "no_data":
            issues.append(("discovery_nodata", "WARN",
                           "DISCOVERY NO_DATA — discovery รอบล่าสุดได้ 0 รายการ"))

    # --- resolve plane checks (INC-001 P1: กันพังเงียบแบบ resolve-down) ---
    # alert = อาการ (fact) เท่านั้น — ไม่เดาสาเหตุ. วิธีแก้ ดู deploy/RUNBOOK.md
    hb_r = _load_json(RESOLVE_HB_FILE)
    if hb_r is None:
        issues.append(("resolve_no_heartbeat", "WARN",
                       "RESOLVE NO HEARTBEAT — worker ยังไม่เคยเขียน resolve_heartbeat"))
    else:
        last_run = _iso_any(hb_r.get("last_run_at"))
        last_ok  = _iso_any(hb_r.get("last_resolve_success_at"))
        pending  = hb_r.get("pending") or 0
        in_cd    = bool(hb_r.get("in_cooldown"))
        # worker liveness — timer/process ตาย
        if last_run and (now - last_run) > WORKER_STALE_SEC:
            mins = int((now - last_run) / 60)
            issues.append(("worker_stale", "CRITICAL",
                           f"ENRICHMENT WORKER STALE — ไม่รัน {mins} นาที (ปกติทุก 2 นาที)"))
        if last_ok:
            stale = now - last_ok
            # resolve ตายเงียบ (= INC-001): worker รันอยู่ แต่ resolve ไม่สำเร็จ + มีงานค้าง + ไม่ได้ตั้งใจ cooldown
            if not in_cd and stale > RESOLVE_DEAD_SEC and pending > 0:
                issues.append(("resolve_dead", "CRITICAL",
                               f"RESOLVE PLANE DEAD — resolve ไม่สำเร็จ {int(stale/60)} นาที ทั้งที่ค้าง {pending} งาน (WAF/token?)"))
            # cooldown ค้าง ฟื้นไม่ขึ้น = WAF/outage ยาว
            if in_cd and stale > RESOLVE_STUCK_SEC:
                issues.append(("resolve_stuck_cooldown", "CRITICAL",
                               f"RESOLVE STUCK IN COOLDOWN — ไม่สำเร็จ {int(stale/60)} นาที, cooldown ฟื้นไม่ขึ้น (WAF ยาว?)"))

    return issues


def _alertable(issues, state):
    """กรอง issue ที่ยังอยู่ใน cooldown ออก, อัปเดต state"""
    now = _now()
    out = []
    for key, sev, msg in issues:
        last = state.get(key, 0)
        if now - last >= COOLDOWN_SEC:
            out.append((key, sev, msg))
            state[key] = now
    return out


def main() -> int:
    issues = check()
    if not issues:
        print("✅ dead-man: healthy (token + discovery OK)")
        return 0

    state = _load_json(STATE_FILE) or {}
    to_alert = _alertable(issues, state)
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass

    for key, sev, msg in issues:
        print(f"{sev} [{key}] {msg}")

    if to_alert:
        crit = [m for k, s, m in to_alert if s == "CRITICAL"]
        warn = [m for k, s, m in to_alert if s == "WARN"]
        head = "🔴 BMS DEAD-MAN ALERT" if crit else "🟠 BMS health warning"
        body = (head + "\n" + "\n".join(f"• {m}" for m in (crit + warn))
                + "\n📋 สาเหตุที่เป็นไปได้ + วิธีแก้: deploy/RUNBOOK.md")
        try:
            from Sebastian_Discord_Notify import load_env, get_credentials, send
            load_env()
            t, ch = get_credentials()
            send(t, ch, body)
            print(f"→ Discord alert ส่งแล้ว ({len(to_alert)} issue)")
        except Exception as e:
            print(f"⚠️ Discord ส่งไม่ได้: {e}")
    else:
        print(f"(มี {len(issues)} issue แต่ยังอยู่ใน cooldown — ไม่ alert ซ้ำ)")
    # exit 0 เสมอ: หน้าที่คือ check+alert สำเร็จ — การเจอ issue ไม่ใช่ service failure
    # (ถ้า return 1 systemd จะ mark unit 'failed' = noise + อาจ trigger alert ซ้อน)
    return 0


if __name__ == "__main__":
    sys.exit(main())
