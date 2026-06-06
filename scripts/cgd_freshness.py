"""cgd_freshness.py — วัดความสด winner_history (max announce_date/ปี) → ตอบ 'CGD lag กี่วัน'."""
import datetime as _dt
import sqlite3
import sys
from pathlib import Path

_TH_MONTH = {"ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
             "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12}


def parse_thai_date(s: str):
    """Thai short date → date. รองรับทั้งเว้นวรรค '9 ก.ค. 68' (วันที่เกิดรายการ, จริงใน CGD)
    และขีด '9-เม.ย.-69'. ปีเป็น พ.ศ. 2 หลัก (69=2569=2026 ค.ศ.). คืน None ถ้า parse ไม่ได้."""
    s = (s or "").strip()
    if not s or s == "-":
        return None
    parts = s.split("-") if "-" in s else s.split()
    try:
        d, mon, yy = parts
        m = _TH_MONTH.get(mon.strip())
        if not m:
            return None
        year_ce = 2500 + int(yy) - 543  # 69 → 2569 พ.ศ. → 2026 ค.ศ.
        return _dt.date(year_ce, m, int(d))
    except (ValueError, KeyError):
        return None


def report(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    out = {}
    for fy, n in conn.execute("SELECT fiscal_year, COUNT(*) FROM winner_history GROUP BY fiscal_year"):
        out[fy] = {"count": n}
    # max announce_date (parse Thai) ของปีล่าสุด
    latest = None
    for (ad,) in conn.execute("SELECT announce_date FROM winner_history WHERE fiscal_year='2569'"):
        d = parse_thai_date(ad)
        if d and (latest is None or d > latest):
            latest = d
    conn.close()
    out["latest_2569"] = latest.isoformat() if latest else None
    if latest:
        out["lag_days"] = (_dt.date.today() - latest).days
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import os
    db = str(Path(os.environ.get("BMS_DATA_DIR", "data")) / "winner_history.db")
    if not Path(db).exists():
        db = "data/winner_history.db"
    print(report(db))
