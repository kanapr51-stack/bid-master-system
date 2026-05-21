"""
bid_history_queries.py -- Query helpers for portal API routes

Queries PostgreSQL bid_history + competitor_profiles.
All functions return plain dicts suitable for JSON serialization.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import db_client


def get_job_bidders(job_id: str) -> dict:
    """
    Return all bidders for a specific job.
    Returns dict with keys: job, bidders, total — or {"error": "not_found"}.
    """
    job = db_client.fetch_one(
        "SELECT job_id, title, department, budget, deadline, province FROM all_jobs WHERE job_id = %s",
        (job_id,)
    )
    if not job:
        return {"error": "not_found"}

    bidders = db_client.fetch_all(
        """
        SELECT bidder_name, bidder_tin, price_proposal, price_agree,
               is_winner, is_sme, is_joint_venture, jv_partners, result_flag, consider_desc
        FROM bid_history
        WHERE job_id = %s
        ORDER BY is_winner DESC, price_agree
        """,
        (job_id,)
    )
    return {
        "job": dict(job),
        "bidders": [dict(b) for b in bidders],
        "total": len(bidders),
    }


def get_competitor_profile(tin: str) -> dict:
    """
    Return profile + recent jobs for a competitor by TIN.
    Returns dict with keys: profile, recent_jobs — or {"error": "not_found"}.
    """
    profile = db_client.fetch_one(
        "SELECT * FROM competitor_profiles WHERE bidder_tin = %s",
        (tin,)
    )
    if not profile:
        return {"error": "not_found"}

    recent = db_client.fetch_all(
        """
        SELECT bh.job_id, aj.title, aj.department, aj.province, aj.publish_date,
               bh.is_winner, bh.price_proposal, bh.price_agree
        FROM bid_history bh
        JOIN all_jobs aj ON aj.job_id = bh.job_id
        WHERE bh.bidder_tin = %s
        ORDER BY aj.publish_date DESC
        LIMIT 20
        """,
        (tin,)
    )
    p = dict(profile)
    p["provinces"] = list(p.get("provinces") or [])
    p["proc_types"] = list(p.get("proc_types") or [])
    return {
        "profile": p,
        "recent_jobs": [dict(r) for r in recent],
    }


def search_competitors(query: str, limit: int = 20) -> list[dict]:
    """Search competitor_profiles by company name (ILIKE)."""
    rows = db_client.fetch_all(
        """
        SELECT bidder_tin, company_name, total_bids, total_wins, win_rate_pct,
               is_sme, provinces, first_seen, last_seen
        FROM competitor_profiles
        WHERE company_name ILIKE %s
        ORDER BY total_bids DESC
        LIMIT %s
        """,
        (f"%{query}%", limit)
    )
    result = []
    for r in rows:
        d = dict(r)
        d["provinces"] = list(d.get("provinces") or [])
        result.append(d)
    return result


def get_jobs_shared_with(tin: str, target_provinces: tuple = ("นครพนม", "บึงกาฬ"), limit: int = 10) -> list[dict]:
    """Jobs where a competitor bid in target provinces (BSC home turf)."""
    placeholders = ", ".join(["%s"] * len(target_provinces))
    rows = db_client.fetch_all(
        f"""
        SELECT DISTINCT bh.job_id, aj.title, aj.department, aj.province, aj.publish_date, aj.budget
        FROM bid_history bh
        JOIN all_jobs aj ON aj.job_id = bh.job_id
        WHERE bh.bidder_tin = %s
          AND aj.province IN ({placeholders})
        ORDER BY aj.publish_date DESC
        LIMIT %s
        """,
        (tin, *target_provinces, limit)
    )
    return [dict(r) for r in rows]
