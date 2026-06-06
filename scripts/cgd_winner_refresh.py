"""cgd_winner_refresh.py — pull CGD ต่อปี/จังหวัด แบบ incremental → upsert winner_history.db.
OS-agnostic (requests + sqlite3). reuse schema/row_from_rec จาก _winner_history_build.
incremental = INSERT OR IGNORE (project_id PK) + หยุดเมื่อทั้งหน้าซ้ำหมด."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import _winner_history_build as whb
from cgd_discovery import _cgd_search

PAGE = 1000


def refresh_year(db_path: str, year: str, rid: str, provinces: list, search=None) -> int:
    """ดึงทุกจังหวัดใน provinces สำหรับปี/resource นี้ → upsert. คืนจำนวน row ใหม่."""
    search = search or _cgd_search
    conn = _open_db(db_path)   # พก schema เอง (ไม่ผูก DB path คงที่ของ _winner_history_build)
    ph = ",".join("?" * len(whb.COLS.split(",")))
    new = 0
    try:
        for prov in provinces:
            offset = 0
            while True:
                res = search(rid, prov, PAGE, offset)
                recs = ((res or {}).get("result", {}) or {}).get("records", []) or []
                if not recs:
                    break
                rows = [whb.row_from_rec(r, year) for r in recs
                        if str(r.get("รหัสโครงการ") or "").strip()]
                before = conn.total_changes
                conn.executemany(f"INSERT OR IGNORE INTO winner_history ({whb.COLS}) VALUES ({ph})", rows)
                new += conn.total_changes - before
                offset += PAGE
        conn.commit()
    finally:
        conn.close()
    return new


def _open_db(db_path: str) -> sqlite3.Connection:
    """สร้าง winner_history schema ที่ db_path (กรณี _winner_history_build ไม่มี helper แยก path)."""
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS winner_history (
        project_id TEXT PRIMARY KEY, fiscal_year TEXT, province TEXT, district TEXT,
        subdistrict TEXT, project_name TEXT, dept TEXT, proc_type TEXT, winner TEXT,
        winner_tin TEXT, budget INTEGER, mid_price INTEGER, win_price INTEGER,
        discount_pct REAL, price_valid INTEGER, announce_date TEXT, contract_no TEXT,
        sign_date TEXT, status TEXT, source TEXT, raw_json TEXT)""")
    conn.commit()
    return conn
