"""_market_size_sheet.py — Phase 2 analytics (backlog 1/3): Market size by work type.
ตลาดงานก่อสร้าง นครพนม+บึงกาฬ 11 ปี (winner_history.db, work_type column).

นับ **primary** (work_type column) — market TOTAL ต้องไม่ double-count → sum ตรงตลาดจริง.
(ต่างจาก tab บริษัทเรา/คู่แข่งที่ใช้ involvement กัน undercount). value = win_price (ราคาชนะจริง).

3 tab:
  market_size_หมวด    — ภาพรวม: หมวด × [จำนวน, มูลค่า, เฉลี่ย/งาน, %share]
  market_size_จังหวัด — จังหวัด × หมวด (มูลค่า ลบ.)
  market_size_ปีงบ    — ปีงบ × หมวด (มูลค่า ลบ.) → seed trend (backlog 3)
รัน: python scripts/_market_size_sheet.py
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from sheets_client import get_client  # noqa: E402

DB = "data/winner_history.db"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
# เรียงหมวดตามลำดับธุรกิจ (core ก่อน, OTHER/UNKNOWN ท้าย)
ORDER = ["ถนน", "รางระบายน้ำ/ท่อ", "แหล่งน้ำ/ชลประทาน", "อาคาร", "สะพาน",
         "ไฟฟ้า/ส่องสว่าง", "ดิน/ปรับพื้นที่", "OTHER", "UNKNOWN"]
HDR_FMT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
           "backgroundColor": {"red": 0.15, "green": 0.35, "blue": 0.25}, "horizontalAlignment": "CENTER"}


def m(baht):  # บาท → ล้านบาท (2 ตำแหน่ง)
    return round((baht or 0) / 1e6, 2)


def write_tab(sh, title, header, rows):
    try:
        ws = sh.worksheet(title)
        ws.clear()
    except Exception:
        ws = sh.add_worksheet(title=title, rows=len(rows) + 10, cols=len(header))
    data = [header] + rows
    ws.resize(rows=len(data) + 2, cols=len(header))
    ws.update(values=data, range_name="A1")
    end_col = chr(ord("A") + len(header) - 1)
    ws.format(f"A1:{end_col}1", HDR_FMT)
    ws.freeze(rows=1)
    print(f"✅ tab '{title}': {len(rows)} rows")


def ordered(keys):
    """เรียง key ตาม ORDER (ตัวที่ไม่อยู่ใน ORDER ต่อท้าย)."""
    return [k for k in ORDER if k in keys] + [k for k in keys if k not in ORDER]


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = c.execute(
        "SELECT work_type, province, fiscal_year, win_price "
        "FROM winner_history WHERE work_type IS NOT NULL"
    ).fetchall()
    c.close()

    cat_n = defaultdict(int)
    cat_v = defaultdict(float)
    prov_cat = defaultdict(lambda: defaultdict(float))   # province -> cat -> value
    year_cat = defaultdict(lambda: defaultdict(float))   # year -> cat -> value
    for wt, prov, fy, wp in rows:
        wp = wp or 0
        cat_n[wt] += 1
        cat_v[wt] += wp
        if prov:
            prov_cat[prov][wt] += wp
        if fy:
            year_cat[fy][wt] += wp

    total_v = sum(cat_v.values())
    total_n = sum(cat_n.values())

    # --- Tab A: ภาพรวมหมวด ---
    hA = ["หมวดงาน", "จำนวนงาน", "มูลค่ารวม (ลบ.)", "เฉลี่ย/งาน (ลบ.)", "%มูลค่า", "%จำนวน"]
    rA = []
    for cat in ordered(cat_v):
        n, v = cat_n[cat], cat_v[cat]
        rA.append([cat, n, m(v), round(v / n / 1e6, 2) if n else 0,
                   round(v / total_v * 100, 1), round(n / total_n * 100, 1)])
    rA.append(["รวมทั้งตลาด", total_n, m(total_v), round(total_v / total_n / 1e6, 2), 100.0, 100.0])

    # --- Tab B: จังหวัด × หมวด (มูลค่า) ---
    cats_core = ordered(cat_v)
    hB = ["จังหวัด"] + cats_core + ["รวม (ลบ.)"]
    rB = []
    for prov in sorted(prov_cat, key=lambda p: -sum(prov_cat[p].values())):
        row = [prov] + [m(prov_cat[prov].get(cat, 0)) for cat in cats_core]
        row.append(m(sum(prov_cat[prov].values())))
        rB.append(row)

    # --- Tab C: ปีงบ × หมวด (มูลค่า) → seed trend ---
    hC = ["ปีงบ"] + cats_core + ["รวม (ลบ.)"]
    rC = []
    for fy in sorted(year_cat, reverse=True):
        row = [fy] + [m(year_cat[fy].get(cat, 0)) for cat in cats_core]
        row.append(m(sum(year_cat[fy].values())))
        rC.append(row)

    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    write_tab(sh, "market_size_หมวด", hA, rA)
    write_tab(sh, "market_size_จังหวัด", hB, rB)
    write_tab(sh, "market_size_ปีงบ", hC, rC)
    print(f"\nตลาดรวม: {m(total_v):,.0f} ลบ. / {total_n:,} งาน (11 ปี, นครพนม+บึงกาฬ)")
    print(f"URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
