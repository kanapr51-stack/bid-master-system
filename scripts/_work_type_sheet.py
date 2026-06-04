"""_work_type_sheet.py — Phase 1 analytics: เขียน Sheet 3 มุม จาก work_type (winner_history.db).
นับ involvement = primary+secondary (spec §7 constraint) — งานหนึ่งนับเข้าทุกหมวดใน all
(กัน undercount ราง/ท่อ = สินค้าหลัก BSC). apply เฉพาะงานก่อสร้าง (work_type IS NOT NULL).

3 tab:
  work_type_บริษัทเรา — เราชนะหมวดไหน (primary + involvement + มูลค่า + ส่วนลด)
  work_type_คู่แข่ง   — top winner ต่อหมวด (ใครครองหมวดไหน)
  work_type_ตำบล      — ตำบล × หมวด (พื้นที่ × ความต้องการ)
รัน: python scripts/_work_type_sheet.py
"""
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from work_type_classifier import classify_work_type  # noqa: E402
from sheets_client import get_client  # noqa: E402

DB = "data/winner_history.db"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
OUR = ("บ้านแพงทรัพย์คอนกรีต", "ยศประทานรุ่งเรืองทรัพย์")  # match by name (winner_tin พังจาก CGD Excel-fmt)
CORE = ["ถนน", "รางระบายน้ำ/ท่อ", "แหล่งน้ำ/ชลประทาน", "อาคาร", "สะพาน", "ไฟฟ้า/ส่องสว่าง", "ดิน/ปรับพื้นที่"]
HDR_FMT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
           "backgroundColor": {"red": 0.15, "green": 0.35, "blue": 0.25}, "horizontalAlignment": "CENTER"}
_GEOM = re.compile(r"^(POINT|LINESTRING|POLYGON|MULTI)")


def clean_tambon(s: str) -> str:
    s = (s or "").strip()
    return "" if (not s or _GEOM.match(s) or "(" in s) else s


def involvement(name: str):
    """หมวด core ที่งานนี้เกี่ยวข้อง (primary+secondary, ตัด OTHER/UNKNOWN). [] ถ้าไม่มี core."""
    a = classify_work_type(name or "")["all"]
    return [c for c in a if c in CORE]


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

    # มุม 1: บริษัทเรา × หมวด
    our_prim = Counter()
    our_invol = Counter()
    our_value = defaultdict(float)   # หมวด -> sum win_price (นับซ้ำตาม involvement)
    our_disc = defaultdict(list)
    # มุม 2: คู่แข่ง × หมวด -> winner -> [count, value]
    rivals = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    # มุม 3: (จังหวัด, อำเภอ, ตำบล) × หมวด — group 3 ชั้น กัน collision ชื่อตำบลซ้ำทั้งประเทศ
    tambon = defaultdict(Counter)

    for name, winner, wp, disc, prov, dist, sub in c.execute(
        "SELECT project_name, winner, win_price, discount_pct, province, district, subdistrict "
        "FROM winner_history WHERE work_type IS NOT NULL"
    ):
        cats = involvement(name)
        if not cats:
            continue
        wp = wp or 0
        is_ours = any(o in (winner or "") for o in OUR)
        if is_ours:
            our_prim[cats[0]] += 1
            for ci in cats:
                our_invol[ci] += 1
                our_value[ci] += wp
                if disc is not None:
                    our_disc[ci].append(disc)
        else:
            for ci in cats:
                rivals[ci][winner or "(ไม่ระบุ)"][0] += 1
                rivals[ci][winner or "(ไม่ระบุ)"][1] += wp
        p, d, t = clean_tambon(prov), clean_tambon(dist), clean_tambon(sub)
        if p and d and t:  # ต้องครบ 3 ชั้น (geometry/ว่าง → ข้าม)
            for ci in cats:
                tambon[(p, d, t)][ci] += 1
    c.close()

    # --- Tab 1: บริษัทเรา × หมวด ---
    h1 = ["หมวดงาน", "จำนวน (primary)", "จำนวน (รวม secondary)", "มูลค่ารวม (ลบ.)", "ส่วนลดเฉลี่ย %"]
    r1 = []
    for cat in sorted(our_invol, key=lambda k: -our_invol[k]):
        d = our_disc[cat]
        r1.append([cat, our_prim[cat], our_invol[cat],
                   round(our_value[cat] / 1e6, 2),
                   round(sum(d) / len(d), 1) if d else 0])

    # --- Tab 2: คู่แข่ง × หมวด (top 5 ต่อหมวด) ---
    h2 = ["หมวดงาน", "อันดับ", "ผู้ชนะ", "จำนวนงาน", "มูลค่ารวม (ลบ.)"]
    r2 = []
    for cat in CORE:
        top = sorted(rivals[cat].items(), key=lambda x: -x[1][0])[:5]
        for i, (w, (n, val)) in enumerate(top, 1):
            r2.append([cat if i == 1 else "", i, (w or "")[:50], n, round(val / 1e6, 2)])

    # --- Tab 3: (จังหวัด/อำเภอ/ตำบล) × หมวด (top 40 ตามจำนวนงานรวม) ---
    h3 = ["จังหวัด", "อำเภอ", "ตำบล"] + CORE + ["รวม"]
    top_t = sorted(tambon.items(), key=lambda x: -sum(x[1].values()))[:40]
    r3 = []
    for (p, d, t), cnt in top_t:
        row = [p, d, t] + [cnt.get(cat, 0) for cat in CORE] + [sum(cnt.values())]
        r3.append(row)

    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    write_tab(sh, "work_type_บริษัทเรา", h1, r1)
    write_tab(sh, "work_type_คู่แข่ง", h2, r2)
    write_tab(sh, "work_type_ตำบล", h3, r3)
    print(f"URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
