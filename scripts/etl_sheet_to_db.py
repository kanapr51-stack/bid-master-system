"""
etl_sheet_to_db.py — One-shot ETL จาก Google Sheets → PostgreSQL

Phase A: คัดลอกอย่างเดียว (Sheet ยังคงเป็น source of truth)
ใช้ตรวจสอบว่า DB เก็บข้อมูลถูก + เปรียบเทียบ row counts

Usage:
  python etl_sheet_to_db.py --table all_jobs
  python etl_sheet_to_db.py --table customers
  python etl_sheet_to_db.py --table dept_catalog
  python etl_sheet_to_db.py --all
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
import db_client

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ============================================================
# all_jobs
# ============================================================
def etl_all_jobs():
    log("=== ETL all_jobs ===")
    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    rows = ws.get_all_values()
    if len(rows) < 2:
        log("  (sheet empty)")
        return

    headers = rows[0]
    h = {name: i for i, name in enumerate(headers)}
    log(f"  Sheet rows: {len(rows) - 1}")

    sql = """
        INSERT INTO all_jobs (
            job_id, title, department, province, district, subdistrict,
            procurement_type, budget, publish_date, deadline,
            project_status, search_keyword, tor_url,
            first_seen_at, last_seen_at,
            step_id, project_status_raw, announce_type,
            project_type, construction_subtype, budget_tier, urgency_tier,
            method_id, sme_suitable, geographic_precision, unspsc_family
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            title = EXCLUDED.title,
            department = EXCLUDED.department,
            province = EXCLUDED.province,
            district = EXCLUDED.district,
            subdistrict = EXCLUDED.subdistrict,
            procurement_type = EXCLUDED.procurement_type,
            budget = EXCLUDED.budget,
            publish_date = EXCLUDED.publish_date,
            deadline = EXCLUDED.deadline,
            project_status = EXCLUDED.project_status,
            search_keyword = EXCLUDED.search_keyword,
            tor_url = EXCLUDED.tor_url,
            first_seen_at = EXCLUDED.first_seen_at,
            last_seen_at = EXCLUDED.last_seen_at,
            step_id = EXCLUDED.step_id,
            project_status_raw = EXCLUDED.project_status_raw,
            announce_type = EXCLUDED.announce_type,
            project_type = EXCLUDED.project_type,
            construction_subtype = EXCLUDED.construction_subtype,
            budget_tier = EXCLUDED.budget_tier,
            urgency_tier = EXCLUDED.urgency_tier,
            method_id = EXCLUDED.method_id,
            sme_suitable = EXCLUDED.sme_suitable,
            geographic_precision = EXCLUDED.geographic_precision,
            unspsc_family = EXCLUDED.unspsc_family
    """

    batch = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        def g(name: str, default: str = "") -> str:
            idx = h.get(name, -1)
            return r[idx] if 0 <= idx < len(r) else default

        batch.append((
            g("job_id"),
            g("title"),
            g("department"),
            g("province"),
            g("district"),
            g("subdistrict"),
            g("procurement_type"),
            g("budget"),
            g("publish_date"),
            g("deadline"),
            g("project_status"),
            g("search_keyword"),
            g("tor_url"),
            parse_ts(g("first_seen_at")),
            parse_ts(g("last_seen_at")),
            g("step_id"),
            g("project_status_raw"),
            g("announce_type"),
            g("project_type"),
            g("construction_subtype"),
            g("budget_tier"),
            g("urgency_tier"),
            g("method_id"),
            g("sme_suitable"),
            g("geographic_precision"),
            g("unspsc_family"),
        ))

    log(f"  Inserting {len(batch)} rows…")
    db_client.execute_many(sql, batch)

    # Verify
    res = db_client.fetch_one("SELECT COUNT(*) as cnt FROM all_jobs")
    log(f"  ✅ DB now has {res['cnt']} rows")


# ============================================================
# customers
# ============================================================
def etl_customers():
    log("=== ETL customers ===")
    try:
        ws = open_sheet(SPREADSHEET_ID, "customers")
    except Exception as e:
        log(f"  customers sheet not found: {e}")
        return
    rows = ws.get_all_values()
    if len(rows) < 2:
        log("  (sheet empty)")
        return
    headers = rows[0]
    h = {name: i for i, name in enumerate(headers)}
    log(f"  Sheet rows: {len(rows) - 1}")

    sql = """
        INSERT INTO customers (
            line_user_id, display_name, email, phone,
            provinces, districts, keywords, status,
            registered_at, expires_at, last_active_at, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (line_user_id) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            phone = EXCLUDED.phone,
            provinces = EXCLUDED.provinces,
            districts = EXCLUDED.districts,
            keywords = EXCLUDED.keywords,
            status = EXCLUDED.status,
            registered_at = EXCLUDED.registered_at,
            expires_at = EXCLUDED.expires_at,
            last_active_at = EXCLUDED.last_active_at,
            notes = EXCLUDED.notes
    """

    batch = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        def g(name: str, default: str = "") -> str:
            idx = h.get(name, -1)
            return r[idx] if 0 <= idx < len(r) else default
        batch.append((
            g("line_user_id"),
            g("display_name"),
            g("email"),
            g("phone"),
            g("จังหวัด"),
            g("อำเภอ"),
            g("keywords"),
            g("status") or "trial",
            parse_ts(g("registered_at")) or datetime.now(),
            parse_ts(g("expires_at")),
            parse_ts(g("last_active_at")) or datetime.now(),
            g("notes"),
        ))

    db_client.execute_many(sql, batch)
    res = db_client.fetch_one("SELECT COUNT(*) as cnt FROM customers")
    log(f"  ✅ DB now has {res['cnt']} rows")


# ============================================================
# dept_catalog (from JSON file, not Sheet)
# ============================================================
def etl_dept_catalog():
    log("=== ETL dept_catalog ===")
    catalog_file = Path(__file__).parent.parent / "data" / "egp_deptid_catalog.json"
    if not catalog_file.exists():
        log("  catalog file not found")
        return
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    log(f"  JSON entries: {len(catalog)}")

    sql = """
        INSERT INTO dept_catalog (
            dept_id, dept_name, item_count, project_ids, sample_titles,
            pub_dates, source, enriched_at, scanned_at
        ) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
        ON CONFLICT (dept_id) DO UPDATE SET
            dept_name = EXCLUDED.dept_name,
            item_count = EXCLUDED.item_count,
            project_ids = EXCLUDED.project_ids,
            sample_titles = EXCLUDED.sample_titles,
            pub_dates = EXCLUDED.pub_dates,
            source = EXCLUDED.source,
            enriched_at = EXCLUDED.enriched_at,
            scanned_at = EXCLUDED.scanned_at
    """

    batch = []
    for d, v in catalog.items():
        batch.append((
            d,
            v.get("dept_name", ""),
            v.get("item_count", 0),
            json.dumps(v.get("projectIds", []), ensure_ascii=False),
            json.dumps(v.get("titles", []), ensure_ascii=False),
            json.dumps(v.get("pubDates", []), ensure_ascii=False),
            v.get("source", v.get("note", "")),
            parse_ts(v.get("enriched_at", "")),
            parse_ts(v.get("scanned_at", "")),
        ))

    db_client.execute_many(sql, batch)
    res = db_client.fetch_one("SELECT COUNT(*) as cnt FROM dept_catalog")
    log(f"  ✅ DB now has {res['cnt']} rows")


# ============================================================
# winners (from winner_cache_bootstrap.json)
# ============================================================
def etl_winners():
    log("=== ETL winners ===")
    cache_file = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"
    if not cache_file.exists():
        log("  winner cache not found")
        return
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    log(f"  Cache entries: {len(cache)}")

    sql = """
        INSERT INTO winners (job_id, winner_name, winner_price, discount_pct, award_date)
        SELECT %s, %s, %s, %s, %s
        WHERE EXISTS (SELECT 1 FROM all_jobs WHERE job_id = %s)
        ON CONFLICT (job_id) DO UPDATE SET
            winner_name = EXCLUDED.winner_name,
            winner_price = EXCLUDED.winner_price,
            discount_pct = EXCLUDED.discount_pct,
            award_date = EXCLUDED.award_date
    """

    batch = []
    for jid, w in cache.items():
        if not isinstance(w, dict):
            continue
        batch.append((
            jid,
            w.get("winner_name", ""),
            w.get("winner_price", ""),
            w.get("discount_pct", ""),
            w.get("award_date", ""),
            jid,  # for WHERE EXISTS
        ))

    db_client.execute_many(sql, batch)
    res = db_client.fetch_one("SELECT COUNT(*) as cnt FROM winners")
    log(f"  ✅ DB now has {res['cnt']} rows (matched with all_jobs)")


# ============================================================
# bid_history (from bid_history sheet)
# ============================================================
def etl_bid_history():
    log("=== ETL bid_history ===")
    try:
        ws = open_sheet(SPREADSHEET_ID, "bid_history")
    except Exception as e:
        log(f"  bid_history sheet not found: {e}")
        return
    rows = ws.get_all_values()
    if len(rows) < 2:
        log("  (sheet empty)")
        return
    headers = rows[0]
    h = {name: i for i, name in enumerate(headers)}
    log(f"  Sheet rows: {len(rows) - 1}")

    sql = """
        INSERT INTO bid_history (
            job_id, bidder_name, bidder_tin, price_proposal, price_agree,
            result_flag, is_winner, is_sme, is_joint_venture,
            jv_partners, consider_desc, fetched_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """

    batch = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        def g(name: str, default: str = "", _r=r) -> str:
            idx = h.get(name, -1)
            return _r[idx] if 0 <= idx < len(_r) else default

        batch.append((
            g("job_id"),
            g("bidder_name"),
            g("bidder_tin"),
            g("price_proposal"),
            g("price_agree"),
            g("result_flag"),
            g("is_winner").upper() in ("TRUE", "1", "YES"),
            g("is_sme").upper() in ("TRUE", "1", "YES"),
            g("is_joint_venture").upper() in ("TRUE", "1", "YES"),
            g("jv_partners"),
            g("consider_desc"),
            parse_ts(g("fetched_at")) or datetime.now(),
        ))

    # Skip rows where job_id not in all_jobs (FK constraint)
    known_jobs = {r["job_id"] for r in db_client.fetch_all("SELECT job_id FROM all_jobs")}
    valid = [b for b in batch if b[0] in known_jobs]
    skipped = len(batch) - len(valid)
    if skipped:
        log(f"  Skipping {skipped} rows (job_id not in all_jobs)")

    log(f"  Inserting {len(valid)} rows…")
    db_client.execute_many(sql, valid)

    res = db_client.fetch_one("SELECT COUNT(*) as cnt FROM bid_history")
    log(f"  ✅ DB now has {res['cnt']} rows")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", choices=["all_jobs", "customers", "dept_catalog", "winners", "bid_history"])
    parser.add_argument("--all", action="store_true", help="ETL all tables")
    args = parser.parse_args()

    started = datetime.now()
    if args.all or args.table is None:
        etl_all_jobs()
        etl_winners()
        etl_customers()
        etl_dept_catalog()
        etl_bid_history()
    elif args.table == "all_jobs":
        etl_all_jobs()
    elif args.table == "customers":
        etl_customers()
    elif args.table == "dept_catalog":
        etl_dept_catalog()
    elif args.table == "winners":
        etl_winners()
    elif args.table == "bid_history":
        etl_bid_history()

    elapsed = (datetime.now() - started).total_seconds()
    log(f"\n✅ ETL DONE — {elapsed:.1f}s")


if __name__ == "__main__":
    main()
