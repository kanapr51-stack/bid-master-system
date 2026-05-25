"""
pipeline_funnel.py — Pipeline funnel metrics for BMS

Reports discovery → enrichment → classification → active_bidding funnel.
Usage:
    python scripts/pipeline_funnel.py
"""

import sys
import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
DATA_DIR = Path(__file__).parent.parent / "data"

# Funnel tracking started when event lineage fields were added to all_jobs
FUNNEL_TRACKING_STARTED_AT = "2026-05-25"


def main():
    now = datetime.now()
    print(f"=== BMS Pipeline Funnel [{now.strftime('%Y-%m-%d %H:%M')}] ===")
    print(f"    (Operational funnel tracking since: {FUNNEL_TRACKING_STARTED_AT})\n")

    # Stage 1: RSS discovered (rss_seen_ids.json)
    seen_file = DATA_DIR / "rss_seen_ids.json"
    rss_discovered = 0
    if seen_file.exists():
        try:
            seen = json.loads(seen_file.read_text(encoding="utf-8"))
            rss_discovered = len(seen) if isinstance(seen, (list, dict)) else 0
        except Exception:
            pass
    print(f"Stage 1 — RSS discovered (seen IDs)     : {rss_discovered:>8,}")
    print(f"          └ NOTE: legacy corpus of 43K+ pre-dates funnel tracking")

    # Stage 2: all_jobs (ingested)
    ws_all = open_sheet(SPREADSHEET_ID, "all_jobs")
    all_rows = ws_all.get_all_values()
    hdrs = all_rows[0] if all_rows else []
    h = {v: i for i, v in enumerate(hdrs)}
    data_rows = all_rows[1:]
    total_jobs = len(data_rows)
    print(f"Stage 2 — all_jobs (ingested)            : {total_jobs:>8,}")

    # Stage 3: process5 enriched (has step_id OR announce_type)
    step_i  = h.get("step_id", -1)
    api_i   = h.get("api_validity_state", -1)
    ann_i   = h.get("announce_type", -1)
    disc_i  = h.get("discovered_at", -1)
    ev_i    = h.get("enrichment_version", -1)

    has_stepid  = sum(1 for r in data_rows if step_i >= 0 and r[step_i].strip())
    has_ann     = sum(1 for r in data_rows if ann_i >= 0 and r[ann_i].strip())
    api_active  = sum(1 for r in data_rows if api_i >= 0 and r[api_i].strip() == "active")
    api_retired = sum(1 for r in data_rows if api_i >= 0 and r[api_i].strip() == "retired")
    enriched    = sum(1 for r in data_rows if (step_i >= 0 and r[step_i].strip()) or (ann_i >= 0 and r[ann_i].strip()))

    # Universe split
    has_lineage  = sum(1 for r in data_rows if disc_i >= 0 and r[disc_i].strip())
    univ_b_count = sum(1 for r in data_rows if ev_i >= 0 and r[ev_i].strip() and r[ev_i].strip() != "legacy_none")
    univ_a_count = total_jobs - univ_b_count

    print(f"Stage 3 — enriched (has stepId/announce) : {enriched:>8,}  ({enriched/total_jobs*100:.1f}%)")
    print(f"          └ has stepId                   : {has_stepid:>8,}")
    print(f"          └ has announce_type            : {has_ann:>8,}")
    print(f"          └ api_validity_state=active    : {api_active:>8,}")
    print(f"          └ api_validity_state=retired   : {api_retired:>8,}")
    print(f"          └ has discovered_at (new era)  : {has_lineage:>8,}")
    print()
    print(f"=== Universe Split ===")
    print(f"  Universe A — legacy corpus (enrichment_version=legacy_none)")
    print(f"    count  : {univ_a_count:>8,}  ({univ_a_count/total_jobs*100:.1f}%)")
    if univ_a_count > 0:
        a_active = sum(1 for r in data_rows
                       if ev_i >= 0 and (not r[ev_i].strip() or r[ev_i].strip() == "legacy_none")
                       and step_i >= 0 and r[step_i].strip())
        print(f"    enriched (has stepId): {a_active:>6,}  ({a_active/univ_a_count*100:.1f}%) ← expected ~0%")
    print(f"  Universe B — operational telemetry era (enrichment_version≠legacy_none)")
    print(f"    count  : {univ_b_count:>8,}  ({univ_b_count/total_jobs*100:.1f}%)")
    if univ_b_count > 0:
        b_stepid = sum(1 for r in data_rows
                       if ev_i >= 0 and r[ev_i].strip() and r[ev_i].strip() != "legacy_none"
                       and step_i >= 0 and r[step_i].strip())
        b_enrich_rate = b_stepid / univ_b_count * 100
        print(f"    has stepId           : {b_stepid:>6,}  ({b_enrich_rate:.1f}%) ← target >70%")
        b_active = sum(1 for r in data_rows
                       if ev_i >= 0 and r[ev_i].strip() and r[ev_i].strip() != "legacy_none"
                       and api_i >= 0 and r[api_i].strip() == "active")
        print(f"    api_validity=active  : {b_active:>6,}")
    else:
        print(f"    (empty — will populate after first pipeline run post {FUNNEL_TRACKING_STARTED_AT})")

    # Stage 4: classified into derived sheets
    sheet_counts = {}
    for sheet in ["pre_tor", "tor_review", "active_bidding", "pending_award",
                  "awarded_jobs", "cancelled_jobs", "archived_unresolved"]:
        try:
            ws = open_sheet(SPREADSHEET_ID, sheet)
            n = len(ws.get_all_values()) - 1
            sheet_counts[sheet] = max(n, 0)
        except Exception:
            sheet_counts[sheet] = 0

    classified = sum(sheet_counts.values())
    print(f"Stage 4 — classified (all sheets)        : {classified:>8,}")
    print()

    # Sheet breakdown
    emoji = {"pre_tor": "🟣", "tor_review": "🟢", "active_bidding": "🔵",
             "pending_award": "🟡", "awarded_jobs": "⚪", "cancelled_jobs": "❌",
             "archived_unresolved": "🗄️"}
    for s, n in sheet_counts.items():
        pct = f"{n/total_jobs*100:.1f}%" if total_jobs else ""
        print(f"  {emoji.get(s,'  ')} {s:<24} : {n:>8,}  {pct}")

    # Funnel drop-off analysis
    print(f"\n=== Bottleneck Analysis ===")
    unenriched = total_jobs - enriched
    unarchived_pending = sheet_counts.get("pending_award", 0)
    print(f"  No enrichment data (no stepId/announce): {unenriched:>7,}  ({unenriched/total_jobs*100:.1f}%) ← discovery gap")
    print(f"  Genuine pending (post-cleanup)         : {unarchived_pending:>7,}")

    # refresh_count distribution
    rc_i = h.get("refresh_count", -1)
    if rc_i >= 0:
        rc_values = [int(r[rc_i]) for r in data_rows if rc_i < len(r) and r[rc_i].strip().isdigit()]
        if rc_values:
            never_refreshed = sum(1 for v in rc_values if v == 0)
            refreshed_once  = sum(1 for v in rc_values if v == 1)
            refreshed_multi = sum(1 for v in rc_values if v > 1)
            print(f"\n  refresh_count=0 (never refreshed)     : {never_refreshed:>7,}")
            print(f"  refresh_count=1                        : {refreshed_once:>7,}")
            print(f"  refresh_count>1                        : {refreshed_multi:>7,}")
        else:
            print(f"\n  refresh_count: no data yet (new field — all rows blank until first refresh)")

    # Discovery freshness (only for rows with discovered_at)
    if disc_i >= 0 and has_lineage > 0:
        print(f"\n=== Discovery Freshness (operational cohort: {has_lineage:,} jobs) ===")
        now_utc = datetime.now(timezone.utc)
        cutoff_24h = now_utc - timedelta(hours=24)
        fresh_24h = 0
        lags = []
        for r in data_rows:
            if disc_i >= len(r) or not r[disc_i].strip():
                continue
            try:
                dt = datetime.fromisoformat(r[disc_i].replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                lag_h = (now_utc - dt).total_seconds() / 3600
                lags.append(lag_h)
                if dt >= cutoff_24h:
                    fresh_24h += 1
            except Exception:
                pass
        if lags:
            lags.sort()
            median_lag = lags[len(lags) // 2]
            enrich_rate = api_active / has_lineage * 100 if has_lineage else 0
            print(f"  Discovered <24h ago                   : {fresh_24h:>7,}")
            print(f"  Median discovery lag                  : {median_lag:>7.1f}h")
            print(f"  Enrich success rate (active/lineage)  : {enrich_rate:>7.1f}%")
    else:
        print(f"\n=== Discovery Freshness ===")
        print(f"  discovered_at: no data yet — will populate after next pipeline run")

    print(f"\n=== Active Bidding Health ===")
    active = sheet_counts.get("active_bidding", 0)
    print(f"  active_bidding count: {active}")
    if active < 50:
        print(f"  ⚠️  LOW — likely RSS coverage gap or classifier issue")
        print(f"       Diagnose: 1) RSS feed health  2) refresh pipeline lag  3) classifier logic")
    elif active < 100:
        print(f"  🟡 GROWING — runner online, expect increase in 24-48h")
    else:
        print(f"  ✅ HEALTHY")

    # Daily new active_bidding KPI (jobs with discovered_at today)
    if disc_i >= 0:
        today_str = now.strftime("%Y-%m-%d")
        new_today = sum(
            1 for r in data_rows
            if disc_i < len(r) and r[disc_i].strip().startswith(today_str)
        )
        print(f"  New jobs discovered today              : {new_today:>7,}")


if __name__ == "__main__":
    main()
