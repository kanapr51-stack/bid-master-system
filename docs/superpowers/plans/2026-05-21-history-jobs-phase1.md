# History Jobs Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate bid_history from Google Sheets → PostgreSQL, build competitor analytics layer, and add portal /history page

**Architecture:** ETL script migrates 2,154 existing rows; competitor_profiles materialized view aggregates per-TIN; Next.js portal page lets users search bidding history by job_id or company name/TIN

**Tech Stack:** Python (psycopg2 via db_client), PostgreSQL (Neon), Next.js App Router, TypeScript

---

### Task 1: ETL bid_history — Sheets → PostgreSQL

**Files:**
- Modify: `scripts/etl_sheet_to_db.py`

- [ ] **Step 1: Add `etl_bid_history()` function to etl_sheet_to_db.py**

Add after `etl_winners()`, before `main()`:

```python
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
    skipped = 0
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        def g(name: str, default: str = "") -> str:
            idx = h.get(name, -1)
            return r[idx] if 0 <= idx < len(r) else default

        job_id = g("job_id")
        # skip rows whose job_id doesn't exist in all_jobs (FK constraint)
        batch.append((
            job_id,
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

    # bid_history has no unique constraint → use execute_many directly
    # but skip rows where job_id not in all_jobs to avoid FK violations
    known_jobs = {r["job_id"] for r in db_client.fetch_all("SELECT job_id FROM all_jobs")}
    valid = [b for b in batch if b[0] in known_jobs]
    skipped = len(batch) - len(valid)
    if skipped:
        log(f"  Skipping {skipped} rows (job_id not in all_jobs)")

    log(f"  Inserting {len(valid)} rows…")
    db_client.execute_many(sql, valid)

    res = db_client.fetch_one("SELECT COUNT(*) as cnt FROM bid_history")
    log(f"  ✅ DB now has {res['cnt']} rows")
```

- [ ] **Step 2: Add `bid_history` to argparse choices and main() dispatch**

In `main()`, update `--table` choices and add `elif`:

```python
parser.add_argument("--table", choices=["all_jobs", "customers", "dept_catalog", "winners", "bid_history"])
```

And in the `elif` chain:
```python
elif args.table == "bid_history":
    etl_bid_history()
```

Also add `etl_bid_history()` call inside `if args.all or args.table is None:` block.

- [ ] **Step 3: Run ETL**

```bash
cd C:/Bid-Master-System
python scripts/etl_sheet_to_db.py --table bid_history
```

Expected output: `✅ DB now has ~2154 rows`

- [ ] **Step 4: Commit**

```bash
git add scripts/etl_sheet_to_db.py
git commit -m "feat(etl): add etl_bid_history() — migrate 2154 rows Sheets→PostgreSQL"
```

---

### Task 2: competitor_profiles Materialized View

**Files:**
- Modify: `scripts/db_schema.sql`

- [ ] **Step 1: Add materialized view to db_schema.sql**

Append to end of `scripts/db_schema.sql`:

```sql
-- ============================================================
-- competitor_profiles — aggregated bidder stats per TIN
-- (Materialized view, refresh after ETL or nightly)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS competitor_profiles AS
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
    ARRAY_AGG(DISTINCT aj.province ORDER BY aj.province)   AS provinces,
    ARRAY_AGG(DISTINCT aj.procurement_type
              ORDER BY aj.procurement_type)                 AS proc_types,
    AVG(
        CASE
            WHEN bh.price_proposal ~ '^[0-9]+(\.[0-9]+)?$'
             AND bh.price_agree    ~ '^[0-9]+(\.[0-9]+)?$'
             AND bh.price_agree::NUMERIC > 0
            THEN 100.0 * (bh.price_proposal::NUMERIC - bh.price_agree::NUMERIC)
                 / bh.price_proposal::NUMERIC
        END
    )                                                       AS avg_discount_pct
FROM bid_history bh
JOIN all_jobs aj ON aj.job_id = bh.job_id
WHERE bh.bidder_tin <> ''
GROUP BY bh.bidder_tin
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_profiles_tin
    ON competitor_profiles(bidder_tin);
CREATE INDEX IF NOT EXISTS idx_competitor_profiles_wins
    ON competitor_profiles(total_wins DESC);
```

- [ ] **Step 2: Run schema on Neon PostgreSQL**

```bash
python - <<'EOF'
import sys; sys.path.insert(0, 'scripts')
import db_client

sql = open('scripts/db_schema.sql').read()
# Run only the materialized view block
view_sql = """
CREATE MATERIALIZED VIEW IF NOT EXISTS competitor_profiles AS
SELECT
    bh.bidder_tin,
    MAX(bh.bidder_name) AS company_name,
    COUNT(DISTINCT bh.job_id) AS total_bids,
    COUNT(DISTINCT CASE WHEN bh.is_winner THEN bh.job_id END) AS total_wins,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN bh.is_winner THEN bh.job_id END) / NULLIF(COUNT(DISTINCT bh.job_id), 0), 1) AS win_rate_pct,
    BOOL_OR(bh.is_sme) AS is_sme,
    BOOL_OR(bh.is_joint_venture) AS has_jv,
    MIN(aj.publish_date) AS first_seen,
    MAX(aj.publish_date) AS last_seen,
    ARRAY_AGG(DISTINCT aj.province ORDER BY aj.province) AS provinces,
    ARRAY_AGG(DISTINCT aj.procurement_type ORDER BY aj.procurement_type) AS proc_types,
    AVG(CASE WHEN bh.price_proposal ~ '^[0-9]+(\\.[0-9]+)?$' AND bh.price_agree ~ '^[0-9]+(\\.[0-9]+)?$' AND bh.price_agree::NUMERIC > 0 THEN 100.0 * (bh.price_proposal::NUMERIC - bh.price_agree::NUMERIC) / bh.price_proposal::NUMERIC END) AS avg_discount_pct
FROM bid_history bh
JOIN all_jobs aj ON aj.job_id = bh.job_id
WHERE bh.bidder_tin <> ''
GROUP BY bh.bidder_tin
WITH DATA;
CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_profiles_tin ON competitor_profiles(bidder_tin);
CREATE INDEX IF NOT EXISTS idx_competitor_profiles_wins ON competitor_profiles(total_wins DESC);
"""
db_client.execute(view_sql)
r = db_client.fetch_one("SELECT COUNT(*) as cnt FROM competitor_profiles")
print(f"competitor_profiles: {r['cnt']} rows")
EOF
```

- [ ] **Step 3: Commit**

```bash
git add scripts/db_schema.sql
git commit -m "feat(db): add competitor_profiles materialized view"
```

---

### Task 3: bid_history_queries.py — Python Query Helpers

**Files:**
- Create: `scripts/bid_history_queries.py`

- [ ] **Step 1: Create the file**

```python
"""
bid_history_queries.py — Query helpers for portal API routes

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
    {
      job: {job_id, title, department, budget, deadline, province},
      bidders: [{bidder_name, bidder_tin, price_proposal, price_agree,
                 is_winner, is_sme, is_joint_venture, jv_partners, result_flag}],
      total: int
    }
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
        ORDER BY is_winner DESC, price_agree NULLIF('', NULL)
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
    {
      profile: {bidder_tin, company_name, total_bids, total_wins, win_rate_pct,
                is_sme, has_jv, first_seen, last_seen, provinces, proc_types, avg_discount_pct},
      recent_jobs: [{job_id, title, department, province, publish_date,
                     is_winner, price_proposal, price_agree}]  (last 20)
    }
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
    # Convert arrays to lists for JSON
    p["provinces"] = list(p.get("provinces") or [])
    p["proc_types"] = list(p.get("proc_types") or [])
    return {
        "profile": p,
        "recent_jobs": [dict(r) for r in recent],
    }


def search_competitors(query: str, limit: int = 20) -> list[dict]:
    """
    Search competitor_profiles by company name (ILIKE).
    Returns list of profile dicts.
    """
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


def get_jobs_shared_with(tin: str, limit: int = 10) -> list[dict]:
    """
    Jobs where our company (BSC) and the given TIN both bid.
    Assumes our TIN is known — filter by province = target area.
    Returns jobs sorted by most recent.
    """
    rows = db_client.fetch_all(
        """
        SELECT DISTINCT bh.job_id, aj.title, aj.department, aj.province, aj.publish_date, aj.budget
        FROM bid_history bh
        JOIN all_jobs aj ON aj.job_id = bh.job_id
        WHERE bh.bidder_tin = %s
          AND (aj.province = 'นครพนม' OR aj.province = 'บึงกาฬ')
        ORDER BY aj.publish_date DESC
        LIMIT %s
        """,
        (tin, limit)
    )
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Commit**

```bash
git add scripts/bid_history_queries.py
git commit -m "feat(scripts): add bid_history_queries.py — get_job_bidders, get_competitor_profile, search"
```

---

### Task 4: Next.js API Routes

**Files:**
- Create: `dashboard/web/src/app/api/portal/history/job/[jobId]/route.ts`
- Create: `dashboard/web/src/app/api/portal/history/company/route.ts`

- [ ] **Step 1: Create `GET /api/portal/history/job/[jobId]`**

```typescript
// dashboard/web/src/app/api/portal/history/job/[jobId]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { queryJobBidders } from '@/lib/bid-history';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Invalid session' }, { status: 401 });

  const { jobId } = await params;
  const data = await queryJobBidders(jobId);
  if ('error' in data) return NextResponse.json(data, { status: 404 });
  return NextResponse.json(data);
}
```

- [ ] **Step 2: Create `GET /api/portal/history/company?tin=X` and `?q=name`**

```typescript
// dashboard/web/src/app/api/portal/history/company/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { queryCompetitorProfile, searchCompetitors } from '@/lib/bid-history';

export async function GET(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Invalid session' }, { status: 401 });

  const { searchParams } = new URL(req.url);
  const tin = searchParams.get('tin');
  const q = searchParams.get('q');

  if (tin) {
    const data = await queryCompetitorProfile(tin);
    if ('error' in data) return NextResponse.json(data, { status: 404 });
    return NextResponse.json(data);
  }
  if (q && q.length >= 2) {
    const data = await searchCompetitors(q);
    return NextResponse.json({ results: data });
  }
  return NextResponse.json({ error: 'Provide tin or q param' }, { status: 400 });
}
```

- [ ] **Step 3: Create `dashboard/web/src/lib/bid-history.ts` — DB query bridge**

```typescript
// dashboard/web/src/lib/bid-history.ts
/**
 * Server-side DB queries for bid_history and competitor_profiles.
 * Uses postgres (Neon) directly via @neondatabase/serverless or pg.
 */
import { neon } from '@neondatabase/serverless';

function sql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error('DATABASE_URL not set');
  return neon(url);
}

export interface JobBiddersResult {
  job: { job_id: string; title: string; department: string; budget: string; deadline: string; province: string };
  bidders: BidderRow[];
  total: number;
}

export interface BidderRow {
  bidder_name: string;
  bidder_tin: string;
  price_proposal: string;
  price_agree: string;
  is_winner: boolean;
  is_sme: boolean;
  is_joint_venture: boolean;
  jv_partners: string;
  result_flag: string;
  consider_desc: string;
}

export interface CompetitorProfile {
  bidder_tin: string;
  company_name: string;
  total_bids: number;
  total_wins: number;
  win_rate_pct: number;
  is_sme: boolean;
  has_jv: boolean;
  first_seen: string;
  last_seen: string;
  provinces: string[];
  proc_types: string[];
  avg_discount_pct: number | null;
}

export interface CompetitorProfileResult {
  profile: CompetitorProfile;
  recent_jobs: RecentJobRow[];
}

export interface RecentJobRow {
  job_id: string;
  title: string;
  department: string;
  province: string;
  publish_date: string;
  is_winner: boolean;
  price_proposal: string;
  price_agree: string;
}

export async function queryJobBidders(jobId: string): Promise<JobBiddersResult | { error: string }> {
  const db = sql();
  const [jobRows, bidderRows] = await Promise.all([
    db`SELECT job_id, title, department, budget, deadline, province FROM all_jobs WHERE job_id = ${jobId}`,
    db`SELECT bidder_name, bidder_tin, price_proposal, price_agree, is_winner, is_sme, is_joint_venture, jv_partners, result_flag, consider_desc
       FROM bid_history WHERE job_id = ${jobId} ORDER BY is_winner DESC, price_agree`,
  ]);
  if (!jobRows.length) return { error: 'not_found' };
  return { job: jobRows[0] as JobBiddersResult['job'], bidders: bidderRows as BidderRow[], total: bidderRows.length };
}

export async function queryCompetitorProfile(tin: string): Promise<CompetitorProfileResult | { error: string }> {
  const db = sql();
  const [profileRows, recentRows] = await Promise.all([
    db`SELECT * FROM competitor_profiles WHERE bidder_tin = ${tin}`,
    db`SELECT bh.job_id, aj.title, aj.department, aj.province, aj.publish_date, bh.is_winner, bh.price_proposal, bh.price_agree
       FROM bid_history bh JOIN all_jobs aj ON aj.job_id = bh.job_id
       WHERE bh.bidder_tin = ${tin} ORDER BY aj.publish_date DESC LIMIT 20`,
  ]);
  if (!profileRows.length) return { error: 'not_found' };
  return { profile: profileRows[0] as CompetitorProfile, recent_jobs: recentRows as RecentJobRow[] };
}

export async function searchCompetitors(query: string): Promise<CompetitorProfile[]> {
  const db = sql();
  const rows = await db`
    SELECT bidder_tin, company_name, total_bids, total_wins, win_rate_pct,
           is_sme, provinces, first_seen, last_seen
    FROM competitor_profiles
    WHERE company_name ILIKE ${'%' + query + '%'}
    ORDER BY total_bids DESC
    LIMIT 20
  `;
  return rows as CompetitorProfile[];
}
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/web/src/app/api/portal/history/
git add dashboard/web/src/lib/bid-history.ts
git commit -m "feat(portal-api): add /api/portal/history/job/[jobId] and /company routes"
```

---

### Task 5: Portal History Page

**Files:**
- Create: `dashboard/web/src/app/portal/history/page.tsx`
- Create: `dashboard/web/src/app/portal/history/_client.tsx`

- [ ] **Step 1: Create server page**

```typescript
// dashboard/web/src/app/portal/history/page.tsx
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import HistoryClient from './_client';

export default async function HistoryPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');
  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  return <HistoryClient />;
}
```

- [ ] **Step 2: Create client component `_client.tsx`**

```typescript
// dashboard/web/src/app/portal/history/_client.tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { TopBar, ButlerNote, Icons } from '../_ui';

type BidderRow = {
  bidder_name: string; bidder_tin: string; price_proposal: string;
  price_agree: string; is_winner: boolean; is_sme: boolean;
  is_joint_venture: boolean; jv_partners: string; result_flag: string;
};

type JobResult = {
  job: { job_id: string; title: string; department: string; budget: string; deadline: string; province: string };
  bidders: BidderRow[];
  total: number;
};

type ProfileResult = {
  profile: {
    bidder_tin: string; company_name: string; total_bids: number; total_wins: number;
    win_rate_pct: number; is_sme: boolean; avg_discount_pct: number | null;
    provinces: string[]; first_seen: string; last_seen: string;
  };
  recent_jobs: {
    job_id: string; title: string; department: string; province: string;
    publish_date: string; is_winner: boolean; price_proposal: string; price_agree: string;
  }[];
};

function fmt(n: string | number | null): string {
  if (!n) return '—';
  const num = typeof n === 'string' ? parseFloat(n) : n;
  if (isNaN(num)) return String(n);
  return num.toLocaleString('th-TH');
}

export default function HistoryClient() {
  const [tab, setTab] = useState<'job' | 'company'>('job');
  const [jobId, setJobId] = useState('');
  const [companyQ, setCompanyQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobResult, setJobResult] = useState<JobResult | null>(null);
  const [profileResult, setProfileResult] = useState<ProfileResult | null>(null);
  const [searchResults, setSearchResults] = useState<ProfileResult['profile'][]>([]);
  const [error, setError] = useState('');

  async function searchJob() {
    if (!jobId.trim()) return;
    setLoading(true); setError(''); setJobResult(null);
    try {
      const res = await fetch(`/api/portal/history/job/${jobId.trim()}`);
      if (!res.ok) { setError('ไม่พบข้อมูลงานนี้'); return; }
      setJobResult(await res.json());
    } catch { setError('เกิดข้อผิดพลาด'); }
    finally { setLoading(false); }
  }

  async function searchCompany() {
    if (!companyQ.trim()) return;
    setLoading(true); setError(''); setSearchResults([]); setProfileResult(null);
    try {
      const res = await fetch(`/api/portal/history/company?q=${encodeURIComponent(companyQ.trim())}`);
      if (!res.ok) { setError('เกิดข้อผิดพลาด'); return; }
      const data = await res.json();
      setSearchResults(data.results ?? []);
    } catch { setError('เกิดข้อผิดพลาด'); }
    finally { setLoading(false); }
  }

  async function loadProfile(tin: string) {
    setLoading(true); setError('');
    try {
      const res = await fetch(`/api/portal/history/company?tin=${encodeURIComponent(tin)}`);
      if (!res.ok) { setError('ไม่พบข้อมูลบริษัทนี้'); return; }
      setProfileResult(await res.json());
      setSearchResults([]);
    } catch { setError('เกิดข้อผิดพลาด'); }
    finally { setLoading(false); }
  }

  return (
    <div className="p-page">
      <TopBar title="ประวัติการประมูล" back="/portal/world" />
      <ButlerNote>ค้นหาประวัติผู้เสนอราคาโดย Job ID หรือชื่อบริษัท</ButlerNote>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['job', 'company'] as const).map(t => (
          <button key={t} className={`p-btn${tab === t ? '' : '-outline'}`}
            onClick={() => { setTab(t); setError(''); setJobResult(null); setProfileResult(null); setSearchResults([]); }}>
            {t === 'job' ? '🔍 ค้นหางาน' : '🏢 ค้นหาบริษัท'}
          </button>
        ))}
      </div>

      {tab === 'job' && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <input className="p-input" placeholder="Job ID เช่น 6701234567" value={jobId}
            onChange={e => setJobId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && searchJob()} style={{ flex: 1 }} />
          <button className="p-btn" onClick={searchJob} disabled={loading}>
            {loading ? '…' : 'ค้นหา'}
          </button>
        </div>
      )}

      {tab === 'company' && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <input className="p-input" placeholder="ชื่อบริษัท หรือ เลขที่ผู้เสียภาษี" value={companyQ}
            onChange={e => setCompanyQ(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && searchCompany()} style={{ flex: 1 }} />
          <button className="p-btn" onClick={searchCompany} disabled={loading}>
            {loading ? '…' : 'ค้นหา'}
          </button>
        </div>
      )}

      {error && <div className="p-card" style={{ color: 'var(--danger)', marginBottom: 12 }}>{error}</div>}

      {/* Job bidders result */}
      {jobResult && (
        <div>
          <div className="p-card" style={{ marginBottom: 12 }}>
            <div className="p-label">งาน</div>
            <div className="p-h3" style={{ marginBottom: 4 }}>{jobResult.job.title}</div>
            <div className="p-fg-mute" style={{ fontSize: 12 }}>
              {jobResult.job.department} · {jobResult.job.province} · งบ {fmt(jobResult.job.budget)} บาท · ปิด {jobResult.job.deadline}
            </div>
          </div>
          <div className="p-label" style={{ marginBottom: 8 }}>ผู้เสนอราคา {jobResult.total} ราย</div>
          {jobResult.bidders.map((b, i) => (
            <div key={i} className="p-card" style={{ marginBottom: 8, borderColor: b.is_winner ? 'var(--accent-deep)' : 'var(--border)', background: b.is_winner ? 'var(--gold-glow)' : 'var(--surface)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <span style={{ fontWeight: 600 }}>{b.bidder_name}</span>
                  {b.is_winner && <span className="p-chip" style={{ marginLeft: 8, background: 'var(--accent)', color: '#000' }}>ชนะ</span>}
                  {b.is_sme && <span className="p-chip" style={{ marginLeft: 4 }}>SME</span>}
                </div>
                <button className="p-btn-outline" style={{ fontSize: 11, padding: '2px 8px' }}
                  onClick={() => loadProfile(b.bidder_tin)}>ดูโปรไฟล์</button>
              </div>
              <div className="p-fg-mute" style={{ fontSize: 11, marginTop: 4 }}>
                TIN: {b.bidder_tin || '—'} · เสนอ {fmt(b.price_proposal)} · ตกลง {fmt(b.price_agree) || '—'}
              </div>
              {b.is_joint_venture && <div style={{ fontSize: 11, color: 'var(--accent)' }}>JV: {b.jv_partners}</div>}
            </div>
          ))}
        </div>
      )}

      {/* Company search results */}
      {searchResults.length > 0 && (
        <div>
          <div className="p-label" style={{ marginBottom: 8 }}>พบ {searchResults.length} บริษัท</div>
          {searchResults.map((p, i) => (
            <div key={i} className="p-card" style={{ marginBottom: 8, cursor: 'pointer' }} onClick={() => loadProfile(p.bidder_tin)}>
              <div style={{ fontWeight: 600 }}>{p.company_name}</div>
              <div className="p-fg-mute" style={{ fontSize: 11 }}>
                TIN: {p.bidder_tin} · {p.total_bids} งาน · ชนะ {p.total_wins} ({p.win_rate_pct}%)
                {p.is_sme && ' · SME'}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Company profile */}
      {profileResult && (
        <div>
          <button className="p-btn-outline" style={{ marginBottom: 12, fontSize: 12 }}
            onClick={() => { setProfileResult(null); setSearchResults([]); }}>← กลับ</button>
          <div className="p-card" style={{ marginBottom: 12, borderColor: 'var(--accent-deep)', background: 'var(--gold-glow)' }}>
            <div className="p-h3">{profileResult.profile.company_name}</div>
            <div className="p-fg-mute" style={{ fontSize: 11, marginBottom: 8 }}>TIN: {profileResult.profile.bidder_tin}</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                ['งานทั้งหมด', profileResult.profile.total_bids, ''],
                ['ชนะการประมูล', profileResult.profile.total_wins, ''],
                ['อัตราชนะ', profileResult.profile.win_rate_pct, '%'],
                ['Avg Discount', profileResult.profile.avg_discount_pct?.toFixed(1) ?? '—', '%'],
              ].map(([label, value, unit]) => (
                <div key={String(label)} className="p-card" style={{ textAlign: 'center' }}>
                  <div className="p-fg-mute" style={{ fontSize: 10 }}>{label}</div>
                  <div className="p-display" style={{ fontSize: 22 }}>{value}<span style={{ fontSize: 12 }}>{unit}</span></div>
                </div>
              ))}
            </div>
            {profileResult.profile.provinces?.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 11 }}>จังหวัด: {profileResult.profile.provinces.join(', ')}</div>
            )}
          </div>
          <div className="p-label" style={{ marginBottom: 8 }}>20 งานล่าสุด</div>
          {profileResult.recent_jobs.map((j, i) => (
            <div key={i} className="p-card" style={{ marginBottom: 6, borderColor: j.is_winner ? 'var(--accent-deep)' : 'var(--border)', cursor: 'pointer' }}
              onClick={() => { setTab('job'); setJobId(j.job_id); setProfileResult(null); }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 13 }}>{j.title.slice(0, 60)}{j.title.length > 60 ? '…' : ''}</span>
                {j.is_winner && <span className="p-chip" style={{ background: 'var(--accent)', color: '#000', fontSize: 10 }}>ชนะ</span>}
              </div>
              <div className="p-fg-mute" style={{ fontSize: 11 }}>
                {j.department} · {j.province} · {j.publish_date} · เสนอ {fmt(j.price_proposal)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add link to History from World page**

In `dashboard/web/src/app/portal/world/_client.tsx`, add a SumCard linking to `/portal/history` (after existing SumCards).

- [ ] **Step 4: Commit**

```bash
git add dashboard/web/src/app/portal/history/
git commit -m "feat(portal): add /portal/history page — job bidder lookup + competitor profile"
```
