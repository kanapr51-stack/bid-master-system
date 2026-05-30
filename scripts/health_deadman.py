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


def check() -> list:
    """คืน list ของ (issue_key, severity, message)"""
    issues = []
    now = _now()

    # --- token checks ---
    tok = _load_json(TOKEN_FILE)
    if not tok:
        issues.append(("token_missing", "CRITICAL", "token_state.json อ่านไม่ได้/หาย"))
    else:
        exp = tok.get("expires_at") or 0
        last_refresh = tok.get("last_refresh_attempt") or 0
        if now >= exp:
            mins = int((now - exp) / 60)
            issues.append(("token_expired", "CRITICAL",
                           f"VPS token หมดอายุ {mins} นาทีแล้ว → discovery ดึงงานใหม่ไม่ได้ "
                           f"(harvest pipeline พัง — ต้อง re-harvest บน Windows)"))
        if last_refresh and (now - last_refresh) > HARVEST_STALE_SEC:
            mins = int((now - last_refresh) / 60)
            issues.append(("harvest_stale", "CRITICAL",
                           f"ไม่มี harvest refresh attempt {mins} นาที "
                           f"(Windows task หยุด/เครื่องดับ?)"))

    # --- discovery heartbeat checks ---
    hb = _load_json(HEARTBEAT_FILE)
    if hb is None:
        issues.append(("discovery_no_heartbeat", "WARN",
                       "ไม่มี heartbeat discovery (ยังไม่เคยรันหลัง deploy?)"))
    else:
        ts = _iso_to_epoch(hb.get("ts"))
        if ts and (now - ts) > DISCOVERY_STALE_SEC:
            hrs = round((now - ts) / 3600, 1)
            issues.append(("discovery_stale", "WARN",
                           f"discovery ไม่ได้รัน {hrs} ชม. (timer หยุด?)"))
        if hb.get("status") == "no_data":
            issues.append(("discovery_nodata", "WARN",
                           "discovery รอบล่าสุดได้ 0 รายการ (token reject / API ผิดปกติ?)"))

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
        body = head + "\n" + "\n".join(f"• {m}" for m in (crit + warn))
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
