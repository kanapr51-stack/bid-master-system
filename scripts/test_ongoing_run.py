"""ongoing_bidder_capture: run_live / run_cgd loops — stats, idempotent, API-only pacing."""
import os, tempfile, sys, datetime
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db
db.init_schema()
import ongoing_bidder_capture as oc

def test_run_cgd_mixed_and_idempotent():
    with db.get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, winner, win_price, budget) VALUES (?,?,?,?,?,?,?)",
            [("G1", "นครพนม", "เฉพาะเจาะจง", "2569", "เอ", 100, 100),
             ("G2", "บึงกาฬ", "สอบราคา", "2569", "บี", 90, 100)])
    api = lambda pid: {"bidders": [{"receiveNameTh": "บี", "receiveTin": "2", "priceProposal": "90"}]}
    stats = oc.run_cgd(oc.PROVINCES, 2569, api, sleep=0)
    assert stats["copied"] == 1 and stats["stored"] == 1, stats     # G1 copy, G2 API
    # idempotent: รอบ 2 ไม่เก็บซ้ำ (อยู่ bid_results แล้ว)
    stats2 = oc.run_cgd(oc.PROVINCES, 2569, api, sleep=0)
    assert stats2 == {"copied": 0, "stored": 0, "empty": 0, "error": 0}, stats2
    assert len(db.SubscriptionStore().get_bid_results("G1")) == 1
    print("✅ run_cgd mixed copy/API + idempotent")

def test_run_cgd_paces_only_api():
    """copy ไม่ยิง API → ต้องไม่ sleep; เฉพาะ competitive ที่ยิง API ถึงพับ cooldown."""
    if oc.SEEN_CGD_PATH.exists():
        oc.SEEN_CGD_PATH.unlink()
    with db.get_connection() as conn:
        conn.execute("DELETE FROM bid_results")
        conn.execute("DELETE FROM cgd_winners")
        conn.executemany(
            "INSERT OR REPLACE INTO cgd_winners "
            "(project_id, province, proc_type, fiscal_year, winner, win_price, budget) VALUES (?,?,?,?,?,?,?)",
            [("P_a", "นครพนม", "เฉพาะเจาะจง", "2569", "เอ", 1, 1),
             ("P_b", "นครพนม", "เฉพาะเจาะจง", "2569", "บี", 1, 1),
             ("P_c", "บึงกาฬ", "สอบราคา", "2569", "ซี", 1, 1)])
    api = lambda pid: {"bidders": [{"receiveNameTh": "ซี", "receiveTin": "3", "priceProposal": "1"}]}
    slept = []
    orig = oc.time.sleep; oc.time.sleep = lambda s: slept.append(s)
    try:
        oc.run_cgd(oc.PROVINCES, 2569, api, sleep=1, cooldown_every=1, cooldown_sec=130)
    finally:
        oc.time.sleep = orig
    # มี API call จริง 1 (P_c) เป็นงาน API สุดท้าย (ไม่พักหลัง API ตัวสุดท้าย) → ไม่มี 130
    # copy 2 ตัวต้องไม่ sleep → จำนวน sleep ต้อง <= จำนวน API call
    assert slept.count(130) == 0, slept
    assert len([s for s in slept if s == 1]) <= 1, slept
    print("✅ run_cgd paces only on API calls (copy ไม่พัก)")

def test_run_live_stats():
    with db.get_connection() as conn:
        conn.execute("DELETE FROM bid_results")
        conn.execute("INSERT OR REPLACE INTO projects_seen (project_id, province, first_seen_at) "
                     "VALUES ('LV1','นครพนม','2026-06-15T00:00:00')")
    api = lambda pid: {"bidders": [{"receiveNameTh": "ก", "receiveTin": "1", "priceProposal": "9"}]}
    stats = oc.run_live(oc.PROVINCES, "2026-06-12", api, sleep=0, today=datetime.date(2026, 6, 27))
    assert stats["stored"] == 1, stats
    print("✅ run_live stats")

def test_run_live_giveup_after_max():
    """งานที่ poll แล้ว empty ครบ MAX_LIVE_TRIES → เลิก poll (ไม่ re-poll ค้างจนหลุด window)."""
    if oc.LIVE_TRIES_PATH.exists():
        oc.LIVE_TRIES_PATH.unlink()
    with db.get_connection() as conn:
        conn.execute("DELETE FROM bid_results")
        conn.execute("DELETE FROM projects_seen")
        conn.execute("INSERT OR REPLACE INTO projects_seen (project_id, province, first_seen_at) "
                     "VALUES ('EMP','นครพนม','2026-06-15T00:00:00')")
    calls = []
    api = lambda pid: calls.append(pid) or {"bidders": []}   # empty เสมอ (ยังไม่ award/ยกเลิก)
    today = datetime.date(2026, 6, 27)
    for _ in range(oc.MAX_LIVE_TRIES):
        oc.run_live(oc.PROVINCES, "2026-06-12", api, sleep=0, today=today)
    assert len(calls) == oc.MAX_LIVE_TRIES, len(calls)      # poll ครบ max ครั้งพอดี
    oc.run_live(oc.PROVINCES, "2026-06-12", api, sleep=0, today=today)
    assert len(calls) == oc.MAX_LIVE_TRIES, f"เลิกลองแล้วต้องไม่ poll เพิ่ม: {len(calls)}"
    print("✅ run_live เลิก poll หลัง MAX_LIVE_TRIES empty")

def test_run_live_stored_clears_tries():
    """empty แล้ว stored ภายหลัง → counter ถูกล้าง (ไม่ค้าง)."""
    if oc.LIVE_TRIES_PATH.exists():
        oc.LIVE_TRIES_PATH.unlink()
    with db.get_connection() as conn:
        conn.execute("DELETE FROM bid_results")
        conn.execute("DELETE FROM projects_seen")
        conn.execute("INSERT OR REPLACE INTO projects_seen (project_id, province, first_seen_at) "
                     "VALUES ('AW','นครพนม','2026-06-15T00:00:00')")
    today = datetime.date(2026, 6, 27)
    oc.run_live(oc.PROVINCES, "2026-06-12", lambda pid: {"bidders": []}, sleep=0, today=today)
    assert oc.load_tries(oc.LIVE_TRIES_PATH).get("AW") == 1
    oc.run_live(oc.PROVINCES, "2026-06-12",
                lambda pid: {"bidders": [{"receiveNameTh": "ก", "receiveTin": "1", "priceProposal": "9"}]},
                sleep=0, today=today)
    assert "AW" not in oc.load_tries(oc.LIVE_TRIES_PATH), oc.load_tries(oc.LIVE_TRIES_PATH)
    print("✅ run_live stored ล้าง tries counter")

test_run_cgd_mixed_and_idempotent()
test_run_cgd_paces_only_api()
test_run_live_stats()
test_run_live_giveup_after_max()
test_run_live_stored_clears_tries()
print("ALL PASS ongoing_run")
