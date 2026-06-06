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


def refresh_year(db_path: str, year: str, rids: list, provinces: list, search=None) -> int:
    """ดึงทุก resource (rids) × ทุกจังหวัด (provinces) สำหรับปีนี้ → upsert. คืนจำนวน row ใหม่.
    โครงสร้าง CGD จริง = 1 package/ปี × ~10 resources → rids เป็น list."""
    search = search or _cgd_search
    conn = _open_db(db_path)   # พก schema เอง (ไม่ผูก DB path คงที่ของ _winner_history_build)
    ph = ",".join("?" * len(whb.COLS.split(",")))
    new = 0
    try:
        for rid in rids:
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


def _load_token() -> str:
    from pathlib import Path as _P
    env = _P(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPEND_USER_TOKEN="):
                return line.split("=", 1)[1].strip()
    import os
    return os.environ.get("OPEND_USER_TOKEN", "")


def main(years=("2569", "2568"), provinces=("นครพนม", "บึงกาฬ"), db_path=None):
    """RUN จริง (เครื่องบ้าน residential): refresh ปีเป้าหมาย → winner_history.db + รายงาน lag.
    ปีที่ CGD ยังไม่ publish (404) → ข้าม + log ชัด."""
    sys.stdout.reconfigure(encoding="utf-8")
    from pathlib import Path as _P
    import cgd_resource_catalog as cat
    import cgd_freshness as fr
    token = _load_token()
    if not token:
        print("❌ OPEND_USER_TOKEN ไม่พบ — หยุด")
        return
    import os
    os.environ["OPEND_USER_TOKEN"] = token   # ให้ cgd_resource_catalog._fetch_package ใช้ token เดียวกัน
    db = db_path or str(_P(__file__).parent.parent / "data" / "winner_history.db")

    def search(rid, prov, limit, offset):
        return _cgd_search(rid, prov, token, limit, offset)

    for year in years:
        rids = cat.resource_ids_for_year(year)
        if not rids:
            print(f"⚠️ CGD ยังไม่ publish ปี {year} (package egp-contact-{year} = 404) — ข้าม")
            continue
        n = refresh_year(db, year, list(rids), list(provinces), search=search)
        print(f"✅ ปี {year}: {len(rids)} resources × {len(provinces)} จว. → +{n} row ใหม่")
    print("freshness:", fr.report(db))


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


if __name__ == "__main__":
    main()
