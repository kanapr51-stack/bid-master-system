# All-Bidders Capture (1b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ให้ `winner_sweep.py` เก็บราคา **ผู้ยื่นทุกราย** (ไม่ใช่แค่ผู้ชนะ) ลง `bid_results` สำหรับงานจังหวัดเป้าหมาย

**Architecture:** winner_sweep มี broad province sweep + `get_procure_result` (คืน bidders ครบ) อยู่แล้ว → `sweep_egp` เก็บ bidders ต่อ job ส่งกลับ → `main()` เขียน `record_bid_results` แบบ sequential + fail-open (เลี่ยง parallel-write, ไม่ทำ winner sweep พัง). ไม่เพิ่ม API call.

**Tech Stack:** Python, sqlite3, concurrent.futures (มีอยู่แล้ว), pytest-style assert scripts (รันด้วย `BMS_ENV=dev python <file>`)

**No-TIN handling:** dedup key = `bidder_tin` fallback → `"name:"+bidder_name`. ปลอดภัยเพราะ `competitor_trend` อ่าน `bidder_name` ไม่ใช่ `bidder_tin` → ไม่ต้อง migration.

---

### Task 1: record_bid_results — name-fallback (เก็บ bidder ไม่มี TIN ครบ)

**Files:**
- Modify: `scripts/Sebastian_Customer_DB.py:896-909` (loop ใน `record_bid_results`)
- Test: `scripts/test_bid_results.py`

- [ ] **Step 1: เพิ่ม failing test** ต่อท้าย `scripts/test_bid_results.py` (ก่อน print สรุปท้ายไฟล์)

```python
# no-TIN: 2 bidder ไม่มี receiveTin คนละชื่อ → ต้องเก็บครบ 2 (เดิม PK ชนเหลือ 1)
s.record_bid_results("P3", [
    {"receiveNameTh": "หจก.ไร้ทิน A", "receiveTin": "", "priceProposal": "800000", "priceAgree": ""},
    {"receiveNameTh": "หจก.ไร้ทิน B", "receiveTin": "", "priceProposal": "900000", "priceAgree": ""},
], fetched_at="2026-06-13")
rows = s.get_bid_results("P3")
assert len(rows) == 2, f"no-TIN ต้องเก็บครบ 2: {len(rows)}"
# bidder ไม่มีทั้ง tin/name → ข้าม
s.record_bid_results("P4", [{"receiveNameTh": "", "receiveTin": "", "priceProposal": "1"}], fetched_at="2026-06-13")
assert len(s.get_bid_results("P4")) == 0, "ไม่มี tin/name → ข้าม"
print("✅ no-TIN name-fallback")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_results.py`
Expected: FAIL — `no-TIN ต้องเก็บครบ 2: 1` (PK (project_id,'') ชนกัน)

- [ ] **Step 3: แก้ loop ใน `record_bid_results`** (`scripts/Sebastian_Customer_DB.py`) — แทน body ของ `for b in bidders:`

```python
            for b in bidders:
                pa = (b.get("priceAgree") or "").strip()
                name = (b.get("receiveNameTh") or "").strip()
                tin = (b.get("receiveTin") or "").strip()
                key = tin or (f"name:{name}" if name else "")  # name-fallback กัน PK ชนเมื่อ TIN ว่าง
                if not key:
                    continue  # ไม่มีทั้ง tin/name → ระบุไม่ได้ ข้าม
                conn.execute("""
                    INSERT OR REPLACE INTO bid_results
                      (project_id, bidder_name, bidder_tin, price_proposal, price_agree,
                       is_winner, is_sme, result_flag, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (project_id, name, key, b.get("priceProposal") or "", pa,
                      1 if pa else 0, 1 if b.get("is_sme") else 0,
                      b.get("resultFlag") or "", fetched_at))
                n += 1
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_bid_results.py`
Expected: PASS — เห็น `✅ no-TIN name-fallback` + `✅ PASS bid_results`

- [ ] **Step 5: regression — competitor_trend ยังอ่านได้**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_competitor_trend_series.py`
Expected: PASS (อ่าน bidder_name ไม่กระทบ)

- [ ] **Step 6: commit**

```bash
git add scripts/Sebastian_Customer_DB.py scripts/test_bid_results.py
git commit -m "feat(db): record_bid_results name-fallback เก็บ bidder ไม่มี TIN ครบ"
```

---

### Task 2: persist_bid_results helper — sequential + fail-open

**Files:**
- Modify: `scripts/winner_sweep.py` (เพิ่มฟังก์ชันใหม่ ก่อน `def main()`)
- Test: `scripts/test_winner_sweep.py` (สร้างใหม่)

- [ ] **Step 1: เขียน failing test** สร้าง `scripts/test_winner_sweep.py`

```python
"""test_winner_sweep.py — persist_bid_results: เขียน sequential + fail-open."""
import os, tempfile, sys
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(__file__)); sys.stdout.reconfigure(encoding="utf-8")
import winner_sweep as ws

def test_persist_fail_open():
    written = []
    class FakeStore:
        def record_bid_results(self, jid, bidders):
            if jid == "BOOM":
                raise RuntimeError("db error")
            written.append((jid, len(bidders)))
    by_jid = {"J1": [{"receiveTin": "1"}], "BOOM": [{"receiveTin": "2"}], "J2": [{"receiveTin": "3"}], "J3": []}
    n = ws.persist_bid_results(FakeStore(), by_jid, log=lambda m: None)
    assert written == [("J1", 1), ("J2", 1)], written   # J3 ว่างข้าม, BOOM พังแต่ไม่ล้ม
    assert n == 2, n
    print("✅ persist_bid_results sequential + fail-open")

test_persist_fail_open()
print("ALL PASS winner_sweep")
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_winner_sweep.py`
Expected: FAIL — `AttributeError: module 'winner_sweep' has no attribute 'persist_bid_results'`

- [ ] **Step 3: เพิ่มฟังก์ชัน** ใน `scripts/winner_sweep.py` (วางก่อน `def main():`)

```python
def persist_bid_results(store, bidders_by_jid: dict, log=log) -> int:
    """เขียน all-bidders ลง bid_results — sequential (connection เดียว เลี่ยง parallel)
    + fail-open (พังต่อ job ไม่ทำ sweep ล้ม). คืนจำนวน job ที่เก็บสำเร็จ."""
    n = 0
    for jid, bidders in bidders_by_jid.items():
        if not bidders:
            continue
        try:
            store.record_bid_results(jid, bidders)
            n += 1
        except Exception as e:
            log(f"  bid_results เก็บ {jid} พลาด: {type(e).__name__}: {e}")
    return n
```

- [ ] **Step 4: รัน test ให้ผ่าน**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_winner_sweep.py`
Expected: PASS — `✅ persist_bid_results sequential + fail-open`

- [ ] **Step 5: commit**

```bash
git add scripts/winner_sweep.py scripts/test_winner_sweep.py
git commit -m "feat(sweep): persist_bid_results helper (sequential + fail-open)"
```

---

### Task 3: sweep_egp เก็บ bidders + main() เรียก persist

**Files:**
- Modify: `scripts/winner_sweep.py:276-303` (`sweep_egp`) + `:490` (caller ใน `main`)
- Test: `scripts/test_winner_sweep.py`

- [ ] **Step 1: เพิ่ม failing test** ต่อท้าย `scripts/test_winner_sweep.py` (ก่อน print "ALL PASS")

```python
def test_sweep_egp_collects_bidders():
    """sweep_egp ต้องคืน bidders ต่อ job (ไม่ใช่แค่ winner) — monkeypatch get_procure_result."""
    fake = {"PA": {"winner": "หจก.X", "winning_price": "950000",
                   "bidders": [{"receiveTin": "1", "priceAgree": "950000"},
                               {"receiveTin": "2", "priceProposal": "1100000"}]},
            "PB": {"bidders": [{"receiveTin": "3", "priceProposal": "500000"}]}}  # prelim ไม่มี winner
    ws.get_procure_result = lambda jid: fake.get(jid, {})
    results, bidders_by_jid = ws.sweep_egp(["PA", "PB"], {}, workers=2)
    assert set(bidders_by_jid) == {"PA", "PB"}, bidders_by_jid
    assert len(bidders_by_jid["PA"]) == 2 and len(bidders_by_jid["PB"]) == 1
    assert "PA" in results and "PB" not in results   # winner เฉพาะ PA
    print("✅ sweep_egp collects bidders (prelim + winner)")

test_sweep_egp_collects_bidders()
```

- [ ] **Step 2: รัน test ให้ fail**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_winner_sweep.py`
Expected: FAIL — `ValueError: not enough values to unpack` (sweep_egp คืน dict เดียว)

- [ ] **Step 3: แก้ `sweep_egp`** ใน `scripts/winner_sweep.py` — แทนทั้งฟังก์ชัน

```python
def sweep_egp(jids: list[str], budget_map: dict[str, str], workers: int) -> tuple[dict, dict]:
    """eGP getProcureResult (parallel). คืน (winners, bidders_by_jid) — เก็บ bidder ทุกราย (1b)."""

    def _fetch(jid: str):
        winfo = get_procure_result(jid)
        bidders = winfo.get("bidders") or []
        winner = None
        if winfo.get("winner"):
            price = winfo.get("winning_price", "")
            winner = {
                "winner_name": winfo["winner"],
                "winner_price": str(price),
                "discount_pct": _pct(budget_map.get(jid, ""), price),
                "award_date": winfo.get("announce_date", ""),
            }
        return jid, winner, bidders

    results: dict[str, dict] = {}
    bidders_by_jid: dict[str, list] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_fetch, jid): jid for jid in jids}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            done += 1
            jid, winner, bidders = future.result()
            if bidders:
                bidders_by_jid[jid] = bidders
            if winner:
                results[jid] = winner
            if done % 50 == 0:
                log(f"    [{done}/{len(jids)}] {len(results)} winners so far...")

    return results, bidders_by_jid
```

- [ ] **Step 4: แก้ caller ใน `main()`** (`scripts/winner_sweep.py:490`) — แทนบรรทัด `egp_updates = sweep_egp(...)` ด้วย

```python
        egp_updates, bidders_by_jid = sweep_egp(sel, budget_map, args.workers)
        from Sebastian_Customer_DB import SubscriptionStore
        n_bid = persist_bid_results(SubscriptionStore(), bidders_by_jid)
        log(f"  💾 bid_results: เก็บ {n_bid} job (ผู้ยื่นทุกราย)")
```

- [ ] **Step 5: รัน test ให้ผ่าน + regression poller (ใช้ record_bid_results)**

Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_winner_sweep.py`
Expected: PASS — `✅ sweep_egp collects bidders`
Run: `BMS_ENV=dev PYTHONIOENCODING=utf-8 python scripts/test_winner_poller.py`
Expected: PASS (ไม่กระทบ)

- [ ] **Step 6: commit**

```bash
git add scripts/winner_sweep.py scripts/test_winner_sweep.py
git commit -m "feat(sweep): 1b เก็บ all-bidders จาก sweep_egp → bid_results"
```

---

### Task 4: Deploy (manual — บน VPS)

- [ ] **Step 1: push + deploy**

```bash
git push origin main
# บน VPS:
cd /opt/bms/app && bash scripts/deploy.sh
```

- [ ] **Step 2: verify รอบ sweep ถัดไป**

หลัง winner_sweep รันรอบถัดไป (cron) — เช็คว่า bid_results โต:
```bash
BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "import sqlite3; \
print('bid_results jobs:', sqlite3.connect('/opt/bms/data/bms_customers.db').execute('SELECT COUNT(DISTINCT project_id) FROM bid_results').fetchone()[0])"
```
Expected: จำนวน job เพิ่มขึ้นจากก่อน deploy (มีทั้ง winner + loser)

---

## Self-Review

**Spec coverage:**
- §3 capture flow → Task 3 (sweep_egp collect + main persist) ✅
- §4 storage + name-fallback → Task 1 ✅ · scope = jids ของ winner_sweep (ไม่แตะ) ✅
- §5 rate-limit (ไม่เพิ่ม API) → ไม่มี API call ใหม่ใน Task 3 ✅ · fail-open → Task 2 ✅
- §6 testing → Task 1/2/3 มี TDD ครบ (name-fallback, fail-open, collect) ✅
- §9 out of scope (backfill/use-in-predictor/B/C) → ไม่มีใน plan ✅

**Placeholder scan:** ไม่มี TBD/TODO — ทุก step มีโค้ด+คำสั่งจริง ✅

**Type consistency:** `sweep_egp` คืน `(dict, dict)` (Task 3) → main unpack `egp_updates, bidders_by_jid` (Task 3 step 4) ✅ · `persist_bid_results(store, bidders_by_jid, log)` (Task 2) เรียกจาก main ด้วย 2 args (Task 3) — log default ✅ · `record_bid_results(project_id, bidders, fetched_at)` ไม่เปลี่ยน signature ✅

**Verify-in-plan (จาก spec §10):**
1. scope winner_sweep pass 2 — ใช้ jids เดิม ไม่เปลี่ยน scope (เก็บเท่าที่มันสวีป) ✅
2. sweep_egp return — แก้เป็น tuple, caller เดียว (main) อัปแล้ว ✅
3. name-fallback least-invasive — synthetic key ใน bidder_tin, competitor_trend อ่าน bidder_name → ไม่ต้อง migration ✅
