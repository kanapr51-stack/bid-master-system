"""
build_winner_cache.py — One-time bootstrap (2026-05-15 redesign)

อ่าน awarded_jobs.json (backup, schema เก่า) → write data/winner_cache_bootstrap.json
ใช้โดย Sebastian_Classifier.py round แรก
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

BACKUP_FILE = Path("backups/sheets_2026-05-15_2046/awarded_jobs.json")
OUT_FILE    = Path("data/winner_cache_bootstrap.json")


def parse_thai_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
            if d.year > 2400:
                d = d.replace(year=d.year - 543)
            return d
        except ValueError:
            continue
    return None


def to_float(s):
    if not s:
        return None
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, TypeError):
        return None


def main():
    if not BACKUP_FILE.exists():
        print(f"ERROR: {BACKUP_FILE} not found")
        return

    rows = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(rows)} rows (incl header)")

    headers = rows[0]
    h_idx = {h: i for i, h in enumerate(headers)}
    print(f"Headers: {headers}")

    def g(r, key):
        i = h_idx.get(key, -1)
        return r[i] if 0 <= i < len(r) else ""

    cache = {}
    for r in rows[1:]:
        jid = g(r, "job_id")
        winner = g(r, "ผู้ชนะประมูล")
        if not jid or not winner:
            continue
        budget = to_float(g(r, "budget"))
        win_price = to_float(g(r, "ราคาที่ชนะ (บาท)"))
        discount_pct = ""
        if budget and win_price and budget > 0:
            discount_pct = f"{((budget - win_price) / budget) * 100:.2f}"

        cache[jid] = {
            "winner_name":  winner,
            "winner_price": g(r, "ราคาที่ชนะ (บาท)"),
            "discount_pct": discount_pct,
            "award_date":   g(r, "วันประกาศผู้ชนะ"),
        }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cache)} winners → {OUT_FILE}")


if __name__ == "__main__":
    main()
