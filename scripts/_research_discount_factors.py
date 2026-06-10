"""_research_discount_factors.py — วิจัยปัจจัยที่ขับเคลื่อน %ส่วนลด งานก่อสร้างถนนภาครัฐ
(นครพนม+บึงกาฬ). อ่าน cgd_winners (+ bid_results). พิมพ์รายงานเป็น section. one-off research."""
import sqlite3, statistics as st, sys, json
DB = sys.argv[1] if len(sys.argv) > 1 else "/opt/bms/data/bms_customers.db"
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
COMP = ("ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)", "ประกวดราคาด้วยวิธีการทางอิเล็กทรอนิกส์",
        "สอบราคา", "คัดเลือก")
ptph = ",".join("?" * len(COMP))
# base = งานก่อสร้างถนน "คอนกรีต" ใหม่ competitive 3 ปี (กรอง ซื้อ ออก)
CONC = "(project_name LIKE '%คอนกรีต%' OR project_name LIKE '%คสล%') AND NOT (project_name LIKE '%แอสฟั%' OR project_name LIKE '%ลาดยาง%')"
BASE = (f"province IN ('นครพนม','บึงกาฬ') AND proc_type IN ({ptph}) AND project_name NOT LIKE '%ซื้อ%' "
        f"AND project_name LIKE '%ก่อสร้าง%' AND {CONC} "
        f"AND fiscal_year IN ('2566','2567','2568') AND win_price>0 AND discount_pct IS NOT NULL AND budget>0")


def stats(ds):
    ds = sorted(ds); n = len(ds)
    if n == 0:
        return None
    return dict(n=n, p10=ds[n // 10], p25=ds[n // 4], med=st.median(ds),
                p75=ds[3 * n // 4], p90=ds[min(n - 1, 9 * n // 10)], mean=round(st.mean(ds), 1))


def line(lbl, s):
    if not s:
        return f"  {lbl:24} n=0"
    return (f"  {lbl:24} n={s['n']:4d} | p10={s['p10']:2.0f} p25={s['p25']:2.0f} "
            f"med={s['med']:2.0f} p75={s['p75']:2.0f} p90={s['p90']:2.0f} | span(p25-75)={s['p75']-s['p25']:2.0f}")


def fetch(extra="", params=()):
    return c.execute(f"SELECT budget, discount_pct, win_price, winner, dept, district, fiscal_year, project_name "
                     f"FROM cgd_winners WHERE {BASE} {extra}", (*COMP, *params)).fetchall()


ALL = fetch()
print(f"=== UNIVERSE: งานก่อสร้างถนนคอนกรีตใหม่ competitive (นครพนม+บึงกาฬ 3ปี) = {len(ALL)} งาน ===")
print(line("ทั้งหมด", stats([r['discount_pct'] for r in ALL])))

print("\n=== A. ตามขนาดงบ (เครดิต/คุณสมบัติ hypothesis) ===")
brackets = [(0, .5e6, "<0.5 ลบ."), (.5e6, 1e6, "0.5-1 ลบ."), (1e6, 1.5e6, "1-1.5 ลบ."),
            (1.5e6, 2e6, "1.5-2 ลบ."), (2e6, 3e6, "2-3 ลบ."), (3e6, 5e6, "3-5 ลบ."),
            (5e6, 10e6, "5-10 ลบ."), (10e6, 1e12, ">10 ลบ.")]
for lo, hi, lbl in brackets:
    print(line(lbl, stats([r['discount_pct'] for r in ALL if lo <= r['budget'] < hi])))

print("\n=== B. จำนวนคู่แข่ง (จาก bid_results ที่เคย poll) ===")
try:
    bidcount = c.execute("""SELECT b.project_id, COUNT(DISTINCT b.bidder_tin) nb,
        MAX(CASE WHEN b.is_winner=1 THEN b.price_agree END) wp, ps.budget
        FROM bid_results b JOIN projects_seen ps ON ps.project_id=b.project_id
        WHERE ps.budget>0 GROUP BY b.project_id""").fetchall()
    by_n = {}
    for r in bidcount:
        try:
            wp = float(r['wp'] or 0); bud = float(r['budget'])
            if wp <= 0 or bud <= 0:
                continue
            disc = (1 - wp / bud) * 100
            by_n.setdefault(min(r['nb'], 6), []).append(disc)
        except (TypeError, ValueError):
            continue
    print(f"  (มี bid_results {len(bidcount)} งานที่ poll ได้)")
    for nb in sorted(by_n):
        lbl = f"{nb} ราย" + ("+" if nb == 6 else "")
        print(line(lbl, stats(by_n[nb])))
except Exception as e:
    print("  bid_results analysis error:", e)

print("\n=== C. ภูมิศาสตร์ (จังหวัด) ===")
for prov in ("นครพนม", "บึงกาฬ"):
    print(line(prov, stats([r['discount_pct'] for r in ALL if True]) if False else
              stats([r['discount_pct'] for r in fetch("AND province=?", (prov,))])))
print("  -- อำเภอเมือง vs อำเภออื่น (เมือง = คู่แข่งเยอะกว่า?) --")
city = [r['discount_pct'] for r in ALL if r['district'] and ('เมือง' in r['district'] or r['district'] == 'ในเมือง')]
rural = [r['discount_pct'] for r in ALL if r['district'] and 'เมือง' not in r['district'] and r['district'] != 'ในเมือง']
print(line("อ.เมือง", stats(city)))
print(line("อ.อื่น (ชนบท)", stats(rural)))

print("\n=== D. ตามปีงบ (เทรนด์เวลา) ===")
for fy in ("2566", "2567", "2568"):
    print(line(f"fy{fy}", stats([r['discount_pct'] for r in ALL if r['fiscal_year'] == fy])))

print("\n=== E. ประเภทหน่วยงาน (dept) ===")
def dept_class(d):
    d = d or ""
    if "ทางหลวงชนบท" in d or "ทางหลวง" in d:
        return "ทางหลวงชนบท"
    if "ชลประทาน" in d:
        return "ชลประทาน"
    if "เทศบาล" in d:
        return "เทศบาล"
    if "องค์การบริหารส่วนจังหวัด" in d or "อบจ" in d:
        return "อบจ"
    if "องค์การบริหารส่วนตำบล" in d or "อบต" in d:
        return "อบต"
    return "อื่นๆ"
by_dept = {}
for r in ALL:
    by_dept.setdefault(dept_class(r['dept']), []).append(r['discount_pct'])
for k in sorted(by_dept, key=lambda x: -len(by_dept[x])):
    print(line(k, stats(by_dept[k])))

print("\n=== F. Market concentration (ผู้ชนะกระจุก?) ===")
from collections import Counter
wc = Counter(r['winner'] for r in ALL if r['winner'])
top = wc.most_common(10)
print(f"  ผู้ชนะ distinct = {len(wc)} ราย จาก {len(ALL)} งาน")
print(f"  top10 ครอง {sum(n for _,n in top)}/{len(ALL)} = {100*sum(n for _,n in top)//len(ALL)}%")
for w, n in top[:8]:
    ds = [r['discount_pct'] for r in ALL if r['winner'] == w]
    print(f"    {(w or '')[:34]:34} {n:3d} งาน · ลด med {st.median(ds):.0f}%")

print("\n=== G. ก่อสร้างใหม่ vs ปรับปรุง/ซ่อม/ปูทับ ===")
maint = lambda n: any(k in (n or "") for k in ("ปรับปรุง", "ปูทับ", "ซ่อมแซม", "เสริมผิว"))
print(line("ก่อสร้างใหม่", stats([r['discount_pct'] for r in ALL if not maint(r['project_name'])])))
print(line("ปรับปรุง/ซ่อม", stats([r['discount_pct'] for r in ALL if maint(r['project_name'])])))

print("\n=== H. bimodality check (กลุ่มต่ำ <15% vs สูง >=15%) ต่อ bracket งบเล็ก ===")
for lo, hi, lbl in [(0, 1e6, "<1 ลบ."), (1e6, 2e6, "1-2 ลบ."), (2e6, 5e6, "2-5 ลบ.")]:
    seg = [r['discount_pct'] for r in ALL if lo <= r['budget'] < hi]
    low = [d for d in seg if d < 15]; high = [d for d in seg if d >= 15]
    print(f"  {lbl:10} ต่ำ<15%: {len(low):3d} งาน (med {st.median(low) if low else 0:.0f}) | "
          f"สูง>=15%: {len(high):3d} งาน (med {st.median(high) if high else 0:.0f}) | "
          f"%สูง={100*len(high)//max(len(seg),1)}%")
