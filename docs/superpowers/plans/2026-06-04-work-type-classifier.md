# Work-Type Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** จัดหมวดงานก่อสร้างย่อย (ถนน/ราง/อาคาร/สะพาน/แหล่งน้ำ/ดิน/ไฟฟ้า) จาก **ชื่องาน** ด้วย rule-based keyword classifier แล้วต่อยอดเป็น market analytics จาก winner_history 617K.

**Architecture:** โมดูล pure-function ใหม่ (`work_type_classifier.py`) แยกขาดจาก `classifier_tags.py` เดิม (parallel system กัน production พัง). Taxonomy/keyword/priority อยู่ใน `config/work_type_keywords.json` แก้ได้โดยไม่แตะ logic. Calibrate กับ 617K (validation set + แหล่งค้น keyword ที่ขาด) จน coverage+precision ≥ 90/90 ก่อนค่อยทำ analytics. Migration เพิ่ม column ใน `winner_history.db` ตามแบบ `_winner_history_proctype_fix.py` (snapshot → idempotent ADD COLUMN → recompute → sanity).

**Tech Stack:** Python 3.14, sqlite3 (stdlib), re (Thai keyword guard), gspread (Sheet), JSON config. **ไม่มี pytest ในเครื่อง** — test = standalone script + `assert` + `__main__` runner (ตาม `scripts/test_province_extractor.py`).

**Spec:** `docs/superpowers/specs/2026-06-04-work-type-classifier-design.md`

---

## File Structure

| ไฟล์ | สร้าง/แก้ | หน้าที่ |
|---|---|---|
| `config/work_type_keywords.json` | **สร้าง** | taxonomy 7 core + other_keywords + guards (regex) + priority + version |
| `scripts/work_type_classifier.py` | **สร้าง** | `classify_work_type(title) -> dict` (pure, no side effect) |
| `scripts/test_work_type_classifier.py` | **สร้าง** | unit test (standalone assert runner) |
| `scripts/validate_work_type.py` | **สร้าง** | รันกับ 52,525 จ้างก่อสร้าง → coverage + stratified precision + dump UNKNOWN bucket |
| `scripts/migrate_work_type_column.py` | **สร้าง** | Phase 1: snapshot → ADD COLUMN work_type/work_type_version → recompute เฉพาะจ้างก่อสร้าง → sanity |
| `scripts/_work_type_sheet.py` | **สร้าง** | Phase 1: เขียน Sheet 3 มุม (primary+secondary counting) |

**Invariant ที่ห้ามพลาด (จาก spec §7):**
- **Classification** (จัดงานเข้าหมวด, validation) → ใช้ `primary` เดี่ยว.
- **Analytics** (Sheet 3 มุม) → นับงานเข้า **ทุกหมวดใน `all` (primary+secondary)** — งานหนึ่งนับได้หลายหมวด. กัน undercount งานราง (BSC = ทรัพย์คอนกรีต ผลิตราง/ท่อ).

---

## PHASE 0 — Classifier + Validation Gate

### Task 1: Config taxonomy + keywords

**Files:**
- Create: `config/work_type_keywords.json`

- [ ] **Step 1: เขียน config ตั้งต้น (v1.0)**

สร้าง `config/work_type_keywords.json`:

```json
{
  "version": "v1.0",
  "categories": {
    "สะพาน": ["สะพาน", "ท่อลอดเหลี่ยม", "ทางต่างระดับ", "ทางเชื่อม", "บ็อกซ์คัลเวิร์ต"],
    "แหล่งน้ำ/ชลประทาน": ["ฝาย", "ขุดลอก", "อ่างเก็บน้ำ", "ประตูระบายน้ำ", "อาคารบังคับน้ำ", "บาดาล", "ประปา", "สถานีสูบน้ำ", "คลอง", "ทำนบ", "พนังกั้นน้ำ", "ดาดคอนกรีต"],
    "รางระบายน้ำ/ท่อ": ["ราง", "ท่อ", "ร่องระบาย", "บ่อพัก"],
    "อาคาร": ["อาคาร", "รั้ว", "กำแพง", "ศาลา", "ห้องน้ำ", "โรงเรียน", "หลังคา", "ฝ้าเพดาน", "ลานคอนกรีต", "ต่อเติม", "ห้องประชุม", "โรงจอด", "ป้อม"],
    "ถนน": ["ถนน", "ลาดยาง", "ผิวจราจร", "แอสฟัลต์", "ลูกรัง", "ไหล่ทาง", "เสริมผิว", "พาราแอสฟัลต์", "หินคลุก", "ผิวทาง", "คันทาง"],
    "ดิน/ปรับพื้นที่": ["ถมดิน", "ปรับพื้นที่", "งานดิน", "ปรับเกลี่ย", "ดินถม", "ถมที่"],
    "ไฟฟ้า/ส่องสว่าง": ["ไฟฟ้าส่องสว่าง", "ไฟฟ้าแสงสว่าง", "เสาไฟ", "โคมไฟ", "ไฟกิ่ง", "ส่องสว่าง"]
  },
  "other_keywords": ["สนามกีฬา", "ลานกีฬา", "สวนสาธารณะ", "ภูมิทัศน์", "เครื่องออกกำลังกาย", "หอกระจายข่าว", "เสียงตามสาย", "กล้องวงจรปิด", "CCTV", "ป้าย"],
  "guards": {
    "ราง": "(?<!ตา)ราง(?!วัล|กูร)",
    "ท่อ": "ท่อ(?!ง)(?!น(?!้))"
  },
  "priority": ["สะพาน", "แหล่งน้ำ/ชลประทาน", "อาคาร", "ถนน", "รางระบายน้ำ/ท่อ", "ไฟฟ้า/ส่องสว่าง", "ดิน/ปรับพื้นที่", "OTHER"]
}
```

หมายเหตุ design:
- `guards` = regex string ต่อ keyword เสี่ยง substring (reuse INC-002/L-007 จาก `job_matcher.py:37-40`). `ราง` กัน ตาราง/รางวัล/วรางกูร, `ท่อ` กัน ท่อง/ท่อน แต่เก็บ ท่อน้ำ.
- keyword ที่ไม่มีใน `guards` → ใช้ substring ปกติ (`kw in title`).
- config นี้เป็น **ตั้งต้น** — Task 4 (calibration loop) จะเพิ่ม keyword ที่ขาดจาก UNKNOWN bucket แล้ว bump version.

- [ ] **Step 2: ตรวจ JSON valid**

Run: `python -c "import json; json.load(open('config/work_type_keywords.json', encoding='utf-8')); print('valid')"`
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add config/work_type_keywords.json
git commit -m "feat(work-type): taxonomy config v1.0 (7 core + ไฟฟ้า + guards)"
```

---

### Task 2: Classifier module (`classify_work_type`)

**Files:**
- Create: `scripts/work_type_classifier.py`
- Test: `scripts/test_work_type_classifier.py`

- [ ] **Step 1: เขียน failing test ก่อน (TDD)**

สร้าง `scripts/test_work_type_classifier.py`:

```python
"""test_work_type_classifier.py — unit test (standalone assert runner, ไม่มี pytest ในเครื่อง)
รัน: python scripts/test_work_type_classifier.py  → exit 0 ถ้าผ่านหมด, exit 1 ถ้า fail
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from work_type_classifier import classify_work_type, WORK_TYPE_VERSION  # noqa: E402

CASES = [
    # (title, expected_primary, expected_secondary_set)
    ("ก่อสร้างถนน คสล. พร้อมรางระบายน้ำ", "ถนน", {"รางระบายน้ำ/ท่อ"}),
    ("ก่อสร้างรางระบายน้ำ รูปตัวยู", "รางระบายน้ำ/ท่อ", set()),
    ("ก่อสร้างอาคารเรียน 3 ชั้น", "อาคาร", set()),
    ("ปรับปรุงผิวจราจรลาดยางแอสฟัลต์", "ถนน", set()),
    ("ก่อสร้างสนามกีฬาอเนกประสงค์", "OTHER", set()),
    ("จัดซื้อวัสดุสำนักงาน", "UNKNOWN", set()),
    ("ก่อสร้างสะพาน คสล. ข้ามคลอง", "สะพาน", {"แหล่งน้ำ/ชลประทาน"}),
    ("ติดตั้งไฟฟ้าส่องสว่างพลังงานแสงอาทิตย์", "ไฟฟ้า/ส่องสว่าง", set()),
    ("ก่อสร้างถนนพร้อมไฟฟ้าส่องสว่าง", "ถนน", {"ไฟฟ้า/ส่องสว่าง"}),
    ("จ้างเหมาจัดทำตารางเมตรวัดพื้นที่", "UNKNOWN", set()),  # guard: ตาราง ไม่ใช่ ราง
    ("มอบรางวัลประจำปี", "UNKNOWN", set()),                  # guard: รางวัล ไม่ใช่ ราง
]


def main():
    fails = []
    for title, exp_primary, exp_secondary in CASES:
        r = classify_work_type(title)
        if r["primary"] != exp_primary:
            fails.append(f"  PRIMARY  {title!r}: got {r['primary']!r} != {exp_primary!r}")
        if set(r["secondary"]) != exp_secondary:
            fails.append(f"  SECONDARY {title!r}: got {set(r['secondary'])} != {exp_secondary}")
        if r["version"] != WORK_TYPE_VERSION:
            fails.append(f"  VERSION  {title!r}: got {r['version']!r}")
        # primary ต้องเป็นตัวแรกของ all
        if r["all"] and r["all"][0] != r["primary"]:
            fails.append(f"  ALL-ORDER {title!r}: all[0]={r['all'][0]!r} != primary")

    if fails:
        print(f"❌ FAIL {len(fails)} assertions:")
        print("\n".join(fails))
        sys.exit(1)
    print(f"✅ PASS {len(CASES)} cases")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: รัน test ให้ FAIL (module ยังไม่มี)**

Run: `python scripts/test_work_type_classifier.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'work_type_classifier'`

- [ ] **Step 3: เขียน classifier ให้ test ผ่าน**

สร้าง `scripts/work_type_classifier.py`:

```python
"""work_type_classifier.py — จัดหมวดงานก่อสร้างจากชื่องาน (rule-based, pure functions).
ดู design: docs/superpowers/specs/2026-06-04-work-type-classifier-design.md

classify_work_type(title) -> {"primary", "secondary", "all", "version"}
  primary   = หมวด score สูงสุด (tie → priority list → ตำแหน่ง keyword เร็วสุด)
  secondary = หมวด core อื่น score>=1 (เรียงตาม score)
  all       = [primary, *secondary]
  score     = จำนวน keyword "ตัวที่ไม่ซ้ำ" ต่อหมวดที่เจอในชื่อ (distinct, กันคำซ้ำ inflate)

ถัง: OTHER = match other_keywords (ไม่ใช่ core), UNKNOWN = ไม่ match keyword ใดเลย.
guard ภาษาไทย: keyword เสี่ยง substring (ราง/ท่อ) ใช้ regex จาก config['guards'] (INC-002/L-007).
"""
import json
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CFG = json.loads((_ROOT / "config" / "work_type_keywords.json").read_text(encoding="utf-8"))

WORK_TYPE_VERSION = _CFG["version"]
_CATEGORIES = _CFG["categories"]
_OTHER_KW = _CFG["other_keywords"]
_PRIORITY = _CFG["priority"]
_GUARDS = {k: re.compile(v) for k, v in _CFG.get("guards", {}).items()}


def _first_pos(k: str, title: str) -> int:
    """ตำแหน่งแรกที่ keyword โผล่ (เคารพ guard) — ใช้ tie-break ชั้น 3."""
    g = _GUARDS.get(k)
    if g:
        m = g.search(title)
        return m.start() if m else -1
    return title.find(k)


def _hit(k: str, title: str) -> bool:
    g = _GUARDS.get(k)
    return bool(g.search(title)) if g else (k in title)


def classify_work_type(title: str) -> dict:
    title = title or ""

    # 1) score ต่อหมวด = จำนวน keyword distinct ที่ hit
    scores = {}      # cat -> distinct keyword count
    earliest = {}    # cat -> ตำแหน่ง keyword เร็วสุด
    for cat, kws in _CATEGORIES.items():
        hits = [k for k in kws if _hit(k, title)]
        if hits:
            scores[cat] = len(set(hits))
            earliest[cat] = min(_first_pos(k, title) for k in hits if _first_pos(k, title) >= 0)

    if scores:
        # primary: max score → tie priority → tie ตำแหน่งเร็วสุด
        def sort_key(cat):
            pri = _PRIORITY.index(cat) if cat in _PRIORITY else len(_PRIORITY)
            return (-scores[cat], pri, earliest[cat])

        ordered = sorted(scores, key=sort_key)
        primary = ordered[0]
        secondary = ordered[1:]  # หมวด core อื่นทั้งหมด score>=1
        return {
            "primary": primary,
            "secondary": secondary,
            "all": [primary, *secondary],
            "version": WORK_TYPE_VERSION,
        }

    # 2) ไม่มี core → OTHER ถ้า match other_keywords
    if any(k in title for k in _OTHER_KW):
        return {"primary": "OTHER", "secondary": [], "all": ["OTHER"], "version": WORK_TYPE_VERSION}

    # 3) ไม่ match อะไรเลย → UNKNOWN
    return {"primary": "UNKNOWN", "secondary": [], "all": ["UNKNOWN"], "version": WORK_TYPE_VERSION}
```

- [ ] **Step 4: รัน test ให้ PASS**

Run: `python scripts/test_work_type_classifier.py`
Expected: `✅ PASS 11 cases`

ถ้า fail: อ่าน assertion ที่ตก → ปรับ keyword/guard ใน config (ไม่แก้ logic) จนผ่าน. เช่น ถ้า "ก่อสร้างสะพาน คสล. ข้ามคลอง" ไม่ได้ secondary แหล่งน้ำ → ตรวจว่า "คลอง" อยู่ใน category แหล่งน้ำ (อยู่แล้ว).

- [ ] **Step 5: Commit**

```bash
git add scripts/work_type_classifier.py scripts/test_work_type_classifier.py
git commit -m "feat(work-type): classifier core + unit test (11 cases pass)"
```

---

### Task 3: Validation harness (coverage + stratified precision)

**Files:**
- Create: `scripts/validate_work_type.py`
- Test: ใช้ data จริง `data/winner_history.db` (52,525 จ้างก่อสร้าง)

- [ ] **Step 1: เขียน validation script**

สร้าง `scripts/validate_work_type.py`:

```python
"""validate_work_type.py — gate Phase 0: รัน classifier กับ 52,525 งานจ้างก่อสร้าง.
metric:
  coverage  = % งานที่ primary ∉ {OTHER, UNKNOWN}        (acceptance >= 90%)
  precision = สุ่มต่อหมวด → audit เอง (manual)            (acceptance ทุกหมวด >= 90%)
output:
  console: coverage + การกระจาย primary + ขนาด UNKNOWN/OTHER bucket
  data/work_type_validation_<ts>.txt : สุ่มตัวอย่างต่อหมวด (สำหรับ audit precision ด้วยมือ)
  data/work_type_unknown_sample.txt  : สุ่ม 200 ชื่อจาก UNKNOWN (สำหรับหา keyword ขาด)
รัน: python scripts/validate_work_type.py
"""
import json
import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from work_type_classifier import classify_work_type, WORK_TYPE_VERSION  # noqa: E402

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "winner_history.db"
SAMPLE_PER_CAT = 30   # stratified precision audit
UNKNOWN_SAMPLE = 200


def construction_titles():
    """ดึงเฉพาะงานจ้างก่อสร้างจาก raw_json (ground-truth type field)."""
    con = sqlite3.connect(DB)
    titles = []
    for (rj,) in con.execute("SELECT raw_json FROM winner_history"):
        try:
            d = json.loads(rj)
        except Exception:
            continue
        if d.get("ชื่อประเภทโครงการ") == "จ้างก่อสร้าง":
            name = d.get("ชื่อโครงการ") or ""
            if name:
                titles.append(name)
    con.close()
    return titles


def main():
    random.seed(42)
    titles = construction_titles()
    total = len(titles)
    print(f"งานจ้างก่อสร้าง: {total:,}  (classifier {WORK_TYPE_VERSION})")

    by_cat = Counter()          # primary -> count
    samples = {}                # primary -> list ตัวอย่าง (สำหรับ audit)
    unknown_titles = []
    for t in titles:
        r = classify_work_type(t)
        p = r["primary"]
        by_cat[p] += 1
        samples.setdefault(p, []).append(t)
        if p == "UNKNOWN":
            unknown_titles.append(t)

    covered = total - by_cat["OTHER"] - by_cat["UNKNOWN"]
    coverage = covered / total * 100 if total else 0
    print(f"\n=== COVERAGE: {coverage:.1f}%  (acceptance >= 90%) ===")
    gate = "✅ PASS" if coverage >= 90 else "❌ FAIL"
    print(f"gate: {gate}")
    print("\n=== primary distribution ===")
    for cat, n in by_cat.most_common():
        print(f"  {n:>8,}  {n/total*100:>5.1f}%  {cat}")

    # dump stratified sample สำหรับ audit precision ด้วยมือ
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "data" / f"work_type_validation_{ts}.txt"
    lines = [f"classifier {WORK_TYPE_VERSION} | coverage {coverage:.1f}% | total {total:,}\n"]
    lines.append("=== STRATIFIED SAMPLE (audit primary ถูกไหม, นับ precision ต่อหมวด) ===")
    for cat in list(by_cat):
        pool = samples[cat]
        pick = random.sample(pool, min(SAMPLE_PER_CAT, len(pool)))
        lines.append(f"\n{'='*60}\n[{cat}]  n={by_cat[cat]:,}  (สุ่ม {len(pick)})")
        for t in pick:
            lines.append(f"   {t}")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 stratified sample → {out.name}  (audit ด้วยมือ → precision ต่อหมวด)")

    # dump UNKNOWN sample สำหรับหา keyword ขาด (calibration loop)
    uout = ROOT / "data" / "work_type_unknown_sample.txt"
    upick = random.sample(unknown_titles, min(UNKNOWN_SAMPLE, len(unknown_titles)))
    uout.write_text("\n".join(upick), encoding="utf-8")
    print(f"📄 UNKNOWN sample ({len(upick)}) → {uout.name}  (หา keyword ที่ขาด)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: รัน validation (baseline)**

Run: `python scripts/validate_work_type.py`
Expected: พิมพ์ coverage % + distribution + สร้าง 2 ไฟล์ใน `data/`. รอบแรก coverage อาจ < 90% (ปกติ — ยังไม่ calibrate).

- [ ] **Step 3: Commit harness**

```bash
git add scripts/validate_work_type.py
git commit -m "feat(work-type): validation harness — coverage + stratified precision + UNKNOWN dump"
```

---

### Task 4: Calibration loop (gate 90/90)

**Files:**
- Modify: `config/work_type_keywords.json` (เพิ่ม keyword, bump version)
- ใช้: `data/work_type_unknown_sample.txt`, `data/work_type_validation_<ts>.txt`

> **นี่เป็น loop ไม่ใช่ step เดียว** — วนจน gate ผ่านทั้ง coverage และ precision

- [ ] **Step 1: อ่าน UNKNOWN sample หา keyword ที่ขาด**

Read: `data/work_type_unknown_sample.txt`
มองหา pattern ซ้ำที่ควรเข้าหมวด core/OTHER แต่หลุดเป็น UNKNOWN (เช่น "เมรุ", "ป้ายจราจร", "เครื่องเล่นสนาม"). จดคำที่ควรเพิ่ม.

- [ ] **Step 2: เพิ่ม keyword ใน config + bump version**

แก้ `config/work_type_keywords.json`:
- เพิ่มคำที่เจอเข้า category ที่ถูก (core) หรือ `other_keywords`
- bump `"version"` → `"v1.1"` (และทุกรอบถัดไป v1.2, ...)

- [ ] **Step 3: รัน unit test (กัน regression)**

Run: `python scripts/test_work_type_classifier.py`
Expected: `✅ PASS` — ถ้า keyword ใหม่ทำ case เดิมพัง ต้องแก้ก่อน

- [ ] **Step 4: รัน validation ใหม่**

Run: `python scripts/validate_work_type.py`
ดู coverage ขึ้นไหม + เปิด `data/work_type_validation_<ts>.txt` audit precision:
- ต่อหมวด: นับว่าใน ~30 ตัวอย่าง มี primary ผิดกี่ตัว → precision = ถูก/30
- **ทุกหมวด core ต้อง >= 90%** (≤ 3 ผิดจาก 30)
- ถ้าหมวดไหน precision ตก → ดูว่า keyword ตัวไหนดึงผิด → ปรับ (ลบ/เพิ่ม guard/ย้าย priority)

- [ ] **Step 5: วน Step 1-4 จน gate ผ่านทั้งคู่**

หยุดเมื่อ: **coverage >= 90%** AND **precision ทุกหมวด >= 90%**.

- [ ] **Step 6: บันทึกผลลง progress_log + commit**

เพิ่ม entry ใน `progress_log.md` (coverage สุดท้าย + precision ต่อหมวด + เวอร์ชัน config).

```bash
git add config/work_type_keywords.json data/work_type_validation_*.txt progress_log.md
git commit -m "feat(work-type): calibrate config to vX.Y — coverage NN% + precision 90/90 gate PASS"
```

- [ ] **Step 7: Discord notify (จบ Phase 0)**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "✅ Work-Type Classifier Phase 0 เสร็จ — gate ผ่าน (coverage NN%, precision 90/90, config vX.Y)")
```

**⚠️ GATE: ห้ามเริ่ม Phase 1 ก่อน Step 5 ผ่าน.**

---

## PHASE 1 — Analytics (หลัง gate ผ่าน)

### Task 5: Migration — เพิ่ม column `work_type` ใน winner_history.db

**Files:**
- Create: `scripts/migrate_work_type_column.py`
- Modify (data): `data/winner_history.db`
- Pattern อ้างอิง: `scripts/_winner_history_proctype_fix.py`

- [ ] **Step 1: เขียน migration script**

สร้าง `scripts/migrate_work_type_column.py`:

```python
"""migrate_work_type_column.py — Phase 1: เพิ่ม work_type + work_type_version ใน winner_history.db.
แบบเดียวกับ _winner_history_proctype_fix.py: snapshot → idempotent ADD COLUMN → recompute → sanity.
recompute เฉพาะงานจ้างก่อสร้าง (ชื่อประเภทโครงการ=จ้างก่อสร้าง) — งานซื้อ/เช่า เก็บ NULL.
เก็บ work_type = primary (เดี่ยว). secondary/all คำนวณ runtime ตอนทำ analytics (Task 6).
รัน: python scripts/migrate_work_type_column.py
"""
import gzip
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from work_type_classifier import classify_work_type, WORK_TYPE_VERSION  # noqa: E402

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "winner_history.db"
BACKUP_DIR = ROOT / "backups"
BACKUP_DIR.mkdir(exist_ok=True)


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 1) snapshot (rowid, work_type เดิมถ้ามี) — เบา, rollback ได้
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cols = [r[1] for r in cur.execute("PRAGMA table_info(winner_history)")]
    if "work_type" in cols:
        snap = BACKUP_DIR / f"work_type_snapshot_{ts}.json.gz"
        old = cur.execute("SELECT rowid, work_type, work_type_version FROM winner_history").fetchall()
        with gzip.open(snap, "wt", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False)
        print(f"📦 snapshot {len(old):,} rows → {snap.name}")

    # 2) ADD COLUMN (idempotent)
    if "work_type" not in cols:
        cur.execute("ALTER TABLE winner_history ADD COLUMN work_type TEXT")
        print("➕ ADD COLUMN work_type")
    if "work_type_version" not in cols:
        cur.execute("ALTER TABLE winner_history ADD COLUMN work_type_version TEXT")
        print("➕ ADD COLUMN work_type_version")

    # 3) recompute เฉพาะงานจ้างก่อสร้าง
    t0 = time.time()
    updates = []
    n = 0
    for rowid, rj in cur.execute("SELECT rowid, raw_json FROM winner_history"):
        try:
            d = json.loads(rj)
        except Exception:
            continue
        if d.get("ชื่อประเภทโครงการ") != "จ้างก่อสร้าง":
            continue
        name = d.get("ชื่อโครงการ") or ""
        primary = classify_work_type(name)["primary"]
        updates.append((primary, WORK_TYPE_VERSION, rowid))
        n += 1
    cur.executemany(
        "UPDATE winner_history SET work_type=?, work_type_version=? WHERE rowid=?", updates
    )
    con.commit()
    print(f"✅ recompute {n:,} construction rows ({time.time()-t0:.0f}s)")

    # 4) sanity
    print("\n=== SANITY ===")
    tagged = cur.execute("SELECT COUNT(*) FROM winner_history WHERE work_type IS NOT NULL").fetchone()[0]
    print(f"tagged (ต้อง ~52,525): {tagged:,}")
    print("work_type distribution:")
    for v, c in cur.execute(
        "SELECT work_type, COUNT(*) FROM winner_history WHERE work_type IS NOT NULL "
        "GROUP BY work_type ORDER BY 2 DESC"
    ):
        print(f"  {c:>7,}  {v}")
    con.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: รัน migration**

Run: `python scripts/migrate_work_type_column.py`
Expected: `📦 snapshot` (ถ้ารันซ้ำ) → `➕ ADD COLUMN` → `✅ recompute ~52,525` → SANITY: tagged ~52,525, distribution ตรงกับ validation Task 3.

- [ ] **Step 3: Sanity check (CLAUDE.md บังคับ)**

Run:
```bash
python -c "import sqlite3; c=sqlite3.connect('data/winner_history.db'); print('total:', c.execute('SELECT COUNT(*) FROM winner_history').fetchone()[0]); print('tagged:', c.execute('SELECT COUNT(*) FROM winner_history WHERE work_type IS NOT NULL').fetchone()[0])"
```
Expected: total = 617,357 (ไม่หาย), tagged ~52,525. ถ้า total เปลี่ยน → STOP หาสาเหตุ.

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_work_type_column.py
git commit -m "feat(work-type): Phase 1 migration — work_type column (52.5K construction jobs)"
```

---

### Task 6: Analytics Sheet 3 มุม (primary + secondary)

**Files:**
- Create: `scripts/_work_type_sheet.py`
- อ้างอิง pattern Sheet: `scripts/_my_company_sheet.py`

- [ ] **Step 1: ยืนยัน BSC TIN (เลขนิติบุคคลบริษัทเรา) สำหรับมุม "บริษัทเรา"**

Run:
```bash
python -c "import sqlite3; c=sqlite3.connect('data/winner_history.db'); [print(r) for r in c.execute('SELECT winner, winner_tin, COUNT(*) FROM winner_history WHERE winner LIKE \"%ทรัพย์คอนกรีต%\" OR winner LIKE \"%ยศประทาน%\" GROUP BY winner_tin ORDER BY 3 DESC LIMIT 5')]"
```
จด TIN ของ BSC ทรัพย์คอนกรีต + หจก.ยศประทานรุ่งเรืองทรัพย์ ไว้ใส่ `OUR_TINS`.

- [ ] **Step 2: เขียน analytics script (primary+secondary counting)**

สร้าง `scripts/_work_type_sheet.py`:

```python
"""_work_type_sheet.py — Phase 1 analytics: เขียน Sheet 3 มุม จาก work_type.
นับ primary+secondary (spec §7 constraint) — งานหนึ่งนับเข้าทุกหมวดใน all (กัน undercount ราง).
3 มุม:
  1. บริษัทเรา × หมวด — เราชนะหมวดไหน (จำนวน + มูลค่า win_price + ส่วนลดเฉลี่ย)
  2. คู่แข่ง × หมวด     — top winner ต่อหมวด
  3. ตำบล × หมวด        — พื้นที่ × ความต้องการแต่ละหมวด
รัน: python scripts/_work_type_sheet.py
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from work_type_classifier import classify_work_type  # noqa: E402

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "winner_history.db"

# เลขนิติบุคคลบริษัทเรา — เติมจาก Task 6 Step 1
OUR_TINS = {
    # "0xxxxxxxxxxxx",  # BSC ทรัพย์คอนกรีต
    # "0xxxxxxxxxxxx",  # หจก.ยศประทานรุ่งเรืองทรัพย์
}


def load_construction():
    """yield (name, winner, winner_tin, win_price, discount_pct, subdistrict, all_cats)."""
    con = sqlite3.connect(DB)
    for name, winner, tin, wp, disc, sub in con.execute(
        "SELECT project_name, winner, winner_tin, win_price, discount_pct, subdistrict "
        "FROM winner_history WHERE work_type IS NOT NULL"
    ):
        cats = classify_work_type(name or "")["all"]  # primary+secondary
        cats = [c for c in cats if c not in ("OTHER", "UNKNOWN")] or cats
        yield name, winner, tin, wp or 0, disc, sub or "", cats
    con.close()


def main():
    # มุม 1: บริษัทเรา × หมวด
    our = defaultdict(lambda: {"n": 0, "value": 0.0, "disc": []})
    # มุม 2: คู่แข่ง × หมวด -> winner -> count
    rivals = defaultdict(lambda: defaultdict(int))
    # มุม 3: ตำบล × หมวด
    tambon = defaultdict(lambda: defaultdict(int))

    for name, winner, tin, wp, disc, sub, cats in load_construction():
        is_ours = tin in OUR_TINS
        for c in cats:  # นับเข้าทุกหมวด (primary+secondary)
            if is_ours:
                our[c]["n"] += 1
                our[c]["value"] += wp
                if disc is not None:
                    our[c]["disc"].append(disc)
            else:
                rivals[c][winner] += 1
            if sub:
                tambon[sub][c] += 1

    print("=== มุม 1: บริษัทเรา × หมวด ===")
    for c, d in sorted(our.items(), key=lambda x: -x[1]["value"]):
        avg = sum(d["disc"]) / len(d["disc"]) if d["disc"] else 0
        print(f"  {c}: {d['n']} งาน, {d['value']/1e6:.1f} ลบ., ส่วนลดเฉลี่ย {avg:.1f}%")

    print("\n=== มุม 2: คู่แข่ง × หมวด (top 3 ต่อหมวด) ===")
    for c, ws in rivals.items():
        top = sorted(ws.items(), key=lambda x: -x[1])[:3]
        print(f"  [{c}] " + " | ".join(f"{w}({n})" for w, n in top))

    # TODO Step 4: เขียนลง Google Sheet (gspread) — tab ใหม่ 3 tab
    # ใช้ pattern จาก _my_company_sheet.py (service_account + worksheet update)
    print("\n(ขั้นต่อไป: wire เข้า Sheet ตาม _my_company_sheet.py)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: รัน + sanity (console ก่อน wire Sheet)**

Run: `python scripts/_work_type_sheet.py`
Expected: 3 มุมพิมพ์ออกมา. ตรวจ:
- มุม 1 มีหมวด **รางระบายน้ำ/ท่อ** โผล่ (พิสูจน์ว่า secondary counting ทำงาน — งาน "ถนนพร้อมราง" ที่เราชนะ ถูกนับเข้าราง ไม่ undercount)
- ผลรวมสมเหตุผล (ไม่ติดลบ, ไม่ว่าง)

- [ ] **Step 4: Wire เข้า Google Sheet**

อ่าน `scripts/_my_company_sheet.py` เป็น template (service_account auth + worksheet) → เพิ่มฟังก์ชันเขียน 3 tab ใหม่:
`work_type_บริษัทเรา`, `work_type_คู่แข่ง`, `work_type_ตำบล`. Header + rows ตาม 3 มุม.

แก้ `_work_type_sheet.py` แทน TODO ด้วย gspread write (copy pattern). หลัง write รัน sanity:
```python
# ตรวจ row count tab ใหม่ ตรงกับจำนวนหมวด/แถวที่คำนวณ
ws = sh.worksheet("work_type_บริษัทเรา")
print("rows:", len(ws.get_all_values()) - 1)
```

- [ ] **Step 5: Discord notify (Sheet change)**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "📊 Sheet เพิ่ม 3 tab analytics หมวดงาน (บริษัทเรา/คู่แข่ง/ตำบล × หมวด) — Phase 1 เสร็จ")
```

- [ ] **Step 6: Commit**

```bash
git add scripts/_work_type_sheet.py progress_log.md
git commit -m "feat(work-type): Phase 1 analytics — Sheet 3 มุม (primary+secondary counting)"
```

---

## Self-Review (ผู้เขียน plan ตรวจเอง)

**Spec coverage:**
- §3 taxonomy 7 core + OTHER + UNKNOWN → Task 1 config ✓
- §4 primary 3-ชั้น (score → priority → ตำแหน่ง) → Task 2 `sort_key` ✓
- §4 secondary = core อื่น score≥1 → Task 2 `ordered[1:]` ✓
- §5 interface `classify_work_type` + `WORK_TYPE_VERSION` + guard → Task 2 ✓
- §6 validation coverage + stratified precision + UNKNOWN loop → Task 3+4 ✓ (gate 90/90)
- §7 Phase 1 migration + Sheet 3 มุม + **primary+secondary constraint** → Task 5+6 ✓
- §8 out-of-scope (ML/live tagging/per-customer) → ไม่มี task ✓

**Placeholder scan:** Task 6 Step 4 มี "copy pattern จาก _my_company_sheet.py" — เป็น reference ไม่ใช่ placeholder (template มีจริง). `OUR_TINS` เติมจาก Step 1 (ระบุวิธีหาแล้ว). ยอมรับได้.

**Type consistency:** `classify_work_type()` คืน `{primary, secondary, all, version}` ใช้สม่ำเสมอทุก task. `WORK_TYPE_VERSION` import จาก module เดียว. column ชื่อ `work_type`/`work_type_version` ตรงกัน Task 5↔6. ✓
