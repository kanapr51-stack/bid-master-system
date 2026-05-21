"""
migrate_competitor_profiles_v2.py
เพิ่ม avg_discount_from_budget_pct + stddev_discount_pct ใน competitor_profiles view
รัน: python scripts/migrate_competitor_profiles_v2.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'web', '.env.local'))

import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set"); sys.exit(1)

NEW_VIEW_SQL = """
DROP MATERIALIZED VIEW IF EXISTS competitor_profiles CASCADE;

CREATE MATERIALIZED VIEW competitor_profiles AS
SELECT
    bh.bidder_tin,
    MAX(bh.bidder_name)                                     AS company_name,
    COUNT(DISTINCT bh.job_id)                               AS total_bids,
    COUNT(DISTINCT CASE WHEN bh.is_winner THEN bh.job_id END) AS total_wins,
    ROUND(
        100.0 * COUNT(DISTINCT CASE WHEN bh.is_winner THEN bh.job_id END)
        / NULLIF(COUNT(DISTINCT bh.job_id), 0), 1
    )                                                       AS win_rate_pct,
    BOOL_OR(bh.is_sme)                                      AS is_sme,
    BOOL_OR(bh.is_joint_venture)                            AS has_jv,
    MIN(aj.publish_date)                                    AS first_seen,
    MAX(aj.publish_date)                                    AS last_seen,
    ARRAY_AGG(DISTINCT aj.province ORDER BY aj.province)    AS provinces,
    ARRAY_AGG(DISTINCT aj.procurement_type
              ORDER BY aj.procurement_type)                 AS proc_types,
    ROUND(AVG(
        CASE
            WHEN bh.price_proposal ~ '^[0-9]+(\\.[0-9]+)?$'
             AND bh.price_agree    ~ '^[0-9]+(\\.[0-9]+)?$'
             AND bh.price_agree::NUMERIC > 0
            THEN 100.0 * (bh.price_proposal::NUMERIC - bh.price_agree::NUMERIC)
                 / bh.price_proposal::NUMERIC
        END
    )::NUMERIC, 1)                                          AS avg_discount_pct,
    ROUND(AVG(
        CASE
            WHEN aj.budget != ''
             AND bh.price_agree ~ '^[0-9]+(\\.[0-9]+)?$'
             AND REPLACE(aj.budget, ',', '') ~ '^[0-9]+(\\.[0-9]+)?$'
             AND REPLACE(aj.budget, ',', '')::NUMERIC > 0
             AND bh.price_agree::NUMERIC > 0
            THEN 100.0 * (REPLACE(aj.budget, ',', '')::NUMERIC - bh.price_agree::NUMERIC)
                 / REPLACE(aj.budget, ',', '')::NUMERIC
        END
    )::NUMERIC, 1)                                          AS avg_discount_from_budget_pct,
    ROUND(STDDEV(
        CASE
            WHEN aj.budget != ''
             AND bh.price_agree ~ '^[0-9]+(\\.[0-9]+)?$'
             AND REPLACE(aj.budget, ',', '') ~ '^[0-9]+(\\.[0-9]+)?$'
             AND REPLACE(aj.budget, ',', '')::NUMERIC > 0
             AND bh.price_agree::NUMERIC > 0
            THEN 100.0 * (REPLACE(aj.budget, ',', '')::NUMERIC - bh.price_agree::NUMERIC)
                 / REPLACE(aj.budget, ',', '')::NUMERIC
        END
    )::NUMERIC, 1)                                          AS stddev_discount_pct
FROM bid_history bh
JOIN all_jobs aj ON aj.job_id = bh.job_id
WHERE bh.bidder_tin <> ''
GROUP BY bh.bidder_tin
WITH DATA;

CREATE UNIQUE INDEX idx_competitor_profiles_tin ON competitor_profiles(bidder_tin);
CREATE INDEX idx_competitor_profiles_wins ON competitor_profiles(total_wins DESC);
"""

def main():
    print("Migrating competitor_profiles view (v2 - discount_from_budget_pct)...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(NEW_VIEW_SQL)
    print("View recreated successfully")

    cur.execute("SELECT COUNT(*) FROM competitor_profiles")
    count = cur.fetchone()[0]
    print(f"   {count} rows in competitor_profiles")

    cur.execute("SELECT bidder_tin, avg_discount_from_budget_pct, stddev_discount_pct FROM competitor_profiles WHERE avg_discount_from_budget_pct IS NOT NULL LIMIT 5")
    rows = cur.fetchall()
    print("   Sample rows with discount_from_budget_pct:")
    for row in rows:
        print(f"   TIN={row[0]} avg={row[1]} stddev={row[2]}")

    cur.close(); conn.close()

if __name__ == '__main__':
    main()
