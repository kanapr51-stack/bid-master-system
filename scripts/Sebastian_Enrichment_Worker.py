"""
Sebastian_Enrichment_Worker.py — Enrichment Plane (2026-05-29)

Role: Take pending project_locations → enrich via eGP API → enqueue notification

  RSS Notifier  → project_locations(pending)
  THIS WORKER   → getProcurementDetail → hard location → enqueue if target province
  LINE Sender   → deliver notification

Design (ChatGPT-confirmed 2026-05-29 · revised INC-001 Rev 3 2026-06-03):
  - Batch: env-tunable, default 5/pass (ADR-003 throughput envelope < burst ~30)
  - Sleep: 1.5s between projects → 2 calls/1.5s ≈ 1.3 req/s/type, safe
  - Enrich ALL projects (not just target) — build canonical intelligence layer
  - WAF downtime: skip run when api_state != HEALTHY
  - INC-001 Rev 3: resolve-plane COOLDOWN — circuit-break (Pass1/Pass3) ตั้ง cooldown
    ข้าม run (default 45m > WAF cooldown) กัน positive feedback loop (worker timer
    2นาที << WAF cooldown 30-40นาที → ต่ออายุ block เอง). ดู docs/lessons_learned.md L-005

Run: every 2 min via systemd timer (bms-enrichment-worker)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bms_paths  # noqa: E402  — runtime-state single authority (BMS_DATA_DIR)
from Sebastian_Customer_DB import (SubscriptionStore, init_schema, get_connection, _now, _now_plus,
                                   save_project_location_raw)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────

TARGET_PROVINCES  = {"นครพนม", "บึงกาฬ"}
# INC-001 Rev 3 (ADR-003 Rate-Limited Resolve): throughput envelope เล็กลง + env-tunable
# (กัญจน์ lock "need adaptive rate control" ไม่ lock ตัวเลข → default conservative, ปรับผ่าน env)
# รวม 3 pass/run ต้อง < burst ~30 generateToken: default 5+5+5=15 projects << 30
BATCH_SIZE        = int(os.environ.get("BMS_ENRICH_BATCH", "5"))      # Pass 1 (RSS)
SLEEP_BETWEEN_SEC = float(os.environ.get("BMS_ENRICH_SLEEP", "1.5"))
RETRY_DELAY_MIN   = 30
MAX_ATTEMPTS      = 5
PROVINCE_QUAL_BATCH = int(os.environ.get("BMS_QUAL_BATCH", "5"))   # Pass 3 (province_api)
MAX_QUAL_ATTEMPTS   = 5    # macro-retry transient (provider error) จน MAX แล้ว fail
CIRCUIT_BREAK       = 5    # provider errors ติดกัน → หยุด batch (กัน WAF/outage)
# INC-001 Rev 3: cross-run cooldown — เมื่อตรวจพบ WAF/circuit-break → หยุดทั้ง plane
# กัน positive feedback loop (worker timer 2นาที << WAF cooldown 30-40นาที → ต่ออายุ block เอง 1.5 วัน)
RESOLVE_COOLDOWN_MIN = int(os.environ.get("BMS_RESOLVE_COOLDOWN_MIN", "45"))  # > observed WAF cooldown
RESOLVE_STATE_PATH = bms_paths.runtime_path("resolve_plane_state.json")
API_STATE_PATH     = bms_paths.runtime_path("api_ingestion_state.json")
LOG_DIR           = Path(__file__).parent.parent / "logs" / "enrichment_worker"
TZ_TH             = timezone(timedelta(hours=7))

# RSS Shadow Mode: gate RSS path enqueue ด้วย discovery_confirmed (reversible ด้วย env)
BMS_RSS_NOTIFY = os.environ.get("BMS_RSS_NOTIFY", "on").strip().lower()


def _rss_gate_ok(pid: str) -> bool:
    """RSS path enqueue gate.
    BMS_RSS_NOTIFY=on  → ผ่านเสมอ (พฤติกรรมเดิม)
    BMS_RSS_NOTIFY=off → ผ่านเฉพาะงานที่ Discovery ประทับตราแล้ว (discovery_confirmed=1)"""
    if BMS_RSS_NOTIFY != "off":
        return True
    with get_connection() as conn:
        row = conn.execute(
            "SELECT discovery_confirmed FROM project_locations WHERE project_id=?", (pid,)
        ).fetchone()
    return bool(row and row[0])

MOI_PROVINCE_MAP = {
    "38": "บึงกาฬ",
    "48": "นครพนม",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _api_state() -> str:
    try:
        if API_STATE_PATH.exists():
            return json.loads(API_STATE_PATH.read_text(encoding="utf-8-sig")).get("api_state", "UNKNOWN")
    except Exception:
        pass
    return "UNKNOWN"


# ── INC-001 Rev 3: Resolve-plane cooldown (L-005 cooldown + recovery state) ──────
# Resolve plane มี health signal ของตัวเอง (L-003) แยกจาก Discovery api_state

def _resolve_in_cooldown() -> tuple[bool, str]:
    """True ถ้า resolve plane อยู่ใน cooldown (เพิ่งโดน WAF/circuit-break) → skip run.
    กัน positive feedback loop: worker ยิงก่อน WAF cooldown ครบ → ต่ออายุ block เอง.
    เทียบ ISO string (รูปแบบเดียวกับ next_retry_at — sortable)."""
    try:
        if RESOLVE_STATE_PATH.exists():
            d = json.loads(RESOLVE_STATE_PATH.read_text(encoding="utf-8-sig"))
            until = d.get("cooldown_until")
            if until and _now() < until:
                return True, until
    except Exception:
        pass
    return False, ""


def _set_resolve_cooldown(reason: str) -> str:
    """ตั้ง cooldown หลังตรวจพบ WAF/circuit-break (recovery state: หยุดยาว > WAF cooldown
    แล้วค่อยกลับมายิง). คืน timestamp ที่จะพ้น cooldown."""
    until = _now_plus(RESOLVE_COOLDOWN_MIN)
    try:
        RESOLVE_STATE_PATH.write_text(
            json.dumps({"cooldown_until": until, "reason": reason, "set_at": _now()},
                       ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        pass
    return until


# ── INC-001 P1: Resolve heartbeat (กันพังเงียบ — dead-man switch ตรวจ) ───────────
# L-004: วัด business-critical path (resolve สำเร็จจริง) ไม่ใช่ synthetic probe (L-002).
# ไม่ยิง API เพิ่ม → ไม่เสี่ยง burst. last_resolve_success_at = สัญญาณ resolve plane alive.
RESOLVE_HEARTBEAT_PATH = bms_paths.runtime_path("resolve_heartbeat.json")


def _write_resolve_heartbeat(status: str, resolved_ok: int = 0,
                             pending: int = 0, in_cooldown: bool = False) -> None:
    """เขียน heartbeat ให้ deadman ตรวจ. last_resolve_success_at update เมื่อ resolve สำเร็จจริง."""
    prev = {}
    try:
        if RESOLVE_HEARTBEAT_PATH.exists():
            prev = json.loads(RESOLVE_HEARTBEAT_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        prev = {}
    last_success = prev.get("last_resolve_success_at")
    if resolved_ok > 0:
        last_success = _now()
    try:
        RESOLVE_HEARTBEAT_PATH.write_text(json.dumps({
            "last_run_at": _now(),
            "last_run_status": status,
            "last_resolve_success_at": last_success,
            "last_run_resolved_ok": resolved_ok,
            "pending": pending,
            "in_cooldown": in_cooldown,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _enrich(project_id: str) -> dict | None:
    try:
        from process5_http_client import get_procurement_detail
        data = get_procurement_detail(project_id)
        if not data.get("valid"):
            return None
        province_moi_id = str(data.get("province_moi_id") or "")
        province_name   = MOI_PROVINCE_MAP.get(province_moi_id[:2], "")
        lat = data.get("latitude") or ""
        lng = data.get("longitude") or ""
        return {
            "province_moi_id": province_moi_id,
            "district_moi_id": str(data.get("district_moi_id") or ""),
            "moi_name":        data.get("moi_name") or "",
            "province_name":   province_name,
            "latitude":        str(lat)[:200],
            "longitude":       str(lng)[:200],
        }
    except Exception:
        return None


def _save_success(project_id: str, loc: dict) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute("""
            UPDATE project_locations
            SET province_moi_id=?, district_moi_id=?, moi_name=?,
                province_name=?, latitude=?, longitude=?,
                location_confidence='hard', enrichment_status='success',
                next_retry_at=NULL, enriched_at=?,
                enrichment_attempts=enrichment_attempts+1
            WHERE project_id=?
        """, (loc["province_moi_id"], loc["district_moi_id"], loc["moi_name"],
              loc["province_name"], loc["latitude"], loc["longitude"],
              now, project_id))


def _save_retry(project_id: str, current_attempts: int) -> bool:
    """Returns True if marked permanently failed (>= MAX_ATTEMPTS), False if scheduled for retry."""
    if current_attempts + 1 >= MAX_ATTEMPTS:
        with get_connection() as conn:
            conn.execute("""
                UPDATE project_locations
                SET enrichment_status='failed',
                    enrichment_attempts=enrichment_attempts+1
                WHERE project_id=?
            """, (project_id,))
        return True
    with get_connection() as conn:
        conn.execute("""
            UPDATE project_locations
            SET next_retry_at=?, enrichment_attempts=enrichment_attempts+1
            WHERE project_id=?
        """, (_now_plus(RETRY_DELAY_MIN), project_id))
    return False


# ── Pass 3: province_api qualification (deadline gate, fail-closed) ─────────────

def _discord_safe(msg: str) -> None:
    """ส่ง Discord แบบ best-effort (preview/circuit-breaker alert) — ไม่ throw"""
    try:
        import Sebastian_Discord_Notify as dn
        dn.load_env(); tok, ch = dn.get_credentials(); dn.send(tok, ch, msg)
    except Exception:
        pass


def _province_epoch():
    """epoch_ts ของ province_api (suppress backlog ก่อน epoch นี้)"""
    with get_connection() as conn:
        r = conn.execute(
            "SELECT epoch_ts FROM source_epochs WHERE source='province_api'").fetchone()
    return r[0] if r else None


def qualify_province_api(store, log) -> int:
    """คืนจำนวน resolve สำเร็จ (RESOLVED) สำหรับ resolve heartbeat.
    province_api → notification: Epoch Gate (primary) → Deadline Gate (secondary) → fail-closed
    (ChatGPT+Claude converged 2026-05-30 — ดู memory/project_delivery_wiring_decision.md)

    - candidate = post-epoch + subscribed province + ยังไม่ qualify
    - deadline = DeadlineService (NullProvider ตอนนี้ → fail-closed = ไม่ส่งจนกว่า resolver จริงมา)
    - enqueue เฉพาะ deadline resolved + ยังเปิดยื่นซอง (deadline >= today)
    - province_api ใช้ enrichment_status='qualified' → RSS Pass1/Pass2 ไม่แตะ (กัน blast)
    """
    epoch = _province_epoch()
    if not epoch:
        log("Province qual: ไม่มี epoch — skip")
        return 0
    try:
        from deadline_service import DeadlineService, make_deadline_provider, DeadlineOutcome
    except Exception as e:
        log(f"Province qual: import deadline_service ล้มเหลว ({e}) — skip")
        return 0
    mode = os.environ.get("BMS_PROVINCE_NOTIFY_MODE", "preview")   # preview (go-live gate) | live
    dsvc = DeadlineService(make_deadline_provider())               # doczip ถ้า env BMS_DEADLINE_PROVIDER set
    # matching layer (keyword + tambon) — shadow (log only) | enforce (กรองจริง) | off
    try:
        import job_matcher as jm
        mcfg = jm.load_config()
        mmode = os.environ.get("BMS_MATCHING_MODE", "shadow")
        # keyword-first: กรอง keyword ก่อน resolve deadline/tambon (= ก่อน API call แพง)
        # off=ไม่ทำ · shadow=log เฉยๆ ไม่ skip (วัด API ที่จะประหยัด) · enforce=skip resolve จริง
        kwmode = os.environ.get("BMS_KEYWORD_FIRST_MODE", "off")
    except Exception as e:
        jm = None; mcfg = None; mmode = "off"; kwmode = "off"
        log(f"Province qual: matcher load fail ({e}) — matching off")
    now = _now()

    # (1) seed: projects_seen ใหม่ (post-epoch, subscribed) → project_locations(qualification_status='pending')
    #     enrichment_status='failed': constraint อนุญาตแค่ pending/success/failed; เลือก 'failed'
    #     เพราะ RSS Pass1(='pending')/Pass2(='success') ไม่แตะ (zero RSS-path change) —
    #     สถานะจริงของ province_api อยู่ใน qualification_status
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO project_locations
              (project_id, province_name, location_confidence, enrichment_status,
               created_at, source, need_location, qualification_status, enrichment_attempts)
            SELECT ps.project_id, ps.province, 'hard', 'failed', ?, 'province_api', 0, 'pending', 0
            FROM projects_seen ps
            WHERE ps.source='province_api' AND ps.first_seen_at >= ?
              AND ps.province IN ('นครพนม','บึงกาฬ')
              AND ps.project_id NOT IN (SELECT project_id FROM project_locations WHERE source='province_api')
        """, (now, epoch))

    # (2) process pending (รวม retry transient — attempts < MAX)
    with get_connection() as conn:
        cands = conn.execute("""
            SELECT pl.project_id, pl.enrichment_attempts, ps.province, ps.announce_type,
                   ps.budget, ps.project_name, ps.dept_name, ps.announce_date
            FROM project_locations pl
            LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE pl.source='province_api' AND pl.qualification_status='pending'
              AND pl.enrichment_attempts < ?
            ORDER BY pl.created_at ASC
            LIMIT ?
        """, (MAX_QUAL_ATTEMPTS, PROVINCE_QUAL_BATCH)).fetchall()
    cands = [dict(r) for r in cands]
    if not cands:
        log("Province qual: 0 pending candidates — OK (backlog suppressed)")
        return 0
    log(f"Province qual: {len(cands)} pending (mode={mode})")

    TRANSIENT = (DeadlineOutcome.PROVIDER_ERROR, DeadlineOutcome.DOWNLOAD_FAILED)
    stats = {"enqueued": 0, "preview": 0, "expired": 0, "failed": 0, "retry": 0,
             "filtered": 0, "soft": 0, "kw_skip": 0}
    consec_err = 0
    for c in cands:
        pid = c["project_id"]

        # ── B0 รับฟังคำวิจารณ์ (early-radar): ไม่มี bidding deadline → ข้าม deadline gate ──
        # match proc-aware (จ้าง=ก่อสร้าง / ซื้อ=วัสดุ BSC) + location จากชื่อ (ไม่ resolve API = INC-001 safe)
        # อยู่ก่อน keyword-first (ซึ่งเช็คคำก่อสร้างอย่างเดียว → จะตัดงานซื้อวัสดุผิด)
        if (c.get("announce_type") or "").upper().startswith("B"):
            # freshness gate: B0 comment period สั้น + backlog เก่า first_seen=วันนี้ →
            # ส่งเฉพาะ announce_date ใน N วันล่าสุด (กัน blast backlog 400+ งาน, env BMS_TOR_FRESH_DAYS)
            tor_days = int(os.environ.get("BMS_TOR_FRESH_DAYS", "14"))
            if jm is None or not jm.tor_is_fresh(c.get("announce_date") or "", days=tor_days):
                with get_connection() as conn:
                    conn.execute("UPDATE project_locations SET qualification_status='suppressed_tor_stale' WHERE project_id=?", (pid,))
                stats["expired"] = stats.get("expired", 0) + 1
                continue
            src_stage = "province_tor_review"
            if jm is not None and mmode != "off":
                decision, mdet = jm.match_job(c.get("project_name") or "", c["province"],
                                              "", c.get("dept_name") or "", cfg=mcfg)
                log(f"  match[tor:{mmode}] {pid}: {decision} ({mdet.get('reason')})")
                if mmode == "enforce" and decision == "cut":
                    with get_connection() as conn:
                        conn.execute("UPDATE project_locations SET qualification_status='filtered_no_match' WHERE project_id=?", (pid,))
                    stats["filtered"] += 1
                    continue
                if decision == "soft_include":
                    src_stage = "province_tor_review_soft"; stats["soft"] += 1
            if mode == "live":
                n = store.enqueue_notifications({
                    "project_id": pid, "province": c["province"], "announce_type": "B0",
                    "budget": int(c.get("budget") or 0), "project_name": c.get("project_name") or "",
                    "dept_name": c.get("dept_name") or "", "extraction_confidence": "high",
                    "is_backfill": False, "source_stage": src_stage,
                }, min_confidence="high")
                status = "enqueued" if n > 0 else "enqueued_dedup"
                if n > 0:
                    stats["enqueued"] += 1
                    log(f"  → ENQUEUED(รับฟังคำวิจารณ์) {pid} {c['province']} [{src_stage}]")
            else:
                _discord_safe(
                    f"🔎 [PREVIEW] รับฟังคำวิจารณ์ (ยังไม่ส่ง LINE)\n"
                    f"{pid} | {c['province']} | ฿{int(c.get('budget') or 0):,}\n{(c.get('project_name') or '')[:60]}")
                status = "preview_held"; stats["preview"] += 1
            with get_connection() as conn:
                conn.execute("UPDATE project_locations SET qualification_status=? WHERE project_id=?", (status, pid))
            continue

        # ── keyword-first pre-filter: กรองก่อน resolve (deadline PDF + tambon = 2 API call) ──
        if jm is not None and kwmode != "off":
            kw_pass, kw_reason = jm.passes_keyword(c.get("project_name") or "", mcfg)
            if not kw_pass:
                stats["kw_skip"] += 1
                if kwmode == "enforce":
                    with get_connection() as conn:
                        conn.execute("UPDATE project_locations SET qualification_status='filtered_no_keyword' WHERE project_id=?", (pid,))
                    log(f"  → ✂️ KW-FILTERED {pid} ({kw_reason}) — skip resolve (ประหยัด 2 API)")
                    continue
                else:  # shadow — log อย่างเดียว ไม่ skip (resolve ต่อตามปกติ เพื่อไม่เปลี่ยน production)
                    log(f"  [kw-first SHADOW] {pid}: would SKIP ({kw_reason}) → ประหยัด deadline+tambon API")

        res = dsvc.resolve(pid)

        # circuit breaker (Caveat 3) — provider error ติดกัน = WAF/outage → หยุด ไม่ยิงรัว
        if res.outcome in TRANSIENT:
            consec_err += 1
            if consec_err >= CIRCUIT_BREAK:
                cd_until = _set_resolve_cooldown(f"pass3_circuit_break_{consec_err}_provider_errors")
                log(f"⚡ circuit breaker: {consec_err} provider errors ติดกัน — abort + cooldown ถึง {cd_until}")
                _discord_safe(
                    f"⚡ BMS resolve plane WAF/outage — {consec_err} errors ติดกัน\n"
                    f"→ COOLDOWN ถึง {cd_until} (INC-001 Rev3 backoff กัน self-sustained loop)")
                break
        else:
            consec_err = 0

        # transient → macro-retry (คง pending รอบหน้า จน MAX)
        if res.outcome in TRANSIENT:
            new_att = c["enrichment_attempts"] + 1
            st = f"failed_{res.outcome.value}" if new_att >= MAX_QUAL_ATTEMPTS else "pending"
            stats["failed" if st.startswith("failed") else "retry"] += 1
            with get_connection() as conn:
                conn.execute("UPDATE project_locations SET qualification_status=?, enrichment_attempts=? WHERE project_id=?",
                             (st, new_att, pid))
            continue

        # P1 audit: เก็บ deadline ที่ resolve ได้ลง DB (cross-check ฟรี — ดู Customer_DB _migrate_v113)
        if res.outcome == DeadlineOutcome.RESOLVED and res.deadline:
            with get_connection() as conn:
                conn.execute("UPDATE project_locations SET deadline=? WHERE project_id=?",
                             (str(res.deadline), pid))

        # terminal outcomes
        if res.outcome == DeadlineOutcome.RESOLVED and res.is_open():
            # matching layer (keyword + tambon + soft-include) — shadow log / enforce apply
            src_stage = "province_qualified"
            if jm is not None and mmode != "off":
                # capture เต็มจาก getProcurementDetail (API call เท่าเดิม) — เก็บ raw location
                # ให้ intel disambiguate ระดับตำบล/อำเภอ (MOI disambiguation Phase A)
                from process5_http_client import get_procurement_detail
                _d = get_procurement_detail(pid)
                tb = (_d.get("moi_name") or "") or jm.tambon_from_dept(c.get("dept_name") or "")
                if _d.get("valid"):
                    save_project_location_raw(pid, _d.get("district_moi_id") or "",
                                              _d.get("moi_name") or "",
                                              _d.get("latitude") or "", _d.get("longitude") or "")
                    # coverage log (ไม่ persist) — วัด % lat/lng & moi ในงานจริง (calibrate Phase B)
                    log(f"  loc captured {pid} has_moi={bool(_d.get('moi_name'))} "
                        f"has_district={bool(_d.get('district_moi_id'))} "
                        f"has_coord={bool(_d.get('latitude'))}")
                decision, mdet = jm.match_job(c.get("project_name") or "", c["province"], tb,
                                              c.get("dept_name") or "", cfg=mcfg)
                log(f"  match[{mmode}] {pid}: {decision} (tb={tb or '-'}, {mdet.get('reason')})")
                if mmode == "enforce":
                    if decision == "cut":
                        with get_connection() as conn:
                            conn.execute("UPDATE project_locations SET qualification_status='filtered_no_match' WHERE project_id=?", (pid,))
                        stats["filtered"] += 1
                        log(f"  → ✂️ FILTERED {pid} (ไม่ตรง: {mdet.get('reason')})")
                        continue
                    if decision == "soft_include":
                        src_stage = "province_soft_location"
                        stats["soft"] += 1
            if mode == "live":
                n = store.enqueue_notifications({
                    "project_id": pid, "province": c["province"],
                    "announce_type": c.get("announce_type") or "D0",
                    "budget": int(c.get("budget") or 0),
                    "project_name": c.get("project_name") or "",
                    "dept_name": c.get("dept_name") or "",
                    "extraction_confidence": "high", "is_backfill": False,
                    "source_stage": src_stage,
                }, min_confidence="high")
                status = "enqueued" if n > 0 else "enqueued_dedup"
                if n > 0:
                    stats["enqueued"] += 1
                    log(f"  → ENQUEUED {pid} {c['province']} deadline={res.deadline} [{src_stage}]")
            else:  # preview go-live gate — ส่ง Discord แทน LINE, ไม่ enqueue
                _discord_safe(
                    f"🔎 [PREVIEW] province_api candidate (ยังไม่ส่ง LINE)\n"
                    f"{pid} | {c['province']} | ฿{int(c.get('budget') or 0):,}\n"
                    f"{(c.get('project_name') or '')[:60]}\n"
                    f"deadline={res.deadline} (เหลือ {(res.deadline - date.today()).days} วัน)")
                status = "preview_held"; stats["preview"] += 1
                log(f"  → PREVIEW {pid} deadline={res.deadline} (held, mode=preview)")
        elif res.outcome == DeadlineOutcome.RESOLVED:
            status = "suppressed_expired"; stats["expired"] += 1
        else:  # NO_DOCUMENT / PARSE_FAILED / DEADLINE_NOT_FOUND → terminal fail-closed
            status = f"failed_{res.outcome.value}"; stats["failed"] += 1

        with get_connection() as conn:
            conn.execute("UPDATE project_locations SET qualification_status=? WHERE project_id=?",
                         (status, pid))

    log(f"Province qual done — enqueued={stats['enqueued']} preview={stats['preview']} "
        f"expired={stats['expired']} failed={stats['failed']} retry={stats['retry']} "
        f"| match[{mmode}] filtered={stats['filtered']} soft={stats['soft']} "
        f"| kw-first[{kwmode}] skip={stats['kw_skip']} (= API call ที่ประหยัดได้ตอน enforce)")
    # resolved_ok = outcome RESOLVED (deadline provider สำเร็จ = generateToken+doczip ผ่าน)
    return stats["enqueued"] + stats["preview"] + stats["expired"]


# ── Main ─────────────────────────────────────────────────────────────────────

def notify_bid_open_followups(store, log, resolve_deadline=None) -> int:
    """⭐ B0→D0: งานที่ติดดาวตอนรับฟังฯ เลื่อนเป็นประมูลแล้ว → แจ้งเฉพาะคนติดดาว (targeted, ไม่ fan-out).
    อ่าน stage ปัจจุบันจาก projects_seen (advance-stage สะท้อน lifecycle จริง).
    resolve deadline เฉพาะงานที่เลื่อนจริง (น้อยมาก = ปลอดภัย INC-001) → เก็บ project_locations.deadline
    → line-sender อ่านตอนส่ง (การ์ดมี ⏰ ยื่นซอง). resolve_deadline inject ได้สำหรับ test.
    preview = shadow (log/Discord ไม่ mark, non-consuming) · live = enqueue + mark D0."""
    import job_followups as jf
    follows = store.get_active_follows()
    if not follows:
        return 0
    pids = list({f["project_id"] for f in follows})
    qs = ",".join("?" * len(pids))
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT project_id, announce_type, province, budget, project_name, dept_name "
            f"FROM projects_seen WHERE project_id IN ({qs})", pids).fetchall()
    meta = {r["project_id"]: dict(r) for r in rows}
    cur = {pid: m["announce_type"] for pid, m in meta.items()}
    due = jf.bid_open_followups([dict(f) for f in follows], cur)
    mode = os.environ.get("BMS_PROVINCE_NOTIFY_MODE", "preview")
    sent = 0
    if not due:
        return 0

    # resolve deadline ครั้งเดียวต่อ pid (เฉพาะที่เลื่อนจริง = น้อย) → เก็บ project_locations.deadline
    if resolve_deadline is None:
        try:
            from deadline_service import DeadlineService, make_deadline_provider
            _dsvc = DeadlineService(make_deadline_provider())

            def resolve_deadline(pid):
                r = _dsvc.resolve(pid)
                return str(r.deadline) if getattr(r, "deadline", None) else None
        except Exception as e:
            log(f"  followup deadline resolver unavailable ({e}) — แจ้งโดยไม่มี deadline")

            def resolve_deadline(pid):
                return None
    for pid in {p for _, p in due}:
        try:
            dl = resolve_deadline(pid)
            if dl:
                with get_connection() as conn:
                    conn.execute("UPDATE project_locations SET deadline=? WHERE project_id=?", (dl, pid))
        except Exception as e:
            log(f"  followup resolve {pid} fail (non-fatal): {e}")
    for cid, pid in due:
        m = meta.get(pid)
        if not m:
            continue
        if mode == "live":
            n = store.enqueue_for_customer(cid, {
                "project_id": pid, "province": m.get("province") or "",
                "project_name": m.get("project_name") or "", "dept_name": m.get("dept_name") or "",
                "source_stage": "followed_bid_open",
            })
            store.mark_stage_notified(cid, pid, "D0")
            if n:
                sent += 1
                log(f"  ⭐→ bid-open followup ENQUEUED {pid} cust{cid}")
        else:
            _discord_safe(f"🔎 [SHADOW] ⭐ followup เปิดประมูล: {pid} cust{cid} | "
                          f"{(m.get('project_name') or '')[:50]} (ยังไม่ส่ง/ไม่ mark)")
    if due:
        log(f"⭐ bid-open followups: {len(due)} due, {sent} enqueued (mode={mode})")
    return sent


def main():
    # migration transition: heal state ที่ copy พลาด + log resolved dir (ถอด heal Phase 4)
    bms_paths.heal_legacy_state("api_ingestion_state.json", "resolve_plane_state.json", "resolve_heartbeat.json")
    bms_paths.log_paths("api_ingestion_state.json", "resolve_plane_state.json", "resolve_heartbeat.json")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"enrichment_{datetime.now().strftime('%Y%m%d')}.log"

    def log(msg: str):
        line = f"[{_now()}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    api = _api_state()
    log(f"=== Enrichment Worker start api_state={api} ===")

    if api != "HEALTHY":
        log("API not HEALTHY — skip run")
        _write_resolve_heartbeat("skip_api")   # P1: worker ยังมีชีวิต (timer ไม่ตาย) แต่ skip
        log("=== Enrichment Worker done (skipped) ===")
        return

    # INC-001 Rev 3: resolve-plane cooldown gate (กัน positive feedback loop)
    in_cd, until = _resolve_in_cooldown()
    if in_cd:
        log(f"Resolve plane in COOLDOWN until {until} (INC-001 Rev3 backoff) — skip run")
        _write_resolve_heartbeat("skip_cooldown", in_cooldown=True)
        log("=== Enrichment Worker done (cooldown) ===")
        return

    init_schema()
    store = SubscriptionStore()
    now   = _now()

    # Pass 3: province_api qualification (epoch + deadline gate, fail-closed)
    # รันก่อน RSS batch + independent (ไม่ skip แม้ RSS queue ว่าง)
    qual_ok = 0
    try:
        qual_ok = qualify_province_api(store, log)
    except Exception as e:
        log(f"Province qual ERROR: {type(e).__name__}: {e}")

    # ⭐ B0→D0 followups: แจ้งงานติดดาวที่เปิดประมูลแล้ว (ไม่ยิง API — รันได้แม้ก่อน cooldown check)
    try:
        notify_bid_open_followups(store, log)
    except Exception as e:
        log(f"Bid-open followups ERROR: {type(e).__name__}: {e}")

    # ถ้า Pass 3 ตั้ง cooldown (circuit-break) → หยุดทันที ไม่ยิง RSS passes ต่อ (กัน burst)
    in_cd, until = _resolve_in_cooldown()
    if in_cd:
        log(f"Cooldown set by Pass 3 (until {until}) — skip RSS passes")
        _write_resolve_heartbeat("skip_cooldown_pass3", resolved_ok=qual_ok, in_cooldown=True)
        log("=== Enrichment Worker done (cooldown set) ===")
        return

    # Take batch of pending items
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT pl.project_id, ps.announce_type, ps.budget,
                   ps.project_name, ps.dept_name, pl.enrichment_attempts
            FROM project_locations pl
            LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE pl.enrichment_status = 'pending'
              AND (pl.next_retry_at IS NULL OR pl.next_retry_at <= ?)
            ORDER BY pl.enrichment_attempts ASC, pl.created_at ASC
            LIMIT ?
        """, (now, BATCH_SIZE)).fetchall()

    rows = [dict(r) for r in rows]
    log(f"Batch: {len(rows)} pending items to enrich")

    if not rows:
        log("No pending items — exit")
        with get_connection() as conn:
            qp = conn.execute(
                "SELECT COUNT(*) FROM project_locations WHERE source='province_api' "
                "AND qualification_status='pending' AND enrichment_attempts < ?",
                (MAX_QUAL_ATTEMPTS,)).fetchone()[0]
        _write_resolve_heartbeat("ok", resolved_ok=qual_ok, pending=qp)
        log("=== Enrichment Worker done ===")
        return

    stats = {"enriched": 0, "failed": 0, "target_hit": 0, "enqueued": 0, "dedup": 0}
    consec_fail = 0   # INC-001 Rev 3: Pass 1 circuit breaker (RSS path กัน WAF hammer)

    for i, row in enumerate(rows):
        pid = row["project_id"]

        loc = _enrich(pid)

        if not loc:
            consec_fail += 1
            gave_up = _save_retry(pid, row["enrichment_attempts"])
            stats["failed"] += 1
            action = "GIVE_UP" if gave_up else "RETRY"
            log(f"  [{i+1}/{len(rows)}] {action} {pid} attempts={row['enrichment_attempts']+1}")
            if consec_fail >= CIRCUIT_BREAK:
                cd_until = _set_resolve_cooldown(f"pass1_circuit_break_{consec_fail}_consec_fail")
                log(f"⚡ Pass1 circuit breaker: {consec_fail} fails ติดกัน — abort + cooldown ถึง {cd_until}")
                _discord_safe(
                    f"⚡ BMS resolve plane (RSS path) WAF/outage — {consec_fail} fails ติดกัน\n"
                    f"→ COOLDOWN ถึง {cd_until} (INC-001 Rev3 backoff)")
                break
        else:
            consec_fail = 0
            _save_success(pid, loc)
            stats["enriched"] += 1
            province = loc["province_name"]
            tambon   = loc["moi_name"]
            log(f"  [{i+1}/{len(rows)}] OK {pid} province={province or '?'} tambon={tambon}")

            if province in TARGET_PROVINCES:
                stats["target_hit"] += 1
                announce_type = row.get("announce_type") or "D0"
                budget        = int(row.get("budget") or 0)
                project_name  = row.get("project_name") or ""

                if not _rss_gate_ok(pid):
                    log(f"    ⏸ SHADOW: {pid} match {province} แต่ Discovery ยังไม่ประทับตรา → ไม่ส่ง (audit)")
                else:
                    n = store.enqueue_notifications({
                        "project_id":           pid,
                        "province":             province,
                        "announce_type":        announce_type,
                        "budget":               budget,
                        "project_name":         project_name,
                        "dept_name":            row.get("dept_name") or "",
                        "extraction_confidence": "high",
                        "is_backfill":          False,
                        "source_stage":         "api_enriched",
                    }, min_confidence="high")

                    if n > 0:
                        stats["enqueued"] += 1
                        log(f"    → ENQUEUED {n}x province={province} tambon={tambon}")
                    else:
                        stats["dedup"] += 1

        # Rate limit guard
        if i < len(rows) - 1:
            time.sleep(SLEEP_BETWEEN_SEC)

    # Summary
    with get_connection() as conn:
        total_pending = conn.execute(
            "SELECT COUNT(*) FROM project_locations WHERE enrichment_status='pending'"
        ).fetchone()[0]
        qual_pending = conn.execute(
            "SELECT COUNT(*) FROM project_locations WHERE source='province_api' "
            "AND qualification_status='pending' AND enrichment_attempts < ?",
            (MAX_QUAL_ATTEMPTS,)).fetchone()[0]

    # P1 resolve heartbeat: resolved_ok = qual RESOLVED + RSS enriched (business outcome จริง)
    _write_resolve_heartbeat("ok", resolved_ok=qual_ok + stats["enriched"],
                             pending=total_pending + qual_pending)

    log(
        f"Done — enriched={stats['enriched']} failed={stats['failed']} "
        f"target_hit={stats['target_hit']} enqueued={stats['enqueued']} "
        f"dedup={stats['dedup']} | queue_remaining={total_pending}"
    )

    # Pass 2: repair success-but-not-enqueued orphans
    with get_connection() as conn:
        orphans = conn.execute("""
            SELECT pl.project_id, pl.province_name, pl.moi_name,
                   ps.announce_type, ps.budget, ps.project_name, ps.dept_name
            FROM project_locations pl
            LEFT JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE pl.enrichment_status = 'success'
              AND pl.province_name IN ('นครพนม', 'บึงกาฬ')
              AND pl.project_id NOT IN (
                  SELECT DISTINCT project_id FROM notification_queue
              )
            LIMIT 20
        """).fetchall()
    orphans = [dict(r) for r in orphans]

    if orphans:
        log(f"Pass 2 (repair): {len(orphans)} success-but-not-enqueued orphans")
        repaired = 0
        for orphan in orphans:
            if not _rss_gate_ok(orphan["project_id"]):
                continue  # SHADOW: Discovery ยังไม่ประทับตรา → ไม่ repair-enqueue
            n = store.enqueue_notifications({
                "project_id":            orphan["project_id"],
                "province":              orphan["province_name"],
                "announce_type":         orphan.get("announce_type") or "D0",
                "budget":                int(orphan.get("budget") or 0),
                "project_name":          orphan.get("project_name") or "",
                "dept_name":             orphan.get("dept_name") or "",
                "extraction_confidence": "high",
                "is_backfill":           False,
                "source_stage":          "repair_pass2",
            }, min_confidence="high")
            if n > 0:
                repaired += 1
        log(f"  repaired={repaired}/{len(orphans)}")
    else:
        log("Pass 2 (repair): 0 orphans — OK")

    log("=== Enrichment Worker done ===")


if __name__ == "__main__":
    main()
