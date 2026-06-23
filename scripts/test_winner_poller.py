"""test_winner_poller.py — poll_winners: ได้ผล→แจ้ง+เก็บ+ปิด · ไม่มีผล→รอ · เกิน max_days→ปิด."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["BMS_PROVINCE_NOTIFY_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()
import Sebastian_Winner_Poller as wp  # noqa: E402

s = db.SubscriptionStore()
c1 = s.add_customer("U1", "พ่อ")
with db.get_connection() as conn:
    for pid, name in [("W1", "ถนน A"), ("W2", "ถนน B"), ("W3", "ถนน C")]:
        conn.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name) "
                     "VALUES (?,?,?,?,?,?)", (pid, "D0", "นครพนม", "province_api", "2026-05-01", name))

# W1: ติดตาม (ถึง D0) + จะมีผล → ควรแจ้ง+ปิด
s.add_follow(c1, "W1", "D0", "2026-06-01T00:00:00"); s.mark_stage_notified(c1, "W1", "D0")
# W2: ติดตาม + ยังไม่มีผล + เพิ่งติดตาม → ควรคงไว้
s.add_follow(c1, "W2", "D0", "2026-06-05T00:00:00"); s.mark_stage_notified(c1, "W2", "D0")
# W3: ติดตาม + ไม่มีผล + ติดตามนานเกิน 60 วัน → ปิด (stale)
s.add_follow(c1, "W3", "D0", "2026-03-01T00:00:00"); s.mark_stage_notified(c1, "W3", "D0")

def fake_resolve(pid):
    if pid == "W1":
        return {"winner": "บ.A", "winning_price": "950000",
                "bidders": [{"receiveNameTh": "บ.A", "receiveTin": "1", "priceProposal": "950000",
                             "priceAgree": "950000"},
                            {"receiveNameTh": "บ.B", "receiveTin": "2", "priceProposal": "1100000",
                             "priceAgree": ""}]}
    return {}  # W2, W3 ยังไม่มีผล

stats = wp.poll_winners(s, fake_resolve, now="2026-06-06T00:00:00", log=lambda m: None, max_days=60)

# W1 → แจ้ง + เก็บ bid_results + mark W0 + close
assert stats["notified"] == 1, stats
with db.get_connection() as c:
    q = c.execute("SELECT COUNT(*) FROM notification_queue WHERE project_id='W1' AND source_stage='followed_winner'").fetchone()[0]
assert q == 1, f"ควร enqueue winner: {q}"
assert len(s.get_bid_results("W1")) == 2, "ควรเก็บ bid_results"
assert not any(f["project_id"] == "W1" for f in s.get_active_follows()), "W1 ควรถูกปิด"
# W2 ยังคงอยู่ (รอผล)
assert any(f["project_id"] == "W2" for f in s.get_active_follows()), "W2 ควรยังตามอยู่"
# W3 stale → ปิด
assert not any(f["project_id"] == "W3" for f in s.get_active_follows()), "W3 ควรปิด (stale)"
assert stats["closed_stale"] == 1, stats

print("✅ PASS winner poller")


# ── closed-loop: verify_hook ถูกเรียกด้วย (pid, winning_price) เมื่อมีผล ──────────
def test_verify_hook():
    calls = []
    class FakeStore:
        def get_active_follows(self):
            return [{"project_id": "V1", "customer_id": 1, "last_stage_notified": "D0",
                     "starred_at": "2026-06-01T00:00:00"}]
        def record_bid_results(self, *a): pass
        def enqueue_for_customer(self, *a, **k): pass
        def mark_stage_notified(self, *a): pass
        def close_follow(self, *a): pass
    res = {"winner": "บ.A", "winning_price": "1,750,000",
           "bidders": [{"receiveTin": "1", "priceAgree": "1750000"}]}
    wp.poll_winners(FakeStore(), lambda pid: res, now="2026-06-06T00:00:00",
                    log=lambda m: None, verify_hook=lambda pid, price: calls.append((pid, price)))
    assert calls == [("V1", "1,750,000")], calls
    print("✅ verify_hook called with (pid, winning_price)")


test_verify_hook()


# ── 1a: capture all-bidders ตอน PRELIM (มี bidders แต่ยังไม่มี winner) ──────────
def test_capture_bidders_at_prelim():
    """เปิดก๊อก: prelim มี bidders (priceProposal) แต่ winner ยังว่าง → ต้อง record_bid_results
    แต่ยังไม่ enqueue winner / ไม่ close (ยังไม่ถึง W0)."""
    captured, enqueued, closed = [], [], []
    class FakeStore:
        def get_active_follows(self):
            return [{"project_id": "P1", "customer_id": 1, "last_stage_notified": "D0",
                     "starred_at": "2026-06-05T00:00:00"}]
        def record_bid_results(self, pid, bidders): captured.append((pid, len(bidders)))
        def enqueue_for_customer(self, cid, data): enqueued.append(data.get("source_stage"))
        def mark_stage_notified(self, *a): pass
        def close_follow(self, *a): closed.append(a)
    res = {"bidders": [{"receiveTin": "1", "priceProposal": "950000", "priceAgree": ""},
                       {"receiveTin": "2", "priceProposal": "1100000", "priceAgree": ""}]}  # ไม่มี winner
    wp.poll_winners(FakeStore(), lambda pid: res, now="2026-06-06T00:00:00", log=lambda m: None, max_days=60)
    assert captured == [("P1", 2)], f"ต้อง capture bidders ตอน prelim: {captured}"
    assert "followed_winner" not in enqueued, "ยังไม่ควร enqueue winner"
    assert closed == [], "ยังไม่ควร close (ยังไม่ W0)"
    print("✅ capture all-bidders ตอน prelim (เปิดก๊อก ไม่รอ winner)")


test_capture_bidders_at_prelim()


def test_cgd_winners_upsert_on_award():
    """winner-poller ตอน award (แข่งจริง ≥2 ราย + budget>0) → upsert cgd_winners ป้อนเครื่องคิด Win%
    ทันที. งานเฉพาะเจาะจง (1 ราย) ไม่เขียน."""
    s2 = db.SubscriptionStore()
    cid = s2.add_customer("U2", "แม่")
    with db.get_connection() as conn:
        conn.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name,budget) "
                     "VALUES (?,?,?,?,?,?,?)", ("AW1", "D0", "นครพนม", "province_api", "2026-05-01",
                     "ก่อสร้างถนนคอนกรีตเสริมเหล็ก องค์การบริหารส่วนตำบลนาทม", 1000000))
        conn.execute("INSERT INTO projects_seen (project_id,announce_type,province,source,first_seen_at,project_name,budget) "
                     "VALUES (?,?,?,?,?,?,?)", ("AW2", "D0", "นครพนม", "province_api", "2026-05-01",
                     "จัดซื้อเฉพาะเจาะจง", 500000))
    s2.add_follow(cid, "AW1", "D0", "2026-06-01T00:00:00"); s2.mark_stage_notified(cid, "AW1", "D0")
    s2.add_follow(cid, "AW2", "D0", "2026-06-01T00:00:00"); s2.mark_stage_notified(cid, "AW2", "D0")

    def fake(pid):
        if pid == "AW1":   # แข่งจริง 2 ราย มีผู้ชนะ
            return {"winner": "หจก.ชนะ", "winning_price": "800000", "announce_date": "2026-06-20",
                    "bidders": [{"receiveNameTh": "หจก.ชนะ", "receiveTin": "1", "priceProposal": "800000", "priceAgree": "800000"},
                                {"receiveNameTh": "หจก.แพ้", "receiveTin": "2", "priceProposal": "900000", "priceAgree": ""}]}
        if pid == "AW2":   # เฉพาะเจาะจง 1 ราย
            return {"winner": "ผู้ขายเดียว", "winning_price": "495000", "announce_date": "2026-06-20",
                    "bidders": [{"receiveNameTh": "ผู้ขายเดียว", "receiveTin": "9", "priceProposal": "495000", "priceAgree": "495000"}]}
        return {}
    wp.poll_winners(s2, fake, now="2026-06-21T00:00:00", log=lambda m: None, max_days=60)

    with db.get_connection() as c:
        row = c.execute("SELECT province,project_name,budget,winner,win_price,discount_pct,proc_type,"
                        "fiscal_year,normalized_winner FROM cgd_winners WHERE project_id='AW1'").fetchone()
    assert row is not None, "งานแข่ง(2+ราย)+ผู้ชนะ → ต้องเขียน cgd_winners"
    assert row[2] == 1000000 and row[3] == "หจก.ชนะ" and row[4] == 800000, row
    assert abs(row[5] - 20.0) < 0.01, row          # (1M-800k)/1M = 20%
    assert "e-bidding" in (row[6] or ""), row[6]    # proc_type ใน COMPETITIVE_SET
    assert row[8], "normalized_winner ต้องถูกเซ็ต (ใช้ join ชื่อในเครื่องคิด)"
    with db.get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM cgd_winners WHERE project_id='AW2'").fetchone()[0] == 0, \
            "เฉพาะเจาะจง 1 ราย → ไม่เขียน cgd_winners"
    print("✅ PASS cgd_winners upsert on award (competitive only)")


test_cgd_winners_upsert_on_award()
print("ALL PASS winner poller")
