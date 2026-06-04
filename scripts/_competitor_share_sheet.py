"""_competitor_share_sheet.py — Phase 2 (backlog 2/3): Competitor market share by work type.
ส่วนแบ่งตลาด % ต่อหมวด (เราอยู่อันดับไหน). ตลาด นครพนม+บึงกาฬ 11 ปี (winner_history.db).

primary-based + win_price → denominator = market size ต่อหมวด (share รวม 100%/หมวด,
สอดคล้อง market_size_หมวด). คู่แข่ง = winner name. เรา = OUR (2 ชื่อ).

2 tab:
  share_หมวด     — top 10 ผู้ชนะต่อหมวด + %share (★ = เรา)
  เรา_share_หมวด — สรุป: เราในแต่ละหมวด (จำนวน/มูลค่า/share/อันดับ/เจ้าตลาด)
รัน: python scripts/_competitor_share_sheet.py
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
OUR = ("บ้านแพงทรัพย์คอนกรีต", "ยศประทานรุ่งเรืองทรัพย์")
CORE = ["ถนน", "รางระบายน้ำ/ท่อ", "แหล่งน้ำ/ชลประทาน", "อาคาร", "สะพาน", "ไฟฟ้า/ส่องสว่าง", "ดิน/ปรับพื้นที่"]
TOPN = 10
HDR_FMT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
           "backgroundColor": {"red": 0.15, "green": 0.35, "blue": 0.25}, "horizontalAlignment": "CENTER"}


def m(b):
    return round((b or 0) / 1e6, 2)


def is_ours(w):
    return any(o in (w or "") for o in OUR)


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
    # cat -> winner -> [n, value]
    cat_win = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for wt, winner, wp in c.execute(
        "SELECT work_type, winner, win_price FROM winner_history WHERE work_type IS NOT NULL"
    ):
        if wt not in CORE:
            continue
        d = cat_win[wt][winner or "(ไม่ระบุ)"]
        d[0] += 1
        d[1] += wp or 0
    c.close()

    # --- Tab A: top 10 ต่อหมวด + share ---
    hA = ["หมวดงาน", "อันดับ", "ผู้ชนะ", "จำนวนงาน", "มูลค่า (ลบ.)", "%share"]
    rA = []
    # --- Tab B: สรุปอันดับเรา ---
    hB = ["หมวดงาน", "จำนวนงานเรา", "มูลค่าเรา (ลบ.)", "%share เรา", "อันดับเรา", "ผู้เล่นทั้งหมด", "เจ้าตลาด (อันดับ 1)"]
    rB = []

    for cat in CORE:
        wins = cat_win[cat]
        cat_total = sum(v[1] for v in wins.values())
        # รวม 2 ชื่อเราเป็น entity เดียวสำหรับจัดอันดับ
        merged = defaultdict(lambda: [0, 0.0])
        for w, (n, val) in wins.items():
            key = "★ บริษัทเรา (BSC+ยศประทาน)" if is_ours(w) else w
            merged[key][0] += n
            merged[key][1] += val
        ranked = sorted(merged.items(), key=lambda x: -x[1][1])

        for i, (w, (n, val)) in enumerate(ranked[:TOPN], 1):
            share = val / cat_total * 100 if cat_total else 0
            rA.append([cat if i == 1 else "", i, w[:50], n, m(val), round(share, 1)])

        # หาอันดับเรา
        our_rank = next((i for i, (w, _) in enumerate(ranked, 1) if w.startswith("★")), None)
        our = merged.get("★ บริษัทเรา (BSC+ยศประทาน)", [0, 0.0])
        leader = ranked[0]
        leader_name = "เรา" if leader[0].startswith("★") else leader[0][:40]
        rB.append([
            cat, our[0], m(our[1]),
            round(our[1] / cat_total * 100, 2) if cat_total else 0,
            our_rank if our_rank else "—",
            len(merged),
            f"{leader_name} ({round(leader[1][1]/cat_total*100,1)}%)",
        ])

    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    write_tab(sh, "share_หมวด", hA, rA)
    write_tab(sh, "เรา_share_หมวด", hB, rB)
    print(f"URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
