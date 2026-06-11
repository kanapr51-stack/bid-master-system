"""_research_subtype_variance.py — สแกนทุกหมวดงาน: หมวดย่อยไหน %ส่วนลดต่างกันมากพอจะคุ้มแยก reference pool.

กฎ (กัญจน์ 2026-06-11): แยก subtype เฉพาะหมวดที่ "หมวดย่อยต่างกันเยอะ" (เหมือนถนนคอนกรีต/แอสฟัลต์)
ไม่แยกหมวดที่หมวดย่อยต่างกันน้อย (เหมือนชนิดอาคาร).

เกณฑ์ตัดสิน (ตายตัว, reproducible):
  - subtype ที่นับ = n >= MIN_N (พอจะเป็น reference pool)
  - SPLIT ถ้า gap(median สูงสุด − ต่ำสุด ในกลุ่มที่ n>=MIN_N) >= GAP_PT
  - ฟิลเตอร์งานแข่งจริง + price_valid + ตัด outlier

output: data/subtype_variance_report.json + ตารางบนจอ. ไม่แตะ DB/production.
"""
import sqlite3, statistics as st, json, sys
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "winner_history.db"
MIN_N = 80
GAP_PT = 10.0
CONTEST = ("(proc_type LIKE '%ประกวดราคา%' OR proc_type LIKE '%e-bidding%' "
           "OR proc_type='สอบราคา' OR proc_type='คัดเลือก')")

# keyword map ต่อหมวด: subtype -> tuple(keywords). 'อื่นๆ' = residual (ไม่ match ตัวไหน).
SUBTYPES = {
    "ถนน": {
        "asphalt": ("แอสฟัลท์", "แอสฟัลต์", "แอสฟัลติก", "ลาดยาง", "พาราแอสฟัลต์"),
        "concrete": ("คอนกรีตเสริมเหล็ก", "คสล", "ค.ส.ล", "คอนกรีต"),
        "หินคลุก/ลูกรัง": ("หินคลุก", "ลูกรัง"),
    },
    "แหล่งน้ำ/ชลประทาน": {
        "ขุดลอก/ขุดสระ": ("ขุดลอก", "ขุดสระ", "ขุดคลอง", "ขุดร่อง"),
        "ฝาย": ("ฝาย",),
        "ประปา": ("ประปา",),
        "อ่างเก็บน้ำ": ("อ่างเก็บน้ำ",),
        "ดาด/คลองส่งน้ำ": ("ดาดคอนกรีต", "คลองส่งน้ำ", "ดาด"),
        "บ่อบาดาล": ("บาดาล", "บ่อบาดาล"),
    },
    "อาคาร": {
        "สำนักงาน": ("สำนักงาน", "ที่ทำการ"),
        "อาคารเรียน": ("อาคารเรียน", "ห้องเรียน"),
        "รพ./อนามัย": ("โรงพยาบาล", "รพ.สต", "อนามัย", "สาธารณสุข"),
        "ศาลา/เอนกประสงค์": ("ศาลา", "อเนกประสงค์", "เอนกประสงค์"),
        "บ้านพัก": ("บ้านพัก", "ที่พัก", "แฟลต", "หอพัก"),
        "โรงจอด/เก็บ": ("โรงจอด", "โรงเก็บ", "คลังพัสดุ", "โกดัง"),
        "ห้องน้ำ/สุขา": ("ห้องน้ำ", "สุขา"),
        "ตลาด": ("ตลาด",),
    },
    "รางระบายน้ำ/ท่อ": {
        "ท่อระบาย": ("ท่อ",),
        "ราง/รางระบาย": ("รางระบาย", "ราง"),
        "บ่อพัก": ("บ่อพัก",),
    },
    "ดิน/ปรับพื้นที่": {
        "ถมดิน": ("ถมดิน", "ดินถม", "ถมที่"),
        "ปรับพื้นที่": ("ปรับพื้น", "ปรับเกลี่ย", "เกรด"),
        "ขุดดิน": ("ขุดดิน",),
    },
    "สะพาน": {
        "สะพาน คสล.": ("คสล", "คอนกรีต"),
        "ท่อเหลี่ยม/บ็อกซ์": ("เหลี่ยม", "box", "บ็อกซ์"),
    },
    "ไฟฟ้า/ส่องสว่าง": {
        "ส่องสว่าง/ไฟกิ่ง": ("ส่องสว่าง", "ไฟฟ้า", "ไฟกิ่ง", "โคมไฟ"),
        "โซลาร์": ("โซลาร์", "solar", "พลังงานแสง"),
    },
}


def stat(vals):
    v = sorted(x for x in vals if x is not None and -5 < x < 80)
    n = len(v)
    if n == 0:
        return None
    return {"n": n, "median": round(st.median(v), 1),
            "p25": round(v[n // 4], 1), "p75": round(v[3 * n // 4], 1)}


def classify(name, kwmap):
    nm = name or ""
    for sub, kws in kwmap.items():
        if any(w in nm for w in kws):
            return sub
    return "อื่นๆ"


def main():
    conn = sqlite3.connect(DB)
    report = {"min_n": MIN_N, "gap_pt": GAP_PT, "categories": {}}
    for wt, kwmap in SUBTYPES.items():
        rows = conn.execute(
            f"SELECT project_name, discount_pct FROM winner_history "
            f"WHERE price_valid=1 AND discount_pct IS NOT NULL AND work_type=? AND {CONTEST}",
            (wt,)).fetchall()
        buckets = defaultdict(list)
        allv = []
        for name, disc in rows:
            allv.append(disc)
            buckets[classify(name, kwmap)].append(disc)
        subs = {k: stat(v) for k, v in buckets.items()}
        subs = {k: s for k, s in subs.items() if s}
        # เกณฑ์: เฉพาะ subtype ที่ n>=MIN_N (และไม่ใช่ residual 'อื่นๆ')
        eligible = {k: s for k, s in subs.items() if s["n"] >= MIN_N and k != "อื่นๆ"}
        meds = [s["median"] for s in eligible.values()]
        gap = round(max(meds) - min(meds), 1) if len(meds) >= 2 else 0.0
        verdict = "SPLIT" if gap >= GAP_PT else "POOL"
        report["categories"][wt] = {
            "total": stat(allv), "subtypes": subs,
            "eligible_count": len(eligible), "gap": gap, "verdict": verdict,
        }
    out = DB.parent / "subtype_variance_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ตารางบนจอ
    for wt, r in sorted(report["categories"].items(), key=lambda x: -x[1]["gap"]):
        flag = "🔴 SPLIT" if r["verdict"] == "SPLIT" else "⚪ POOL "
        t = r["total"]
        print(f"\n{flag} | {wt}  (gap={r['gap']} จุด · รวม n={t['n']} med={t['median']}%)")
        for k, s in sorted(r["subtypes"].items(), key=lambda x: -x[1]["median"]):
            mark = "✓" if (s["n"] >= MIN_N and k != "อื่นๆ") else " "
            print(f"   {mark} {k:18s} n={s['n']:5d}  med={s['median']:5.1f}%  p25-75={s['p25']:4.1f}-{s['p75']:4.1f}")
    print(f"\n→ saved {out}")
    print("เกณฑ์: subtype n>=%d, SPLIT เมื่อ gap>=%.0f จุด" % (MIN_N, GAP_PT))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
