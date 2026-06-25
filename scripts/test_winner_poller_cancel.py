"""test_winner_poller_cancel.py — cancellation pass: ตรวจยกเลิก → enqueue+mark+close+skip winner."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()  # ให้ get_connection() เจอ projects_seen ตอน names lookup (ว่างก็พอ)
import Sebastian_Winner_Poller as wp  # noqa: E402


# ── cancelled pid → enqueue followed_cancelled + mark CANCELLED + close + ไม่ poll winner ──
def test_cancellation_pass():
    enq, marked, closed, winner_calls = [], [], [], []

    class FakeStore:
        def get_active_follows(self):
            return [{"project_id": "C1", "customer_id": 7, "last_stage_notified": "PRELIM",
                     "starred_at": "2026-06-05T00:00:00"}]
        def record_bid_results(self, *a): pass
        def enqueue_for_customer(self, cid, data): enq.append((cid, data.get("source_stage")))
        def mark_stage_notified(self, cid, pid, stage): marked.append((cid, pid, stage))
        def close_follow(self, pid, cid): closed.append((pid, cid))

    def fake_resolve_winner(pid):
        winner_calls.append(pid)            # ต้องไม่ถูกเรียกสำหรับ pid ที่ยกเลิก
        return {}

    def fake_status(pid):
        return {"step_id": "S01", "project_status_raw": "R", "announce_type": "D0"}  # ยกเลิก

    stats = wp.poll_winners(FakeStore(), fake_resolve_winner, now="2026-06-06T00:00:00",
                            log=lambda m: None, resolve_status=fake_status)

    assert enq == [(7, "followed_cancelled")], enq
    assert marked == [(7, "C1", "CANCELLED")], marked
    assert closed == [("C1", 7)], closed
    assert winner_calls == [], f"ยกเลิกแล้วต้องไม่ poll winner: {winner_calls}"
    assert stats["cancelled"] == 1, stats
    print("✅ cancellation pass — enqueue+mark+close+skip winner")


# ── fail-safe: resolve_status error → ไม่ false-cancel ──────────────────────
def test_cancel_fail_safe():
    enq, closed = [], []

    class FakeStore:
        def get_active_follows(self):
            return [{"project_id": "C2", "customer_id": 7, "last_stage_notified": "D0",
                     "starred_at": "2026-06-05T00:00:00"}]
        def record_bid_results(self, *a): pass
        def enqueue_for_customer(self, cid, data): enq.append(data.get("source_stage"))
        def mark_stage_notified(self, *a): pass
        def close_follow(self, pid, cid): closed.append((pid, cid))

    def boom(pid):
        raise RuntimeError("network")

    stats = wp.poll_winners(FakeStore(), lambda pid: {}, now="2026-06-06T00:00:00",
                            log=lambda m: None, resolve_status=boom)
    assert "followed_cancelled" not in enq, enq
    assert closed == [], f"error ต้องไม่ปิด follow: {closed}"
    assert stats["cancelled"] == 0, stats
    print("✅ fail-safe — resolve_status error ไม่ false-cancel")


# ── backward-compat: resolve_status=None → ไม่มี cancellation pass ──────────
def test_no_resolve_status():
    class FakeStore:
        def get_active_follows(self):
            return [{"project_id": "C3", "customer_id": 7, "last_stage_notified": "D0",
                     "starred_at": "2026-06-05T00:00:00"}]
        def record_bid_results(self, *a): pass
        def enqueue_for_customer(self, *a, **k): pass
        def mark_stage_notified(self, *a): pass
        def close_follow(self, *a): pass

    stats = wp.poll_winners(FakeStore(), lambda pid: {}, now="2026-06-06T00:00:00", log=lambda m: None)
    assert stats.get("cancelled", 0) == 0, stats
    print("✅ backward-compat — resolve_status=None ไม่ทำ cancellation pass")


test_cancellation_pass()
test_cancel_fail_safe()
test_no_resolve_status()
print("✅ ALL PASS test_winner_poller_cancel")
