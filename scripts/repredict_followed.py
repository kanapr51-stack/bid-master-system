"""repredict_followed.py — งาน 3: re-predict ราคางานที่ปักหมุด (⭐) ทั้งหมดด้วย logic ใหม่.

logic ใหม่ = market segmentation (local/provincial/central) + floor ต่อหมวด + subtype น้ำ/ถนน
+ ค่ากลาง (median). ดู docs/research_market_regime_discount.md.

default = DRY-RUN (เทียบเดิม vs ใหม่ ไม่เขียน). --apply = save_prediction จริง (อัปเดตเฉพาะ
คอลัมน์ prediction — ไม่แตะ actual_price/verified). รันบน VPS (มี cgd_winners + followed_jobs จริง).

usage:
  python repredict_followed.py            # dry-run (ดูผลก่อน)
  python repredict_followed.py --apply     # เขียนจริง
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

import cgd_intel as ci
from Sebastian_Customer_DB import get_connection, get_prediction, save_prediction


def _fmt(v):
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "—"


def _med(p):
    return p.get("area_price_med") if p else None


def run(apply: bool = False, limit: int = 0) -> dict:
    """re-predict followed jobs. apply=False → dry-run (ไม่เขียน). คืน summary dict."""
    mode = "APPLY (เขียนจริง)" if apply else "DRY-RUN (ไม่เขียน)"
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT fj.project_id, ps.project_name, ps.dept_name, ps.province, ps.budget "
            "FROM followed_jobs fj LEFT JOIN projects_seen ps ON ps.project_id=fj.project_id "
            "WHERE fj.status='active'").fetchall()
    if limit:
        rows = rows[:limit]

    print(f"=== repredict followed ⭐ — {mode} ===")
    print(f"งานปักหมุด active: {len(rows)}\n")
    print(f"{'project_id':14s} {'ค่ากลางเดิม':>13s} {'ค่ากลางใหม่':>13s} {'เปลี่ยน':>9s}  งาน")

    n_changed = n_new = n_nodata = n_applied = 0
    for pid, pname, dept, prov, budget in rows:
        if not pname or not prov:
            n_nodata += 1
            print(f"{pid:14s} {'—':>13s} {'—':>13s} {'(ไม่มี context)':>9s}")
            continue
        old = get_prediction(pid)
        old_med = _med(old)
        try:
            ctx = ci.intel_context(prov, pname, dept or "", pid, budget or 0)
        except Exception as e:
            print(f"{pid:14s} ERROR: {str(e)[:50]}")
            continue
        new = ctx.get("prediction") if ctx else None
        new_med = _med(new)
        if new_med is None:
            n_nodata += 1
            print(f"{pid:14s} {_fmt(old_med):>13s} {'—':>13s} {'(คาดไม่ได้)':>9s}  {(pname or '')[:24]}")
            continue
        if old_med is None:
            n_new += 1
            delta = "ใหม่"
        else:
            d = (new_med - old_med) / old_med * 100 if old_med else 0
            delta = f"{d:+.0f}%"
            if abs(d) >= 1:
                n_changed += 1
        print(f"{pid:14s} {_fmt(old_med):>13s} {_fmt(new_med):>13s} {delta:>9s}  {(pname or '')[:24]}")
        if apply and new:
            save_prediction({"project_id": pid, **new})
            n_applied += 1

    print(f"\nสรุป: เปลี่ยน {n_changed} · ใหม่ {n_new} · คาดไม่ได้/ไม่มี context {n_nodata}")
    if apply:
        print(f"✅ เขียนจริงแล้ว {n_applied} งาน")
    else:
        print("ℹ️ DRY-RUN — ยังไม่เขียน (ใส่ --apply เพื่อเขียนจริง)")
    return {"total": len(rows), "changed": n_changed, "new": n_new,
            "nodata": n_nodata, "applied": n_applied}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="เขียน save_prediction จริง (default = dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="จำกัดจำนวนงาน (0 = ทั้งหมด)")
    a = ap.parse_args()
    run(apply=a.apply, limit=a.limit)


if __name__ == "__main__":
    main()
