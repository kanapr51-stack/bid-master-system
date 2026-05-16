# eGP API Catalog — stepId / flowId / announceType (Research 2026-05-16)

**Sources:**
- `data/stepid_research.json` (Phase 1: 63 jobs)
- `data/stepid_research_v2.json` (Phase 4+retry: 214 jobs)
- `data/doc_endpoint_research.json` + `_v2.json` (Phase 5: doc API discovery)

**Total samples:** 277 jobs probed, **18 unique stepIds discovered**
**Method:** `scripts/research_stepid.py`, `research_stepid_v2.py`, `research_stepid_retry.py`, `research_doc_endpoints.py`, `research_doc_v2.py`, `analyze_announce_type.py`

---

## 📊 Master Table — 18 stepIds (sorted by frequency)

| stepId | n | flowSeqno | flowId | projectStatus | announceType | Phase Meaning | Recommended Sheet |
|---|---:|---|---:|---|---|---|---|
| **C01** | 74 | 8 (1×9) | 15 | A | W0 | ✅ บริหารสัญญา (มี winner) | awarded (มี cache) / pending |
| **B03** | 51 | 0 | 0 | R | W1 | ❌ ยกเลิก (early common) | SKIP |
| **S01** | 24 | 4 | 16 | A=15, R=9 | B0/D0/D1/B3 | 🔵 เปิดยื่นซองอยู่ | active (A) / SKIP (R) |
| **M03** | 17 | 3 (1×2) | 1 | A=9, R=8 | B0/D0/D1/BOQ | TOR-final → active (A) หรือ cancelled (R) | active (A) / SKIP (R) |
| **Z01** | 11 | 4 | 16 | A=2, R=9 | B0/D1 | 🔵 Bidding variant (mostly cancelled) | active (A) / SKIP (R) |
| **I03** | 10 | 7-8 | 9 | A | W0 | ✅ จัดทำ/บริหารสัญญา | pending → awarded |
| **W03** | 9 | 5 | 7 | A | W0 | 🏆 ประกาศผู้ชนะ | pending → awarded |
| **Q03** | 8 | 1 | 10 | A=7, R=1 | BOQ/W1 | 🟡 Quote stage 03 (pre-TOR) | SKIP (ยังไม่พร้อม) |
| **Q01** | 7 | 1 | 10 | A=6, R=1 | BOQ/W1 | 🟡 Quote stage 01 | SKIP |
| **C03** | 6 | 8 (1×4) | 15 (1×7) | A | W0/BOQ | rare — re-bid variant | pending / active (rare) |
| **U03** | 6 | 3 | 1 | A=4, R=2 | B0 | 🟢 รับฟังคำวิจารณ์ | tor_review (A) / SKIP (R) |
| **E03** | 3 | 3 | 16 | A=2, R=1 | W1 | rare — re-bid after winner cancel? | pending / SKIP |
| **W01** | 3 | 5 (1×4) | 7 | A | B0/W1/D0 | Winner stage 01 (transitional) | pending |
| **B01** | 2 | 0 | 0 | R | W1 | ❌ ยกเลิก stage 01 | SKIP |
| **Z03** | 2 | 4 | 16 | A | D0 | 🔵 Bidding variant | active |
| **U06** | 1 | 3 | 1 | A | B0 | rare — TOR variant | tor_review |
| **X01** | 1 | 5 | 13 | A | W0 | rare — X-class winner | pending → awarded |
| **X03** | 1 | 5 | 13 | A | W0 | rare — X-class winner | pending → awarded |

---

## 🔑 flowId → Stage Family Mapping (confirmed)

| flowId | Family | stepIds | Total | Meaning |
|---:|---|---|---:|---|
| 0 | **B (Block/Cancel)** | B01, B03 | 53 | ยกเลิก (early stage) |
| 1 | **M/U (TOR)** | M03, U03, U06 | 24 | TOR drafting + consultation |
| 7 | **W (Winner)** | W01, W03, C03(1) | 13 | ประกาศผู้ชนะ |
| 9 | **I (Implementation)** | I03 | 10 | จัดทำ/บริหารสัญญา (post-winner) |
| 10 | **Q (Quote)** | Q01, Q03 | 15 | Early prep (pre-TOR) |
| 13 | **X (rare)** | X01, X03 | 2 | Winner variant (น้อยมาก) |
| 15 | **C (Contract)** | C01, C03 | 79 | สัญญา (most common post-winner) |
| 16 | **S (Submission)** | S01, Z01, Z03, E03 | 40 | ยื่นซอง + variants |

---

## 🔑 announceType Decoded

| Code | Meaning | projectStatus correlation | Notes |
|---|---|---|---|
| **B0** | Bidding announcement (original) | 100% A | ปกติ |
| **B3** | Bidding stage 3 (rare) | 100% A | 1 ตัวเดียว |
| **BOQ** | Bill of Quantity posted | 100% A | Q stage + 1 C03 |
| **D0** | Document/announcement (original) | 100% A | ปกติ |
| **D1** | Document **CANCELLED** | **100% R (25/25)** | ⭐ strong signal |
| **W0** | Winner announcement (original) | 100% A | ปกติ |
| **W1** | Winner cancelled / pre-cancel marker | **90% R (56/62)** | strong signal (6 exceptions in E03/W01/Q01/Q03) |

**Pattern: suffix "1" = cancellation marker** (D1, W1) — เกือบ 100% correlate กับ projectStatus="R"

---

## 🎯 Classification Decision Logic

### Strong cancellation signals (skip → ไม่แสดงใน sheet ใด):
```
projectStatus == "R"        ← gold standard
OR announceType in ("D1", "W1")  ← strong (W1 มี exception 10%)
OR stepId in ("B01", "B03")     ← Block family
```

### Letter-prefix fallback for unknown stepIds:
```python
LETTER_MAP = {
    "M": "active_bidding",   # M03 = TOR-final, ประกาศวันยื่นแล้ว
    "U": "tor_review",       # U03/U06 = ยังรับฟัง
    "S": "active_bidding",   # S01 = ยื่นซองอยู่
    "Z": "active_bidding",   # Z01/Z03 = bidding variant
    "E": "pending_award",    # E03 rare re-bid
    "W": "pending_award",    # W01/W03 = pending winner
    "C": "pending_award",    # C01/C03 = contract (มี winner)
    "I": "pending_award",    # I03 = implementation (มี winner)
    "X": "pending_award",    # X01/X03 rare winner
    "Q": None,               # Q01/Q03 = early prep → skip
    "B": None,               # B01/B03 = cancelled → skip
}
```

### Final order (top to bottom — stop at first match):

1. **Cancelled** (projectStatus=R OR announceType ends "1") → **SKIP**
2. **Winner in cache** → **awarded_jobs**
3. **stepId starts with "U"** → **tor_review**
4. **stepId starts with "M"** + projectStatus=A → **active_bidding** ⭐ (Q7-9 fix)
5. **stepId starts with "S"/"Z"** → **active_bidding**
6. **stepId starts with "W"/"C"/"I"/"E"/"X"** → **pending_award**
7. **stepId starts with "Q"** → **SKIP** (early prep)
8. **stepId starts with "B"** → **SKIP** (cancelled)
9. **Unknown letter** → **pending_award** + LOG WARNING

---

## 📑 Document API Discovery (Phase 5)

**Result: ❌ ไม่มี endpoint แยกสำหรับ document list**

ลอง 30+ endpoint patterns + spy network ระหว่าง click ผ่าน search:
- ทุก `/file/`, `/document/`, `/attachment/` pattern → **404**
- Detail page เรียก getProjectDetail เท่านั้น
- เอกสาร PDF (TOR, ปร.4, ปร.5) ดึงได้จาก **`tor_url`** field ใน search result (Scraper เก็บอยู่แล้ว)

**Conclusion:**
- ปัจจุบัน `Sebastian_Doc_Downloader.py` ใช้ tor_url ดึง PDF ได้
- `patch_deadlines.py` ใช้ tor_url + parse PDF
- ไม่ต้อง implement endpoint document ใหม่ — work with existing tor_url

---

## 📊 Data Quality

- Sampled: **277 jobs**, valid: **277/277 (100%)** หลัง retry
- Coverage: ทุก project_status (กำลังประมูล/ประมูลแล้ว/ยกเลิก/กำลังเตรียม)
- Q7-9 verified: 5/5 jobs ตรงกับ rule M03/U03 ที่เสนอ
- Cancelled detection: 53/53 cancelled samples มี projectStatus=R (100%)

---

## ⚠️ Known Unknowns (low priority)

1. **stepIds 01/02 อื่นๆ** (M01/M02/S02/S03 ฯลฯ) — ยังไม่เคยเจอใน production
   - แก้ด้วย letter-prefix fallback
2. **X family** — เห็นแค่ X01, X03 (2 jobs) — flowId=13 ที่ rare
3. **B3 announceType** — เห็น 1 ตัว, projectStatus=A → variant ของ B0
4. **C03 + flowSeqno=4 + announceType=BOQ** — เห็น 1 ตัว — น่าจะเป็น re-bid scenario
5. **E03 rare cases** — 3 jobs, all flowId=16 + announceType=W1 — น่าจะเป็น "ประมูลใหม่หลัง winner ถูกยกเลิก"

**Mitigation:** ทุกครั้งที่ Classifier เจอ unknown stepId → log + ใส่ pending_award default (ไม่ทำงานหาย)
