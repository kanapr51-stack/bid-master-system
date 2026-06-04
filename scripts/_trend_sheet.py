"""_trend_sheet.py — Phase 2 (backlog 3/3): Work-type trend over time.
เทรนด์งานแต่ละหมวดตามปีงบ (หมวดไหนโต/หด). ตลาด นครพนม+บึงกาฬ (winner_history.db).

complement market_size_ปีงบ (มูลค่า) ด้วยจำนวนงาน + สรุปเทรนด์.
**หน้าต่างเทียบ:** early 2561-2562 vs recent 2567-2568 (ปี data สมบูรณ์ทั้งคู่).
เลี่ยง 2566 (data บางผิดปกติ ~2.9K vs ปกติ 5-8K) + ปีเก่า 2558-2560 (งานน้อย/มี gap).

2 tab:
  trend_จำนวน_ปีงบ — ปีงบ × หมวด (จำนวนงาน)
  trend_สรุป       — หมวด: early vs recent (มูลค่า+จำนวน) + %เปลี่ยน + ทิศทาง
รัน: python scripts/_trend_sheet.py
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
ORDER = ["ถนน", "รางระบายน้ำ/ท่อ", "แหล่งน้ำ/ชลประทาน", "อาคาร", "สะพาน",
         "ไฟฟ้า/ส่องสว่าง", "ดิน/ปรับพื้นที่", "OTHER", "UNKNOWN"]
EARLY = ["2561", "2562"]
RECENT = ["2567", "2568"]
HDR_FMT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
           "backgroundColor": {"red": 0.15, "green": 0.35, "blue": 0.25}, "horizontalAlignment": "CENTER"}


def m(b):
    return round((b or 0) / 1e6, 2)


def pct_change(early, recent):
    if early <= 0:
        return None
    return round((recent - early) / early * 100, 1)


def arrow(p):
    if p is None:
        return "—"
    if p >= 15:
        return "📈 โต"
    if p <= -15:
        return "📉 หด"
    return "➡️ ทรง"


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


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yc_n = defaultdict(lambda: defaultdict(int))     # year -> cat -> count
    yc_v = defaultdict(lambda: defaultdict(float))   # year -> cat -> value
    for wt, fy, wp in c.execute(
        "SELECT work_type, fiscal_year, win_price FROM winner_history WHERE work_type IS NOT NULL"
    ):
        if not fy:
            continue
        yc_n[fy][wt] += 1
        yc_v[fy][wt] += wp or 0
    c.close()

    cats = [k for k in ORDER if any(k in yc_n[y] for y in yc_n)]

    # --- Tab A: ปีงบ × หมวด (จำนวน) ---
    hA = ["ปีงบ"] + cats + ["รวม"]
    rA = []
    for fy in sorted(yc_n, reverse=True):
        row = [fy] + [yc_n[fy].get(cat, 0) for cat in cats]
        row.append(sum(yc_n[fy].values()))
        rA.append(row)

    # --- Tab B: สรุปเทรนด์ (early vs recent) ---
    hB = ["หมวดงาน", "มูลค่า/ปี 2561-62 (ลบ.)", "มูลค่า/ปี 2567-68 (ลบ.)", "%เปลี่ยน มูลค่า",
          "งาน/ปี 2561-62", "งาน/ปี 2567-68", "%เปลี่ยน จำนวน", "ทิศทาง (มูลค่า)"]
    rB = []

    def avg_v(cat, years):
        return sum(yc_v[y].get(cat, 0) for y in years) / len(years)

    def avg_n(cat, years):
        return sum(yc_n[y].get(cat, 0) for y in years) / len(years)

    for cat in cats:
        ev, rv = avg_v(cat, EARLY), avg_v(cat, RECENT)
        en, rn = avg_n(cat, EARLY), avg_n(cat, RECENT)
        pv = pct_change(ev, rv)
        pn = pct_change(en, rn)
        rB.append([cat, m(ev), m(rv), f"{pv}%" if pv is not None else "—",
                   round(en, 1), round(rn, 1), f"{pn}%" if pn is not None else "—", arrow(pv)])

    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    write_tab(sh, "trend_จำนวน_ปีงบ", hA, rA)
    write_tab(sh, "trend_สรุป", hB, rB)
    print(f"URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
