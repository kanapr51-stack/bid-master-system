"""วิเคราะห์ผลงานบริษัทกัญจน์ (บ้านแพงทรัพย์คอนกรีต + ยศประทานรุ่งเรืองทรัพย์) จาก winner_history 11 ปี."""
import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
c = sqlite3.connect("file:data/winner_history.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

WHERE = "(winner LIKE '%บ้านแพงทรัพย์คอนกรีต%' OR winner LIKE '%ยศประทานรุ่งเรืองทรัพย์%')"


def q(sql):
    return list(c.execute(sql))


def baht(n):
    return f"{n:,.0f}"


# ── ภาพรวม ──
r = q(f"SELECT COUNT(*) n, SUM(price_valid) pv, SUM(CASE WHEN price_valid THEN win_price END) val, "
      f"MIN(fiscal_year) y0, MAX(fiscal_year) y1 FROM winner_history WHERE {WHERE}")[0]
print("=" * 60)
print("ภาพรวม 11 ปี (2558-2568)")
print("=" * 60)
print(f"งานที่ชนะรวม: {r['n']:,} งาน | ราคาใช้ได้ {r['pv']:,} | มูลค่ารวม {baht(r['val'] or 0)} บาท")

# ── แยกบริษัท ──
print("\n--- แยกบริษัท ---")
for row in q(f"""SELECT CASE WHEN winner LIKE '%บ้านแพง%' THEN 'บ้านแพงทรัพย์คอนกรีต' ELSE 'ยศประทานรุ่งเรืองทรัพย์' END co,
       COUNT(*) n, SUM(CASE WHEN price_valid THEN win_price END) val
       FROM winner_history WHERE {WHERE} GROUP BY co ORDER BY n DESC"""):
    print(f"  {row['co']:28} {row['n']:>4} งาน | {baht(row['val'] or 0):>15} บาท")

# ── แยกปี ──
print("\n--- แนวโน้มรายปี ---")
for row in q(f"""SELECT fiscal_year fy, COUNT(*) n, SUM(CASE WHEN price_valid THEN win_price END) val,
       AVG(CASE WHEN price_valid THEN discount_pct END) d
       FROM winner_history WHERE {WHERE} GROUP BY fy ORDER BY fy"""):
    print(f"  {row['fy']}: {row['n']:>3} งาน | {baht(row['val'] or 0):>14} บาท | ส่วนลดเฉลี่ย {row['d'] or 0:.1f}%")

# ── พื้นที่ที่เก่ง (อำเภอ) ──
print("\n" + "=" * 60)
print("พื้นที่ที่เก่ง — แยกอำเภอ (เรียงตามจำนวนงาน)")
print("=" * 60)
for row in q(f"""SELECT district d, COUNT(*) n, SUM(CASE WHEN price_valid THEN win_price END) val,
       AVG(CASE WHEN price_valid THEN discount_pct END) disc
       FROM winner_history WHERE {WHERE} AND district != '' GROUP BY d ORDER BY n DESC LIMIT 15"""):
    print(f"  {row['d'] or '(ไม่ระบุ)':18} {row['n']:>4} งาน | {baht(row['val'] or 0):>14} | ส่วนลด {row['disc'] or 0:.1f}%")

# ── พื้นที่ที่เก่ง (ตำบล) + ส่วนลดต่อพื้นที่ ──
print("\n" + "=" * 60)
print("ราคาต่ำกว่าราคากลาง — แยกตำบล (top 20 ตามจำนวนงาน)")
print("=" * 60)
print(f"  {'ตำบล':16} {'อำเภอ':14} {'งาน':>4} {'ส่วนลดเฉลี่ย':>11} {'มูลค่ารวม':>14}")
for row in q(f"""SELECT subdistrict sub, district d, COUNT(*) n,
       AVG(CASE WHEN price_valid THEN discount_pct END) disc,
       SUM(CASE WHEN price_valid THEN win_price END) val
       FROM winner_history WHERE {WHERE} AND subdistrict != '' GROUP BY sub, d
       ORDER BY n DESC LIMIT 20"""):
    print(f"  {(row['sub'] or '')[:16]:16} {(row['d'] or '')[:14]:14} {row['n']:>4} {row['disc'] or 0:>9.1f}% {baht(row['val'] or 0):>14}")

# ── ส่วนลด: ภาพรวม + ช่วง ──
print("\n" + "=" * 60)
print("สถิติส่วนลด (เทียบราคากลาง)")
print("=" * 60)
dr = q(f"""SELECT AVG(discount_pct) avg, MIN(discount_pct) mn, MAX(discount_pct) mx,
       SUM(CASE WHEN discount_pct > 0 THEN 1 ELSE 0 END) below, COUNT(*) tot
       FROM winner_history WHERE {WHERE} AND price_valid=1""")[0]
print(f"  ส่วนลดเฉลี่ย: {dr['avg'] or 0:.1f}% | ต่ำสุด {dr['mn'] or 0:.1f}% | สูงสุด {dr['mx'] or 0:.1f}%")
print(f"  ชนะแบบราคาต่ำกว่าราคากลาง: {dr['below']}/{dr['tot']} งาน ({(dr['below'] or 0)/max(dr['tot'],1)*100:.0f}%)")

# ── หน่วยงานที่ชนะบ่อย ──
print("\n--- หน่วยงานที่จ้างบ่อย (top 10) ---")
for row in q(f"""SELECT dept, COUNT(*) n FROM winner_history WHERE {WHERE} AND dept != ''
       GROUP BY dept ORDER BY n DESC LIMIT 10"""):
    print(f"  {row['n']:>3} งาน | {row['dept'][:50]}")

# ── งานใหญ่สุด ──
print("\n--- งานมูลค่าสูงสุด 5 อันดับ ---")
for row in q(f"""SELECT project_name pn, win_price w, mid_price m, discount_pct d, fiscal_year fy, district dist
       FROM winner_history WHERE {WHERE} AND price_valid=1 ORDER BY win_price DESC LIMIT 5"""):
    print(f"  {baht(row['w']):>14} ({row['d']:.0f}% | ปี{row['fy']} | {row['dist']}) {row['pn'][:45]}")
