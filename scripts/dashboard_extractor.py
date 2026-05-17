"""
dashboard_extractor.py — รวบรวม metrics จาก logs/sheets/git → snapshot.json

ใช้สำหรับ Bid Master Dashboard (Next.js)
Output: dashboard/data/snapshot.json

Sources:
1. logs/pipeline_*.txt — scrape time, items, classifier counts, Cloudflare hits per run
2. Google Sheets — current counts per sheet (active/tor/pending/awarded/cancelled)
3. git log — commits + timestamps สำหรับ inflection points
4. data/winner_cache_bootstrap.json — winner growth
"""
import sys
import os
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parent.parent
LOGS_DIR = ROOT / "logs"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "dashboard" / "data"
PUBLIC_DIR = ROOT / "dashboard" / "web" / "public"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ================================================================
# 1. Parse pipeline logs (history per run)
# ================================================================
def parse_pipeline_log(path: Path) -> dict | None:
    """Extract metrics from one pipeline log file"""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return None

    # Extract date from filename: pipeline_YYYYMMDD.txt or pipeline_collect_YYYYMMDD.txt
    date_match = re.search(r'(\d{4})(\d{2})(\d{2})', path.name)
    if not date_match:
        return None
    y, m, d = date_match.groups()
    run_date = f"{y}-{m}-{d}"

    metrics = {
        'date': run_date,
        'filename': path.name,
        'phase': 'collect' if 'collect' in path.name else ('notify' if 'notify' in path.name else 'full'),
        'file_size': path.stat().st_size,
        'last_modified': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }

    # Pipeline เสร็จสิ้นใน X วินาที
    pipeline_durations = re.findall(r'Pipeline เสร็จสิ้นใน ([\d.]+) วินาที', text)
    if pipeline_durations:
        metrics['pipeline_durations_sec'] = [float(d) for d in pipeline_durations]
        metrics['total_duration_sec'] = sum(metrics['pipeline_durations_sec'])

    # Scrape per keyword: 'XYZ': N รายการ → กรองแล้ว M, ใหม่ K
    keyword_results = []
    for m in re.finditer(
        r"'([^']+)':\s*(\d+)\s*รายการ\s*→\s*กรองแล้ว\s*(\d+)(?:,\s*ข้ามผิดจังหวัด\s*(\d+))?,\s*ใหม่\s*(\d+)",
        text
    ):
        keyword_results.append({
            'keyword': m.group(1),
            'raw_items': int(m.group(2)),
            'filtered': int(m.group(3)),
            'province_skipped': int(m.group(4) or 0),
            'new': int(m.group(5)),
        })
    metrics['scrape_keywords'] = keyword_results
    metrics['total_raw'] = sum(k['raw_items'] for k in keyword_results)
    metrics['total_filtered'] = sum(k['filtered'] for k in keyword_results)
    metrics['total_new'] = sum(k['new'] for k in keyword_results)

    # Cloudflare hits — heuristic count
    metrics['cloudflare_hits'] = text.count('Cloudflare') + text.count('ไม่ผ่านการตรวจสอบ')
    metrics['search_timeouts'] = text.count('Search timeout')
    metrics['rate_limit_hits'] = text.count('rate limit')

    # Classifier counts
    cls = {}
    for label, key in [
        ('pre_tor', 'pre_tor'),
        ('tor_review', 'tor_review'),
        ('active_bidding', 'active_bidding'),
        ('pending_award', 'pending_award'),
        ('awarded_jobs', 'awarded_jobs'),
        ('cancelled_jobs', 'cancelled_jobs'),
    ]:
        # หา "   pre_tor        (ขั้นวางแผน Q):       N"
        # หรือ "   pre_tor: 0 งาน" (ตอน write phase)
        # ใช้ตัวแรก (classify summary)
        matches = re.findall(rf'\s{re.escape(label)}\s+\([^)]*\):\s*(\d+)', text)
        if matches:
            cls[key] = int(matches[-1])  # ใช้ค่าล่าสุด (หลัง refresh แล้ว)
    metrics['classifier'] = cls
    metrics['total_active_pipeline'] = sum(cls.values()) if cls else 0

    # All jobs count
    jobs_match = re.search(r'jobs:\s*(\d+)', text)
    if jobs_match:
        metrics['all_jobs_count'] = int(jobs_match.group(1))

    # LINE notify success
    metrics['line_notify_success'] = text.count('✅ ส่ง LINE part')
    metrics['discord_notify_success'] = text.count('Discord: ส่งสำเร็จ')

    return metrics


def collect_pipeline_runs() -> list[dict]:
    """รวบ pipeline log ทุกไฟล์"""
    runs = []
    for log_file in sorted(LOGS_DIR.glob("pipeline_*.txt")):
        m = parse_pipeline_log(log_file)
        if m:
            runs.append(m)
    return runs


# ================================================================
# 2. Sheet snapshot — ดึงจำนวน rows ใน Sheet ปัจจุบัน
# ================================================================
def fetch_sheet_snapshot() -> dict:
    """ลองดึงจำนวน rows จาก Google Sheets"""
    try:
        from sheets_client import open_sheet
    except ImportError:
        log("⚠️ sheets_client ไม่พบ — skip Sheet snapshot")
        return {}

    snapshot = {'fetched_at': datetime.now().isoformat()}
    for sheet_name in ['pre_tor', 'tor_review', 'active_bidding', 'pending_award',
                       'awarded_jobs', 'cancelled_jobs', 'all_jobs']:
        try:
            ws = open_sheet(SPREADSHEET_ID, sheet_name)
            rows = ws.get_all_values()
            # ลบ header row
            snapshot[sheet_name] = max(0, len(rows) - 1) if rows else 0
        except Exception as e:
            snapshot[sheet_name] = None
            log(f"  ⚠️ {sheet_name}: {e}")
    return snapshot


# ================================================================
# 3. Git log — commits สำหรับ inflection points
# ================================================================
def collect_git_log(limit: int = 50) -> list[dict]:
    """ดึง git log ล่าสุด"""
    try:
        result = subprocess.run(
            ['git', 'log', f'-{limit}', '--pretty=format:%H|%ai|%s'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding='utf-8',
        )
        commits = []
        for line in result.stdout.splitlines():
            if '|' not in line:
                continue
            parts = line.split('|', 2)
            if len(parts) == 3:
                commits.append({
                    'hash': parts[0][:8],
                    'date': parts[1],
                    'subject': parts[2],
                })
        return commits
    except Exception as e:
        log(f"⚠️ git log error: {e}")
        return []


# ================================================================
# 4. Winner cache growth
# ================================================================
def winner_cache_stats() -> dict:
    """อ่าน winner_cache_bootstrap.json"""
    cache_file = DATA_DIR / "winner_cache_bootstrap.json"
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding='utf-8'))
        winners = data if isinstance(data, list) else list(data.values())
        return {
            'total_winners': len(winners),
            'unique_tins': len(set(w.get('winner_tin', '') for w in winners if isinstance(w, dict))),
            'unique_jobs': len(set(w.get('job_id', '') for w in winners if isinstance(w, dict))),
            'last_modified': datetime.fromtimestamp(cache_file.stat().st_mtime).isoformat(),
        }
    except Exception as e:
        log(f"⚠️ winner_cache parse error: {e}")
        return {}


# ================================================================
# 4.5 RSS catalog stats (Phase 1)
# ================================================================
def rss_catalog_stats() -> dict:
    """อ่าน egp_deptid_catalog.json + history จาก rss_run_*.json"""
    catalog_file = DATA_DIR / "egp_deptid_catalog.json"
    if not catalog_file.exists():
        return {}
    try:
        catalog = json.loads(catalog_file.read_text(encoding='utf-8'))
    except Exception as e:
        log(f"⚠️ catalog parse error: {e}")
        return {}

    total = len(catalog)
    active = sum(1 for v in catalog.values() if v.get('item_count', 0) > 0)
    total_items = sum(v.get('item_count', 0) for v in catalog.values())
    empty = total - active

    # Top depts by item count
    top = sorted(
        [(d, v.get('item_count', 0), v.get('titles', [''])[0] if v.get('titles') else '',
          v.get('dept_name', ''))
         for d, v in catalog.items() if v.get('item_count', 0) > 0],
        key=lambda x: -x[1],
    )[:10]
    enriched_count = sum(1 for v in catalog.values() if v.get('dept_name'))

    # History from rss_run_*.json (last 50 runs)
    run_files = sorted(DATA_DIR.glob("rss_run_*.json"))[-50:]
    history = []
    for rf in run_files:
        try:
            d = json.loads(rf.read_text(encoding='utf-8'))
            history.append({
                'at': d.get('run_at', ''),
                'catalog_size': d.get('catalog_size', 0),
                'total_items': d.get('total_items', 0),
                'missed_by_process5': d.get('missed_by_process5_count', 0),
            })
        except Exception:
            continue

    # Queue size
    queue_file = DATA_DIR / "rss_queue.json"
    queue_count = 0
    if queue_file.exists():
        try:
            q = json.loads(queue_file.read_text(encoding='utf-8'))
            queue_count = len(q) if isinstance(q, list) else 0
        except Exception:
            pass

    # Full list (compact) สำหรับ catalog browser ใน dashboard
    all_depts = []
    for d, v in sorted(catalog.items()):
        titles = v.get('titles', [])
        first_title = titles[0] if titles else ''
        all_depts.append({
            'dept_id': d,
            'dept_name': v.get('dept_name', ''),  # enriched via process5 getProjectDetail
            'item_count': v.get('item_count', 0),
            'sample_title': first_title[:120],
            'pub_date': (v.get('pubDates', []) or [''])[0],
        })

    return {
        'total_depts': total,
        'active_depts': active,
        'empty_depts': empty,
        'total_items': total_items,
        'queue_size': queue_count,
        'coverage_pct': round(total / 9999 * 100, 2),
        'active_pct': round(active / max(1, total) * 100, 2),
        'top_depts': [
            {'dept_id': d, 'dept_name': n, 'item_count': c, 'sample_title': t[:80]}
            for d, c, t, n in top
        ],
        'enriched_count': enriched_count,
        'all_depts': all_depts,
        'history': history,
    }


# ================================================================
# 5. Build daily aggregates สำหรับ time-series
# ================================================================
def build_daily_aggregates(runs: list[dict]) -> dict:
    """รวม metrics ต่อวัน"""
    by_date = defaultdict(lambda: {
        'pipeline_durations': [],
        'total_raw': 0,
        'total_filtered': 0,
        'total_new': 0,
        'cloudflare_hits': 0,
        'search_timeouts': 0,
        'classifier_snapshots': [],
        'phases_run': set(),
    })

    for r in runs:
        d = by_date[r['date']]
        if 'total_duration_sec' in r:
            d['pipeline_durations'].append(r['total_duration_sec'])
        d['total_raw'] += r.get('total_raw', 0)
        d['total_filtered'] += r.get('total_filtered', 0)
        d['total_new'] += r.get('total_new', 0)
        d['cloudflare_hits'] += r.get('cloudflare_hits', 0)
        d['search_timeouts'] += r.get('search_timeouts', 0)
        if r.get('classifier'):
            d['classifier_snapshots'].append(r['classifier'])
        d['phases_run'].add(r['phase'])

    # Serialize
    result = {}
    for date_key, agg in sorted(by_date.items()):
        result[date_key] = {
            'date': date_key,
            'total_pipeline_sec': sum(agg['pipeline_durations']),
            'pipeline_runs': len(agg['pipeline_durations']),
            'total_raw_scraped': agg['total_raw'],
            'total_filtered': agg['total_filtered'],
            'total_new_jobs': agg['total_new'],
            'cloudflare_hits': agg['cloudflare_hits'],
            'search_timeouts': agg['search_timeouts'],
            'classifier_latest': agg['classifier_snapshots'][-1] if agg['classifier_snapshots'] else None,
            'phases': sorted(agg['phases_run']),
        }
    return result


# ================================================================
# 6. Build inflection points (commit + metrics impact)
# ================================================================
def build_inflection_points(commits: list[dict], daily: dict) -> list[dict]:
    """หา commits ที่มี impact กับ metrics"""
    points = []
    for c in commits[:20]:  # last 20 commits
        commit_date = c['date'][:10]  # YYYY-MM-DD
        # คำนวณ before/after metrics
        dates_sorted = sorted(daily.keys())
        try:
            idx = dates_sorted.index(commit_date)
            before = daily[dates_sorted[idx - 1]] if idx > 0 else None
            current = daily[commit_date]
            after = daily[dates_sorted[idx + 1]] if idx + 1 < len(dates_sorted) else None
        except (ValueError, IndexError):
            before = current = after = None

        points.append({
            'hash': c['hash'],
            'date': c['date'],
            'subject': c['subject'],
            'before_metrics': before,
            'current_metrics': current,
            'after_metrics': after,
        })
    return points


# ================================================================
# Main
# ================================================================
def main():
    log("=== Dashboard Extractor ===")
    log(f"Root: {ROOT}")
    log(f"Output: {OUT_DIR}")

    log("\n📊 Parsing pipeline logs...")
    runs = collect_pipeline_runs()
    log(f"  ✅ {len(runs)} runs parsed")

    log("\n📅 Building daily aggregates...")
    daily = build_daily_aggregates(runs)
    log(f"  ✅ {len(daily)} days of data")

    log("\n🌀 Fetching Sheet snapshot...")
    sheet = fetch_sheet_snapshot()
    log(f"  ✅ {len([v for v in sheet.values() if isinstance(v, int)])} sheets fetched")

    log("\n🔧 Collecting git log...")
    commits = collect_git_log(50)
    log(f"  ✅ {len(commits)} commits")

    log("\n🏆 Winner cache stats...")
    winners = winner_cache_stats()
    log(f"  ✅ {winners.get('total_winners', 0)} winners cached")

    log("\n⚡ Building inflection points...")
    inflections = build_inflection_points(commits, daily)
    log(f"  ✅ {len(inflections)} commits with impact data")

    # Compute current KPIs (latest run)
    latest = runs[-1] if runs else {}
    today_str = date.today().isoformat()
    today_daily = daily.get(today_str, {})

    kpis = {
        'pipeline_duration_today': today_daily.get('total_pipeline_sec', 0),
        'pipeline_duration_yesterday': None,  # compute
        'active_jobs': sheet.get('active_bidding', 0),
        'tor_jobs': sheet.get('tor_review', 0),
        'pending_jobs': sheet.get('pending_award', 0),
        'awarded_jobs': sheet.get('awarded_jobs', 0),
        'cancelled_jobs': sheet.get('cancelled_jobs', 0),
        'all_jobs_count': sheet.get('all_jobs', 0),
        'cloudflare_hits_today': today_daily.get('cloudflare_hits', 0),
        'total_winners': winners.get('total_winners', 0),
    }
    # Yesterday for comparison
    dates_sorted = sorted(daily.keys())
    if len(dates_sorted) >= 2:
        kpis['pipeline_duration_yesterday'] = daily[dates_sorted[-2]].get('total_pipeline_sec', 0)

    # ================================================================
    # RSS catalog stats
    # ================================================================
    log("\n📡 Collecting RSS catalog stats...")
    rss_catalog = rss_catalog_stats()
    log(f"  ✅ total={rss_catalog.get('total_depts', 0)} active={rss_catalog.get('active_depts', 0)} coverage={rss_catalog.get('coverage_pct', 0)}%")

    # ================================================================
    # Build final snapshot
    # ================================================================
    snapshot = {
        'generated_at': datetime.now().isoformat(),
        'version': 1,
        'kpis': kpis,
        'daily': daily,
        'runs': runs,
        'sheet_snapshot': sheet,
        'winners': winners,
        'commits': commits,
        'inflections': inflections,
        'rss_catalog': rss_catalog,
    }

    # Save to both locations: dashboard/data + dashboard/web/public
    snapshot_text = json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)
    out_file = OUT_DIR / "snapshot.json"
    out_file.write_text(snapshot_text, encoding='utf-8')
    public_file = PUBLIC_DIR / "snapshot.json"
    public_file.write_text(snapshot_text, encoding='utf-8')
    log(f"\n✅ Snapshot saved:")
    log(f"   {out_file} ({out_file.stat().st_size:,} bytes)")
    log(f"   {public_file} (web public)")

    # Pretty summary
    log("\n=== SUMMARY ===")
    log(f"  📅 Days tracked: {len(daily)}")
    log(f"  📊 Pipeline runs: {len(runs)}")
    log(f"  🔧 Git commits: {len(commits)}")
    log(f"  🏆 Winners: {winners.get('total_winners', 0)}")
    log(f"  ⚡ Inflections: {len(inflections)}")


if __name__ == "__main__":
    main()
