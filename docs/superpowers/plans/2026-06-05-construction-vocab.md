# Construction Vocabulary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่มความครอบคลุม keyword งานก่อสร้าง — Step 1 normalize ข้อความ (กู้ UNKNOWN ที่เพี้ยน Unicode ฟรี), Step 2 ขุด gap แบบคัดมือ → คลังคำกลาง → sync เข้า classifier + matcher.

**Architecture:** `text_normalize.normalize_thai()` (pure) เรียกก่อน match ทั้ง classifier+matcher. `mine_vocab_gaps.py` (offline, pythainlp) ขุดเฉพาะงาน UNKNOWN + งานพื้นที่เป้าหมายที่ matcher cut → candidate → `construction_vocab.json` + Sheet. `apply_vocab_review.py` อ่าน Sheet → sync additive เข้า config (backup ก่อน).

**Tech Stack:** Python 3.14 (sqlite3/re/unicodedata stdlib), pythainlp (offline dev only), gspread. Test = standalone assert (ไม่มี pytest). PowerShell: ตั้ง `$env:PYTHONIOENCODING="utf-8"` ก่อนรัน.

**Spec:** `docs/superpowers/specs/2026-06-05-construction-vocab-design.md` (rev2)

---

## File Structure

| ไฟล์ | สร้าง/แก้ | หน้าที่ |
|---|---|---|
| `scripts/text_normalize.py` | **สร้าง** | `normalize_thai(s)` pure |
| `scripts/test_text_normalize.py` | **สร้าง** | test เคสจริง |
| `scripts/work_type_classifier.py` | **แก้** (line 42) | เรียก normalize ก่อน match |
| `scripts/job_matcher.py` | **แก้** (line 140,154) | เรียก normalize ก่อน match |
| `config/construction_vocab.json` | **สร้าง** | คลังคำกลาง |
| `scripts/mine_vocab_gaps.py` | **สร้าง** | ขุด gap → คลัง + Sheet |
| `scripts/apply_vocab_review.py` | **สร้าง** | Sheet → คลัง → sync config |
| `scripts/test_vocab_sync.py` | **สร้าง** | test sync additive/idempotent |

---

### Task 1: `text_normalize.py` + test

**Files:** Create `scripts/text_normalize.py`, `scripts/test_text_normalize.py`

- [ ] **Step 1: เขียน test (TDD)** — สร้าง `scripts/test_text_normalize.py`:

```python
"""test_text_normalize.py — standalone assert runner."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from text_normalize import normalize_thai  # noqa: E402

CASES = [
    # (input, expected)
    ("ธนาคารนํ้าใต้ดิน", "ธนาคารน้ำใต้ดิน"),          # นํ้า(U+0E4D 0E49 0E32) → น้ำ
    ("เก็บกักนํ้าไว้ใช้", "เก็บกักน้ำไว้ใช้"),
    ("ก่อสร้างถนน ค.ส.ล.", "ก่อสร้างถนน คสล"),
    ("ถนน ค.ส.ล สายหลัก", "ถนน คสล สายหลัก"),
    ("ถนนคสล.", "ถนนคสล"),
    ("ราง  ระบาย   น้ำ", "ราง ระบาย น้ำ"),            # ยุบเว้นวรรค
    ("  ก่อสร้าง  ", "ก่อสร้าง"),                      # strip
    ("ก่อสร้างรางระบายน้ำ", "ก่อสร้างรางระบายน้ำ"),    # น้ำ ถูกอยู่แล้ว ไม่เปลี่ยน
    ("", ""),
]

def main():
    fails = []
    for inp, exp in CASES:
        got = normalize_thai(inp)
        if got != exp:
            fails.append(f"  {inp!r} → {got!r} != {exp!r}  ({[hex(ord(c)) for c in got]})")
    # guard None
    if normalize_thai(None) != "":
        fails.append("  None ไม่คืน ''")
    if fails:
        print("❌ FAIL:\n" + "\n".join(fails)); sys.exit(1)
    print(f"✅ PASS {len(CASES)} cases")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: รัน test ให้ FAIL**

Run: `$env:PYTHONIOENCODING="utf-8"; python scripts/test_text_normalize.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'text_normalize'`

- [ ] **Step 3: เขียน `scripts/text_normalize.py`**

```python
"""text_normalize.py — normalize ชื่องานก่อสร้าง ก่อน match keyword (classifier + matcher).
แก้ Unicode เพี้ยนจาก data ภาครัฐ (ยืนยันจาก winner_history 617K):
  - "นํ้า" (น + ํ U+0E4D + ้ U+0E49 + า) → "น้ำ" (น + ้ + ำ U+0E33)  [7% ของ UNKNOWN]
  - ค.ส.ล. / ค.ส.ล / คสล. → คสล
  - ยุบ whitespace ซ้ำ + strip
pure function ไม่มี side effect. ดู spec 2026-06-05-construction-vocab-design.md
"""
import re
import unicodedata

# ค.ส.ล. / ค.ส.ล / คสล. / คสล → คสล  (จุด optional ทุกตำแหน่ง)
_CSL = re.compile(r"ค\.?ส\.?ล\.?")
_WS = re.compile(r"\s+")


def normalize_thai(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFC", s)
    s = s.replace("ํ้า", "้ำ")  # ํ้า → ้ำ (กู้ น้ำ เพี้ยน)
    s = _CSL.sub("คสล", s)
    s = _WS.sub(" ", s).strip()
    return s
```

- [ ] **Step 4: รัน test ให้ PASS**

Run: `$env:PYTHONIOENCODING="utf-8"; python scripts/test_text_normalize.py`
Expected: `✅ PASS 9 cases`

- [ ] **Step 5: Commit**

```bash
git add scripts/text_normalize.py scripts/test_text_normalize.py
git commit -m "feat(vocab): text_normalize — กู้ Unicode เพี้ยน (นํ้า→น้ำ, คสล)"
```

---

### Task 2: Wire normalize เข้า classifier + matcher + re-validate

**Files:** Modify `scripts/work_type_classifier.py:42`, `scripts/job_matcher.py:140,154`

- [ ] **Step 1: classifier — เพิ่ม import + normalize**

ใน `scripts/work_type_classifier.py`: เพิ่ม import หลัง `from pathlib import Path`:
```python
from text_normalize import normalize_thai
```
แก้บรรทัด `title = title or ""` (ใน `classify_work_type`) เป็น:
```python
    title = normalize_thai(title)
```

- [ ] **Step 2: matcher — เพิ่ม import + normalize ทั้ง 2 จุด**

ใน `scripts/job_matcher.py`: เพิ่ม import (ใกล้ import อื่นด้านบน):
```python
from text_normalize import normalize_thai
```
แก้ **ทั้ง 2 บรรทัด** ที่เป็น `name = project_name or ""` (บรรทัด ~140 ใน prefilter และ ~154 ใน `match_job`) เป็น:
```python
    name = normalize_thai(project_name)
```

- [ ] **Step 3: รัน unit test เดิม (กัน regression)**

Run: `$env:PYTHONIOENCODING="utf-8"; python scripts/test_work_type_classifier.py`
Expected: `✅ PASS 11 cases` (เคส spelling ถูกอยู่แล้ว ไม่กระทบ)

- [ ] **Step 4: วัด UNKNOWN before/after + precision**

Run: `$env:PYTHONIOENCODING="utf-8"; python scripts/validate_work_type.py`
Expected: UNKNOWN ลดจาก 4.4% (เป้า: ลง ~0.3% จาก พวก นํ้า ที่ตอนนี้ match ธนาคารน้ำใต้ดินได้แล้ว). เปิด `data/work_type_validation_<ts>.txt` audit สะพาน/แหล่งน้ำ ว่า precision ไม่ตก (ยังควร ≥ 90%).
ถ้า coverage/precision **ตก** → STOP, ตรวจว่า normalize ทำคำอื่นเพี้ยนไหม (เช่น คสล ไปชนคำ) ก่อน commit.

- [ ] **Step 5: Sanity matcher — normalize ไม่ทำ match เพี้ยน**

Run:
```
$env:PYTHONIOENCODING="utf-8"; python -c "import sys; sys.path.insert(0,'scripts'); from job_matcher import match_job; print(match_job('ก่อสร้างรางระบายน้ำ คสล. ตำบลบ้านแพง','นครพนม','บ้านแพง')[0])"
```
Expected: ผลลัพธ์เป็น dict/tuple ไม่ error (normalize ทำงานใน path matcher).

- [ ] **Step 6: Commit**

```bash
git add scripts/work_type_classifier.py scripts/job_matcher.py
git commit -m "feat(vocab): wire normalize_thai เข้า classifier+matcher (กู้ UNKNOWN เพี้ยน)"
```

---

### Task 3: `construction_vocab.json` + `mine_vocab_gaps.py`

**Files:** Create `config/construction_vocab.json`, `scripts/mine_vocab_gaps.py`

- [ ] **Step 1: สร้างคลังเปล่า** — `config/construction_vocab.json`:

```json
{
  "version": "v1",
  "updated": "2026-06-05",
  "terms": []
}
```

- [ ] **Step 2: เขียน `scripts/mine_vocab_gaps.py`**

```python
"""mine_vocab_gaps.py — ขุด candidate keyword จาก "ช่องโหว่" (offline, pythainlp).
gap = (a) UNKNOWN จ้างก่อสร้าง [classifier]  (b) จ้างก่อสร้างในตำบลเป้าหมาย ที่ matcher ไม่มี keyword.
กรองหนัก (เลข/สถานที่/stopword/generic/boilerplate/มีแล้ว) → uni+bigram freq≥FLOOR → merge เข้าคลัง + Sheet.
รัน: python scripts/mine_vocab_gaps.py
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from pythainlp.tokenize import word_tokenize
from pythainlp.corpus import thai_stopwords
from text_normalize import normalize_thai
from work_type_classifier import classify_work_type
from sheets_client import get_client

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "winner_history.db"
VOCAB = ROOT / "config" / "construction_vocab.json"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
FLOOR = 10
THAI = re.compile(r"^[ก-๙]+$")
NUM = re.compile(r"[0-9๐-๙]")
STOP = set(thai_stopwords())
GENERIC = set("""จ้าง โครงการ ก่อสร้าง ปรับปรุง ซ่อมแซม ซ่อม โดยวิธี วิธี เฉพาะเจาะจง ตกลงราคา ประกวดราคา
อิเล็กทรอนิกส์ สอบราคา คัดเลือก หมู่ ตำบล อำเภอ จังหวัด บ้าน ที่ แห่ง จำนวน ขนาด พร้อม ภายใน เพื่อ ของ และ
งาน เหมา ดำเนินการ ตาม แบบ รายการ ป้าย ประจำ ปีงบประมาณ งบประมาณ สาย เส้น หมู่ที่ ราย นาย นาง กว้าง ยาว
หนา เมตร พื้นที่ ระบบ ศูนย์ องค์การบริหารส่วนตำบล เทศบาล การ ความ โครง คสล""".split())
# boilerplate = คำบรรยายโครงการ (เจอจาก probe) ไม่ใช่ "ประเภทงาน"
BOILER = set("""เศรษฐกิจพอเพียง ภัยแล้ง ยั่งยืน ส่งเสริมอาชีพ ส่งเสริม อาชีพ ฤดูแล้ง ปรัชญา ต้นทุน เก็บกัก
เพิ่มปริมาณ ท่วม อย่างยั่งยืน แนวปรัชญา การแก้ปัญหา ช่วงฤดูแล้ง ไว้ใช้ ตามแนว แห่ง""".split())


def load_vocab():
    return json.loads(VOCAB.read_text(encoding="utf-8"))


def place_stoplist(con):
    place = set()
    for prov, dist, sub in con.execute("SELECT DISTINCT province, district, subdistrict FROM winner_history"):
        for g in (prov, dist, sub):
            if g and "(" not in g and not re.match(r"^(POINT|LINE|POLY|MULTI)", g):
                place.add(g.strip())
                for t in word_tokenize(g, engine="newmm", keep_whitespace=False):
                    if len(t.strip()) >= 2:
                        place.add(t.strip())
    return place


def existing_terms():
    terms = set()
    wt = json.loads((ROOT / "config" / "work_type_keywords.json").read_text(encoding="utf-8"))
    for kws in wt["categories"].values():
        terms |= set(kws)
    terms |= set(wt["other_keywords"])
    mp = json.loads((ROOT / "config" / "matching_preferences.json").read_text(encoding="utf-8"))
    terms |= set(mp.get("keywords", []))
    return terms


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    mp = json.loads((ROOT / "config" / "matching_preferences.json").read_text(encoding="utf-8"))
    target_tb = set(mp.get("target_tambons", []))
    mkw = mp.get("keywords", [])
    place = place_stoplist(con)
    have = existing_terms()

    # gap jobs: (a) UNKNOWN  (b) ตำบลเป้าหมาย + ไม่มี matcher keyword
    gap = []  # (name, gap_source)
    for rj, sub in con.execute("SELECT raw_json, subdistrict FROM winner_history"):
        d = json.loads(rj)
        if d.get("ชื่อประเภทโครงการ") != "จ้างก่อสร้าง":
            continue
        name = normalize_thai(d.get("ชื่อโครงการ") or "")
        if not name:
            continue
        is_unknown = classify_work_type(name)["primary"] == "UNKNOWN"
        in_target = (sub or "").strip() in target_tb
        no_mkw = in_target and not any(k in name for k in mkw)
        if is_unknown or no_mkw:
            src = "both" if (is_unknown and no_mkw) else ("classifier" if is_unknown else "matcher")
            gap.append((name, src))
    con.close()
    print(f"gap jobs: {len(gap)}")

    def keep(t):
        t = t.strip()
        return (len(t) >= 2 and THAI.match(t) and not NUM.search(t)
                and t not in STOP and t not in GENERIC and t not in BOILER
                and t not in place and t not in have)

    df, src_of, ex_of = Counter(), {}, {}
    for name, src in gap:
        toks = word_tokenize(name, engine="newmm", keep_whitespace=False)
        seen = set()
        for i, t in enumerate(toks):
            t = t.strip()
            if keep(t):
                seen.add(t)
            if i + 1 < len(toks):
                bg = t + toks[i + 1].strip()
                if THAI.match(bg) and not NUM.search(bg) and bg not in have and len(bg) >= 4 \
                        and (keep(t) or keep(toks[i + 1])) and bg not in BOILER:
                    seen.add(bg)
        for s in seen:
            df[s] += 1
            src_of.setdefault(s, src)
            ex_of.setdefault(s, name[:70])

    cands = [(t, n) for t, n in df.most_common() if n >= FLOOR]
    print(f"candidate (freq>={FLOOR}): {len(cands)}")

    # merge เข้าคลัง — term ใหม่=candidate, ของเดิม (approved/rejected) ไม่แตะ (refresh freq/example ได้)
    vocab = load_vocab()
    by_term = {e["term"]: e for e in vocab["terms"]}
    added = 0
    for t, n in cands:
        if t in by_term:
            by_term[t]["freq"] = n
            continue
        by_term[t] = {"term": t, "freq": n, "examples": [ex_of[t]], "gap": src_of[t],
                      "category": "", "bsc_relevant": False, "status": "candidate", "guard": None}
        added += 1
    vocab["terms"] = sorted(by_term.values(), key=lambda e: -e["freq"])
    vocab["updated"] = datetime.now().strftime("%Y-%m-%d")
    VOCAB.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"คลัง: +{added} candidate ใหม่ (รวม {len(vocab['terms'])})")

    # push Sheet review (เฉพาะ status=candidate)
    rows = [["term", "freq", "gap", "ตัวอย่าง", "approve(✓/✗)", "หมวด", "bsc(y/n)", "guard"]]
    for e in vocab["terms"]:
        if e["status"] == "candidate":
            rows.append([e["term"], e["freq"], e["gap"], e["examples"][0], "", e["category"],
                         "y" if e["bsc_relevant"] else "", e["guard"] or ""])
    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet("vocab_review"); ws.clear()
    except Exception:
        ws = sh.add_worksheet(title="vocab_review", rows=len(rows) + 10, cols=8)
    ws.resize(rows=len(rows) + 2, cols=8)
    ws.update(values=rows, range_name="A1")
    ws.freeze(rows=1)
    print(f"📊 Sheet 'vocab_review': {len(rows)-1} candidate รอรีวิว")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: รัน mining + sanity**

Run: `$env:PYTHONIOENCODING="utf-8"; python scripts/mine_vocab_gaps.py`
Expected: print `gap jobs: N`, `candidate (freq>=10): M` (คาด M หลักสิบ-ร้อยต้นๆ), เขียน vocab + Sheet tab. เปิด Sheet `vocab_review` เช็คว่าคำส่วนใหญ่เป็น "ประเภทงาน" จริง (ไม่ใช่ boilerplate/สถานที่). ถ้ายัง noise เยอะ → เพิ่มคำใน `BOILER`/`GENERIC` แล้วรันใหม่.

- [ ] **Step 4: Commit**

```bash
git add config/construction_vocab.json scripts/mine_vocab_gaps.py
git commit -m "feat(vocab): gap-driven mining → construction_vocab.json + Sheet review"
```

---

### Task 4: `apply_vocab_review.py` + `test_vocab_sync.py`

**Files:** Create `scripts/apply_vocab_review.py`, `scripts/test_vocab_sync.py`

- [ ] **Step 1: เขียน test sync (TDD)** — `scripts/test_vocab_sync.py`:

```python
"""test_vocab_sync.py — sync ต้อง additive + idempotent + ไม่ทำลาย key เดิม."""
import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from apply_vocab_review import sync_into_configs  # noqa: E402

def main():
    wt = {"version": "v1", "categories": {"ถนน": ["ถนน"], "ดิน/ปรับพื้นที่": []},
          "other_keywords": ["ป้าย"], "guards": {}, "priority": ["ถนน"]}
    mp = {"keywords": ["รางระบาย"], "target_tambons": ["บ้านแพง"], "negative_keywords": []}
    approved = [
        {"term": "ผนังกันดิน", "category": "ดิน/ปรับพื้นที่", "bsc_relevant": True, "guard": None, "status": "approved"},
        {"term": "สนามกีฬา", "category": "OTHER", "bsc_relevant": False, "guard": None, "status": "approved"},
        {"term": "ถนน", "category": "ถนน", "bsc_relevant": True, "guard": None, "status": "approved"},  # มีแล้ว
    ]
    wt2, mp2 = copy.deepcopy(wt), copy.deepcopy(mp)
    sync_into_configs(approved, wt2, mp2)
    fails = []
    if "ผนังกันดิน" not in wt2["categories"]["ดิน/ปรับพื้นที่"]: fails.append("ดิน ไม่ได้ ผนังกันดิน")
    if "สนามกีฬา" not in wt2["other_keywords"]: fails.append("OTHER ไม่ได้ สนามกีฬา")
    if "ผนังกันดิน" not in mp2["keywords"]: fails.append("matcher ไม่ได้ ผนังกันดิน (bsc=y)")
    if "สนามกีฬา" in mp2["keywords"]: fails.append("matcher ได้ สนามกีฬา ผิด (bsc=n)")
    if wt2["categories"]["ถนน"].count("ถนน") != 1: fails.append("ถนน ซ้ำ (ไม่ idempotent)")
    if mp2["target_tambons"] != ["บ้านแพง"]: fails.append("target_tambons เปลี่ยน (ทำลาย key เดิม)")
    # idempotent: รันซ้ำผลเท่าเดิม
    wt3, mp3 = copy.deepcopy(wt2), copy.deepcopy(mp2)
    sync_into_configs(approved, wt3, mp3)
    if wt3 != wt2 or mp3 != mp2: fails.append("รันซ้ำผลเปลี่ยน (ไม่ idempotent)")
    if fails:
        print("❌ FAIL:\n" + "\n".join("  " + f for f in fails)); sys.exit(1)
    print("✅ PASS sync additive + idempotent + คง key เดิม")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: รัน test ให้ FAIL** — `$env:PYTHONIOENCODING="utf-8"; python scripts/test_vocab_sync.py` → FAIL (`No module named 'apply_vocab_review'`)

- [ ] **Step 3: เขียน `scripts/apply_vocab_review.py`**

```python
"""apply_vocab_review.py — อ่าน Sheet vocab_review → อัปเดต construction_vocab.json status
→ sync term approved เข้า work_type_keywords.json + matching_preferences.json (additive, backup ก่อน).
รัน: python scripts/apply_vocab_review.py
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from sheets_client import get_client

ROOT = Path(__file__).parent.parent
VOCAB = ROOT / "config" / "construction_vocab.json"
WT = ROOT / "config" / "work_type_keywords.json"
MP = ROOT / "config" / "matching_preferences.json"
BACKUP = ROOT / "backups"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"


def sync_into_configs(approved, wt, mp):
    """เติม term approved เข้า config (additive, idempotent). แก้ wt, mp in-place."""
    for e in approved:
        term, cat = e["term"], e.get("category") or ""
        # classifier
        if cat and cat != "OTHER" and cat in wt["categories"]:
            if term not in wt["categories"][cat]:
                wt["categories"][cat].append(term)
        elif cat == "OTHER":
            if term not in wt["other_keywords"]:
                wt["other_keywords"].append(term)
        if e.get("guard"):
            wt.setdefault("guards", {})[term] = e["guard"]
        # matcher
        if e.get("bsc_relevant") and term not in mp["keywords"]:
            mp["keywords"].append(term)


def main():
    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    rows = sh.worksheet("vocab_review").get_all_values()[1:]  # ข้าม header
    # cols: term, freq, gap, ตัวอย่าง, approve, หมวด, bsc, guard
    review = {}
    for r in rows:
        if not r or not r[0].strip():
            continue
        term = r[0].strip()
        approve = (r[4] or "").strip()
        review[term] = {
            "approve": approve in ("✓", "y", "yes", "Y", "ใช่", "1"),
            "reject": approve in ("✗", "x", "n", "no", "ไม่"),
            "category": (r[5] or "").strip(),
            "bsc_relevant": (r[6] or "").strip().lower() in ("y", "yes", "1", "ใช่"),
            "guard": (r[7] or "").strip() or None,
        }

    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    approved = []
    for e in vocab["terms"]:
        rv = review.get(e["term"])
        if not rv:
            continue
        if rv["approve"]:
            e["status"] = "approved"
            e["category"] = rv["category"] or e["category"]
            e["bsc_relevant"] = rv["bsc_relevant"]
            e["guard"] = rv["guard"]
        elif rv["reject"]:
            e["status"] = "rejected"
        if e["status"] == "approved":
            approved.append(e)
    VOCAB.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")

    # backup + sync
    BACKUP.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(WT, BACKUP / f"work_type_keywords_{ts}.json")
    shutil.copy(MP, BACKUP / f"matching_preferences_{ts}.json")
    wt = json.loads(WT.read_text(encoding="utf-8"))
    mp = json.loads(MP.read_text(encoding="utf-8"))
    before = (sum(len(v) for v in wt["categories"].values()) + len(wt["other_keywords"]), len(mp["keywords"]))
    sync_into_configs(approved, wt, mp)
    after = (sum(len(v) for v in wt["categories"].values()) + len(wt["other_keywords"]), len(mp["keywords"]))
    WT.write_text(json.dumps(wt, ensure_ascii=False, indent=2), encoding="utf-8")
    MP.write_text(json.dumps(mp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ approved {len(approved)} | classifier kw {before[0]}→{after[0]} | matcher kw {before[1]}→{after[1]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: รัน test ให้ PASS** — `$env:PYTHONIOENCODING="utf-8"; python scripts/test_vocab_sync.py` → `✅ PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/apply_vocab_review.py scripts/test_vocab_sync.py
git commit -m "feat(vocab): apply_vocab_review — Sheet→คลัง→sync config (additive+test)"
```

---

### Task 5: รอบจริง — mine → review → apply → validate (human-in-loop)

**Files:** ใช้สคริปต์ Task 1-4 + curate ใน Sheet

- [ ] **Step 1: รัน mining** — `$env:PYTHONIOENCODING="utf-8"; python scripts/mine_vocab_gaps.py` → ได้ candidate ใน Sheet `vocab_review`

- [ ] **Step 2: กัญจน์ review ใน Sheet** — เรียงตามความถี่, ต่อแถวใส่ `approve` = ✓/✗, แก้ `หมวด` (core 7 / OTHER), `bsc` (y/n), `guard` (regex ถ้าคำสั้นเสี่ยงชน เช่น INC-002). ไม่ต้องครบรอบเดียว

- [ ] **Step 3: apply + sync** — `$env:PYTHONIOENCODING="utf-8"; python scripts/apply_vocab_review.py` → print classifier/matcher kw before→after

- [ ] **Step 4: validate (CLAUDE.md บังคับ)**

Run: `$env:PYTHONIOENCODING="utf-8"; python scripts/test_work_type_classifier.py; python scripts/validate_work_type.py`
Expected: unit test PASS, UNKNOWN ลดลง (เป้ารวม < 3%), precision ทุกหมวด ≥ 90% (audit ถ้าขยับ). ถ้าหมวดไหนตก → ดู keyword ที่เพิ่งเพิ่ม, แก้ category/guard ใน Sheet → apply ใหม่

- [ ] **Step 5: Discord + commit**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "✅ Construction vocab รอบ 1: classifier kw +X, matcher kw +Y, UNKNOWN A%→B%")
```
```bash
git add config/construction_vocab.json config/work_type_keywords.json config/matching_preferences.json data/work_type_validation_*.txt progress_log.md
git commit -m "feat(vocab): รอบ 1 curate — classifier+matcher keyword จากคลังคำกลาง"
```

---

## Self-Review

**Spec coverage:**
- §3 Step 1 normalize → Task 1+2 ✓ · §5 text_normalize map → Task 1 (นํ้า/คสล/ws) ✓
- §6 gap mining (UNKNOWN+matcher-cut, filters, uni+bigram, floor) → Task 3 ✓
- §7 vocab schema (term/freq/gap/category/bsc_relevant/status/guard) → Task 3 Step 1+2 ✓
- §8 review Sheet + apply + sync additive → Task 4 ✓ · §9 validation → Task 2 Step 4 + Task 5 Step 4 ✓
- §10 out-of-scope (no full-mine/pythainlp-in-pipeline/auto-adopt) → ไม่มี task ✓

**Placeholder scan:** X/Y/A/B/M/N = runtime report values (ไม่ใช่ placeholder). ไม่มี TBD. Task 5 = human-in-loop (curate) โดยตั้งใจ — มีคำสั่ง+expected ทุก step.

**Type consistency:** `normalize_thai(s)->str` ใช้ตรงกัน Task 1/2/3. vocab entry keys (term/freq/examples/gap/category/bsc_relevant/status/guard) ตรงกัน Task 3↔4. `sync_into_configs(approved, wt, mp)` signature ตรงกัน test (Task 4 Step 1) ↔ impl (Step 3). config keys (categories/other_keywords/guards/keywords) ตรง schema จริง. ✓
