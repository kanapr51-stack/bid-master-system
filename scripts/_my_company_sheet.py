"""สร้าง Sheet tab "ผลงานบริษัทเรา" — รายการ 316 งานที่ บ้านแพงทรัพย์คอนกรีต + ยศประทานรุ่งเรืองทรัพย์
ชนะ ย้อนหลัง 11 ปี (winner_history.db). clean ตำบลที่ปน geometry (POINT/LINESTRING จาก CGD shift)."""
import sys, sqlite3, re
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from sheets_client import get_client

DB = "data/winner_history.db"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
TAB = "ผลงานบริษัทเรา"
WHERE = "(winner LIKE '%บ้านแพงทรัพย์คอนกรีต%' OR winner LIKE '%ยศประทานรุ่งเรืองทรัพย์%')"
HDR_FMT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
           "backgroundColor": {"red": 0.15, "green": 0.35, "blue": 0.25}, "horizontalAlignment": "CENTER"}

_GEOM = re.compile(r"^(POINT|LINESTRING|POLYGON|MULTI)")


def clean_tambon(s: str) -> str:
    s = (s or "").strip()
    if not s or _GEOM.match(s) or "(" in s:
        return ""  # geometry ปน → เว้นว่าง (ดู column-shift CGD)
    return s


def co_name(winner: str) -> str:
    return "บ้านแพงทรัพย์คอนกรีต" if "บ้านแพง" in winner else "ยศประทานรุ่งเรืองทรัพย์"


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = []
    for r in c.execute(f"""
        SELECT fiscal_year, winner, district, subdistrict, project_name, dept,
               mid_price, win_price, discount_pct, announce_date
        FROM winner_history WHERE {WHERE}
        ORDER BY fiscal_year DESC, win_price DESC"""):
        fy, winner, dist, sub, pn, dept, mid, win, disc, adate = r
        rows.append([
            fy, co_name(winner or ""), dist or "", clean_tambon(sub),
            (pn or "")[:120], (dept or "")[:60],
            int(mid or 0), int(win or 0),
            round(disc or 0, 1), (adate or "")[:10],
        ])

    header = ["ปีงบ", "บริษัท", "อำเภอ", "ตำบล", "ชื่องาน", "หน่วยงานที่จ้าง",
              "ราคากลาง", "ราคาที่ชนะ", "ส่วนลด %", "วันประกาศ"]

    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(TAB)
        ws.clear()
    except Exception:
        ws = sh.add_worksheet(title=TAB, rows=len(rows) + 10, cols=len(header))
    data = [header] + rows
    ws.resize(rows=len(data) + 2, cols=len(header))
    ws.update(values=data, range_name="A1")
    end_col = chr(ord("A") + len(header) - 1)
    ws.format(f"A1:{end_col}1", HDR_FMT)
    ws.freeze(rows=1)

    n_clean = sum(1 for x in rows if x[3])
    print(f"✅ tab '{TAB}': {len(rows)} งาน (ตำบลสะอาด {n_clean}/{len(rows)})")
    print(f"URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
