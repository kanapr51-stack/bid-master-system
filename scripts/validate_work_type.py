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
SAMPLE_PER_CAT = 30
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

    by_cat = Counter()
    samples = {}
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
    print(f"\n📄 stratified sample → {out.name}")

    uout = ROOT / "data" / "work_type_unknown_sample.txt"
    upick = random.sample(unknown_titles, min(UNKNOWN_SAMPLE, len(unknown_titles)))
    uout.write_text("\n".join(upick), encoding="utf-8")
    print(f"📄 UNKNOWN sample ({len(upick)}) → {uout.name}")


if __name__ == "__main__":
    main()
