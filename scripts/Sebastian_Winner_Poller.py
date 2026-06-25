"""Sebastian_Winner_Poller.py — ⭐ Phase 2: poll ผู้ชนะของงานที่ติดตาม (B0/D0) → แจ้ง + เก็บ bid_results.

flow: followed_jobs (last in B0/D0, active) → getProcureResult (AES-token, ไม่ browser)
  • มีผล  → record_bid_results + enqueue followed_winner (line-sender render การ์ดผู้ชนะ+คู่แข่ง) + mark W0 + close
  • ไม่มีผล → รอรอบหน้า (จนเกิน BMS_WINNER_POLL_MAX_DAYS=60 วัน → ปิด กัน loop)
rate-limit: poll เฉพาะงานติดตาม (น้อย) + cooldown ระหว่างงาน (INC-001 discipline). timer ~6 ชม.
รัน: python Sebastian_Winner_Poller.py           (live ตาม env BMS_PROVINCE_NOTIFY_MODE)
"""
import datetime as _dt
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import SubscriptionStore, get_connection  # noqa: E402

POLL_SLEEP_SEC = 3       # cooldown ระหว่างงาน (กัน burst)
MAX_DAYS = int(os.environ.get("BMS_WINNER_POLL_MAX_DAYS", "60"))


def _parse_money(s):
    """'1,750,000' → 1750000.0 · None ถ้าแปลงไม่ได้."""
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _too_old(starred_at: str, now: str, max_days: int) -> bool:
    try:
        s = _dt.datetime.fromisoformat((starred_at or "")[:19])
        n = _dt.datetime.fromisoformat((now or "")[:19])
        return (n - s).days > max_days
    except (ValueError, TypeError):
        return False


def poll_winners(store, resolve_result, now: str = None, log=print,
                 max_days: int = MAX_DAYS, sleep_sec: int = 0, verify_hook=None,
                 resolve_prelim=None, resolve_status=None) -> dict:
    """core (testable): resolve_result(pid) → {} หรือ {winner, bidders[...]}.
    mode จาก env BMS_PROVINCE_NOTIFY_MODE (live=enqueue, อื่น=shadow log).
    verify_hook(pid, winning_price) = closed-loop เทียบราคาคาด vs จริง (inject ได้, ปลอดภัย).
    resolve_prelim(pid) → {} หรือ {has_summary, lowest_price, num_bidders, ...} = prelim pass (Round 1).
    resolve_status(pid) → {step_id, project_status_raw, announce_type} = cancellation pass
      (ตรวจ is_cancelled ก่อน prelim/formal; pid ที่ยกเลิก → แจ้ง+ปิด+ข้ามการ poll winner)."""
    now = now or _dt.datetime.now().isoformat()
    mode = os.environ.get("BMS_PROVINCE_NOTIFY_MODE", "preview")
    all_active = store.get_active_follows()
    stats = {"polled": 0, "notified": 0, "no_result": 0, "closed_stale": 0,
             "notified_prelim": 0, "cancelled": 0}

    # --- Cancellation pass (ก่อน prelim/formal) — ทุก active follow (B0/D0/PRELIM) ---
    cancelled_pids = set()
    if resolve_status is not None:
        from Sebastian_Classifier import is_cancelled
        cancel_by_pid = {}
        for f in all_active:
            cancel_by_pid.setdefault(f["project_id"], []).append(f)
        for pid, fs in cancel_by_pid.items():
            try:
                det = resolve_status(pid) or {}
            except Exception as e:
                log(f"  status {pid} error: {type(e).__name__}: {e}")
                continue  # fail-safe: ไม่ false-cancel
            cancelled, note = is_cancelled(det.get("step_id", ""),
                                           det.get("project_status_raw", ""),
                                           det.get("announce_type", ""))
            if not cancelled:
                continue
            cancelled_pids.add(pid)
            for f in fs:
                cid = f["customer_id"]
                if mode == "live":
                    store.enqueue_for_customer(cid, {
                        "project_id": pid, "source_stage": "followed_cancelled"})
                    store.mark_stage_notified(cid, pid, "CANCELLED")
                    store.close_follow(pid, cid)
                    log(f"  ❌→ cancelled ENQUEUED {pid} cust{cid} ({note})")
                else:
                    log(f"  [SHADOW] cancelled {pid} cust{cid}: {note}")
            stats["cancelled"] += 1
            if sleep_sec:
                time.sleep(sleep_sec)

    # formal pass: poll งานที่ stage D0 หรือ PRELIM (ข้าม pid ที่ยกเลิกแล้ว)
    formal_follows = [f for f in all_active
                      if (f.get("last_stage_notified") or "") in ("D0", "PRELIM")
                      and f["project_id"] not in cancelled_pids]
    # prelim pass: เฉพาะ stage D0 ที่ยังไม่เคยแจ้งเบื้องต้น
    prelim_follows = [f for f in all_active
                      if (f.get("last_stage_notified") or "") == "D0"
                      and f["project_id"] not in cancelled_pids]
    by_pid = {}
    for f in formal_follows:
        by_pid.setdefault(f["project_id"], []).append(f)
    prelim_by_pid = {}
    for f in prelim_follows:
        prelim_by_pid.setdefault(f["project_id"], []).append(f)
    # ชื่องาน (snapshot) — ดึงครอบคลุมทั้ง formal + prelim
    qpids = set(by_pid) | set(prelim_by_pid)
    names = {}
    if qpids:
        with get_connection() as conn:
            qs = ",".join("?" * len(qpids))
            for r in conn.execute(
                f"SELECT project_id, project_name, province, budget FROM projects_seen "
                f"WHERE project_id IN ({qs})", list(qpids)):
                names[r[0]] = {"project_name": r[1] or "", "province": r[2] or "", "budget": r[3] or 0}

    # --- Prelim pass (Round 1) ---
    if resolve_prelim is not None:
        for pid, fs in prelim_by_pid.items():
            try:
                pr = resolve_prelim(pid) or {}
            except Exception as e:
                log(f"  prelim {pid} error: {type(e).__name__}: {e}"); pr = {}
            if not pr.get("has_summary"):
                continue
            meta = names.get(pid, {})
            for f in fs:
                cid = f["customer_id"]
                if mode == "live":
                    store.enqueue_for_customer(cid, {
                        "project_id": pid, "province": meta.get("province", ""),
                        "project_name": meta.get("project_name", ""),
                        "source_stage": "followed_prelim"})
                    store.mark_stage_notified(cid, pid, "PRELIM")
                    log(f"  📊→ prelim ENQUEUED {pid} cust{cid} low={pr.get('lowest_price')}")
                else:
                    log(f"  [SHADOW] prelim {pid} cust{cid}: {pr.get('lowest_price')} / {pr.get('num_bidders')} ราย")
            stats["notified_prelim"] += 1
            if sleep_sec:
                time.sleep(sleep_sec)

    for pid, fs in by_pid.items():
        stats["polled"] += 1
        try:
            res = resolve_result(pid) or {}
        except Exception as e:
            log(f"  poll {pid} error: {type(e).__name__}: {e}")
            res = {}
        # 1a (เปิดก๊อก all-bidders): เก็บผู้ยื่นทุกราย ทันทีที่มี bidders — ไม่รอ winner ทางการ
        # prelim = priceProposal, W0 = priceAgree (INSERT OR REPLACE อัปเดต row เดิม). ข้อมูลสะสมเร็วขึ้น
        if res.get("bidders"):
            store.record_bid_results(pid, res["bidders"])
        if res.get("bidders") and res.get("winner"):
            # closed-loop: เทียบราคาคาด vs จริง (ก่อน enqueue → การ์ดอ่าน prediction ที่ update แล้ว)
            if verify_hook is not None:
                try:
                    verify_hook(pid, res.get("winning_price"))
                except Exception as e:
                    log(f"  verify {pid} error: {type(e).__name__}: {e}")
            meta = names.get(pid, {})
            # ป้อน cgd_winners ทันที (แข่งจริง ≥2 ราย + budget>0) → เครื่องคิด Win% เห็นงาน awarded สด
            # ไม่ต้องรอ CGD open-data sync (ช้าเป็นเดือน). เฉพาะเจาะจง 1 ราย ข้าม (ไม่ใช่งานแข่ง)
            if len(res["bidders"]) >= 2 and meta.get("budget"):
                try:
                    store.upsert_cgd_winner(pid, meta.get("province", ""),
                                            meta.get("project_name", ""), meta.get("budget"),
                                            res.get("winner"), res.get("winning_price"),
                                            res.get("announce_date", ""))
                except Exception as e:
                    log(f"  cgd_winner upsert {pid} error: {type(e).__name__}: {e}")
            for f in fs:
                cid = f["customer_id"]
                if mode == "live":
                    store.enqueue_for_customer(cid, {
                        "project_id": pid, "province": meta.get("province", ""),
                        "project_name": meta.get("project_name", ""),
                        "source_stage": "followed_winner"})
                    store.mark_stage_notified(cid, pid, "W0")
                    store.close_follow(pid, cid)
                    log(f"  ⭐→ winner ENQUEUED {pid} cust{cid} ({res.get('winner')})")
                else:
                    log(f"  [SHADOW] winner {pid} cust{cid}: {res.get('winner')} "
                        f"{res.get('winning_price')} + {len(res['bidders'])} bidders")
            stats["notified"] += 1
        else:
            stats["no_result"] += 1
            for f in fs:
                if _too_old(f.get("starred_at"), now, max_days):
                    store.close_follow(pid, f["customer_id"])
                    stats["closed_stale"] += 1
                    log(f"  ⏹ stale (>{max_days}วัน) ปิด {pid} cust{f['customer_id']}")
        if sleep_sec:
            time.sleep(sleep_sec)
    return stats


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    def log(m):
        print(f"[{_dt.datetime.now().isoformat(timespec='seconds')}] {m}", flush=True)

    log("=== Winner Poller start ===")
    from Sebastian_Customer_DB import init_schema
    init_schema()
    store = SubscriptionStore()
    try:
        from process5_http_client import get_procure_result
    except Exception as e:
        log(f"ABORT: import get_procure_result fail: {e}")
        return
    def verify_hook(pid, winning_price):
        """closed-loop: เทียบราคาคาด vs จริง → update DB → Discord real-time + running accuracy."""
        import cgd_intel
        from Sebastian_Customer_DB import prediction_accuracy_summary
        v = cgd_intel.compare_prediction(pid, _parse_money(winning_price))
        if not v:
            return
        s = prediction_accuracy_summary()
        verdict = "✅ อยู่ในกรอบ" if v["held"] else "❌ นอกกรอบ"
        msg = (f"🎯 ผลทำนาย {pid}\n"
               f"   คาด {v['area_price_lo']/1e6:.1f}–{v['area_price_hi']/1e6:.1f} / "
               f"จริง {v['actual']/1e6:.2f} ลบ. → {verdict} (คลาด {v['error_pct']:.0f}%)\n"
               f"   📊 สะสม: ตรง {s['in_range']}/{s['verified']} ({s['in_range_pct']}%) · "
               f"คลาดเฉลี่ย {s['mean_error_pct']}%")
        try:
            from Sebastian_Discord_Notify import load_env, get_credentials, send
            load_env(); tok, ch = get_credentials(); send(tok, ch, msg)
        except Exception as e:
            log(f"  discord verify fail: {e}")

    def resolve_prelim(pid):
        from prelim_summary import fetch_prelim_summary
        return fetch_prelim_summary(pid)

    def resolve_status(pid):
        from process5_http_client import get_project_detail
        return get_project_detail(pid)

    stats = poll_winners(store, get_procure_result, log=log, sleep_sec=POLL_SLEEP_SEC,
                         verify_hook=verify_hook, resolve_prelim=resolve_prelim,
                         resolve_status=resolve_status)
    log(f"=== Winner Poller done — {stats} ===")


if __name__ == "__main__":
    main()
