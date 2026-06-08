"""_probe_road_subtype_discount.py — PROBE (evidence-first) สำหรับ requirement:
"คาดราคาแยกประเภทถนน คอนกรีต vs แอสฟัลต์ — % ลดต่างกันมาก" (กัญจน์ 2026-06-09).

พิสูจน์ 2 ข้อก่อน implement (ดู memory project_price_by_road_type + project_value_principle):
  1. จำแนก road_subtype จากชื่องานได้จริงไหม (coverage = classify ได้กี่ %)
  2. discount_pct ของ คอนกรีต vs แอสฟัลต์ ต่างกันจริงไหม (median/IQR/n)

อ่าน data/winner_history.db (617K, = cgd_winners บน VPS). READ-ONLY. ไม่แก้ data.
ผลเขียนลง data/probe_road_subtype_discount.json + print สรุป.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB = Path(__file__).parent.parent / "data" / "winner_history.db"
OUT = Path(__file__).parent.parent / "data" / "probe_road_subtype_discount.json"

# สอดคล้องกับ cgd_intel.py
COMPETITIVE_SET = (
    "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
    "ประกวดราคาด้วยวิธีการทางอิเล็กทรอนิกส์",
    "สอบราคา",
    "คัดเลือก",
)
RECENT_FY = ("2566", "2567", "2568")
TARGET_PROVINCES = ("นครพนม", "บึงกาฬ")

# --- subtype markers (hypothesis ตั้งต้น — จะ refine จากผล) ---
ASPHALT_KW = ("แอสฟัลท์", "แอสฟัลต์", "แอสฟัลติก", "ลาดยาง", "พาราแอสฟัลต์",
              "พาราแอสฟัลท์", "เคพซีล", "ผิวจราจรลาดยาง")
CONCRETE_KW = ("คอนกรีตเสริมเหล็ก", "คสล.", "ค.ส.ล.", "คสล", "ค.ส.ล", "คอนกรีต")
ROAD_KW = ("ถนน", "ผิวทาง", "ผิวจราจร", "สายทาง", "ทางหลวง")


def classify_subtype(name: str) -> str:
    n = name or ""
    a = any(k in n for k in ASPHALT_KW)
    c = any(k in n for k in CONCRETE_KW)
    if a and c:
        return "both"
    if a:
        return "asphalt"
    if c:
        return "concrete"
    return "unknown"


def is_road(name: str) -> bool:
    n = name or ""
    return any(k in n for k in ROAD_KW) or any(k in n for k in ASPHALT_KW + CONCRETE_KW)


def _pct(values, p):
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(v) - 1)
    if f == c:
        return v[f]
    return v[f] + (v[c] - v[f]) * (k - f)


def stats(discs):
    if not discs:
        return {"n": 0}
    return {
        "n": len(discs),
        "median": round(_pct(discs, 50), 2),
        "p25": round(_pct(discs, 25), 2),
        "p75": round(_pct(discs, 75), 2),
        "mean": round(sum(discs) / len(discs), 2),
        "min": round(min(discs), 2),
        "max": round(max(discs), 2),
    }


def run():
    if not DB.exists():
        print(f"ERR: ไม่พบ {DB}")
        return
    c = sqlite3.connect(DB)
    fy_ph = ",".join("?" for _ in RECENT_FY)
    pt_ph = ",".join("?" for _ in COMPETITIVE_SET)
    q = (f"SELECT project_name, discount_pct, province, win_price FROM winner_history "
         f"WHERE win_price>0 AND discount_pct IS NOT NULL "
         f"AND fiscal_year IN ({fy_ph}) AND proc_type IN ({pt_ph})")
    rows = c.execute(q, [*RECENT_FY, *COMPETITIVE_SET]).fetchall()
    c.close()

    # buckets: subtype → discs (เฉพาะงานถนน)
    by_sub = {"concrete": [], "asphalt": [], "both": [], "unknown": []}
    road_total = 0
    nonroad = 0
    target_sub = {p: {"concrete": [], "asphalt": []} for p in TARGET_PROVINCES}
    for name, disc, prov, _wp in rows:
        if not is_road(name):
            nonroad += 1
            continue
        road_total += 1
        st = classify_subtype(name)
        by_sub[st].append(disc)
        prov = prov or ""
        for tp in TARGET_PROVINCES:
            if tp in prov and st in ("concrete", "asphalt"):
                target_sub[tp][st].append(disc)

    result = {
        "competitive_recent_total": len(rows),
        "nonroad": nonroad,
        "road_total": road_total,
        "coverage": {
            "classified": road_total - len(by_sub["unknown"]),
            "unknown": len(by_sub["unknown"]),
            "unknown_pct": round(len(by_sub["unknown"]) / road_total * 100, 1) if road_total else None,
        },
        "discount_by_subtype": {k: stats(v) for k, v in by_sub.items()},
        "target_provinces": {
            p: {st: stats(d) for st, d in subs.items()} for p, subs in target_sub.items()
        },
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- สรุป human-readable ---
    print(f"=== PROBE road_subtype discount (competitive-set, FY {'/'.join(RECENT_FY)}) ===")
    print(f"งาน competitive ทั้งหมด: {len(rows):,} | งานถนน: {road_total:,} | ไม่ใช่ถนน: {nonroad:,}")
    cov = result["coverage"]
    print(f"จำแนกได้: {cov['classified']:,} | unknown: {cov['unknown']:,} ({cov['unknown_pct']}%)")
    print()
    print(f"{'subtype':12} {'n':>8} {'median':>8} {'p25':>7} {'p75':>7} {'mean':>7}")
    for st in ("concrete", "asphalt", "both", "unknown"):
        s = result["discount_by_subtype"][st]
        if s["n"]:
            print(f"{st:12} {s['n']:>8,} {s['median']:>8} {s['p25']:>7} {s['p75']:>7} {s['mean']:>7}")
        else:
            print(f"{st:12} {0:>8}")
    cc = result["discount_by_subtype"]["concrete"]
    aa = result["discount_by_subtype"]["asphalt"]
    if cc["n"] and aa["n"]:
        gap = round(aa["median"] - cc["median"], 2)
        print(f"\n>>> ส่วนต่าง median (แอสฟัลต์ − คอนกรีต) = {gap} จุด %")
        print(f">>> hypothesis '{('ต่างกันมาก' if abs(gap) >= 3 else 'ต่างกันน้อย')}' "
              f"(เกณฑ์หยาบ |gap|>=3 จุด)")
    print("\n=== target provinces (นครพนม/บึงกาฬ) ===")
    for p in TARGET_PROVINCES:
        for st in ("concrete", "asphalt"):
            s = result["target_provinces"][p][st]
            if s.get("n"):
                print(f"  {p} {st}: n={s['n']} median={s['median']}% (p25-75 {s['p25']}-{s['p75']})")
            else:
                print(f"  {p} {st}: n=0")
    print(f"\nบันทึก: {OUT}")


if __name__ == "__main__":
    run()
