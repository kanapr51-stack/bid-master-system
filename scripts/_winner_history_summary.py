"""Phase 3: สร้าง Sheet สรุปจาก data/winner_history.db (ข้อมูลดิบอยู่ SQLite).
3 tab: ภาพรวม (ปี×จังหวัด), คู่แข่งรายใหญ่ (top winners), ตามตำบล (target insight).
ใช้เฉพาะ price_valid=1 + winner != '' สำหรับ aggregate เงิน."""
import sys, sqlite3
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from sheets_client import get_client

DB = "data/winner_history.db"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
HDR_FMT = {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
           "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5}, "horizontalAlignment": "CENTER"}


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
    print(f"  ✅ {title}: {len(rows)} rows")
    return ws


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)

    # 1) ภาพรวม ปี×จังหวัด
    print("สร้าง tab ภาพรวม...")
    rows = []
    for r in c.execute("""
        SELECT fiscal_year, province, COUNT(*),
               SUM(CASE WHEN price_valid=1 THEN win_price ELSE 0 END),
               AVG(CASE WHEN price_valid=1 THEN discount_pct END)
        FROM winner_history GROUP BY fiscal_year, province
        ORDER BY fiscal_year DESC, province"""):
        rows.append([r[0], r[1], r[2], int(r[3] or 0), round(r[4] or 0, 2)])
    # total row
    tot = c.execute("SELECT COUNT(*), SUM(CASE WHEN price_valid=1 THEN win_price ELSE 0 END) FROM winner_history").fetchone()
    rows.append(["รวม", "ทั้งหมด", tot[0], int(tot[1] or 0), ""])
    write_tab(sh, "ผลประมูลย้อนหลัง", ["ปีงบ", "จังหวัด", "จำนวนงาน", "มูลค่ารวม (บาท)", "ส่วนลดเฉลี่ย %"], rows)

    # 2) คู่แข่งรายใหญ่ (top winners by จำนวนงานชนะ)
    print("สร้าง tab คู่แข่งรายใหญ่...")
    rows = []
    for r in c.execute("""
        SELECT winner, province, COUNT(*) AS n,
               SUM(CASE WHEN price_valid=1 THEN win_price ELSE 0 END),
               AVG(CASE WHEN price_valid=1 THEN discount_pct END)
        FROM winner_history
        WHERE winner != '' AND winner IS NOT NULL
        GROUP BY winner, province HAVING n >= 2
        ORDER BY n DESC, 4 DESC LIMIT 500"""):
        rows.append([r[0], r[1], r[2], int(r[3] or 0), round(r[4] or 0, 2)])
    write_tab(sh, "คู่แข่งรายใหญ่", ["ผู้ชนะ", "จังหวัด", "จำนวนงานชนะ", "มูลค่ารวม (บาท)", "ส่วนลดเฉลี่ย %"], rows)

    # 3) ตามตำบล (target insight)
    print("สร้าง tab ตามตำบล...")
    rows = []
    for r in c.execute("""
        SELECT province, district, subdistrict, COUNT(*),
               SUM(CASE WHEN price_valid=1 THEN win_price ELSE 0 END)
        FROM winner_history
        WHERE subdistrict != ''
        GROUP BY province, district, subdistrict
        ORDER BY 4 DESC LIMIT 1000"""):
        rows.append([r[0], r[1], r[2], r[3], int(r[4] or 0)])
    write_tab(sh, "ตามตำบล", ["จังหวัด", "อำเภอ", "ตำบล", "จำนวนงาน", "มูลค่ารวม (บาท)"], rows)

    print(f"\nURL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
